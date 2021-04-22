# -*- coding: utf-8 -*-
import os

import boto3

from datetime import timedelta, datetime

from codeguru_profiler_agent.agent_metadata.agent_debug_info import ErrorsMetadata, AgentDebugInfo
from codeguru_profiler_agent.utils.time import current_milli_time
from test.pytestutils import before
from unittest.mock import MagicMock
from botocore.stub import Stubber, ANY

from codeguru_profiler_agent.reporter.agent_configuration import AgentConfigurationMerger
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo
from codeguru_profiler_agent.agent_metadata.aws_lambda import LAMBDA_EXECUTION_ENV, \
    LAMBDA_MEMORY_SIZE_ENV, LAMBDA_TASK_ROOT, LAMBDA_RUNTIME_DIR
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from codeguru_profiler_agent.sdk_reporter.sdk_reporter import SdkReporter
from codeguru_profiler_agent.sdk_reporter.profile_encoder import ProfileEncoder
from codeguru_profiler_agent.model.profile import Profile
from codeguru_profiler_agent.codeguru_client_builder import CodeGuruClientBuilder

profiling_group_name = "test-ProfilingGroup-name"
autocreated_test_lambda_profiling_group_name = "aws-lambda-testLambdaName"
errors_metadata = ErrorsMetadata()
profile = Profile(profiling_group_name, 1.0, 0.5, current_milli_time(), AgentDebugInfo(errors_metadata))
expected_response_create_pg = {
    'profilingGroup': {
        'agentOrchestrationConfig': {
            'profilingEnabled': True
        },
        'arn': 'string',
        'computePlatform': 'AWSLambda',
        'createdAt': datetime(2015, 1, 1),
        'name': 'string',
        'profilingStatus': {
            'latestAgentOrchestratedAt': datetime(2015, 1, 1),
            'latestAgentProfileReportedAt': datetime(2015, 1, 1),
            'latestAggregatedProfile': {
                'period': 'PT5M',
                'start': datetime(2015, 1, 1)
            }
        },
        'tags': {
            'string': 'string'
        },
        'updatedAt': datetime(2015, 1, 1)
    }
}


class TestSdkReporter:
    def before(self):
        codeguru_client_builder = CodeGuruClientBuilder(environment={
            "aws_session": boto3.session.Session()
        })

        self.client_stubber = Stubber(codeguru_client_builder.codeguru_client)

        self.clear_lambda_specific_environment_variables_for_test_run()

        profile_encoder = MagicMock(name="profile_encoder", spec=ProfileEncoder)
        profile_encoder.encode.side_effect = lambda **args: args["output_stream"].write(
            b"test-profile-encoder-output")
        self.environment = {
            "profiling_group_name": profiling_group_name,
            "profile_encoder": profile_encoder,
            "codeguru_profiler_builder": codeguru_client_builder,
            "agent_metadata": AgentMetadata(fleet_info=DefaultFleetInfo()),
            "errors_metadata": errors_metadata,
            "reporting_interval": timedelta(minutes=13),
            "sampling_interval": timedelta(seconds=13),
            "minimum_time_reporting": timedelta(minutes=13),
            "max_stack_depth": 1300
        }
        default_config = AgentConfiguration(
            should_profile=True,
            sampling_interval=self.environment["sampling_interval"],
            reporting_interval=self.environment["reporting_interval"],
            minimum_time_reporting=self.environment["minimum_time_reporting"])
        self.environment["agent_config_merger"] = AgentConfigurationMerger(default_config)
        self.subject = SdkReporter(environment=self.environment)
        self.subject.setup()
        self.subject.errors_metadata.reset()

    def clear_lambda_specific_environment_variables_for_test_run(self):
        keys_to_delete = [LAMBDA_TASK_ROOT, LAMBDA_RUNTIME_DIR, LAMBDA_EXECUTION_ENV, LAMBDA_MEMORY_SIZE_ENV]
        for key in keys_to_delete:
            if key in os.environ:
                os.environ.__delitem__(key)


class TestReport(TestSdkReporter):
    @before
    def before(self):
        super().before()

    def test_report_calls_the_client(self):
        expected_params = {
            'agentProfile': ANY,
            'contentType': 'application/json',
            'profilingGroupName': profiling_group_name
        }
        self.client_stubber.add_response('post_agent_profile', {}, expected_params)

        with self.client_stubber:
            assert self.subject.report(profile) is True

    def test_return_false_when_report_throws_error(self):
        self.client_stubber.add_client_error('post_agent_profile', http_status_code=500,
                                             service_message='Simulated error in post_agent_profile call')
        with self.client_stubber:
            assert self.subject.report(profile) is False

    def test_errors_metadata_when_post_agent_profile_error(self):
        self.client_stubber.add_client_error('post_agent_profile', service_error_code="InternalFailure",
                                             service_message='Simulated error in post_agent_profile call')
        with self.client_stubber:
            assert self.subject.report(profile) is False
            assert self.subject.errors_metadata.serialize_to_json() == {
                "configureAgentErrors": 0,
                "configureAgentRnfeAutoCreateEnabledErrors": 0,
                "createProfilingGroupErrors": 0,
                "errorsCount": 1,
                "postAgentProfileErrors": 1,
                "postAgentProfileRnfeAutoCreateEnabledErrors": 0,
                "sdkClientErrors": 1
            }

    def test_errors_metadata_when_post_agent_profile_rnfe_error(self):
        self.client_stubber.add_client_error('post_agent_profile', service_error_code="ResourceNotFoundException",
                                             service_message='Simulated error in post_agent_profile call')
        with self.client_stubber:
            assert self.subject.report(profile) is False
            assert self.subject.errors_metadata.serialize_to_json() == {
                "configureAgentErrors": 0,
                "configureAgentRnfeAutoCreateEnabledErrors": 0,
                "createProfilingGroupErrors": 0,
                "errorsCount": 1,
                "postAgentProfileErrors": 1,
                "postAgentProfileRnfeAutoCreateEnabledErrors": 0,
                "sdkClientErrors": 1
            }

    def test_errors_metadata_when_post_agent_profile_rnfe_error_auto_create_enabled(self):
        self.client_stubber.add_client_error('post_agent_profile', service_error_code="ResourceNotFoundException",
                                             service_message='Simulated error in post_agent_profile call')
        self.client_stubber.add_response('create_profiling_group', expected_response_create_pg)

        os.environ.__setitem__(LAMBDA_TASK_ROOT, 'test-task-root')
        os.environ.__setitem__(LAMBDA_RUNTIME_DIR, 'test-dir')

        with self.client_stubber:
            assert self.subject.report(profile) is False
            assert self.subject.errors_metadata.serialize_to_json() == {
                "configureAgentErrors": 0,
                "configureAgentRnfeAutoCreateEnabledErrors": 0,
                "createProfilingGroupErrors": 0,
                "errorsCount": 1,
                "postAgentProfileErrors": 0,
                "postAgentProfileRnfeAutoCreateEnabledErrors": 1,
                "sdkClientErrors": 1
            }

    def test_create_profiling_group_called_when_pg_does_not_exist_lambda_case(self):
        expected_params = {
            'agentProfile': ANY,
            'contentType': 'application/json',
            'profilingGroupName': autocreated_test_lambda_profiling_group_name
        }
        self.client_stubber.add_client_error('post_agent_profile',
                                             service_error_code='ResourceNotFoundException',
                                             service_message='Simulated ResourceNotFoundException in '
                                                             'post_agent_profile call',
                                             expected_params=expected_params)

        self.client_stubber.add_response('create_profiling_group', expected_response_create_pg)

        expected_params_post_agent_profile = {
            'agentProfile': ANY,
            'contentType': 'application/json',
            'profilingGroupName': autocreated_test_lambda_profiling_group_name
        }
        self.client_stubber.add_response('post_agent_profile', {}, expected_params_post_agent_profile)

        os.environ.__setitem__(LAMBDA_TASK_ROOT, 'test-task-root')
        os.environ.__setitem__(LAMBDA_RUNTIME_DIR, 'test-dir')
        self.subject.profiling_group_name = autocreated_test_lambda_profiling_group_name

        with self.client_stubber:
            assert self.subject.report(profile) is False
            assert self.subject.report(profile) is True

    def test_create_pg_not_invoked_in_non_lambda_case(self):
        expected_params = {
            'agentProfile': ANY,
            'contentType': 'application/json',
            'profilingGroupName': profiling_group_name
        }
        self.client_stubber.add_client_error('post_agent_profile',
                                             service_error_code="ResourceNotFoundException",
                                             service_message='Simulated ResourceNotFoundException in '
                                                             'post_agent_profile call',
                                             expected_params=expected_params)

        with self.client_stubber:
            assert self.subject.report(profile) is False
            self.client_stubber.assert_no_pending_responses()


class TestConfigureAgent(TestSdkReporter):
    @before
    def before(self):
        super().before()

    def test_configure_agent_calls_the_client(self):
        response = {
            'configuration': {
                'agentParameters': {
                    'SamplingIntervalInMilliseconds': '91000',
                    'MinimumTimeForReportingInMilliseconds': '60000',
                    'MaxStackDepth': '1001'
                },
                'periodInSeconds': 123,
                'shouldProfile': False
            }
        }
        self.client_stubber.add_response('configure_agent', response)
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert AgentConfiguration.get().should_profile is False
            assert AgentConfiguration.get().sampling_interval.total_seconds() == 91

    def test_agent_configuration_when_configure_agent_throws_error(self):
        self.client_stubber.add_client_error('configure_agent', http_status_code=500,
                                             service_message='Simulated error in configure_agent call')
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert AgentConfiguration.get().should_profile is True
            assert AgentConfiguration.get().sampling_interval == timedelta(seconds=13)

    def test_errors_metadata_when_configure_agent_error(self):
        self.client_stubber.add_client_error('configure_agent', service_error_code="InternalFailure",
                                             service_message='Simulated error in configure_agent call')
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert self.subject.errors_metadata.serialize_to_json() == {
                "configureAgentErrors": 1,
                "configureAgentRnfeAutoCreateEnabledErrors": 0,
                "createProfilingGroupErrors": 0,
                "errorsCount": 1,
                "postAgentProfileErrors": 0,
                "postAgentProfileRnfeAutoCreateEnabledErrors": 0,
                "sdkClientErrors": 1
            }

    def test_errors_metadata_when_configure_agent_validation_exception_error(self):
        self.client_stubber.add_client_error('configure_agent', service_error_code="ValidationException",
                                             service_message='Simulated error in configure_agent call')
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert self.subject.errors_metadata.serialize_to_json() == {
                "configureAgentErrors": 1,
                "configureAgentRnfeAutoCreateEnabledErrors": 0,
                "createProfilingGroupErrors": 0,
                "errorsCount": 1,
                "postAgentProfileErrors": 0,
                "postAgentProfileRnfeAutoCreateEnabledErrors": 0,
                "sdkClientErrors": 1
            }

    def test_errors_metadata_when_configure_agent_rnfe_error(self):
        self.client_stubber.add_client_error('configure_agent', service_error_code="ResourceNotFoundException",
                                             service_message='Simulated error in configure_agent call')
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert self.subject.errors_metadata.serialize_to_json() == {
                "configureAgentErrors": 1,
                "configureAgentRnfeAutoCreateEnabledErrors": 0,
                "createProfilingGroupErrors": 0,
                "errorsCount": 1,
                "postAgentProfileErrors": 0,
                "postAgentProfileRnfeAutoCreateEnabledErrors": 0,
                "sdkClientErrors": 1
            }

    def test_errors_metadata_when_configure_agent_rnfe_error_auto_create_enabled(self):
        self.client_stubber.add_client_error('configure_agent', service_error_code="ResourceNotFoundException",
                                             service_message='Simulated error in configure_agent call')
        self.client_stubber.add_response('create_profiling_group', expected_response_create_pg)

        os.environ.__setitem__(LAMBDA_TASK_ROOT, 'test-task-root')
        os.environ.__setitem__(LAMBDA_RUNTIME_DIR, 'test-dir')

        with self.client_stubber:
            self.subject.refresh_configuration()
            assert self.subject.errors_metadata.serialize_to_json() == {
                "configureAgentErrors": 0,
                "configureAgentRnfeAutoCreateEnabledErrors": 1,
                "createProfilingGroupErrors": 0,
                "errorsCount": 1,
                "postAgentProfileErrors": 0,
                "postAgentProfileRnfeAutoCreateEnabledErrors": 0,
                "sdkClientErrors": 1
            }

    def test_when_backends_sends_resource_not_found_it_stops_the_profiling_in_non_lambda_case(self):
        self.client_stubber.add_client_error('configure_agent', service_error_code='ResourceNotFoundException',
                                             service_message='Simulated error in configure_agent call')
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert AgentConfiguration.get().should_profile is False

    def test_when_backends_sends_resource_not_found_it_does_not_stop_the_profiling_in_lambda_case(self):
        self.client_stubber.add_client_error('configure_agent', service_error_code='ResourceNotFoundException',
                                             service_message='Simulated error in configure_agent call')
        os.environ.__setitem__(LAMBDA_TASK_ROOT, 'test-task-root')
        os.environ.__setitem__(LAMBDA_RUNTIME_DIR, 'test-dir')
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert AgentConfiguration.get().should_profile is True

    def test_when_backend_sends_validation_exception_it_stops_the_profiling(self):
        self.client_stubber.add_client_error('configure_agent', service_error_code='ValidationException',
                                             service_message='Simulated error in configure_agent call')
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert AgentConfiguration.get().should_profile is False

    def test_create_profiling_group_called_when_pg_does_not_exist_in_lambda_case(self):
        self.client_stubber.add_client_error('configure_agent',
                                             service_error_code='ResourceNotFoundException',
                                             service_message='Simulated ResourceNotFoundException in '
                                                             'configure_agent call')

        self.client_stubber.add_response('create_profiling_group', expected_response_create_pg)

        os.environ.__setitem__(LAMBDA_MEMORY_SIZE_ENV, "512")
        os.environ.__setitem__(LAMBDA_EXECUTION_ENV, "AWS_Lambda_python3.8")
        os.environ.__setitem__(LAMBDA_TASK_ROOT, 'test-task-root')
        os.environ.__setitem__(LAMBDA_RUNTIME_DIR, 'test-dir')
        self.subject.profiling_group_name = autocreated_test_lambda_profiling_group_name
        with self.client_stubber:
            self.subject.refresh_configuration()
            self.client_stubber.assert_no_pending_responses()

    def test_create_pg_not_invoked_in_non_lambda_case(self):
        self.client_stubber.add_client_error('configure_agent',
                                             service_error_code='ResourceNotFoundException',
                                             service_message='Simulated ResourceNotFoundException in '
                                                             'configure_agent call')

        with self.client_stubber:
            self.subject.refresh_configuration()
            self.client_stubber.assert_no_pending_responses()


class TestCreateProfilingGroup(TestSdkReporter):
    @before
    def before(self):
        super().before()

    def test_errors_metadata_when_create_profiling_group_error(self):
        self.client_stubber.add_client_error('create_profiling_group', service_error_code="InternalFailure",
                                             service_message='Simulated error in create_profiling_group call')
        with self.client_stubber:
            self.subject.create_profiling_group()
            assert self.subject.errors_metadata.serialize_to_json() == {
                "configureAgentErrors": 0,
                "configureAgentRnfeAutoCreateEnabledErrors": 0,
                "createProfilingGroupErrors": 1,
                "errorsCount": 1,
                "postAgentProfileErrors": 0,
                "postAgentProfileRnfeAutoCreateEnabledErrors": 0,
                "sdkClientErrors": 1
            }
