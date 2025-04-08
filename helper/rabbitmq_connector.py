import json
import hmac
import hashlib
import logging
import asyncio
from typing import Callable, Dict, Any, Optional, Union, List, Coroutine
import aio_pika
from aio_pika import Message, DeliveryMode
from aio_pika.abc import AbstractIncomingMessage


class AsyncRabbitMQConnection:
    """
    Asynchronous RabbitMQ connection manager with HMAC authentication using aio-pika
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 5672,
        user: str = 'guest',
        password: str = 'guest',
        vhost: str = '/',
        secret_key: str = None,
        connection_attempts: int = 3,
        retry_delay: int = 1,
        heartbeat: int = 600
    ):
        """
        Initialize Async RabbitMQ connection manager
        
        Args:
            host: RabbitMQ server hostname
            port: RabbitMQ server port
            user: RabbitMQ username
            password: RabbitMQ password
            vhost: RabbitMQ virtual host
            secret_key: Secret key for HMAC authentication
            connection_attempts: Number of connection attempts
            retry_delay: Delay between connection attempts in seconds
            heartbeat: Heartbeat interval in seconds
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.vhost = vhost
        self.secret_key = secret_key or self._get_default_secret()
        
        # Connection parameters
        self.connection_url = f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/{self.vhost}"
        self.connection_kwargs = {
            "reconnect_interval": retry_delay,
            "heartbeat": heartbeat
        }
        
        # Connection and channel
        self._connection = None
        self._channel = None
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Track declared queues
        self._declared_queues = set()
        
        # For consumer callbacks
        self._consumer_tasks = {}
        self._message_queues = {}
        self._message_events = {}
    
    def _get_default_secret(self) -> bytes:
        """Get default secret key from environment or use fallback"""
        import os
        secret = os.getenv('RABBITMQ_HMAC_SECRET', 'default-secret-key')
        return secret.encode() if isinstance(secret, str) else secret
    
    async def _get_connection(self) -> aio_pika.RobustConnection:
        """Get or create connection"""
        if self._connection is None or self._connection.is_closed:
            self.logger.debug("Creating new connection")
            try:
                self._connection = await aio_pika.connect_robust(
                    self.connection_url,
                    **self.connection_kwargs
                )
            except Exception as e:
                self.logger.error(f"Error connecting to RabbitMQ: {e}")
                raise
        return self._connection
    
    async def _get_channel(self) -> aio_pika.RobustChannel:
        """Get or create channel"""
        if self._channel is None or self._channel.is_closed:
            connection = await self._get_connection()
            self.logger.debug("Creating new channel")
            try:
                self._channel = await connection.channel()
            except Exception as e:
                self.logger.error(f"Error creating channel: {e}")
                raise
        return self._channel
    
    async def close(self):
        """Close the connection and channel safely"""
        if self._channel is not None and not self._channel.is_closed:
            try:
                await self._channel.close()
                self.logger.debug("Channel closed")
            except Exception as e:
                self.logger.warning(f"Error closing channel: {e}")
            finally:
                self._channel = None
                
        if self._connection is not None and not self._connection.is_closed:
            try:
                await self._connection.close()
                self.logger.debug("Connection closed")
            except Exception as e:
                self.logger.warning(f"Error closing connection: {e}")
            finally:
                self._connection = None
    
    async def declare_queue(self, queue_name: str, durable: bool = True) -> aio_pika.Queue:
        """Declare a queue"""
        channel = await self._get_channel()
        
        if queue_name not in self._declared_queues:
            queue = await channel.declare_queue(
                queue_name, 
                durable=durable,
                auto_delete=False
            )
            self._declared_queues.add(queue_name)
            return queue
        else:
            return await channel.get_queue(queue_name)
    
    def _generate_hmac(self, message_body: bytes) -> str:
        """Generate HMAC signature for message body"""
        secret_bytes = self.secret_key
        if isinstance(secret_bytes, str):
            secret_bytes = secret_bytes.encode()
            
        return hmac.new(
            secret_bytes,
            msg=message_body,
            digestmod=hashlib.sha256
        ).hexdigest()
    
    def _verify_hmac(self, message_body: bytes, signature: str) -> bool:
        """Verify HMAC signature for message body"""
        expected = self._generate_hmac(message_body)
        return hmac.compare_digest(signature, expected)
    
    async def publish(self, queue_name: str, message: Union[Dict, Any], durable: bool = True):
        """
        Publish a message to a queue with HMAC signature
        
        Args:
            queue_name: Name of the queue
            message: Message to publish (will be JSON serialized)
            durable: Whether the queue should be durable
        """
        # Ensure queue exists
        await self.declare_queue(queue_name, durable=durable)
        
        # Serialize message
        if isinstance(message, dict):
            body = json.dumps(message).encode()
        elif isinstance(message, str):
            body = message.encode()
        elif isinstance(message, bytes):
            body = message
        else:
            body = json.dumps(message).encode()
        
        # Generate signature
        signature = self._generate_hmac(body)
        
        # Create message with signature in headers
        aio_message = Message(
            body=body,
            delivery_mode=DeliveryMode.PERSISTENT if durable else DeliveryMode.NOT_PERSISTENT,
            headers={'hmac': signature}
        )
        
        # Publish message
        channel = await self._get_channel()
        await channel.default_exchange.publish(
            aio_message,
            routing_key=queue_name
        )
        
        self.logger.debug(f"Published message to {queue_name}")
    
    def _init_queue_resources(self, queue_name: str):
        """Initialize resources for a queue"""
        if queue_name not in self._message_queues:
            self._message_queues[queue_name] = asyncio.Queue()
        
        if queue_name not in self._message_events:
            self._message_events[queue_name] = asyncio.Event()
    
    async def _process_message(
        self, 
        message: AbstractIncomingMessage, 
        queue_name: str, 
        callback: Callable
    ):
        """Process a received message with HMAC verification"""
        async with message.process():
            try:
                body = message.body
                headers = message.headers or {}
                
                # Verify HMAC signature
                if 'hmac' in headers:
                    signature = headers['hmac']
                    
                    if self._verify_hmac(body, signature):
                        # Parse message if JSON
                        try:
                            payload = json.loads(body)
                        except json.JSONDecodeError:
                            payload = body
                        
                        # Store message in queue
                        if queue_name in self._message_queues:
                            await self._message_queues[queue_name].put(payload)
                            
                            # Signal message received
                            if queue_name in self._message_events:
                                self._message_events[queue_name].set()
                        
                        # Call callback
                        if callable(callback):
                            if asyncio.iscoroutinefunction(callback):
                                await callback(payload)
                            else:
                                callback(payload)
                    else:
                        self.logger.warning(f"Invalid HMAC signature for message on {queue_name}")
                else:
                    self.logger.warning(f"Message on {queue_name} missing HMAC signature")
            except Exception as e:
                self.logger.error(f"Error processing message: {e}")
    
    async def start_consumer(
        self, 
        queue_name: str, 
        callback: Callable,
        prefetch_count: int = 10
        ) -> str:
        """
        Start consuming messages from a queue

        Args:
            queue_name: Name of the queue
            callback: Callback function to process messages
            prefetch_count: Number of messages to prefetch

        Returns:
            Consumer tag
        """
        # Initialize resources
        self._init_queue_resources(queue_name)
        
        # Declare queue
        queue = await self.declare_queue(queue_name)
        
        # Set QoS
        channel = await self._get_channel()
        await channel.set_qos(prefetch_count=prefetch_count)
        
        # Start consuming
        consumer_tag = f"consumer-{queue_name}-{id(self)}"
        
        async def _consumer_callback(message: aio_pika.abc.AbstractIncomingMessage):
            await self._process_message(message, queue_name, callback)
        
        # Start consuming and get the consumer tag
        consumer_tag = await queue.consume(_consumer_callback, consumer_tag=consumer_tag)
        self.logger.info(f"Started consumer for {queue_name} with tag {consumer_tag}")
        
        return consumer_tag
    
    async def start_consumer_task( 
        self, 
        queue_name: str, 
        callback: Callable,
        prefetch_count: int = 10
        ) -> asyncio.Task:
        """
        Start a consumer in a separate task

        Args:
            queue_name: Name of the queue
            callback: Callback function to process messages
            prefetch_count: Number of messages to prefetch

        Returns:
            Task object for the consumer
        """
        async def _consumer_task():
            # Store the consumer tag for later cancellation
            consumer_tag = None
            try:
                # Start consumer
                consumer_tag = await self.start_consumer(
                    queue_name, 
                    callback,
                    prefetch_count
                )

                # Keep task alive
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                # Task cancelled, stop consuming
                if consumer_tag:
                    try:
                        channel = await self._get_channel()
                        # Use basic_cancel instead of cancel
                        await channel.basic_cancel(consumer_tag)
                        self.logger.info(f"Cancelled consumer {consumer_tag} for {queue_name}")
                    except Exception as e:
                        self.logger.error(f"Error cancelling consumer: {e}")
                # Re-raise to properly handle task cancellation
                raise
            
        # Create and start the task
        task = asyncio.create_task(_consumer_task())

        # Store task reference
        self._consumer_tasks[queue_name] = task

        return task
    
    async def stop_consumer_task(self, queue_name: str, timeout: float = 5.0):
        """
        Stop a consumer task
        
        Args:
            queue_name: Name of the queue
            timeout: Timeout in seconds
        """
        if queue_name in self._consumer_tasks:
            task = self._consumer_tasks[queue_name]
            
            # Cancel task
            task.cancel()
            
            # Wait for task to finish with timeout
            try:
                await asyncio.wait_for(task, timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.logger.warning(f"Timeout waiting for consumer task to stop for {queue_name}")
            
            # Remove task reference
            del self._consumer_tasks[queue_name]
            
            self.logger.info(f"Stopped consumer task for {queue_name}")
    
    async def get_all_messages(self, queue_name: str) -> List[Any]:
        """
        Get all messages received on a queue
        
        Args:
            queue_name: Name of the queue
            
        Returns:
            List of messages
        """
        if queue_name not in self._message_queues:
            return []
        
        messages = []
        
        # Get all messages without waiting
        while not self._message_queues[queue_name].empty():
            try:
                message = self._message_queues[queue_name].get_nowait()
                self._message_queues[queue_name].task_done()
                messages.append(message)
            except asyncio.QueueEmpty:
                break
        
        return messages
    
    async def wait_for_messages(
        self, 
        queue_name: str, 
        count: int, 
        timeout: float = 5.0
    ) -> List[Any]:
        """
        Wait for a specific number of messages
        
        Args:
            queue_name: Name of the queue
            count: Number of messages to wait for
            timeout: Timeout in seconds
            
        Returns:
            List of messages received within timeout
        """
        # Initialize resources
        self._init_queue_resources(queue_name)
        
        # Start timer
        start_time = asyncio.get_event_loop().time()
        
        # Reset event
        self._message_events[queue_name].clear()
        
        # Wait until timeout or message count reached
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            # Check if we have enough messages
            if self._message_queues[queue_name].qsize() >= count:
                break
            
            # Calculate remaining time
            remaining = timeout - (asyncio.get_event_loop().time() - start_time)
            if remaining <= 0:
                break
            
            # Wait for next message
            try:
                # Reset event before waiting
                self._message_events[queue_name].clear()
                await asyncio.wait_for(
                    self._message_events[queue_name].wait(),
                    timeout=min(0.5, remaining)
                )
            except asyncio.TimeoutError:
                continue
        
        # Get all available messages
        return await self.get_all_messages(queue_name)
    
    async def wait_for_message(self, queue_name: str, timeout: float = 5.0) -> Optional[Any]:
        """
        Wait for a single message on a queue with timeout
        
        Args:
            queue_name: Name of the queue
            timeout: Timeout in seconds
            
        Returns:
            Message or None if timeout
        """
        messages = await self.wait_for_messages(queue_name, 1, timeout)
        return messages[0] if messages else None