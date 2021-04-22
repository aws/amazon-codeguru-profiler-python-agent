from codeguru_profiler_agent.utils.synchronization import synchronized


class ErrorsMetadata:
    def __init__(self):
        self.errors_count = 0
        self.sdk_client_errors = 0
        self.configure_agent_errors = 0
        self.configure_agent_rnfe_auto_create_enabled_errors = 0
        self.create_profiling_group_errors = 0
        self.post_agent_profile_errors = 0
        self.post_agent_profile_rnfe_auto_create_enabled_errors = 0

    def reset(self):
        self.errors_count = 0
        self.sdk_client_errors = 0
        self.configure_agent_errors = 0
        self.configure_agent_rnfe_auto_create_enabled_errors = 0
        self.create_profiling_group_errors = 0
        self.post_agent_profile_errors = 0
        self.post_agent_profile_rnfe_auto_create_enabled_errors = 0

    """
    This needs to be compliant with errors count schema.
    https://code.amazon.com/packages/SkySailProfileIonSchema/blobs/811cc0e7e406e37a5b878acf31468be3dcd2963d/--/src/main/resources/schema/DebugInfo.isl#L21
    """

    def serialize_to_json(self):
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
        self.errors_count += 1
        self.sdk_client_errors += 1

        if error_type == "configureAgentErrors":
            self.configure_agent_errors += 1
        elif error_type == "configureAgentRnfeAutoCreateEnabledErrors":
            self.configure_agent_rnfe_auto_create_enabled_errors += 1
        elif error_type == "createProfilingGroupErrors":
            self.create_profiling_group_errors += 1
        elif error_type == "postAgentProfileErrors":
            self.post_agent_profile_errors += 1
        elif error_type == "postAgentProfileRnfeAutoCreateEnabledErrors":
            self.post_agent_profile_rnfe_auto_create_enabled_errors += 1

    def record_sdk_error(self, error_type):
        self.increment_sdk_error(error_type)


class AgentDebugInfo:
    def __init__(self, errors_metadata):
        self.errors_metadata = errors_metadata

    def serialize_to_json(self):
        """
        This needs to be compliant with agent debug info schema.
        https://code.amazon.com/packages/SkySailProfileIonSchema/blobs/811cc0e7e406e37a5b878acf31468be3dcd2963d/--/src/main/resources/schema/DebugInfo.isl#L21
        """
        return {
            "errorsCount": self.errors_metadata.serialize_to_json()
        }
