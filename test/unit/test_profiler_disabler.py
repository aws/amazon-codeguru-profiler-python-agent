import tempfile
from pathlib import Path
import shutil
from mock import Mock, patch
import time

from codeguru_profiler_agent.model.profile import Profile
from test.pytestutils import before
from datetime import timedelta

from codeguru_profiler_agent.profiler import DEFAULT_MEMORY_LIMIT_BYTES, DEFAULT_CPU_LIMIT_PERCENTAGE
from codeguru_profiler_agent.profiler_disabler import KillSwitch, CpuUsageCheck, ProfilerDisabler, \
    MINIMUM_SAMPLES_IN_PROFILE
from codeguru_profiler_agent.metrics.timer import Timer
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration


def set_agent_config(sampling_interval_seconds=1, cpu_limit_percentage=DEFAULT_CPU_LIMIT_PERCENTAGE):
    """
    Reporting interval needs to have a minimum value and cpu_limit_percentage is used later in tests;
    the other values can be None as we are not using them here.
    """
    return AgentConfiguration.set(
        AgentConfiguration(sampling_interval=timedelta(seconds=sampling_interval_seconds),
                           reporting_interval=timedelta(seconds=300),
                           minimum_time_reporting=timedelta(seconds=60),
                           cpu_limit_percentage=cpu_limit_percentage))


def assert_config_sampling_interval_used(process_duration_check, profile):
    assert process_duration_check.is_cpu_usage_limit_reached(profile)

    set_agent_config(sampling_interval_seconds=42, cpu_limit_percentage=80)
    assert not process_duration_check.is_cpu_usage_limit_reached(profile)


class TestProfilerDisabler:
    def before(self):
        self.timer = Timer()
        self.env = {
            'timer': self.timer,
            'killswitch_filepath': 'path_to_my_kill_switch',
            'memory_limit_bytes': DEFAULT_MEMORY_LIMIT_BYTES
        }
        self.disabler = ProfilerDisabler(self.env)


class TestSetupParameters(TestProfilerDisabler):
    @before
    def before(self):
        super().before()

    def test_it_sets_all_parameters(self):
        self.env['memory_limit_bytes'] = 42
        self.disabler = ProfilerDisabler(self.env)
        assert self.disabler.memory_limit_bytes == 42
        assert self.disabler.killswitch.killswitch_filepath == 'path_to_my_kill_switch'
        assert self.disabler.cpu_usage_check.timer == self.timer
        assert AgentConfiguration.get().cpu_limit_percentage == DEFAULT_CPU_LIMIT_PERCENTAGE


class TestWhenAnyFails(TestProfilerDisabler):
    @before
    def before(self):
        super().before()
        self.profiler = Mock()
        self.disabler.killswitch = Mock()
        self.disabler.cpu_usage_check = Mock()
        self.disabler._is_memory_limit_reached = Mock(return_value=False)
        self.disabler.killswitch.is_killswitch_on = Mock(return_value=False)
        self.disabler.killswitch.is_process_duration_limit_reached = Mock(return_value=False)

    def test_it_stops_profiling_if_killswitch_is_on(self):
        self.disabler.killswitch.is_killswitch_on = Mock(return_value=True)
        assert self.disabler.should_stop_profiling(self.profiler)

    def test_it_stops_profiling_if_memory_limit_is_reached(self):
        self.disabler._is_memory_limit_reached = Mock(return_value=True)
        assert self.disabler.should_stop_profiling(self.profiler)

    def test_it_stops_profiling_if_process_duration_is_reached(self):
        self.disabler.cpu_usage_check.is_cpu_usage_limit_reached = Mock(return_value=True)
        assert self.disabler.should_stop_profiling(self.profiler)


class TestKillSwitch:
    class TestWhenKillSwitchFileExists:
        @before
        def before(self):
            self.temporary_directory = tempfile.mkdtemp()
            self.temp_filepath = str(
                Path(self.temporary_directory,
                     'test_killswitch_unit_test'))
            Path(self.temp_filepath).touch()
            yield
            shutil.rmtree(self.temporary_directory)

        def test_it_returns_true(self):
            assert KillSwitch(self.temp_filepath).is_killswitch_on()

    class TestWhenKillSwitchFileDoesNotExists:
        def test_it_returns_false(self):
            assert not KillSwitch("this_file_does_not_exists_in_the_file_system_or_i_am_unlucky").is_killswitch_on()


class TestWhenKillSwitchFileIsAdded:
    @before
    def before(self):
        self.temporary_directory = tempfile.mkdtemp()
        self.temp_filepath = str(
            Path(self.temporary_directory,
                 'test_killswitch_unit_test'))
        self.current_time = time.time()
        self.killswitch = KillSwitch(self.temp_filepath, clock=lambda: self.current_time)
        self.killswitch.is_killswitch_on()
        Path(self.temp_filepath).touch()
        yield
        shutil.rmtree(self.temporary_directory)

    def test_it_still_returns_false_for_less_than_a_minute(self):
        self.current_time = self.current_time + 10
        assert not self.killswitch.is_killswitch_on()

    def test_it_returns_true_after_a_minute(self):
        self.current_time = self.current_time + 61
        assert self.killswitch.is_killswitch_on()


class TestWhenKillSwitchFileIsRemoved:
    @before
    def before(self):
        self.temporary_directory = tempfile.mkdtemp()
        self.temp_filepath = str(
            Path(self.temporary_directory,
                 'test_killswitch_unit_test'))
        self.current_time = time.time()
        self.killswitch = KillSwitch(self.temp_filepath, clock=lambda: self.current_time)
        Path(self.temp_filepath).touch()
        self.killswitch.is_killswitch_on()
        shutil.rmtree(self.temporary_directory)
        yield

    def test_it_returns_false_after_a_minute(self):
        self.current_time = self.current_time + 61
        assert not self.killswitch.is_killswitch_on()


class TestCpuUsageCheck:
    def before(self):
        self.timer = Timer()
        self.profile = Mock(spec=Profile)
        for i in range(20):
            self.timer.record('sampleAndAggregate', 0.5)
        set_agent_config(sampling_interval_seconds=1, cpu_limit_percentage=10)
        self.process_duration_check = CpuUsageCheck(self.timer)


class TestGetAverageSamplingIntervalSeconds(TestCpuUsageCheck):
    @before
    def before(self):
        super().before()
        set_agent_config(sampling_interval_seconds=23)
        self.profile.get_active_millis_since_start = Mock(return_value=40000)
        self.profile.total_sample_count = 10

    def test_it_returns_average_sampling_interval_seconds_based_on_profile(self):
        # sampling interval seconds = (40000/10)/1000 = 4
        assert CpuUsageCheck._get_average_sampling_interval_seconds(self.profile) == 4

    def test_when_profile_is_none_it_returns_configuration_sampling_interval(self):
        assert CpuUsageCheck._get_average_sampling_interval_seconds(None) == 23

    def test_when_profiler_sample_count_less_than_min_samples_in_profile_it_returns_configuration_sampling_interval(
            self):
        self.profile.total_sample_count = MINIMUM_SAMPLES_IN_PROFILE - 1
        assert CpuUsageCheck._get_average_sampling_interval_seconds(self.profile) == 23


class TestIsCpuUsageLimitReached(TestCpuUsageCheck):
    @before
    def before(self):
        super().before()
        with patch(
                "codeguru_profiler_agent.profiler_disabler.CpuUsageCheck._get_average_sampling_interval_seconds",
                return_value=4) as m:
            self.get_average_sampling_interval_mock = m
            yield

    def test_it_calls_get_average_sampling_interval_with_profile(self):
        self.process_duration_check.is_cpu_usage_limit_reached(self.profile)
        self.get_average_sampling_interval_mock.assert_called_once_with(self.profile)

    def test_when_average_duration_exceeds_limit_it_returns_true(self):
        # timer: (0.5/4) * 100= 12.5%
        assert self.process_duration_check.is_cpu_usage_limit_reached()

    def test_when_average_duragtion_is_below_limit_it_returns_false(self):
        # timer: (0.5/4) * 100= 12.5%
        set_agent_config(cpu_limit_percentage=13)
        assert not self.process_duration_check.is_cpu_usage_limit_reached()

    def test_when_profile_is_none_it_calls_get_average_sampling_interval_without_profile(self):
        self.process_duration_check.is_cpu_usage_limit_reached()
        self.get_average_sampling_interval_mock.assert_called_once_with(None)


class TestWhenTimerDoesNotHaveTheKey(TestCpuUsageCheck):
    @before
    def before(self):
        super().before()

    def test_it_returns_false(self):
        self.process_duration_check.timer = Timer()
        assert not self.process_duration_check.is_cpu_usage_limit_reached()


class TestWhenTimerDoesNotHaveEnoughMeasures(TestCpuUsageCheck):
    @before
    def before(self):
        super().before()

    def test_it_returns_false(self):
        self.timer.reset()
        for i in range(4):
            self.timer.record('sampleAndAggregate', 0.5)
        assert not self.process_duration_check.is_cpu_usage_limit_reached()


class TestMemoryLimitCheck:
    @before
    def before(self):
        self.env = {
            'timer': None,
            'killswitch_filepath': '',
            'memory_limit_bytes': 10 * 1024 * 1024
        }
        self.disabler = ProfilerDisabler(self.env)
        self.profile = Mock()
        self.profile.get_memory_usage_bytes = Mock(return_value=10 * 1024 * 1024 + 1)
        self.disabler = ProfilerDisabler(self.env)

    def test_when_memory_usage_exceeds_limit_it_returns_true(self):
        assert self.disabler._is_memory_limit_reached(self.profile)

    def test_when_memory_usage_is_below_limit_it_returns_false(self):
        self.profile.get_memory_usage_bytes = Mock(return_value=10 * 1024 * 1024 - 1)
        assert not self.disabler._is_memory_limit_reached(self.profile)
