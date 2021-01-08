from test.pytestutils import before

from datetime import timedelta

from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration, AgentConfigurationMerger


class TestAgentConfigurationMerger:

    @before
    def before(self):
        self.config = AgentConfiguration(
            should_profile=True,
            sampling_interval=timedelta(milliseconds=1),
            minimum_time_reporting=timedelta(seconds=1),
            reporting_interval=timedelta(minutes=1),
            max_stack_depth=998)
        self.overide_config = AgentConfiguration(sampling_interval=timedelta(seconds=9))
        self.configure_agent_response = {
            "agentParameters": {
                "SamplingIntervalInMilliseconds": "2000",
                "MinimumTimeForReportingInMilliseconds": "21000",
                "MaxStackDepth": "1001"
            },
            "periodInSeconds": 123,
            "shouldProfile": False
        }

    def test_default_values_are_overridden_at_merge_with(self):
        agent_config_merger = AgentConfigurationMerger(default=self.config)
        self.assert_init_values()

        agent_config_merger.merge_with(configure_agent_response=self.configure_agent_response)
        assert AgentConfiguration.get().should_profile is False
        assert AgentConfiguration.get().sampling_interval == timedelta(milliseconds=2000)
        assert AgentConfiguration.get().minimum_time_reporting == timedelta(milliseconds=21000)
        assert AgentConfiguration.get().reporting_interval == timedelta(seconds=123)
        assert AgentConfiguration.get().max_stack_depth == 1001

    def test_user_overrides_are_not_overridden_at_merge_with(self):
        agent_config_merger = AgentConfigurationMerger(default=AgentConfiguration(), user_overrides=self.config)
        self.assert_init_values()

        agent_config_merger.merge_with(configure_agent_response=self.configure_agent_response)
        self.assert_init_values()

    def test_a_user_override_is_not_overridden_at_merge(self):
        agent_config_merger = AgentConfigurationMerger(default=self.config,
                                                       user_overrides=self.overide_config)
        assert AgentConfiguration.get().should_profile is True
        assert AgentConfiguration.get().sampling_interval == timedelta(seconds=9)
        assert AgentConfiguration.get().minimum_time_reporting == timedelta(seconds=1)
        assert AgentConfiguration.get().reporting_interval == timedelta(minutes=1)
        assert AgentConfiguration.get().max_stack_depth == 998

        agent_config_merger.merge_with(configure_agent_response=self.configure_agent_response)
        assert AgentConfiguration.get().should_profile is False
        assert AgentConfiguration.get().sampling_interval == timedelta(seconds=9)
        assert AgentConfiguration.get().minimum_time_reporting == timedelta(milliseconds=21000)
        assert AgentConfiguration.get().reporting_interval == timedelta(seconds=123)
        assert AgentConfiguration.get().max_stack_depth == 1001

    def assert_init_values(self):
        assert AgentConfiguration.get().should_profile is True
        assert AgentConfiguration.get().sampling_interval == timedelta(milliseconds=1)
        assert AgentConfiguration.get().minimum_time_reporting == timedelta(seconds=1)
        assert AgentConfiguration.get().reporting_interval == timedelta(minutes=1)
        assert AgentConfiguration.get().max_stack_depth == 998

    class TestDisableProfiling:
        @before
        def before(self):
            self.config = AgentConfiguration(
                should_profile=True,
                sampling_interval=timedelta(milliseconds=1),
                minimum_time_reporting=timedelta(seconds=1),
                reporting_interval=timedelta(minutes=1),
                max_stack_depth=998)
            self.agent_config_merger = AgentConfigurationMerger(default=self.config)

        def test_it_sets_should_profile_to_false(self):
            self.agent_config_merger.disable_profiling()
            assert AgentConfiguration.get().should_profile is False

        def test_it_leaves_other_values_untouched(self):
            self.agent_config_merger.disable_profiling()
            assert AgentConfiguration.get().sampling_interval == timedelta(milliseconds=1)
            assert AgentConfiguration.get().minimum_time_reporting == timedelta(seconds=1)
            assert AgentConfiguration.get().reporting_interval == timedelta(minutes=1)
            assert AgentConfiguration.get().max_stack_depth == 998
