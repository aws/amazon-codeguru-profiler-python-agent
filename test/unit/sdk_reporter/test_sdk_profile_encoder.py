# -*- coding: utf-8 -*-
import platform

import pytest
from unittest.mock import MagicMock

from codeguru_profiler_agent.agent_metadata.agent_debug_info import ErrorsMetadata, AgentDebugInfo
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata
from codeguru_profiler_agent.agent_metadata.aws_ec2_instance import AWSEC2Instance
from codeguru_profiler_agent.model.frame import Frame
from test.pytestutils import before
import json
import io
import gzip
from datetime import timedelta
from pathlib import Path

from codeguru_profiler_agent.metrics.timer import Timer
from codeguru_profiler_agent.model.profile import Profile
from codeguru_profiler_agent.model.sample import Sample
from codeguru_profiler_agent.sdk_reporter.profile_encoder import ProfileEncoder


def example_profile():
    start_time = 1514764800000
    end_time = 1514772000000
    profile = Profile(profiling_group_name="TestProfilingGroupName", sampling_interval_seconds=1.0, host_weight=2,
                      start=start_time, agent_debug_info=AgentDebugInfo(errors_metadata), clock=lambda: 1514772000000)
    profile.add(
        Sample(stacks=[[Frame("bottom"), Frame("middle"), Frame("top")],
                       [Frame("bottom"), Frame("middle"), Frame("different_top")],
                       [Frame("bottom"), Frame("middle")]], attempted_sample_threads_count=10, seen_threads_count=15))
    profile.end = end_time
    profile.set_overhead_ms(timedelta(milliseconds=256))
    if platform.system() == "Windows":
        # In Windows, as time.process stays constant if no cpu time was used (https://bugs.python.org/issue37859), we
        # would need to manually override the cpu_time_seconds to ensure the test runs as expected
        profile.cpu_time_seconds = 0.123
    return profile


agent_metadata = AgentMetadata(
    fleet_info=AWSEC2Instance(host_name="testHostName", host_type="testHostType")
)
errors_metadata = ErrorsMetadata()

environment = {
    "timer": Timer(),
    "agent_metadata": agent_metadata,
    "errors_metadata": errors_metadata
}


class TestSdkProfileEncoder:
    def before(self):
        self.profile = example_profile()
        self.output_stream = io.BytesIO()
        self.subject = \
            ProfileEncoder(gzip=False, environment=environment)
        self.decoded_json_result = self.decoded_json_result.__get__(self)
        self._decoded_json_result = None

    def decoded_json_result(self):
        if not self._decoded_json_result:
            self.subject.encode(
                profile=self.profile, output_stream=self.output_stream)
            self._decoded_json_result = json.loads(
                self.output_stream.getvalue().decode("utf-8"))
        return self._decoded_json_result


class TestEncode(TestSdkProfileEncoder):
    @before
    def before(self):
        super().before()

    def test_it_encodes_the_result_as_a_json_file(self):
        assert (type(self.decoded_json_result()) is dict)


class TestInsideTheResult(TestSdkProfileEncoder):
    @before
    def before(self):
        super().before()

    def test_it_includes_the_start_time_from_the_profile_in_epoch_millis(
            self):
        assert (self.decoded_json_result()["start"] == 1514764800000)

    def test_it_includes_the_end_time_from_the_profile_in_epoch_millis(
            self):
        assert (self.decoded_json_result()["end"] == 1514772000000)

    def test_it_includes_the_agent_info_in_the_agent_metadata(self):
        assert (self.decoded_json_result()["agentMetadata"]["agentInfo"]["type"] ==
                agent_metadata.agent_info.agent_type)
        assert (self.decoded_json_result()["agentMetadata"]["agentInfo"]["version"] ==
                agent_metadata.agent_info.version)

    def test_it_includes_the_runtime_version_in_the_agent_metadata(self):
        assert (self.decoded_json_result()["agentMetadata"]["runtimeVersion"] ==
                agent_metadata.runtime_version)

    def test_it_includes_the_fleet_info_in_the_agent_metadata(self):
        assert (self.decoded_json_result()["agentMetadata"]["fleetInfo"] ==
                agent_metadata.fleet_info.serialize_to_map())

    def test_it_includes_the_sample_weight_in_the_agent_metadata(self):
        # Given the example profile, sample_weight = 1 / (1514772000000 - 1514764800000) = ~0.00013888
        assert (0.000138 < self.decoded_json_result()["agentMetadata"]["sampleWeights"]["WALL_TIME"] < 0.000139)

    def test_it_includes_profile_duration_in_the_agent_metadata(self):
        assert (self.decoded_json_result()["agentMetadata"]["durationInMs"] == 7200000)

    def test_it_includes_the_cpu_time_in_the_agent_metadata(self):
        assert (self.decoded_json_result()["agentMetadata"]["cpuTimeInSeconds"] > 0)

    def test_it_includes_the_num_threads_in_the_agent_metadata(self):
        assert (self.decoded_json_result()["agentMetadata"]["metrics"]["numThreads"] == 15)

    def test_it_includes_the_overhead_ms_in_the_agent_metadata(self):
        assert (self.decoded_json_result()["agentMetadata"]["agentOverhead"]["timeInMs"] == 256)

    def test_it_includes_the_memory_overhead_in_the_agent_metadata(self):
        assert (self.decoded_json_result()["agentMetadata"]["agentOverhead"]["memory_usage_mb"] > 0)

    def test_it_includes_the_num_times_sampled_in_the_agent_metadata(self):
        assert (self.decoded_json_result()["agentMetadata"]["numTimesSampled"] > 0)

    def test_it_handles_unicode_frames_correctly(self):
        self.profile.add(
            Sample(stacks=[[Frame("unicode_bottom"), Frame(u"😉"), Frame(u"🙃")]]))

        assert (self.decoded_json_result()["callgraph"]["children"][
                    "unicode_bottom"] == {
                    "children": {
                        u"😉": {
                            "children": {
                                u"🙃": {
                                    "counts": {
                                        "WALL_TIME": 1
                                    }
                                }
                            }
                        }
                    }
                })

    @pytest.mark.skipif(platform.system() != "Windows", reason="This test should only be run on Windows")
    def test_it_handles_unicode_escape_correctly_on_Windows(self):
            self.profile.add(
                Sample(stacks=[[Frame("bottom_with_path"),
                                Frame("middle", file_path="C:/User/ironman/path/xs.py", class_name="ClassA"),
                                Frame("top", file_path="C:\\User\\ironman\\path\\xs.py", class_name="ClassA")]])
            )

            assert (self.decoded_json_result()["callgraph"]["children"]["bottom_with_path"] ==
                    {
                        "children": {
                            "User.ironman.path.xs:ClassA:middle": {
                                "children": {
                                    "User.ironman.path.xs:ClassA:top": {
                                        "file": "C:\\User\\ironman\\path\\xs.py",
                                        "counts": {
                                            "WALL_TIME": 1
                                        }
                                    }
                                },
                                "file": "C:\\User\\ironman\\path\\xs.py"
                            }
                        }
                    })

    @pytest.mark.skipif(platform.system() == "Windows", reason="This test should not be run on Windows")
    def test_it_handles_unicode_escape_correctly_on_non_Windows_system(self):
        self.profile.add(
            Sample(stacks=[[Frame("bottom_with_path"),
                            Frame("top", file_path="C:\\User\\ironman\\path\\xs.py", class_name="ClassA")]])
        )

        assert (self.decoded_json_result()["callgraph"]["children"]["bottom_with_path"] ==
                {
                    "children": {
                        "C:\\User\\ironman\\path\\xs:ClassA:top": {
                            'file': 'C:\\User\\ironman\\path\\xs.py',
                            "counts": {
                                "WALL_TIME": 1
                            }
                        }
                    }
                })

    @pytest.mark.skipif(platform.system() == "Windows", reason="This test should not be run on Windows")
    def test_it_includes_correct_file_path_when_available_on_non_Windows_system(self):
        self.profile.add(
            Sample(stacks=[[Frame("bottom_with_path", file_path="path/file1.py"),
                            Frame("middle_with_path", file_path="path/file2.py"),
                            Frame("top_without_path")]]))

        assert (self.decoded_json_result()["callgraph"]["children"]["path.file1:bottom_with_path"] ==
                {
                    "children": {
                        "path.file2:middle_with_path": {
                            "children": {
                                "top_without_path": {
                                    "counts": {
                                        "WALL_TIME": 1
                                    }
                                }
                            },
                            'file': 'path/file2.py'
                        }
                    },
                    'file': 'path/file1.py'
                })

    @pytest.mark.skipif(platform.system() != "Windows", reason="This test should not be run on Windows")
    def test_it_includes_correct_file_path_when_available_on_Windows(self):
        self.profile.add(
            Sample(stacks=[[Frame("bottom_with_path", file_path="path/file1.py"),
                            Frame("middle_with_path", file_path="path/file2.py"),
                            Frame("top_without_path")]]))

        assert (self.decoded_json_result()["callgraph"]["children"]["path.file1:bottom_with_path"] ==
                {
                    "children": {
                        "path.file2:middle_with_path": {
                            "children": {
                                "top_without_path": {
                                    "counts": {
                                        "WALL_TIME": 1
                                    }
                                }
                            },
                            'file': 'path\\file2.py'
                        }
                    },
                    'file': 'path\\file1.py'
                })

    def test_it_includes_class_name_when_available(self):
        self.profile.add(
            Sample(stacks=[[Frame("bottom_with_path", class_name="ClassA"),
                            Frame("middle_with_path", class_name="ClassB"),
                            Frame("top_without_path")]]))

        assert (self.decoded_json_result()["callgraph"]["children"]["ClassA:bottom_with_path"] ==
                {
                    "children": {
                        "ClassB:middle_with_path": {
                            "children": {
                                "top_without_path": {
                                    "counts": {
                                        "WALL_TIME": 1
                                    }
                                }
                            }
                        }
                    }
                })

    def test_it_includes_line_when_available(self):
        self.profile.add(
            Sample(stacks=[[Frame("bottom_with_line_no", line_no=123),
                            Frame("middle_with_line_no", line_no=234),
                            Frame("top_without_line_no")],
                           [Frame("bottom_with_line_no", line_no=123),
                            Frame("middle_with_line_no", line_no=345),
                            Frame("top_without_line_no")]
                           ]))

        assert (self.decoded_json_result()["callgraph"]["children"]["bottom_with_line_no"] ==
                {
                    "children": {
                        "middle_with_line_no": {
                            "children": {
                                "top_without_line_no": {
                                    "counts": {
                                        "WALL_TIME": 2
                                    }
                                }
                            },
                            "line": [234, 345]
                        }
                    },
                    "line": [123]
                })

    def test_it_includes_the_call_graph_in_self_time_mode(self):
        assert (self.decoded_json_result()["callgraph"] == {
            "children": {
                "bottom": {
                    "children": {
                        "middle": {
                            "counts": {
                                "WALL_TIME": 1
                            },
                            "children": {
                                "top": {
                                    "counts": {
                                        "WALL_TIME": 1
                                    }
                                },
                                "different_top": {
                                    "counts": {
                                        "WALL_TIME": 1
                                    }
                                }
                            }
                        }
                    }
                }
            }
        })


class TestWhenGzippingIsEnabled(TestSdkProfileEncoder):
    @before
    def before(self):
        super().before()

    def test_it_gzips_the_result_before_writing_to_the_stream(self):
        ProfileEncoder(gzip=True, environment=environment).encode(
            profile=self.profile, output_stream=self.output_stream)

        self.output_stream.seek(0)
        uncompressed_result = gzip.GzipFile(
            fileobj=self.output_stream, mode="rb").read()

        assert (len(uncompressed_result) > 0)


class TestModulePathExtractorWithCurrentPath:
    @before
    def before(self):
        self.current_path = str(Path().absolute())
        self.subject = ProfileEncoder(gzip=False, environment=environment).ModulePathExtractor(sys_path=[])

    def test_it_removes_current_path(self):
        file_path = self.current_path + '/polls/views.py'
        assert self.subject.get_module_path(file_path) == "polls.views"

    def test_it_removes_current_path_and_slash_and_dot(self):
        file_path = self.current_path + '/./polls/views.py'
        assert self.subject.get_module_path(file_path) == "polls.views"

    def test_it_does_nothing_when_file_path_has_no_current_path(self):
        file_path ='/polls/views.py'
        assert self.subject.get_module_path(file_path) == "polls.views"


class TestModulePathExtractor:
    @before
    def before(self):
        self.subject = ProfileEncoder(gzip=False, environment=environment).ModulePathExtractor(
            sys_path=["/tmp/TestPythonAgent/site-package/", "\\tmp\\TestPythonAgent\\site-package\\"])

    def test_it_removes_root_path(self):
        assert self.subject \
                   .get_module_path("/tmp/TestPythonAgent/site-package/DummyPackage/dummy") == \
               "DummyPackage.dummy"

    def test_it_returns_same_path_if_no_match_from_sys_paths(self):
        assert self.subject \
                   .get_module_path("this/is/clearly/not/in/sys/path/dummy.py") == \
               "this.is.clearly.not.in.sys.path.dummy"

    def test_it_removes_longest_root_path_matched_from_sys_path(self):
        subject = ProfileEncoder(gzip=False, environment=environment).ModulePathExtractor(
            sys_path=["/tmp/TestPythonAgent/site-package/", "/tmp/TestPythonAgent/site-package/threading/",
                      "\\tmp\\TestPythonAgent\\site-package\\", "\\tmp\\TestPythonAgent\\site-package\\threading\\"])

        assert subject.get_module_path("/tmp/TestPythonAgent/site-package/threading/DummyPackage/dummy") == \
               "DummyPackage.dummy"

    def test_it_caches_result(self):
        self.dummy_module_extract = MagicMock("dummy_module_extractor")
        self.subject = ProfileEncoder(gzip=False, environment=environment).ModulePathExtractor(
            sys_path=["/tmp/TestPythonAgent/site-package/"], extractor_fun=self.dummy_module_extract)

        some_path = "/tmp/TestPythonAgent/site-package/DummyPackage/dummy.py"
        self.subject.get_module_path(some_path)
        self.subject.get_module_path(some_path)

        self.dummy_module_extract.assert_called_once_with(
            "/tmp/TestPythonAgent/site-package/DummyPackage/dummy.py",
            ["/tmp/TestPythonAgent/site-package/"]
        )

    def test_debug_pretty_encode_it_returns_a_json_representation_for_a_profile(self):
        result = ProfileEncoder.debug_pretty_encode(profile=example_profile(), environment=environment)

        assert (json.loads(result)["start"] == 1514764800000)
