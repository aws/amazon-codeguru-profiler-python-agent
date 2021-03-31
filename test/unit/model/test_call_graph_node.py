import pytest

from codeguru_profiler_agent.model.frame import Frame
from test.pytestutils import before
from unittest.mock import MagicMock

from codeguru_profiler_agent.model.call_graph_node import CallGraphNode
from codeguru_profiler_agent.model.memory_counter import MemoryCounter


class TestCallGraphNodeInit:
    def test_memory_count_called(self):
        mock_memory_counter = _mock_memory_counter()
        CallGraphNode("foo", class_name=None, file_path=None, line_no=None, memory_counter=mock_memory_counter)

        mock_memory_counter.count_create_node.assert_called_once()
        mock_memory_counter.count_first_child.assert_not_called()
        mock_memory_counter.count_add_child.assert_not_called()


class TestCallGraphNode:
    def before(self):
        self.subject = CallGraphNode("dummy_frame", None, file_path="file_path/file.py", line_no=123)


class TestUpdateCurrentNodeAndGetChild(TestCallGraphNode):
    @before
    def before(self):
        super().before()

    def test_when_child_node_with_frame_does_not_exist_it_adds_a_new_child_node(self):
        new_child_node = self.subject.update_current_node_and_get_child(Frame("new_child_frame"))

        assert (new_child_node in self.subject.children)

    def test_when_child_node_with_frame_does_not_exist__it_returns_a_new_child_node_for_the_given_frame(
            self):
        new_child_node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", class_name="TestClass", file_path="file_path/file.py", line_no=123))

        assert (new_child_node.frame_name == "new_child_frame")
        assert (new_child_node.class_name == "TestClass")
        assert (new_child_node.file_path == "file_path/file.py")
        assert (new_child_node.start_line == 123)
        assert (new_child_node.end_line == 123)
        assert (new_child_node.runnable_count == 0)

    def test_when_class_does_not_exist_it_returns_a_new_child_node_with_None_class_name(self):
        new_child_node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", class_name=None))

        assert (new_child_node.class_name is None)

    def test_when_file_path_does_not_exist_it_returns_a_new_child_node_with_None_file_path(self):
        new_child_node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", file_path=None))

        assert (new_child_node.file_path is None)

    def test_when_line_no_does_not_exist_it_returns_a_new_child_node_with_None_line_no(self):
        new_child_node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", line_no=None))

        assert (new_child_node.start_line is None)
        assert (new_child_node.end_line is None)

    def test_when_class_name_is_different_it_returns_a_new_child_node(self):
        existing_node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", class_name="TestClassA"))
        new_node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", class_name="TestClassB"))

        assert (existing_node is not new_node)

    def test_when_file_path_is_different_it_returns_a_new_child_node(self):
        existing_node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", file_path="file_path/file1.py"))
        new_node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", class_name="file_path/file2.py"))

        assert (existing_node is not new_node)

    def test_when_frame_name_is_different_it_returns_a_new_child_node(self):
        existing_node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame_1"))
        new_node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame_2"))

        assert (existing_node is not new_node)

    def test_when_child_node_with_frame_already_existed_it_does_not_add_a_new_one(self):
        self.subject.update_current_node_and_get_child(Frame("new_child_frame"))

        self.subject.update_current_node_and_get_child(Frame("new_child_frame"))

        assert (len(self.subject.children) == 1)

    def test_when_child_node_with_frame_already_existed_it_returns_the_existing_child_node(
            self):
        new_child_node = self.subject.update_current_node_and_get_child(Frame("new_child_frame"))

        assert (self.subject.update_current_node_and_get_child(Frame("new_child_frame")) is new_child_node)

    def test_when_line_no_needs_to_be_updated_it_takes_the_smallest_start_line_no(self):
        self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", file_path="file_path/file.py", line_no=123))

        node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", file_path="file_path/file.py", line_no=100))

        assert (node.start_line == 100)
        assert (node.end_line == 123)

    def test_when_line_no_needs_to_be_updated_it_takes_the_largest_end_line_no(self):
        self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", file_path="file_path/file.py", line_no=200))

        node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", file_path="file_path/file.py", line_no=234))

        assert (node.start_line == 200)
        assert (node.end_line == 234)

    def test_when_no_lines_existed_before_it_updates_line_no_range(self):
        self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", file_path="file_path/file.py", line_no=None))

        node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", file_path="file_path/file.py", line_no=200))

        assert (node.start_line == 200)
        assert (node.end_line == 200)

    def test_when_lines_no_not_available_it_does_not_update_line_no(self):
        self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", file_path="file_path/file.py", line_no=None))

        node = self.subject.update_current_node_and_get_child(
            Frame("new_child_frame", file_path="file_path/file.py", line_no=None))

        assert (node.start_line is None)
        assert (node.end_line is None)

        def test_when_line_no_existed_before_it_does_not_update_line_no(self):
            self.subject.update_current_node_and_get_child(
                Frame("new_child_frame", file_path="file_path/file.py", line_no=100))

            node = self.subject.update_current_node_and_get_child(
                Frame("new_child_frame", file_path="file_path/file.py", line_no=None))

            assert (node.start_line == 100)
            assert (node.end_line == 100)

class TestInteractionWithMemoryCounter:
    def test_insert_first_child_calls_memory_counter(self):
        mock_memory_counter = _mock_memory_counter()
        call_graph_node = CallGraphNode("foo", class_name=None, file_path=None, line_no=None,
                                        memory_counter=mock_memory_counter)

        call_graph_node.update_current_node_and_get_child(Frame("new_child_frame"))

        mock_memory_counter.count_first_child.assert_called_once()
        mock_memory_counter.count_add_child.assert_not_called()

    def test_insert_already_exist_child_does_not_call_memory_counter(self):
        mock_memory_counter = _mock_memory_counter()
        call_graph_node = CallGraphNode("foo", class_name=None, file_path=None, line_no=None,
                                        memory_counter=mock_memory_counter)
        call_graph_node.update_current_node_and_get_child(Frame("new_child_frame"))
        mock_memory_counter.reset_mock()

        call_graph_node.update_current_node_and_get_child(Frame("new_child_frame"))

        mock_memory_counter.assert_not_called()

    def test_insert_extra_child_calls_memory_counter(self):
        mock_memory_counter = _mock_memory_counter()
        call_graph_node = CallGraphNode("foo", class_name=None, file_path=None, line_no=None,
                                        memory_counter=mock_memory_counter)
        call_graph_node.update_current_node_and_get_child(Frame("new_child_frame_1"))
        mock_memory_counter.reset_mock()

        call_graph_node.update_current_node_and_get_child(Frame("new_child_frame_2"))

        mock_memory_counter.count_first_child.assert_not_called()
        mock_memory_counter.count_add_child.assert_called_once()


class TestIncreaseRunnableCount:
    def test_it_increases_the_runnable_count_by_one(self):
        subject = CallGraphNode("dummy_frame", class_name=None, file_path=None, line_no=None)
        subject.increase_runnable_count()

        assert (subject.runnable_count == 1)

    def test_when_a_custom_value_to_add_is_used_it_increases_the_runnable_count_by_the_value_to_add(self):
        subject = CallGraphNode("dummy_frame", class_name=None, file_path=None, line_no=None)
        subject.increase_runnable_count(value_to_add=2)

        assert (subject.runnable_count == 2)

    def test_when_a_custom_value_to_add_is_used_it_raises_a_value_error(self):
        subject = CallGraphNode("dummy_frame", class_name=None, file_path=None, line_no=None)
        with pytest.raises(ValueError):
            subject.increase_runnable_count(value_to_add=-1)


def _mock_memory_counter():
    return MagicMock(name="memory_counter", spec=MemoryCounter)
