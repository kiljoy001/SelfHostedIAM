# tpm/tpm_service.py
import asyncio
import logging
import threading
import os
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional, Union, Awaitable

from helper.finite_state_machine import BaseStateMachine
from helper.script_runner import ScriptRunner
from tpm.tpm_message_handler import TPMMessageHandler

logger = logging.getLogger(__name__)

class TPMService:
    """
    TPM Service that provides TPM functionality through message processing.
    Supports both synchronous and asynchronous operations.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the TPM service.
        
        Args:
            config: Configuration dictionary with settings
        """
        self.config = config or {}
        self.state_machine = None
        self.script_runner = None
        self.message_handler = None
        self.active = False
        self.loop = None  # AsyncIO event loop for async operations
        self.worker_thread = None
        
        # Initialize components
        self._initialize()
    
    def _initialize(self):
        """Initialize TPM service components"""
        logger.info("Initializing TPM service")
        
        # Get configuration values with defaults
        rabbitmq_host = self.config.get('rabbitmq_host', 'localhost')
        secret_key = self.config.get('secret_key', os.getenv('HMAC_SECRET', 'default_secret'))
        exchange = self.config.get('exchange', 'app_events')
        
        # Determine script paths
        script_dir = self.config.get('script_dir', os.path.dirname(__file__))
        script_paths = self.config.get('script_paths', {
            "tpm_provision": Path(script_dir) / "tpm_provisioning.sh",
            "generate_cert": Path(script_dir) / "tpm_self_signed_cert.sh",
            "get_random": Path(script_dir) / "tpm_random_number.sh"
        })
        
        # Create components
        self.state_machine = BaseStateMachine()
        self.script_runner = ScriptRunner(script_paths)
        
        # Create message handler
        self.message_handler = TPMMessageHandler(
            script_runner=self.script_runner,
            state_machine=self.state_machine,
            host=rabbitmq_host,
            secret_key=secret_key,
            exchange=exchange
        )
        
        logger.info("TPM service initialized")
    
    def start(self) -> bool:
        """Start the TPM service in a non-blocking way"""
        if self.active:
            logger.warning("TPM service already running")
            return True
        
        logger.info("Starting TPM service")
        if self.message_handler and self.message_handler.channel:
            # Start consuming messages in a non-blocking way
            result = self.message_handler.start_consuming(non_blocking=True)
            self.active = result
            return result
        else:
            logger.error("Cannot start TPM service: No message handler or channel")
            return False
    
    async def start_async(self) -> bool:
        """Start the TPM service asynchronously"""
        # We can use the thread-based start method as it's already non-blocking
        return self.start()
    
    def stop(self) -> bool:
        """Stop the TPM service"""
        if not self.active:
            logger.warning("TPM service not running")
            return True
        
        logger.info("Stopping TPM service")
        
        try:
            if self.message_handler:
                try:
                    # Try normal shutdown - this should close channels but not connections
                    result = self.message_handler.stop_consuming()
                    return True
                except Exception as e:
                    logger.error(f"Error during normal stop: {e}")
                    
                    # If stop_consuming fails, try to clean up just this service's channel
                    try:
                        if hasattr(self.message_handler, 'channel') and self.message_handler.channel:
                            self.message_handler.channel.close()
                        return True
                    except Exception as e2:
                        logger.error(f"Failed to close channel: {e2}")
                        # Don't close the connection as it may be shared
                        return False
            return True
        finally:
            # Always set to inactive regardless of success/failure
            self.active = False
    
    async def stop_async(self) -> bool:
        """Stop the TPM service asynchronously"""
        # We can use the thread-based stop method
        return self.stop()
    
    def execute_command(self, command: str, args: List[str] = None) -> Dict[str, Any]:
        """Execute a TPM command directly (synchronously)"""
        if not self.script_runner:
            raise RuntimeError("TPM service not properly initialized")
        
        return self.script_runner.execute(command, args or [])
    
    async def execute_command_async(self, command: str, args: List[str] = None) -> Dict[str, Any]:
        """Execute a TPM command asynchronously"""
        # Run the command in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.execute_command, command, args
        )
    
    def send_command(self, command: str, args: List[str] = None) -> str:
        """Send a TPM command through the message queue"""
        if not self.message_handler or not self.message_handler.channel:
            raise RuntimeError("TPM service not properly initialized")
        
        # The message handler will handle publishing
        message_id = self.message_handler.publish_command(command, args or [])
        return message_id
    
    async def send_command_async(self, command: str, args: List[str] = None) -> str:
        """Send a TPM command asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.send_command, command, args
        )
    
    def get_handler(self):
        """Get the TPM message handler"""
        return self.message_handler
    
    def get_state(self):
        """Get the current state of the TPM service"""
        if self.state_machine:
            return self.state_machine.state
        return None
    
    def is_active(self):
        """Check if the service is active"""
        return self.active
    
    def add_event_listener(self, event_type: str, callback: Union[Callable, Awaitable]):
        """
        Add an event listener for TPM events
        
        Args:
            event_type: Type of event to listen for (e.g., 'state_change')
            callback: Callback function (sync or async)
        """
        if not hasattr(self, '_event_listeners'):
            self._event_listeners = {}
            
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
            
        self._event_listeners[event_type].append(callback)
        return True
    
    def emit_event(self, event_type: str, *args, **kwargs):
        """
        Emit an event to all registered listeners
        
        Args:
            event_type: Type of event to emit
            args, kwargs: Arguments to pass to listeners
        """
        if not hasattr(self, '_event_listeners') or event_type not in self._event_listeners:
            return 0
            
        count = 0
        for listener in self._event_listeners[event_type]:
            try:
                if asyncio.iscoroutinefunction(listener):
                    # For async listeners, we need to schedule them
                    if self.loop is None:
                        # Ensure we have a loop
                        try:
                            self.loop = asyncio.get_event_loop()
                        except RuntimeError:
                            # Create a new loop if none is available
                            self.loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(self.loop)
                    
                    # Schedule the async callback
                    asyncio.run_coroutine_threadsafe(
                        listener(*args, **kwargs), self.loop
                    )
                else:
                    # For synchronous listeners, just call directly
                    listener(*args, **kwargs)
                count += 1
            except Exception as e:
                logger.error(f"Error in event listener for {event_type}: {e}")
        
        return count