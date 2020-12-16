from test.pytestutils import before

from codeguru_profiler_agent.metrics.timer import Timer


class TestTimer:
    class TestRecord:
        @before
        def before(self):
            self.subject = Timer()
            self.subject.record("test-record", 10)

        def test_new_record_comes_in(self):
            self.subject.record("new-record", 12)

            assert (self.subject.metrics["new-record"].total == 12)
            assert (self.subject.metrics["new-record"].counter == 1)

        def test_update_old_record(self):
            self.subject.record("test-record", 20)

            assert (self.subject.metrics["test-record"].total == 30)
            assert (self.subject.metrics["test-record"].counter == 2)

    class TestReset:
        def test_metrics_get_reset(self):
            subject = Timer()
            subject.record("test-record", 10)

            subject.reset()

            assert (not "test-record" in subject.metrics)
