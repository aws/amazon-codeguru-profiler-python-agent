import logging

from datetime import timedelta

# The keys for the Agent Configuration's parameters from the API configuration.
# https://docs.aws.amazon.com/codeguru/latest/profiler-api/API_AgentConfiguration.html
# ReportingIntervalInMilliseconds is intentionally left out as it doesn't make sense.

MEMORY_USAGE_LIMIT_PERCENT_KEY = "MemoryUsageLimitPercent"
MINIMUM_TIME_FOR_REPORTING_MILLISECONDS_KEY = "MinimumTimeForReportingInMilliseconds"
SAMPLING_INTERVAL_MILLISECONDS_KEY = "SamplingIntervalInMilliseconds"
MAX_STACK_DEPTH_KEY = "MaxStackDepth"
PERIOD_IN_SECONDS_KEY = "periodInSeconds"
SHOULD_PROFILE_KEY = "shouldProfile"

_singleton = None

logger = logging.getLogger(__name__)


class AgentConfiguration:
    """
    Singleton class that holds the configuration for the agent that can be updated based on a json configuration.
    """

    def __init__(self, should_profile=None, sampling_interval=None, reporting_interval=None,
                 minimum_time_reporting=None, max_stack_depth=None, cpu_limit_percentage=None):
        self.should_profile = should_profile
        self.sampling_interval = sampling_interval
        self.reporting_interval = reporting_interval
        self.minimum_time_reporting = minimum_time_reporting
        self.max_stack_depth = max_stack_depth
        self.cpu_limit_percentage = cpu_limit_percentage
        if self._is_reporting_interval_smaller_than_minimum_allowed():
            raise ValueError(
                "Configuration issue: reporting_interval cannot be smaller than {} (got {})".format(
                    minimum_time_reporting, str(self.reporting_interval)))

    def as_dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}

    @classmethod
    def get(cls):
        """
        Returns the singleton instance of the AgentConfiguration().
        :return: the one instance of the agent configuration
        """
        if _singleton is None:
            raise ValueError("Instance for singleton is None, use AgentConfigurationMerger for initialization.")
        return _singleton

    @classmethod
    def set(cls, current):
        """
       Sets the singleton instance of the AgentConfiguration() with the one set as parameter.
       """
        if current is None:
            raise ValueError("You can not set a None instance for the singleton instance.")
        global _singleton
        _singleton = current
        logger.info("New agent configuration: " + str(_singleton.as_dict()))

    @classmethod
    def _get_new_config(cls, configure_agent_response=dict()):
        agent_parameters_response = configure_agent_response.get("agentParameters", {})

        current = AgentConfiguration.get()
        return AgentConfiguration(
            should_profile=configure_agent_response.get(SHOULD_PROFILE_KEY, current.should_profile),
            reporting_interval=cls._get_interval_from_seconds(key=PERIOD_IN_SECONDS_KEY,
                                                              response=configure_agent_response,
                                                              default_value=current.reporting_interval),
            sampling_interval=cls._get_interval_from_milliseconds(key=SAMPLING_INTERVAL_MILLISECONDS_KEY,
                                                                  response=agent_parameters_response,
                                                                  default_value=current.sampling_interval),
            minimum_time_reporting=cls._get_interval_from_milliseconds(key=MINIMUM_TIME_FOR_REPORTING_MILLISECONDS_KEY,
                                                                       response=agent_parameters_response,
                                                                       default_value=current.minimum_time_reporting),
            max_stack_depth=cls._get_int_value_from(key=MAX_STACK_DEPTH_KEY,
                                                    response=agent_parameters_response,
                                                    default_value=current.max_stack_depth),
            cpu_limit_percentage=cls._get_int_value_from(key=MEMORY_USAGE_LIMIT_PERCENT_KEY,
                                                         response=agent_parameters_response,
                                                         default_value=current.cpu_limit_percentage)
        )

    @classmethod
    def _get_interval_from_milliseconds(cls, key, response, default_value):
        return cls._get_interval_from(key, response, default_value, in_milliseconds=True)

    @classmethod
    def _get_interval_from_seconds(cls, key, response, default_value):
        return cls._get_interval_from(key, response, default_value, in_seconds=True)

    @classmethod
    def _get_interval_from(cls, key, response, default_value, in_seconds=False, in_milliseconds=False):
        if not in_seconds ^ in_milliseconds:
            raise ValueError("Only one of the parameters 'in_seconds' and 'in_milliseconds' must be true.")
        int_value = cls._get_int_value_from(key, response)
        if int_value is None:
            logger.debug("Setting back to previous value: " + str(default_value))
            return default_value
        if in_seconds:
            return timedelta(seconds=int_value)
        else:
            return timedelta(milliseconds=int_value)

    @classmethod
    def _get_int_value_from(cls, key, response, default_value=None):
        if key not in response:
            logger.debug("The response '{}' does not contain key '{}'.".format(response, key))
            return default_value

        value = response.get(key)
        try:
            return int(value)
        except Exception:
            logger.info("The response contains invalid integer value '{}' for key '{}'.".format(value, key),
                           exc_info=False)
            return default_value

    def is_under_min_reporting_time(self, time_delay_since_last_report):
        return time_delay_since_last_report < self.minimum_time_reporting.total_seconds() * 1000

    def is_over_reporting_interval(self, time_delay_since_last_report):
        return time_delay_since_last_report > self.reporting_interval.total_seconds() * 1000

    def _is_reporting_interval_smaller_than_minimum_allowed(self):
        if self.reporting_interval is None or self.minimum_time_reporting is None:
            return False
        return self.reporting_interval < self.minimum_time_reporting


class AgentConfigurationMerger:

    def __init__(self, default=AgentConfiguration(), user_overrides=AgentConfiguration()):
        self.default = default.as_dict()
        self.user_overrides = user_overrides.as_dict()
        self._merge_and_set()

    def merge_with(self, configure_agent_response):
        """
        This refreshes only the configuration that was NOT overridden by the customer and sets the singleton instance.
        :param configure_agent_response: the dict from the backend response
        """
        orchestration_config = AgentConfiguration._get_new_config(configure_agent_response)
        self._merge_and_set(orchestration_overrides=orchestration_config.as_dict())

    def _merge_and_set(self, orchestration_overrides=dict()):
        merged = self.default
        merged.update(orchestration_overrides)
        merged.update(self.user_overrides)
        AgentConfiguration.set(AgentConfiguration(**merged))

    def disable_profiling(self):
        """
        Only sets should_profile to False, other values in the configuration are unchanged.
        This is used for error handling when we call orchestrator.
        """
        self._merge_and_set(orchestration_overrides=AgentConfiguration(should_profile=False).as_dict())
