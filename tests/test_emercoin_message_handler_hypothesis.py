import pytest
from unittest.mock import patch, MagicMock
import unittest.mock as mock
import time
from hypothesis import given, strategies as st, settings, assume, example
from helper.message import BaseMessage
from helper.finite_state_machine import BaseStateMachine, State
from emercoin.emercoin_message_handler import EmercoinMessageHandler, SecurityError
from emercoin.emercoin_connection_handler import ConnectionError, AuthError, RPCError
import emercoin.emercoin_message


@pytest.fixture
def service_mock():
    """Create a mock Emercoin service."""
    return mock.Mock()


@pytest.fixture
def auth_service_mock():
    """Create a mock authentication service."""
    auth_mock = mock.Mock()
    # Default behavior - allow operations
    auth_mock.validate_token.return_value = True
    auth_mock.check_permission.return_value = True
    return auth_mock


@pytest.fixture
def handler(service_mock, auth_service_mock):
    """Create an Emercoin message handler with mocked dependencies."""
    return EmercoinMessageHandler(service_mock, auth_service_mock)


# ----- Test Strategies -----

# Message IDs
message_id_strategy = st.text(min_size=1, max_size=50).filter(lambda x: x and not x.isspace())

# User IDs
user_id_strategy = st.text(min_size=1, max_size=50).filter(lambda x: x and not x.isspace())

# Authentication tokens
auth_token_strategy = st.text(min_size=10, max_size=100)

# Emercoin names following the namespace:value format
name_strategy = st.one_of(
    st.from_regex(r'dns:[a-zA-Z0-9_\-\.]{1,100}', fullmatch=True),
    st.from_regex(r'id:[a-zA-Z0-9_\-\.]{1,100}', fullmatch=True),
    st.from_regex(r'ssl:[a-zA-Z0-9_\-\.]{1,100}', fullmatch=True),
    st.from_regex(r'ssh:[a-zA-Z0-9_\-\.]{1,100}', fullmatch=True),
    st.from_regex(r'test:[a-zA-Z0-9_\-\.]{1,100}', fullmatch=True)
)

# Emercoin values
value_strategy = st.text(max_size=512)

# Options for name operations
options_strategy = st.fixed_dictionaries({
    'days': st.integers(min_value=1, max_value=365)
})

# Read operation message types
read_message_type_strategy = st.sampled_from([
    'emercoin_get_info',
    'emercoin_name_show',
    'emercoin_name_history',
    'emercoin_name_filter'
])

# Write operation message types
write_message_type_strategy = st.sampled_from([
    'emercoin_name_new',
    'emercoin_name_update'
])

# All message types
message_type_strategy = st.one_of(read_message_type_strategy, write_message_type_strategy)

# Invalid message types
invalid_message_type_strategy = st.text(min_size=1, max_size=50).filter(
    lambda x: x not in [
        'emercoin_get_info', 'emercoin_name_show', 'emercoin_name_history',
        'emercoin_name_filter', 'emercoin_name_new', 'emercoin_name_update'
    ]
)

# Blockchain info response
info_strategy = st.fixed_dictionaries({
    'version': st.text(min_size=1, max_size=20),
    'blocks': st.integers(min_value=0, max_value=1000000),
    'balance': st.floats(min_value=0, max_value=1000000),
    'connections': st.integers(min_value=0, max_value=100),
    'testnet': st.booleans(),
    'errors': st.text(max_size=200)
})

# Name record response
record_strategy = st.fixed_dictionaries({
    'name': name_strategy,
    'value': value_strategy,
    'txid': st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'),
    'address': st.text(min_size=30, max_size=34, alphabet='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'),
    'expires_in': st.integers(min_value=0, max_value=100000),
    'expires_at': st.integers(min_value=0),
    'time': st.integers(min_value=0)
})

# Error codes and messages
error_code_strategy = st.integers(min_value=-32099, max_value=-32000)
error_message_strategy = st.text(min_size=1, max_size=100)


# ----- Basic Message Handling Tests -----

@given(
    message_id=message_id_strategy,
    info=info_strategy
)
def test_handle_get_info_message(handler, service_mock, message_id, info):
    """Test handling of emercoin_get_info messages."""
    # Create message
    message = Message(
        message_type='emercoin_get_info',
        payload={},
        message_id=message_id
    )
    
    # Mock service response
    service_mock.get_blockchain_info.return_value = info
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response
    assert response.message_type == 'emercoin_get_info_response'
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'success'
    assert response.payload['data'] == info


@given(
    message_id=message_id_strategy,
    name=name_strategy,
    record=record_strategy
)
def test_handle_name_show_message(handler, service_mock, message_id, name, record):
    """Test handling of emercoin_name_show messages."""
    # Update record name to match query
    record_copy = record.copy()
    record_copy['name'] = name
    
    # Create message
    message = Message(
        message_type='emercoin_name_show',
        payload={'name': name},
        message_id=message_id
    )
    
    # Mock service response
    service_mock.name_show.return_value = record_copy
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response
    assert response.message_type == 'emercoin_name_show_response'
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'success'
    assert response.payload['data'] == record_copy
    
    # Verify service call
    service_mock.name_show.assert_called_once_with(name)


@given(
    message_id=message_id_strategy,
    name=name_strategy,
    records=st.lists(record_strategy, min_size=0, max_size=5)
)
def test_handle_name_history_message(handler, service_mock, message_id, name, records):
    """Test handling of emercoin_name_history messages."""
    # Update all record names to match query
    modified_records = []
    for record in records:
        record_copy = record.copy()
        record_copy['name'] = name
        modified_records.append(record_copy)
    
    # Create message
    message = Message(
        message_type='emercoin_name_history',
        payload={'name': name},
        message_id=message_id
    )
    
    # Mock service response
    service_mock.name_history.return_value = modified_records
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response
    assert response.message_type == 'emercoin_name_history_response'
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'success'
    assert response.payload['data'] == modified_records
    
    # Verify service call
    service_mock.name_history.assert_called_once_with(name)


@given(
    message_id=message_id_strategy,
    regex=st.one_of(st.just('dns:'), st.just('id:'), st.just('test:')),
    records=st.lists(record_strategy, min_size=0, max_size=5)
)
def test_handle_name_filter_message(handler, service_mock, message_id, regex, records):
    """Test handling of emercoin_name_filter messages."""
    # Update all record names to match filter
    modified_records = []
    prefix = regex.split(':')[0]
    for record in records:
        record_copy = record.copy()
        record_copy['name'] = f"{prefix}:example"
        modified_records.append(record_copy)
    
    # Create message
    message = Message(
        message_type='emercoin_name_filter',
        payload={'regex': regex},
        message_id=message_id
    )
    
    # Mock service response
    service_mock.name_filter.return_value = modified_records
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response
    assert response.message_type == 'emercoin_name_filter_response'
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'success'
    assert response.payload['data'] == modified_records
    
    # Verify service call
    service_mock.name_filter.assert_called_once_with(regex)


@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    name=name_strategy,
    value=value_strategy,
    options=options_strategy,
    auth_token=auth_token_strategy
)
def test_handle_name_new_message(handler, service_mock, auth_service_mock, 
                               message_id, user_id, name, value, options, auth_token):
    """Test handling of emercoin_name_new messages."""
    # Create message
    message = Message(
        message_type='emercoin_name_new',
        payload={
            'name': name,
            'value': value,
            'options': options,
            'auth_token': auth_token
        },
        message_id=message_id,
        source_id=user_id
    )
    
    # Configure auth service
    auth_service_mock.validate_token.return_value = True
    auth_service_mock.check_permission.return_value = True
    
    # Mock service response
    expected_txid = '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef'
    service_mock.name_new.return_value = expected_txid
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response
    assert response.message_type == 'emercoin_name_new_response'
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'success'
    assert response.payload['data']['txid'] == expected_txid
    
    # Verify service call
    service_mock.name_new.assert_called_once_with(name, value, options)
    
    # Verify auth calls
    auth_service_mock.validate_token.assert_called_once_with(user_id, auth_token)
    auth_service_mock.check_permission.assert_called_once_with(user_id, 'emercoin:write')


@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    name=name_strategy,
    value=value_strategy,
    options=options_strategy,
    auth_token=auth_token_strategy
)
def test_handle_name_update_message(handler, service_mock, auth_service_mock,
                                  message_id, user_id, name, value, options, auth_token):
    """Test handling of emercoin_name_update messages."""
    # Create message
    message = Message(
        message_type='emercoin_name_update',
        payload={
            'name': name,
            'value': value,
            'options': options,
            'auth_token': auth_token
        },
        message_id=message_id,
        source_id=user_id
    )
    
    # Configure auth service
    auth_service_mock.validate_token.return_value = True
    auth_service_mock.check_permission.return_value = True
    
    # Mock service response
    expected_txid = 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890'
    service_mock.name_update.return_value = expected_txid
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response
    assert response.message_type == 'emercoin_name_update_response'
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'success'
    assert response.payload['data']['txid'] == expected_txid
    
    # Verify service call
    service_mock.name_update.assert_called_once_with(name, value, options)
    
    # Verify auth calls
    auth_service_mock.validate_token.assert_called_once_with(user_id, auth_token)
    auth_service_mock.check_permission.assert_called_once_with(user_id, 'emercoin:write')


# ----- Error Handling Tests -----

@given(
    message_type=message_type_strategy,
    message_id=message_id_strategy,
    error_code=error_code_strategy,
    error_message=error_message_strategy
)
def test_handle_rpc_error(handler, service_mock, message_type, message_id, error_code, error_message):
    """Test handling of RPC errors for various message types."""
    # Create a message with minimal required fields
    payload = {}
    if message_type == 'emercoin_name_show' or message_type == 'emercoin_name_history':
        payload = {'name': 'test:example'}
    elif message_type == 'emercoin_name_filter':
        payload = {'regex': 'test:'}
    elif message_type == 'emercoin_name_new' or message_type == 'emercoin_name_update':
        payload = {
            'name': 'test:example', 
            'value': 'test', 
            'options': {'days': 30},
            'auth_token': 'valid_token'
        }
            
    message = Message(
        message_type=message_type,
        payload=payload,
        message_id=message_id,
        source_id='test_user'
    )
    
    # Configure the service mock to raise an RPC error
    error = RPCError(error_code, error_message)
    
    if message_type == 'emercoin_get_info':
        service_mock.get_blockchain_info.side_effect = error
    elif message_type == 'emercoin_name_show':
        service_mock.name_show.side_effect = error
    elif message_type == 'emercoin_name_history':
        service_mock.name_history.side_effect = error
    elif message_type == 'emercoin_name_filter':
        service_mock.name_filter.side_effect = error
    elif message_type == 'emercoin_name_new':
        service_mock.name_new.side_effect = error
    elif message_type == 'emercoin_name_update':
        service_mock.name_update.side_effect = error
        
    # Process message
    response = handler.handle_message(message)
    
    # Expected response type
    expected_response_type = f"{message_type}_response"
    
    # Verify response
    assert response.message_type == expected_response_type
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'error'
    assert response.payload['error']['type'] == 'rpc_error'
    assert 'code' in response.payload['error']
    assert response.payload['error']['code'] == error_code
    assert 'message' in response.payload['error']
    assert error_message in response.payload['error']['message']


@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    read_message_type=read_message_type_strategy
)
def test_handle_connection_error(handler, service_mock, message_id, user_id, read_message_type):
    """Test handling of connection errors."""
    # Create a message
    payload = {}
    if read_message_type == 'emercoin_name_show' or read_message_type == 'emercoin_name_history':
        payload = {'name': 'test:example'}
    elif read_message_type == 'emercoin_name_filter':
        payload = {'regex': 'test:'}
    
    message = Message(
        message_type=read_message_type,
        payload=payload,
        message_id=message_id,
        source_id=user_id
    )
    
    # Configure the service mock to raise a connection error
    error_message = "Failed to connect to Emercoin node: Connection refused"
    
    if read_message_type == 'emercoin_get_info':
        service_mock.get_blockchain_info.side_effect = ConnectionError(error_message)
    elif read_message_type == 'emercoin_name_show':
        service_mock.name_show.side_effect = ConnectionError(error_message)
    elif read_message_type == 'emercoin_name_history':
        service_mock.name_history.side_effect = ConnectionError(error_message)
    elif read_message_type == 'emercoin_name_filter':
        service_mock.name_filter.side_effect = ConnectionError(error_message)
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response
    assert response.message_type == f"{read_message_type}_response"
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'error'
    assert response.payload['error']['type'] == 'connection_error'
    assert error_message in response.payload['error']['message']


@given(
    message_id=message_id_strategy,
    invalid_message_type=invalid_message_type_strategy
)
@example(message_id='test_id', invalid_message_type='unknown_type')
def test_handle_unknown_message_type(handler, message_id, invalid_message_type):
    """Test handling of unknown message types."""
    # Create message with unknown type
    message = Message(
        message_type=invalid_message_type,
        payload={},
        message_id=message_id
    )
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response
    assert response.message_type == 'error_response'
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'error'
    assert response.payload['error']['type'] == 'unsupported_message'
    assert 'Unsupported message type' in response.payload['error']['message']


@given(
    message_type=st.sampled_from(['emercoin_name_show', 'emercoin_name_history']),
    message_id=message_id_strategy
)
def test_handle_missing_required_field(handler, message_type, message_id):
    """Test handling of messages with missing required fields."""
    # Create message with empty payload (missing required 'name' field)
    message = Message(
        message_type=message_type,
        payload={},  # Missing required 'name' field
        message_id=message_id
    )
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response
    assert response.message_type == f"{message_type}_response"
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'error'
    assert response.payload['error']['type'] == 'validation_error'
    assert 'Missing required field' in response.payload['error']['message']


# ----- Security Tests -----

@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy
)
def test_read_operation_without_auth(handler, service_mock, auth_service_mock, message_id, user_id):
    """Test that read operations can proceed without authentication."""
    # Create a read-only message
    message = Message(
        message_type='emercoin_get_info',
        payload={},
        message_id=message_id,
        source_id=user_id
    )
    
    # Configure auth service to return False for token validation
    auth_service_mock.validate_token.return_value = False
    
    # Configure service to return a successful response
    service_mock.get_blockchain_info.return_value = {'version': '0.7.11-emc'}
    
    # Process message
    response = handler.handle_message(message)
    
    # Auth service should not be called for read operations
    auth_service_mock.validate_token.assert_not_called()
    
    # Verify response is successful
    assert response.message_type == 'emercoin_get_info_response'
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'success'


@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    write_message_type=write_message_type_strategy
)
def test_write_operation_without_auth_token(handler, service_mock, message_id, user_id, write_message_type):
    """Test that write operations fail without an auth token."""
    # Create payload with required fields but no auth token
    payload = {
        'name': 'test:example',
        'value': 'test_value',
        'options': {'days': 30}
        # No auth_token
    }
    
    # Create a write operation message
    message = Message(
        message_type=write_message_type,
        payload=payload,
        message_id=message_id,
        source_id=user_id
    )
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response is an error
    assert response.message_type == f"{write_message_type}_response"
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'error'
    assert response.payload['error']['type'] == 'authorization_error'
    assert 'Auth token required' in response.payload['error']['message']


@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    auth_token=auth_token_strategy,
    write_message_type=write_message_type_strategy
)
def test_write_operation_with_invalid_auth(handler, service_mock, auth_service_mock,
                                          message_id, user_id, auth_token, write_message_type):
    """Test that write operations fail with invalid authentication."""
    # Create a write operation message
    message = Message(
        message_type=write_message_type,
        payload={
            'name': 'test:example',
            'value': 'test_value',
            'options': {'days': 30},
            'auth_token': auth_token
        },
        message_id=message_id,
        source_id=user_id
    )
    
    # Configure auth service to return False for token validation
    auth_service_mock.validate_token.return_value = False
    
    # Process message
    response = handler.handle_message(message)
    
    # Auth service should be called for write operations
    auth_service_mock.validate_token.assert_called_once_with(user_id, auth_token)
    
    # Verify response is an error
    assert response.message_type == f"{write_message_type}_response"
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'error'
    assert response.payload['error']['type'] == 'authorization_error'
    assert 'Invalid authentication token' in response.payload['error']['message']


@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    auth_token=auth_token_strategy,
    write_message_type=write_message_type_strategy
)
def test_write_operation_without_permission(handler, service_mock, auth_service_mock,
                                           message_id, user_id, auth_token, write_message_type):
    """Test that write operations fail without proper permissions."""
    # Create a write operation message
    message = Message(
        message_type=write_message_type,
        payload={
            'name': 'test:example',
            'value': 'test_value',
            'options': {'days': 30},
            'auth_token': auth_token
        },
        message_id=message_id,
        source_id=user_id
    )
    
    # Configure auth service to return True for token validation but False for permission check
    auth_service_mock.validate_token.return_value = True
    auth_service_mock.check_permission.return_value = False
    
    # Process message
    response = handler.handle_message(message)
    
    # Auth service should be called for write operations
    auth_service_mock.validate_token.assert_called_once_with(user_id, auth_token)
    auth_service_mock.check_permission.assert_called_once_with(user_id, 'emercoin:write')
    
    # Verify response is an error
    assert response.message_type == f"{write_message_type}_response"
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'error'
    assert response.payload['error']['type'] == 'authorization_error'
    assert 'does not have write permission' in response.payload['error']['message']


def test_rate_limiting(handler, service_mock, auth_service_mock):
    """Test that rate limiting works for different security levels."""
    # Create a user ID and message template
    user_id = "test_user"
    
    # Test rate limiting for read operations
    read_message = Message(
        message_type='emercoin_get_info',
        payload={},
        message_id='read_test',
        source_id=user_id
    )
    
    # Configure service to return a successful response
    service_mock.get_blockchain_info.return_value = {'version': '0.7.11-emc'}
    
    # Set a low rate limit for testing
    handler.rate_limits = {
        handler.SECURITY_LEVEL_READ: {'max_requests': 2, 'period': 60}
    }
    
    # First two requests should succeed
    for i in range(2):
        response = handler.handle_message(read_message)
        assert response.payload['status'] == 'success'
    
    # Third request should fail with rate limit error
    response = handler.handle_message(read_message)
    assert response.payload['status'] == 'error'
    assert response.payload['error']['type'] == 'rate_limit_error'
    assert 'Rate limit exceeded' in response.payload['error']['message']
    
    # Reset rate limit counters
    handler._rate_limit_counters = {}
    
    # Test rate limiting for write operations
    write_message = Message(
        message_type='emercoin_name_new',
        payload={
            'name': 'test:example',
            'value': 'test_value',
            'options': {'days': 30},
            'auth_token': 'valid_token'
        },
        message_id='write_test',
        source_id=user_id
    )
    
    # Configure auth service to approve the operation
    auth_service_mock.validate_token.return_value = True
    auth_service_mock.check_permission.return_value = True
    
    # Configure service to return a successful response
    service_mock.name_new.return_value = 'txid_12345'
    
    # Set a low rate limit for testing
    handler.rate_limits = {
        handler.SECURITY_LEVEL_WRITE: {'max_requests': 1, 'period': 60}
    }
    
    # First request should succeed
    response = handler.handle_message(write_message)
    assert response.payload['status'] == 'success'
    
    # Second request should fail with rate limit error
    response = handler.handle_message(write_message)
    assert response.payload['status'] == 'error'
    assert response.payload['error']['type'] == 'rate_limit_error'
    assert 'Rate limit exceeded' in response.payload['error']['message']


def test_rate_limit_reset(handler, service_mock):
    """Test that rate limits reset after the specified period."""
    # Create a user ID and message
    user_id = "test_user"
    message = Message(
        message_type='emercoin_get_info',
        payload={},
        message_id='reset_test',
        source_id=user_id
    )
    
    # Configure service to return a successful response
    service_mock.get_blockchain_info.return_value = {'version': '0.7.11-emc'}
    
    # Set a low rate limit with a short period for testing
    handler.rate_limits = {
        handler.SECURITY_LEVEL_READ: {'max_requests': 1, 'period': 0.1}  # 100ms
    }
    
    # First request should succeed
    response = handler.handle_message(message)
    assert response.payload['status'] == 'success'
    
    # Second request should fail with rate limit error
    response = handler.handle_message(message)
    assert response.payload['status'] == 'error'
    
    # Wait for the rate limit period to expire
    time.sleep(0.2)  # 200ms
    
    # Next request should succeed
    response = handler.handle_message(message)
    assert response.payload['status'] == 'success'


@mock.patch('emercoin.emercoin_message_handler.logger')
def test_audit_logging(mock_logger, handler, service_mock, auth_service_mock):
    """Test that write operations are logged for audit purposes."""
    # Create a user ID and message
    user_id = "test_user"
    message = Message(
        message_type='emercoin_name_new',
        payload={
            'name': 'test:example',
            'value': 'test_value',
            'options': {'days': 30},
            'auth_token': 'valid_token'
        },
        message_id='audit_test',
        source_id=user_id
    )
    
    # Configure auth service to approve the operation
    auth_service_mock.validate_token.return_value = True
    auth_service_mock.check_permission.return_value = True
    
    # Configure service to return a successful response
    expected_txid = 'txid_12345'
    service_mock.name_new.return_value = expected_txid
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify audit log was called
    mock_logger.info.assert_called()
    audit_log_message = mock_logger.info.call_args[0][0]
    assert 'AUDIT' in audit_log_message
    assert user_id in audit_log_message
    assert 'name_new' in audit_log_message
    assert expected_txid in str(mock_logger.info.call_args)


# ----- Edge Case Tests -----

def test_no_auth_service_configured(service_mock):
    """Test behavior when no auth service is configured."""
    # Create handler without auth service
    handler = EmercoinMessageHandler(service_mock)
    
    # Create a write operation message
    message = Message(
        message_type='emercoin_name_new',
        payload={
            'name': 'test:example',
            'value': 'test_value',
            'options': {'days': 30},
            'auth_token': 'valid_token'
        },
        message_id='test_id',
        source_id='test_user'
    )
    
    # Mock service response
    service_mock.name_new.return_value = 'txid_12345'
    
    # In development mode (no auth service), this should log a warning but proceed
    with mock.patch('emercoin.emercoin_message_handler.logger') as mock_logger:
        response = handler.handle_message(message)
        
        # Should log a warning
        mock_logger.warning.assert_called()
        warning_message = mock_logger.warning.call_args[0][0]
        assert 'but write operation requested' in warning_message
        
        # But should still succeed
        assert response.payload['status'] == 'success'


@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    name=name_strategy,
    value=value_strategy,
    days=st.integers(min_value=1, max_value=365),
    auth_token=auth_token_strategy
)
def test_message_with_different_options_format(handler, service_mock, auth_service_mock,
                                             message_id, user_id, name, value, days, auth_token):
    """Test handling of messages with different options format."""
    # Create message with simple days value instead of options dictionary
    message = Message(
        message_type='emercoin_name_new',
        payload={
            'name': name,
            'value': value,
            'days': days,  # Not nested in 'options'
            'auth_token': auth_token
        },
        message_id=message_id,
        source_id=user_id
    )
    
    # Configure auth service to approve the operation
    auth_service_mock.validate_token.return_value = True
    auth_service_mock.check_permission.return_value = True
    
    # Configure service to return a successful response
    expected_txid = 'txid_12345'
    service_mock.name_new.return_value = expected_txid
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response
    assert response.message_type == 'emercoin_name_new_response'
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'success'
    assert response.payload['data']['txid'] == expected_txid
    
    # Verify service call - should convert days to options
    expected_options = {'days': days}
    service_mock.name_new.assert_called_once_with(name, value, expected_options)


@given(
    message_id=message_id_strategy
)
def test_extremely_long_value(handler, service_mock, auth_service_mock, message_id):
    """Test handling of messages with extremely long values."""
    # Create message with extremely long value
    very_long_value = "x" * 5000  # Emercoin typically has a 520-byte limit
    
    message = Message(
        message_type='emercoin_name_new',
        payload={
            'name': 'test:example',
            'value': very_long_value,
            'options': {'days': 30},
            'auth_token': 'valid_token'
        },
        message_id=message_id,
        source_id='test_user'
    )
    
    # Configure auth service to approve the operation
    auth_service_mock.validate_token.return_value = True
    auth_service_mock.check_permission.return_value = True
    
    # Configure service to raise an RPC error about value too long
    service_mock.name_new.side_effect = RPCError(-32000, "Value too long")
    
    # Process message
    response = handler.handle_message(message)
    
    # Verify response contains the error
    assert response.message_type == 'emercoin_name_new_response'
    assert response.correlation_id == message_id
    assert response.payload['status'] == 'error'
    assert response.payload['error']['type'] == 'rpc_error'
    assert "Value too long" in response.payload['error']['message']


@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy
)
def test_multiple_error_types(handler, service_mock, auth_service_mock, message_id, user_id):
    """Test handling of multiple error types in sequence."""
    # Create a message
    message = Message(
        message_type='emercoin_get_info',
        payload={},
        message_id=message_id,
        source_id=user_id
    )
    
    # 1. Test with connection error
    service_mock.get_blockchain_info.side_effect = ConnectionError("Failed to connect")
    response1 = handler.handle_message(message)
    assert response1.payload['status'] == 'error'
    assert response1.payload['error']['type'] == 'connection_error'
    
    # 2. Test with auth error
    service_mock.get_blockchain_info.side_effect = AuthError("Authentication failed")
    response2 = handler.handle_message(message)
    assert response2.payload['status'] == 'error'
    assert response2.payload['error']['type'] == 'auth_error'
    
    # 3. Test with RPC error
    service_mock.get_blockchain_info.side_effect = RPCError(-32000, "RPC error")
    response3 = handler.handle_message(message)
    assert response3.payload['status'] == 'error'
    assert response3.payload['error']['type'] == 'rpc_error'
    
    # 4. Test with generic exception
    service_mock.get_blockchain_info.side_effect = Exception("Unexpected error")
    response4 = handler.handle_message(message)
    assert response4.payload['status'] == 'error'
    assert response4.payload['error']['type'] == 'internal_error'


@settings(max_examples=5)
@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    name=st.text(min_size=1, max_size=300)  # Potentially invalid names
)
def test_invalid_name_validation(handler, service_mock, auth_service_mock, message_id, user_id, name):
    """Test validation of invalid name formats."""
    # Create message with potentially invalid name
    message = Message(
        message_type='emercoin_name_show',
        payload={'name': name},
        message_id=message_id,
        source_id=user_id
    )
    
    # Configure service to validate and potentially reject the name
    service_mock.name_show.side_effect = ValueError(f"Invalid name format: {name}")
    
    # Process message
    response = handler.handle_message(message)
    
    # Check if response indicates validation error
    if not name or ':' not in name or len(name) > 255:
        assert response.message_type == 'emercoin_name_show_response'
        assert response.correlation_id == message_id
        assert response.payload['status'] == 'error'
        assert response.payload['error']['type'] == 'validation_error'
        assert f"Invalid name format: {name}" in response.payload['error']['message']