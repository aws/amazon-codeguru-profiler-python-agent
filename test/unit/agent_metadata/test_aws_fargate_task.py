import httpretty
import pytest
import sys
from codeguru_profiler_agent.agent_metadata.aws_fargate_task import AWSFargateTask

DUMMY_URI_FOR_TEST = "http://dummy-ecs/meta-data"


@pytest.mark.skipif(sys.version_info >= (3, 9),
                    reason="These tests require use of httpPretty that doesn't support yet Python 3.9.")
class TestAWSFargateTask:
    class TestLookUpMetadata:
        """
        See https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-metadata-endpoint-v3.html for details of
        the format returned by the ecs container metadata endpoint.
        """

        class TestWhenCalledOutsideFargate:
            @pytest.fixture(autouse=True)
            def around(self):
                httpretty.enable()
                httpretty.HTTPretty.allow_net_connect = False
                yield
                httpretty.disable()
                httpretty.reset()

            def test_it_returns_none_when_url_is_not_set(self):
                subject = AWSFargateTask.look_up_metadata()
                assert subject is None

            def test_it_returns_none_when_url_is_none(self):
                subject = AWSFargateTask.look_up_metadata(url=None)
                assert subject is None

            def test_it_returns_none_when_call_fails(self):
                """
                With httpretty, we have disabled all network connection; hence the call to get the fargate metadata
                should always fail.
                """
                subject = AWSFargateTask.look_up_metadata(url=DUMMY_URI_FOR_TEST)

                assert subject is None

        class TestWhenTaskArnAndLimitsCanBeDetermined:
            @pytest.fixture(autouse=True)
            def around(self):
                httpretty.enable()
                httpretty.HTTPretty.allow_net_connect = False
                httpretty.register_uri(
                    httpretty.GET,
                    DUMMY_URI_FOR_TEST + "/task",
                    body='{"TaskARN": "testTaskARN", "Limits": {"CPU": 123, "Memory": 789}}')
                yield
                httpretty.disable()
                httpretty.reset()

            def test_it_returns_host_name_and_host_type(self):
                subject = AWSFargateTask.look_up_metadata(url=DUMMY_URI_FOR_TEST)

                assert subject.task_arn == "testTaskARN"
                assert subject.cpu_limit == 123
                assert subject.memory_limit_in_mb == 789
                assert subject.get_fleet_instance_id() == "testTaskARN"

        class TestWhenTaskArnCannotBeDetermined:
            @pytest.fixture(autouse=True)
            def around(self):
                httpretty.enable()
                httpretty.HTTPretty.allow_net_connect = False
                httpretty.register_uri(
                    httpretty.GET,
                    DUMMY_URI_FOR_TEST + "/task",
                    body='{"Limits": {"CPU": 123, "Memory": 789}}')
                yield
                httpretty.disable()
                httpretty.reset()

            def test_it_returns_none(self):
                subject = AWSFargateTask.look_up_metadata(url=DUMMY_URI_FOR_TEST)

                assert subject is None

        class TestWhenLimitsCannotBeDetermined:
            class TestWhenCPULimitIsMissing:
                @pytest.fixture(autouse=True)
                def around(self):
                    httpretty.enable()
                    httpretty.HTTPretty.allow_net_connect = False
                    httpretty.register_uri(
                        httpretty.GET,
                        DUMMY_URI_FOR_TEST + "/task",
                        body='{"TaskARN": "testTaskARN", "Limits": {"Memory": 789}}')
                    yield
                    httpretty.disable()
                    httpretty.reset()

                def test_it_returns_none_for_cpu_limit(self):
                    subject = AWSFargateTask.look_up_metadata(url=DUMMY_URI_FOR_TEST)

                    assert subject.cpu_limit is None

            class TestWhenMemoryLimitIsMissing:
                @pytest.fixture(autouse=True)
                def around(self):
                    httpretty.enable()
                    httpretty.HTTPretty.allow_net_connect = False
                    httpretty.register_uri(
                        httpretty.GET,
                        DUMMY_URI_FOR_TEST + "/task",
                        body='{"TaskARN": "testTaskARN", "Limits": {"CPU": 123}}')
                    yield
                    httpretty.disable()
                    httpretty.reset()

                def test_it_returns_none(self):
                    subject = AWSFargateTask.look_up_metadata(url=DUMMY_URI_FOR_TEST)

                    assert subject.memory_limit_in_mb is None

    class TestSerializeToMap:
        def test_it_returns_a_map(self):
            subject = AWSFargateTask(task_arn="testTaskArn", cpu_limit=100, memory_limit_in_mb=200)

            assert subject.serialize_to_map() == {
                "computeType": "aws_fargate_task",
                "taskArn": "testTaskArn",
                "cpuLimit": 100,
                "memoryLimitInMB": 200
            }

    class TestGetMetadataForConfigureAgentCall:
        def test_it_returns_the_compute_platform(self):
            subject = AWSFargateTask(task_arn="testTaskArn", cpu_limit=100, memory_limit_in_mb=200)

            assert subject.get_metadata_for_configure_agent_call() == None
