class Metric:
    def __init__(self):
        self.counter = 0
        self.total = 0
        self.max = 0

    def add(self, value):
        self.counter += 1
        self.total += value
        if self.max < value:
            self.max = value

    def average(self):
        return 0 if self.counter == 0 else self.total / self.counter

    def __repr__(self):
        return "{}@{:#04x}(counter={}, total={:.5f}, max={:.5f}, average={:.5f})".format(
            self.__class__.__name__, id(self), self.counter, self.total,
            self.max, self.average())
