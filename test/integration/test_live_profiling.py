import pytest
import socket
import time

from datetime import timedelta
from mock import patch

from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from codeguru_profiler_agent.profiler import Profiler
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo

TEST_PROFILING_GROUP_NAME = "integrationTest"


class TestLiveProfiling:

    def test_live_profiling(self):
        with \
                patch(
                    "codeguru_profiler_agent.reporter.agent_configuration.AgentConfiguration.is_under_min_reporting_time",
                    return_value=False), \
                patch(
                    "codeguru_profiler_agent.reporter.agent_configuration.AgentConfiguration._is_reporting_interval_smaller_than_minimum_allowed",
                    return_value=False):

            profiler = Profiler(
                profiling_group_name=TEST_PROFILING_GROUP_NAME,
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
                    time.sleep(3)
                finally:
                    profiler.stop()

                assert wrapped_add.call_count >= 3
                assert wrapped_post_agent_profile.call_count >= 1
                assert wrapped_configure_agent.call_count >= 1
                assert AgentConfiguration.get().sampling_interval == timedelta(seconds=1)
                assert AgentConfiguration.get().reporting_interval == timedelta(seconds=2)
