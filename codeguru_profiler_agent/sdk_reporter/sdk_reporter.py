# -*- coding: utf-8 -*-

import logging
import io
import os

from botocore.exceptions import ClientError
from codeguru_profiler_agent.utils.log_exception import log_exception
from codeguru_profiler_agent.reporter.reporter import Reporter
from codeguru_profiler_agent.metrics.with_timer import with_timer
from codeguru_profiler_agent.sdk_reporter.profile_encoder import ProfileEncoder
from codeguru_profiler_agent.agent_metadata.aws_lambda import HANDLER_ENV_NAME_FOR_CODEGURU_KEY, \
    LAMBDA_TASK_ROOT, LAMBDA_RUNTIME_DIR

logger = logging.getLogger(__name__)
AWS_EXECUTION_ENV_KEY = "AWS_EXECUTION_ENV"


class SdkReporter(Reporter):
    """
    Handles communication with the CodeGuru Profiler Service backend.
    Encodes profiles using the ProfilerEncoder and reports them using the CodeGuru profiler SDK.
    """
    is_create_pg_called_during_submit_profile = False

    def __init__(self, environment):
        """
        :param environment: dependency container dictionary for the current profiler.
        :param profiling_group_name: (required inside environment) name of the profiling group.
        :param codeguru_profiler_client: (required inside environment) sdk client for CodeGuru Profiler calls.
        """
        self.profiling_group_name = environment["profiling_group_name"]
        self.codeguru_client_builder = environment["codeguru_profiler_builder"]
        # TODO decide if we need to compress with gzip or not.
        self.profile_encoder = \
            environment.get("profile_encoder") or ProfileEncoder(environment=environment, gzip=False)
        self.timer = environment.get("timer")
        self.metadata = environment["agent_metadata"]
        self.agent_config_merger = environment["agent_config_merger"]
        self.errors_metadata = environment["errors_metadata"]

    def _encode_profile(self, profile):
        output_profile_stream = io.BytesIO()
        self.profile_encoder.encode(
            profile=profile, output_stream=output_profile_stream)
        output_profile_stream.seek(0)
        return output_profile_stream

    @with_timer("setupSdkReporter", measurement="wall-clock-time")
    def setup(self):
        """
        Initialize expensive resources.
        """
        self.codeguru_client_builder.codeguru_client

    @with_timer("refreshConfiguration", measurement="wall-clock-time")
    def refresh_configuration(self):
        """
        Refresh the agent configuration by calling the profiler backend service.

        Note:
        For an agent running on AWS Lambda, if the environment variables for Profiling using
        Lambda layers are set, it tries to create a Profiling Group whenever a ResourceNotFoundException
        is encountered.
        """
        try:
            fleet_instance_id = self.metadata.fleet_info.get_fleet_instance_id()
            metadata = self.metadata.fleet_info.get_metadata_for_configure_agent_call()
            configuration = self.codeguru_client_builder.codeguru_client.configure_agent(
                fleetInstanceId=fleet_instance_id,
                metadata=metadata if metadata is not None else {},
                profilingGroupName=self.profiling_group_name
            ).get('configuration')
            logger.debug("Got response from backend for configure_agent operation: " + str(configuration))
            self.agent_config_merger.merge_with(configure_agent_response=configuration)
        except ClientError as error:
            # If we get a validation error or the profiling group does not exists, do not profile. We do not stop the
            # whole process because the customer may fix this on their side by creating/changing the profiling group.
            # We handle service exceptions like this in boto3
            # see https://boto3.amazonaws.com/v1/documentation/api/latest/guide/error-handling.html
            if error.response['Error']['Code'] == 'ValidationException':
                self.errors_metadata.record_sdk_error("configureAgentErrors")
                self.agent_config_merger.disable_profiling()
                self._log_request_failed(operation="configure_agent", exception=error)
            elif error.response['Error']['Code'] == 'ResourceNotFoundException':
                if self.should_auto_create_profiling_group():
                    self.errors_metadata.record_sdk_error("configureAgentRnfeAutoCreateEnabledErrors")
                    logger.info(
                        "Profiling group not found. Will try to create a profiling group "
                        "with name = {} and compute platform = {} and retry calling configure agent after 5 minutes. "
                        "Make sure that Lambda's execution role has AmazonCodeGuruProfilerAgentAccess policy added."
                        .format(self.profiling_group_name, 'AWSLambda'))
                    self.create_profiling_group()
                else:
                    self.errors_metadata.record_sdk_error("configureAgentErrors")
                    self.agent_config_merger.disable_profiling()
            else:
                self.errors_metadata.record_sdk_error("configureAgentErrors")
        except Exception as e:
            self._log_request_failed(operation="configure_agent", exception=e)

    @with_timer("report", measurement="wall-clock-time")
    def report(self, profile):
        """
        Report profile to the profiler backend service.

        :param profile: Profile to be encoded and reported to the profiler backend service.
        :return: True if profile gets reported successfully; False otherwise.

        Note:
        For an agent running on AWS Lambda, if the environment variables for Profiling using
        Lambda layers are set, it tries to create a Profiling Group whenever a ResourceNotFoundException
        is encountered.
        """
        try:
            profile_stream = self._encode_profile(profile)
            self.codeguru_client_builder.codeguru_client.post_agent_profile(
                agentProfile=profile_stream,
                contentType='application/json',
                profilingGroupName=self.profiling_group_name
            )
            logger.info("Reported profile successfully")
            return True
        except ClientError as error:
            if error.response['Error']['Code'] == 'ResourceNotFoundException':
                if self.should_auto_create_profiling_group():
                    self.__class__.is_create_pg_called_during_submit_profile = True
                    self.errors_metadata.record_sdk_error("postAgentProfileRnfeAutoCreateEnabledErrors")
                    logger.info(
                        "Profiling group not found. Will try to create a profiling group "
                        "with name = {} and compute platform = {} and retry reporting during next invocation. "
                        "Make sure that Lambda's execution role has AmazonCodeGuruProfilerAgentAccess policy added."
                        .format(self.profiling_group_name, 'AWSLambda'))
                    self.create_profiling_group()
                else:
                    self.errors_metadata.record_sdk_error("postAgentProfileErrors")
            else:
                self.errors_metadata.record_sdk_error("postAgentProfileErrors")
            return False
        except Exception as e:
            self._log_request_failed(operation="post_agent_profile", exception=e)
            return False

    @with_timer("createProfilingGroup", measurement="wall-clock-time")
    def create_profiling_group(self):
        """
        Create a Profiling Group for the AWS Lambda function.
        """
        try:
            self.codeguru_client_builder.codeguru_client.create_profiling_group(
                profilingGroupName=self.profiling_group_name,
                computePlatform='AWSLambda'
            )
            logger.info("Created Lambda Profiling Group with name " + str(self.profiling_group_name))
        except ClientError as error:
            if error.response['Error']['Code'] == 'ConflictException':
                logger.info("Profiling Group with name {} already exists. Please use a different name."
                            .format(self.profiling_group_name))
            else:
                self.errors_metadata.record_sdk_error("createProfilingGroupErrors")
        except Exception as e:
            self._log_request_failed(operation="create_profiling_group", exception=e)

    def should_auto_create_profiling_group(self):
        """
        Currently the only condition we check is to verify that the Compute Platform is AWS Lambda.
        In future, other checks could be places inside this method.
        """
        return self.is_compute_platform_lambda()

    def is_compute_platform_lambda(self):
        """
        Check if the compute platform is AWS Lambda.
        """
        does_lambda_task_root_exist = os.environ.get(LAMBDA_TASK_ROOT)
        does_lambda_runtime_dir_exist = os.environ.get(LAMBDA_RUNTIME_DIR)
        return bool(does_lambda_task_root_exist) and bool(does_lambda_runtime_dir_exist)

    @staticmethod
    def _log_request_failed(operation, exception):
        log_exception(logger, "Failed to call the CodeGuru Profiler service for the {} operation: {}"
                      .format(operation, str(exception)))

    @classmethod
    def check_create_pg_called_during_submit_profile(cls):
        return cls.is_create_pg_called_during_submit_profile

    @classmethod
    def reset_check_create_pg_called_during_submit_profile_flag(cls):
        cls.is_create_pg_called_during_submit_profile = False
