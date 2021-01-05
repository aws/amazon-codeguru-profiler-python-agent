from codeguru_profiler_agent.metrics.metric import Metric


class Timer:
    """
    Keeps all metrics collected during Profiler execution.
    At the moment these metrics are collected but not reported to the backend.
    """

    def __init__(self):
        self.metrics = {}

    def record(self, name, value):
        metric = self.metrics.get(name)
        if metric is None:
            metric = self.metrics[name] = Metric()
        metric.add(value)

    def reset(self):
        self.metrics = {}

    def get_metric(self, name):
        return self.metrics.get(name)
