# Overview

The tests from this folder are marked to be skipped when run on shared build fleet because they require AWS credentials.

# Run locally

For running them locally on your development machine, follow the next steps.

1. Make sure you have installed the latest version of [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-welcome.html).

2. Use an IAM entity for the AWS CLI that has permissions to access CodeGuru Profiler.
    ```
    aws configure # Set up your AWS credentials and region as usual.
    ```

3. Create a PG with the name ``MyProfilingGroupForIntegrationTests``
    ```
    aws codeguruprofiler create-profiling-group --profiling-group-name MyProfilingGroupForIntegrationTests
    ```

4. To run the integration tests with logs enabled, run the following command.
    ```
    pytest -v -o log_cli=true test/integration
    ```

5. Consider including the output in the PR for an easier review.