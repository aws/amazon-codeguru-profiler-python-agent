import json
from platform import python_version

from codeguru_profiler_agent.agent_metadata.aws_ec2_instance import AWSEC2Instance
from codeguru_profiler_agent.agent_metadata.aws_fargate_task import AWSFargateTask
from codeguru_profiler_agent.agent_metadata.fleet_info import DefaultFleetInfo


# NOTE: Please do not alter the value for the following constants without the full knowledge of the use of them.
# These constants are used in several scripts, including setup.py.
__agent_name__ = "CodeGuruProfiler-python"
__agent_version__ = "1.2.2"


def look_up_fleet_info(
        platform_metadata_fetchers=(
                AWSEC2Instance.look_up_metadata,
                AWSFargateTask.look_up_metadata
        )
):
    for metadata_fetcher in platform_metadata_fetchers:
        fleet_info = metadata_fetcher()
        if fleet_info is not None:
            return fleet_info

    return DefaultFleetInfo()


class AgentInfo:
    PYTHON_AGENT = __agent_name__
    CURRENT_VERSION = __agent_version__

    def __init__(self, agent_type=PYTHON_AGENT, version=CURRENT_VERSION):
        self.agent_type = agent_type
        self.version = version

    @classmethod
    def default_agent_info(cls):
        return cls()

    def __eq__(self, other):
        if not isinstance(other, AgentInfo):
            return False

        return self.agent_type == other.agent_type and self.version == other.version


class AgentMetadata:
    """
    This is once instantianted in the profiler.py file, marked as environment variable and reused in the other parts.
    When needed to override for testing other components, update those components to allow a default parameter for
    agent_metadata, or use the environment["agent_metadata"].
    """
    def __init__(self,
                 fleet_info=None,
                 agent_info=AgentInfo.default_agent_info(),
                 runtime_version=python_version()):
        self._fleet_info = fleet_info
        self.agent_info = agent_info
        self.runtime_version = runtime_version
        self.json_rep = None

    @property
    def fleet_info(self):
        if self._fleet_info is None:
            self._fleet_info = look_up_fleet_info()
        return self._fleet_info

    def serialize_to_json(self, sample_weight, duration_ms, cpu_time_seconds,
                          average_num_threads, overhead_ms, memory_usage_mb, total_sample_count):
        """
        This needs to be compliant with agent profile schema.
        """
        if self.json_rep is None:
            self.json_rep = {
                "sampleWeights": {
                    "WALL_TIME": sample_weight
                },
                "durationInMs": duration_ms,
                "fleetInfo": self.fleet_info.serialize_to_map(),
                "agentInfo": {
                    "type": self.agent_info.agent_type,
                    "version": self.agent_info.version
                },
                "agentOverhead": {
                    "memory_usage_mb": memory_usage_mb
                },
                "runtimeVersion": self.runtime_version,
                "cpuTimeInSeconds": cpu_time_seconds,
                "metrics": {
                    "numThreads": average_num_threads
                },
                "numTimesSampled": total_sample_count
            }
            if overhead_ms != 0:
                self.json_rep["agentOverhead"]["timeInMs"] = overhead_ms
        return self.json_rep
