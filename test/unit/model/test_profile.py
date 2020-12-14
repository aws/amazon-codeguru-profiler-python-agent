import pytest
from mock import Mock

from codeguru_profiler_agent.model.frame import Frame
from test.pytestutils import before
import datetime

from codeguru_profiler_agent.model.profile import Profile
from codeguru_profiler_agent.model.sample import Sample


class TestProfile:
    def before(self):
        self.test_start_time = 1603884061556
        self.mock_clock = Mock()
        self.mock_clock.return_value = self.test_start_time / 1000
        self.subject = Profile(
            profiling_group_name="foo",
            sampling_interval_seconds=1.0,
            host_weight=2,
            start=self.test_start_time,
            clock=self.mock_clock
        )

        def turn_clock(seconds):
            self.mock_clock.return_value += seconds

        self.turn_clock = turn_clock


class TestAdd(TestProfile):
    @before
    def before(self):
        super().before()

    @pytest.mark.parametrize("stacks, expected", [
        ([[Frame("method_one"), Frame("method_two"), Frame("method_three")]], {
            "count": 0,
            "children": {
                "method_one": {
                    "count": 0,
                    "children": {
                        "method_two": {
                            "count": 0,
                            "children": {
                                "method_three": {
                                    "count": 1,
                                    "children": {}
                                }
                            }
                        }
                    }
                }
            }
        }), ([[Frame("method_one"), Frame("method_two"), Frame("method_three"), Frame("method_five")],
              [Frame("method_one"), Frame("method_two"), Frame("method_four"), Frame("method_five")],
              [Frame("method_one"), Frame("method_two"), Frame("method_three"), Frame("method_six")],
              [Frame("method_one"), Frame("method_seven"), Frame("method_three")]], {
                 "count": 0,
                 "children": {
                     "method_one": {
                         "count": 0,
                         "children": {
                             "method_two": {
                                 "count": 0,
                                 "children": {
                                     "method_three": {
                                         "count": 0,
                                         "children": {
                                             "method_five": {
                                                 "count": 1,
                                                 "children": {}
                                             },
                                             "method_six": {
                                                 "count": 1,
                                                 "children": {}
                                             }
                                         }
                                     },
                                     "method_four": {
                                         "count": 0,
                                         "children": {
                                             "method_five": {
                                                 "count": 1,
                                                 "children": {}
                                             }
                                         }
                                     }
                                 }
                             },
                             "method_seven": {
                                 "count": 0,
                                 "children": {
                                     "method_three": {
                                         "count": 1,
                                         "children": {}
                                     }
                                 }
                             }
                         }
                     }
                 }
             }),
        ([[Frame("method_one"), Frame("method_two"), Frame("method_three"), Frame("method_four")],
          [Frame("method_one"), Frame("method_two"), Frame("method_three"), Frame("method_four")]], {
             "count": 0,
             "children": {
                 "method_one": {
                     "count": 0,
                     "children": {
                         "method_two": {
                             "count": 0,
                             "children": {
                                 "method_three": {
                                     "count": 0,
                                     "children": {
                                         "method_four": {
                                             "count": 2,
                                             "children": {}
                                         }
                                     }
                                 }
                             }
                         }
                     }
                 }
             }
         }),
        ([[Frame("method_one"), Frame("method_two"), Frame("method_three")],
          [Frame("method_one"), Frame("method_two")]], {
             "count": 0,
             "children": {
                 "method_one": {
                     "count": 0,
                     "children": {
                         "method_two": {
                             "count": 1,
                             "children": {
                                 "method_three": {
                                     "count": 1,
                                     "children": {}
                                 }
                             }
                         }
                     }
                 }
             }
         }),
        ([[Frame("method_one", file_path="path/file1.py"), Frame("method_two", file_path="path/file2.py"),
           Frame("method_three", file_path="path/file3.py")],
          [Frame("method_one", file_path="path/file1.py"), Frame("method_two", file_path="path/file2.py")]], {
             "count": 0,
             "children": {
                 "method_one": {
                     "count": 0,
                     "children": {
                         "method_two": {
                             "count": 1,
                             "children": {
                                 "method_three": {
                                     "count": 1,
                                     "children": {},
                                     "file": "path/file3.py"
                                 }
                             },
                             "file": "path/file2.py"
                         }
                     },
                     "file": "path/file1.py"
                 }
             }
         }),
        # The following test case is for testing that line_no is correctly written to the profile; it covers
        # when line_no points to a specific line or to a range of lines represented in a list
        ([[Frame("method_one", file_path="path/file1.py", line_no=1),
           Frame("method_two", file_path="path/file2.py", line_no=10),
           Frame("method_three", file_path="path/file3.py", line_no=100)],
          [Frame("method_one", file_path="path/file1.py", line_no=1),
           Frame("method_two", file_path="path/file2.py", line_no=20),
           Frame("method_three", file_path="path/file3.py", line_no=90)]], {
             "count": 0,
             "children": {
                 "method_one": {
                     "count": 0,
                     "children": {
                         "method_two": {
                             "count": 0,
                             "children": {
                                 "method_three": {
                                     "count": 2,
                                     "children": {},
                                     "file": "path/file3.py",
                                     "line": [90, 100]
                                 }
                             },
                             "file": "path/file2.py",
                             "line": [10, 20]
                         }
                     },
                     "file": "path/file1.py",
                     "line": [1]
                 }
             }
         }),
        # The following test case is for testing that class_name is correctly written to the profile; it covers
        # the cases when frame name/ file_path are the same when the class_name is different; frame_name/ file_path
        # are different when the class_name is the same
        ([[Frame("method_one", file_path="path/file1.py", class_name="ClassA"),
           Frame("method_two", file_path="path/file2.py", class_name="ClassB")],
          [Frame("method_one", file_path="path/file1.py", class_name="ClassA"),
           Frame("method_two", file_path="path/file2.py", class_name="AnotherClassB")],
          [Frame("another_method_one", file_path="path/file1.py", class_name="ClassA")],
          [Frame("method_one", file_path="path/another_file1.py", class_name="ClassA")]], {
             "count": 0,
             "children": {
                 "method_one": {
                     "count": 0,
                     "children": {
                         "method_two": {
                             "count": 1,
                             "children": {},
                             "file": "path/file2.py",
                             "class_name": "ClassB"
                         },
                         "method_two": {
                             "count": 1,
                             "children": {},
                             "file": "path/file2.py",
                             "class_name": "AnotherClassB"
                         }
                     },
                     "file": "path/file1.py",
                     "class_name": "ClassA"
                 },
                 "another_method_one": {
                     "count": 1,
                     "children": {},
                     "file": "path/file1.py",
                     "class_name": "ClassA"
                 },
                 "method_one": {
                     "count": 1,
                     "children": {},
                     "file": "path/another_file1.py",
                     "class_name": "ClassA"
                 }
             }
         })
    ])
    def test_add_stack(self, stacks, expected):
        sample = Sample(stacks=stacks)

        self.subject.add(sample)

        assert (_convert_profile_into_dict(self.subject) == expected)

    def test_it_keeps_the_total_sum_of_the_attempted_sample_threads_count_values(
            self):
        sample1 = Sample(stacks=[[Frame("frame1")]], attempted_sample_threads_count=12)
        sample2 = Sample(stacks=[[Frame("frame1")]], attempted_sample_threads_count=34)

        self.subject.add(sample1)
        self.subject.add(sample2)

        assert (self.subject.total_attempted_sample_threads_count == (
                12 + 34))

    def test_it_keeps_the_total_sum_of_the_seen_threads_count_values(self):
        sample1 = Sample(stacks=[[Frame("frame1")]], seen_threads_count=56)
        sample2 = Sample(stacks=[[Frame("frame1")]], seen_threads_count=78)

        self.subject.add(sample1)
        self.subject.add(sample2)

        assert (self.subject.total_seen_threads_count == (56 + 78))


class TestStartTime(TestProfile):
    @before
    def before(self):
        super().before()

    def test_it_stores_valid_start_time(self):
        assert self.subject.start == self.test_start_time

    def test_it_raise_exception_for_invalid_start_time(self):
        with pytest.raises(ValueError):
            Profile(profiling_group_name="foo", sampling_interval_seconds=1.0, host_weight=2, start=0)
        with pytest.raises(ValueError):
            Profile(profiling_group_name="foo", sampling_interval_seconds=1.0, host_weight=2, start=-100)
        with pytest.raises(TypeError):
            Profile(profiling_group_name="foo", sampling_interval_seconds=1.0, host_weight=2, start=None)


class TestEndTime(TestProfile):
    @before
    def before(self):
        super().before()

    def test_it_sets_valid_end_time(self):
        test_end_time = self.test_start_time + 1
        self.subject.end = test_end_time
        assert self.subject.end == test_end_time

    def test_it_sets_invalid_end_time(self):
        test_end_time = self.test_start_time - 1
        with pytest.raises(ValueError):
            self.subject.end = test_end_time
        with pytest.raises(TypeError):
            self.subject.end = None


class TestPause(TestProfile):
    @before
    def before(self):
        super().before()

    def test_it_sets_last_resume_to_none(self):
        assert self.subject.last_resume is not None
        self.subject.pause()
        assert self.subject.last_resume is None
        assert self.subject.last_pause is not None

    def test_when_last_pause_is_not_none_it_returns(self):
        self.subject.last_pause = self.test_start_time
        self.subject.pause()

    def test_when_last_pause_is_not_none_it_does_not_update_last_pause(self):
        assert self.subject.last_pause is None
        self.subject.last_pause = self.test_start_time
        self.turn_clock(seconds=1)
        self.subject.pause()
        assert self.subject.last_pause == self.test_start_time


class TestResume(TestProfile):
    @before
    def before(self):
        super().before()

    def test_it_sets_last_resume(self):
        self.turn_clock(seconds=1)
        self.subject.pause()
        assert self.subject.last_resume is None
        self.turn_clock(seconds=1)
        self.subject.resume()
        assert self.subject.last_resume == self.test_start_time + 2000
        assert self.subject.last_pause is None


class TestWhenLastResumeIsNotNone(TestProfile):
    @before
    def before(self):
        super().before()

    def test_it_returns(self):
        self.subject.resume()

    def test_it_does_not_update_last_resume(self):
        assert self.subject.last_resume == self.test_start_time
        self.subject.resume()
        assert self.subject.last_resume == self.test_start_time


class TestGetActiveMillisSinceStart(TestProfile):
    @before
    def before(self):
        super().before()

    def test_it_return_duration_since_start(self):
        self.turn_clock(seconds=4)
        assert self.subject.get_active_millis_since_start() == 4000


class TestWhenStillPaused(TestProfile):
    @before
    def before(self):
        super().before()
        self.turn_clock(seconds=9)
        self.subject.pause()
        self.turn_clock(seconds=3)

    def test_it_returns_duration_up_to_last_pause_time(self):
        assert self.subject.get_active_millis_since_start() == 9000


class TestWhenPauseAndResumeWereCalled(TestProfile):
    @before
    def before(self):
        super().before()
        self.turn_clock(seconds=9)
        self.subject.pause()
        self.turn_clock(seconds=3)
        self.subject.resume()
        self.turn_clock(seconds=1)

    def test_it_returns_duration_minus_paused_time(self):
        assert self.subject.get_active_millis_since_start() == 10000


class TestWhenEndHasBeenSet(TestProfile):
    @before
    def before(self):
        super().before()
        self.turn_clock(seconds=9)
        self.subject.pause()
        self.turn_clock(seconds=3)
        self.subject.resume()
        self.turn_clock(seconds=5)
        self.subject.end = self.mock_clock() * 1000
        self.turn_clock(seconds=1)  # that extra second should not be included in the duration

    def test_it_returns_duration_up_to_end_time(self):
        assert self.subject.get_active_millis_since_start() == 14000


class TestSetOverhead(TestProfile):
    @before
    def before(self):
        super().before()

    def test_it_overrides_the_overhead_duration(self):
        self.subject.set_overhead_ms(duration_timedelta=datetime.timedelta(seconds=5.0))
        self.subject.set_overhead_ms(duration_timedelta=datetime.timedelta(seconds=37.0))
        assert self.subject.overhead_ms == 37000


class TestInit(TestProfile):
    @before
    def before(self):
        super().before()

    def test_root_node_frame_is_ALL(self):
        assert (self.subject.callgraph.frame_name == "ALL")

    def test_set_metadata_correctly(self):
        assert (self.subject.sampling_interval_ms == 1000)
        assert (isinstance(self.subject.sampling_interval_ms, int))
        assert (self.subject.host_weight == 2)
        assert (isinstance(self.subject.host_weight, int))

    def test_it_initializes_the_total_attempted_sample_threads_count_to_zero(
            self):
        assert (self.subject.total_attempted_sample_threads_count == 0)

    def test_it_initializes_the_total_seen_threads_count_to_zero(self):
        assert (self.subject.total_seen_threads_count == 0)

    def test_when_profile_is_empty_it_returns_1(self):
        assert (self.subject.average_thread_weight() == 1.0)


class TestGetAverageThreadWeight(TestProfile):
    @before
    def before(self):
        super().before()

    def test_it_returns_the_average_thread_weight_for_the_samples_in_the_profile(
            self):
        sample = Sample(stacks=[[Frame("frame1")]], attempted_sample_threads_count=10, seen_threads_count=15)

        self.subject.add(sample)

        assert (self.subject.average_thread_weight() == 1.5)


def _convert_profile_into_dict(profile):
    return _convert_node_into_dict(profile.callgraph)


def _convert_node_into_dict(node):
    node_in_dict = {
        "count": node.runnable_count,
        "children":
            {node.frame_name: _convert_node_into_dict(node) for node in node.children}
    }

    if node.file_path is not None:
        node_in_dict["file"] = node.file_path
    if node.class_name is not None:
        node_in_dict["class_name"] = node.class_name
    if node.start_line is not None:
        if node.start_line == node.end_line:
            node_in_dict["line"] = [node.start_line]
        else:
            node_in_dict["line"] = [node.start_line, node.end_line]

    return node_in_dict
