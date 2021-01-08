class Sample:
    __slots__ = ["stacks", "attempted_sample_threads_count", "seen_threads_count"]

    def __init__(self, stacks, attempted_sample_threads_count=0, seen_threads_count=0):
        """
        :param stacks: list of lists; each list is a list of Frame object representing a thread stack in bottom (of thread stack) to top (of thread stack) order
        :param start_time: current time (in ms) just before we started taking the sample
        :param end_time: current time (in ms) just after we started taking the sample
        :param attempted_sample_threads_count: how many threads we tried to sample (can be > than len(stacks) if we could not get/excluded some threads)
        :param seen_threads_count: total number of threads observed in the system when we took the sample
        """
        self.stacks = stacks
        self.attempted_sample_threads_count = attempted_sample_threads_count
        self.seen_threads_count = seen_threads_count
