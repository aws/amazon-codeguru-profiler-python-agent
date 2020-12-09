import codecs
import re
import subprocess
import tempfile
import shutil
import os
import json

# Changing any of those means we need to change documentation !!
AGENT_DISTRIBUTION_ACCOUNT = '157417159150'
DISTRIBUTION_ASSUME_ROLE = 'AgentPublish'
LAYER_NAME = 'AWSCodeGuruProfilerPythonAgentLambdaLayerBeta'  # FIXME, remove Beta suffix when we actually release
SUPPORTED_VERSIONS = ['3.6', '3.7', '3.8']
EXEC_SCRIPT_FILE_NAME = 'codeguru_profiler_lambda_exec'

# We should release in all the regions that lambda layer supports, not just the ones CodeGuru Profiler supports
# See this link for supported regions: https://docs.aws.amazon.com/general/latest/gr/lambda-service.html
LAMBDA_LAYER_SUPPORTED_REGIONS = ["us-east-1", "us-east-2", "us-west-1", "us-west-2",
                                  "ap-south-1", "ap-northeast-2", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-east-1",
                                  "ca-central-1",
                                  "eu-central-1", "eu-west-1", "eu-west-2", "eu-west-3", "eu-north-1", "eu-south-1",
                                  "af-south-1", "me-south-1", "sa-east-1",
                                  "cn-north-1", "cn-northwest-1",
                                  "us-gov-west-1", "us-gov-east-1"]
# Now we do not release for some of those regions yet:
#  - China regions are not available through the lambda console: cn-north-1, cn-northwest-1
#  - Some regions are opt-in, customers have to manually activate them to use so we will wait for customers to ask
#    for them: me-south-1, eu-south-1, af-south-1, ap-east-1
#  - US gov regions are also skipped for now: us-gov-west-1, us-gov-east-1
SKIPPED_REGIONS = ["cn-north-1", "cn-northwest-1", "us-gov-west-1", "us-gov-east-1",
                   "me-south-1", "eu-south-1", "af-south-1", "ap-east-1"]
REGIONS_TO_RELEASE_TO = sorted(set(LAMBDA_LAYER_SUPPORTED_REGIONS) - set(SKIPPED_REGIONS))

here = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    return codecs.open(os.path.join(here, *parts), 'r').read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__agent_version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


def build_libraries():
    """
    Build the module, this will allow us to generate the archive for layer after
    FIXME: change this if we stop using brazil and a different command is necessary to build.
    """
    build_command = ['brazil-build']
    subprocess.run(build_command)


def build_layer_archive():
    temporary_directory = tempfile.mkdtemp()
    print("created temporary directory for the layer archive: " + str(temporary_directory))
    layer_content_path = os.path.join(temporary_directory, 'layer')

    # copy the eggs for each supported version
    for version in SUPPORTED_VERSIONS:
        # FIXME: change this if we stop using brazil and the module is no more built in this location
        shutil.copytree(os.path.join('build', 'lib', 'python' + version, 'site-packages', 'codeguru_profiler_agent'),
                        os.path.join(layer_content_path, 'python', 'lib', 'python' + version, 'site-packages', 'codeguru_profiler_agent'))

    # copy the exec script, shutil.copyfile does not copy the permissions (i.e. script is executable) while copy2 does.
    shutil.copy2(EXEC_SCRIPT_FILE_NAME, os.path.join(layer_content_path, EXEC_SCRIPT_FILE_NAME))

    shutil.make_archive(os.path.join(temporary_directory, 'layer'), 'zip', layer_content_path)
    return os.path.join(temporary_directory, 'layer.zip')


def get_credentials(account_id=None, role_name=None):
    if account_id is None:
        account_id = AGENT_DISTRIBUTION_ACCOUNT
    if role_name is None:
        role_name = DISTRIBUTION_ASSUME_ROLE
    command = ['ada', 'credentials', 'update', '--account=' + account_id, '--provider=isengard',
               '--role=' + role_name, '--once']
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(str(result.stderr))
        raise RuntimeError('Failed to get credentials')


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
    print('')
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
    parser.add_argument('-n', '--layer-name', dest="layer_name", help='Name of the layer, default is ' + LAYER_NAME)
    parser.add_argument('-r', '--region', dest="region",
                        help='Region in which you want to create the layer or add permission, '
                             'default is all supported regions')
    parser.add_argument('-a', '--account-id', dest="account_id",
                        help='Account Id where we want to publish the layer, default is ' + AGENT_DISTRIBUTION_ACCOUNT)
    parser.add_argument('--role', dest="role", help='Role to use to publish, default is ' + DISTRIBUTION_ASSUME_ROLE)
    parser.add_argument('--skip-build', dest='skip_build', action='store_true',
                        help='Skip build step, the module must have been built already', default=False)

    args = parser.parse_args()
    layer_name = args.layer_name if args.layer_name else LAYER_NAME
    regions = [args.region] if args.region else REGIONS_TO_RELEASE_TO
    customer_accounts = ['*']
    get_credentials(args.account_id, args.role)
    module_version = find_version("src/codeguru_profiler_agent/agent_metadata", "agent_metadata.py")
    if not args.skip_build:
        build_libraries()
    archive = build_layer_archive()
    publish_layer(path_to_archive=archive, module_version=module_version, regions=regions,
                  layer_name=layer_name, customer_accounts=customer_accounts)


if __name__ == "__main__":
    main()
