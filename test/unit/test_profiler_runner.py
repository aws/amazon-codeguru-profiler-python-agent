from datetime import timedelta
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from test.pytestutils import before
from test.help_utils import wait_for
from mock import MagicMock
from time import sleep

from codeguru_profiler_agent.profiler_runner import ProfilerRunner
from codeguru_profiler_agent.profiler_disabler import ProfilerDisabler
from codeguru_profiler_agent.local_aggregator import LocalAggregator
from codeguru_profiler_agent.sampler import Sampler


class TestProfilerRunner:
    @before
    def before(self):
        self.mock_collector = MagicMock(name="collector", spec=LocalAggregator)
        self.mock_disabler = MagicMock(name="profile", spec=ProfilerDisabler)
        self.mock_disabler.should_stop_profiling.return_value = False
        self.mock_sampler = MagicMock(name="sampler", spec=Sampler)

        self.environment = {
            "collector": self.mock_collector,
            "profiler_disabler": self.mock_disabler,
            "sampler": self.mock_sampler,
            "initial_sampling_interval": timedelta(),
            "profiler_thread_name": "codeguru-profiler-agent-TestProfilerRunner"
        }

        self.agent_configuration = AgentConfiguration(should_profile=True,
                                                      sampling_interval=timedelta(seconds=2),
                                                      reporting_interval=timedelta(seconds=100))

        # mock the collector's refresh_configuration function to actual set agent configuration singleton
        def set_new_configuration():
            AgentConfiguration.set(self.agent_configuration)

        self.mock_collector.refresh_configuration.side_effect = set_new_configuration

        # mock the collector's flush function to return True or False according to self.is_time_to_report
        self.is_time_to_report = False
        self.mock_collector.flush.side_effect = lambda *args, **kwargs: self.is_time_to_report
        self.mock_collector.profile = None  # we need this as we pass the profile object to the disabler, None is fine
        self.profiler_runner = ProfilerRunner(self.environment)

        yield
        self.profiler_runner.stop()

    def test_when_runner_executes_for_the_first_time(self):
        self.profiler_runner._profiling_command()
        self.mock_collector.refresh_configuration.assert_called_once()
        self.mock_collector.add.assert_called_once()
        self.mock_collector.setup.assert_called_once()

    def test_when_runner_executes_for_the_second_time(self):
        self.profiler_runner._profiling_command()
        self.mock_collector.reset_mock()

        self.profiler_runner._profiling_command()

        self.mock_collector.add.assert_called_once()
        self.mock_collector.refresh_configuration.assert_not_called()
        self.mock_collector.flush.assert_called_once()
        self.mock_collector.setup.assert_not_called()

    def test_when_it_is_time_to_report_it_refreshes_configuration_again(self):
        self.is_time_to_report = True
        # this will call flush which will return True, so we simulate we have reported,
        # next call should refresh configuration
        self.profiler_runner._profiling_command()
        self.mock_collector.reset_mock()

        self.profiler_runner._profiling_command()
        self.mock_collector.refresh_configuration.assert_called_once()

    def test_when_disabler_say_to_stop(self):
        self.mock_disabler.should_stop_profiling.return_value = True
        self.profiler_runner._profiling_command()

        self.mock_collector.refresh_configuration.assert_not_called()
        self.mock_collector.add.assert_not_called()

    def test_when_orchestrator_says_no_to_profiler(self):
        self.agent_configuration = AgentConfiguration(should_profile=False,
                                                      sampling_interval=timedelta(seconds=2),
                                                      reporting_interval=timedelta(seconds=151))
        # calling start in this test, it will start the scheduler and because initial delay is 0 it will execute now
        self.profiler_runner.start()
        # still it is safer to wait until the new config has been applied
        wait_for(lambda: AgentConfiguration.get().reporting_interval.total_seconds() == 151)
        # sometimes it takes a few milliseconds for the scheduler to be updated with the AgentConfiguration,
        # so let's sleep for 100 ms
        sleep(0.1)

        assert self.profiler_runner.scheduler._get_next_delay_seconds() == 151
        self.mock_collector.add.assert_not_called()
