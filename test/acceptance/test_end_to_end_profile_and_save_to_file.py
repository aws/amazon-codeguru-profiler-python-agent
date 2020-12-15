import json
import pytest
import shutil
import tempfile
import os

from datetime import timedelta
from mock import patch
from pathlib import Path

from codeguru_profiler_agent.profiler import Profiler
from codeguru_profiler_agent.utils import time as time_utils
from test.help_utils import HelperThreadRunner, TEST_PROFILING_GROUP_NAME
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata, DefaultFleetInfo


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
    @pytest.fixture(autouse=True)
    def around(self):
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

            file_prefix = str(
                Path(self.temporary_directory,
                     "pytest-SkySailPythonAgent-"))

            test_start_time = time_utils.current_milli_time()

            profiler = Profiler(
                profiling_group_name=TEST_PROFILING_GROUP_NAME,
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
                resulting_json = json.loads(profiling_result_file.read())

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
        assert agent_metadata["agentOverhead"]["memory_usage_mb"]
        assert agent_metadata["agentOverhead"]["timeInMs"]
        assert agent_metadata["cpuTimeInSeconds"] > 0
