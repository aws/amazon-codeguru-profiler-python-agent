import pytest

from datetime import timedelta

from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from codeguru_profiler_agent.utils.time import current_milli_time
from test.pytestutils import before
from mock import MagicMock, call

from codeguru_profiler_agent.profiler import DEFAULT_REPORTING_INTERVAL, \
    DEFAULT_MEMORY_LIMIT_BYTES, Profiler, INITIAL_MINIMUM_REPORTING_INTERVAL, DEFAULT_SAMPLING_INTERVAL
from codeguru_profiler_agent.sdk_reporter.sdk_reporter import SdkReporter
from codeguru_profiler_agent.local_aggregator import LocalAggregator, OverMemoryLimitException
from codeguru_profiler_agent.metrics.timer import Timer
from codeguru_profiler_agent.metrics.metric import Metric
from codeguru_profiler_agent.model.profile import Profile
from codeguru_profiler_agent.model.sample import Sample

CURRENT_TIME_FOR_TESTING_MILLI = 1528887859058
CURRENT_TIME_FOR_TESTING_SECOND = 1528887859.058

TEST_PROFILING_GROUP_NAME = "test-application"
TEST_SAMPLING_INTERVAL = 0.5
TEST_HOST_WEIGHT = 1.0

ONE_SECOND = timedelta(seconds=1)


def mock_timer():
    mock_timer = MagicMock(name="timer", spec=Timer)
    mock_timer.get_metric.return_value = None
    return mock_timer


def assert_profile_is_reset(profile_factory, clock):
    profile_factory.assert_called_once_with(
        profiling_group_name=TEST_PROFILING_GROUP_NAME, host_weight=TEST_HOST_WEIGHT,
        sampling_interval_seconds=TEST_SAMPLING_INTERVAL, start=current_milli_time(clock), clock=clock)


class TestLocalAggregator:
    @before
    def before(self):
        self.mock_reporter = MagicMock(name="reporter", spec=SdkReporter)
        self.mock_profile = MagicMock(name="profile", spec=Profile)
        self.mock_profile_factory = MagicMock(
            name="profile_factory",
            spec=Profile,
            return_value=self.mock_profile)
        self.timer = mock_timer()
        self.time_now = CURRENT_TIME_FOR_TESTING_SECOND
        self.clock = lambda: self.time_now
        self.reporting_interval = DEFAULT_REPORTING_INTERVAL

        self.environment = {
            "profiling_group_name": TEST_PROFILING_GROUP_NAME,
            "sampling_interval": timedelta(seconds=TEST_SAMPLING_INTERVAL),
            "host_weight": TEST_HOST_WEIGHT,
            "profile_factory": self.mock_profile_factory,
            "memory_limit_bytes": DEFAULT_MEMORY_LIMIT_BYTES,
            "clock": self.clock,
            "timer": self.timer,
        }

        self.configuration = {
            "reporter": self.mock_reporter,
            "environment": self.environment,
        }

        AgentConfiguration.set(
            AgentConfiguration(
                should_profile=True,
                sampling_interval=timedelta(seconds=TEST_SAMPLING_INTERVAL),
                minimum_time_reporting=INITIAL_MINIMUM_REPORTING_INTERVAL,
                reporting_interval=self.reporting_interval,
                max_stack_depth=999,
                cpu_limit_percentage=10
            )
        )

        assert len(self.environment.keys()) == 7
        self.profiler = Profiler(profiling_group_name=TEST_PROFILING_GROUP_NAME, environment_override=self.environment)
        assert len(self.environment.keys()) == 6

        self.subject = LocalAggregator(**self.configuration)
        self.mock_profile_factory.reset_mock()
        self.timer.reset_mock()

        def move_clock_to(duration_timedelta):
            self.time_now = \
                CURRENT_TIME_FOR_TESTING_SECOND + duration_timedelta.total_seconds()

        self.move_clock_to = move_clock_to

    class TestAdd:
        @before
        def before(self):
            self.mock_profile.get_memory_usage_bytes = MagicMock(
                return_value=DEFAULT_MEMORY_LIMIT_BYTES - 1)
            self.sample = Sample([["method1", "method2"]])
            self.move_clock_to(self.reporting_interval - ONE_SECOND)

        def test_adding_sample_to_profile_successfully(self):
            self.subject.add(self.sample)

            self.mock_profile.add.assert_called_once_with(self.sample)

        def test_exception_raised_is_propagated(self):
            self.mock_profile.add.side_effect = ValueError("Foo")
            with pytest.raises(ValueError):
                self.subject.add(self.sample)

    class TestFlush:
        class TestWhenReportingIntervalReached:
            @before
            def before(self):
                self.mock_profile.get_memory_usage_bytes = MagicMock(
                    return_value=DEFAULT_MEMORY_LIMIT_BYTES - 1)
                self.move_clock_to(self.reporting_interval + ONE_SECOND)
                self.mock_profile.is_empty = MagicMock(
                    return_value=False)

            def test_it_reports(self):
                self.mock_reporter.report.return_value = True
                self.subject.flush()
                self.mock_reporter.report.assert_called_once_with(self.subject.profile)

            def test_it_returns_true(self):
                self.mock_reporter.report.return_value = True
                assert self.subject.flush()

            def test_profile_gets_reset(self):
                self.mock_reporter.report.return_value = True

                self.subject.flush()

                assert_profile_is_reset(self.mock_profile_factory, self.clock)

            def test_timer_gets_reset(self):
                self.mock_reporter.report.return_value = True

                self.subject.flush()

                self.timer.reset.assert_called_once()

            def test_it_adds_the_run_profiler_overhead_metric_to_the_profile(
                    self):
                run_profiler_metric = Metric()
                run_profiler_metric.add(0.1)
                self.timer.get_metric.side_effect = \
                    lambda metric_name: metric_name == "runProfiler" and run_profiler_metric

                self.subject.flush()

                self.mock_profile.set_overhead_ms.assert_called_once_with(duration_timedelta=timedelta(seconds=0.1))

            class TestWhenProfileIsEmpty:
                @before
                def before(self):
                    self.mock_profile.is_empty = MagicMock(return_value=True)

                def test_it_does_not_report(self):
                    self.subject.flush()

                    self.mock_reporter.report.assert_not_called()

                def test_it_resets_the_profile(self):
                    self.subject.flush()

                    assert_profile_is_reset(self.mock_profile_factory, self.clock)

                def test_it_resets_the_timer(self):
                    self.subject.flush()

                    self.timer.reset.assert_called_once()

            class TestWhenReportFailed:
                @before
                def before(self):
                    self.mock_reporter.report.return_value = False

                def test_it_resets_the_profile(self):
                    self.subject.flush()

                    assert_profile_is_reset(self.mock_profile_factory, self.clock)

                def test_it_resets_the_timer(self):
                    self.subject.flush()

                    self.timer.reset.assert_called_once()

                class TestWhenRetryingReport:
                    def test_it_updates_the_profiler_overhead_metric_on_the_profile(
                            self):
                        run_profiler_metric = Metric()
                        run_profiler_metric.add(0.1)
                        self.timer.get_metric.side_effect = \
                            lambda metric_name: metric_name == "runProfiler" and run_profiler_metric

                        self.subject._is_over_reporting_interval = MagicMock(returnValue=False)
                        # first failed report
                        self.subject.flush()

                        # some more time is added to the metric
                        run_profiler_metric.add(0.3)

                        # try to report again
                        self.time_now += timedelta(minutes=10).total_seconds()
                        self.subject.flush()
                        self.mock_profile.set_overhead_ms.assert_has_calls([
                            call(duration_timedelta=timedelta(seconds=0.1)),
                            call(duration_timedelta=timedelta(seconds=0.4))
                        ])

        class TestWhenReportingIntervalNotReached:
            @before
            def before(self):
                self.mock_profile.get_memory_usage_bytes = MagicMock(
                    return_value=DEFAULT_MEMORY_LIMIT_BYTES - 1)
                self.move_clock_to(self.reporting_interval - ONE_SECOND)
                self.mock_profile.is_empty = MagicMock(
                    return_value=False)

            def test_it_does_not_report(self):
                self.mock_reporter.report.return_value = True
                self.mock_reporter.report.assert_not_called()

            def test_it_returns_false(self):
                self.mock_reporter.report.return_value = True
                assert not self.subject.flush()

    class TestForceFlush:
        @before
        def before(self):
            self.mock_profile.get_memory_usage_bytes.return_value = DEFAULT_MEMORY_LIMIT_BYTES - 1
            self.mock_profile.is_empty = MagicMock(return_value=False)

        class TestWhenMinReportingTimeNotReached:
            @before
            def before(self):
                self.move_clock_to(INITIAL_MINIMUM_REPORTING_INTERVAL - ONE_SECOND)
                self.mock_profile_factory.reset_mock()

            def test_it_does_not_report(self):
                self.subject.flush(force=True)

                self.mock_reporter.report.assert_not_called()

            def test_profile_gets_reset(self):
                self.subject.flush(force=True)

                assert_profile_is_reset(self.mock_profile_factory, self.clock)

            def test_timer_gets_reset(self):
                self.subject.flush(force=True)

                self.timer.reset.assert_called_once()

        class TestWhenMinReportingTimeReached:
            @before
            def before(self):
                self.move_clock_to(INITIAL_MINIMUM_REPORTING_INTERVAL + ONE_SECOND)

            def test_it_reports(self):
                self.mock_reporter.report = MagicMock(return_value=True)

                self.subject.flush(force=True)

                self.mock_reporter.report.assert_called_once()

            def test_profile_gets_reset(self):
                self.mock_reporter.report = MagicMock(return_value=True)

                self.subject.flush(force=True)

                assert_profile_is_reset(self.mock_profile_factory, self.clock)

            def test_timer_gets_reset(self):
                self.subject.flush(force=True)

                self.timer.reset.assert_called_once()

            def test_it_adds_the_run_profiler_overhead_metric_to_the_profile(
                    self):
                run_profiler_metric = Metric()
                run_profiler_metric.add(0.1)
                self.timer.get_metric.side_effect = \
                    lambda metric_name: metric_name == "runProfiler" and run_profiler_metric

                self.subject.flush(force=True)

                self.mock_profile.set_overhead_ms.assert_called_once_with(duration_timedelta=timedelta(seconds=0.1))

            def test_when_report_failed_profile_gets_reset(self):
                self.mock_reporter.report = MagicMock(return_value=False)

                self.subject.flush(force=True)

                assert_profile_is_reset(self.mock_profile_factory, self.clock)

    class TestMemoryUsageLimitExceeded:
        @before
        def before(self):
            self.mock_profile.get_memory_usage_bytes = MagicMock(
                return_value=DEFAULT_MEMORY_LIMIT_BYTES + 1)
            self.sample = Sample([["method1", "method2"]])

        class TestLastFlushWasLongerThanMinTimeForReporting:
            @before
            def before(self):
                self.move_clock_to(INITIAL_MINIMUM_REPORTING_INTERVAL + ONE_SECOND)
                self.mock_profile.is_empty = MagicMock(return_value=False)

            def test_it_reports_without_exception(self):
                self.mock_reporter.report.return_value = True
                self.subject.add(self.sample)
                self.mock_reporter.report.assert_called_once_with(self.subject.profile)

            def test_it_updates_last_report_attempted(self):
                self.mock_reporter.report.return_value = True
                assert (self.subject.last_report_attempted == CURRENT_TIME_FOR_TESTING_MILLI)
                self.subject.add(self.sample)
                assert (self.subject.last_report_attempted == self.time_now * 1000)

        class TestLastFlushWasWithinMinTimeForReporting:
            @before
            def before(self):
                self.sample = Sample([["method1", "method2"]])
                self.move_clock_to(INITIAL_MINIMUM_REPORTING_INTERVAL - ONE_SECOND)

            def test_exception_raised_when_memory_usage_exceeded(self):
                with pytest.raises(OverMemoryLimitException):
                    self.subject.add(self.sample)
