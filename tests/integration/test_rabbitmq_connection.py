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
async def test_connection_basics():
    """Test basic connection functionality"""
    print("Starting connection test")
    
    # Create connection directly in test
    connection_manager = AsyncRabbitMQConnection(
        host="localhost",
        port=5672,
        user="guest",
        password="guest",
        vhost="/",
        secret_key="test-secret-key"
    )
    
    try:
        # Check initial state
        print("Checking connection is open")
        connection = await connection_manager._get_connection()
        assert connection is not None
        assert not connection.is_closed
        
        print("Checking channel is open")
        channel = await connection_manager._get_channel()
        assert channel is not None
        assert not channel.is_closed
        
        print("Testing close")
        # Test close
        await connection_manager.close()
        
        # Check connection is now None or not referenced
        print("Checking connection is closed")
        assert connection_manager._connection is None
        
        print("Testing reconnect")
        # Verify reconnection works
        new_channel = await connection_manager._get_channel()
        assert new_channel is not None
        assert not new_channel.is_closed
        
        new_connection = await connection_manager._get_connection()
        assert new_connection is not None
        assert not new_connection.is_closed
        
        print("Test completed successfully")
    finally:
        # Ensure cleanup
        await connection_manager.close()

@pytest.mark.asyncio
async def test_hmac_authentication():
    """Test HMAC signature generation and verification"""
    # Create connection directly in test
    connection_manager = AsyncRabbitMQConnection(
        host="localhost",
        secret_key="test-secret-key"
    )
    
    try:
        # Test message bodies
        test_bodies = [
            b"test message",
            json.dumps({"key": "value"}).encode(),
            b"",
            b"special chars: !@#$%^&*()"
        ]
        
        for body in test_bodies:
            # Generate signature
            signature = connection_manager._generate_hmac(body)
            
            # Verify signature
            assert connection_manager._verify_hmac(body, signature)
            
            # Test invalid signature
            invalid_sig = "invalid" + signature[7:] if len(signature) > 7 else "invalid"
            assert not connection_manager._verify_hmac(body, invalid_sig)
    finally:
        # Ensure cleanup
        await connection_manager.close()

@pytest.mark.asyncio
async def test_publish_consume():
    """Test publishing and consuming messages"""
    # Create connection directly in test
    connection_manager = AsyncRabbitMQConnection(
        host="localhost",
        secret_key="test-secret-key"
    )
    
    try:
        # Setup test queues
        test_queue = await connection_manager.declare_queue("test_queue")
        
        # Purge any existing messages
        await test_queue.purge()
        
        # Messages received
        received_messages = []
        
        # Callback to collect messages
        def message_callback(message):
            received_messages.append(message)
            print(f"Received message: {message}")
        
        # Start consumer task
        await connection_manager.start_consumer_task(
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
            await connection_manager.publish("test_queue", message)
        
        # Allow time for messages to be consumed
        await asyncio.sleep(1)
        
        # Stop consumer
        await connection_manager.stop_consumer_task("test_queue")
        
        # Check received messages
        assert len(received_messages) == len(test_messages), f"Expected {len(test_messages)} messages, got {len(received_messages)}"
        
        # Verify message content preservation
        for i, message in enumerate(test_messages):
            assert received_messages[i]["type"] == message["type"]
            assert received_messages[i]["value"] == message["value"]
    finally:
        # Ensure cleanup
        await connection_manager.close()

@pytest.mark.asyncio
async def test_wait_for_message_timeout():
    """Test waiting for a message with timeout"""
    # Create connection directly in test
    connection_manager = AsyncRabbitMQConnection(
        host="localhost",
        secret_key="test-secret-key"
    )
    
    try:
        # Setup test queues
        response_queue = await connection_manager.declare_queue("response_queue")
        
        # Purge any existing messages
        await response_queue.purge()
        
        # Test timeout - should return None after timeout
        start_time = time.time()
        result = await connection_manager.wait_for_message("response_queue", timeout=1.0)
        elapsed = time.time() - start_time
        
        # Check timeout behavior
        assert result is None
        assert elapsed >= 1.0
        assert elapsed < 3.0  # Allow some leeway but not too much
    finally:
        # Ensure cleanup
        await connection_manager.close()

@pytest.mark.asyncio
async def test_concurrent_consumers():
    """Test multiple concurrent consumers"""
    # Create connection directly in test
    connection_manager = AsyncRabbitMQConnection(
        host="localhost",
        secret_key="test-secret-key"
    )
    
    try:
        # Setup test queues
        test_queue = await connection_manager.declare_queue("test_queue")
        response_queue = await connection_manager.declare_queue("response_queue")
        
        # Purge existing messages from queues to ensure clean test
        await test_queue.purge()
        await response_queue.purge()
        
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
        await connection_manager.start_consumer_task(
            "test_queue",
            test_callback
        )
        
        await connection_manager.start_consumer_task(
            "response_queue",
            resp_callback
        )
        
        # Allow consumers to start
        await asyncio.sleep(1)
        
        # Send messages
        for i in range(5):
            await connection_manager.publish("test_queue", {"queue": "test", "index": i})
            await connection_manager.publish("response_queue", {"queue": "response", "index": i})
            await asyncio.sleep(0.1)  # Small delay between sends
        
        # Wait for messages to be processed
        await asyncio.sleep(2)
        
        # Stop consumers
        await connection_manager.stop_consumer_task("test_queue")
        await connection_manager.stop_consumer_task("response_queue")
        
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
    finally:
        # Ensure cleanup
        await connection_manager.close()

@pytest.mark.asyncio
@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
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
        max_size=5  # Reduced for faster tests
    )
)
async def test_message_fidelity(messages):
    """Test message content fidelity with Hypothesis-generated data"""
    # Create connection directly in test
    connection_manager = AsyncRabbitMQConnection(
        host="localhost",
        secret_key="test-secret-key"
    )
    
    try:
        # Setup test queue
        test_queue = await connection_manager.declare_queue("test_queue")
        
        # Purge the queue to ensure clean test
        await test_queue.purge()
        
        # Setup a consumer to verify message receipt
        received_messages = []
        
        def message_callback(message):
            received_messages.append(message)
            print(f"Received in consumer: {message}")
        
        # Start a consumer
        await connection_manager.start_consumer_task(
            "test_queue",
            message_callback
        )
        
        # Allow consumer to start
        await asyncio.sleep(0.5)
        
        # Publish all messages
        for message in messages:
            await connection_manager.publish("test_queue", message)
            # Small delay between sends
            await asyncio.sleep(0.1)
        
        # Allow messages to be consumed
        # Calculate wait time based on message count
        wait_time = max(1.0, 0.5 * len(messages))
        await asyncio.sleep(wait_time)
        
        # Stop the consumer
        await connection_manager.stop_consumer_task("test_queue")
        
        # Check that all messages were received
        assert len(received_messages) == len(messages), f"Expected {len(messages)} messages, got {len(received_messages)}"
        
        # Verify each message was received correctly (contents preserved)
        # Since the order might not be preserved, we need to check for matching content
        for sent in messages:
            message_found = False
            for received in received_messages:
                if sent == received:
                    message_found = True
                    break
            
            assert message_found, f"Message {sent} was not received correctly"
    finally:
        # Ensure cleanup
        await connection_manager.close()