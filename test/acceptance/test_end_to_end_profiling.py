from botocore.stub import Stubber, ANY
from datetime import timedelta
from mock import patch
from test.pytestutils import before

from codeguru_profiler_agent.profiler import Profiler
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo
from test.help_utils import DUMMY_TEST_PROFILING_GROUP_NAME


class TestEndToEndProfiling:
    @before
    def before(self):
        self.profiler = Profiler(
            profiling_group_name=DUMMY_TEST_PROFILING_GROUP_NAME,
            environment_override={'initial_sampling_interval': timedelta(),
                                  'agent_metadata': AgentMetadata(fleet_info=DefaultFleetInfo())}
        )
        self.client_stubber = Stubber(
            self.profiler._profiler_runner.collector.reporter.codeguru_client_builder.codeguru_client)
        report_expected_params = {
            'agentProfile': ANY,
            'contentType': 'application/json',
            'profilingGroupName': DUMMY_TEST_PROFILING_GROUP_NAME
        }
        self.client_stubber.add_response('configure_agent',
                                         {'configuration': {'shouldProfile': True, 'periodInSeconds': 100}})
        self.client_stubber.add_response('post_agent_profile', {}, report_expected_params)
        yield
        self.profiler.stop()

    def test_report_when_stopped(self):
        with \
                patch(
                    "codeguru_profiler_agent.reporter.agent_configuration.AgentConfiguration.is_under_min_reporting_time",
                    return_value=False), \
                patch(
                    "codeguru_profiler_agent.sdk_reporter.sdk_reporter.SdkReporter.check_create_pg_called_during_submit_profile",
                    return_value=False):
            with self.client_stubber:
                self.profiler.start()
                self.profiler.stop()  # stop will trigger the report

            # check that we have reported. assert_no_pending_responses will fail if post_agent_profile is not called
            # with the expected parameters.
            self.client_stubber.assert_no_pending_responses()

    def test_report_via_invalid_reporting_mode(self):
        self.profiler = Profiler(
            profiling_group_name=DUMMY_TEST_PROFILING_GROUP_NAME,
            environment_override={
                "reporting_mode": "invalid_reporting_mode",
            })

        self.profiler.start()
        assert self.profiler.is_running() is False
