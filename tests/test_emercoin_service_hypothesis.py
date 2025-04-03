import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume, example
from emercoin.module.emercoin_service import EmercoinService
from emercoin.emercoin_connection_handler import ConnectionError, AuthError, RPCError


@pytest.fixture
def default_config():
    return {
        'rpc_url': 'http://localhost:6662',
        'rpc_user': 'test_user',
        'rpc_password': 'test_password',
        'timeout': 10,
        'max_retries': 3,
        'retry_delay': 1,
        'use_queue': False
    }

@pytest.fixture
def service(default_config):
    return EmercoinService(default_config)

# Strategy for valid Emercoin name-value records
name_value_strategy = st.fixed_dictionaries({
    'name': st.one_of(
        st.from_regex(r'dns:[a-zA-Z0-9_\-\.]{1,100}', fullmatch=True),
        st.from_regex(r'id:[a-zA-Z0-9_\-\.]{1,100}', fullmatch=True),
        st.from_regex(r'ssl:[a-zA-Z0-9_\-\.]{1,100}', fullmatch=True),
        st.from_regex(r'ssh:[a-zA-Z0-9_\-\.]{1,100}', fullmatch=True),
        st.from_regex(r'test:[a-zA-Z0-9_\-\.]{1,100}', fullmatch=True)
    ),
    'value': st.text(max_size=512),
    'days': st.integers(min_value=1, max_value=365)
})

# Strategy for name_filter regex patterns
name_filter_strategy = st.one_of(
    st.just('dns:'),
    st.just('id:'),
    st.just('ssl:'),
    st.just('ssh:'),
    st.just('test:'),
    st.from_regex(r'[a-z]+:.+', fullmatch=True)
)


@given(info=st.fixed_dictionaries({
    'version': st.text(),
    'protocolversion': st.integers(),
    'walletversion': st.integers(),
    'balance': st.floats(min_value=0, max_value=1000000),
    'blocks': st.integers(min_value=0),
    'timeoffset': st.integers(),
    'connections': st.integers(min_value=0, max_value=100),
    'difficulty': st.floats(min_value=0),
    'testnet': st.booleans(),
    'errors': st.text()
}))
def test_get_blockchain_info(service, info):
    """Test get_blockchain_info with various info structures."""
    # Setup mock
    with mock.patch('emercoin.emercoin_connection.EmercoinConnection.call') as mock_call:
        mock_call.return_value = info
        
        # Call the service
        result = service.get_blockchain_info()
        
        # Verify results match mock data
        assert result == info
        mock_call.assert_called_once_with('getinfo')


@given(record=st.fixed_dictionaries({
    'name': st.text(min_size=1, max_size=255),
    'value': st.text(max_size=512),
    'txid': st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'),
    'address': st.text(min_size=30, max_size=34),
    'expires_in': st.integers(min_value=0),
    'expires_at': st.integers(min_value=0),
    'time': st.integers(min_value=0)
}))
def test_name_show(service, record):
    """Test name_show with various record structures."""
    # Setup mock
    with mock.patch('emercoin.emercoin_connection.EmercoinConnection.call') as mock_call:
        mock_call.return_value = record
        
        # Call the service with the record name
        result = service.name_show(record['name'])
        
        # Verify results match mock data
        assert result == record
        mock_call.assert_called_once_with('name_show', [record['name']])


@given(records=st.lists(
    st.fixed_dictionaries({
        'name': st.text(min_size=1, max_size=255),
        'value': st.text(max_size=512),
        'txid': st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'),
        'address': st.text(min_size=30, max_size=34),
        'expires_in': st.integers(min_value=0),
        'expires_at': st.integers(min_value=0),
        'time': st.integers(min_value=0)
    }),
    min_size=0, max_size=10
))
def test_name_history(service, records):
    """Test name_history with various record collections."""
    # Setup mock
    with mock.patch('emercoin.emercoin_connection.EmercoinConnection.call') as mock_call:
        mock_call.return_value = records
        
        # Use the first record's name or a default if empty
        name = records[0]['name'] if records else 'test:example'
        
        # Call the service
        result = service.name_history(name)
        
        # Verify results match mock data
        assert result == records
        mock_call.assert_called_once_with('name_history', [name])


@given(pattern=name_filter_strategy)
def test_name_filter(service, pattern):
    """Test name_filter with various filter patterns."""
    # Setup a mock response with records matching the pattern
    with mock.patch('emercoin.emercoin_connection.EmercoinConnection.call') as mock_call:
        mock_records = [
            {
                'name': f"{pattern.split(':')[0]}:example1",
                'value': 'test_value_1',
                'txid': '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
                'expires_in': 15000
            },
            {
                'name': f"{pattern.split(':')[0]}:example2",
                'value': 'test_value_2',
                'txid': 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
                'expires_in': 10000
            }
        ]
        mock_call.return_value = mock_records
        
        # Call the service
        result = service.name_filter(pattern)
        
        # Verify results match mock data
        assert result == mock_records
        mock_call.assert_called_once_with('name_filter', [pattern])


@given(record=name_value_strategy)
def test_name_new(service, record):
    """Test name_new with various name-value records."""
    # Setup mock
    with mock.patch('emercoin.emercoin_connection.EmercoinConnection.call') as mock_call:
        expected_txid = '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef'
        mock_call.return_value = expected_txid
        
        # Create options dict
        options = {'days': record['days']}
        
        # Call the service
        result = service.name_new(record['name'], record['value'], options)
        
        # Verify results and call parameters
        assert result == expected_txid
        mock_call.assert_called_once_with('name_new', [record['name'], record['value'], options])


@given(record=name_value_strategy)
def test_name_update(service, record):
    """Test name_update with various name-value records."""
    # Setup mock
    with mock.patch('emercoin.emercoin_connection.EmercoinConnection.call') as mock_call:
        expected_txid = 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890'
        mock_call.return_value = expected_txid
        
        # Create options dict
        options = {'days': record['days']}
        
        # Call the service
        result = service.name_update(record['name'], record['value'], options)
        
        # Verify results and call parameters
        assert result == expected_txid
        mock_call.assert_called_once_with('name_update', [record['name'], record['value'], options])


@given(name=st.text(min_size=1, max_size=255))
def test_validate_name(service, name):
    """Test name validation with various input strings."""
    # Valid name should have a namespace prefix with colon
    is_valid = ':' in name and len(name.split(':')[0]) > 0 and len(name.split(':')[1]) > 0
    
    # Names shouldn't be too long
    is_valid = is_valid and len(name) <= 255
    
    # Call the validation method
    result = service.validate_name(name)
    
    # Built-in validation may have additional checks, but should at least
    # match our basic validation logic
    if not is_valid:
        assert result == False


@settings(max_examples=20)
@given(name=st.text(min_size=1, max_size=255))
@example("test:example")  # Always include this known good example
@example("invalid_name")  # Always include this known bad example
@example(":")  # Edge case: empty prefix and value
@example("test:")  # Edge case: empty value
@example(":test")  # Edge case: empty prefix
def test_validate_name_edge_cases(service, name):
    """Test name validation with specific edge cases."""
    # Call the validation method
    result = service.validate_name(name)
    
    # For the specific examples, verify expected results
    if name == "test:example":
        assert result == True
    elif name in ["invalid_name", ":", "test:", ":test"]:
        assert result == False


@given(
    error_code=st.integers(min_value=-32099, max_value=-32000),
    error_message=st.text(min_size=1, max_size=100)
)
def test_rpc_error_handling(service, error_code, error_message):
    """Test RPC error handling in the service layer."""
    # Setup mock to raise RPC error
    with mock.patch('emercoin.emercoin_connection.EmercoinConnection.call') as mock_call:
        mock_call.side_effect = RPCError(error_code, error_message)
        
        # Call a service method that uses the mock
        with pytest.raises(RPCError) as excinfo:
            service.get_blockchain_info()
            
        # Verify error details
        assert excinfo.value.code == error_code
        assert excinfo.value.message == error_message