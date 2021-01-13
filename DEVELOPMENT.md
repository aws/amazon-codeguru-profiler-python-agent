
# Release

## How to release to PyPI

#### Create PR with the new agent version

- Create a pull request that updates the agent's version number in the source code [here](https://github.com/aws/amazon-codeguru-profiler-python-agent/blob/main/codeguru_profiler_agent/agent_metadata/agent_metadata.py#L12). You can use directly the editor to edit the file and create the PR.

- Get approval from the [amazon-codeguru-profiler team](https://github.com/orgs/aws/teams/amazon-codeguru-profiler).

- Wait until the [``Run tests`` workflow](https://github.com/aws/amazon-codeguru-profiler-python-agent/actions) passes successfully.

#### Publish package to Test PyPI

- Create a [new pre-release](https://github.com/aws/amazon-codeguru-profiler-python-agent/releases/new) with the agent version and details about what is changed, in the format of a changelog as [in previous releases](https://github.com/aws/amazon-codeguru-profiler-python-agent/releases). Make sure you check the box with "pre-release".

- This will trigger a release to the Test Registry of PyPI, and you can track it in the [Actions tab](https://github.com/aws/amazon-codeguru-profiler-python-agent/actions).

- You can use the agent now from the PyPI **Test** registry as [codeguru-profiler-agent](https://test.pypi.org/project/codeguru-profiler-agent/).

#### Publish package to Live PyPI

- If you want to release to the Live registry of PyPI to be used by customers, go to the [Releases tab]([here](https://test.pypi.org/project/codeguru-profiler-agent/) and edit your pre-releases as prod release.

- This will trigger publishing the package to the Live Registry of PyPI, and you can track it in the [Actions tab](https://github.com/aws/amazon-codeguru-profiler-python-agent/actions).

- You can use the agent now from the PyPI **Live** registry as [codeguru-profiler-agent](https://pypi.org/project/codeguru-profiler-agent/).

## How to release the Lambda Layer.

The layer is used for profiling AWS lambda functions. The layer contains only our module source code as `boto3` is already available in a lambda environment.

Check internal instructions for what credentials to use.

1. Checkout the last version of the `main` branch locally after you did the release to PyPI.

2. Run the following command in this package to publish a new version for the layer that will be available to the public immediately.
    ```
    python release_layer.py
    ```

3. Update the documentation with the ARN that was printed.
