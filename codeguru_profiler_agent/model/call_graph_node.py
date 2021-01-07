class CallGraphNode:
    # Python magic: By declaring which fields/slots this class is going to have in advance, Python dispenses with the
    # internal dictionary where these are usually stored, which noticeably improves memory footprint, which we are
    # trying to optimize for with this class.
    #
    # Note that of course these need to be maintained in sync with the fields being used by the class.
    __slots__ = ("frame_name", "class_name", "file_path", "runnable_count", "start_line", "end_line", "children",
                 "memory_counter")

    def __init__(self, frame_name, class_name, file_path, line_no, memory_counter=None):
        """
        A node represents a given stack frame at a given position in the stack:
        * it can have children -- frames that were observed to be on top of this frame in some samples
        * it will probably have a parent (except for the root node), but does not keep a reference to it
        It also keeps track of how many times (per thread state) this frame was observed in thread stacks across
        one or more samples.

        :param frame_name: name of the stack frame
        :param class_name: name of the class for where the method is sampled; or None if not applicable
        :param file_path: the absolute path for the file containing the frame; or None if not applicable
        :param line_no: the line_no where we observed this node; or None if not applicable
        """
        self.frame_name = frame_name
        # For normal usage of class, we are able to extract the class name from solution mentioned on
        # https://stackoverflow.com/questions/2203424/python-how-to-retrieve-class-information-from-a-frame-object/2544639#2544639
        # Note that this solution relies on the assumption that the class method has taken self as its first argument
        self.class_name = class_name
        # In well-behaved Python code (not messing with importlib.reload and with dynamically changing the search path),
        # the same frame_name will always correspond to the same file. Since we don't really think those use cases are
        # common, for now we just assume this is the case and don't check for it
        self.file_path = file_path
        self.runnable_count = 0
        # the start and end of the range of line number where we observed this node
        # None is expected for root node and agent duration metric node
        self.start_line = line_no
        self.end_line = line_no
        self.children = ()
        self.memory_counter = memory_counter
        if memory_counter:
            memory_counter.count_create_node(frame_name, file_path, class_name)

    def update_current_node_and_get_child(self, frame):
        """
        According to https://docs.python.org/3.3/tutorial/modules.html#the-module-search-path, it is not possible
        to have same module:function existing in two different files. Therefore, we only compare nodes by
        its frame_name but not by its file_path.
        """
        node = self._get_child(frame=frame) or \
            self._insert_new_child(
                CallGraphNode(frame_name=frame.name, class_name=frame.class_name, file_path=frame.file_path,
                              line_no=frame.line_no))
        node._maybe_update_line_no(frame.line_no)
        return node

    def increase_runnable_count(self, value_to_add=1):
        if value_to_add < 0:
            raise ValueError(
                "Cannot add negative counts to node: {}".format(value_to_add))

        self.runnable_count += value_to_add

    def _maybe_update_line_no(self, line_no):
        if line_no is None:
            return
        if self.start_line is None or self.start_line > line_no:
            self.start_line = line_no
        if self.end_line is None or self.end_line < line_no:
            self.end_line = line_no

    def is_node_match_frame(self, other_frame):
        return self.frame_name == other_frame.name and self.class_name == other_frame.class_name and \
               self.file_path == other_frame.file_path

    # FIXME: Review use of tuple vs list vs dictionary, and linear search vs binary search
    def _get_child(self, frame):
        for child in self.children:
            if child.is_node_match_frame(frame):
                return child
        return None

    def _insert_new_child(self, new_child):
        """
        FIXME: We still need to review the memory vs cpu tradeoffs of using a tuple vs an list vs a dictionary here,
        and if we should keep it sorted (like the Java agent) or keep using the current approach.

        Right now we use a tuple as it uses the least amount of memory (and it simplifies the code, as the empty tuple
        is reused by python):

        >>> import sys
        >>> sys.getsizeof((1,))
        64
        >>> sys.getsizeof([1])
        80
        >>> sys.getsizeof((1, 2))
        72
        >>> sys.getsizeof([1, 2])
        88

        :param new_child: graph node that holds the new child frame
        :return:
        """
        if self.memory_counter:
            if self.children:
                self.memory_counter.count_add_child()
            else:
                self.memory_counter.count_first_child()
        self.children = self.children + (new_child, )
        return new_child
