import logging
from codeguru_profiler_agent.utils.log_exception import log_exception
from codeguru_profiler_agent.agent_metadata.fleet_info import FleetInfo, http_get

# Currently, there is not a utility function in boto3 to retrieve the instance metadata; hence we would need
# get the metadata through URI.
# See https://github.com/boto/boto3/issues/313 for tracking the work for supporting such function in boto3
DEFAULT_EC2_METADATA_URI = "http://169.254.169.254/latest/meta-data/"
EC2_HOST_NAME_URI = DEFAULT_EC2_METADATA_URI + "local-hostname"
EC2_HOST_INSTANCE_TYPE_URI = DEFAULT_EC2_METADATA_URI + "instance-type"

logger = logging.getLogger(__name__)

class AWSEC2Instance(FleetInfo):
    """
    This class will get and parse the EC2 metadata if available.
    See https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instancedata-data-retrieval.html.
    """

    def __init__(self, host_name, host_type):
        super().__init__()
        self.host_name = host_name
        self.host_type = host_type

    def get_fleet_instance_id(self):
        return self.host_name

    @classmethod
    def __look_up_host_name(cls):
        # The id of the fleet element. Eg. host name in ec2.
        return http_get(url=EC2_HOST_NAME_URI).read().decode()

    @classmethod
    def __look_up_instance_type(cls):
        return http_get(url=EC2_HOST_INSTANCE_TYPE_URI).read().decode()

    @classmethod
    def look_up_metadata(cls):
        try:
            return cls(
                host_name=cls.__look_up_host_name(),
                host_type=cls.__look_up_instance_type()
            )
        except Exception:
            log_exception(logger, "Unable to get Ec2 instance metadata, this is normal when running in a different "
                                  "environment (e.g. Fargate), profiler will still work")
            return None
    
    def serialize_to_map(self):
        return {
            "computeType": "aws_ec2_instance", 
            "hostName": self.host_name, 
            "hostType": self.host_type
        }
