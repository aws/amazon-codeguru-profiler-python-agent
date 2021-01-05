from __future__ import absolute_import

from time import perf_counter
from time import process_time


def with_timer(metric_name, measurement="cpu-time"):
    """
    The decorator only works on all methods under the class which contains a Timer (with name timer).
    """

    def wrapper(fn):
        if measurement == "cpu-time":
            get_time_seconds = process_time
        elif measurement == "wall-clock-time":
            get_time_seconds = perf_counter
        else:
            raise Exception(
                "Unexpected measurement mode for timer '{}'".format(
                    str(measurement)))

        def timed(self, *args, **kwargs):
            if self.timer is None:
                return fn(self, *args, **kwargs)
            time_start_seconds = get_time_seconds()
            result = fn(self, *args, **kwargs)
            self.timer.record(metric_name,
                              get_time_seconds() - time_start_seconds)

            return result

        return timed

    return wrapper
