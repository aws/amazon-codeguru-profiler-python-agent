import json
import gzip
import io
import platform
import sys
from functools import lru_cache
import os
from pathlib import Path

GZIP_BALANCED_COMPRESSION_LEVEL = 6
DEFAULT_FRAME_COMPONENT_DELIMITER = ":"

def _get_module_path(file_path, sys_paths):
    """
    We tried to remove the python library root path in order to give a reasonable expression of the module path.
    For example, /tmp/bin/python/site-packages/great_app/simple_expansions/simple_interface.py
    will get turned into great_app.simple_expansions.simple_interface given that the syspath contains
    /tmp/bin/python/site-packages

    We are making sure we're removing the current path for this special usecase, by checking if it contains "/./".
    For example, '/Users/mirelap/Documents/workspace/JSON/aws-codeguru-profiler-python-demo-application/sample-demo-django-app/./polls/views.py'
    will get turned into `polls.views' given that the file path contains the current path.
    This should not happen usually, but we've found a case where the "/." is added when calling traceback.walk_stack(..)
    in a uwsgi application. Check sampling_utils.py file for details.

    sampling_utils.py returns different values when calling traceback.walk_stack(..) for uwsgi vs non-uwsgi
    for Python 3.8.10-Python 3.9.2.
    Examples of results:
    - file '/Users/mirelap/Documents/workspace/JSON/aws-codeguru-profiler-python-demo-application/sample-demo-django-app/./polls/views.py', line 104, code get_queryset>, 104
    - file '/Users/mirelap/Documents/workspace/JSON/aws-codeguru-profiler-python-demo-application/sample-demo-django-app/polls/views.py', line 104, code get_queryset>, 104
    """
    module_path = file_path

    if platform.system() == "Windows":
        # In Windows, separator can either be / or \ from experimental result
        module_path = module_path.replace("/", os.sep)

    # remove prefix path
    module_path = _remove_prefix_path(module_path, sys_paths)

    # remove suffix
    module_path = str(Path(module_path).with_suffix(""))

    # remove drive (applicable for WINDOWS customers)
    module_path = os.path.splitdrive(module_path)[1]

    module_path = module_path.replace(os.sep, ".")

    if module_path.startswith("."):
        module_path = module_path[1:]

    return module_path


def _remove_prefix_path(module_path, sys_paths):
    if "/./" in module_path and platform.system() != "Windows":
        module_path = module_path.replace("/./", "/")
        current_path = str(Path().absolute())
        if current_path != "/": # this may be Fargate
            return module_path.replace(current_path, "")
        return module_path

    for root in sys_paths:
        if root in module_path:
            return module_path.replace(root, "")

    return module_path

class ProfileEncoder:
    """
    Encodes a given Profile into the JSON version of the ion-based profile format

    For efficiency, this encoder:
    * compresses the output as gzip, thus reducing the size of the final result
    * writes the output incrementally to a stream, thus reduces the footprint of the conversion
    * implements its own json writer:
        * enables the incremental stream-based output
        * decouples our in-memory implementation from the current ion format
    """

    def __init__(self, environment=dict(), gzip=True):
        self._gzip = gzip
        self._agent_metadata = environment["agent_metadata"]
        self._module_path_extractor = self.ModulePathExtractor(environment.get("sys_path") or sys.path)

    def encode(self, profile, output_stream):
        if self._gzip:
            output_stream = self._gzip_stream_from(output_stream)

        output_stream.write(
            self.InnerProfileEncoder(profile, self._agent_metadata, self._module_path_extractor)
                .encode_content().encode("utf-8")
        )

        if self._gzip:
            output_stream.close()

    def _gzip_stream_from(self, stream):
        return gzip.GzipFile(
            fileobj=stream,
            mode="wb",
            compresslevel=GZIP_BALANCED_COMPRESSION_LEVEL)

    class ModulePathExtractor:
        def __init__(self, sys_path=[], extractor_fun=_get_module_path):
            self._sys_path = sorted(sys_path, key=len, reverse=True)
            self._extractor_fun = extractor_fun

        @lru_cache(maxsize=128)
        def get_module_path(self, file_path):
            if file_path is None:
                return None
            return self._extractor_fun(file_path, self._sys_path)

    class InnerProfileEncoder:
        def __init__(self, profile, agent_metadata, module_path_extractor):
            self._profile = profile
            self._agent_metadata = agent_metadata
            self._module_path_extractor = module_path_extractor

        def encode_content(self):
            profile_in_map = {
                "start": int(self._profile.start),
                "end": int(self._profile.end),
                "agentMetadata": self._encode_agent_metadata(),
                "callgraph": self._encode_call_graph(self._profile.callgraph),
                "debugInfo": self._encode_debug_info()
            }

            return json.dumps(profile_in_map)

        def _encode_debug_info(self):
            return self._profile.serialize_agent_debug_info_to_json()

        def _encode_agent_metadata(self):
            profile_duration_seconds = self._profile.get_active_millis_since_start() / 1000.0
            sample_weight = 1.0 if (profile_duration_seconds == 0) else self._profile.total_sample_count / profile_duration_seconds
            average_num_threads = 0.0 if (self._profile.total_sample_count == 0) else (self._profile.total_seen_threads_count / self._profile.total_sample_count)

            return self._agent_metadata.serialize_to_json(
                        sample_weight=sample_weight,
                        duration_ms=self._profile.get_active_millis_since_start(),
                        cpu_time_seconds=self._profile.cpu_time_seconds,
                        average_num_threads=average_num_threads,
                        memory_usage_mb=self._convert_to_mb(self._profile.get_memory_usage_bytes()),
                        overhead_ms=self._profile.overhead_ms,
                        total_sample_count = self._profile.total_sample_count
            )

        def _convert_to_mb(self, bytes_to_convert):
            return bytes_to_convert / (1024 * 1024)

        def _encode_call_graph(self, call_graph):
            return self._encode_node_recursive(call_graph)

        def _convert_line_range(self, node):
            if node.start_line is None:
                return None

            if node.start_line == node.end_line:
                return {
                    "line": [node.start_line]
                }
            else:
                return {
                    "line": [node.start_line, node.end_line]
                }

        def _convert_file_path(self, node):
            if node.file_path is None:
                return None
            if platform.system() == "Windows":
                # In Windows, separator can either be / or \ from experimental result
                file_path = node.file_path.replace("/", os.sep)
            else:
                file_path = node.file_path
            return {
                "file": file_path
            }

        def _convert_runnable_count(self, node):
            if node.runnable_count > 0:
                return {
                    "counts": {
                        "WALL_TIME": node.runnable_count
                    }
                }
            return None

        def _encode_node_recursive(self, node):
            node_map = {}
            runnable_count_map = self._convert_runnable_count(node)
            if runnable_count_map:
                node_map.update(runnable_count_map)
            file_path_map = self._convert_file_path(node)
            if file_path_map:
                node_map.update(file_path_map)
            line_range_map = self._convert_line_range(node)
            if line_range_map:
                node_map.update(line_range_map)

            if node.children:
                node_map["children"] = self._encode_children_nodes_recursive(node.children)

            return node_map

        def _encode_children_nodes_recursive(self, children_nodes):
            node_map = {}
            for child_node in children_nodes:
                frame = DEFAULT_FRAME_COMPONENT_DELIMITER.join(
                    list(filter(None, [self._module_path_extractor.get_module_path(child_node.file_path),
                                       child_node.class_name, child_node.frame_name])))
                child_node_map = self._encode_node_recursive(child_node)
                node_map[frame] = child_node_map

            return node_map

    # Useful for debugging, converts a profile into a prettified JSON output
    @staticmethod
    def debug_pretty_encode(profile, environment=dict(), sort_keys=True):
        stream = io.BytesIO()
        ProfileEncoder(gzip=False, environment=environment).encode(profile, stream)
        parsed_json = json.loads(stream.getvalue().decode("utf-8"))
        return json.dumps(parsed_json, indent=2, sort_keys=sort_keys)
