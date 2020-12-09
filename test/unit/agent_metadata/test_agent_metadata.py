import pytest
from codeguru_profiler_agent.agent_metadata.agent_metadata import look_up_fleet_info, AgentInfo, AgentMetadata
from codeguru_profiler_agent.agent_metadata.aws_ec2_instance import AWSEC2Instance
from codeguru_profiler_agent.agent_metadata.fleet_info import DefaultFleetInfo, http_get


class TestAgentMetadata:
    class TestLookUpFleetInfo:
        class TestWhenMetadataIsNotAvailable:
            def test_it_returns_default_fleet_info(self):
                subject = look_up_fleet_info(platform_metadata_fetchers=(lambda: None,))

                assert isinstance(subject, DefaultFleetInfo)
                fleet_instance_id = subject.get_fleet_instance_id()
                assert fleet_instance_id is not None
                fleet_instance_serialized = subject.serialize_to_map()
                assert fleet_instance_serialized["id"] == fleet_instance_id
                assert fleet_instance_serialized["type"] == "UNKNOWN"
                assert fleet_instance_serialized["vCPUs"] is not None
                assert subject.get_metadata_for_configure_agent_call() == None

        class TestWhenMetadataIsAvailable:
            def test_it_returns_fleet_info(self):
                test_fleet_info = AWSEC2Instance(host_name="testHost", host_type="testType")
                subject = look_up_fleet_info(
                    platform_metadata_fetchers=(lambda: None, lambda: test_fleet_info)
                )

                assert subject == test_fleet_info

    class TestAgentMetadataInit:
        class TestWhenFleetInfoIsNotAvailable:
            def test_it_returns_default_agent_metadata(self):
                subject = AgentMetadata()

                assert subject.agent_info == AgentInfo.default_agent_info()
                assert subject.fleet_info is not None
                assert subject.runtime_version[0] == "3"

    class TestAgentInfo:
        class TestEqual:
            def test_it_does_equality_correctly(self):
                subject = AgentInfo(agent_type="testAgentType", version="2345")
                same = AgentInfo(agent_type="testAgentType", version="2345")

                assert subject == same
                assert subject.agent_type == same.agent_type
                assert subject.version == same.version

                different = AgentInfo(agent_type="testDifferentAgentType", version="9876")

                assert subject != different
                assert subject.agent_type != different.agent_type
                assert subject.version != different.version

                assert subject != "abc"


class TestHttpGet:
    class TestWhenUrlIsNotHttp:
        def test_it_throws_value_error(self):
            with pytest.raises(ValueError):
                http_get(url='file://sensitive_file.txt')
