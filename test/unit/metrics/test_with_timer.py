from test.pytestutils import before

from codeguru_profiler_agent.metrics.with_timer import with_timer
from codeguru_profiler_agent.metrics.timer import Timer


class TargetClass:
    def __init__(self):
        self.timer = Timer()

    @with_timer(metric_name="test-foo-wall", measurement="wall-clock-time")
    def foo_wall(self):
        return

    @with_timer(metric_name="test-foo-cpu", measurement="cpu-time")
    def foo_cpu(self):
        # Run something to make sure the cpu clock does tick (https://bugs.python.org/issue37859)
        len(str(2 ** 500_000))
        return


class TestWithTimer:
    @before
    def before(self):
        self.test_class = TargetClass()

    def test_it_times_wall_time(self):
        self.test_class.foo_wall()

        assert (self.test_class.timer.metrics["test-foo-wall"].counter == 1)
        assert (self.test_class.timer.metrics["test-foo-wall"].max > 0)
        assert (self.test_class.timer.metrics["test-foo-wall"].total ==
                self.test_class.timer.metrics["test-foo-wall"].max)

    def test_it_times_cpu_time(self):
        self.test_class.foo_cpu()

        assert (self.test_class.timer.metrics["test-foo-cpu"].counter == 1)
        assert (self.test_class.timer.metrics["test-foo-cpu"].max > 0)
        assert (self.test_class.timer.metrics["test-foo-cpu"].total ==
                self.test_class.timer.metrics["test-foo-cpu"].max)
