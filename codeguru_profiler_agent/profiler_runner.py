import logging

from codeguru_profiler_agent.metrics.with_timer import with_timer
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from codeguru_profiler_agent.sampler import Sampler
from codeguru_profiler_agent.utils.scheduler import Scheduler

logger = logging.getLogger(__name__)


class ProfilerRunner:
    """
    ProfilerRunner instantiates and orchestrates all components required for running the profiler.
    It implements and checks the kill switch and cpu limit every time before it samples.
    This class should only be accessed by Profiler for controlling and monitoring the profiler.

    NOTE: If CPU usage exceed CPU limit, profiler will be terminated immediately without any attempt to flush
    the existing data.
    NOTE: Memory limit check is implemented in LocalAggregator
    """

    def __init__(self, environment=dict()):
        """
        :param environment: dependency container dictionary for the current profiler
        :param sampling_interval: (required inside environment) delay between profile reports in datetime.timedelta
        :param killswitch_filepath: (required inside environment) filepath pointing to the killswitch file. This path
            gets checked every time the profiler samples; the profiler is immediately stopped if this file exists.
        :param collector: (required inside environment) collector object to handle sample processing
        :param initial_sampling_interval: (required inside environment) Initial delay signal sampler takes for starting
        to sample
        :param profiler_thread_name: (required inside environment) Thread name used for running the
        report_orchestration_scheduler
        """
        self.timer = environment.get("timer")
        self.sampler = environment.get("sampler") or Sampler(environment=environment)

        self.scheduler = Scheduler(
            command=self._profiling_command,
            delay_provider=lambda: AgentConfiguration.get().sampling_interval,
            initial_delay=environment["initial_sampling_interval"],
            thread_name=environment["profiler_thread_name"])
        self.collector = environment["collector"]
        self.profiler_disabler = environment["profiler_disabler"]
        self.is_profiling_in_progress = False
        self._first_execution = True

    def start(self):
        """
        Start running the profiler.
        Note: Profiler will not start if killswitch file exists.

        :return: True if the profiler was started successfully; False otherwise.
        """
        if self.profiler_disabler.should_stop_profiling():
            logger.info("Profiler will not start.")
            return False
        self.scheduler.start()
        return True

    def _refresh_configuration(self):
        self.collector.refresh_configuration()
        self.is_profiling_in_progress = AgentConfiguration.get().should_profile
        if self.is_profiling_in_progress:
            self.scheduler.update_delay_provider(lambda: AgentConfiguration.get().sampling_interval)
        else:
            # if we should not profile we can simply wait for the reporting interval and call again at that time.
            self.scheduler.update_delay_provider(lambda: AgentConfiguration.get().reporting_interval)

    def _profiling_command(self):
        try:
            if self._first_execution:
                self.collector.setup()
                self._first_execution = False
            sample_result = self._run_profiler()
            if sample_result.success and sample_result.is_end_of_cycle:
                if self.profiler_disabler.should_stop_profiling(profile=self.collector.profile):
                    return False
                self.collector.reset()
                return True
            return sample_result.success
        except:
            logger.info("An unexpected issue caused the profiling command to terminate.", exc_info=True)
            return False

    @with_timer("runProfiler")
    def _run_profiler(self):
        if self.profiler_disabler.should_stop_sampling(self.collector.profile):
            return RunProfilerStatus(success=False, is_end_of_cycle=False)

        if not self.is_profiling_in_progress:
            self._refresh_configuration()

        # after the refresh we may be working on a profile
        if self.is_profiling_in_progress:
            if self.collector.flush(reset=False):
                self.is_profiling_in_progress = False
                return RunProfilerStatus(success=True, is_end_of_cycle=True)
            self._sample_and_aggregate()
        return RunProfilerStatus(success=True, is_end_of_cycle=False)

    @with_timer("sampleAndAggregate")
    def _sample_and_aggregate(self):
        sample = self.sampler.sample()
        self.collector.add(sample)

    def is_running(self):
        return self.scheduler.is_running()

    def is_paused(self):
        return self.scheduler.is_paused()

    def stop(self):
        """
        Terminate profiler gracefully.
        It terminates the profiling thread and flushes existing profile to the backend.
        """
        self.scheduler.stop()
        self.collector.flush(force=True)
        self.is_profiling_in_progress = False

    def resume(self, block=False):
        """
        Will signal the scheduler that profiling should resume.

        :param block: if True, we will not return from this function before the change is applied, default is False.
        """
        self.collector.profile.resume()
        self.scheduler.resume(block)

    def pause(self, block=False):
        """
        Will signal the scheduler that profiling should pause.

        :param block: if True, we will not return from this function before the change is applied, default is False.
        """
        self.scheduler.pause(block)
        self.collector.profile.pause()


class RunProfilerStatus:
    def __init__(self, success, is_end_of_cycle):
        self.success = success
        self.is_end_of_cycle = is_end_of_cycle
