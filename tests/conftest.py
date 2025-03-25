"""
Global test fixtures and configuration for pytest.
This file is automatically loaded by pytest when running tests.
"""
import os
import pytest
import logging
import hmac
import hashlib
import json
import subprocess
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_hmac(secret: str, body: bytes) -> str:
    """Generate an HMAC signature for a message body"""
    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    return hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Set up the test environment before any tests run.
    This gets run once at the beginning of the test session.
    """
    # Check if TPM simulator is running
    tpm_running = check_tpm_status()
    if not tpm_running:
        logger.warning("⚠️ TPM simulator is not running. TPM tests will be skipped.")
    
    # Check if RabbitMQ is running
    rabbitmq_running = check_rabbitmq_status()
    if not rabbitmq_running:
        logger.warning("⚠️ RabbitMQ is not running. Integration tests will be skipped.")
    
    if rabbitmq_running:
        try:
            # Try to setup RabbitMQ queues
            setup_rabbitmq_queues()
        except Exception as e:
            logger.warning(f"⚠️ Failed to set up RabbitMQ queues: {e}")
    
    yield
    
    # Clean up after all tests are done
    logger.info("Test session completed")

def check_tpm_status():
    """Check if TPM simulator is running"""
    try:
        # Try multiple methods to check TPM status
        
        # Method 1: Check for swtpm process
        ps_result = subprocess.run(
            ["ps", "-ef"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        
        if "swtpm" in ps_result.stdout:
            logger.info("✅ TPM simulator (swtpm) process is running")
            return True
        
        # Method 2: Try using TPM2 tools
        try:
            tpm2_result = subprocess.run(
                ["tpm2_getcap", "properties-fixed"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            
            if tpm2_result.returncode == 0:
                logger.info("✅ TPM is accessible via tpm2_getcap")
                return True
            else:
                logger.warning(f"❌ tpm2_getcap failed: {tpm2_result.stderr}")
        except Exception as e:
            logger.warning(f"Error running tpm2_getcap: {e}")
        
        # Method 3: Check if TPM device exists
        if os.path.exists("/dev/tpm0") or os.path.exists("/dev/tpmrm0"):
            logger.info("✅ TPM device file exists")
            return True
        
        logger.warning("❌ TPM simulator does not appear to be running")
        return False
        
    except Exception as e:
        logger.error(f"Error checking TPM status: {e}")
        return False

def check_rabbitmq_status():
    """Check if RabbitMQ is running"""
    try:
        # Check RabbitMQ status
        result = subprocess.run(
            ["rabbitmqctl", "status"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            logger.info("✅ RabbitMQ is running")
            return True
        else:
            logger.warning(f"❌ RabbitMQ is not running: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error checking RabbitMQ status: {e}")
        return False

def setup_rabbitmq_queues():
    """Set up RabbitMQ queues for testing"""
    try:
        # Try to import pika
        import pika
        
        # Connect to RabbitMQ
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            host='localhost',
            connection_attempts=2,
            retry_delay=1
        ))
        channel = connection.channel()
        
        # Declare exchange
        channel.exchange_declare(
            exchange='app_events',
            exchange_type='topic',
            durable=True
        )
        
        # Define and declare necessary queues
        queues = {
            'tpm.commands': ['tpm.command.#'],
            'tpm.results': [],
            'tpm.error': [],
            'tpm_worker': ['tpm.command.#']
        }
        
        # Create queues and bind to exchange if routing keys are specified
        for queue, routing_keys in queues.items():
            channel.queue_declare(queue=queue, durable=True)
            for routing_key in routing_keys:
                channel.queue_bind(
                    exchange='app_events',
                    queue=queue,
                    routing_key=routing_key
                )
        
        connection.close()
        logger.info("✅ RabbitMQ queues and exchange set up successfully")
        return True
    except ImportError:
        logger.warning("⚠️ Pika not installed, skipping RabbitMQ setup")
        return False
    except Exception as e:
        logger.error(f"❌ Failed to set up RabbitMQ: {e}")
        return False