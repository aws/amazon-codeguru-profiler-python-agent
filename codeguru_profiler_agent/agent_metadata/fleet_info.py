from abc import ABCMeta, abstractmethod
import uuid
from urllib import request
import os

METADATA_URI_TIMEOUT_SECONDS = 3

def http_get(url):
    # request.urlopen has been flagged as risky because it can be used to open local files if url starts with
    # file://, to protect us from that we add a check in the passed url.
    # With this check we can tell bandit (static analysis tool) to ignore this error with #nosec
    if not url.startswith("http"):
        raise ValueError("url for metadata is not a valid http address. We will not try to get metadata")
    return request.urlopen(url, timeout=METADATA_URI_TIMEOUT_SECONDS)  # nosec


class FleetInfo(metaclass=ABCMeta):  # pragma: no cover
    def __init__(self):
        pass

    """
    Returns the id of the fleet element, that is used to tell if multiple agents come from the same fleet element.
    This id can be the hostname for an EC2 or the task ARN for Fargate.
    @return the id in string.
    """
    @abstractmethod
    def get_fleet_instance_id(self):
        pass

    @abstractmethod
    def serialize_to_map(self):
        pass

    def get_metadata_for_configure_agent_call(self):
        """
        Used for the configure_agent call, the default is to send nothing. Specifics are sent for Lambda.
        """
        return None


class DefaultFleetInfo(FleetInfo):

    def __init__(self):
        self.fleet_instance_id = str(uuid.uuid4())
        try: 
            # sched_getaffinity gives the number of logical cpus that the process can use on Unix systems.
            # If not available, we default to the cpu_count().
            self.vCPUs = len(os.sched_getaffinity(0))
        except AttributeError:
            self.vCPUs = os.cpu_count()

    def get_fleet_instance_id(self):
        return self.fleet_instance_id

    def serialize_to_map(self):
        return {
            "id": self.fleet_instance_id, 
            "type": "UNKNOWN", 
            "vCPUs": self.vCPUs
        }
