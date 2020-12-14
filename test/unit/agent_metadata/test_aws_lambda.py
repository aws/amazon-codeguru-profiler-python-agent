import pytest
from test.pytestutils import before
from mock import Mock
from datetime import timedelta
from codeguru_profiler_agent.agent_metadata.aws_lambda import AWSLambda
from codeguru_profiler_agent.aws_lambda.lambda_context import LambdaContext


class TestAWSLambda:
    class TestLookUpMetadata:
        class TestWhenContextIsAvailable:
            class TestWhenEnvIsAvailable:
                @before
                def before(self):
                    self.context = Mock()
                    self.context.invoked_function_arn = "the_lambda_function_arn"
                    self.env = {"AWS_EXECUTION_ENV": "AWS_Lambda_python3.6", "AWS_LAMBDA_FUNCTION_MEMORY_SIZE": "2048"}

                def test_it_finds_the_arn(self):
                    subject = AWSLambda.look_up_metadata(self.context, self.env)
                    assert subject.function_arn == "the_lambda_function_arn"

                def test_it_finds_memory_limit(self):
                    subject = AWSLambda.look_up_metadata(self.context, self.env)
                    assert subject.memory_limit_mb == 2048

                def test_it_finds_the_execution_env(self):
                    subject = AWSLambda.look_up_metadata(self.context, self.env)
                    assert subject.execution_env == "AWS_Lambda_python3.6"

                def test_when_env_is_not_available_it_still_returns_at_least_the_arn(self):
                    subject = AWSLambda.look_up_metadata(self.context, {})
                    assert subject.function_arn == "the_lambda_function_arn"

                def test_other_values_are_set_to_none(self):
                    subject = AWSLambda.look_up_metadata(self.context, {})
                    assert subject.execution_env is None
                    assert subject.memory_limit_mb is None

            class TestWhenMemoryEnvIsNotValidInt:
                @before
                def before(self):
                    self.context = Mock()
                    self.context.invoked_function_arn = "the_lambda_function_arn"
                    self.env = {"AWS_EXECUTION_ENV": "AWS_Lambda_python3.6",
                                "AWS_LAMBDA_FUNCTION_MEMORY_SIZE": "not_a_valid_integer"}

                def test_it_still_returns_the_arn(self):
                    subject = AWSLambda.look_up_metadata(self.context, {})
                    assert subject.function_arn == "the_lambda_function_arn"

                def test_it_finds_the_execution_env(self):
                    subject = AWSLambda.look_up_metadata(self.context, self.env)
                    assert subject.execution_env == "AWS_Lambda_python3.6"

                def test_memory_limit_is_set_to_none(self):
                    subject = AWSLambda.look_up_metadata(self.context, self.env)
                    assert subject.memory_limit_mb is None

        class TestWhenContextIsNotAvailable:
            def test_it_returns_none(self):
                subject = AWSLambda.look_up_metadata(context=None, env={})
                assert subject is None

    class TestSerializeToMap:
        def test_it_returns_a_map(self):
            subject = AWSLambda(function_arn="the_arn", memory_limit_mb=512, execution_env="AWS_Lambda_python3.8")

            assert subject.serialize_to_map() == {
                "computeType": "aws_lambda",
                "functionArn": "the_arn",
                "memoryLimitInMB": 512,
                "executionEnv": "AWS_Lambda_python3.8"
            }

        def test_it_ignores_memory_limit_if_none(self):
            subject = AWSLambda(function_arn="the_arn", memory_limit_mb=None, execution_env="AWS_Lambda_python3.8")

            assert subject.serialize_to_map() == {
                "computeType": "aws_lambda",
                "functionArn": "the_arn",
                "executionEnv": "AWS_Lambda_python3.8"
            }

        def test_it_ignores_execution_env_if_none(self):
            subject = AWSLambda(function_arn="the_arn", memory_limit_mb=512, execution_env=None)

            assert subject.serialize_to_map() == {
                "computeType": "aws_lambda",
                "functionArn": "the_arn",
                "memoryLimitInMB": 512
            }

    class TestGetMetadataForConfigureAgentCall:
        @before
        def before(self):
            self.context = Mock()
            self.context.invoked_function_arn = "the_lambda_function_arn"
            self.context.aws_request_id = "the_aws_request_id"
            self.context.get_remaining_time_in_millis = Mock(return_value=30125)
            self.subject = AWSLambda(function_arn="the_lambda_function_arn", memory_limit_mb=512,
                                     execution_env="AWS_Lambda_python3.8",
                                     agent_id="a509707f-12db-462d-b5c9-18bc19c69bf0")
            self.lambda_context = LambdaContext()
            self.lambda_context.context = self.context
            self.lambda_context.last_execution_duration = timedelta(seconds=1, milliseconds=234, microseconds=987)

        def test_it_returns_the_metadata_needed_for_configure_agent_call(self):
            assert self.subject.get_metadata_for_configure_agent_call(lambda_context=self.lambda_context) == {
                "ComputePlatform": "AWSLambda",
                "AgentId": "a509707f-12db-462d-b5c9-18bc19c69bf0",
                "AwsRequestId": "the_aws_request_id",
                "ExecutionEnvironment": "AWS_Lambda_python3.8",
                "LambdaFunctionArn": "the_lambda_function_arn",
                "LambdaMemoryLimitInMB": "512",
                "LambdaRemainingTimeInMilliseconds": "30125",
                "LambdaPreviousExecutionTimeInMilliseconds": "1234"
            }

        class TestWhenSomeFieldsAreMissing:
            @pytest.fixture(autouse=True)
            def around(self):
                self.subject = AWSLambda(function_arn="the_lambda_function_arn",
                                         memory_limit_mb=None,
                                         execution_env=None,
                                         agent_id="a509707f-12db-462d-b5c9-18bc19c69bf0")
                LambdaContext.get()
                yield
                LambdaContext._singleton = None

            def test_it_returns_at_least_the_compute_platform(self):
                metadata = self.subject.get_metadata_for_configure_agent_call()
                assert metadata["ComputePlatform"] == "AWSLambda"

            def test_it_can_return_last_execution_duration_independently(self):
                LambdaContext.get().last_execution_duration = timedelta(seconds=1, milliseconds=234, microseconds=987)
                metadata = self.subject.get_metadata_for_configure_agent_call()
                assert metadata["LambdaPreviousExecutionTimeInMilliseconds"] == "1234"
