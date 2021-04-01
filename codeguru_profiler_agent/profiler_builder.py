import os
import logging
import datetime
import boto3

from codeguru_profiler_agent.utils.log_exception import log_exception

logger = logging.getLogger(__name__)

# These variables names will be in external documentation and must be the same as for other agents (e.g. java agent)
# Do not change them unless you are sure.
# TODO: Should we move these logic to Profiler instead?
PG_NAME_ENV = "AWS_CODEGURU_PROFILER_GROUP_NAME"
PG_ARN_ENV = "AWS_CODEGURU_PROFILER_GROUP_ARN"
REGION_ENV = "AWS_CODEGURU_PROFILER_TARGET_REGION"
# Note: Please check function `check_credential_through_environment` before supporting the following env variable
CREDENTIAL_PATH = "AWS_CODEGURU_PROFILER_CREDENTIAL_PATH"
ENABLED_ENV = "AWS_CODEGURU_PROFILER_ENABLED"

# Environment variables provided by AWS Lambda
AWS_LAMBDA_FUNCTION_NAME_ENV_VAR_KEY = "AWS_LAMBDA_FUNCTION_NAME"

# non documented parameters
SAMPLING_INTERVAL = "AWS_CODEGURU_PROFILER_SAMPLING_INTERVAL_MS"
REPORTING_INTERVAL = "AWS_CODEGURU_PROFILER_REPORTING_INTERVAL_MS"


def _read_millis(override, env_name, override_key, env=os.environ):
    value = env.get(env_name)
    if value:
        try:
            override[override_key] = datetime.timedelta(milliseconds=int(value))
        except Exception:
            logger.info("Unable to convert value to a time range for environment variable " + env_name)


def _read_override(env=os.environ):
    override = dict()
    _read_millis(override, SAMPLING_INTERVAL, "sampling_interval", env)
    _read_millis(override, REPORTING_INTERVAL, "reporting_interval", env)
    return override


def _read_profiling_group_arn(env=os.environ):
    """
    Reads profiling group ARN from the environment and extract the name, region and account id from it.
    Arn is expected to be in this format:
    arn:aws:codeguru-profiler:us-west-2:003713371902:profilingGroup/profilingGroupName
    :param env: typically os.environ
    :return: (name, region, account id)
    """
    arn = env.get(PG_ARN_ENV)
    if not arn:
        return None, None, None
    parts = arn.split(':')
    try:
        return parts[5].split('/', 1)[1], parts[3], parts[4]
    except Exception:
        # print stack trace for unknown errors are they can help us investigate.
        log_exception(logger, "Malformed profiling group arn, was expecting"
                              " arn:aws:codeguru-profiler:<region>:<account_id>:profilingGroup/<profiling_group_name>"
                              " but got: " + arn)
    return None, None, None


def _get_profiling_group_name(pg_name=None, pg_name_from_arn=None, env=os.environ):
    return pg_name or _get_profiling_group_name_from_env(pg_name_from_arn, env)


def _get_profiling_group_name_from_env(pg_name_from_arn=None, env=os.environ):
    pg_name_from_env = env.get(PG_NAME_ENV)
    if pg_name_from_env and pg_name_from_arn and pg_name_from_env != pg_name_from_arn:
        logger.info("Different Profiling group name found from " + PG_NAME_ENV + " and " + PG_ARN_ENV +
                    " will use value from " + PG_ARN_ENV + " : " + pg_name_from_arn)
    return pg_name_from_arn or pg_name_from_env


def _get_region(region_name=None, region_from_arn=None, env=os.environ):
    return region_name or _get_region_from_env(region_from_arn, env)


def _get_region_from_env(region_from_arn=None, env=os.environ):
    region_from_env = env.get(REGION_ENV)
    if region_from_env and region_from_arn and region_from_env != region_from_arn:
        logger.info("Different region found from " + REGION_ENV + " and " + PG_ARN_ENV +
                    " will use value from " + PG_ARN_ENV + " : " + region_from_arn)
    return region_from_arn or region_from_env


def _is_enabled(env=os.environ):
    """
    By default profiler is enabled, any value in the environment variable other than "true" (case-insensitive) will disable it
    """
    enable_env_value = env.get(ENABLED_ENV, 'true').lower()
    result = enable_env_value == 'true'
    if not result:
        logger.info(ENABLED_ENV + " is set to " + enable_env_value + ", CodeGuru Profiler is disabled")
    return result


def _check_credential_through_environment(env=os.environ):
    """
    According to https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#shared-credentials-file,
    the credential file path gets set globally through setting the env variable AWS_SHARED_CREDENTIALS_FILE. We may
    reconsider whether we should support this override or not.
    """
    if env.get(CREDENTIAL_PATH):
        logger.info("Credential detected from environment variable " + CREDENTIAL_PATH + ". Unfortunately, we " +
                       "do not support setting credential file path through env variable yet for Python agent. " +
                       "Please follow the guide on https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#shared-credentials-file " +
                       "and set the credential file path globally through env variable AWS_SHARED_CREDENTIALS_FILE")

    return


def build_profiler(pg_name=None, region_name=None, credential_profile=None,
                   env=os.environ, session_factory=boto3.session.Session, profiler_factory=None, override=None,
                   should_autocreate_profiling_group=False):
    """
    Creates a Profiler object from given parameters or environment variables
    :param pg_name: given profiling group name, default is None
    :param region_name: given region name, default is None
    :param credential_profile: Name of the profile created in credential file used for submitting profiles
    :param env: environment variables are used if parameters are not provided, default is os.environ
    :param session_factory: (For testing) function for creating boto3.session.Session, default is boto3.session.Session
    :param override: a dictionary with possible extra parameters to override default values
    :param should_autocreate_profiling_group: True when Compute Platform is AWS Lambda. False otherwise
    :return: a Profiler object or None, this function does not throw exceptions
    """
    if profiler_factory is None:
        # We importing Profiler here rather than at the head is to avoid having import loop
        from codeguru_profiler_agent.profiler import Profiler
        profiler_factory = Profiler
    try:
        if not _is_enabled(env):
            logger.info("CodeGuru Profiler is not started as it has been explicitly disabled. Set environment " +
                        "variable " + ENABLED_ENV + " to true if you wish to enable profiler.")
            return None

        _check_credential_through_environment(env)

        name_from_arn, region_from_arn, _account_id = _read_profiling_group_arn(env)
        profiling_group_name = _get_profiling_group_name(pg_name, name_from_arn, env)
        if not profiling_group_name:
            if should_autocreate_profiling_group:
                profiling_group_name = "aws-lambda-" + env.get(AWS_LAMBDA_FUNCTION_NAME_ENV_VAR_KEY)
            else:
                logger.info("Could not find a profiling group name to start the CodeGuru Profiler agent. "
                            + "Add command line argument or environment variable. e.g. " + PG_ARN_ENV)
                return None
        region = _get_region(region_name, region_from_arn, env)
        session = session_factory(region_name=region, profile_name=credential_profile)

        override_values = _read_override(env)
        if override:
            override_values.update(override)
        return profiler_factory(profiling_group_name=profiling_group_name, region_name=region, aws_session=session,
                                environment_override=override_values)

    except Exception:
        # print stack trace for unknown errors are they can help us investigate.
        logger.info("Unable to create profiler", exc_info=True)
    return None
