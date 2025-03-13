# tests/integration/test_full_flow.py
import pika
import json
import hmac
import hashlib
import time

def send_test_command(command: dict, secret: str):
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()
    
    body = json.dumps(command).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    
    channel.basic_publish(
        exchange='',
        routing_key='tpm.commands',
        body=body,
        properties=pika.BasicProperties(
            headers={'hmac': signature}
        )
    )
    connection.close()

def test_integration_flow():
    # 1. Send provision command
    send_test_command({
        "action": "tpm_provision",
        "args": ["--test-mode"]
    }, "test_secret")
    
    # 2. Verify results
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()
    
    def callback(ch, method, properties, body):
        result = json.loads(body)
        assert result['success'] is True
        assert 'signing_key.pem' in result['artifacts']
        connection.close()
    
    channel.basic_consume(
        queue='tpm.results',
        on_message_callback=callback,
        auto_ack=True
    )
    channel.start_consuming()