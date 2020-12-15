import subprocess
import threading
import time
from queue import Queue

INTEGRATION_TEST_ACCOUNT_ID = "519630429520"
TEST_PROFILING_GROUP_NAME = "integrationTest"
DUMMY_TEST_PROFILING_GROUP_NAME = "DummyNameThatWillNotBeUsed"


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


def _get_credentials():
    command = ['ada', 'credentials', 'update', '--account=' + INTEGRATION_TEST_ACCOUNT_ID, '--provider=isengard',
               '--role=SkySailFullAccessForLocalTests', '--once']
    subprocess.check_call(command)
