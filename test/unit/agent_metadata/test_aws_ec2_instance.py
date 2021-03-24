import pytest
import httpretty
import sys
from codeguru_profiler_agent.agent_metadata.aws_ec2_instance import EC2_HOST_NAME_URI, \
    EC2_HOST_INSTANCE_TYPE_URI, EC2_API_TOKEN_URI
from codeguru_profiler_agent.agent_metadata.aws_ec2_instance import AWSEC2Instance


@pytest.mark.skipif(sys.version_info >= (3, 9),
                    reason="These tests require use of httpPretty that doesn't support yet Python 3.9.")
class TestAWSEC2Instance:
    class TestLookUpMetadata:
        class TestWhenCalledOutsideEc2:
            @pytest.fixture(autouse=True)
            def around(self):
                httpretty.enable()
                httpretty.HTTPretty.allow_net_connect = False
                yield
                httpretty.disable()
                httpretty.reset()

            def test_it_returns_none(self):
                """
                With httpretty, we have disabled all network connection; hence the call to get the ec2 metadata should
                always fail.
                """
                subject = AWSEC2Instance.look_up_metadata()

                assert subject is None

        class TestWhenHostNameAndHostTypeCanBeDetermined:
            @pytest.fixture(autouse=True)
            def around(self):
                httpretty.enable()
                httpretty.HTTPretty.allow_net_connect = False
                httpretty.register_uri(
                    httpretty.GET,
                    EC2_HOST_NAME_URI,
                    body="testHostName")
                httpretty.register_uri(
                    httpretty.GET,
                    EC2_HOST_INSTANCE_TYPE_URI,
                    body="testHostType")
                httpretty.register_uri(
                    httpretty.GET,
                    EC2_API_TOKEN_URI,
                    body="PARIOq_FXbIyL0maE9RcmrsyWtylvFh1ZDt0NrRUyNxeV1-DlpFpA==")
                yield
                httpretty.disable()
                httpretty.reset()

            def test_it_returns_host_name_and_host_type(self):
                subject = AWSEC2Instance.look_up_metadata()

                assert subject.host_name == "testHostName"
                assert subject.host_type == "testHostType"
                assert subject.get_fleet_instance_id() == "testHostName"

        class TestWhenHostNameCannotBeDetermined:
            @pytest.fixture(autouse=True)
            def around(self):
                httpretty.enable()
                httpretty.HTTPretty.allow_net_connect = False
                httpretty.register_uri(
                    httpretty.GET,
                    EC2_HOST_INSTANCE_TYPE_URI,
                    body="testHostType")
                yield
                httpretty.disable()
                httpretty.reset()

            def test_it_returns_none(self):
                subject = AWSEC2Instance.look_up_metadata()

                assert subject is None

        class TestWhenHostTypeCannotBeDetermined:
            @pytest.fixture(autouse=True)
            def around(self):
                httpretty.enable()
                httpretty.HTTPretty.allow_net_connect = False
                httpretty.register_uri(
                    httpretty.GET,
                    EC2_HOST_NAME_URI,
                    body="testHostName")
                yield
                httpretty.disable()
                httpretty.reset()

            def test_it_returns_none(self):
                subject = AWSEC2Instance.look_up_metadata()

                assert subject is None

    class TestSerializeToMap:
        def test_it_returns_a_map(self):
            subject = AWSEC2Instance(host_name="testHostName", host_type="testHostType")

            assert subject.serialize_to_map() == {
                "computeType": "aws_ec2_instance",
                "hostName": "testHostName",
                "hostType": "testHostType"
            }

    class TestGetMetadataForConfigureAgentCall:
        def test_it_returns_the_compute_platform(self):
            subject = AWSEC2Instance(host_name="testHostName", host_type="testHostType")

            assert subject.get_metadata_for_configure_agent_call() == None
