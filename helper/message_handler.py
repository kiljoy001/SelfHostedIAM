import hmac
import hashlib
import os

class SecureMessageHandler:
    def __init__(self, host: str = 'rabbitmq', secret_key: str = None):
        self.secret_key = secret_key or os.getenv('HMAC_SECRET').encode()
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=host)
        )
        self.channel = self.connection.channel()
        
    def _generate_hmac(self, message_body: bytes) -> str:
        return hmac.new(
            self.secret_key,
            msg=message_body,
            digestmod=hashlib.sha256
        ).hexdigest()

    def send(self, queue: str, message: dict):
        body = json.dumps(message).encode()
        signature = self._generate_hmac(body)
        
        self.channel.basic_publish(
            exchange='',
            routing_key=queue,
            body=body,
            properties=pika.BasicProperties(
                headers={'hmac': signature}
            )
        )

    def listen(self, queue: str, callback):
        def verified_callback(ch, method, properties, body):
            received_hmac = properties.headers.get('hmac', '')
            valid_hmac = self._generate_hmac(body)
            
            if not hmac.compare_digest(received_hmac, valid_hmac):
                ch.basic_nack(delivery_tag=method.delivery_tag)
                logging.error("Invalid HMAC signature")
                return
                
            try:
                message = json.loads(body)
                callback(message)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except json.JSONDecodeError:
                logging.error("Invalid message format")
                ch.basic_nack(delivery_tag=method.delivery_tag)

        self.channel.basic_consume(
            queue=queue,
            on_message_callback=verified_callback
        )