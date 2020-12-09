from datetime import timedelta

_singleton = None


class LambdaContext:
    """
    This class contains the contextual data about AWS lambda execution
    It is kept updated by the profiler decorator when a lambda function is called
    It has a singleton pattern to make it available from anywhere for convenience.
    """
    def __init__(self):
        self.context = None
        self.last_execution_duration = timedelta()

    @classmethod
    def get(cls):
        global _singleton
        if _singleton is None:
            _singleton = LambdaContext()
        return _singleton


