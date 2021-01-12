import codecs
import re
import subprocess
import tempfile
import shutil
import os
import json

# The following values are used in the documentation, so any change of them requires updates to the documentation.
LAYER_NAME = 'AWSCodeGuruProfilerPythonAgentLambdaLayerTestDev'
SUPPORTED_VERSIONS = ['3.6', '3.7', '3.8']
EXEC_SCRIPT_FILE_NAME = 'codeguru_profiler_lambda_exec'

# We should release in all the regions that lambda layer is supported, not just the ones CodeGuru Profiler Service supports.
# See this link for supported regions: https://docs.aws.amazon.com/general/latest/gr/lambda-service.html
LAMBDA_LAYER_SUPPORTED_REGIONS = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
                                  'ap-south-1', 'ap-northeast-2', 'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
                                  'ap-east-1',
                                  'ca-central-1',
                                  'eu-central-1', 'eu-west-1', 'eu-west-2', 'eu-west-3', 'eu-north-1', 'eu-south-1',
                                  'af-south-1', 'me-south-1', 'sa-east-1',
                                  'cn-north-1', 'cn-northwest-1',
                                  'us-gov-west-1', 'us-gov-east-1']

# Now we do not release for some of those regions yet:
#  - China regions are not available through the lambda console: cn-north-1, cn-northwest-1
#  - Some regions are opt-in, customers have to manually activate them to use so we will wait for customers to ask
#    for them: me-south-1, eu-south-1, af-south-1, ap-east-1
#  - US gov regions are also skipped for now: us-gov-west-1, us-gov-east-1
SKIPPED_REGIONS = ['cn-north-1', 'cn-northwest-1', 'us-gov-west-1', 'us-gov-east-1',
                   'me-south-1', 'eu-south-1', 'af-south-1', 'ap-east-1']
REGIONS_TO_RELEASE_TO = sorted(set(LAMBDA_LAYER_SUPPORTED_REGIONS) - set(SKIPPED_REGIONS))

here = os.path.abspath(os.path.dirname(__file__))


def confirm(prompt_str, answer_true='y', answer_false='n'):
    """
    Just a manual prompt to ask for confirmation.
    This gives time for engineers to check the archive we have generated before publishing.
    """
    prompt = '%s (%s|%s): ' % (prompt_str, answer_true, answer_false)

    while True:
        answer = input(prompt).lower()
        if answer == answer_true:
            return True
        elif answer == answer_false:
            return False
        else:
            print('Please enter ' + answer_true + ' or ' + answer_false)


def read(*parts):
    return codecs.open(os.path.join(here, *parts), 'r').read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__agent_version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError('Unable to find version string.')


def build_libraries():
    """
    Build the module that will be later used to generate the archive for the layer.
    """
    print('Building the module.')
    build_command = ['python setup.py build']
    subprocess.run(build_command, shell=True)


def build_layer_archive():
    temporary_directory = tempfile.mkdtemp()
    print('Created temporary directory for the layer archive: ' + str(temporary_directory))
    layer_content_path = os.path.join(temporary_directory, 'layer')

    # building the module
    build_libraries()

    # copy the built module for each supported version
    for version in SUPPORTED_VERSIONS:
        shutil.copytree(os.path.join('build', 'lib', 'codeguru_profiler_agent'),
                        os.path.join(layer_content_path, 'python', 'lib', 'python' + version, 'site-packages',
                                     'codeguru_profiler_agent'))

    # copy the exec script, shutil.copyfile does not copy the permissions (i.e. script is executable) while copy2 does.
    shutil.copy2(EXEC_SCRIPT_FILE_NAME, os.path.join(layer_content_path, EXEC_SCRIPT_FILE_NAME))

    shutil.make_archive(os.path.join(temporary_directory, 'layer'), 'zip', layer_content_path)
    return os.path.join(temporary_directory, 'layer.zip')


def _disable_pager_for_aws_cli():
    """
    By default AWS CLI v2 returns all output through your operating system’s default pager program
    This can mess up with scripts calling aws commands, disable it by setting an environment variable.
    See https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-pagination.html
    """
    os.environ['AWS_PAGER'] = ''


def publish_new_version(layer_name, path_to_archive, region, module_version):
    cmd = ['aws', '--region', region, 'lambda', 'publish-layer-version',
           '--layer-name', layer_name,
           '--zip-file', 'fileb://' + path_to_archive,
           '--description', 'Python agent layer for AWS CodeGuru Profiler. Module version = ' + module_version,
           '--license-info', 'ADSL',  # https://spdx.org/licenses/ADSL.html
           '--compatible-runtimes']
    cmd += ['python' + v for v in SUPPORTED_VERSIONS]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(str(result.stderr))
        raise RuntimeError('Failed to publish layer')
    output = json.loads(result.stdout)
    return str(output['Version']), output['LayerVersionArn']


def add_permission_to_layer(layer_name, region, version, principal=None):
    if not principal:
        principal = '*'
    print('  - Adding permission to use the layer to: ' + principal)
    state_id = 'UniversalReadPermissions' if principal == '*' else 'ReadPermissions-' + principal
    cmd = ['aws', 'lambda', 'add-layer-version-permission',
           '--layer-name', layer_name,
           '--region', region,
           '--version-number', version,
           '--statement-id', state_id,
           '--principal', principal,
           '--action', 'lambda:GetLayerVersion']
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(str(result.stderr))
        raise RuntimeError('Failed to add permission to layer')


def publish_layer(path_to_archive, module_version, regions=None, layer_name=None, customer_accounts=None):
    print('Publishing module version {} from archive {}.'.format(module_version, path_to_archive))
    _disable_pager_for_aws_cli()
    for region in regions:
        print('Publishing layer in region ' + region)
        new_version, arn = publish_new_version(layer_name, path_to_archive, region, module_version)
        print('  ' + arn)
        for account_id in customer_accounts:
            add_permission_to_layer(layer_name, region, new_version, account_id)


def main():
    from argparse import ArgumentParser
    usage = 'python %(prog)s [-r region] [-a account] [--role role]'
    parser = ArgumentParser(usage=usage)
    parser.add_argument('-n', '--layer-name', dest='layer_name', help='Name of the layer, default is ' + LAYER_NAME)
    parser.add_argument('-r', '--region', dest='region',
                        help='Region in which you want to create the layer or add permission, '
                             'default is all supported regions')

    args = parser.parse_args()
    layer_name = args.layer_name if args.layer_name else LAYER_NAME
    regions = [args.region] if args.region else REGIONS_TO_RELEASE_TO
    customer_accounts = ['*']
    module_version = find_version('codeguru_profiler_agent/agent_metadata', 'agent_metadata.py')

    archive = build_layer_archive()
    print('Preparing to publish archive ' + archive)
    if confirm('Publish the layer? Check the archive before responding. '):
        publish_layer(path_to_archive=archive, module_version=module_version, regions=regions,
                      layer_name=layer_name, customer_accounts=customer_accounts)
    else:
        print('Nothing was published.')


if __name__ == '__main__':
    main()
