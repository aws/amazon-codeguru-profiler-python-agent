import pytest
import time
import codeguru_profiler_agent.aws_lambda.profiler_decorator

from unittest.mock import MagicMock
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from codeguru_profiler_agent import with_lambda_profiler
from codeguru_profiler_agent import Profiler
from codeguru_profiler_agent.aws_lambda.lambda_context import LambdaContext


class TestWithLambdaProfiler:
    @pytest.fixture(autouse=True)
    def around(self):
        self.mock_profiler = MagicMock(name="profiler", spec=Profiler)
        self.context = MagicMock()
        self.context.invoked_function_arn = "the_lambda_function_arn"

        @with_lambda_profiler(profiler_factory=lambda *args, **kwargs: self.mock_profiler)
        def handler_function(event, context):
            self.counter += 1
            if event.get('throw'):
                raise ValueError(
                    "Simulated error in a lambda handler (unit test)")

        self.counter = 0
        self.handler = handler_function
        self.mock_profiler.start.return_value = True

        yield \
            codeguru_profiler_agent.aws_lambda.profiler_decorator.clear_static_profiler()
        if Profiler._active_profiler is not None:
            Profiler._active_profiler.stop()

    def test_function_is_called(self):
        self.handler({}, self.context)
        assert (self.counter == 1)

    def test_profiler_is_started_and_paused(self):
        self.handler({}, self.context)
        self.mock_profiler.start.assert_called_once()
        self.mock_profiler.pause.assert_called_once()

    def test_profiler_is_paused_when_handler_fails(self):
        try:
            self.handler({'throw': True}, self.context)
        except ValueError:
            pass
        self.mock_profiler.pause.assert_called_once()

    def test_profiler_is_disabled_if_start_fails(self):
        self.mock_profiler.start.return_value = False
        self.handler({}, self.context)
        # now call again and check that profiler is disabled
        self.handler({}, self.context)
        assert isinstance(codeguru_profiler_agent.aws_lambda.profiler_decorator._profiler,
                          type(codeguru_profiler_agent.aws_lambda.profiler_decorator._EmptyProfiler()))

    def test_function_runs_even_when_profiler_is_disabled(self):
        self.mock_profiler.start.return_value = False
        self.handler({}, self.context)
        # make sure function is still called
        assert (self.counter == 1)
        # now call again, function is still called.
        self.handler({}, self.context)
        assert (self.counter == 2)


class TestWithParameters:
    @pytest.fixture(autouse=True)
    def around(self):
        self.context = MagicMock()
        self.context.invoked_function_arn = "the_lambda_function_arn"
        self.env = {"AWS_LAMBDA_FUNCTION_MEMORY_SIZE": "1024",
                    "AWS_EXECUTION_ENV_KEY": "AWS_Lambda_python3.6"}

        # define a handler function with the profiler decorator and parameters
        @with_lambda_profiler(profiling_group_name="pg_name", region_name="eu-north-1",
                              environment_override={'cpu_limit_percentage': 42}, env=self.env)
        def handler_function(event, context):
            time.sleep(0.5)
            return True

        self.handler = handler_function
        yield \
            codeguru_profiler_agent.aws_lambda.profiler_decorator.clear_static_profiler()
        codeguru_profiler_agent.aws_lambda.profiler_decorator.clear_static_profiler()


    def test_given_profiling_group_is_used(self):
        self.handler({}, self.context)
        assert (codeguru_profiler_agent.aws_lambda.profiler_decorator._profiler._profiler_runner.collector
                .profiling_group_name == "pg_name")

    def test_given_region_name_is_used(self):
        self.handler({}, self.context)
        assert ('eu-north-1' in codeguru_profiler_agent.aws_lambda.profiler_decorator._profiler._profiler_runner.
                collector.reporter.codeguru_client_builder.codeguru_client._endpoint.host)

    def test_given_override_is_used(self):
        self.handler({}, self.context)
        assert AgentConfiguration.get().cpu_limit_percentage == 42

    def test_metadata_is_properly_set(self):
        self.handler({}, self.context)
        fleet_info = codeguru_profiler_agent.aws_lambda.profiler_decorator._profiler. \
            _profiler_runner.collector.reporter.metadata.fleet_info
        assert (fleet_info.get_fleet_instance_id() == "the_lambda_function_arn")

    def test_context_is_set_in_lambda_context_singleton(self):
        self.handler({}, self.context)
        assert LambdaContext.get().context is self.context

    def test_last_call_duration_is_set_in_lambda_context_singleton(self):
        self.handler({}, self.context)
        assert LambdaContext.get().last_execution_duration
