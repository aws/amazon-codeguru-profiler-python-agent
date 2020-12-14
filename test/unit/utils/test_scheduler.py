from queue import Queue
import pytest
from test.pytestutils import before
from codeguru_profiler_agent.utils.scheduler import Scheduler

# this is to make sure the unit test does not run forever if there is a bug in the scheduler
TEST_TIMEOUT_SECONDS = 5


class TestScheduler:
    class TestStart:
        @pytest.fixture(autouse=True)
        def around(self):
            self.ready_queue = Queue()
            self.done_queue = Queue()
            self.scheduler = Scheduler(
                self.running_test_process, thread_name="test_thread")
            self.scheduler.start()
            self.ready_queue.get(TEST_TIMEOUT_SECONDS)
            yield
            self.done_queue.put(True)
            self.scheduler.stop()

        def running_test_process(self):
            self.ready_queue.put(True)
            self.done_queue.get(TEST_TIMEOUT_SECONDS)

        def test_function_run_on_new_thread(self):
            assert (self.scheduler.is_running())
            assert (self.scheduler._thread.name == "test_thread")

    class TestStop:
        @before
        def before(self):
            self.scheduler = Scheduler(lambda: True, thread_name="test_thread")
            self.scheduler.start()
            # Make sure thread is alive
            assert (self.scheduler.is_running())

        def test_thread_terminates_when_called_stop(self):
            self.scheduler.stop()
            assert (not self.scheduler.is_running())

    class TestErrorHandling:
        def test_exception_not_propagated_from_scheduled_thread(self):
            self.exception_thrown = False

            def throw_exception():
                self.exception_thrown = True
                raise Exception("testing")

            scheduler = \
                Scheduler(command=throw_exception, thread_name="test_thread")
            scheduler.start()
            scheduler._thread.join()

            assert self.exception_thrown

        def test_exception_not_thrown_when_stop_is_called_before_starting(self):
            scheduler = Scheduler(lambda: True, thread_name="test_thread")

            scheduler.stop()

    class TestPauseAndResume:
        @pytest.fixture(autouse=True)
        def around(self):
            self.ready_queue = Queue()
            self.done_queue = Queue()

            def running_test_process():
                self.ready_queue.put(True)
                return self.done_queue.get(TEST_TIMEOUT_SECONDS)

            self.scheduler = \
                Scheduler(running_test_process, thread_name="test_thread")
            self.scheduler.start()
            self.ready_queue.get(TEST_TIMEOUT_SECONDS)
            # finish first execution by pushing into done_queue
            # the scheduler should go into wait
            self.done_queue.put(True)

            # then pause
            self.scheduler.pause(block=True)
            yield
            self.scheduler.stop()

        def test_pause_when_scheduler_is_paused(self):
            assert (self.scheduler.is_running())
            assert (self.scheduler.is_paused())

        def test_resume_when_scheduler_is_running(self):
            self.scheduler.resume(block=True)
            assert (self.scheduler.is_running())
            assert (not self.scheduler.is_paused())
