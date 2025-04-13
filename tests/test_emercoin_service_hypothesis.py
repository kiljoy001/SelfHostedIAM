import pytest
import unittest.mock as mock
import asyncio
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume, example, HealthCheck
from emercoin.module.emercoin_service import EmercoinService
from emercoin.emercoin_connection_handler import ConnectionError, AuthError, RPCError
from contextlib import asynccontextmanager


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
async def service(default_config):
    service = EmercoinService(default_config)
    await service.initialize_async()
    return service

# Define a strategy for valid Emercoin name-value records
name_value_strategy = st.fixed_dictionaries({
    'name': st.builds(
        lambda namespace, domain: f"{namespace}:{domain}",
        namespace=st.sampled_from(['dns', 'id', 'ssl', 'ssh', 'test']),
        # Generate valid domain names rather than arbitrary strings
        domain=st.from_regex(r'[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)*', fullmatch=True)
    ),
    'value': st.text(min_size=0, max_size=100),
    'days': st.integers(min_value=1, max_value=90)
})

# Strategy for name_filter regex patterns
name_filter_strategy = st.one_of(
    st.just('dns:'),
    st.just('id:'),
    st.just('ssl:'),
    st.just('ssh:'),
    st.just('test:'),
    st.from_regex(r'dns:[a-zA-Z0-9_\-\.]*', fullmatch=True),
    st.from_regex(r'id:[a-zA-Z0-9_\-\.]*', fullmatch=True),
    st.from_regex(r'ssl:[a-zA-Z0-9_\-\.]*', fullmatch=True),
    st.from_regex(r'ssh:[a-zA-Z0-9_\-\.]*', fullmatch=True),
    st.from_regex(r'test:[a-zA-Z0-9_\-\.]*', fullmatch=True)
)

# Create a context manager for the service
@asynccontextmanager
async def create_service(service_class=None, config=None, mock_dependencies=True):
    """
    Create a service instance for testing with optional dependency mocking.

    Args:
        service_class: The service class to instantiate (defaults to EmercoinService if None)
        config: Configuration to pass to the service
        mock_dependencies: Whether to mock external dependencies

    Returns:
        Service instance with appropriate configuration
    """
    # Default to EmercoinService if not specified
    if service_class is None:
        from emercoin.module.emercoin_service import EmercoinService
        service_class = EmercoinService

    if config is None:
        # Default test configuration with correct parameter names
        config = {
            "rpc_url": "http://localhost:6662",
            "rpc_user": "test",
            "rpc_password": "test",
            "timeout": 10,
            "max_retries": 3
        }

    # Create service instance
    service = service_class(config)
    await service.initialize_async()

    # If we should mock dependencies
    if mock_dependencies:
        # For EmercoinService, we need to mock the connection
        if service_class.__name__ == "EmercoinService":
            # Replace the real connection with a mock
            service.connection = mock.MagicMock()

        # For TPMService, mock appropriate components
        elif service_class.__name__ == "TPMService":
            service.message_handler = mock.MagicMock()
            service.script_runner = mock.MagicMock()

    try:
        # Start the service if it's TPMService (as that's expected behavior)
        if service_class.__name__ == "TPMService":
            await service.start_async()  # Use async version consistently

        yield service
    finally:
        # Ensure cleanup happens
        if service_class.__name__ == "TPMService" and service.is_active():
            await service.stop_async()  # Use async version consistently
        # Reset state for next test
        await service.reset_state_async()  # Use the async version instead of reset_state


@pytest.mark.asyncio  # Mark test as asyncio
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    blockchain_info=st.dictionaries(
        keys=st.sampled_from(['version', 'blocks', 'connections', 'difficulty', 'testnet']),
        values=st.one_of(st.text(), st.integers(), st.booleans()),
        min_size=1
    )
)
async def test_get_blockchain_info(blockchain_info):
    """Test getting blockchain info from Emercoin service"""
    # Use context manager instead of fixture
    async with create_service() as service:
        # Configure the mock correctly
        service.connection.call.return_value = blockchain_info
        
        # Call the method and verify results
        result = await service.get_blockchain_info()
        
        # Make assertions
        assert result == blockchain_info
        service.connection.call.assert_called_once_with('getinfo')

@pytest.mark.asyncio  # Mark test as asyncio
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(record=st.fixed_dictionaries({
    'name': st.text(min_size=1, max_size=255),
    'value': st.text(max_size=512),
    'txid': st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'),
    'address': st.text(min_size=30, max_size=34),
    'expires_in': st.integers(min_value=0),
    'expires_at': st.integers(min_value=0),
    'time': st.integers(min_value=0)
}))
async def test_name_show(record):
    """Test name_show with various record structures."""
    # Assume name has correct format for validation to pass
    name = "dns:example.com"  # Use a valid name format
    
    # Use our improved service creation
    async with create_service() as service:
        # Service.connection is already mocked by create_service
        service.connection.call.return_value = record
        
        # Call method under test
        result = await service.name_show(name)
        
        # Verify call was made correctly
        service.connection.call.assert_called_once_with('name_show', [name])
        
        # Verify results match mock data
        assert result == record

@pytest.mark.asyncio  # Mark test as asyncio
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
async def test_name_history(records):
    """Test name_history with various record collections."""
    # Use a valid name format
    name = "dns:example.com"
    
    async with create_service() as service:
        # Setup service mock
        service.connection.call.return_value = records
        
        # Call the service
        result = await service.name_history(name)
        
        # Verify results match mock data
        assert result == records
        service.connection.call.assert_called_once_with('name_history', [name])

@pytest.mark.asyncio  # Mark test as asyncio
@given(pattern=name_filter_strategy)
async def test_name_filter(pattern):
    """Test name_filter with various filter patterns."""
    # Setup a mock response with records matching the pattern
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
    
    async with create_service() as service:
        # Setup mock
        service.connection.call.return_value = mock_records
        
        # Call the service
        result = await service.name_filter(pattern)
        
        # Verify results match mock data
        assert result == mock_records
        service.connection.call.assert_called_once_with('name_filter', [pattern])

@pytest.mark.asyncio  # Mark test as asyncio
@given(record=name_value_strategy)
async def test_name_new(record):
    """Test name_new with various name-value records."""
    expected_txid = '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef'
    
    async with create_service() as service:
        # Setup mock
        service.connection.call.return_value = expected_txid
        
        # Create options dict
        options = {'days': record['days']}
        
        # Call the service
        result = await service.name_new(record['name'], record['value'], options)
        
        # Verify results and call parameters
        assert result == expected_txid
        service.connection.call.assert_called_once_with('name_new', [record['name'], record['value'], options])

@pytest.mark.asyncio  # Mark test as asyncio
@given(record=name_value_strategy)
async def test_name_update(record):
    """Test name_update with various name-value records."""
    expected_txid = 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890'
    
    async with create_service() as service:
        # Setup mock
        service.connection.call.return_value = expected_txid
        
        # Create options dict
        options = {'days': record['days']}
        
        # Call the service
        result = await service.name_update(record['name'], record['value'], options)
        
        # Verify results and call parameters
        assert result == expected_txid
        service.connection.call.assert_called_once_with('name_update', [record['name'], record['value'], options])

@pytest.mark.asyncio  # Mark test as asyncio
@given(name=st.text(min_size=1, max_size=255))
async def test_validate_name(name):
    """Test name validation with various input strings."""
    async with create_service() as service:
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

@pytest.mark.asyncio  # Mark test as asyncio
@settings(max_examples=20)
@given(name=st.text(min_size=1, max_size=255))
@example("test:example")  # Always include this known good example
@example("invalid_name")  # Always include this known bad example
@example(":")  # Edge case: empty prefix and value
@example("test:")  # Edge case: empty value
@example(":test")  # Edge case: empty prefix
async def test_validate_name_edge_cases(name):
    """Test name validation with specific edge cases."""
    async with create_service() as service:
        # Call the validation method
        result = service.validate_name(name)
        
        # For the specific examples, verify expected results
        if name == "test:example":
            assert result == True
        elif name in ["invalid_name", ":", "test:", ":test"]:
            assert result == False

@pytest.mark.asyncio  # Mark test as asyncio
@given(
    error_code=st.integers(min_value=-32099, max_value=-32000),
    error_message=st.text(min_size=1, max_size=100)
)
async def test_rpc_error_handling(error_code, error_message):
    """Test RPC error handling in the service layer."""
    async with create_service() as service:
        # Setup mock to raise RPC error
        service.connection.call.side_effect = RPCError(error_code, error_message)
        
        # Call a service method that uses the mock
        with pytest.raises(RPCError) as excinfo:
            await service.get_blockchain_info()
            
        # Verify error details
        assert excinfo.value.code == error_code
        assert excinfo.value.message == error_message