"""
This module handles creating the CodeGuru Profiler client.
"""
import boto3
import logging

from botocore.config import Config

logger = logging.getLogger(__name__)


class CodeGuruClientBuilder:
    """
    Utility class that can create the CodeGuru Profiler sdk client.
    The goal is to make sure it is created only when needed, hopefully inside the profiler runner so the customer's code
    is not blocked waiting for the sdk client to be built.
    This is also useful to share the client between the reporter and the orchestrator.
    The client can be provided directly in the environment with key 'codeguru_profiler_client' this can used for
    testing or customization.
    If no client is provided explicitly, it creates a client with the boto3.Session object either provided directly
    by customer or the default aws session will be used.
    """

    def __init__(self, environment):
        self._provided_endpoint_url = environment.get("endpoint_url")
        self._codeguru_client_instance = environment.get("codeguru_profiler_client")
        self._aws_session = environment.get("aws_session")
        self._region_name = environment.get("region_name")

    @property
    def codeguru_client(self):
        """
        Creates an client instance the first time it is called.
        :return: a codeguru client object from the AWS SDK
        """
        if self._codeguru_client_instance is None:
            logger.debug("Initializing an instance of a codeguru client.")
            self._codeguru_client_instance = self._create_codeguru_client()
        return self._codeguru_client_instance

    def _create_codeguru_client(self):
        region = self._get_region_or_default()

        # the default retry mode is 'legacy', not 'standard'
        standard_config = Config(
            retries={
                'mode': 'standard'
            }
        )
        return self._get_session_or_default().client(
            service_name='codeguruprofiler',
            region_name=region,
            endpoint_url=self._provided_endpoint_url,
            config=standard_config)

    def _get_region_or_default(self):
        """
        Creating a AWS client can fail with NoRegionError if there was no way for the sdk to detect the region
        If the region is not specified in the client constructor through providing boto3.Session, the sdk would
        search in ~/.aws/config or AWS_DEFAULT_REGION
        Any user running in an EC2, lambda, fargate... etc would have this set somehow but to prevent the agent from
        crashing for customers running on a different environment we will set region to IAD with a warning if there is
        not one defined.
        """
        region_from_session = self._get_session_or_default().region_name
        if self._region_name is not None:
            if region_from_session is not None and self._region_name != region_from_session:
                logger.info("Different region settings were detected - session: {region_from_session}, "
                            "parameter: {region_from_param}. By default, client will be created with region "
                            "specified in parameter: {region_from_param}"
                            .format(region_from_session=region_from_session, region_from_param=self._region_name))
            return self._region_name

        # let the SDK search for the region...
        if region_from_session is not None:
            return region_from_session

        # No region has been set, creating an AWS client will fail in this case, set region to IAD by default.
        # Debatable if we want to do this best effort here. We could simply let the boto3 client raise an exception
        # when it finds that there is no way to chose the region. I decided to do this for our agent not to block the
        # process for users running it in local environment, even if it will probably not work unless their profiling
        # group happens to be in IAD. This also saves us from having to set a region everywhere in unit tests.
        logger.info(
            "AWS SDK was not able to detect the region either from config file or environment variable, "
            + "default region will be set to us-east-1. Make sure you set the region_name parameter in the "
            + "Profiler constructor to the region in which you created your profiling group. "
            + "See https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html for other ways."
        )
        return "us-east-1"

    def _get_session_or_default(self):
        """
        Creates a default boto3 session if it was not provided in init.
        """
        if not self._aws_session:
            self._aws_session = boto3.session.Session()
        return self._aws_session
