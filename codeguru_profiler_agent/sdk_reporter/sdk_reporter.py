# -*- coding: utf-8 -*-

import logging
import io
import os

from botocore.exceptions import ClientError
from codeguru_profiler_agent.utils.log_exception import log_exception
from codeguru_profiler_agent.reporter.reporter import Reporter
from codeguru_profiler_agent.metrics.with_timer import with_timer
from codeguru_profiler_agent.sdk_reporter.profile_encoder import ProfileEncoder

logger = logging.getLogger(__name__)
HANDLER_ENV_NAME_FOR_CODEGURU = "HANDLER_ENV_NAME_FOR_CODEGURU"

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
        self.is_lambda_one_click_pg_created_during_execution = False

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
                self.agent_config_merger.disable_profiling()
            if error.response['Error']['Code'] == 'ResourceNotFoundException':
                if self.is_lambda_one_click_integration_active():
                    self.create_pg_when_one_click_integration_is_active()
                else:
                    self.agent_config_merger.disable_profiling()
            self._log_request_failed(operation="configure_agent", exception=error)
        except Exception as e:
            self._log_request_failed(operation="configure_agent", exception=e)

    @with_timer("report", measurement="wall-clock-time")
    def report(self, profile):
        """
        Report profile to the profiler backend service.

        :param profile: Profile to be encoded and reported to the profiler backend service.
        :return: True if profile gets reported successfully; False otherwise.
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
                if self.is_lambda_one_click_integration_active():
                    global is_create_pg_called_during_submit_profile
                    is_create_pg_called_during_submit_profile = True
                    logger.info("Received ResourceNotFoundException. Attempting to create 1-click PG in Report Profile")
                    self.create_pg_when_one_click_integration_is_active()
            return False
        except Exception as e:
            self._log_request_failed(operation="post_agent_profile", exception=e)
            return False

    @with_timer("createOneClickPG", measurement="wall-clock-time")
    def create_pg_when_one_click_integration_is_active(self):
        """
        Create a PG for the Lambda function onboarded with 1-click integration
        """
        function_name = str(self.metadata.fleet_info.function_arn).split(':')[6]

        profiling_group_name_for_1_click = "aws-lambda-{}".format(function_name)
        profiling_group_name_to_be_created = os.getenv("AWS_CODEGURU_PROFILER_GROUP_NAME",
                                                       profiling_group_name_for_1_click)
        try:
            self.codeguru_client_builder.codeguru_client.create_profiling_group(
                profilingGroupName=profiling_group_name_to_be_created,
                computePlatform='AWSLambda'
            )
            self.profiling_group_name = profiling_group_name_to_be_created
            self.is_lambda_one_click_pg_created_during_execution = True
            logger.info("Created Lambda Profiling Group with name {}", profiling_group_name_to_be_created)

        except Exception as e:
            self._log_request_failed(operation="create_profiling_group", exception=e)

    def is_lambda_one_click_integration_active(self):
        """
        Check if the ComputeType is AWSLambda and if the environment
        variables for Lambda Layer Profiling are set
        """
        fleet_info_as_map = self.metadata.fleet_info.serialize_to_map()
        if 'computeType' in fleet_info_as_map:
            if fleet_info_as_map['computeType'] == 'aws_lambda':
                handler_name_ = os.environ.get(HANDLER_ENV_NAME_FOR_CODEGURU)
                if not handler_name_:
                    logger.error("Env Variables for CodeGuru Profiler Lambda Layer are not set. Cannot create PG.")
                    return False
                return True
        return False

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
