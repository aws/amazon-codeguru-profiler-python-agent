import pytest
from test.pytestutils import before

from codeguru_profiler_agent.metrics.metric import Metric


class TestMetric:
    @before
    def before(self):
        self.subject = Metric()

    class TestAdd:
        @before
        def before(self):
            self.subject.add(10)

        def test_value_less_than_max(self):
            self.subject.add(5)

            assert (self.subject.counter == 2)
            assert (self.subject.max == 10)
            assert (self.subject.total == 15)

        def test_value_greater_than_max(self):
            self.subject.add(15)

            assert (self.subject.counter == 2)
            assert (self.subject.max == 15)
            assert (self.subject.total == 25)

    class TestAverage:
        def test_get_average_when_counter_is_zero(self):
            assert (self.subject.average() == 0)

        def test_get_average_when_counter_is_not_zero(self):
            self.subject.add(5)
            self.subject.add(10)
            self.subject.add(15)

            assert (self.subject.average() == 10)
