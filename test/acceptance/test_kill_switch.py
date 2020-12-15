import tempfile
import shutil

from datetime import timedelta
from pathlib import Path

from codeguru_profiler_agent.profiler import Profiler
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo
from test.help_utils import wait_for, DUMMY_TEST_PROFILING_GROUP_NAME
from test.pytestutils import before


class TestKillSwitch:
    class TestKillSwitchActivatesAtStart:
        def test_profiler_does_not_start(self):
            with tempfile.NamedTemporaryFile() as killswitch_file:
                profiler = Profiler(
                    profiling_group_name=DUMMY_TEST_PROFILING_GROUP_NAME,
                    environment_override={"killswitch_filepath": killswitch_file.name})

                try:
                    assert profiler.start() is False
                finally:
                    profiler.stop()

    class TestKillSwitchActivatesDuringExecution:
        @before
        def before(self):
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
