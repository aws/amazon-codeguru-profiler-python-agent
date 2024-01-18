import json
import platform
import shutil
import tempfile
import os

from datetime import timedelta
from unittest.mock import patch
from pathlib import Path

from codeguru_profiler_agent.profiler import Profiler
from codeguru_profiler_agent.utils import time as time_utils
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo
from test.help_utils import HelperThreadRunner, DUMMY_TEST_PROFILING_GROUP_NAME, FILE_PREFIX
from test.pytestutils import before


def frames_in_callgraph_are_in_expected_order(node, parent_frame, child_frame):
    if not "children" in node:
        return False
    for child_node in node["children"]:
        if parent_frame in child_node:
            for grand_child_node in node["children"][child_node]["children"].keys():
                if child_frame in grand_child_node:
                    return True
        if frames_in_callgraph_are_in_expected_order(
                node["children"][child_node], parent_frame, child_frame):
            return True
    return False


class TestEndToEndProfileAndSaveToFile:
    @before
    def before(self):
        self.temporary_directory = tempfile.mkdtemp()

        helper = HelperThreadRunner()
        helper.new_helper_thread_blocked_inside_dummy_method()

        yield

        helper.stop_helper_thread()

        shutil.rmtree(self.temporary_directory)

    def test_it_samples_and_saves_a_profile_to_a_file(self):
        with \
                patch(
                    "codeguru_profiler_agent.reporter.agent_configuration.AgentConfiguration.is_under_min_reporting_time",
                    return_value=False):

            file_prefix = str(Path(self.temporary_directory, FILE_PREFIX))

            test_start_time = time_utils.current_milli_time()


            profiler = Profiler(
                profiling_group_name=DUMMY_TEST_PROFILING_GROUP_NAME,
                environment_override={
                    "initial_sampling_interval": timedelta(),
                    "reporting_mode": "file",
                    "file_prefix": file_prefix,
                    'agent_metadata': AgentMetadata(fleet_info=DefaultFleetInfo())
                })

            try:
                profiler.start()
            finally:
                profiler.stop()

            test_end_time = time_utils.current_milli_time()

            resulting_profile_path = str(
                Path(self.temporary_directory,
                     os.listdir(self.temporary_directory)[0]))
                        
            with (open(resulting_profile_path)) as profiling_result_file:
                file_content = profiling_result_file.read()

            try: 
                resulting_json = json.loads(file_content)
            except json.JSONDecodeError as e:
                raise

            self.assert_valid_agent_metadata(resulting_json["agentMetadata"])
            assert test_start_time <= resulting_json["start"] <= resulting_json["end"] <= test_end_time
            assert frames_in_callgraph_are_in_expected_order(
                resulting_json["callgraph"],
                "test.help_utils:HelperThreadRunner:dummy_parent_method",
                "test.help_utils:HelperThreadRunner:dummy_method")

    @staticmethod
    def assert_valid_agent_metadata(agent_metadata):
        assert agent_metadata["agentInfo"]
        assert agent_metadata["fleetInfo"]
        assert agent_metadata["runtimeVersion"]
        assert agent_metadata["sampleWeights"]
        assert agent_metadata["agentOverhead"]
        assert agent_metadata["durationInMs"]
        assert agent_metadata["sampleWeights"]["WALL_TIME"]
        assert type(agent_metadata["agentOverhead"]["memoryInMB"]) is int

        if platform.system() != "Windows":
            # Due to the issue mentioned on https://bugs.python.org/issue37859, we would skip checking agentOverhead for
            # Windows system as the agent is only run for very short period of time. We may improve the accuracy of
            # measuring the overhead by using time.perf_counter_ns for Windows in the future.
            assert type(agent_metadata["agentOverhead"]["timeInMs"]) is int
            assert agent_metadata["cpuTimeInSeconds"] > 0
