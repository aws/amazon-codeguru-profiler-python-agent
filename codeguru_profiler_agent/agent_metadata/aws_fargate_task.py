import logging
import os
import json
from codeguru_profiler_agent.agent_metadata.fleet_info import FleetInfo, http_get

# https://docs.amazonaws.cn/en_us/AmazonECS/latest/developerguide/task-metadata-endpoint-v4.html
ECS_CONTAINER_METADATA_URI = "ECS_CONTAINER_METADATA_URI_V4"

logger = logging.getLogger(__name__)

class AWSFargateTask(FleetInfo):
    """
    This class will get and parse the Fargate metadata if available.
    Note, limit can be None if no resource limit is defined.
    See https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-metadata-endpoint-v3.html
    """

    def __init__(self, task_arn, cpu_limit, memory_limit_in_mb):
        super().__init__()
        self.task_arn = task_arn
        self.cpu_limit = cpu_limit
        self.memory_limit_in_mb = memory_limit_in_mb

    def get_fleet_instance_id(self):
        return self.task_arn

    @classmethod
    def __look_up_metadata(cls, url):
        return json.load(http_get(url=url + "/task"))


    @classmethod
    def look_up_metadata(cls, url=os.getenv(ECS_CONTAINER_METADATA_URI)):
        """
        The hardcoded keys below are described on
        https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-metadata-endpoint-v3.html
        """
        if not url:
            return None
        try:
            metadata = cls.__look_up_metadata(url=url)

            return cls(
                task_arn=metadata["TaskARN"],
                cpu_limit=metadata.get("Limits", {}).get("CPU"),
                memory_limit_in_mb=metadata.get("Limits", {}).get("Memory")
            )
        except Exception:
            # if we are not in a fargate environment we expect to have url being None so we expect to return before,
            # catching an exception here should be rare so we do print the stack trace.
            logger.info("Unable to get Fargate instance metadata, this is normal when running in a different "
                        "environment (e.g. local dev machine), profiler will still work: ", exc_info=True)
            return None
            
    def serialize_to_map(self):
        fleet_info_in_map = {
            "computeType": "aws_fargate_task", 
            "taskArn": self.task_arn
        }
        if self.cpu_limit is not None:
            fleet_info_in_map["cpuLimit"] = self.cpu_limit
        if self.memory_limit_in_mb is not None:
            fleet_info_in_map["memoryLimitInMB"] = self.memory_limit_in_mb
        return fleet_info_in_map
