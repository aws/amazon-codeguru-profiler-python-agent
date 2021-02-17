import codecs
import os
import re

from setuptools import setup, find_packages

REQUIREMENTS = [i.strip() for i in open("requirements.txt").readlines()]

here = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    return codecs.open(os.path.join(here, *parts), 'r').read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__agent_version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


# https://packaging.python.org/tutorials/packaging-projects/#creating-the-package-files
setup(
    name="codeguru_profiler_agent",
    version=find_version("codeguru_profiler_agent/agent_metadata", "agent_metadata.py"),
    packages=find_packages(exclude=("test",)),
    include_package_data=True,
    description="The Python agent to be used for Amazon CodeGuru Profiler",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    author="Amazon Web Services",
    url="https://github.com/aws/amazon-codeguru-profiler-python-agent",
    download_url="https://github.com/aws/amazon-codeguru-profiler-python-agent",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Development Status :: 5 - Production/Stable",
        "Topic :: Utilities",
        "License :: OSI Approved :: Apache Software License"
    ],

    python_requires='>=3.6',
    # The Lambda layer doesn't use this file to install the following needed packages,
    # so we have to make sure the customer has them set in place (by default or by updating the docs to install them).
    # - boto3 is already included in the Lambda Runtime for Python
    #   https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html.
    install_requires=REQUIREMENTS
)
