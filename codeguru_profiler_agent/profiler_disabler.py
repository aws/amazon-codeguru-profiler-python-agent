import os
import time
import logging
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from codeguru_profiler_agent.utils.time import current_milli_time

logger = logging.getLogger(__name__)
CHECK_KILLSWITCH_FILE_INTERVAL_SECONDS = 60
MINIMUM_MEASURES_IN_DURATION_METRICS = 20
MINIMUM_SAMPLES_IN_PROFILE = 5


class ProfilerDisabler:
    """
    This class encapsulates all checks that can disable profiler
    """

    def __init__(self, environment, clock=time.time):
        self.cpu_usage_check = CpuUsageCheck(environment['timer'])
        self.killswitch = KillSwitch(environment['killswitch_filepath'], clock)
        self.memory_limit_bytes = environment['memory_limit_bytes']

    def should_stop_profiling(self, profile=None):
        return (self.killswitch.is_killswitch_on()
                or self.cpu_usage_check.is_cpu_usage_limit_reached(profile)
                or profile is not None and self._is_memory_limit_reached(profile))

    def _is_memory_limit_reached(self, profile):
        return profile.get_memory_usage_bytes() > self.memory_limit_bytes


class CpuUsageCheck:
    """
    Checks for process duration: we measure the actual wall clock duration of running the profiler, if this duration
    becomes too long compared to the sampling interval, we stop profiling.
    """

    def __init__(self, timer):
        self.timer = timer

    def is_cpu_usage_limit_reached(self, profile=None):
        profiler_metric = self.timer.metrics.get("runProfiler")
        if not profiler_metric or profiler_metric.counter < MINIMUM_MEASURES_IN_DURATION_METRICS:
            return False

        sampling_interval_seconds = self._get_average_sampling_interval_seconds(profile)
        used_time_percentage = 100 * profiler_metric.average() / sampling_interval_seconds

        if used_time_percentage >= AgentConfiguration.get().cpu_limit_percentage:
            logger.debug(self.timer.metrics)
            logger.info(
                "Profiler cpu usage limit reached: {:.2f} % (limit: {:.2f} %), will stop CodeGuru Profiler.".format(
                    used_time_percentage, AgentConfiguration.get().cpu_limit_percentage))
            return True
        else:
            return False

    @staticmethod
    def _get_average_sampling_interval_seconds(profile):
        if profile is None or profile.total_sample_count < MINIMUM_SAMPLES_IN_PROFILE:
            return AgentConfiguration.get().sampling_interval.total_seconds()
        return (profile.get_active_millis_since_start() / profile.total_sample_count) / 1000


class KillSwitch:
    """
    Checks for a kill switch file: if a file with a specific name is present in the file system we stop profiling.
    """

    def __init__(self, killswitch_filepath, clock=time.time):
        self.killswitch_filepath = killswitch_filepath
        self.last_check_for_file_time = None
        self.last_check_for_file_result = False
        self.clock = clock

    def is_killswitch_on(self):
        now = self.clock()
        should_check_file = self.last_check_for_file_time is None or \
                            now - self.last_check_for_file_time > CHECK_KILLSWITCH_FILE_INTERVAL_SECONDS
        if should_check_file:
            self.last_check_for_file_result = os.path.isfile(self.killswitch_filepath)
            self.last_check_for_file_time = now
            if self.last_check_for_file_result:
                logger.info(
                    "Found kill-switch file at {}, will stop CodeGuru Profiler.".format(self.killswitch_filepath))
        return self.last_check_for_file_result
