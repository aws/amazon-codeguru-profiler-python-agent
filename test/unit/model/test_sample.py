from codeguru_profiler_agent.model.sample import Sample
from pympler.asizeof import asizeof


class TestSample:
    def test_sizeof_sample(self):
        sample = Sample(stacks="foo")
        assert asizeof(sample) == 136

