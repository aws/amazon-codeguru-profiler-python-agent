import logging
import re
import datetime
import uuid
import threading

from datetime import timedelta
from random import SystemRandom
from types import MappingProxyType as UnmodifiableDict

from codeguru_profiler_agent.agent_metadata.agent_debug_info import ErrorsMetadata
from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata
from codeguru_profiler_agent.profiler_disabler import ProfilerDisabler
from codeguru_profiler_agent.reporter.agent_configuration import AgentConfiguration, AgentConfigurationMerger

from codeguru_profiler_agent.metrics.timer import Timer
from codeguru_profiler_agent.profiler_runner import ProfilerRunner
from codeguru_profiler_agent.file_reporter.file_reporter import FileReporter
from codeguru_profiler_agent.local_aggregator import LocalAggregator
from codeguru_profiler_agent.sdk_reporter.sdk_reporter import SdkReporter
from codeguru_profiler_agent.codeguru_client_builder import CodeGuruClientBuilder

INITIAL_MINIMUM_REPORTING_INTERVAL = timedelta(seconds=30)

DEFAULT_CPU_LIMIT_PERCENTAGE = 10
DEFAULT_REPORTING_INTERVAL = datetime.timedelta(minutes=5)
DEFAULT_SAMPLING_INTERVAL = datetime.timedelta(seconds=1.0)
DEFAULT_MAX_STACK_DEPTH = 1000
# TODO: Review the memory limit
DEFAULT_MEMORY_LIMIT_BYTES = 10 * 1024 * 1024

# Skip issue reported by Bandit.
# [B108:hardcoded_tmp_directory] Probable insecure usage of temp file/directory.
# https://bandit.readthedocs.io/en/latest/plugins/b108_hardcoded_tmp_directory.html
# This file can be used by the customer as kill switch for the Profiler.
# TODO FIXME Consider making this work for Windows.
KILLSWITCH_FILEPATH = "/var/tmp/killProfiler" #nosec

logger = logging.getLogger(__name__)

# this lock is used for checking the singleton when we start and stop the profiler
start_profiler_lock = threading.Lock()


class Profiler:
    """
    The Profiler Python agent provides a lightweight way of monitoring your service performance. It uses
    collected samples to provide information about what's on the stack of each thread in the python interpreter.
    You MUST provide a profiling_group_name.
    """

    # this singleton instance is used to make sure only one profiler instance is started at a time.
    _active_profiler = None

    def __init__(self,
                 profiling_group_name,
                 region_name=None,
                 aws_session=None,
                 environment_override=dict()):
        """
        NOTE: The profiler MUST be instantiated using keyword arguments. We provide no compatibility for the order
        (or number) of arguments.

        - Configuration

            :param profiling_group_name: name of the profiling group where the profiles will be stored.
            :param region_name: AWS Region to report to, given profiling group name must exist in that region. Note
                that this value overwrites what is used in aws_session. If not provided, boto3 will search
                configuration for the region. (e.g. "us-west-2")
            :param aws_session: The boto3.Session that this profiler should be using for communicating with the backend
                Check https://boto3.amazonaws.com/v1/documentation/api/latest/guide/session.html for more details.

        - Advanced Configuration Options - We recommend not to touch these
            :param environment_override: custom dependency container dictionary. allows custom behavior to be injected
                but please note that we do not guarantee compatibility between any different profiler agent versions for
                this api (default: dict()). Possible keys:
                    - reporting_interval: delay between profile reports in datetime.timedelta (default: None)
                    - sampling_interval: delay between each sample in datetime.timedelta (default: 1 seconds)
                    - reporting_mode: Reporting mode to be used, two modes are supported: "codeguru_service" and "file".
                                      "file" mode is only used for testing at the moment. (default: "codeguru_service")
                    - file_prefix: path + file prefix to use for profile reports when in "file" reporting mode
                                   (default: './profile-{profiling_group_name}' only used when reporting mode is "file")
                    - cpu_limit_percentage: cpu limit (%) for profiler (default: 30)
                    - max_threads: the max number of threads getting sampled (default: 100)
                    - killswitch_filepath: file path pointing to the killswitch file (default: "/var/tmp/killProfiler")
                    - host_weight: A scale factor used to rescale the profile collected in this host to make the profile
                                   representative of the whole fleet (default: 1)
                    - endpoint_url: url used for submitting profile (default: None, will target codeguru prod APIs)
                    - excluded_threads: set of thread names to be excluded from sampling (default: set())
        """
        self._profiler_runner_instance = None
        self.environment = {}
        try:
            if not profiling_group_name:
                logger.info(
                    "Profiler must be passed a non empty profiling group name, CodeGuru Profiler will not start. "
                    "Please specify a ``profiling_group_name`` when configuring the ``Profiler`` class."
                )
                return

            # This is the profiler instance-wide dependency container aka environment
            # It is used to contain shared dependencies and configuration, and can also be used to override the behavior
            # on the profiler classes without needing to monkey-patch.
            self.environment = self._set_default_environment(profiling_group_name)
            self.environment["profiling_group_name"] = profiling_group_name
            self.environment["region_name"] = region_name
            self.environment["aws_session"] = aws_session

            default_config = AgentConfiguration(
                should_profile=self.environment["should_profile"],
                sampling_interval=self.environment["sampling_interval"],
                reporting_interval=self.environment["reporting_interval"],
                minimum_time_reporting=self.environment["minimum_time_reporting"],
                max_stack_depth=self.environment["max_stack_depth"],
                cpu_limit_percentage=self.environment["cpu_limit_percentage"])
            user_overrides = AgentConfiguration(
                should_profile=environment_override.get('should_profile'),
                sampling_interval=environment_override.get('sampling_interval'),
                reporting_interval=environment_override.get('reporting_interval'),
                minimum_time_reporting=environment_override.get('minimum_time_reporting'),
                max_stack_depth=environment_override.get('max_stack_depth'),
                cpu_limit_percentage=environment_override.get('cpu_limit_percentage'))
            agent_config_merger = AgentConfigurationMerger(default=default_config, user_overrides=user_overrides)
            self.environment["agent_config_merger"] = agent_config_merger

            # Removing all keys from the environment that were used for the AgentConfigurationMerger
            # to make sure the rest of the code would read it from the AgentConfiguration.
            for key in default_config.as_dict().keys():
                del self.environment[key]
            for key in user_overrides.as_dict().keys():
                del environment_override[key]

            self.environment = self._setup_final_environment(self.environment, environment_override)
            profiler_runner_factory = self.environment.get("profiler_runner_factory") or ProfilerRunner
            self._profiler_runner_instance = profiler_runner_factory(environment=self.environment)
        except:
            logger.info("Caught exception while creating the CodeGuru Profiler Agent instance", exc_info=True)
            if environment_override.get("allow_top_level_exceptions") is True:
                raise

    @staticmethod
    def _set_default_environment(profiling_group_name):
        return {
            'timer': Timer(),
            'profiler_thread_name': 'codeguru-profiler-agent-' + str(uuid.uuid4()).replace('-', ''),
            'reporting_mode': 'codeguru_service',
            'file_prefix': 'profile-{}'.format(re.sub(r"\W", "", profiling_group_name)),
            'excluded_threads': set(),
            'should_profile': True,
            'sampling_interval': DEFAULT_SAMPLING_INTERVAL,
            'reporting_interval': DEFAULT_REPORTING_INTERVAL,
            'minimum_time_reporting': INITIAL_MINIMUM_REPORTING_INTERVAL,
            'max_stack_depth': DEFAULT_MAX_STACK_DEPTH,
            'cpu_limit_percentage': DEFAULT_CPU_LIMIT_PERCENTAGE,
            'memory_limit_bytes': DEFAULT_MEMORY_LIMIT_BYTES,
            'host_weight': 1.0,
            'killswitch_filepath': KILLSWITCH_FILEPATH,
            'max_threads': 100
        }

    def _setup_final_environment(self, environment, environment_override):
        environment.update(environment_override)

        # set additional parameters if needed (costly default init or depend on other parameters)
        if environment.get('initial_sampling_interval') is None:
            environment['initial_sampling_interval'] = datetime.timedelta(
                seconds=SystemRandom().uniform(0, AgentConfiguration.get().sampling_interval.total_seconds()))
        environment['excluded_threads'] = \
            frozenset({environment['profiler_thread_name']}.union(environment['excluded_threads']))
        # TODO delay metadata lookup until we need it
        environment['agent_metadata'] = environment.get('agent_metadata') or AgentMetadata()
        environment['errors_metadata'] = environment.get('errors_metadata') or ErrorsMetadata()
        environment['collector'] = environment.get('collector') or self._select_collector(environment)
        environment["profiler_disabler"] = environment.get('profiler_disabler') or ProfilerDisabler(environment)
        return UnmodifiableDict(environment)

    @staticmethod
    def _select_collector(environment):
        reporting_mode = environment.get('reporting_mode')
        if reporting_mode == "codeguru_service":
            environment["codeguru_profiler_builder"] = CodeGuruClientBuilder(environment)
            return LocalAggregator(
                reporter=SdkReporter(environment=environment),
                environment=environment)
        elif reporting_mode == "file":
            return LocalAggregator(
                reporter=FileReporter(environment=environment),
                environment=environment)
        else:
            raise ValueError("Invalid reporting mode for CodeGuru Profiler detected: {}".format(reporting_mode))

    def start(self, block=False):
        """
        Start executing the profiler with the settings provided on creation. If the profiler was paused
        it will resume profiling.
        Resuming profiling is done asynchronously by default so the method can return before the action
        is effectively applied.
        TODO Currently we can start multiple instances of Profiler which we want to avoid. Implement a singleton
            solution here so that we can only start one instance of Profiler (similar to what we have for java agent)
        :param block: if True, we will not return from this function before the profiling started, default is False.
        :return: True if the profiler was started successfully; False otherwise.
        """
        try:
            if not self.is_running():
                return self._start(block)
            else:
                logger.debug("Resuming CodeGuru Profiler activity")
                self._profiler_runner.resume(block)
            return True
        except:
            logger.info("Caught exception while trying to start the CodeGuru Profiler Agent", exc_info=True)
            return False

    def _start(self, block=False):
        logger.debug("Attempting to start the CodeGuru profiler")
        with start_profiler_lock:
            if Profiler._active_profiler is not None and Profiler._active_profiler != self:
                logger.info("Starting multiple instances of profiler agents is not allowed. "
                               "Please validate the configuration of the profiler. "
                               "If this is intentional, then stop the active profiler agent before starting a new one.")
                return False
            logger.info("Starting profiler, " + str(self))
            if not self._profiler_runner.start():
                logger.info("CodeGuru Profiler Agent failed to start.")
                return False
            Profiler._active_profiler = self
            return True

    def is_running(self):
        """
        Determine if the Profiler is actually running or not.

        :return: True if the profiler is running.
        """
        try:
            return self._profiler_runner.is_running()
        except:
            logger.info("Unable to detect if the CodeGuru Profiler is running.", exc_info=True)
            return False

    def stop(self):
        """
        Terminates the profiler and flushes existing profile to the backend. If this method is called whilst
        this instance of the profiler has never been started it will return False.

        :return: True if the profiler was stopped successfully or was already stopped; False otherwise.
        """
        try:
            with start_profiler_lock:
                if Profiler._active_profiler == self:
                    self._profiler_runner.stop()
                    Profiler._active_profiler = None
                return True
        except:
            logger.info("Caught exception while trying to stop the CodeGuru Profiler Agent", exc_info=True)
            return False

    def pause(self, block=False):
        """
        Pauses all profiler activity until start() is called again.
        By default the pause will be done asynchronously so the method can return before pause is effectively applied.

        :param block: if True, we will not return from this function before the pause is applied, default is False.
        """
        try:
            logger.debug("Pausing CodeGuru Profiler activity")
            self._profiler_runner.pause(block)
            return True
        except:
            logger.info("Unable to pause the CodeGuru Profiler.", exc_info=True)
            return False

    @property
    def _profiler_runner(self):
        if self._profiler_runner_instance:
            return self._profiler_runner_instance
        else:
            raise Exception("CodeGuru Profiler was not correctly initialized; see previous error messages for cause")

    def __str__(self):
        return 'Profiler(environment=' + str({k: self.environment.get(k) for k in
                                              ['max_threads', 'profiling_group_name', 'region_name', 'aws_session']})
