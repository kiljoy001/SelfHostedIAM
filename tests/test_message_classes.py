from hypothesis import given, strategies as st
from helper.message import CommandMessage, MessageFactory, ResponseMessage, BaseMessage
import pytest

# Define strategies for generating message data
@st.composite
def command_message_data(draw):
    """Strategy for generating CommandMessage data"""
    return {
        "command": draw(st.text(min_size=1)),
        "args": draw(st.lists(st.one_of(st.text(), st.integers()))),
        "source": draw(st.text(min_size=1)),
        "target": draw(st.text(min_size=1)),
        "id": draw(st.text(min_size=1))
    }

@st.composite
def response_message_data(draw):
    """Strategy for generating ResponseMessage data"""
    return {
        "success": draw(st.booleans()),
        "result": draw(st.dictionaries(st.text(), st.text())),
        "error": draw(st.one_of(st.none(), st.text())),
        "correlation_id": draw(st.one_of(st.none(), st.text())),
        "id": draw(st.text(min_size=1))
    }

# Test roundtrip serialization/deserialization
@given(
    command=st.text(min_size=1),
    args=st.lists(st.text()),
    source=st.text(min_size=1),
    target=st.text(min_size=1),
    custom_id=st.text(min_size=1)
)
def test_command_message_roundtrip(command, args, source, target, custom_id):
    """Test that CommandMessage serializes and deserializes correctly"""
    # Create message with explicit parameters
    message_data = {
        "command": command,
        "args": args,
        "source": source,
        "target": target,
        "id": custom_id
    }
    
    # Create message directly
    cmd = CommandMessage(**message_data)
    
    # Explicitly check ID is preserved after initialization
    assert cmd.id == custom_id, "ID should be preserved during initialization"
    
    # Convert to dict
    data = cmd.to_dict()
    
    # Verify dict contains correct ID
    assert data["id"] == custom_id, "ID should be preserved in dictionary"
    
    # Convert back to object
    restored = MessageFactory.create_from_dict(data)
    
    # Verify all properties are preserved
    assert isinstance(restored, CommandMessage)
    assert restored.command == command
    assert restored.args == args
    assert restored.source == source
    assert restored.target == target
    assert restored.id == custom_id, "ID should be preserved after deserialization"

# Test factory functionality with different message types
@given(
    command_data=command_message_data(),
    response_data=response_message_data()
)
def test_message_factory_creates_correct_types(command_data, response_data):
    """Test MessageFactory creates the correct message types"""
    # Add message_type to the test data
    command_data["message_type"] = "command"
    response_data["message_type"] = "response"
    
    # Create messages using factory
    cmd = MessageFactory.create_from_dict(command_data)
    resp = MessageFactory.create_from_dict(response_data)
    
    # Verify types
    assert isinstance(cmd, CommandMessage)
    assert isinstance(resp, ResponseMessage)

# Test handling of invalid data
@given(st.dictionaries(st.text(), st.text()))
def test_message_factory_handles_invalid_data(invalid_data):
    """Test MessageFactory handles invalid data appropriately"""
    # Remove message_type to ensure it's invalid
    invalid_data.pop("message_type", None)
    
    # Attempt to create message from invalid data
    try:
        MessageFactory.create_from_dict(invalid_data)
        pytest.fail("Should have raised ValueError for invalid data")
    except (ValueError, TypeError) as e:
        # Successfully caught error - this is expected
        pass

# Basic tests
def test_basic_message_creation():
    msg = BaseMessage(id="test-id", source="test-source")
    assert msg.id == "test-id"
    assert msg.source == "test-source"

# Hypothesis property-based tests

@given(
    command=st.text(min_size=1, max_size=100),
    args=st.lists(st.text(min_size=0, max_size=100), min_size=0, max_size=10),
    source=st.text(min_size=1, max_size=50),
    target=st.text(min_size=1, max_size=50),
    correlation_id=st.one_of(st.none(), st.text(min_size=1, max_size=50))
)
def test_command_message_serialization(command, args, source, target, correlation_id):
    """Test message serialization with diverse content"""
    # Create message with valid fields only
    msg_data = {
        "command": command,
        "args": args,
        "source": source,
        "target": target
    }
    
    # Add optional correlation_id if it's not None
    if correlation_id is not None:
        msg_data["correlation_id"] = correlation_id
    
    # Create message with proper fields
    msg = CommandMessage(**msg_data)
    
    # Serialize to dict
    data = msg.to_dict()
    
    # Verify message properties are preserved
    assert data["command"] == command
    assert data["args"] == args
    assert data["source"] == source
    assert data["target"] == target
    if correlation_id is not None:
        assert data["correlation_id"] == correlation_id
    
    # Verify message type is included
    assert data["message_type"] == "command"
        
    # Convert back to object
    restored = MessageFactory.create_from_dict(data)
    
    # Verify properties match original
    assert restored.command == command
    assert restored.args == args
    assert restored.source == source
    assert restored.target == target
    if correlation_id is not None:
        assert restored.correlation_id == correlation_id