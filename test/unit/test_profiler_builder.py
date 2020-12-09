import os
import datetime
from unittest.mock import MagicMock, ANY
import boto3
import pytest
from codeguru_profiler_agent import Profiler
from test.pytestutils import before
from codeguru_profiler_agent.profiler_builder import \
    build_profiler, PG_NAME_ENV, PG_ARN_ENV, ENABLED_ENV, REGION_ENV, CREDENTIAL_PATH


class TestProfilerBuilder:
    class TestWhenProfilingGroupNameParameterIsProvided:
        @before
        def before(self):
            self.pg_name = "my_profiling_group"
            self.profiler_factory = MagicMock(spec=Profiler)
            self.subject = build_profiler(pg_name=self.pg_name, env={},
                                          profiler_factory=self.profiler_factory)

        def test_it_creates_a_profiler(self):
            assert self.subject is not None

        def test_it_uses_correct_name(self):
            self.profiler_factory.assert_called_once_with(profiling_group_name=self.pg_name, region_name=ANY,
                                                          aws_session=ANY, environment_override=ANY)

    class TestWhenProfilingGroupNameIsInEnvironment:
        @before
        def before(self):
            self.pg_name = "my_profiling_group"
            self.profiler_factory = MagicMock(spec=Profiler)
            self.env = {PG_NAME_ENV: self.pg_name}
            self.subject = build_profiler(env=self.env, profiler_factory=self.profiler_factory)

        def test_it_creates_a_profiler(self):
            assert self.subject is not None

        def test_it_uses_correct_name(self):
            self.profiler_factory.assert_called_once_with(profiling_group_name=self.pg_name, region_name=ANY,
                                                          aws_session=ANY, environment_override=ANY)

    class TestWhenProfilingGroupNameIsMissing:
        def test_it_returns_none(self):
            assert build_profiler(env={}) is None

    class TestWhenRegionNameParameterIsProvided:
        @before
        def before(self):
            self.region = "eu-north-1"
            self.profiler_factory = MagicMock(spec=Profiler)
            self.subject = build_profiler(pg_name="my_profiling_group", region_name=self.region,
                                          env={}, profiler_factory=self.profiler_factory)

        def test_it_creates_a_profiler(self):
            assert self.subject is not None

        def test_it_uses_correct_region(self):
            self.profiler_factory.assert_called_once_with(profiling_group_name=ANY, region_name=self.region,
                                                          aws_session=ANY, environment_override=ANY)

    class TestWhenCredentialProfileIsProvided:
        @before
        def before(self):
            self.credential_profile = "test-profile"
            self.mock_session = MagicMock(name="profiler", spec=boto3.session.Session)
            self.subject = build_profiler(pg_name="my_profiling_group", credential_profile=self.credential_profile,
                                          env={}, session_factory=self.mock_session)

        def test_it_creates_a_profiler(self):
            assert self.subject is not None

        def test_it_uses_correct_credential_profile(self):
            self.mock_session.assert_called_once_with(region_name=ANY, profile_name=self.credential_profile)

    class TestWhenCredentialProfileIsInEnvironment:
        @pytest.fixture(autouse=True)
        def around(self):
            self.credential_profile = "test-profile"
            previous_credential_value = os.environ.get(CREDENTIAL_PATH)
            os.environ[CREDENTIAL_PATH] = self.credential_profile
            self.mock_session = MagicMock(name="profiler", spec=boto3.session.Session)
            self.subject = build_profiler(pg_name="my_profiling_group", env={}, session_factory=self.mock_session)
            yield
            if previous_credential_value is not None:
                os.environ[CREDENTIAL_PATH] = previous_credential_value
            else:
                del os.environ[CREDENTIAL_PATH]

        def test_it_creates_a_profiler(self):
            assert self.subject is not None

        def test_it_ignores_credential_profile_set_in_env(self):
            self.mock_session.assert_called_once_with(region_name=ANY, profile_name=None)

    class TestWhenProfilingGroupArnIsInEnvironment:
        @before
        def before(self):
            self.env = {PG_ARN_ENV: 'arn:aws:codeguru-profiler:us-west-2:003713371902:profilingGroup/name_from_arn'}

        def test_it_creates_a_profiler(self):
            assert build_profiler(env=self.env) is not None

        def test_it_uses_correct_name(self):
            assert build_profiler(env=self.env) \
                       ._profiler_runner.collector.reporter.profiling_group_name == 'name_from_arn'

        def test_it_uses_correct_region(self):
            assert 'us-west-2' in build_profiler(env=self.env) \
                ._profiler_runner.collector.reporter.codeguru_client_builder.codeguru_client._endpoint.host

        class TestWhenRegionIsAlsoProvided:
            @before
            def before(self):
                self.env[REGION_ENV] = 'eu-north-1'

            def test_it_uses_region_from_arn(self):
                assert 'us-west-2' in build_profiler(env=self.env) \
                    ._profiler_runner.collector.reporter.codeguru_client_builder.codeguru_client._endpoint.host

        class TestWhenProfilingGroupNameIsAlsoProvided:
            @before
            def before(self):
                self.env[PG_NAME_ENV] = 'different_name_here'

            def test_it_uses_name_from_arn(self):
                assert build_profiler(env=self.env) \
                           ._profiler_runner.collector.reporter.profiling_group_name == 'name_from_arn'

    class TestWhenProfilingGroupArnIsMalformed:
        @before
        def before(self):
            self.env = {PG_ARN_ENV: 'this_arn_is_definitely_not_correct',
                        PG_NAME_ENV: 'but_this_name_should_do',
                        REGION_ENV: 'eu-north-1'}

        def test_it_creates_profiler_using_the_name(self):
            assert build_profiler(env=self.env) \
                       ._profiler_runner.collector.reporter.profiling_group_name == 'but_this_name_should_do'

        def test_it_creates_profiler_using_the_region_from_env(self):
            assert 'eu-north-1' in build_profiler(env=self.env) \
                    ._profiler_runner.collector.reporter.codeguru_client_builder.codeguru_client._endpoint.host

    class TestWhenRegionNameIsInEnvironment:
        @before
        def before(self):
            self.region = "eu-north-1"
            self.env = {REGION_ENV: self.region}
            self.profiler_factory = MagicMock(spec=Profiler)
            self.subject = build_profiler(pg_name="my_profiling_group", env=self.env,
                                          profiler_factory=self.profiler_factory)

        def test_it_creates_a_profiler(self):
            assert self.subject is not None

        def test_it_uses_correct_region(self):
            self.profiler_factory.assert_called_once_with(profiling_group_name=ANY, region_name=self.region,
                                                          aws_session=ANY, environment_override=ANY)

    class TestWhenSamplingIntervalIsInEnvironment:
        @before
        def before(self):
            self.env = {"AWS_CODEGURU_PROFILER_SAMPLING_INTERVAL_MS": "100"}
            self.profiler_factory = MagicMock(spec=Profiler)
            self.subject = build_profiler(pg_name="my_profiling_group", env=self.env,
                                          profiler_factory=self.profiler_factory)

        def test_it_uses_correct_sampling_interval(self):
            self.profiler_factory.assert_called_once_with(profiling_group_name=ANY, region_name=ANY, aws_session=ANY,
                                                          environment_override={"sampling_interval": datetime.timedelta(
                                                              milliseconds=100)})

    class TestWhenReportingIntervalIsInEnvironment:
        @before
        def before(self):
            self.env = {"AWS_CODEGURU_PROFILER_REPORTING_INTERVAL_MS": "60000"}
            self.profiler_factory = MagicMock(spec=Profiler)
            self.subject = build_profiler(pg_name="my_profiling_group", env=self.env,
                                          profiler_factory=self.profiler_factory)

        def test_it_uses_correct_sampling_interval(self):
            self.profiler_factory.assert_called_once_with(profiling_group_name=ANY, region_name=ANY, aws_session=ANY,
                                            environment_override={"reporting_interval": datetime.timedelta(seconds=60)})

    class TestWhenMalformedReportingIntervalIsInEnvironment:
        @before
        def before(self):
            self.env = {"AWS_CODEGURU_PROFILER_REPORTING_INTERVAL_MS": "12.5"}
            self.profiler_factory = MagicMock(spec=Profiler)
            self.subject = build_profiler(pg_name="my_profiling_group", env=self.env,
                                          profiler_factory=self.profiler_factory)

        def test_it_still_creates_a_profiler(self):
            assert self.subject is not None

    class TestWhenProfilingIsDisabled:
        def test_it_returns_none(self):
            for value in ["False", "false", "0", "Nope", "Yes" "anything"]:
                env = {ENABLED_ENV: value}
                assert build_profiler(pg_name="my_profiling_group", env=env) is None

    class TestWhenProfilingIsEnabled:
        def test_it_builds_the_profiler(self):
            for value in ["True", "true"]:
                env = {ENABLED_ENV: value}
                assert build_profiler(pg_name="my_profiling_group", env=env) is not None

    class TestWhenUnknownExceptionIsThrown:
        def test_it_returns_none(self):
            assert build_profiler(pg_name="my_profiling_group", env="not_a_dictionary") is None
