import threading
import time
import datetime
from test.pytestutils import before
from queue import Queue, Empty
from mock import MagicMock, call

from codeguru_profiler_agent.utils.execution_state import ExecutionState

# this is to make sure the unit test does not run forever if there is a bug in the scheduler
TEST_TIMEOUT_SECONDS = 5


class ExecutorForTest:
    def __init__(self, execution_state):
        self.execution_state = execution_state
        self.thread = \
            threading.Thread(target=self.execute, name="from_test_execution_state")
        self.execution_counter = 0
        self.timeout = TEST_TIMEOUT_SECONDS
        self.start_time = time.time()
        self.thread.start()

    def execute(self):
        while (not self.execution_state.is_stopped()
               and time.time() < self.start_time + self.timeout):
            self.execution_state.wait_for_next_tick_or_stop()
            if not self.execution_state.is_stopped():
                self.execution_counter += 1


class TestPause:
    @before
    def before(self):
        self.state = ExecutionState()
        self.executor = ExecutorForTest(self.state)
        yield
        self.state.signal_stop()

    def test_is_paused(self):
        self.state.signal_pause(block=True)
        assert self.state.is_paused()

    def test_when_resumed_it_continues_to_run(self):
        self.state.signal_resume(block=True)
        assert not self.state.is_paused()
        assert not self.state.is_stopped()

    def test_when_it_is_paused_it_resumes(self):
        self.state.signal_pause(block=True)

        self.state.signal_resume(block=True)
        assert not self.state.is_paused()
        assert not self.state.is_stopped()

    def test_it_resumes_after_pausing_several_times(self):
        self.state.signal_pause(block=True)
        self.state.signal_pause(block=True)

        self.state.signal_resume(block=True)
        assert not self.state.is_paused()
        assert not self.state.is_stopped()


class TestStop:
    @before
    def before(self):
        self.state = ExecutionState()
        self.executor = ExecutorForTest(self.state)

    def test_is_stopped(self):
        self.state.signal_stop(block=True)
        assert self.state.is_stopped()


class TestDelay:
    def before(self):
        self.initial_delay = datetime.timedelta(seconds=1)
        self.default_delay = datetime.timedelta(seconds=2)
        self.mock_queue = MagicMock(name="queue", spec=Queue)
        self.state = ExecutionState(
            delay_provider=lambda: self.default_delay,
            initial_delay=self.initial_delay,
            state_changes_queue=self.mock_queue,
            clock=lambda: 1)
        # mock queue so that we instantly return Empty without waiting for timeout
        self.mock_queue.get.side_effect = Empty


class TestDelayFirstExecution(TestDelay):
    @before
    def before(self):
        super().before()

    def test_we_waited_for_initial_delay(self):
        is_time_to_execute = self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.assert_called_once_with(
            block=True, timeout=self.initial_delay.total_seconds())
        assert is_time_to_execute

    def test_when_delay_changed_after_first_execution_we_then_waited_for_default_delay(self):
        self.default_delay = datetime.timedelta(milliseconds=2700)
        self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.reset_mock()
        is_time_to_execute = self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.assert_called_once_with(block=True, timeout=2.7)
        assert is_time_to_execute


class TestDelayChangedDuringAnExecution(TestDelay):
    @before
    def before(self):
        super().before()
        self.default_delay = datetime.timedelta(milliseconds=2700)

        # wait for first execution, initial_delay has elapsed
        self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.reset_mock()

        # wait for second execution, normal delay has elapsed
        self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.reset_mock()

        # now delay changes (e.g. new configuration from orchestrator)
        self.default_delay = datetime.timedelta(milliseconds=1234)

    def test_we_then_waited_for_new_delay(self):
        is_time_to_execute = self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.assert_called_once_with(block=True, timeout=1.234)
        assert is_time_to_execute


class TestDelayProviderChangedDuringAnExecution(TestDelay):
    @before
    def before(self):
        super().before()
        self.default_delay = datetime.timedelta(milliseconds=2700)

        # wait for first execution, initial_delay has elapsed
        self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.reset_mock()

        # wait for second execution, normal delay has elapsed
        self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.reset_mock()

        # now delay provider changes (e.g. profiler_runner changes the scheduler config)
        self.state.delay_provider = lambda: datetime.timedelta(milliseconds=1234)

    def test_we_then_waited_for_new_delay(self):
        is_time_to_execute = self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.assert_called_once_with(block=True, timeout=1.234)
        assert is_time_to_execute


class TestPausedTime:
    @before
    def before(self):
        self.initial_delay = datetime.timedelta(seconds=10)
        self.default_delay = datetime.timedelta(seconds=20)
        self.first_pause_time = 3
        self.first_resume_time = 8
        self.mock_queue = MagicMock(name="queue", spec=Queue)
        self.mock_clock = MagicMock(name="clock", spec=time.time)
        self.mock_clock.side_effect = [
            0, self.first_pause_time, self.first_resume_time
        ]
        self.state = ExecutionState(
            delay_provider=lambda: self.default_delay,
            initial_delay=self.initial_delay,
            state_changes_queue=self.mock_queue,
            clock=self.mock_clock)
        # mock queue so that we simulate a pause command at 3 o'clock
        # then a resume command at 8 o'clock and then no change.
        # With initial delay being 10, we should wait for 7 more after resume.
        self.mock_queue.get.side_effect = \
            [
                {
                    "state": ExecutionState.PAUSED,
                    "current_time": self.first_pause_time
                },
                {
                    "state": ExecutionState.RUNNING,
                    "current_time": self.first_resume_time
                },
                Empty
            ]

    def test_when_paused_during_initial_delay_we_waited_for_remaining_time_after_resume(self):
        is_time_to_execute = self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.assert_called_with(
            block=True,
            timeout=7)
        assert is_time_to_execute

    def test_when_paused_again_after_first_execution_we_waited_for_correct_remaining_time_after_second_resume(self):
        self.initial_execution_time = 15
        self.second_pause_time = 19
        self.second_resume_time = 23
        self.mock_queue.get.side_effect = \
            [
                {
                    "state": ExecutionState.PAUSED,
                    "current_time": self.first_pause_time
                },
                {
                    "state": ExecutionState.RUNNING,
                    "current_time": self.first_resume_time
                },
                Empty,
                {
                    "state": ExecutionState.PAUSED,
                    "current_time": self.second_pause_time
                },
                {
                    "state": ExecutionState.RUNNING,
                    "current_time": self.second_resume_time
                },
                Empty
            ]
        self.mock_clock.side_effect = [
            0, self.first_pause_time, self.first_resume_time, self.initial_execution_time,
            self.second_pause_time, self.second_resume_time
        ]

        # first wait until we execute at time 15s
        self.state.wait_for_next_tick_or_stop()

        # second call should wait for 20s for normal delay, then wait for 15s remaining after resume
        is_time_to_execute = self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.assert_has_calls([
            call(block=True, timeout=10),  # wanted to wait for 10s, the initial delay
            call(block=True),  # after pause at 3s, wait until next resume
            call(block=True, timeout=7),  # after resume at 8s wait for 7s remaining from initial delay
            call(block=True, timeout=20),  # at 15s, wanted to wait for 20s, the normal delay
            call(block=True),  # after pause at 19s, wait until next resume
            call(block=True, timeout=16)])  # after resume at 23s wait for 6s remaining from initial delay
        assert is_time_to_execute

    def test_when_paused_multiple_times_in_initial_delay_the_wait_time_accumulates(self):
        self.first_pause_time = 3
        self.first_resume_time = 8
        self.second_pause_time = 9
        self.second_resume_time = 10
        self.mock_queue.get.side_effect = \
            [
                {
                    "state": ExecutionState.PAUSED,
                    "current_time": self.first_pause_time
                },
                {
                    "state": ExecutionState.RUNNING,
                    "current_time": self.first_resume_time
                },
                {
                    "state": ExecutionState.PAUSED,
                    "current_time": self.second_pause_time
                },
                {
                    "state": ExecutionState.RUNNING,
                    "current_time": self.second_resume_time
                },
                Empty
            ]
        self.mock_clock.side_effect = [
            0, self.first_pause_time, self.first_resume_time, self.second_pause_time, self.second_resume_time
        ]

        is_time_to_execute = self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.assert_has_calls([
            call(block=True, timeout=10),  # wanted to wait for 10s, the initial delay
            call(block=True),  # after pause at 3s, wait until next resume
            call(block=True, timeout=7),  # after resume at 8s wait for 7s remaining from initial delay
            call(block=True),  # after pause at 9s, wait until next resume
            call(block=True, timeout=6)])  # after resume at 10s wait for 6s remaining from initial delay
        assert is_time_to_execute

    def test_when_paused_multiple_times_in_normal_delay_the_wait_time_accumulates_the_wait_time_accumulates(self):
        self.first_pause_time = 13
        self.first_resume_time = 18
        self.second_pause_time = 19
        self.second_resume_time = 20
        self.mock_queue.get.side_effect = \
            [
                Empty,
                {
                    "state": ExecutionState.PAUSED,
                    "current_time": self.first_pause_time
                },
                {
                    "state": ExecutionState.RUNNING,
                    "current_time": self.first_resume_time
                },
                {
                    "state": ExecutionState.PAUSED,
                    "current_time": self.second_pause_time
                },
                {
                    "state": ExecutionState.RUNNING,
                    "current_time": self.second_resume_time
                },
                Empty
            ]
        self.mock_clock.side_effect = [
            0, 10, self.first_pause_time, self.first_resume_time, self.second_pause_time, self.second_resume_time
        ]

        # first wait until we execute after 10s, the initial delay
        self.state.wait_for_next_tick_or_stop()
        # then wait again for the normal delay and receive multiple pause and resume calls
        is_time_to_execute = self.state.wait_for_next_tick_or_stop()
        self.mock_queue.get.assert_has_calls([
            call(block=True, timeout=10),  # wait for 10s, the initial delay
            call(block=True, timeout=20),  # wanted to wait for 20s, the normal delay
            call(block=True),  # after pause at 13s, wait until next resume
            call(block=True, timeout=17),  # after resume at 18s wait for 17s remaining from initial delay
            call(block=True),  # after pause at 19s, wait until next resume
            call(block=True, timeout=16)])  # after resume at 10s wait for 16s remaining from initial delay
        assert is_time_to_execute
