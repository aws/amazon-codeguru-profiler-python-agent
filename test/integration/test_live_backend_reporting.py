import boto3
import pytest
import socket
import time
import platform

from datetime import timedelta

from codeguru_profiler_agent.agent_metadata.agent_debug_info import ErrorsMetadata, AgentDebugInfo
from test.help_utils import MY_PROFILING_GROUP_NAME_FOR_INTEG_TESTS
from test.pytestutils import before

from codeguru_profiler_agent.model.frame import Frame
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration, AgentConfigurationMerger
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo
from codeguru_profiler_agent.sdk_reporter.sdk_reporter import SdkReporter
from codeguru_profiler_agent.codeguru_client_builder import CodeGuruClientBuilder
from codeguru_profiler_agent.model.profile import Profile
from codeguru_profiler_agent.model.sample import Sample


@pytest.mark.skipif(
    socket.getfqdn().endswith("internal.cloudapp.net"),  # hosts running ubuntu and windows in GitHub
    socket.getfqdn().endswith("ip6.arpa"),  # hosts running macs in GitHub
    reason="This integration test is skipped on any shared fleet from Amazon or GitHub "
           "because it needs credentials to access the backend service. "
           "For information on how to run this locally, read the README.md file from the test/integration/ folder.")
class TestLiveBackendReporting:
    @before
    def before(self):
        now_millis = int(time.time()) * 1000
        five_minutes_ago_millis = now_millis - (5 * 60 * 1000)
        sample = Sample(
            stacks=[[Frame(MY_PROFILING_GROUP_NAME_FOR_INTEG_TESTS)]],
            attempted_sample_threads_count=1,
            seen_threads_count=1)
        errors_metadata = ErrorsMetadata()

        self.profile = Profile(MY_PROFILING_GROUP_NAME_FOR_INTEG_TESTS, 1.0, 1.0, five_minutes_ago_millis,
                               AgentDebugInfo(errors_metadata))
        # FIXME: Remove adding the end time manually below after feature fully support
        self.profile.end = now_millis
        self.profile.add(sample)

        self.environment = {
            "should_profile": True,
            "profiling_group_name": MY_PROFILING_GROUP_NAME_FOR_INTEG_TESTS,
            "aws_session": boto3.session.Session(),
            "reporting_interval": timedelta(minutes=13),
            "sampling_interval": timedelta(seconds=1),
            "minimum_time_reporting": timedelta(minutes=6),
            "max_stack_depth": 2345,
            "cpu_limit_percentage": 29,
            "agent_metadata": AgentMetadata(fleet_info=DefaultFleetInfo()),
            "errors_metadata": errors_metadata
        }
        self.environment["codeguru_profiler_builder"] = CodeGuruClientBuilder(self.environment)
        self.agent_config = AgentConfiguration(
            should_profile=True,
            sampling_interval=self.environment["sampling_interval"],
            reporting_interval=self.environment["reporting_interval"],
            minimum_time_reporting=self.environment["minimum_time_reporting"],
            max_stack_depth=self.environment["max_stack_depth"],
            cpu_limit_percentage=self.environment["cpu_limit_percentage"])

    def test_beta_endpoint_call_report_and_refresh_and_do_not_override_user_overrides_agent_configuration(self):
        if (platform.system == "Darwin"): 
            print(socket.getfqdn())
        self.environment["agent_config_merger"] = AgentConfigurationMerger(user_overrides=self.agent_config)

        sdk_reporter = SdkReporter(self.environment)
        sdk_reporter.setup()

        self.assert_initial_values()
        assert sdk_reporter.report(self.profile) is True

        sdk_reporter.refresh_configuration()
        self.assert_initial_values()

    def test_beta_endpoint_call_report_and_refresh_and_overrides_default_agent_configuration(self):
        self.environment["agent_config_merger"] = AgentConfigurationMerger(default=self.agent_config)

        sdk_reporter = SdkReporter(self.environment)
        sdk_reporter.setup()
        self.assert_initial_values()
        assert sdk_reporter.report(self.profile) is True

        sdk_reporter.refresh_configuration()
        assert AgentConfiguration.get().should_profile is True
        assert AgentConfiguration.get().sampling_interval == timedelta(seconds=1)
        assert AgentConfiguration.get().reporting_interval == timedelta(minutes=5)
        assert AgentConfiguration.get().minimum_time_reporting == timedelta(seconds=60)
        assert AgentConfiguration.get().max_stack_depth == 1000
        assert AgentConfiguration.get().cpu_limit_percentage == 10

    def test_beta_endpoint_call_report_and_refresh_and_do_not_override_one_setting_of_default_agent_configuration(self):
        self.environment["agent_config_merger"] = AgentConfigurationMerger(default=self.agent_config,
                                                                           user_overrides=AgentConfiguration(
                                                                               sampling_interval=timedelta(seconds=2)))

        sdk_reporter = SdkReporter(self.environment)
        sdk_reporter.setup()

        assert AgentConfiguration.get().should_profile is True
        assert AgentConfiguration.get().sampling_interval == timedelta(seconds=2)
        assert AgentConfiguration.get().reporting_interval == timedelta(minutes=13)
        assert AgentConfiguration.get().minimum_time_reporting == timedelta(minutes=6)
        assert AgentConfiguration.get().max_stack_depth == 2345
        assert AgentConfiguration.get().cpu_limit_percentage == 29

        assert sdk_reporter.report(self.profile) is True

        sdk_reporter.refresh_configuration()
        assert AgentConfiguration.get().should_profile is True
        assert AgentConfiguration.get().sampling_interval == timedelta(seconds=2)
        assert AgentConfiguration.get().reporting_interval == timedelta(minutes=5)
        assert AgentConfiguration.get().minimum_time_reporting == timedelta(seconds=60)
        assert AgentConfiguration.get().max_stack_depth == 1000
        assert AgentConfiguration.get().cpu_limit_percentage == 10

    @staticmethod
    def assert_initial_values():
        assert AgentConfiguration.get().should_profile is True
        assert AgentConfiguration.get().sampling_interval == timedelta(seconds=1)
        assert AgentConfiguration.get().reporting_interval == timedelta(minutes=13)
        assert AgentConfiguration.get().minimum_time_reporting == timedelta(minutes=6)
        assert AgentConfiguration.get().max_stack_depth == 2345
        assert AgentConfiguration.get().cpu_limit_percentage == 29
