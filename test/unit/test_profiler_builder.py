import os
import datetime
from unittest.mock import MagicMock, ANY
import boto3
from codeguru_profiler_agent import Profiler
from codeguru_profiler_agent.profiler_builder import \
    build_profiler, PG_NAME_ENV, PG_ARN_ENV, ENABLED_ENV, REGION_ENV, CREDENTIAL_PATH


class TestProfilerBuilder:
    class TestWhenProfilingGroupNameParameterIsProvided:
        def test_it_creates_a_profiler_and_uses_correct_name(self):
            pg_name = "my_profiling_group"
            profiler_factory = MagicMock(spec=Profiler)
            subject = build_profiler(pg_name=pg_name, env={},
                                     profiler_factory=profiler_factory)

            assert subject is not None
            profiler_factory.assert_called_once_with(profiling_group_name=pg_name, region_name=ANY,
                                                     aws_session=ANY, environment_override=ANY)

    class TestWhenProfilingGroupNameIsInEnvironment:
        def test_it_creates_a_profiler_and_uses_correct_name(self):
            pg_name = "my_profiling_group"
            profiler_factory = MagicMock(spec=Profiler)
            env = {PG_NAME_ENV: pg_name}
            subject = build_profiler(env=env, profiler_factory=profiler_factory)

            assert subject is not None
            profiler_factory.assert_called_once_with(profiling_group_name=pg_name, region_name=ANY,
                                                     aws_session=ANY, environment_override=ANY)

    class TestWhenProfilingGroupNameIsMissing:
        def test_it_returns_none(self):
            assert build_profiler(env={}) is None

    class TestWhenRegionNameParameterIsProvided:
        def test_it_creates_a_profiler_and_uses_correct_region(self):
            region = "eu-north-1"
            profiler_factory = MagicMock(spec=Profiler)
            subject = build_profiler(pg_name="my_profiling_group", region_name=region,
                                     env={}, profiler_factory=profiler_factory)
            assert subject is not None
            profiler_factory.assert_called_once_with(profiling_group_name=ANY, region_name=region,
                                                     aws_session=ANY, environment_override=ANY)

    class TestWhenCredentialProfileIsProvided:
        def test_it_creates_a_profile_rand_uses_correct_credential_profile(self):
            credential_profile = "test-profile"
            mock_session = MagicMock(name="profiler", spec=boto3.session.Session)
            subject = build_profiler(pg_name="my_profiling_group", credential_profile=credential_profile,
                                     env={}, session_factory=mock_session)

            assert subject is not None
            mock_session.assert_called_once_with(region_name=ANY, profile_name=credential_profile)

    class TestWhenCredentialProfileIsInEnvironment:
        def test_it_creates_a_profiler_and_it_ignores_credential_profile_set_in_env(self):
            credential_profile = "test-profile"
            previous_credential_value = os.environ.get(CREDENTIAL_PATH)
            os.environ[CREDENTIAL_PATH] = credential_profile
            mock_session = MagicMock(name="profiler", spec=boto3.session.Session)
            subject = build_profiler(pg_name="my_profiling_group", env={}, session_factory=mock_session)
            if previous_credential_value is not None:
                os.environ[CREDENTIAL_PATH] = previous_credential_value
            else:
                del os.environ[CREDENTIAL_PATH]

            assert subject is not None
            mock_session.assert_called_once_with(region_name=ANY, profile_name=None)

    class TestWhenProfilingGroupArnIsInEnvironment:
        def test_it_creates_a_profiler_and_uses_correct_name_and_region(self):
            env = {PG_ARN_ENV: 'arn:aws:codeguru-profiler:us-west-2:003713371902:profilingGroup/name_from_arn'}
            profiler = build_profiler(env=env)
            assert profiler is not None
            assert profiler._profiler_runner.collector.reporter.profiling_group_name == 'name_from_arn'
            assert 'us-west-2' in profiler._profiler_runner.collector.reporter.codeguru_client_builder.codeguru_client._endpoint.host

        def test_it_creates_a_profiler_and_uses_correct_name_and_region(self):
            env = {PG_ARN_ENV: 'arn:aws:codeguru-profiler:us-west-2:003713371902:profilingGroup/name_from_arn',
                   REGION_ENV: 'eu-north-1'}
            profiler = build_profiler(env=env)
            assert profiler is not None
            assert profiler._profiler_runner.collector.reporter.profiling_group_name == 'name_from_arn'
            assert 'us-west-2' in profiler._profiler_runner.collector.reporter.codeguru_client_builder.codeguru_client._endpoint.host

        class TestWhenProfilingGroupNameIsAlsoProvided:
            def test_it_uses_name_from_arn(self):
                env = {PG_ARN_ENV: 'arn:aws:codeguru-profiler:us-west-2:003713371902:profilingGroup/name_from_arn',
                       PG_NAME_ENV: 'different_name_here'}
                assert build_profiler(env=env) \
                           ._profiler_runner.collector.reporter.profiling_group_name == 'name_from_arn'

    class TestWhenProfilingGroupArnIsMalformed:
        def test_it_creates_profiler_using_the_name_and_region_from_env(self):
            env = {PG_ARN_ENV: 'this_arn_is_definitely_not_correct',
                   PG_NAME_ENV: 'but_this_name_should_do',
                   REGION_ENV: 'eu-north-1'}
            assert build_profiler(env=env) \
                       ._profiler_runner.collector.reporter.profiling_group_name == 'but_this_name_should_do'
            assert 'eu-north-1' in build_profiler(env=env) \
                ._profiler_runner.collector.reporter.codeguru_client_builder.codeguru_client._endpoint.host

    class TestWhenRegionNameIsInEnvironment:
        def test_it_creates_a_profiler_and_uses_correct_region(self):
            region = "eu-north-1"
            env = {REGION_ENV: region}
            profiler_factory = MagicMock(spec=Profiler)
            subject = build_profiler(pg_name="my_profiling_group", env=env,
                                     profiler_factory=profiler_factory)
            assert subject is not None
            profiler_factory.assert_called_once_with(profiling_group_name=ANY, region_name=region,
                                                     aws_session=ANY, environment_override=ANY)

    class TestWhenSamplingIntervalIsInEnvironment:
        def test_it_uses_correct_sampling_interval(self):
            env = {"AWS_CODEGURU_PROFILER_SAMPLING_INTERVAL_MS": "100"}
            profiler_factory = MagicMock(spec=Profiler)
            subject = build_profiler(pg_name="my_profiling_group", env=env,
                                     profiler_factory=profiler_factory)

            profiler_factory.assert_called_once_with(profiling_group_name=ANY, region_name=ANY, aws_session=ANY,
                                                     environment_override={"sampling_interval": datetime.timedelta(
                                                         milliseconds=100)})

    class TestWhenReportingIntervalIsInEnvironment:
        def test_it_uses_correct_sampling_interval(self):
            env = {"AWS_CODEGURU_PROFILER_REPORTING_INTERVAL_MS": "60000"}
            profiler_factory = MagicMock(spec=Profiler)
            subject = build_profiler(pg_name="my_profiling_group", env=env,
                                     profiler_factory=profiler_factory)
            profiler_factory.assert_called_once_with(profiling_group_name=ANY, region_name=ANY, aws_session=ANY,
                                                     environment_override={
                                                         "reporting_interval": datetime.timedelta(seconds=60)})

    class TestWhenMalformedReportingIntervalIsInEnvironment:
        def test_it_still_creates_a_profiler(self):
            env = {"AWS_CODEGURU_PROFILER_REPORTING_INTERVAL_MS": "12.5"}
            profiler_factory = MagicMock(spec=Profiler)
            subject = build_profiler(pg_name="my_profiling_group", env=env,
                                     profiler_factory=profiler_factory)
            assert subject is not None

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
