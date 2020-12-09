import socket
import tempfile
import shutil
import pytest

from datetime import timedelta
from pathlib import Path

from codeguru_profiler_agent.profiler import Profiler
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo
from test.help_utils import wait_for, TEST_PROFILING_GROUP_NAME, _get_credentials


class TestKillSwitch:
    class TestKillSwitchActivatesAtStart:
        def test_profiler_does_not_start(self):
            with tempfile.NamedTemporaryFile() as killswitch_file:
                profiler = Profiler(
                    profiling_group_name=TEST_PROFILING_GROUP_NAME,
                    environment_override={"killswitch_filepath": killswitch_file.name})

                try:
                    assert profiler.start() is False
                finally:
                    profiler.stop()

    # TODO FIXME Consider moving the integration tests and run them in pipeline as an approval step.
    @pytest.mark.skipif(
        not (socket.gethostname().endswith("ant.amazon.com") or socket.gethostname().startswith("dev-dsk")),
        reason="This integration test runs only on local development machines, with access to the backend service.")
    class TestKillSwitchActivatesDuringExecution:
        @pytest.fixture(autouse=True)
        def around(self):
            _get_credentials()

            temporary_directory = tempfile.mkdtemp()
            self.temp_filepath = str(
                Path(temporary_directory,
                     'test_profiler_stops_after_killswitch_was_detected'))

            self.profiler = Profiler(
                profiling_group_name="test-application",
                environment_override={
                    "cpu_limit_percentage": None,
                    "killswitch_filepath": self.temp_filepath,
                    "sampling_interval": timedelta(seconds=0.1),
                    'agent_metadata': AgentMetadata(fleet_info=DefaultFleetInfo())
                })
            yield
            shutil.rmtree(temporary_directory)
            self.profiler.stop()

        def test_profiler_stops_after_killswitch_was_detected(self):
            self.profiler.start()
            assert self.profiler.is_running() is True

            Path(self.temp_filepath).touch()

            # Force the killswitch check happens immediately
            self.profiler._profiler_runner_instance.profiler_disabler.killswitch.last_check_for_file_time = None

            assert (wait_for(lambda: not self.profiler.is_running(), timeout_seconds=5))
