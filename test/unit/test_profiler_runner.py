from datetime import timedelta
import time
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from test.pytestutils import before
from mock import MagicMock

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

    class TestWhenRunnerExecutesForTheFirstTime:
        @before
        def before(self):
            self.profiler_runner._profiling_command()

        def test_it_refreshes_configuration(self):
            self.mock_collector.refresh_configuration.assert_called_once()

        def test_it_sampled(self):
            self.mock_collector.add.assert_called_once()

        def test_it_calls_setup(self):
            self.mock_collector.setup.assert_called_once()

    class TestWhenRunnerExecutesForTheSecondTime:
        @before
        def before(self):
            self.profiler_runner._profiling_command()
            self.mock_collector.reset_mock()

        def test_it_does_not_refresh_config(self):
            self.profiler_runner._profiling_command()
            self.mock_collector.refresh_configuration.assert_not_called()

        def test_it_sampled(self):
            self.profiler_runner._profiling_command()
            self.mock_collector.add.assert_called_once()

        def test_it_called_flush(self):
            self.profiler_runner._profiling_command()
            self.mock_collector.flush.assert_called_once()

        def test_does_not_call_setup(self):
            self.mock_collector.setup.assert_not_called()

        class TestWhenItIsTimeToReport:
            @before
            def before(self):
                self.is_time_to_report = True
                # this will call flush which will return True, so we simulate we have reported,
                # next call should refresh configuration
                self.profiler_runner._profiling_command()
                self.mock_collector.reset_mock()

            def test_it_refreshes_configuration_again(self):
                self.profiler_runner._profiling_command()
                self.mock_collector.refresh_configuration.assert_called_once()

    class TestWhenDisablerSayWeShouldStop:
        @before
        def before(self):
            self.mock_disabler.should_stop_profiling.return_value = True
            self.profiler_runner._profiling_command()

        def test_it_does_not_refresh_config(self):
            self.mock_collector.refresh_configuration.assert_not_called()

        def test_it_does_not_sample(self):
            self.mock_collector.add.assert_not_called()

    class TestWhenOrchestratorSaysNotToProfile:
        @before
        def before(self):
            self.agent_configuration = AgentConfiguration(should_profile=False,
                                                          sampling_interval=timedelta(seconds=2),
                                                          reporting_interval=timedelta(seconds=150))
            # calling start in this test, it will start the scheduler and because initial delay is 0 it will execute now
            self.profiler_runner.start()
            # still it is safer to wait until the new config has been applied
            wait_until(lambda: AgentConfiguration.get().should_profile == False)

        def test_it_sets_the_scheduler_to_execute_again_after_reporting_interval(self):
            assert self.profiler_runner.scheduler._get_next_delay_seconds() == 150

        def test_it_does_not_sample(self):
            self.mock_collector.add.assert_not_called()


def wait_until(predicate, max_wait_seconds=1, period_seconds=0.1):
    start = time.time()
    timeout = start + max_wait_seconds
    while time.time() < timeout:
        if predicate():
            return True
        time.sleep(period_seconds)
    raise AssertionError("Predicate was never true after waiting for " + str(max_wait_seconds) + " seconds")
