import threading
import time
from queue import Queue
import boto3
from botocore.client import Config

INTEGRATION_TEST_ACCOUNT_ID = "519630429520"
MY_PROFILING_GROUP_NAME_FOR_INTEG_TESTS = "MyProfilingGroupForIntegrationTests"
DUMMY_TEST_PROFILING_GROUP_NAME = "DummyNameThatWillNotBeUsed"

FILE_PREFIX = "pytest-CodeGuruPythonAgent"


class HelperThreadRunner:
    def __init__(self):
        pass

    def new_helper_sleep_thread(self, sleep_sec=1, thread_name="test-sleep-thread"):
        self.sleep_thread = threading.Thread(
            name=thread_name, target=self.sleep_for, daemon=True, kwargs={"sleep_sec": sleep_sec})
        self.sleep_thread.start()

    def sleep_for(self, sleep_sec):
        time.sleep(sleep_sec)

    def new_helper_thread_blocked_inside_dummy_method(
            self, thread_name="test-thread"):
        self.ready_queue = Queue()
        self.done_queue = Queue()

        self.thread = threading.Thread(
            name=thread_name, target=self.dummy_parent_method)
        self.thread.start()
        self.ready_queue.get()

    def stop_helper_thread(self):
        self.done_queue.put(True)
        self.thread.join()

    def dummy_method(self):
        """
        Running this function in a thread provides us a test stack to compare against.
        """
        self.ready_queue.put(True)
        self.done_queue.get()

    def dummy_parent_method(self):
        """
        By creating a function calling the long_running_test_process, we create an ordered stack for testing.
        """
        self.dummy_method()

    def make_boto_api_call(self, boto_client):
        try:
            boto_client.put_metric_data(Namespace="any_namespace", MetricData=[])
        except Exception as e:
            print("This should be a ConnectTimeoutError", e)

    def new_thread_sending_boto_api_call(self, timeout_seconds=1, thread_name="test-boto-api-call"):
        no_retry_config = Config(connect_timeout=timeout_seconds, retries={'max_attempts': 0})
        # we do not want boto to look for real credentials so provide fake ones
        session = boto3.Session(region_name="us-east-1", aws_access_key_id="fake_id", aws_secret_access_key="fake_key")
        # we set a fake endpoint in the client because we do not want to make a real call
        # this is only so we can have a thread inside an api call trying to make a connection
        # long enough for us to take a sample
        no_target_client = session.client('cloudwatch', endpoint_url='https://notExisting.com/', config=no_retry_config)
        self.boto_thread = threading.Thread(
            name=thread_name, target=self.make_boto_api_call, daemon=True, kwargs={"boto_client": no_target_client})
        self.boto_thread.start()

def wait_for(condition, timeout_seconds=1.0, poll_interval_seconds=0.01):
    """
    Timed out waiting for condition to be true
    """
    end_time = time.time() + timeout_seconds
    while time.time() < end_time:
        if condition():
            return True
        time.sleep(poll_interval_seconds)
    raise Exception("wait_for: Timed out waiting for condition to be true")
