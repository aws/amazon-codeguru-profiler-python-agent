import os

import boto3
import pytest
from unittest.mock import MagicMock

from test.pytestutils import before
from codeguru_profiler_agent.codeguru_client_builder import CodeGuruClientBuilder


class TestCodeGuruClientBuilder:
    @before
    def before(self):
        default_session = boto3.session.Session()
        self.subject = CodeGuruClientBuilder(environment={'aws_session': default_session})

    def test_codeguru_client_is_not_built_at_initialization(self):
        assert self.subject._codeguru_client_instance is None

    def test_codeguru_client_getter_builds_the_client(self):
        # make sure the getter builds it
        assert self.subject.codeguru_client is not None
        assert self.subject._codeguru_client_instance is not None

    class TestWhenSessionIsProvided:
        @before
        def before(self):
            self.subject = CodeGuruClientBuilder(environment={
                'aws_session': boto3.session.Session(region_name='ap-southeast-2')
            })

        def test_session_region_is_used(self):
            assert 'ap-southeast-2' in self.subject.codeguru_client._endpoint.host

        class TestWhenRegionProvidedInSessionDoesNotMatchWithRegionSetInEnvironment:
            @pytest.fixture(autouse=True)
            def around(self):
                previous_region_value = os.environ.get('AWS_DEFAULT_REGION')
                os.environ['AWS_DEFAULT_REGION'] = 'eu-west-2'
                self.subject = CodeGuruClientBuilder(environment={
                    'aws_session': boto3.session.Session(region_name="ap-southeast-2")
                })
                yield
                if previous_region_value is not None:
                    os.environ['AWS_DEFAULT_REGION'] = previous_region_value
                else:
                    del os.environ['AWS_DEFAULT_REGION']

            def test_provided_region_is_used(self):
                assert 'ap-southeast-2' in self.subject.codeguru_client._endpoint.host

    class TestWhenRegionIsProvided:
        @before
        def before(self):
            self.subject = CodeGuruClientBuilder(environment={
                'aws_session': boto3.session.Session(region_name='eu-west-2'),
                'region_name': 'eu-west-2'
            })

        def test_provided_region_is_used(self):
            assert 'eu-west-2' in self.subject.codeguru_client._endpoint.host

        class TestWhenRegionProvidedDoesNotMatchWithSessionRegion:
            @before
            def before(self):
                self.subject = CodeGuruClientBuilder(environment={
                    'aws_session': boto3.session.Session(region_name='eu-west-2'),
                    'region_name': 'ap-southeast-2'
                })

            def test_provided_region_is_used(self):
                assert 'ap-southeast-2' in self.subject.codeguru_client._endpoint.host

        class TestWhenRegionProvidedDoesNotMatchWithRegionSetInEnvironment:
            @pytest.fixture(autouse=True)
            def around(self):
                previous_region_value = os.environ.get('AWS_DEFAULT_REGION')
                os.environ['AWS_DEFAULT_REGION'] = 'eu-west-2'
                self.subject = CodeGuruClientBuilder(environment={
                    'aws_session': boto3.session.Session(),
                    'region_name': 'ap-southeast-2'
                })
                yield
                if previous_region_value is not None:
                    os.environ['AWS_DEFAULT_REGION'] = previous_region_value
                else:
                    del os.environ['AWS_DEFAULT_REGION']

            def test_provided_region_is_used(self):
                assert 'ap-southeast-2' in self.subject.codeguru_client._endpoint.host

    class TestWhenRegionIsSetInEnvironment:
        @pytest.fixture(autouse=True)
        def around(self):
            previous_region_value = os.environ.get('AWS_DEFAULT_REGION')
            os.environ['AWS_DEFAULT_REGION'] = 'ap-southeast-2'
            self.subject = CodeGuruClientBuilder(environment={
                'aws_session': boto3.session.Session()
            })
            yield
            if previous_region_value is not None:
                os.environ['AWS_DEFAULT_REGION'] = previous_region_value
            else:
                del os.environ['AWS_DEFAULT_REGION']

        def test_correct_region_is_used(self):
            assert 'ap-southeast-2' in self.subject.codeguru_client._endpoint.host

    class TestWhenEndpointIsProvided:
        @before
        def before(self):
            self.subject = CodeGuruClientBuilder(environment={
                'aws_session': boto3.session.Session(),
                'endpoint_url': 'https://some-endpoint.amazonaws.com'
            })

        def test_provided_region_is_used(self):
            assert self.subject.codeguru_client._endpoint.host == 'https://some-endpoint.amazonaws.com'

    class TestWhenAwsSessionIsProvided:
        @before
        def before(self):
            self.mock_session = MagicMock(name="profiler", spec=boto3.session.Session)
            self.subject = CodeGuruClientBuilder(
                environment={
                    'aws_session': self.mock_session
                }
            )
            # it is necessary to call codeguru_client; otherwise no session will be created.
            self.subject.codeguru_client

        def test_it_creates_client_with_given_session(self):
            self.mock_session.client.assert_called_once()
