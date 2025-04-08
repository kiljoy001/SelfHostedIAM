# tests/integration/test_rabbitmq_connection.py
import pytest
import hypothesis
from hypothesis import given, HealthCheck, settings, strategies as st
import json
import asyncio
import time
import os
from typing import Dict, Any

# Import your async RabbitMQ connection manager
from helper.rabbitmq_connector import AsyncRabbitMQConnection

# Configure hypothesis
hypothesis.settings.register_profile("rabbitmq", max_examples=20, deadline=None)
hypothesis.settings.load_profile("rabbitmq")

# Setup a fixture for the connection
@pytest.fixture
async def async_rabbitmq_connection():
    """Create a test connection to RabbitMQ"""
    # Use test host from environment or default to localhost
    host = os.environ.get("TEST_RABBITMQ_HOST", "localhost")
    
    # Create connection with test secret
    connection = AsyncRabbitMQConnection(
        host=host,
        port=5672,
        user="guest",
        password="guest",
        vhost="/",
        secret_key="test-secret-key"
    )
    
    # Setup test queues
    await connection.declare_queue("test_queue")
    await connection.declare_queue("response_queue")
    
    # Return connection for testing
    yield connection
    
    # Cleanup
    await connection.close()

@pytest.mark.asyncio
async def test_direct_rabbitmq_connection():
    """Test direct RabbitMQ connection without your custom class"""
    print("\n--- Testing direct RabbitMQ connection ---")
    
    # Using aio-pika directly
    import aio_pika
    
    # Connect
    print("Connecting...")
    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
    print("Connection established")
    
    # Create a channel
    print("Creating channel...")
    channel = await connection.channel()
    print("Channel created")
    
    # Test a basic operation
    print("Declaring test queue...")
    queue = await channel.declare_queue("direct_test_queue")
    print("Queue declared")
    
    # Close everything
    print("Closing channel...")
    await channel.close()
    print("Channel closed")
    
    print("Closing connection...")
    await connection.close()
    print("Connection closed")
    
    print("Test completed successfully")

@pytest.mark.asyncio
async def test_simple_connection():
    """Test the most basic RabbitMQ connection"""
    import aio_pika
    
    print("Attempting to connect")
    try:
        connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
        print("Connection successful")
        assert not connection.is_closed
        await connection.close()
        print("Connection closed successfully")
    except Exception as e:
        print(f"Connection failed: {e}")
        raise

@pytest.mark.asyncio
async def test_connection_basics(async_rabbitmq_connection):
    """Test basic connection functionality"""
    print("Starting connection test")
    
    # Check initial state
    print("Checking connection is open")
    connection = await async_rabbitmq_connection._get_connection()
    assert connection is not None
    assert not connection.is_closed
    print("Checking channel is open")
    channel = await async_rabbitmq_connection._get_channel()
    assert channel is not None
    assert not channel.is_closed
    
    print("Testing close")
    # Test close
    await async_rabbitmq_connection.close()
    
    # Check connection is now None or not referenced
    print("Checking connection is closed")
    assert async_rabbitmq_connection._connection is None
    
    print("Testing reconnect")
    # Verify reconnection works
    new_channel = await async_rabbitmq_connection._get_channel()
    assert new_channel is not None
    assert not new_channel.is_closed
    
    new_connection = await async_rabbitmq_connection._get_connection()
    assert new_connection is not None
    assert not new_connection.is_closed
    print("Test completed successfully")

@pytest.mark.asyncio
async def test_hmac_authentication(async_rabbitmq_connection):
    """Test HMAC signature generation and verification"""
    # Test message bodies
    test_bodies = [
        b"test message",
        json.dumps({"key": "value"}).encode(),
        b"",
        b"special chars: !@#$%^&*()"
    ]
    
    for body in test_bodies:
        # Generate signature
        signature = async_rabbitmq_connection._generate_hmac(body)
        
        # Verify signature
        assert async_rabbitmq_connection._verify_hmac(body, signature)
        
        # Test invalid signature
        invalid_sig = "invalid" + signature[7:] if len(signature) > 7 else "invalid"
        assert not async_rabbitmq_connection._verify_hmac(body, invalid_sig)

@pytest.mark.asyncio
async def test_publish_consume(async_rabbitmq_connection):
    """Test publishing and consuming messages"""
    # Messages received
    received_messages = []
    
    # Callback to collect messages
    def message_callback(message):
        received_messages.append(message)
        print(f"Received message: {message}")
    
    # Start consumer task
    await async_rabbitmq_connection.start_consumer_task(
        "test_queue", 
        message_callback
    )
    
    # Allow consumer to start
    await asyncio.sleep(0.5)
    
    # Test messages
    test_messages = [
        {"type": "test", "value": 1},
        {"type": "test", "value": "string"},
        {"type": "test", "value": [1, 2, 3]},
        {"type": "test", "value": {"nested": "object"}}
    ]
    
    # Publish test messages
    for message in test_messages:
        await async_rabbitmq_connection.publish("test_queue", message)
    
    # Allow time for messages to be consumed
    await asyncio.sleep(1)
    
    # Stop consumer
    await async_rabbitmq_connection.stop_consumer_task("test_queue")
    
    # Check received messages
    assert len(received_messages) == len(test_messages), f"Expected {len(test_messages)} messages, got {len(received_messages)}"
    
    # Verify message content preservation
    for i, message in enumerate(test_messages):
        assert received_messages[i]["type"] == message["type"]
        assert received_messages[i]["value"] == message["value"]

@pytest.mark.asyncio
async def test_wait_for_message_timeout(async_rabbitmq_connection):
    """Test waiting for a message with timeout"""
    # Test timeout - should return None after timeout
    start_time = time.time()
    result = await async_rabbitmq_connection.wait_for_message("response_queue", timeout=1.0)
    elapsed = time.time() - start_time
    
    # Check timeout behavior
    assert result is None
    assert elapsed >= 1.0
    assert elapsed < 3.0  # Allow some leeway but not too much

@pytest.mark.asyncio
async def test_concurrent_consumers(async_rabbitmq_connection):
    """Test multiple concurrent consumers"""
    # Purge existing messages from queues to ensure clean test
    channel = await async_rabbitmq_connection._get_channel()
    await channel.queue_purge("test_queue")
    await channel.queue_purge("response_queue")
    
    # Collect results
    test_results = []
    resp_results = []
    
    # Callbacks
    def test_callback(message):
        test_results.append(message)
        print(f"Received test message: {message}")
    
    def resp_callback(message):
        resp_results.append(message)
        print(f"Received response message: {message}")
    
    # Start consumer tasks
    await async_rabbitmq_connection.start_consumer_task(
        "test_queue",
        test_callback
    )
    
    await async_rabbitmq_connection.start_consumer_task(
        "response_queue",
        resp_callback
    )
    
    # Allow consumers to start
    await asyncio.sleep(1)
    
    # Send messages
    for i in range(5):
        await async_rabbitmq_connection.publish("test_queue", {"queue": "test", "index": i})
        await async_rabbitmq_connection.publish("response_queue", {"queue": "response", "index": i})
        await asyncio.sleep(0.1)  # Small delay between sends
    
    # Wait for messages to be processed
    await asyncio.sleep(2)
    
    # Stop consumers
    await async_rabbitmq_connection.stop_consumer_task("test_queue")
    await async_rabbitmq_connection.stop_consumer_task("response_queue")
    
    # Check results
    assert len(test_results) == 5, f"Expected 5 test messages, got {len(test_results)}"
    assert len(resp_results) == 5, f"Expected 5 response messages, got {len(resp_results)}"
    
    # Verify message content
    for i, message in enumerate(test_results):
        assert message["queue"] == "test"
        assert message["index"] < 5
    
    for i, message in enumerate(resp_results):
        assert message["queue"] == "response"
        assert message["index"] < 5

@pytest.mark.asyncio
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    messages=st.lists(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=10),
            values=st.one_of(
                st.text(),
                st.integers(),
                st.booleans(),
                st.lists(st.integers(), max_size=5),
                st.dictionaries(
                    keys=st.text(min_size=1, max_size=5),
                    values=st.integers(),
                    max_size=3
                )
            )
        ),
        min_size=1,
        max_size=10
    )
)
async def test_message_fidelity(async_rabbitmq_connection, messages):
    """Test message content fidelity with Hypothesis-generated data"""
    # First purge the queue to ensure clean test
    channel = await async_rabbitmq_connection._get_channel()
    await channel.queue_purge("test_queue")
    
    # Publish all messages first
    for message in messages:
        await async_rabbitmq_connection.publish("test_queue", message)
    
    # Wait to ensure all messages are published
    await asyncio.sleep(0.5)
    
    # Now collect and verify all messages
    received = await async_rabbitmq_connection.wait_for_messages(
        "test_queue", 
        len(messages),
        timeout=max(1.0, 0.2 * len(messages))
    )
    
    # Check that all messages were received
    assert len(received) == len(messages), f"Expected {len(messages)} messages, got {len(received)}"
    
    # Sort and compare message content - since order might not be preserved with async
    # We'll check that each sent message has a matching received message
    for sent in messages:
        matching_message = False
        for recv in received:
            if sent == recv:
                matching_message = True
                break
        assert matching_message, f"Message {sent} was not received correctly"