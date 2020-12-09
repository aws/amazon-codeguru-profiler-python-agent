# -*- coding: utf-8 -*-
import boto3

from datetime import timedelta
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
profile = Profile(profiling_group_name, 1.0, 0.5, current_milli_time())


class TestSdkReporter:
    @before
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

    class TestReport:
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

    class TestConfigureAgent:
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

        class TestWhenBackendsSendsResourceNotFound:
            def test_it_stops_the_profiling(self):
                self.client_stubber.add_client_error('configure_agent', service_error_code='ResourceNotFoundException',
                                                     service_message='Simulated error in configure_agent call')
                with self.client_stubber:
                    self.subject.refresh_configuration()
                    assert AgentConfiguration.get().should_profile is False

        class TestWhenBackendsSendsValidationException:
            def test_it_stops_the_profiling(self):
                self.client_stubber.add_client_error('configure_agent', service_error_code='ValidationException',
                                                     service_message='Simulated error in configure_agent call')
                with self.client_stubber:
                    self.subject.refresh_configuration()
                    assert AgentConfiguration.get().should_profile is False
