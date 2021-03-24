import logging
from codeguru_profiler_agent.utils.log_exception import log_exception
from codeguru_profiler_agent.agent_metadata.fleet_info import FleetInfo, http_get

# Currently, there is not a utility function in boto3 to retrieve the instance metadata; hence we would need
# get the metadata through URI.
# See https://github.com/boto/boto3/issues/313 for tracking the work for supporting such function in boto3
DEFAULT_EC2_METADATA_URI = "http://169.254.169.254/latest/meta-data/"
EC2_HOST_NAME_URI = DEFAULT_EC2_METADATA_URI + "local-hostname"
EC2_HOST_INSTANCE_TYPE_URI = DEFAULT_EC2_METADATA_URI + "instance-type"

# Used for IMDSv2 to retrieve API token that will be used to call the EC2 METADATA service.
# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instancedata-data-retrieval.html
# Bandit marks the following line as risky because it contains the word "token",
# thought it doesn't contain any secret; ignoring with # nosec
# https://bandit.readthedocs.io/en/latest/plugins/b105_hardcoded_password_string.html
EC2_API_TOKEN_URI = "http://169.254.169.254/latest/api/token"  # nosec
EC2_METADATA_TOKEN_HEADER_KEY = 'X-aws-ec2-metadata-token'  # nosec
EC2_METADATA_TOKEN_TTL_HEADER_KEY = 'X-aws-ec2-metadata-token-ttl-seconds'  # nosec
EC2_METADATA_TOKEN_TTL_HEADER_VALUE = '21600'  # nosec

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
    def __look_up_host_name(cls, token):
        """
        The id of the fleet element. Eg. host name in ec2.
        """
        return cls.__look_up_with_IMDSv2(EC2_HOST_NAME_URI, token)

    @classmethod
    def __look_up_instance_type(cls, token):
        """
        The type of the instance. Eg. m5.2xlarge
        """
        return cls.__look_up_with_IMDSv2(EC2_HOST_INSTANCE_TYPE_URI, token)

    @classmethod
    def __look_up_with_IMDSv2(cls, url, token):
        return http_get(url=url,
                        headers={EC2_METADATA_TOKEN_HEADER_KEY: token}) \
            .read().decode()

    @classmethod
    def __look_up_ec2_api_token(cls):
        return http_get(url=EC2_API_TOKEN_URI,
                        headers={EC2_METADATA_TOKEN_TTL_HEADER_KEY: EC2_METADATA_TOKEN_TTL_HEADER_VALUE}) \
            .read().decode()

    @classmethod
    def look_up_metadata(cls):
        try:
            token = cls.__look_up_ec2_api_token()
            return cls(
                host_name=cls.__look_up_host_name(token),
                host_type=cls.__look_up_instance_type(token)
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
