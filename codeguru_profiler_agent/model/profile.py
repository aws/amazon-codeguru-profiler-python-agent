import time
import logging

from random import SystemRandom
from codeguru_profiler_agent.model.call_graph_node import CallGraphNode
from codeguru_profiler_agent.model.frame import Frame
from codeguru_profiler_agent.model.memory_counter import MemoryCounter
from codeguru_profiler_agent.utils.time import current_milli_time
from codeguru_profiler_agent.utils.time import to_iso

ROOT_NODE_NAME = "ALL"

logger = logging.getLogger(__name__)

class Profile:
    def __init__(self, profiling_group_name, sampling_interval_seconds, host_weight, start, agent_debug_info, clock=time.time):
        """
        A profile holds the root node of the call graph and the metadata related to the profile
        """
        self.memory_counter = MemoryCounter()

        self.profiling_group_name = profiling_group_name
        self.callgraph = CallGraphNode(ROOT_NODE_NAME, class_name=None, file_path=None, line_no=None,
                                       memory_counter=self.memory_counter)
        self._validate_positive_number(start)
        self.start = start
        self.last_resume = start
        self.last_pause = None
        self._paused_ms = 0
        self._clock = clock
        self._end = None
        self.cpu_time_seconds = None
        self.total_attempted_sample_threads_count = 0
        self.total_seen_threads_count = 0
        self.total_sample_count = 0
        self.sampling_interval_ms = int(sampling_interval_seconds * 1000)
        self.host_weight = int(host_weight)
        self._start_process_time = time.process_time()  # provides process time in fractional seconds as float.
        self.overhead_ms = 0
        self.agent_debug_info = agent_debug_info

    @property
    def end(self):
        return self._end

    @end.setter
    def end(self, value):
        self._validate_positive_number(value)
        if value <= self.start:
            raise ValueError(
                "Profile end value must be greater than {}, got {}".format(self.start, value))
        self._end = value
        # this is the total cpu time spent in this application since start, not just the overhead
        self.cpu_time_seconds = time.process_time() - self._start_process_time

    def get_active_millis_since_start(self):
        """
        This returns the total "active" wall clock time since start. In AWS lambda the process can be frozen, the
        time while we are frozen should not be counted in here. In an EC2 or other type of host it is simply the wall
        clock time since start.

        Previously self.end was used to calculate active_millis_since_start but self.end is updated when a sample is added
        so in rare cases where a sample is collected before the last pause time then we might add additional pause time
        which can lead to incorrect calculation of active time. In worst cases, it can even lead to negative values depending
        on the pause time.

        Below is an example indicating the potential error of considering self.end in the calculation.
        ------------------------------------------------------------------
        |          |        |    |         |    |     |       |     ||||||
        S          P        R    P         R    SE    P       R     REPORT
        s1_________|___p1___|____|____p2___|____e1____|___p3__|__________|

        S - Start
        P - Pause
        R - Resume
        SE - self.end (last sample)
        REPORT - Calculating active time.

        If we consider self.end which is e1 in above case then active time would be e1-s1-(p1+p2+p3). But pause p3 is after e1
        so that leads to incorrect calculation of active time.

        Ideally we would want to set profile_end to be last sample time and subtract pause times only before that but it requires
        additional work in maintaining pause time which isn't worth as it makes the logic complex with very little gain.

        So we are setting it to current time and in some corner cases to last_pause time.
        """
        end = self.last_pause if self.last_pause is not None else current_milli_time(clock=self._clock)
        active_time_millis_since_start = end - self.start - self._paused_ms
        logger.debug(
            "Active time since start is {activeTime} which is calculated using start: {start}, end: {end}, last_pause: {last_pause}, paused_ms: {paused_ms}, last_resume: {last_resume}"
            .format(activeTime = active_time_millis_since_start, start = self.start, end = self._end, last_pause = self.last_pause, paused_ms = self._paused_ms, last_resume = self.last_resume)
        )

        return active_time_millis_since_start

    def add(self, sample):
        """
        Merge Sample into the call graph and update profile end time pointing to the last sample time.
        """
        self.total_attempted_sample_threads_count += \
            sample.attempted_sample_threads_count
        self.total_seen_threads_count += \
            sample.seen_threads_count
        self.total_sample_count += 1

        for stack in sample.stacks:
            self._insert_stack(stack)

        self.end = current_milli_time(clock=self._clock)

    def set_overhead_ms(self, duration_timedelta):
        """
        The overhead is the total cpu time spent profiling since start. It is measured by a Timer object and only passed
        to the profile object before we report it so it is only added here because it is more convenient to convey this
        data with the rest of the profile data.
        """
        self.overhead_ms = duration_timedelta.total_seconds() * 1000

    def _insert_stack(self, stack, runnable_count_increase=1):
        current_node = self.callgraph

        # navigate to the end of the stack in the graph, adding nodes when necessary
        for frame in stack:
            current_node = current_node.update_current_node_and_get_child(frame)

        # only increment the end of the stack as we use self time in the graph
        current_node.increase_runnable_count(runnable_count_increase)

    def get_memory_usage_bytes(self):
        return self.memory_counter.get_memory_usage_bytes()

    def serialize_agent_debug_info_to_json(self):
        return self.agent_debug_info.serialize_to_json()

    def pause(self):
        if self.last_pause is not None:
            # pause gets called when profile is paused
            return
        self.last_pause = current_milli_time(clock=self._clock)
        self.last_resume = None

    def resume(self):
        if self.last_resume is not None:
            # resume gets called when profile is running
            return
        self.last_resume = current_milli_time(clock=self._clock)
        prev_last_pause = self.last_pause
        self.last_pause = None
        self._paused_ms += self.last_resume - prev_last_pause

    def is_empty(self):
        return self.total_seen_threads_count == 0.0

    @staticmethod
    def _validate_positive_number(value):
        if value <= 0:
            raise ValueError(
                "Value must be bigger than 0, got {}".format(value))

    def average_thread_weight(self):
        """
        The average thread weight can be used to detect if the samples contained
        in a given profile were taken from all of the application threads, or
        just from a smaller subset, and thus to rescale counts when profiles
        from several machines are aggregated.

        This value will be 1.0 if all threads were sampled, and > 1.0 if a
        subset was chosen.
        """
        if self.total_attempted_sample_threads_count == 0:
            return 1.0

        return self.total_seen_threads_count / float(
            self.total_attempted_sample_threads_count)

    def __str__(self):
        return "Profile(profiling_group_name=" + self.profiling_group_name \
               + ", start=" + to_iso(self.start) \
               + ', end=' + "none" if self.end is None else to_iso(self.end) \
               + ', duration_ms=' + str(self.get_active_millis_since_start()) \
               + ')'
