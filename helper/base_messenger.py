
import pika
import json
import hmac
import hashlib
import os
import logging
from typing import Callable, Optional

class BaseMessageHandler:
    def __init__(
        self,
        host: str = "rabbitmq",
        secret_key: str = None,
        exchange: str = "app_events",
        exchange_type: str = "topic"
    ):
        self.secret_key = secret_key or os.getenv("HMAC_SECRET", "default_secret").encode()
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=host))
        self.channel = self.connection.channel()
        self.channel.confirm_delivery()
        self.exchange = exchange
        self.exchange_type = exchange_type
        self._declare_exchange()

    def _declare_exchange(self):
        """Declare a topic exchange for flexible routing"""
        self.channel.exchange_declare(
            exchange=self.exchange,
            exchange_type=self.exchange_type,
            durable=True
        )

    def _generate_hmac(self, message_body: bytes) -> str:
        return hmac.new(
            self.secret_key,
            msg=message_body,
            digestmod=hashlib.sha256
        ).hexdigest()

    def publish(
        self,
        routing_key: str,
        message: dict,
        persistent: bool = True
    ):
        """Publish a message to a topic"""
        try:
            body = json.dumps(message).encode()
            signature = self._generate_hmac(body)
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=body,
                properties=pika.BasicProperties(
                    headers={"hmac": signature},
                    delivery_mode=pika.DeliveryMode.Persistent if persistent else None
                )
            )
            logging.info(f"Published to {routing_key}")
        except pika.exceptions.AMQPError as e:
            logging.error(f"Publish failed: {e}")

    def subscribe(
        self,
        routing_key: str,
        queue_name: str,
        callback: Callable[[dict], None],
        auto_ack: bool = False
    ):
        """Subscribe to messages matching a routing key"""
        try:
            # Declare a queue and bind it to the exchange
            self.channel.queue_declare(queue=queue_name, durable=True)
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=queue_name,
                routing_key=routing_key
            )
            self.channel.basic_qos(prefetch_count=1)

            def _verified_callback(ch, method, properties, body):
                # HMAC validation logic
                received_hmac = properties.headers.get("hmac", "")
                valid_hmac = self._generate_hmac(body)
                if not hmac.compare_digest(received_hmac, valid_hmac):
                    ch.basic_reject(method.delivery_tag, requeue=False)
                    return

                try:
                    message = json.loads(body)
                    callback(message)
                    ch.basic_ack(method.delivery_tag)
                except json.JSONDecodeError:
                    ch.basic_reject(method.delivery_tag, requeue=False)

            self.channel.basic_consume(
                queue=queue_name,
                on_message_callback=_verified_callback,
                auto_ack=auto_ack
            )
            logging.info(f"Subscribed to {routing_key} via {queue_name}")
        except pika.exceptions.AMQPError as e:
            logging.error(f"Subscription failed: {e}")

    def start_consuming(self):
        self.channel.start_consuming()