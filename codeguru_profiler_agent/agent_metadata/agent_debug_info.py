import logging
import os

from codeguru_profiler_agent.utils.synchronization import synchronized
from codeguru_profiler_agent.utils.time import to_iso

logger = logging.getLogger(__name__)


class ErrorsMetadata:
    def __init__(self):
        self.reset()

    def reset(self):
        """
        We want to differentiate API call errors more granularly. We want to gather ResourceNotFoundException errors
        because we are going to get this exception with auto-create  feature and want to monitor how many times
        the agent is not able to create the PG and resulting in subsequent ResourceNotFoundException.
        """
        self.errors_count = 0
        self.sdk_client_errors = 0
        self.configure_agent_errors = 0
        self.configure_agent_rnfe_auto_create_enabled_errors = 0
        self.create_profiling_group_errors = 0
        self.post_agent_profile_errors = 0
        self.post_agent_profile_rnfe_auto_create_enabled_errors = 0

    def serialize_to_json(self):
        """
        This needs to be compliant with errors count schema.
        """
        return {
            "errorsCount": self.errors_count,
            "sdkClientErrors": self.sdk_client_errors,
            "configureAgentErrors": self.configure_agent_errors,
            "configureAgentRnfeAutoCreateEnabledErrors": self.configure_agent_rnfe_auto_create_enabled_errors,
            "createProfilingGroupErrors": self.create_profiling_group_errors,
            "postAgentProfileErrors": self.post_agent_profile_errors,
            "postAgentProfileRnfeAutoCreateEnabledErrors": self.post_agent_profile_rnfe_auto_create_enabled_errors
        }

    @synchronized
    def increment_sdk_error(self, error_type):
        """
        ErrorsCount is the umbrella of all the kinds of error we want to capture. Currently we have only SdkClientErrors
        in it. SdkClientErrors is comprised of different API level errors like ConfigureAgentErrors,
        PostAgentProfileErrors, CreateProfilingGroupErrors.
        :param error_type: The type of API level error that we want to capture.
        """
        self.errors_count += 1
        self.sdk_client_errors += 1

        """
        Special handling for ResourceNotFoundException errors.
        For example configureAgentRnfeAutoCreateEnabledErrors is also a configureAgentErrors.
        """
        if error_type == "configureAgentErrors":
            self.configure_agent_errors += 1
        elif error_type == "configureAgentRnfeAutoCreateEnabledErrors":
            self.configure_agent_errors += 1
            self.configure_agent_rnfe_auto_create_enabled_errors += 1
        elif error_type == "createProfilingGroupErrors":
            self.create_profiling_group_errors += 1
        elif error_type == "postAgentProfileErrors":
            self.post_agent_profile_errors += 1
        elif error_type == "postAgentProfileRnfeAutoCreateEnabledErrors":
            self.post_agent_profile_errors += 1
            self.post_agent_profile_rnfe_auto_create_enabled_errors += 1

    def record_sdk_error(self, error_type):
        self.increment_sdk_error(error_type)


class AgentDebugInfo:
    def __init__(self, errors_metadata=None, agent_start_time=None, timer=None):
        self.process_id = get_process_id()
        self.errors_metadata = errors_metadata
        self.agent_start_time = agent_start_time
        self.timer = timer

    def serialize_to_json(self):
        """
        This needs to be compliant with agent debug info schema.
        """
        json = {}

        self.add_agent_start_time(json)
        self.add_process_id(json)
        self.add_errors_metadata(json)
        self.add_generic_metrics(json)

        return json

    def add_agent_start_time(self, json):
        if self.agent_start_time is not None:
            json["agentStartTime"] = to_iso(self.agent_start_time)

    def add_errors_metadata(self, json):
        if self.errors_metadata is not None:
            json["errorsCount"] = self.errors_metadata.serialize_to_json()

    def add_process_id(self, json):
        if self.process_id is not None:
            json["processId"] = self.process_id

    def add_generic_metrics(self, json):
        if self.timer is not None and self.timer.metrics:
            generic_metrics = {}

            for metric, metric_value in self.timer.metrics.items():
                generic_metrics[metric + "_timings_max"] = metric_value.max
                generic_metrics[metric + "_timings_average"] = metric_value.average()

            if generic_metrics:
                json["genericMetrics"] = generic_metrics


def get_process_id():
    try:
        return os.getpid()
    except Exception as e:
        logger.info("Failed to get the process id", exc_info=True)
        return None

