from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration
from test.pytestutils import before
import unittest.mock as mock
from mock import create_autospec, MagicMock, ANY

from codeguru_profiler_agent.sampler import Sampler
from codeguru_profiler_agent.sampling_utils import get_stacks


class TestSampler:
    def before(self):
        AgentConfiguration.set(AgentConfiguration._get_new_config(configure_agent_response={
            "agentParameters": {
                "SamplingIntervalInMilliseconds": "2700",
                "MinimumTimeForReportingInMilliseconds": "60000",
                "MaxStackDepth": "1000"
            },
            "periodInSeconds": 123
        }))
        self.mock_get_stacks = create_autospec(get_stacks)
        self.mock_thread_lister = MagicMock(name="thread_lister")
        self._current_frames_reply = {
            "fake_thread_1": "fake_thread_frames_1",
            "fake_thread_2": "fake_thread_frames_2"
        }
        self.mock_thread_lister._current_frames = \
            MagicMock(name="current_frames_list", return_value=self._current_frames_reply)
        self.environment = {
            "get_stacks": self.mock_get_stacks,
            "thread_lister": self.mock_thread_lister,
        }


class TestSample(TestSampler):
    @before
    def before(self):
        super().before()

    def test_it_includes_the_number_of_threads_it_attempted_to_sample_and_how_many_in_total_were_seen_in_the_system(
            self):
        self.mock_get_stacks.result = [["dummy_stack_sample"]]
        sampler = Sampler(environment=self.environment)

        result = sampler.sample()

        assert (result.attempted_sample_threads_count == 2)
        assert (result.seen_threads_count == 2)

    def test_it_calls_the_get_stacks_method_with_the_current_threads_and_the_default_excluded_threads_and_default_max_depth(
            self):
        default_excluded_threads = set()
        default_max_depth = 1000

        sampler = Sampler(environment=self.environment)

        sampler.sample()

        self.mock_get_stacks.assert_called_once_with(
            threads_to_sample=self._current_frames_reply.items(),
            excluded_threads=default_excluded_threads,
            max_depth=default_max_depth,
        )


class TestWhenThereAreMoreThreadsThanMaxThreads(TestSampler):
    @before
    def before(self):
        super().before()
        self.environment["max_threads"] = 1
        self.subject = Sampler(environment=self.environment)

    def test_it_calls_the_get_stacks_method_with_a_subset_of_the_threads(
            self):
        self.subject.sample()

        allowed_results = [
            mock.call(
                threads_to_sample=[("fake_thread_1", "fake_thread_frames_1")],
                excluded_threads=ANY,
                max_depth=ANY,
            ),
            mock.call(
                threads_to_sample=[("fake_thread_2", "fake_thread_frames_2")],
                excluded_threads=ANY,
                max_depth=ANY,
            ),
        ]

        assert (self.mock_get_stacks.call_args in allowed_results)

    def test_it_includes_the_number_of_threads_it_attempted_to_sample_and_how_many_in_total_were_seen_in_the_system(
            self):
        self.mock_get_stacks.result = [["dummy_stack_sample"]]

        result = self.subject.sample()

        assert (result.attempted_sample_threads_count == 1)
        assert (result.seen_threads_count == 2)


class TestWhenACustomStackDepthLimitIsSpecified(TestSampler):
    @before
    def before(self):
        super().before()

    def test_it_calls_the_get_stacks_method_with_the_custom_max_stack_depth(
            self):
        AgentConfiguration.set(AgentConfiguration._get_new_config(configure_agent_response={
            "agentParameters": {
                "SamplingIntervalInMilliseconds": "2700",
                "MinimumTimeForReportingInMilliseconds": "60000",
                "MaxStackDepth": "10"
            },
            "periodInSeconds": 123
        }))
        sampler = Sampler(environment=self.environment)

        sampler.sample()

        self.mock_get_stacks.assert_called_once_with(
            threads_to_sample=ANY,
            excluded_threads=ANY,
            max_depth=10,
        )


class TestWhenExcludedThreadsAreSpecified(TestSampler):
    @before
    def before(self):
        super().before()

    def test_it_calls_the_get_stacks_method_with_the_custom_excluded_threads_list(
            self):
        self.environment["excluded_threads"] = {"exclude_me"}
        sampler = Sampler(environment=self.environment)

        sampler.sample()

        self.mock_get_stacks.assert_called_once_with(
            threads_to_sample=ANY,
            excluded_threads={"exclude_me"},
            max_depth=ANY)
