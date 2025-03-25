import threading
import json
import hmac
import hashlib
import time
import logging
import pika
from pathlib import Path
from tpm.tpm_message_handler import TPMMessageHandler
from helper.finite_state_machine import BaseStateMachine
from helper.script_runner import ScriptRunner

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestMessageHandler:
    """
    A temporary message handler for testing purposes that:
    1. Sets up a real TPMMessageHandler instance
    2. Starts consuming messages in a background thread
    3. Processes messages and publishes responses
    4. Can be safely started and stopped
    """
    
    def __init__(self):
        self.running = False
        self.thread = None
        self.handler = None
    
    def start(self):
        """Start the test message handler in a background thread"""
        if self.running:
            logger.warning("Handler is already running")
            return
        
        # Set up scripts
        scripts = {
            "tpm_provision": Path("/tests/mock_scripts/tpm_provisioning.sh"),
            "generate_cert": Path("/tests/mock_scripts/tpm_self_signed_cert.sh")
        }
        
        # Verify scripts exist and are executable
        for name, path in scripts.items():
            if not path.exists():
                logger.warning(f"Script {path} does not exist")
                
                # Create parent directories if they don't exist
                path.parent.mkdir(parents=True, exist_ok=True)
                
                # Create a mock script
                with open(path, 'w') as f:
                    f.write('#!/bin/bash\n')
                    f.write('echo "Mock script execution"\n')
                    f.write('echo "{\\"key\\": \\"value\\"}"\n')  # Mock JSON output
                    f.write('exit 0\n')
                
                # Make it executable
                path.chmod(0o755)
                logger.info(f"Created mock script at {path}")
        
        # Create handler components
        runner = ScriptRunner(scripts)
        state_machine = BaseStateMachine()
        
        # Create the handler
        self.handler = TPMMessageHandler(
            script_runner=runner,
            state_machine=state_machine,
            host="localhost",
            secret_key="test-secret"
        )
        
        # Check if connection was successful
        if not self.handler.channel:
            logger.error("Failed to connect to RabbitMQ")
            return False
        
        # Start consuming messages in a background thread
        self.running = True
        self.thread = threading.Thread(target=self._consume_loop)
        self.thread.daemon = True  # Allow Python to exit even if thread is running
        self.thread.start()
        
        logger.info("Test message handler started")
        return True
    
    def _consume_loop(self):
        """Background thread to consume messages"""
        try:
            logger.info("Starting to consume messages")
            
            # The handler's channel already has a consumer set up,
            # so we just need to start consuming
            self.handler.channel.start_consuming()
            
        except Exception as e:
            logger.error(f"Error in consume loop: {e}")
        finally:
            self.running = False
            logger.info("Consume loop ended")
    
    def stop(self):
        """Stop the test message handler"""
        if not self.running:
            logger.warning("Handler is not running")
            return
        
        try:
            # Stop consuming
            if self.handler.channel:
                self.handler.channel.stop_consuming()
            
            # Wait for thread to end
            self.thread.join(timeout=2)
            
            # Close connection
            if self.handler.connection and self.handler.connection.is_open:
                self.handler.connection.close()
            
            self.running = False
            logger.info("Test message handler stopped")
            
        except Exception as e:
            logger.error(f"Error stopping handler: {e}")

# Example usage - can be imported and used in tests
if __name__ == "__main__":
    handler = TestMessageHandler()
    if handler.start():
        try:
            # Keep it running until interrupted
            while handler.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            handler.stop()