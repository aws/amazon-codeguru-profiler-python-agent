import os
from datetime import datetime
from codeguru_profiler_agent.aws_lambda.lambda_context import LambdaContext

_profiler = None


def _create_lambda_profiler(profiling_group_name, region_name, environment_override, context, env=os.environ):
    """
    Calls build_profiler module to create the profiler object. If we fail to create it we return a no-op profiler
    so that we don't even go through this method again.
    """
    from codeguru_profiler_agent.profiler_builder import build_profiler
    from codeguru_profiler_agent.agent_metadata.agent_metadata import AgentMetadata
    from codeguru_profiler_agent.agent_metadata.aws_lambda import AWSLambda
    override = {'agent_metadata': AgentMetadata(AWSLambda.look_up_metadata(context))}
    override.update(environment_override)
    profiler = build_profiler(pg_name=profiling_group_name, region_name=region_name, override=override, env=env,
                              should_autocreate_profiling_group=True)
    if profiler is None:
        return _EmptyProfiler()
    return profiler


def with_lambda_profiler(profiling_group_name=None, region_name=None, environment_override=dict(),
                         profiler_factory=_create_lambda_profiler, env=os.environ):
    """
    Adds profiler start and pause calls around given function execution.
    start() and pause() should never throw exceptions.
    :param profiling_group_name: name of the profiling group where the profiles will be stored.
    :param region_name: AWS Region to report to, given profiling group name must exist in that region. Note
        that this value overwrites what is used in aws_session. If not provided, boto3 will search
        configuration for the region. (e.g. "us-west-2")
    :param environment_override: custom dependency container dictionary. allows custom behavior to be injected.
        See Profiler class for details.
    """
    def function_decorator(function):
        def profiler_decorate(event, context):
            start_time = datetime.now()
            global _profiler
            if _profiler is None:
                _profiler = profiler_factory(profiling_group_name=profiling_group_name,
                                             region_name=region_name,
                                             environment_override=environment_override,
                                             context=context, env=env)
            LambdaContext.get().context = context
            if not _profiler.start():
                # if start() failed, there is high chance it will fail again
                # so we disable the profiler to prevent further attempts.
                _profiler = _EmptyProfiler()
            try:
                return function(event, context)
            finally:
                LambdaContext.get().last_execution_duration = datetime.now() - start_time
                _profiler.pause()

        return profiler_decorate

    return function_decorator


def clear_static_profiler():
    """
    Used for unit tests
    """
    global _profiler
    if _profiler is not None:
        _profiler.stop()
        _profiler = None


class _EmptyProfiler:
    """
    This class implements the public interface of Profiler but is doing nothing
    """

    def start(self, block=False):
        return True

    def pause(self, block=False):
        return True

    def is_running(self):
        return False

    def stop(self):
        return True
