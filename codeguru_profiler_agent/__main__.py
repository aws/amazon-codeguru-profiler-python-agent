import os
import sys
import runpy
import logging

profiler = None


def _start_profiler(options, env):
    """
    This will init the profiler object and start it.
    :param options: options may contain profiling group name, region or credential profile if they are passed in command
    :param env: the environment dict from which to search for variables (usually os.environ is passed)
    :return: the profiler object
    """
    from codeguru_profiler_agent.profiler_builder import build_profiler
    global profiler
    profiler = build_profiler(pg_name=options.profiling_group_name, region_name=options.region,
                              credential_profile=options.credential_profile, env=env)
    if profiler is not None:
        profiler.start()
    return profiler


def _set_log_level(log_level):
    if log_level is None:
        return
    numeric_level = getattr(logging, log_level.upper(), None)
    if isinstance(numeric_level, int):
        logging.basicConfig(level=numeric_level)


def main(input_args=sys.argv[1:], env=os.environ, start_profiler=_start_profiler):
    from argparse import ArgumentParser
    usage = 'python -m codeguru_profiler_agent [-p profilingGroupName] [-r region] [-c credentialProfileName]' \
            ' [-m module | scriptfile.py] [arg]' \
            + '...\nexample: python -m codeguru_profiler_agent -p myProfilingGroup hello_world.py'
    parser = ArgumentParser(usage=usage)
    parser.add_argument('-p', '--profiling-group-name', dest="profiling_group_name",
                        help='Name of the profiling group to send profiles into')
    parser.add_argument('-r', '--region', dest="region",
                        help='Region in which you have created your profiling group. e.g. "us-west-2".'
                             + ' Default depends on your configuration'
                             + ' (see https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html)')
    parser.add_argument('-c', '--credential-profile-name', dest="credential_profile",
                        help='Name of the profile created in shared credential file used for submitting profiles. '
                             + '(see https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#shared-credentials-file)')
    parser.add_argument('-m', dest='module', action='store_true',
                        help='Profile a library module', default=False)
    parser.add_argument('--log', dest='log_level',
                        help='Set log level, possible values: debug, info, warning, error and critical'
                             + ' (default is warning)')
    parser.add_argument('scriptfile')

    (known_args, rest) = parser.parse_known_args(args=input_args)

    # Set the sys arguments to the remaining arguments (the one needed by the client script) if they were set.
    sys.argv = sys.argv[:1]
    if len(rest) > 0:
        sys.argv += rest

    _set_log_level(known_args.log_level)

    if known_args.module:
        code = "run_module(modname, run_name='__main__')"
        globs = {
            'run_module': runpy.run_module,
            'modname': known_args.scriptfile
        }
    else:
        script_name = known_args.scriptfile
        sys.path.insert(0, os.path.dirname(script_name))
        with open(script_name, 'rb') as fp:
            code = compile(fp.read(), script_name, 'exec')
        globs = {
            '__file__': script_name,
            '__name__': '__main__',
            '__package__': None,
            '__cached__': None,
        }

    # now start and stop profile around executing the user's code
    if not start_profiler(known_args, env):
        parser.print_usage()
    try:
        # Skip issue reported by Bandit.
        # Issue: [B102:exec_used] Use of exec detected.
        # https://bandit.readthedocs.io/en/latest/plugins/b102_exec_used.html
        # We need exec(..) here to run the code from the customer.
        # Only the code from the customer's script is executed and only inside the customer's environment,
        # so the customer's code cannot be altered before it is executed.
        exec(code, globs, None)  # nosec
    finally:
        if profiler is not None:
            profiler.stop()


if __name__ == "__main__":
    main()
