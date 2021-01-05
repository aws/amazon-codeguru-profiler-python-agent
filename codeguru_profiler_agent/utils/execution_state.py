from __future__ import absolute_import

import time
import datetime

from queue import Queue, Empty


class ExecutionState:
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"

    def __init__(self,
                 delay_provider=None,
                 initial_delay=datetime.timedelta(),
                 state_changes_queue=None,
                 clock=time.time):
        """
        This class keeps track of the state of execution for the scheduler,
        and it handles the delay between executions.
        The user thread should be the only one changing the state with signal_* calls.
        The profiler sampling thread should only read the state and call wait_for_next_tick_or_stop() which
        waits for the appropriate delay and handles pause and resume signals.
        :param delay_provider: function that provides the delay as timedelta, default returns always 1s
        :param initial_delay: time we have to wait before the first execution, default is empty timedelta.
        :param state_changes_queue: the queue in which signals for changes are going. used only for unit tests.
        :param clock: a function to return current time, used only for unit tests. default is time.time
        """
        self._state_changes = state_changes_queue or Queue()
        self._current_state = ExecutionState.RUNNING
        self._clock = clock
        self.initial_delay = initial_delay
        self._already_waited_seconds = 0.0
        self._time_when_waiting_started = None
        self.delay_provider = delay_provider if delay_provider else lambda: datetime.timedelta(seconds=1)

    def signal_resume(self, block=False):
        self._state_changes.put({
            "state": ExecutionState.RUNNING,
            "current_time": self._clock()
        })
        if block:
            self._state_changes.join()

    def signal_pause(self, block=False):
        self._state_changes.put({
            "state": ExecutionState.PAUSED,
            "current_time": self._clock()
        })
        if block:
            self._state_changes.join()

    def signal_stop(self, block=False):
        self._state_changes.put({"state": ExecutionState.STOPPED})
        if block:
            self._state_changes.join()

    def set_stopped(self):
        """
        Contrary to signal_stop, this should not be used by the user thread.
        This is used by sampling thread to make sure the state is set to STOPPED
        when it is stopping for other reasons than a user's signal_stop() call.
        """
        self._current_state = ExecutionState.STOPPED

    def is_paused(self):
        return self._current_state is ExecutionState.PAUSED

    def is_stopped(self):
        return self._current_state is ExecutionState.STOPPED

    def next_delay_seconds(self):
        """
        returns the delay in seconds that we are going to wait next
        """
        if self.initial_delay is None:
            return self.delay_provider().total_seconds()
        else:
            return self.initial_delay.total_seconds()

    def _wait_for_execution_time(self):
        """
        wait for next execution time or for any change of status.
        The first time this is called, if initial_delay is an empty timedelta
        we return immediately without even checking the queue to avoid the small delay.

        :return: The new status change or None if it is time to execute.
        """
        next_delay_seconds = self.next_delay_seconds()
        if next_delay_seconds == 0:
            return None
        try:
            wait_time = max(0.0, next_delay_seconds - self._already_waited_seconds)
            return self._state_changes.get(block=True, timeout=wait_time)
        except Empty:
            return None

    def _wait_for_resume(self):
        return self._state_changes.get(block=True)

    def _apply_new_state(self, new_state):
        """
        Update the current state variable and save the waited time if we paused.

        :return True if there was a change in the state, False otherwise.
        """
        if not new_state:
            return False
        self._current_state = new_state["state"]
        if self._current_state is ExecutionState.PAUSED:
            # if we paused, we save how much time we have already waited so we know how much longer we need to wait.
            # use the time provided by signal_* call as reference in case we were late to catch up with pause signal.
            now = new_state["current_time"]
            self._already_waited_seconds += max(0, now - self._time_when_waiting_started)
        return True

    def wait_for_next_tick_or_stop(self):
        """
        Wait until it is time to execute or the process is stopped.
        Status should either be RUNNING or STOPPED at the end.
        If initial_delay was set to 0 this will return True even if we
        have immediately paused or stopped.

        :return: True if the status is RUNNING at the end. False otherwise.
        """
        is_time_to_execute = False
        while self._current_state is not ExecutionState.STOPPED and not is_time_to_execute:
            self._time_when_waiting_started = self._clock()
            if self._current_state is ExecutionState.PAUSED:
                new_state = self._wait_for_resume()
            else:
                new_state = self._wait_for_execution_time()
            # update state, if there is no change in the state after waiting then it is time to execute.
            is_time_to_execute = not self._apply_new_state(new_state)
            if new_state:
                self._state_changes.task_done()

        # if we exit the while loop that means either we are stopped or it is time to execute
        # remove the initial_delay as we do not need it anymore, also reset _already_waited_seconds
        self.initial_delay = None
        self._already_waited_seconds = 0.0
        return self._current_state is ExecutionState.RUNNING
