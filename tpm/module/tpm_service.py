# tpm/tpm_service.py
import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional, Union, Awaitable

from helper.finite_state_machine import BaseStateMachine, State
from helper.script_runner import ScriptRunner
from tpm.tpm_message_handler import TPMMessageHandler
from helper.base_service import BaseService

logger = logging.getLogger(__name__)

class TPMService(BaseService):
    """
    TPM Service that provides TPM functionality through message processing.
    Supports both synchronous and asynchronous operations.
    """
    
    async def _initialize(self):
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
        
        script_hashes = self.config.get('script_hashes', {
            "tpm_provision": "56175ef85b51d414f7cc4cf7da5cc6c5c65fd59d4de74431ea3ccd9bd80e3bec",
            "generate_cert": "019325eca0c5748aa6079fd99eabe64f67d0b4573a05afec39f0e6f627840d76",
            "get_random": "ad8ff1334920941997f18d5da362abcf80bea5df5445ccc0d6bec4e8cb5612dc"
        })
        
        # Create script runner - no need to create state machine as it's already in BaseService
        self.script_runner = ScriptRunner(script_paths, script_hashes)
        
        # Create message handler
        self.message_handler = await self._run_in_executor(
            lambda: TPMMessageHandler(
                script_runner=self.script_runner,
                state_machine=self.state_machine,
                host=rabbitmq_host,
                secret_key=secret_key,
                exchange=exchange
            )
        )
        
        logger.info("TPM service initialized")
    
    async def start(self) -> bool:
        """Start the TPM service asynchronously"""
        # First call the parent class's start method to update state
        await super().start()
        
        if self.active:
            logger.warning("TPM service already running")
            return True
        
        logger.info("Starting TPM service")
        if self.message_handler and self.message_handler.channel:
            # Start consuming messages in a non-blocking way
            result = await self._run_in_executor(
                lambda: self.message_handler.start_consuming(non_blocking=True)
            )
            if result:
                self.active = True
                self.state_machine.transition(State.COMPLETED, {"action": "start", "completed": True})
                await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.COMPLETED)
            return result
        else:
            logger.error("Cannot start TPM service: No message handler or channel")
            self.state_machine.transition(State.FAILED, {"action": "start", "error": "No message handler or channel"})
            await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.FAILED)
            return False
    
    async def stop(self) -> bool:
        """Stop the TPM service asynchronously"""
        # First call the parent class's stop method to update state
        await super().stop()
        
        if not self.active:
            logger.warning("TPM service not running")
            return True

        logger.info("Stopping TPM service")

        try:
            if self.message_handler:
                try:
                    # Try normal shutdown - this should close channels but not connections
                    result = await self._run_in_executor(
                        lambda: self.message_handler.stop_consuming()
                    )
                    self.state_machine.transition(State.IDLE, {"action": "stop", "completed": True})
                    await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.IDLE)
                    return True
                except Exception as e:
                    logger.error(f"Error during normal stop: {e}")

                    # If stop_consuming fails, try to clean up just this service's channel
                    try:
                        if hasattr(self.message_handler, 'channel') and self.message_handler.channel:
                            await self._run_in_executor(
                                lambda: self.message_handler.channel.close()
                            )
                            self.state_machine.transition(State.IDLE, {"action": "stop", "completed": True})
                            await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.IDLE)
                            return True
                    except Exception as e2:
                        logger.error(f"Failed to close channel: {e2}")
                        self.state_machine.transition(State.FAILED, {"action": "stop", "error": str(e2)})
                        await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.FAILED)
                        # Don't close the connection as it may be shared
                        return False
            self.state_machine.transition(State.IDLE, {"action": "stop", "completed": True})
            await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.IDLE)
            return True
        finally:
            # Always set to inactive regardless of success/failure
            self.active = False
    
    def execute_command(self, command: str, args: List[str] = None) -> Dict[str, Any]:
        """Execute a TPM command directly (synchronously)"""
        if not self.script_runner:
            raise RuntimeError("TPM service not properly initialized")
        
        return self.script_runner.execute(command, args or [])
    
    async def execute_command_async(self, command: str, args: List[str] = None) -> Dict[str, Any]:
        """Execute a TPM command asynchronously"""
        # Update state to processing
        self.state_machine.transition(State.PROCESSING, {
            "action": "execute_command", 
            "command": command,
            "args": args or []
        })
        await self.emit_event("operation_started", operation="execute_command", command=command, args=args or [])
        
        try:
            # Run the command in a thread pool to avoid blocking
            result = await self._run_in_executor(
                lambda: self.execute_command(command, args)
            )
            
            # Set state back to completed
            self.state_machine.transition(State.COMPLETED, {
                "action": "execute_command", 
                "command": command,
                "args": args or [],
                "success": True
            })
            await self.emit_event("operation_completed", operation="execute_command", command=command, args=args or [])
            
            return result
        except Exception as e:
            # Set state to failed
            self.state_machine.transition(State.FAILED, {
                "action": "execute_command", 
                "command": command,
                "args": args or [],
                "error": str(e)
            })
            await self.emit_event("operation_failed", operation="execute_command", command=command, args=args or [], error=str(e))
            raise
        finally:
            # Reset state to IDLE after command is complete
            self.state_machine.reset()
    
    def send_command(self, command: str, args: List[str] = None) -> str:
        """Send a TPM command through the message queue"""
        if not self.message_handler or not self.message_handler.channel:
            raise RuntimeError("TPM service not properly initialized")
        
        # The message handler will handle publishing
        message_id = self.message_handler.publish_command(command, args or [])
        return message_id
    
    async def send_command_async(self, command: str, args: List[str] = None) -> str:
        """Send a TPM command asynchronously"""
        # Update state to processing
        self.state_machine.transition(State.PROCESSING, {
            "action": "send_command", 
            "command": command,
            "args": args or []
        })
        await self.emit_event("operation_started", operation="send_command", command=command, args=args or [])
        
        try:
            # Run in executor to avoid blocking
            message_id = await self._run_in_executor(
                lambda: self.send_command(command, args)
            )
            
            # Set state back to completed
            self.state_machine.transition(State.COMPLETED, {
                "action": "send_command", 
                "command": command,
                "args": args or [],
                "message_id": message_id,
                "success": True
            })
            await self.emit_event("operation_completed", operation="send_command", command=command, args=args or [], message_id=message_id)
            
            return message_id
        except Exception as e:
            # Set state to failed
            self.state_machine.transition(State.FAILED, {
                "action": "send_command", 
                "command": command,
                "args": args or [],
                "error": str(e)
            })
            await self.emit_event("operation_failed", operation="send_command", command=command, args=args or [], error=str(e))
            raise
        finally:
            # Reset state to IDLE after command is complete
            self.state_machine.reset()
    
    def get_handler(self):
        """Get the TPM message handler"""
        return self.message_handler
    
    async def _run_in_executor(self, func):
        """
        Run a synchronous function in an executor (thread pool).
        
        Args:
            func: Function to run
            
        Returns:
            Result of the function call
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)