import pytest
from mock import mock
import sys

from test import help_utils

from codeguru_profiler_agent.sampling_utils import get_stacks

DEFAULT_TRUNCATED_FRAME_NAME = "<Truncated>"


def is_frame_in_stacks(stacks, target_frame):
    for stack in stacks:
        for frame in stack:
            if target_frame in frame.name:
                return True
    return False


def assert_frames_in_stack_are_in_expected_order(stacks, parent_frame, child_frame):
    for stack in stacks:
        for i in range(len(stack)):
            if parent_frame in stack[i].name:
                assert child_frame in stack[i + 1].name
                return
    assert False


class TestSamplingUtils:
    class TestGetStacks:
        @pytest.fixture(autouse=True)
        def around(self):
            self.helper = help_utils.HelperThreadRunner()
            self.helper.new_helper_thread_blocked_inside_dummy_method()
            yield
            self.helper.stop_helper_thread()

        def test_it_adds_time_sleep_frame(self):
            # Run a sleeping thread for 1 second so get_stack should capture it; it will not block the test and it
            # dies after a second.
            self.helper.new_helper_sleep_thread(sleep_sec=1)
            stacks = get_stacks(
                threads_to_sample=sys._current_frames().items(),
                excluded_threads=set(),
                max_depth=100)

            assert is_frame_in_stacks(stacks, target_frame="<Sleep>")

        def test_it_returns_a_list_of_lists_containing_stack_frames(self):
            stacks = get_stacks(
                threads_to_sample=sys._current_frames().items(),
                excluded_threads=set(),
                max_depth=100)

            assert_frames_in_stack_are_in_expected_order(
                stacks, "dummy_parent_method",
                "dummy_method")

        def test_it_truncates_stacks_deeper_than_max_depth(self):
            stacks = get_stacks(
                threads_to_sample=sys._current_frames().items(),
                excluded_threads=set(),
                max_depth=2)

            for stack in stacks:
                assert len(stack) == 2
                assert stack[-1].name == DEFAULT_TRUNCATED_FRAME_NAME

        def test_it_excludes_the_given_threads_from_the_output(self):
            stacks = get_stacks(
                threads_to_sample=sys._current_frames().items(),
                excluded_threads=set(["test-thread"]),
                max_depth=100)

            assert not is_frame_in_stacks(stacks, "dummy_parent_method")

        def test_it_does_not_include_zombie_threads(self):
            with mock.patch(
                    "codeguru_profiler_agent.sampling_utils._is_zombie",
                    side_effect=
                    lambda thread: True if thread.name == "test-thread" else False
            ):

                stacks = get_stacks(
                    threads_to_sample=sys._current_frames().items(),
                    excluded_threads=set(),
                    max_depth=100)

                assert not is_frame_in_stacks(
                    stacks, "dummy_parent_method")
