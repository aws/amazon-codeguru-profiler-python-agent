import pytest
from datetime import timedelta
from mock import Mock
from codeguru_profiler_agent.profiler import Profiler
from codeguru_profiler_agent.profiler_runner import ProfilerRunner


def throw_exception(*args, **kwargs):
    raise Exception("Exception from TestProfiler")


def mock_profiler_runner_factory(profiler_runner):
    return lambda environment: profiler_runner


class TestProfiler:
    class TestInit:
        class TestExceptionHandling:
            def test_exceptions_are_caught_and_do_not_propagate(self):
                Profiler(
                    profiling_group_name="test-application",
                    environment_override={
                        "profiler_runner_factory": throw_exception
                    },
                )
                Profiler(profiling_group_name=None)

        class TestReportingModeValidation:
            class TestWhenReportingModeIsInvalid:
                def test_it_raises_a_value_error(self):
                    with pytest.raises(ValueError):
                        Profiler(
                            profiling_group_name="unit-test",
                            environment_override={
                                "allow_top_level_exceptions": True,
                                "reporting_mode": "wrong-reporting-mode"
                            },
                        )

        class TestWhenCustomReportingIntervalIsLessThan30Seconds:
            def test_it_does_propagate_a_value_error(self):
                environment = {"reporting_interval": timedelta(seconds=29)}
                Profiler(profiling_group_name="test-application", environment_override=environment)

        class TestRemovesEnvironmentOverridesForAgentConfiguration:
            def test_checks_number_of_params(self):
                environment = {
                    'reporting_mode': 'codeguru_service',
                    'excluded_threads': set(),
                    'should_profile': True,
                    'sampling_interval': timedelta(seconds=1),
                    'reporting_interval': timedelta(minutes=10),
                    'minimum_time_reporting': timedelta(minutes=1),
                    'max_stack_depth': 1000,
                    'cpu_limit_percentage': 10,
                    'memory_limit_bytes': 1024,
                    'host_weight': 1.0,
                    'max_threads': 100
                }
                assert len(environment.keys()) == 11
                Profiler(profiling_group_name="test-application", environment_override=environment)
                assert len(environment.keys()) == 5

    class TestStart:
        class TestExceptionHandling:
            @pytest.fixture(autouse=True)
            def around(self):
                self.profiler_runner = Mock(spec_set=ProfilerRunner)
                self.profiler_runner.is_running = Mock(return_value=False)
                self.profiler_runner.start = throw_exception
                self.profiler = Profiler(
                    profiling_group_name="test-application",
                    environment_override={
                        "profiler_runner_factory": mock_profiler_runner_factory(self.profiler_runner)
                    })
                yield
                self.profiler.stop()

            def test_exceptions_are_caught_and_do_not_propagate(self):
                assert (not self.profiler.start())

        class TestWhenAnotherInstanceAlreadyStarted:
            @pytest.fixture(autouse=True)
            def around(self):
                self.profiler_runner = Mock(spec_set=ProfilerRunner)
                self.profiler_runner.start = Mock(return_value=True)
                self.profiler_runner.is_running = Mock(return_value=False)
                self.first_profiler = Profiler(
                    profiling_group_name="pg_name",
                    environment_override={
                        "profiler_runner_factory": mock_profiler_runner_factory(self.profiler_runner)
                    })
                self.first_profiler.start()
                self.second_profiler = Profiler(
                    profiling_group_name="test-application",
                    environment_override={
                        "profiler_runner_factory":
                            mock_profiler_runner_factory(self.profiler_runner)
                    })
                yield
                self.first_profiler.stop()
                self.second_profiler.stop()

            def test_it_fails_to_start_a_second_profiler(self):
                assert (not self.second_profiler.start())

        class TestWhenRunnerIsRunning:
            @pytest.fixture(autouse=True)
            def around(self):
                self.profiler_runner = Mock(spec_set=ProfilerRunner)
                self.profiler_runner.is_running = Mock(return_value=True)
                self.profiler_runner.resume = Mock()
                self.profiler = Profiler(
                    profiling_group_name="test-application",
                    environment_override={
                        "profiler_runner_factory":
                            mock_profiler_runner_factory(self.profiler_runner)
                    })
                yield
                self.profiler.stop()

            def test_it_returns_true(self):
                assert self.profiler.start()

            def test_it_calls_resume(self):
                self.profiler.start()
                assert self.profiler_runner.resume.called

    class TestStop:
        class TestWhenStartWasNotCalled:
            @pytest.fixture(autouse=True)
            def around(self):
                self.profiler = Profiler(profiling_group_name="test-application")
                yield

            def test_it_returns_true(self):
                assert self.profiler.stop()

        class TestExceptionHandling:
            @pytest.fixture(autouse=True)
            def around(self):
                self.profiler_runner = Mock(spec_set=ProfilerRunner)
                self.profiler_runner.stop = throw_exception
                self.profiler_runner.is_running = Mock(return_value=False)
                self.profiler = Profiler(
                    profiling_group_name="test-application",
                    environment_override={
                        "profiler_runner_factory": mock_profiler_runner_factory(self.profiler_runner)
                    })
                yield
                self.profiler_runner.stop = Mock(return_value=True)
                self.profiler.stop()

            def test_exceptions_are_caught_and_do_not_propagate(self):
                self.profiler.start()
                assert (not self.profiler.stop())

        class TestWhenAnotherInstanceAlreadyStarted:
            @pytest.fixture(autouse=True)
            def around(self):
                self.profiler_runner = Mock(spec_set=ProfilerRunner)
                self.profiler_runner.start = Mock(return_value=True)
                self.profiler_runner.is_running = Mock(return_value=False)
                self.first_profiler = Profiler(
                    profiling_group_name="pg_name",
                    environment_override={
                        "profiler_runner_factory": mock_profiler_runner_factory(self.profiler_runner)
                    })
                self.first_profiler.start()
                self.second_profiler = Profiler(
                    profiling_group_name="test-application",
                    environment_override={
                        "profiler_runner_factory": mock_profiler_runner_factory(self.profiler_runner)
                    })
                yield
                self.first_profiler.stop()
                self.second_profiler.stop()

            def test_stopping_first_instance_allows_next_profiler_to_start(self):
                self.first_profiler.stop()
                assert self.second_profiler.start()

    class TestPause:
        @pytest.fixture(autouse=True)
        def around(self):
            self.profiler_runner = Mock(spec_set=ProfilerRunner)
            self.profiler_runner.pause = Mock()
            self.profiler = Profiler(
                profiling_group_name="test-application",
                environment_override={
                    "profiler_runner_factory": mock_profiler_runner_factory(self.profiler_runner)
                })
            yield
            self.profiler.stop()

        def test_it_returns_true(self):
            assert self.profiler.pause()

        def test_it_calls_pause_on_runner(self):
            self.profiler.pause()
            assert self.profiler_runner.pause.called

        class TestExceptionHandling:
            def test_exceptions_are_caught_and_do_not_propagate(self):
                self.profiler_runner.pause = throw_exception
                assert (not self.profiler.pause())

    class TestStr:
        @pytest.fixture(autouse=True)
        def around(self):
            self.profiler_runner = Mock(spec_set=ProfilerRunner)
            self.session = Mock()
            self.session.__repr__ = \
                Mock(return_value="Session(region_name='eu-west-2', profile_name='alternate_credentials')")
            self.profiler = Profiler(
                profiling_group_name="test-application",
                region_name="ap-southeast-1",
                aws_session=self.session,
                environment_override={
                    "sampling_interval": timedelta(seconds=0.01),
                    "profiler_runner_factory": mock_profiler_runner_factory(self.profiler_runner)
                })
            yield

        def test_it_prints_a_subset_of_parameters(self):
            assert str(self.profiler) == \
                   "Profiler(environment={'max_threads': 100," \
                   " 'profiling_group_name': 'test-application'," \
                   " 'region_name': 'ap-southeast-1'," \
                   " 'aws_session': Session(region_name='eu-west-2', profile_name='alternate_credentials')}"
