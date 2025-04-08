import pytest
from unittest.mock import patch, MagicMock
import unittest.mock as mock
import time
from contextlib import contextmanager
from hypothesis import given, strategies as st, settings, assume, example, HealthCheck
from emercoin.emercoin_message_handler import EmercoinMessageHandler, SecurityError
from emercoin.emercoin_connection_handler import ConnectionError, AuthError, RPCError
from emercoin.emercoin_message import (
    EmercoinBaseMessage, 
    EmercoinInfoRequestMessage,
    EmercoinInfoResponseMessage,
    EmercoinNameShowRequestMessage, 
    EmercoinNameShowResponseMessage,
    EmercoinNameHistoryRequestMessage,
    EmercoinNameHistoryResponseMessage,
    EmercoinNameFilterRequestMessage,
    EmercoinNameFilterResponseMessage,
    EmercoinNameNewRequestMessage,
    EmercoinNameNewResponseMessage,
    EmercoinNameUpdateRequestMessage,
    EmercoinNameUpdateResponseMessage
)


# ----- Message Factory Functions -----

def create_info_request(message_id, user_id=None):
    """Create an EmercoinInfoRequestMessage for testing"""
    message = EmercoinInfoRequestMessage()
    message.id = message_id
    message.user_id = user_id or "test_user"
    return message


def create_name_show_request(message_id, user_id, name):
    """Create an EmercoinNameShowRequestMessage for testing"""
    message = EmercoinNameShowRequestMessage()
    message.id = message_id
    message.user_id = user_id
    message.name = name
    return message


def create_name_history_request(message_id, user_id, name):
    """Create an EmercoinNameHistoryRequestMessage for testing"""
    message = EmercoinNameHistoryRequestMessage()
    message.id = message_id
    message.user_id = user_id
    message.name = name
    return message


def create_name_filter_request(message_id, user_id, pattern):
    """Create an EmercoinNameFilterRequestMessage for testing"""
    message = EmercoinNameFilterRequestMessage()
    message.id = message_id
    message.user_id = user_id
    message.pattern = pattern
    return message


def create_name_new_request(message_id, user_id, name, value, options, auth_token):
    """Create an EmercoinNameNewRequestMessage for testing"""
    message = EmercoinNameNewRequestMessage()
    message.id = message_id
    message.user_id = user_id
    message.name = name
    message.value = value
    message.options = options
    message.auth_token = auth_token
    return message


def create_name_update_request(message_id, user_id, name, value, options, auth_token):
    """Create an EmercoinNameUpdateRequestMessage for testing"""
    message = EmercoinNameUpdateRequestMessage()
    message.id = message_id
    message.user_id = user_id
    message.name = name
    message.value = value
    message.options = options
    message.auth_token = auth_token
    return message


# ----- Context Managers (replacing fixtures) -----

@contextmanager
def create_service_mock():
    """Create a mock Emercoin service."""
    service = mock.Mock()
    try:
        yield service
    finally:
        pass  # Any cleanup if needed


@contextmanager
def create_auth_service_mock():
    """Create a mock authentication service."""
    auth_mock = mock.Mock()
    # Default behavior - allow operations
    auth_mock.validate_token.return_value = True
    auth_mock.check_permission.return_value = True
    try:
        yield auth_mock
    finally:
        pass  # Any cleanup if needed


@contextmanager
def create_handler(service_mock=None, auth_service_mock=None):
    """Create an Emercoin message handler with mocked dependencies."""
    # Create mocks if not provided
    if service_mock is None:
        with create_service_mock() as service:
            service_mock = service
    
    if auth_service_mock is None:
        with create_auth_service_mock() as auth:
            auth_service_mock = auth
    
    # Create handler instance
    handler = EmercoinMessageHandler(service_mock, auth_service_mock)
    
    try:
        # Yield handler to the test
        yield handler, service_mock, auth_service_mock
    finally:
        pass  # Any cleanup if needed


# Keep the original fixtures for non-Hypothesis tests
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

@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy,
    info=info_strategy
)
def test_handle_get_info_message(message_id, info):
    """Test handling of emercoin_get_info messages."""
    with create_handler() as (handler, service_mock, _):
        # Create message using factory function
        message = create_info_request(message_id)
        
        # Mock service response
        service_mock.get_blockchain_info.return_value = info
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response
        assert isinstance(response, EmercoinInfoResponseMessage)
        assert response.correlation_id == message_id
        assert not hasattr(response, 'error') or response.error is None


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    name=name_strategy,
    record=record_strategy
)
def test_handle_name_show_message(message_id, user_id, name, record):
    """Test handling of emercoin_name_show messages."""
    with create_handler() as (handler, service_mock, _):
        # Update record name to match query
        record_copy = record.copy()
        record_copy['name'] = name
        
        # Create message
        message = create_name_show_request(message_id, user_id, name)
        
        # Mock service response
        service_mock.name_show.return_value = record_copy
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response
        assert isinstance(response, EmercoinNameShowResponseMessage)
        assert response.correlation_id == message_id
        assert not hasattr(response, 'error') or response.error is None
        
        # Verify service call
        service_mock.name_show.assert_called_once_with(name)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    name=name_strategy,
    records=st.lists(record_strategy, min_size=0, max_size=5)
)
def test_handle_name_history_message(message_id, user_id, name, records):
    """Test handling of emercoin_name_history messages."""
    with create_handler() as (handler, service_mock, _):
        # Update all record names to match query
        modified_records = []
        for record in records:
            record_copy = record.copy()
            record_copy['name'] = name
            modified_records.append(record_copy)
        
        # Create message
        message = create_name_history_request(message_id, user_id, name)
        
        # Mock service response
        service_mock.name_history.return_value = modified_records
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response
        assert isinstance(response, EmercoinNameHistoryResponseMessage)
        assert response.correlation_id == message_id
        assert not hasattr(response, 'error') or response.error is None
        
        # Verify service call
        service_mock.name_history.assert_called_once_with(name)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    regex=st.one_of(st.just('dns:'), st.just('id:'), st.just('test:')),
    records=st.lists(record_strategy, min_size=0, max_size=5)
)
def test_handle_name_filter_message(message_id, user_id, regex, records):
    """Test handling of emercoin_name_filter messages."""
    with create_handler() as (handler, service_mock, _):
        # Update all record names to match filter
        modified_records = []
        prefix = regex.split(':')[0]
        for record in records:
            record_copy = record.copy()
            record_copy['name'] = f"{prefix}:example"
            modified_records.append(record_copy)
        
        # Create message
        message = create_name_filter_request(message_id, user_id, regex)
        
        # Mock service response
        service_mock.name_filter.return_value = modified_records
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response
        assert isinstance(response, EmercoinNameFilterResponseMessage)
        assert response.correlation_id == message_id
        assert not hasattr(response, 'error') or response.error is None
        
        # Verify service call
        service_mock.name_filter.assert_called_once_with(regex)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    name=name_strategy,
    value=value_strategy,
    options=options_strategy,
    auth_token=auth_token_strategy
)
def test_handle_name_new_message(message_id, user_id, name, value, options, auth_token):
    """Test handling of emercoin_name_new messages."""
    with create_handler() as (handler, service_mock, auth_service_mock):
        # Create message
        message = create_name_new_request(message_id, user_id, name, value, options, auth_token)
        
        # Configure auth service
        auth_service_mock.verify_token.return_value = True
        
        # Mock service response
        expected_txid = '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef'
        service_mock.name_new.return_value = expected_txid
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response
        assert isinstance(response, EmercoinNameNewResponseMessage)
        assert response.correlation_id == message_id
        assert not hasattr(response, 'error') or response.error is None
        assert hasattr(response, 'txid')
        assert response.txid == expected_txid
        
        # Verify service call
        days = options.get('days', 30)
        service_mock.name_new.assert_called_once_with(name, value, days)
        
        # Verify auth calls
        auth_service_mock.verify_token.assert_called_once_with(auth_token, user_id, "write")


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    name=name_strategy,
    value=value_strategy,
    options=options_strategy,
    auth_token=auth_token_strategy
)
def test_handle_name_update_message(message_id, user_id, name, value, options, auth_token):
    """Test handling of emercoin_name_update messages."""
    with create_handler() as (handler, service_mock, auth_service_mock):
        # Create message
        message = create_name_update_request(message_id, user_id, name, value, options, auth_token)
        
        # Configure auth service
        auth_service_mock.verify_token.return_value = True
        
        # Mock service response
        expected_txid = 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890'
        service_mock.name_update.return_value = expected_txid
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response
        assert isinstance(response, EmercoinNameUpdateResponseMessage)
        assert response.correlation_id == message_id
        assert not hasattr(response, 'error') or response.error is None
        assert hasattr(response, 'txid')
        assert response.txid == expected_txid
        
        # Verify service call
        days = options.get('days', 30)
        service_mock.name_update.assert_called_once_with(name, value, days)
        
        # Verify auth calls
        auth_service_mock.verify_token.assert_called_once_with(auth_token, user_id, "write")


# ----- Error Handling Tests -----

@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_type=message_type_strategy,
    message_id=message_id_strategy,
    error_code=error_code_strategy,
    error_message=error_message_strategy
)
def test_handle_rpc_error(message_type, message_id, error_code, error_message):
    """Test handling of RPC errors for various message types."""
    with create_handler() as (handler, service_mock, auth_service_mock):
        # Create a message based on type
        if message_type == 'emercoin_get_info':
            message = create_info_request(message_id)
            service_mock.get_blockchain_info.side_effect = RPCError(error_code, error_message)
        elif message_type == 'emercoin_name_show':
            message = create_name_show_request(message_id, "test_user", "test:example")
            service_mock.name_show.side_effect = RPCError(error_code, error_message)
        elif message_type == 'emercoin_name_history':
            message = create_name_history_request(message_id, "test_user", "test:example")
            service_mock.name_history.side_effect = RPCError(error_code, error_message)
        elif message_type == 'emercoin_name_filter':
            message = create_name_filter_request(message_id, "test_user", "test:")
            service_mock.name_filter.side_effect = RPCError(error_code, error_message)
        elif message_type == 'emercoin_name_new':
            message = create_name_new_request(
                message_id, "test_user", "test:example", "test_value",
                {"days": 30}, "valid_token"
            )
            auth_service_mock.verify_token.return_value = True
            service_mock.name_new.side_effect = RPCError(error_code, error_message)
        elif message_type == 'emercoin_name_update':
            message = create_name_update_request(
                message_id, "test_user", "test:example", "test_value",
                {"days": 30}, "valid_token"
            )
            auth_service_mock.verify_token.return_value = True
            service_mock.name_update.side_effect = RPCError(error_code, error_message)
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response
        assert response.correlation_id == message_id
        assert hasattr(response, 'error')
        assert response.error is not None
        
        # Check that error code is preserved or the error message contains relevant info
        error_str = str(response.error)
        assert (str(error_code) in error_str) or ("RPC Error" in error_str)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    read_message_type=read_message_type_strategy
)
def test_handle_connection_error(message_id, user_id, read_message_type):
    """Test handling of connection errors."""
    with create_handler() as (handler, service_mock, _):
        # Create a message based on type
        if read_message_type == 'emercoin_get_info':
            message = create_info_request(message_id, user_id)
            service_mock.get_blockchain_info.side_effect = ConnectionError("Failed to connect")
        elif read_message_type == 'emercoin_name_show':
            message = create_name_show_request(message_id, user_id, "test:example")
            service_mock.name_show.side_effect = ConnectionError("Failed to connect")
        elif read_message_type == 'emercoin_name_history':
            message = create_name_history_request(message_id, user_id, "test:example")
            service_mock.name_history.side_effect = ConnectionError("Failed to connect")
        elif read_message_type == 'emercoin_name_filter':
            message = create_name_filter_request(message_id, user_id, "test:")
            service_mock.name_filter.side_effect = ConnectionError("Failed to connect")
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response
        assert response.correlation_id == message_id
        assert hasattr(response, 'error')
        assert response.error is not None
        assert "Failed to connect" in str(response.error)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    auth_token=auth_token_strategy,
    write_message_type=write_message_type_strategy
)
def test_write_operation_with_invalid_auth(message_id, user_id, auth_token, write_message_type):
    """Test that write operations fail with invalid authentication."""
    with create_handler() as (handler, service_mock, auth_service_mock):
        # Create a message based on type
        if write_message_type == 'emercoin_name_new':
            message = create_name_new_request(
                message_id, user_id, "test:example", "test_value", 
                {"days": 30}, auth_token
            )
        else:  # emercoin_name_update
            message = create_name_update_request(
                message_id, user_id, "test:example", "test_value", 
                {"days": 30}, auth_token
            )
        
        # Configure auth service to return False for token validation
        auth_service_mock.verify_token.return_value = False
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response
        assert response.correlation_id == message_id
        assert hasattr(response, 'error')
        assert response.error is not None
        assert "Unauthorized" in str(response.error) or "invalid token" in str(response.error)


@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    name=st.text(min_size=1, max_size=300)  # Potentially invalid names
)
def test_invalid_name_validation(message_id, user_id, name):
    """Test validation of invalid name formats."""
    with create_handler() as (handler, service_mock, _):
        # Create message with potentially invalid name
        message = create_name_show_request(message_id, user_id, name)
        
        # Configure service to validate and potentially reject the name
        service_mock.name_show.side_effect = ValueError(f"Invalid name format: {name}")
        
        # Process message
        response = handler._handle_message(message)
        
        # Check response
        assert response.correlation_id == message_id
        assert hasattr(response, 'error')
        assert response.error is not None
        assert "Invalid name format" in str(response.error)


def test_no_auth_service_configured(service_mock):
    """Test behavior when no auth service is configured."""
    # Create handler without auth service
    handler = EmercoinMessageHandler(service_mock)
    
    # Create a write operation message
    message = create_name_new_request(
        "test_id", "test_user", "test:example", "test_value", 
        {"days": 30}, "valid_token"
    )
    
    # Mock service response
    service_mock.name_new.return_value = 'txid_12345'
    
    # In development mode (no auth service), this should proceed without auth
    with mock.patch('emercoin.emercoin_message_handler.logger') as mock_logger:
        response = handler._handle_message(message)
        
        # Should not have error
        assert not hasattr(response, 'error') or response.error is None
        assert hasattr(response, 'txid')
        assert response.txid == 'txid_12345'


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy,
    user_id=user_id_strategy,
    name=name_strategy,
    value=value_strategy,
    days=st.integers(min_value=1, max_value=365),
    auth_token=auth_token_strategy
)
def test_message_with_different_options_format(message_id, user_id, name, value, days, auth_token):
    """Test handling of messages with different options format."""
    with create_handler() as (handler, service_mock, auth_service_mock):
        # Create message with days correctly in options dictionary
        options = {"days": days}  # Wrap the days in a dictionary
        message = create_name_new_request(
            message_id, user_id, name, value, options, auth_token
        )
        
        # Configure auth service to approve the operation
        auth_service_mock.verify_token.return_value = True
        
        # Mock service response
        expected_txid = 'txid_12345'
        service_mock.name_new.return_value = expected_txid
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response
        assert isinstance(response, EmercoinNameNewResponseMessage)
        assert response.correlation_id == message_id
        assert not hasattr(response, 'error') or response.error is None
        assert hasattr(response, 'txid')
        assert response.txid == expected_txid


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    message_id=message_id_strategy
)
def test_extremely_long_value(message_id):
    """Test handling of messages with extremely long values."""
    with create_handler() as (handler, service_mock, auth_service_mock):
        # Create message with extremely long value
        very_long_value = "x" * 5000  # Emercoin typically has a 520-byte limit
        
        message = create_name_new_request(
            message_id, "test_user", "test:example", very_long_value, 
            {"days": 30}, "valid_token"
        )
        
        # Configure auth service to approve the operation
        auth_service_mock.verify_token.return_value = True
        
        # Configure service to raise an RPC error about value too long
        service_mock.name_new.side_effect = RPCError(-32000, "Value too long")
        
        # Process message
        response = handler._handle_message(message)
        
        # Verify response contains the error
        assert response.correlation_id == message_id
        assert hasattr(response, 'error')
        assert response.error is not None
        assert "Value too long" in str(response.error)


@mock.patch('emercoin.emercoin_message_handler.logger')
def test_audit_logging(mock_logger, handler, service_mock, auth_service_mock):
    """Test that write operations are logged for audit purposes."""
    # Create a user ID and message
    user_id = "test_user"
    message = create_name_new_request(
        "audit_test", user_id, "test:example", "test_value", 
        {"days": 30}, "valid_token"
    )
    
    # Configure auth service to approve the operation
    auth_service_mock.verify_token.return_value = True
    
    # Configure service to return a successful response
    expected_txid = 'txid_12345'
    service_mock.name_new.return_value = expected_txid
    
    # Process message
    handler._handle_message(message)
    
    # Verify audit log was called
    called = False
    for call in mock_logger.mock_calls:
        if len(call.args) > 0 and isinstance(call.args[0], str):
            if "test_user" in call.args[0] and "txid_12345" in call.args[0]:
                called = True
                break
    
    assert called, "Audit log was not called with expected information"