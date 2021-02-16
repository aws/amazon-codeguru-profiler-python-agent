import logging
import datetime

from codeguru_profiler_agent.reporter.reporter import Reporter
from codeguru_profiler_agent.sdk_reporter.profile_encoder import ProfileEncoder

logger = logging.getLogger(__name__)


class FileReporter(Reporter):
    """
    Writes JSON-encoded profiles to a file; this is used for testing purposes.
    """

    _FILE_SUFFIX = ".json"

    def __init__(self, environment=dict()):
        """
        :param environment: dependency container dictionary for the current profiler
        :param file_prefix: (required inside environment) path + file prefix to use for profile reports
        """
        self._file_prefix = environment["file_prefix"]
        self._profile_encoder = \
            environment.get("profile_encoder") or ProfileEncoder(gzip=False, environment=environment)

    def setup(self):
        """
        File reporter has static configuration, no expensive resources to be initialized.
        """
        pass

    def refresh_configuration(self):
        """
        File reporter has static configuration, no refresh.
        """
        pass

    def report(self, profile, agent_metadata=None, timestamp=None):
        if timestamp is None:
            timestamp = datetime.datetime.now()
        output_filename = self._output_filename_for(timestamp)

        logger.info("Writing profile to '{}'".format(output_filename))

        with open(output_filename, 'wb') as output_file_stream:
            self._profile_encoder.encode(
                profile=profile, output_stream=output_file_stream)

        return output_filename

    def _output_filename_for(self, timestamp):
        return self._file_prefix \
            + timestamp.strftime("%Y-%m-%dT%H-%M-%S") \
            + self._FILE_SUFFIX
