import os
import logging
import uuid

from unittest.mock import MagicMock
from codeguru_profiler_agent.agent_metadata.fleet_info import FleetInfo
from codeguru_profiler_agent.aws_lambda.lambda_context import LambdaContext

logger = logging.getLogger(__name__)

LAMBDA_MEMORY_SIZE_ENV = "AWS_LAMBDA_FUNCTION_MEMORY_SIZE"
LAMBDA_EXECUTION_ENV = "AWS_EXECUTION_ENV"
HANDLER_ENV_NAME_FOR_CODEGURU_KEY = "HANDLER_ENV_NAME_FOR_CODEGURU"
LAMBDA_TASK_ROOT = "LAMBDA_TASK_ROOT"
LAMBDA_RUNTIME_DIR = "LAMBDA_RUNTIME_DIR"

# Those are used for the configure agent call:
# See https://docs.aws.amazon.com/codeguru/latest/profiler-api/API_ConfigureAgent.html
# note how these are not consistent with the profile schema which is unfortunate
COMPUTE_PLAFORM_KEY = "ComputePlatform"
COMPUTE_PLAFORM_VALUE = "AWSLambda"
AGENT_ID_KEY = "AgentId"
AWS_REQUEST_ID_KEY = "AwsRequestId"
EXECUTION_ENVIRONMENT_KEY = "ExecutionEnvironment"
LAMBDA_FUNCTION_ARN_KEY = "LambdaFunctionArn"
LAMBDA_MEMORY_LIMIT_IN_MB_KEY = "LambdaMemoryLimitInMB"
LAMBDA_PREVIOUS_EXECUTION_TIME_IN_MILLISECONDS_KEY = "LambdaPreviousExecutionTimeInMilliseconds"
LAMBDA_REMAINING_TIME_IN_MILLISECONDS_KEY = "LambdaRemainingTimeInMilliseconds"
# LambdaTimeGapBetweenInvokesInMilliseconds not sent at the moment

class AWSLambda(FleetInfo):
    """
    This class will get and parse the lambda metadata from the environment. For details about available env vars,
    See https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html
    """
    def __init__(self, function_arn, memory_limit_mb, execution_env, agent_id=None):
        super().__init__()
        self.function_arn = function_arn
        self.memory_limit_mb = memory_limit_mb
        self.execution_env = execution_env
        self.agent_id = agent_id or str(uuid.uuid4())

    def get_fleet_instance_id(self):
        return self.function_arn

    @classmethod
    def __look_up_memory_limit(cls, env=os.environ):
        try:
            return int(env.get(LAMBDA_MEMORY_SIZE_ENV))
        except (TypeError, ValueError):
            return None

    @classmethod
    def __look_execution_env(cls, env=os.environ):
        return env.get(LAMBDA_EXECUTION_ENV)

    @classmethod
    def __look_function_arn(cls, context):
        return context.invoked_function_arn

    @classmethod
    def look_up_metadata(cls, context, env=os.environ):
        """
        Either the account_id or context parameter should be provided
        """
        try:
            return cls(
                function_arn=cls.__look_function_arn(context),
                memory_limit_mb=cls.__look_up_memory_limit(env),
                execution_env=cls.__look_execution_env(env)
            )
        except Exception:
            logger.info("Unable to get Lambda metadata", exc_info=True)
            return None

    def serialize_to_map(self):
        as_map = {
            "computeType": "aws_lambda",
            "functionArn": self.function_arn
        }
        if self.memory_limit_mb:
            as_map["memoryLimitInMB"] = self.memory_limit_mb
        if self.execution_env:
            as_map["executionEnv"] = self.execution_env
        return as_map

    def get_metadata_for_configure_agent_call(self, lambda_context=None):
        """
        This gathers metadata from self and from given lambda context to build a map used for the configure_agent call
        :param lambda_context: a LambdaContext object which contains mainly the context from lambda framework.
            See https://docs.aws.amazon.com/lambda/latest/dg/python-context.html for details about the context.
        :return: a map with all metadata we want to send in configure_agent call.
        """
        # get the singleton lambda context. The decorator should set it.
        if lambda_context is None:
            lambda_context = LambdaContext.get()

        as_map = {
            COMPUTE_PLAFORM_KEY: COMPUTE_PLAFORM_VALUE,
            LAMBDA_FUNCTION_ARN_KEY: self.function_arn,
            AGENT_ID_KEY: self.agent_id
        }
        if self.memory_limit_mb:
            as_map[LAMBDA_MEMORY_LIMIT_IN_MB_KEY] = str(self.memory_limit_mb)
        if self.execution_env:
            as_map[EXECUTION_ENVIRONMENT_KEY] = self.execution_env

        '''
        Adding a specific condition to ignore MagicMock instances from being added to the metadata since
        it causes boto to raise a ParamValidationError, similar to https://github.com/boto/botocore/issues/2063.
        '''
        if lambda_context.context is not None and not isinstance(lambda_context.context, MagicMock):
            as_map[AWS_REQUEST_ID_KEY] = lambda_context.context.aws_request_id
            as_map[LAMBDA_REMAINING_TIME_IN_MILLISECONDS_KEY] = \
                str(lambda_context.context.get_remaining_time_in_millis())
        if lambda_context.last_execution_duration:
            as_map[LAMBDA_PREVIOUS_EXECUTION_TIME_IN_MILLISECONDS_KEY] = \
                str(int(lambda_context.last_execution_duration.total_seconds() * 1000))
        return as_map
