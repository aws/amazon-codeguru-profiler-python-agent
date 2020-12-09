import pytest
from datetime import timedelta
from test.pytestutils import before
import codeguru_profiler_agent.reporter.agent_configuration
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration


class TestAgentConfiguration:

    @before
    def before(self):
        self.agent_config = AgentConfiguration(
            should_profile=True,
            sampling_interval=timedelta(milliseconds=9100),
            minimum_time_reporting=timedelta(seconds=7),
            reporting_interval=timedelta(minutes=7),
            max_stack_depth=999,
            cpu_limit_percentage=9
        )
        AgentConfiguration.set(self.agent_config)

    class TestInit:
        def test_it_sets_values_from_constructor(self):
            assert self.agent_config.should_profile is True
            assert self.agent_config.sampling_interval == timedelta(milliseconds=9100)
            assert self.agent_config.reporting_interval == timedelta(minutes=7)
            assert self.agent_config.minimum_time_reporting == timedelta(seconds=7)
            assert self.agent_config.max_stack_depth == 999
            assert self.agent_config.cpu_limit_percentage == 9

        class TestWhenCustomReportingIntervalIsLessThan30Seconds:
            def test_it_raises_a_value_error(self):
                with pytest.raises(ValueError):
                    AgentConfiguration(reporting_interval=timedelta(seconds=28),
                                       minimum_time_reporting=timedelta(seconds=29))

    class TestGet:

        def test_it_throws_error_at_calling_get_when_singleton_is_none(self):
            setattr(codeguru_profiler_agent.reporter.agent_configuration, "_singleton", None)
            with pytest.raises(ValueError):
                AgentConfiguration.get()

    class TestSet:
        def test_set_throws_error_when_setting_a_none_instance(self):
            with pytest.raises(ValueError):
                AgentConfiguration.set(None)

    class TestGetNewConfig:
        def test_it_sets_the_values_after_updating_using_new_configuration(self):
            new_config = self.agent_config._get_new_config(configure_agent_response={
                "agentParameters": {
                    "SamplingIntervalInMilliseconds": "2100",
                    "MinimumTimeForReportingInMilliseconds": "60000",
                    "MaxStackDepth": "1001",
                    "MemoryUsageLimitPercent": "10"
                },
                "periodInSeconds": 123,
                "shouldProfile": False
            })
            assert new_config.should_profile is False
            assert new_config.sampling_interval == timedelta(seconds=2.1)
            assert new_config.minimum_time_reporting == timedelta(milliseconds=60000)
            assert new_config.reporting_interval == timedelta(seconds=123)
            assert new_config.max_stack_depth == 1001
            assert new_config.cpu_limit_percentage == 10

    class TestGetValuesFromResponse:
        @before
        def before(self):
            self.response = {"one": 1, "two": "2", "three": "not a number"}
            self.default_value = timedelta(seconds=999)

        def test_get_int_value_from(self):
            assert AgentConfiguration._get_int_value_from("one", self.response) is 1
            assert AgentConfiguration._get_int_value_from("two", self.response) is 2
            assert AgentConfiguration._get_int_value_from("three", self.response) is None
            assert AgentConfiguration._get_int_value_from("three", self.response, 0) is 0
            assert AgentConfiguration._get_int_value_from("four", self.response) is None
            assert AgentConfiguration._get_int_value_from("four", self.response, 999) is 999

        def test_get_interval_from(self):
            assert AgentConfiguration._get_interval_from("one", self.response, self.default_value,
                                                         in_seconds=True) == timedelta(seconds=1)
            assert AgentConfiguration._get_interval_from("one", self.response, self.default_value,
                                                         in_milliseconds=True) == timedelta(milliseconds=1)
            assert AgentConfiguration._get_interval_from("three", self.response, self.default_value,
                                                         in_milliseconds=True) == self.default_value

        def test_get_interval_from_raises_error_if_both_true(self):
            with pytest.raises(ValueError):
                AgentConfiguration._get_interval_from("one", self.response, self.default_value,
                                                      in_seconds=True, in_milliseconds=True)

        def test_get_interval_from_raises_error_if_both_false(self):
            with pytest.raises(ValueError):
                AgentConfiguration._get_interval_from("one", self.response, self.default_value,
                                                      in_seconds=False, in_milliseconds=False)

        def test_get_interval_from_raises_error_if_both_are_the_defaults(self):
            with pytest.raises(ValueError):
                AgentConfiguration._get_interval_from("one", self.response, self.default_value)
