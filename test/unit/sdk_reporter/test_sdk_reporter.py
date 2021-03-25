# -*- coding: utf-8 -*-
import os

import boto3

from datetime import timedelta, datetime

from codeguru_profiler_agent.agent_metadata.aws_lambda import AWSLambda
from codeguru_profiler_agent.utils.time import current_milli_time
from test.pytestutils import before
from mock import MagicMock
from botocore.stub import Stubber, ANY

from codeguru_profiler_agent.reporter.agent_configuration import AgentConfigurationMerger
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from codeguru_profiler_agent.sdk_reporter.sdk_reporter import SdkReporter
from codeguru_profiler_agent.sdk_reporter.profile_encoder import ProfileEncoder
from codeguru_profiler_agent.model.profile import Profile
from codeguru_profiler_agent.codeguru_client_builder import CodeGuruClientBuilder

profiling_group_name = "test-ProfilingGroup-name"
lambda_one_click_profiling_group_name = "aws-lambda-testLambdaName"
test_agent_metadata_for_lambda = AgentMetadata(
    fleet_info=AWSLambda("arn:aws:lambda:us-east-1:111111111111:function:testLambdaName", "memory", "env", "agentId"))
profile = Profile(profiling_group_name, 1.0, 0.5, current_milli_time())


class TestSdkReporter:
    def before(self):
        codeguru_client_builder = CodeGuruClientBuilder(environment={
            "aws_session": boto3.session.Session()
        })

        self.client_stubber = Stubber(codeguru_client_builder.codeguru_client)

        profile_encoder = MagicMock(name="profile_encoder", spec=ProfileEncoder)
        profile_encoder.encode.side_effect = lambda **args: args["output_stream"].write(
            b"test-profile-encoder-output")
        self.environment = {
            "profiling_group_name": profiling_group_name,
            "profile_encoder": profile_encoder,
            "codeguru_profiler_builder": codeguru_client_builder,
            "agent_metadata": AgentMetadata(fleet_info=DefaultFleetInfo()),
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

    def test_creates_pg_if_onboarded_with_lambda_one_click_integration(self):
        expected_params = {
            'agentProfile': ANY,
            'contentType': 'application/json',
            'profilingGroupName': profiling_group_name
        }
        self.client_stubber.add_client_error('post_agent_profile',
                                             service_error_code='ResourceNotFoundException',
                                             service_message='Simulated ResourceNotFoundException in '
                                                             'post_agent_profile call',
                                             expected_params=expected_params)

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
        self.client_stubber.add_response('create_profiling_group', expected_response_create_pg)

        expected_params_one_click = {
            'agentProfile': ANY,
            'contentType': 'application/json',
            'profilingGroupName': lambda_one_click_profiling_group_name
        }
        self.client_stubber.add_response('post_agent_profile', {}, expected_params_one_click)

        os.environ.__setitem__('AWS_CODEGURU_PROFILER_GROUP_NAME', lambda_one_click_profiling_group_name)
        os.environ.__setitem__('HANDLER_ENV_NAME_FOR_CODEGURU', 'test-handler')
        self.subject.metadata = test_agent_metadata_for_lambda
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

        expected_params_post_agent_profile = {
            'agentProfile': ANY,
            'contentType': 'application/json',
            'profilingGroupName': profiling_group_name
        }
        self.client_stubber.add_response('post_agent_profile', {}, expected_params_post_agent_profile)

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
        self.client_stubber.add_response('create_profiling_group', expected_response_create_pg)

        with self.client_stubber:
            assert self.subject.report(profile) is False
            assert self.subject.report(profile) is True
            try:
                self.client_stubber.assert_no_pending_responses()
                assert False
            except AssertionError:
                assert True


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

    def test_when_backends_sends_resource_not_found_it_stops_the_profiling(self):
        self.client_stubber.add_client_error('configure_agent', service_error_code='ResourceNotFoundException',
                                             service_message='Simulated error in configure_agent call')
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert AgentConfiguration.get().should_profile is False

    def test_when_backend_sends_validation_exception_it_stops_the_profiling(self):
        self.client_stubber.add_client_error('configure_agent', service_error_code='ValidationException',
                                             service_message='Simulated error in configure_agent call')
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert AgentConfiguration.get().should_profile is False

    def test_creates_lambda_pg_if_onboarded_with_lambda_one_click_integration(self):
        self.client_stubber.add_client_error('configure_agent',
                                             service_error_code='ResourceNotFoundException',
                                             service_message='Simulated ResourceNotFoundException in '
                                                             'configure_agent call')

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
        self.client_stubber.add_response('create_profiling_group', expected_response_create_pg)

        os.environ.__setitem__('AWS_LAMBDA_FUNCTION_MEMORY_SIZE', "512")
        os.environ.__setitem__('AWS_EXECUTION_ENV', "AWS_Lambda_python3.8")
        os.environ.__setitem__('AWS_CODEGURU_PROFILER_GROUP_NAME', lambda_one_click_profiling_group_name)
        os.environ.__setitem__('HANDLER_ENV_NAME_FOR_CODEGURU', 'test-handler')
        self.subject.metadata = test_agent_metadata_for_lambda
        with self.client_stubber:
            self.subject.refresh_configuration()
            assert self.subject.is_lambda_one_click_pg_created_during_execution is True

    def test_create_pg_not_invoked_in_non_lambda_case(self):
        self.client_stubber.add_client_error('configure_agent',
                                             service_error_code='ResourceNotFoundException',
                                             service_message='Simulated ResourceNotFoundException in '
                                                             'configure_agent call')

        with self.client_stubber:
            self.subject.refresh_configuration()
            assert self.subject.is_lambda_one_click_pg_created_during_execution is False
            try:
                self.client_stubber.assert_no_pending_responses()
                assert False
            except AssertionError:
                assert True
