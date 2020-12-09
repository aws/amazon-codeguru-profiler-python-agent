import logging
import time
import datetime

from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from codeguru_profiler_agent.metrics.with_timer import with_timer
from codeguru_profiler_agent.model.profile import Profile
from codeguru_profiler_agent.utils.time import current_milli_time

logger = logging.getLogger(__name__)


class LocalAggregator:
    """
    The local aggregator receives samples reported by the sampler and aggregates them into one profile.
    When flush is called, the aggregator will first check whether the profile should be flushed or not (e.g.
    whether the reporting interval is reached or not) and the profile will be reported through the configured reporter.
    Each time we sample, the aggregator will check if the memory usage of the profile exceeds the memory limit.
    If memory limit is violated, a force_flush will be executed first; if the last flush action happened within
    the minimum time for reporting, OverMemoryLimitException will be raised.
    """

    def __init__(self, reporter, environment=dict()):
        """
        :param reporter: reporter object used for reporting profiles
        :param environment: dependency container dictionary for the current profiler
        :param profiling_group_name: (required inside environment) name of the profiling group
        :param memory_limit_bytes: (required inside environment) memory limit (Bytes) for profiler
        :param host_weight: (required inside environment) scale factor used to rescale the profile collected in this
            host to make the profile representative of the whole fleet
        :param timer: (required inside environment) timer to be used for metrics
        :param profile_factory: (inside environment) the factory to created profiler; default Profile.
        :param clock: (inside environment) clock to be used; default is time.time
        """
        self.reporter = reporter
        self.profiling_group_name = environment["profiling_group_name"]
        self.host_weight = environment["host_weight"]
        self.timer = environment["timer"]

        self.profile_factory = environment.get("profile_factory") or Profile
        self.clock = environment.get("clock") or time.time

        self.profile = None
        self.memory_limit_bytes = environment["memory_limit_bytes"]
        self.last_report_attempted = current_milli_time(clock=self.clock)

        self._reset()

    def add(self, sample):
        """
        Aggregate reported sample into the profile
        :param sample: Sample instance reported by Sampler
        """
        self._aggregate_sample(sample)
        self._check_memory_limit()

    def setup(self):
        self.reporter.setup()

    @with_timer("aggregateThreadDumps")
    def _aggregate_sample(self, sample):
        self.profile.add(sample)

    def _check_memory_limit(self):
        if self.profile.get_memory_usage_bytes() > self.memory_limit_bytes:
            if self._is_under_min_reporting_time(
                    current_milli_time(clock=self.clock)):
                raise OverMemoryLimitException(
                    "Profiler memory usage limit has been reached")
            self.flush(force=True)

    def _reset(self):
        self.profile = self.profile_factory(
            profiling_group_name=self.profiling_group_name,
            sampling_interval_seconds=AgentConfiguration.get().sampling_interval.total_seconds(),
            host_weight=self.host_weight,
            start=current_milli_time(clock=self.clock),
            clock=self.clock
        )
        self.timer.reset()

    @with_timer("flush")
    def flush(self, force=False):
        now = current_milli_time(clock=self.clock)
        reported = False
        if not force and not self._is_over_reporting_interval(now):
            return False

        if self._is_under_min_reporting_time(now):
            logger.info("Dropping the profile as it is under the minimum reporting time")
        else:
            self._report_profile(now)
            reported = True

        if force or reported:
            self._reset()
        return reported

    def refresh_configuration(self):
        self.reporter.refresh_configuration()

    def _report_profile(self, now):
        self.last_report_attempted = now
        self._add_overhead_metric_to_profile()
        self.profile.end = now
        logger.info("Attempting to report profile data: " + str(self.profile))
        if self.profile.is_empty():
            logger.info("Report was cancelled because it was empty")
            return False
        return self.reporter.report(self.profile)

    def _is_under_min_reporting_time(self, now):
        return AgentConfiguration.get().is_under_min_reporting_time(now - self.last_report_attempted)

    def _is_over_reporting_interval(self, now):
        return AgentConfiguration.get().is_over_reporting_interval(now - self.last_report_attempted)

    def _add_overhead_metric_to_profile(self):
        run_profiler_metric = self.timer and self.timer.get_metric("runProfiler")

        # By default, if overhead_ms is 0 in Profile, it will be treated as overhead not available during encoding.
        run_profiler_metric_seconds = run_profiler_metric.total if run_profiler_metric else 0
        self.profile.set_overhead_ms(duration_timedelta=datetime.timedelta(seconds=run_profiler_metric_seconds))


class OverMemoryLimitException(Exception):
    pass
