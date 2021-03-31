import time

from datetime import timedelta
from unittest.mock import patch

from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from codeguru_profiler_agent.sdk_reporter.sdk_reporter import SdkReporter
from codeguru_profiler_agent.profiler import Profiler
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo
from test.help_utils import DUMMY_TEST_PROFILING_GROUP_NAME


class TestLiveProfiling:

    def test_live_profiling(self):
        with \
                patch(
                    "codeguru_profiler_agent.reporter.agent_configuration.AgentConfiguration.is_under_min_reporting_time",
                    return_value=False), \
                patch(
                    "codeguru_profiler_agent.sdk_reporter.sdk_reporter.SdkReporter.check_create_pg_called_during_submit_profile",
                    return_value=False), \
                patch(
                    "codeguru_profiler_agent.reporter.agent_configuration.AgentConfiguration._is_reporting_interval_smaller_than_minimum_allowed",
                    return_value=False):

            profiler = Profiler(
                profiling_group_name=DUMMY_TEST_PROFILING_GROUP_NAME,
                region_name='eu-west-2',
                environment_override={"initial_sampling_interval": timedelta(),
                                      "sampling_interval": timedelta(seconds=1),
                                      "reporting_interval": timedelta(seconds=2),
                                      'agent_metadata': AgentMetadata(fleet_info=DefaultFleetInfo())}
            )

            client = profiler._profiler_runner.collector.reporter.codeguru_client_builder.codeguru_client
            aggregator = profiler._profiler_runner.collector

            assert AgentConfiguration.get().sampling_interval == timedelta(seconds=1)
            assert AgentConfiguration.get().reporting_interval == timedelta(seconds=2)

            with \
                    patch.object(client, "post_agent_profile",
                                 wraps=client.post_agent_profile) as wrapped_post_agent_profile, \
                    patch.object(client, "configure_agent",
                                 wraps=client.configure_agent) as wrapped_configure_agent, \
                    patch.object(aggregator, "add",
                                 wraps=aggregator.add) as wrapped_add, \
                    patch(
                        "codeguru_profiler_agent.reporter.agent_configuration.AgentConfiguration.is_under_min_reporting_time",
                        return_value=False), \
                    patch(
                        "codeguru_profiler_agent.reporter.agent_configuration.AgentConfiguration._is_reporting_interval_smaller_than_minimum_allowed",
                        return_value=False):

                wrapped_configure_agent.return_value = {
                    "configuration": {
                        "agentParameters": {
                            "SamplingIntervalInMilliseconds": "100",
                            "MinimumTimeForReportingInMilliseconds": "1000",
                            "MaxStackDepth": "1000",
                            "MemoryUsageLimitPercent": "29"
                        },
                        "periodInSeconds": 2,
                        "shouldProfile": True
                    }
                }

                try:
                    start_status = profiler.start()
                    assert start_status
                    assert profiler.is_running()
                    time.sleep(4)
                finally:
                    profiler.stop()

                # We should see at least 2 samples in 4 seconds as the sequence should happen in the order of
                # initial delay (1 second)
                # After 1 second, no flush -> sample
                # After 2 seconds, it attempt to flush (possibly succeed) -> sample/ no sample
                # After 3 seconds, it attempt to flush (must succeed if it did not flush before) -> no sample/ sample
                # After 4 seconds, no flush -> sample (if profiler has not stopped yet)
                assert wrapped_add.call_count >= 2
                assert wrapped_post_agent_profile.call_count >= 1
                assert wrapped_configure_agent.call_count >= 1
                assert AgentConfiguration.get().sampling_interval == timedelta(seconds=1)
                assert AgentConfiguration.get().reporting_interval == timedelta(seconds=2)
