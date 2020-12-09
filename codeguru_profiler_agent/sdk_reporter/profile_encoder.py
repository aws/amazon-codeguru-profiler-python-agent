import json
import gzip
import io
import sys
from functools import lru_cache

GZIP_BALANCED_COMPRESSION_LEVEL = 6
DEFAULT_FRAME_COMPONENT_DELIMITER = ":"


def _get_module_path(file_path, sys_paths):
    """
    We tried to remove the python library root path in order to give a reasonable expression of the module path.
    For example, /tmp/bin/python/site-packages/great_app/simple_expansions/simple_interface.py
    will get turned into great_app.simple_expansions.simple_interface given that the syspath contains
    /tmp/bin/python/site-packages
    """
    module_path = file_path
    for root in sys_paths:
        if root in file_path:
            module_path = file_path.replace(root, "")
            if module_path.startswith("/"):
                module_path = module_path[1:]
            break
    return module_path.rsplit(".", 1)[0].replace("/", ".")


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

        self.InnerProfileEncoder(profile, self._agent_metadata, output_stream, self._module_path_extractor).encode()

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
        def __init__(self, profile, agent_metadata, output_stream, module_path_extractor):
            self._profile = profile
            self._output_stream = output_stream
            self._agent_metadata = agent_metadata
            self._module_path_extractor = module_path_extractor

        def encode(self):
            profile = self._profile
            self._stream_append('{\n  ')
            self._stream_append('"start": {start},\n  '.format(start=int(profile.start)))
            self._stream_append('"end": {end},\n  '.format(end=int(profile.end)))
            self._encode_agent_metadata()
            self._stream_append(',\n  ')
            self._encode_call_graph(profile.callgraph)
            self._stream_append("\n}")

        def _encode_agent_metadata(self):
            profile_duration_seconds = self._profile.get_active_millis_since_start() / 1000.0
            sample_weight = 1.0 if (profile_duration_seconds == 0) else self._profile.total_sample_count / profile_duration_seconds
            average_num_threads = 0.0 if (self._profile.total_sample_count == 0) else (self._profile.total_seen_threads_count / self._profile.total_sample_count)
            self._stream_append(
                '"agentMetadata": {agent_metadata}'.format(
                    agent_metadata=self._agent_metadata.serialize_to_json_string(
                        sample_weight=sample_weight,
                        duration_ms=self._profile.get_active_millis_since_start(),
                        cpu_time_seconds=self._profile.cpu_time_seconds,
                        average_num_threads=average_num_threads,
                        memory_usage_mb=self._convert_to_mb(self._profile.get_memory_usage_bytes()),
                        overhead_ms=self._profile.overhead_ms
                    )
                )
            )

        def _convert_to_mb(self, bytes_to_convert):
            return bytes_to_convert / (1024 * 1024)

        def _encode_call_graph(self, call_graph):
            self._stream_append('"callgraph": ')
            self._encode_node_recursive(call_graph)

        def _convert_line_range(self, node):
            if node.start_line is None:
                return None

            if node.start_line == node.end_line:
                return '"line": [{line_no}]'.format(line_no=node.start_line)
            else:
                return '"line": [{start_line}, {end_line}]'.format(start_line=node.start_line, end_line=node.end_line)

        def _convert_file_path(self, node):
            if node.file_path is None:
                return None
            return '"file": "{file_path}"'.format(file_path=node.file_path)

        def _convert_runnable_count(self, node):
            if node.runnable_count > 0:
                return '"counts": {{"WALL_TIME": {runnable_count}}}'.format(runnable_count=node.runnable_count)
            return None

        def _encode_node_recursive(self, node):
            self._stream_append('{')

            frame_metadata = list(filter(None, [self._convert_runnable_count(node), self._convert_file_path(node),
                                                self._convert_line_range(node)]))
            self._stream_append(','.join(frame_metadata))

            if not node.children:
                self._stream_append('}')
                return node.runnable_count
            else:
                if frame_metadata:
                    self._stream_append(',')
                self._stream_append('"children": {')
                self._encode_children_nodes_recursive(node.children)
                self._stream_append('}}')

        def _encode_children_nodes_recursive(self, children_nodes):
            first_element = True
            for child_node in children_nodes:
                if not first_element:
                    self._stream_append(", ")
                else:
                    first_element = False

                frame = DEFAULT_FRAME_COMPONENT_DELIMITER.join(
                    list(filter(None, [self._module_path_extractor.get_module_path(child_node.file_path),
                                       child_node.class_name, child_node.frame_name])))
                self._stream_append(u'"{node_frame}": '.format(node_frame=frame))
                self._encode_node_recursive(child_node)

        def _stream_append(self, string):
            self._output_stream.write(string.encode("utf-8"))

    # Useful for debugging, converts a profile into a prettified JSON output
    @staticmethod
    def debug_pretty_encode(profile, environment=dict(), sort_keys=True):
        stream = io.BytesIO()
        ProfileEncoder(gzip=False, environment=environment).encode(profile, stream)
        parsed_json = json.loads(stream.getvalue().decode("utf-8"))
        return json.dumps(parsed_json, indent=2, sort_keys=sort_keys)
