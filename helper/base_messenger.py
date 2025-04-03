# helper/base_messenger.py
import os
import pika
import json
import hmac
import hashlib
import logging
import asyncio
import threading
from typing import Callable, Optional, Dict, Any
from pika.adapters.asyncio_connection import AsyncioConnection

class BaseMessageHandler:
    def __init__(self, host: str = None, secret_key: str = None, exchange: str = "app_events"):
        # Configure logging
        logging.basicConfig(
            level=logging.DEBUG if os.getenv('DEBUG', '0') == '1' else logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Secret key handling
        if secret_key is None:
            secret_key = os.getenv("HMAC_SECRET", "default_secret")
        
        # Convert to bytes if it's not already
        self.secret_key = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key

        self._verified_callback = None  # Track the active callback
        
        # Connection setup
        self.connection = None
        self.channel = None
        self.exchange = exchange
        self._consuming = False
        self._consume_thread = None

        # Determine host with multiple fallback options
        possible_hosts = [
            host,  # Explicitly passed host
            os.getenv('RABBITMQ_HOST'),  # Environment variable
            'localhost',  # Default localhost
            'rabbitmq',   # Common Docker service name
        ]

        # Connect to RabbitMQ
        self._connect_to_rabbitmq(possible_hosts)
        
        # Declare exchange if channel exists
        if self.channel:
            self._declare_exchange()

    def _connect_to_rabbitmq(self, hosts: list):
        """
        Attempt to connect to RabbitMQ using a list of possible hosts
        
        :param hosts: List of potential hostnames to try
        """
        for attempted_host in filter(None, hosts):
            try:
                logging.info(f"Attempting to connect to RabbitMQ at {attempted_host}")
                
                # Use default credentials, can be overridden by env vars
                credentials = pika.PlainCredentials(
                    username=os.getenv('RABBITMQ_USERNAME', 'guest'),
                    password=os.getenv('RABBITMQ_PASSWORD', 'guest')
                )
                
                connection_params = pika.ConnectionParameters(
                    host=attempted_host,
                    port=int(os.getenv('RABBITMQ_PORT', 5672)),
                    virtual_host=os.getenv('RABBITMQ_VHOST', '/'),
                    credentials=credentials,
                    connection_attempts=3,
                    retry_delay=1
                )
                
                self.connection = pika.BlockingConnection(connection_params)
                self.channel = self.connection.channel()
                
                logging.info(f"Successfully connected to RabbitMQ at {attempted_host}")
                return
            
            except Exception as e:
                logging.warning(f"Failed to connect to RabbitMQ at {attempted_host}. Error: {e}")
        
        # If all connection attempts fail
        logging.error("Could not establish RabbitMQ connection")
        self.connection = None
        self.channel = None

    def _declare_exchange(self):
        """Declare exchange if channel exists"""
        if self.channel:
            try:
                self.channel.exchange_declare(
                    exchange=self.exchange,
                    exchange_type="topic",
                    durable=True
                )
            except Exception as e:
                logging.error(f"Failed to declare exchange: {e}")

    @property
    def message_callback(self):
        """Access point for the verified callback wrapper"""
        return self._verified_callback

    def subscribe(self, routing_key: str, queue_name: str, callback: Callable[[dict], None]):
        """
        Subscribe to a message queue with a specific routing key

        :param routing_key: RabbitMQ routing key to subscribe to
        :param queue_name: Name of the queue to consume from
        :param callback: Callback function to process messages
        """
        # Check if channel exists
        if self.channel is None:
            logging.error("Cannot subscribe: No RabbitMQ channel available")
            raise RuntimeError("RabbitMQ channel not initialized")

        # Create a verified callback wrapper
        verified_callback = self._create_verified_callback(callback)
        self._verified_callback = verified_callback

        try:
            # Declare queue and make it durable
            self.channel.queue_declare(queue=queue_name, durable=True)

            # Bind queue to exchange with routing key
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=queue_name,
                routing_key=routing_key
            )

            # Setup consumer
            self.channel.basic_consume(
                queue=queue_name,
                on_message_callback=verified_callback
            )

            logging.info(f"Subscribed to queue {queue_name} with routing key {routing_key}")

        except Exception as e:
            logging.error(f"Failed to subscribe to queue {queue_name}: {e}")
            raise

    def _create_verified_callback(self, user_callback: Callable) -> Callable:
        """Factory method for creating verified callbacks"""
        def wrapper(channel, method, properties, body):
            # HMAC validation logic
            received_hmac = properties.headers.get("hmac", "") if hasattr(properties, 'headers') and properties.headers else ""
            valid_hmac = hmac.new(
                self.secret_key,
                body,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(received_hmac, valid_hmac):
                channel.basic_reject(method.delivery_tag, requeue=False)
                return

            try:
                message = json.loads(body)
                # Process in a separate thread to avoid blocking
                threading.Thread(target=self._process_message, 
                                args=(user_callback, message, channel, method.delivery_tag)).start()
            except json.JSONDecodeError:
                channel.basic_reject(method.delivery_tag, requeue=False)
        
        return wrapper
    
    def _process_message(self, callback, message, channel, delivery_tag):
        """Process a message in a separate thread"""
        try:
            # Call the user callback
            callback(message)
            # Acknowledge the message
            channel.basic_ack(delivery_tag)
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            channel.basic_nack(delivery_tag, requeue=False)

    def publish(self, routing_key: str, message: dict):
        """
        Publish a message to RabbitMQ

        :param routing_key: Routing key for the message
        :param message: Message payload
        """
        if not self.channel:
            logging.error("Cannot publish: No RabbitMQ channel available")
            return False

        try:
            # Serialize message
            serialized_message = json.dumps(message).encode('utf-8')
            
            # Calculate HMAC
            hmac_digest = hmac.new(
                self.secret_key,
                serialized_message,
                hashlib.sha256
            ).hexdigest()
            
            # Publish message
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=serialized_message,
                properties=pika.BasicProperties(
                    headers={"hmac": hmac_digest},
                    delivery_mode=2  # Make message persistent
                )
            )
            
            return True
        
        except Exception as e:
            logging.error(f"Error publishing message: {e}")
            return False
    
    def start_consuming(self, non_blocking=True):
        """
        Start consuming messages
        
        :param non_blocking: If True, runs in a separate thread; if False, blocks
        """
        if self._consuming:
            logging.warning("Already consuming messages")
            return False
            
        if not self.channel:
            logging.error("Cannot start consuming: No channel available")
            return False
            
        if non_blocking:
            # Start in a separate thread
            self._consume_thread = threading.Thread(target=self._consume_loop)
            self._consume_thread.daemon = True
            self._consume_thread.start()
            self._consuming = True
            logging.info("Started message consumption in background thread")
            return True
        else:
            # Blocking consumption
            try:
                self._consuming = True
                logging.info("Starting message consumption (blocking)")
                self.channel.start_consuming()
                return True
            except Exception as e:
                self._consuming = False
                logging.error(f"Error in message consumption: {e}")
                return False
    
    def _consume_loop(self):
        """Background thread for consuming messages"""
        try:
            self.channel.start_consuming()
        except Exception as e:
            logging.error(f"Error in consume loop: {e}")
        finally:
            self._consuming = False
    
    def stop_consuming(self):
        """Stop consuming messages"""
        if not self._consuming:
            logging.warning("Not currently consuming messages")
            return True
            
        if not self.channel:
            logging.error("Cannot stop consuming: No channel available")
            return False
            
        try:
            self.channel.stop_consuming()
            if self._consume_thread and self._consume_thread.is_alive():
                self._consume_thread.join(timeout=2)
            self._consuming = False
            logging.info("Stopped message consumption")
            return True
        except Exception as e:
            logging.error(f"Error stopping consumption: {e}")
            return False
    
    def close(self):
        """Close the connection"""
        if self._consuming:
            self.stop_consuming()
        
        if self.channel and self.channel.is_open:
            try:
                self.channel.close()
                self._channel = None
            except Exception as e:
                logging.error(f"Error closing channel: {e}")
        
        if self.connection and self.connection.is_open:
            try:
                self.connection.close()
                self._connection = None
            except Exception as e:
                logging.error(f"Error closing connection: {e}")