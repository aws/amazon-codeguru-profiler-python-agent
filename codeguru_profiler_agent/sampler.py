import logging
import random
import sys

import codeguru_profiler_agent.sampling_utils
from codeguru_profiler_agent.metrics.with_timer import with_timer
from codeguru_profiler_agent.model.sample import Sample
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration

logger = logging.getLogger(__name__)


class Sampler:
    """
    Returns a Sample containing the stack frames for the currently running threads.

    A Sample includes the thread doing the sample, unless that thread is included in the `excluded_threads` set.
    (Within the context of a running Profiler, the Profiler top-level class is currently responsible for adding the
    Profiler background thread to the `excluded_threads` so that it does not appear in the call graph.)
    """

    def __init__(self, environment=dict()):
        """
        :param environment: dependency container dictionary for the current profiler
        :param max_threads: (inside environment) the max number of threads getting sampled
        :param excluded_threads: (inside environment) set of thread names to be excluded from sampling
        """
        self._max_threads = environment.get("max_threads") or 100
        self._excluded_threads = environment.get("excluded_threads") or set()
        self._get_stacks = \
            environment.get("get_stacks") or codeguru_profiler_agent.sampling_utils.get_stacks
        self._thread_lister = environment.get("thread_lister") or sys
        self.timer = environment.get("timer")

    @with_timer("dumpAllStackTraces")
    def sample(self):
        """
        Samples stack traces of running threads (up to max_threads, and excluding excluded_threads) running in the
        current Python instance. Any exception encountered during sampling process will be propagated.
        """
        all_threads = self._get_all_threads()
        all_threads_count = len(all_threads)
        threads_to_sample = self._threads_to_sample_from(all_threads)
        threads_to_sample_count = len(threads_to_sample)

        stacks = self._get_stacks(
            threads_to_sample=threads_to_sample,
            excluded_threads=self._excluded_threads,
            max_depth=AgentConfiguration.get().max_stack_depth)

        # Memory usage optimization
        del all_threads
        del threads_to_sample

        return Sample(stacks=stacks, attempted_sample_threads_count=threads_to_sample_count,
                      seen_threads_count=all_threads_count)

    def _get_all_threads(self):
        return self._thread_lister._current_frames().items()

    def _threads_to_sample_from(self, all_threads):
        if len(all_threads) > self._max_threads:
            return random.sample(all_threads, self._max_threads)
        else:
            return all_threads
