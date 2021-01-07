from __future__ import absolute_import
import threading
import logging
import datetime

from codeguru_profiler_agent.utils.execution_state import ExecutionState

logger = logging.getLogger(__name__)

DEFAULT_TIME_TO_AWAIT_TERMINATION_SECONDS = 2


class Scheduler:
    def __init__(self,
                 command,
                 delay_provider=None,
                 initial_delay=datetime.timedelta(),
                 thread_name=None,
                 args=None,
                 kwargs=None):
        """
        Creates and executes a periodic action that will be run first without any delay and subsequently with the
        given delay between the termination of one execution and the commencement of the next.
        Scheduled thread gets terminated if exception thrown, hence subsequent execution will not happen.
        The scheduler can be paused, it will then keep running but not execute the command until resume() is called.

        :param command: a new thread will be spawned for executing this command with arguments
            specified in args and kwargs
        :param delay_provider: function providing the delay between executions as a timedelta, default returns always 1s
        :param initial_delay: delay before first execution as a timedelta, default is 0s.
        :param thread_name: name of the new spawned thread
        :param args: (list) passing argument by its position
        :param kwargs: (dict) passing argument by the arguments' names
        """
        self._command = command
        self._thread = \
            threading.Thread(target=self._schedule_task_execution, name=thread_name)
        self._thread.daemon = True
        self._args = args if args is not None else []
        self._kwargs = kwargs if kwargs is not None else {}
        self._state = ExecutionState(
            delay_provider=delay_provider if delay_provider else lambda: datetime.timedelta(seconds=1),
            initial_delay=initial_delay)

    def start(self):
        if self.is_running():
            # nothing to do if we are already running
            logger.info("Ignored Scheduler.start() as it is already running!")
            return
        try:
            self._thread.start()
        except RuntimeError:
            # replace the exception from threading by ours with more explanations.
            raise RuntimeError(
                "Profiler cannot be started again after stop. Use a new Profiler instance or use pause() instead of stop()"
            )

    def is_running(self):
        """
        This tells if the scheduler is currently running.
        It still returns True when we are paused.
        """
        return self._thread.is_alive()

    def is_paused(self):
        return self.is_running() and self._state.is_paused()

    def stop(self):
        """
        Stop the scheduled thread from executing the command and wait for termination.
        """
        self._state.signal_stop()
        if not self.is_running():
            return
        self._thread.join(DEFAULT_TIME_TO_AWAIT_TERMINATION_SECONDS)

    def _schedule_task_execution(self):
        should_run = self._state.wait_for_next_tick_or_stop()
        while should_run:
            should_run = \
                self._command(*self._args, **self._kwargs) and self._state.wait_for_next_tick_or_stop()
        # call set_stopped in case it is the command that returned False.
        self._state.set_stopped()

    def update_delay_provider(self, delay_provider):
        self._state.delay_provider = delay_provider

    def resume(self, block=False):
        """
        Will signal the sampling thread that profiling should resume.

        :param block: if True, we will not return from this function before the change is applied, default is False.
        """
        self._state.signal_resume(block)

    def pause(self, block=False):
        """
        Will signal the sampling thread that profiling should pause.

        :param block: if True, we will not return from this function before the change is applied, default is False.
        """
        self._state.signal_pause(block)

    def _get_next_delay_seconds(self):
        """
        Useful for testing
        """
        return self._state.next_delay_seconds()
