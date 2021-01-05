from sys import getsizeof

from codeguru_profiler_agent.model.call_graph_node import CallGraphNode


class MemoryCounter:

    empty_node = CallGraphNode(frame_name="empty_node", class_name=None, file_path=None, line_no=None)
    python_int_size = getsizeof(2**40)
    runnable_counter_size = python_int_size
    # As we store the min and max of line number for each frame, we would need to add these to our memory
    # estimation twice.
    line_no_size = 2 * python_int_size

    empty_node_size_bytes = getsizeof(empty_node) + runnable_counter_size
    base_storage_size_bytes = getsizeof((empty_node, ))
    storage_increment_size_bytes = getsizeof(
        (empty_node, empty_node)) - base_storage_size_bytes

    def __init__(self):
        self.memory_usage_bytes = 0

    def get_memory_usage_bytes(self):
        return self.memory_usage_bytes

    def count_create_node(self, frame, file_path, class_name):
        self.memory_usage_bytes += MemoryCounter.empty_node_size_bytes
        self.memory_usage_bytes += getsizeof(frame)
        self.memory_usage_bytes += getsizeof(file_path)
        self.memory_usage_bytes += getsizeof(class_name)
        # For simplicity, we assume all nodes contain line_no and we only expect root node and
        # duration metric node not to have line_no.
        self.memory_usage_bytes += MemoryCounter.line_no_size

    def count_first_child(self):
        self.memory_usage_bytes += MemoryCounter.base_storage_size_bytes

    def count_add_child(self):
        self.memory_usage_bytes += MemoryCounter.storage_increment_size_bytes
