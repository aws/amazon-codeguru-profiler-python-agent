import datetime
import tempfile
import pytest
import shutil

from mock import MagicMock
from mock import ANY
from pathlib import Path

from codeguru_profiler_agent.file_reporter.file_reporter import FileReporter
from codeguru_profiler_agent.sdk_reporter.profile_encoder import ProfileEncoder


class TestFileReporter:
    class TestReport:
        @pytest.fixture(autouse=True)
        def around(self):
            temporary_directory = tempfile.mkdtemp()
            self.file_prefix = str(
                Path(temporary_directory, "pytest-SkySailPythonAgent-"))

            self.profile_encoder = MagicMock(
                name="profile_encoder", spec=ProfileEncoder)
            self.profile = MagicMock(name="profile")

            self.subject = FileReporter(
                environment={
                    "file_prefix": self.file_prefix,
                    "profile_encoder": self.profile_encoder
                })

            yield

            shutil.rmtree(temporary_directory)

        def report(self):
            return self.subject.report(profile=self.profile)

        def test_it_uses_the_file_prefix_to_create_a_file_name_for_the_profile(
                self):
            assert (self.report().startswith(self.file_prefix))

        def test_it_adds_the_json_file_extension(self):
            assert (self.report().endswith(".json"))

        def test_it_calls_the_profile_encoder_with_the_profile(self):
            self.report()

            self.profile_encoder.encode.assert_called_once_with(
                profile=self.profile, output_stream=ANY)

        def test_it_writes_the_encoded_profile_to_a_file(self):
            self.profile_encoder.encode.side_effect = lambda **args: args["output_stream"].write(b"output-from-encoder")

            output_file = self.report()

            with open(output_file) as output_file_content:
                assert (output_file_content.read() == "output-from-encoder")
