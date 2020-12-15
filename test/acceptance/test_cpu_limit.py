import socket

import pytest

from datetime import timedelta

from codeguru_profiler_agent.metrics.timer import Timer
from codeguru_profiler_agent.profiler import Profiler
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo
from test.help_utils import wait_for, TEST_PROFILING_GROUP_NAME, _get_credentials

# TODO FIXME Consider moving the integration tests and run them in pipeline as an approval step.
@pytest.mark.skipif(
    not (socket.gethostname().endswith("ant.amazon.com") or socket.gethostname().startswith("dev-dsk")),
    reason="This integration test runs only on local development machines, with access to the backend service.")
class TestCPULimit:
    class TestCPULimitReachedDuringProfiling:
        @pytest.fixture(autouse=True)
        def around(self):
            _get_credentials()

            self.timer = Timer()
            self.profiler = Profiler(
                profiling_group_name=TEST_PROFILING_GROUP_NAME,
                environment_override={
                    "timer": self.timer,
                    "cpu_limit_percentage": 40,
                    "sampling_interval": timedelta(seconds=0.01),
                    'agent_metadata': AgentMetadata(fleet_info=DefaultFleetInfo())
                },
            )
            yield
            self.profiler.stop()

        def test_profiler_terminates(self):
            self.profiler.start()
            assert self.profiler.is_running()

            # With sampling_interval to be 0.01 seconds, having runProfiler as 0.5 seconds should breach
            # the cpu limit. We need to sample 20 times before we check the CPU limit
            for i in range(20):
                self.timer.record('runProfiler', 0.5)

            assert wait_for(lambda: not self.profiler.is_running(), timeout_seconds=5)
