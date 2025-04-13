import pytest
from unittest.mock import patch, MagicMock, Mock
import json
import requests
from hypothesis import given, strategies as st, settings, assume
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout, RequestException

# Module we're testing
from emercoin.emercoin_connection_handler import EmercoinConnection, ConnectionError, AuthError, RPCError


def default_config():
    return {
        'rpc_url': 'http://localhost:6662',
        'rpc_user': 'test',
        'rpc_password': 'test',
        'timeout': 10,
        'max_retries': 3,
        'retry_delay': 1,
        'use_queue': False
    }

@pytest.fixture
def connection(default_config):
    return EmercoinConnection(default_config)

# Strategy for valid connection configurations
config_strategy = st.fixed_dictionaries({
    'rpc_url': st.one_of(
        st.just('http://localhost:6662'),
        st.just('https://emercoin.example.com:6662'),
        st.just('http://192.168.1.10:6662')
    ),
    'rpc_user': st.text(min_size=1, max_size=50),
    'rpc_password': st.text(min_size=1, max_size=50),
    'timeout': st.integers(min_value=1, max_value=60),
    'max_retries': st.integers(min_value=0, max_value=10),
    'retry_delay': st.integers(min_value=0, max_value=5),
    'use_queue': st.booleans()
})

# Strategy for RPC method calls
method_call_strategy = st.fixed_dictionaries({
    'method': st.one_of(
        st.just('getinfo'),
        st.just('name_show'),
        st.just('name_history'),
        st.just('name_filter'),
        st.just('name_new'),
        st.just('name_update')
    ),
    'params': st.lists(
        st.one_of(
            st.text(min_size=0, max_size=100),
            st.integers(),
            st.booleans(),
            st.dictionaries(
                keys=st.text(min_size=1, max_size=10),
                values=st.one_of(st.text(), st.integers(), st.booleans())
            )
        ),
        min_size=0, max_size=5
    )
})


@given(config=config_strategy)
def test_connection_initialization(config):
    """Test that the connection can be initialized with various valid configurations."""
    connection = EmercoinConnection(config)
    assert connection.config == config


@given(config=st.dictionaries(
    # Only include fields that are actually required in your validation
    keys=st.sampled_from(['rpc_user', 'rpc_password']),
    values=st.none(),
    min_size=1
))
def test_connection_with_missing_config(config):
    """Test that the connection raises appropriate errors when required config is missing."""
    # Create a config with some fields set to None
    test_config = default_config().copy()
    for key, value in config.items():
        test_config[key] = value
    
    # We expect ValueError only for missing required fields
    with pytest.raises(ValueError):
        EmercoinConnection(test_config)

@given(method_call=method_call_strategy)
def test_rpc_call_formats(method_call):
    """Test that RPC calls are formatted correctly with various methods and parameters."""
    # Get default config
    config = default_config()
    
    # Setup mock response
    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'result': 'success', 'error': None, 'id': 1}
        mock_post.return_value = mock_response
        
        # Create connection and make call
        connection = EmercoinConnection(config)
        result = connection.call(method_call['method'], method_call['params'])
        
        # Verify the call was formatted correctly
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        
        # Check URL and auth
        assert kwargs['url'] == config['rpc_url']
        assert kwargs['auth'] == (config['rpc_user'], config['rpc_password'])
        
        # Check request payload
        payload = json.loads(kwargs['data'])
        assert payload['method'] == method_call['method']
        assert payload['params'] == method_call['params']
        assert payload['jsonrpc'] == '2.0'
        assert 'id' in payload

@given(auth_status=st.sampled_from([401, 403]))  # Only test the exact status codes handled
def test_auth_error_handling(auth_status):
    """Test that authentication errors are correctly handled."""
    # Create config directly in the test
    config = default_config()
    
    # Setup mock response with auth error
    with patch('requests.post') as mock_post:
        # Create a more complete mock response
        mock_response = Mock(spec=requests.Response)
        mock_response.status_code = auth_status
        
        # Make raise_for_status() not do anything
        mock_response.raise_for_status = Mock()
        
        # Configure the mock to return our response
        mock_post.return_value = mock_response
        
        # Create connection and test auth error handling
        connection = EmercoinConnection(config)
        
        with pytest.raises(AuthError):
            connection.call('getinfo')


@given(
    retry_count=st.integers(min_value=1, max_value=5),
    success_index=st.integers(min_value=0, max_value=4)
)
def test_retry_behavior(retry_count, success_index):
    """Test that the connection retries failed requests according to its configuration."""
    assume(success_index < retry_count)
    
    # Get default config
    config = default_config()
    
    # Create side effects: ConnectionError for all attempts except the success_index
    side_effects = []
    for i in range(retry_count):
        if i == success_index:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'result': 'success', 'error': None, 'id': 1}
            side_effects.append(mock_resp)
        else:
            side_effects.append(RequestsConnectionError("Failed to connect"))
    
    with patch('requests.post') as mock_post:
        mock_post.side_effect = side_effects
        
        # Create connection with configured retry count
        test_config = config.copy()
        test_config['max_retries'] = retry_count
        test_config['retry_delay'] = 0  # Set to 0 for faster tests
        
        connection = EmercoinConnection(test_config)
        
        # This should succeed on the success_index attempt
        if success_index < retry_count:
            result = connection.call('getinfo')
            assert result == 'success'
            assert mock_post.call_count == success_index + 1
        else:
            # Should fail if success_index is beyond retry limit
            with pytest.raises(ConnectionError):
                connection.call('getinfo')


@given(
    url=st.text(min_size=1, max_size=100).filter(lambda x: not x.startswith('http')),
    custom_message=st.text()
)
def test_invalid_url_handling(url, custom_message):
    """Test that the connection handles invalid URLs appropriately."""
    # Get the configuration
    config = default_config()
    
    with patch('requests.post') as mock_post:
        mock_post.side_effect = RequestException(custom_message)
        
        # Create connection with invalid URL
        test_config = config.copy()
        test_config['rpc_url'] = url
        
        connection = EmercoinConnection(test_config)
        
        with pytest.raises(ConnectionError) as excinfo:
            connection.call('getinfo')
            
        # Verify error message contains useful information
        assert custom_message in str(excinfo.value) or 'Failed to connect' in str(excinfo.value)