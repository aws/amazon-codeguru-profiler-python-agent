from abc import ABCMeta, abstractmethod


class Reporter(metaclass=ABCMeta):  # pragma: no cover
    """
    A reporter to be used by the aggregator.
    """

    @abstractmethod
    def setup(self):
        """
        Setup expensive resources.
        """
        pass

    @abstractmethod
    def refresh_configuration(self):
        """
        Configure agent by calling the profiler backend service.

        :return: the updated agent configuration
        """
        pass

    @abstractmethod
    def report(self, profile):
        """
        Report profile.

        :param profile: profile to be reported
        :return: True if profile gets reported successfully; False otherwise.
        """
        pass
