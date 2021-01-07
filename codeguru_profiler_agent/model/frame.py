class Frame:

    __slots__ = ("name", "class_name", "line_no", "file_path")

    def __init__(self, name, class_name=None, line_no=None, file_path=None):
        self.name = name
        self.class_name = class_name
        self.line_no = line_no
        self.file_path = file_path
