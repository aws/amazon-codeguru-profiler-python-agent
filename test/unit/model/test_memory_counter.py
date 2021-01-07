import sys

from pympler import asizeof

from codeguru_profiler_agent.model.call_graph_node import CallGraphNode
from codeguru_profiler_agent.model.frame import Frame
from codeguru_profiler_agent.model.memory_counter import MemoryCounter


# These tests validate that our simple memory tracker's math matches with what we can observe in the Pympler memory
# sizing library
class TestMemoryCounter:
    class TestEmptyNodeSize:
        def test_it_matches_the_expected_size(self):
            dummy_frame_name = None

            node = CallGraphNode(frame_name=dummy_frame_name, class_name=None, file_path=None, line_no=None)
            node.increase_runnable_count()

            full_recursive_size_of_node = asizeof.asizeof(node)

            frame_name_size = sys.getsizeof(dummy_frame_name)
            empty_children_tuple_size = sys.getsizeof(())

            assert (MemoryCounter.empty_node_size_bytes == \
                (full_recursive_size_of_node \
                    # The empty size should not include the frame name, so we subtract it
                    - frame_name_size
                    # The empty tuple is always reused by Python, so we also subtract it
                    - empty_children_tuple_size))

        def test_sanity_check_it_is_smaller_than_512_bytes(self):
            assert (MemoryCounter.empty_node_size_bytes <= 256)

    class TestBaseStorageSize:
        def test_it_matches_the_expected_size(self):
            node = CallGraphNode(frame_name=None, class_name=None, file_path=None, line_no=None)
            node.update_current_node_and_get_child(frame=Frame(None))

            recursive_node_storage_size = asizeof.asizeof(node.children)
            child_node_size = asizeof.asizeof(
                CallGraphNode(frame_name=None, class_name=None, file_path=None, line_no=None))

            assert (MemoryCounter.base_storage_size_bytes == (
                recursive_node_storage_size - child_node_size))

        def test_sanity_check_it_is_smaller_than_100_bytes(self):
            assert (MemoryCounter.base_storage_size_bytes <= 100)

    class TestStorageIncrementSize:
        def test_it_matches_the_expected_size(self):
            node = CallGraphNode(frame_name=None, class_name=None, file_path=None, line_no=None)

            node.update_current_node_and_get_child(Frame("child1"))
            one_child_storage_size = asizeof.asizeof(node.children, limit=0)

            node.update_current_node_and_get_child(Frame("child2"))
            two_children_storage_size = asizeof.asizeof(node.children, limit=0)

            assert (MemoryCounter.storage_increment_size_bytes == (
                two_children_storage_size - one_child_storage_size))

        def test_sanity_check_it_is_smaller_than_16_bytes(self):
            assert (MemoryCounter.storage_increment_size_bytes <= 16)

    class TestCountCreateNode:
        def test_sanity_check_it_counts_frame_file_path_line_no_class_name_size(self):
            subject = MemoryCounter()
            subject.count_create_node(frame="test/frame", file_path="test/file/path", class_name="TestClass")
            # [Oct-2020 Python-3.7.7] "test/frame" size: 59 bytes; "test/file/path" size: 63 bytes; "TestClass" size:
            # 58 bytes; fixed line_no size: 2 * 32 = 64; sum = 244
            expected_size = subject.empty_node_size_bytes + 244
            assert (subject.get_memory_usage_bytes() == expected_size)
