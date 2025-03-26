# tpm/tpm_message_handler.py
import uuid
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional

from helper.base_messenger import BaseMessageHandler
from helper.finite_state_machine import BaseStateMachine, State

logger = logging.getLogger(__name__)

class TPMMessageHandler(BaseMessageHandler):
    def __init__(self, script_runner, state_machine, **kwargs):
        super().__init__(**kwargs)
        self.script_runner = script_runner
        self.state_machine = state_machine
        self.last_response = None
        self.last_error = None
        
        self.subscribe(
            routing_key="tpm.command.#",
            queue_name="tpm_worker",
            callback=self.handle_tpm_command
        )

    def handle_tpm_command(self, message: dict):
        """Process validated TPM commands"""
        self.last_response = None
        self.last_error = None
        logging.debug(f"Processing message: {message}")
        command = message.get("action")
        args = message.get("args", [])
        message_id = message.get("id", "unknown")

        # State validation
        if self.state_machine.state != State.IDLE:
            self.last_error = "System busy"
            self.publish("tpm.error", {"error": self.last_error, "id": message_id})
            return

        try:
            if self.state_machine.transition(State.PROCESSING, {"command": command}):
                result = self.script_runner.execute(command, args)
                
                # Add message ID to result for tracking
                result["id"] = message_id
                
                if result["success"]:
                    self.state_machine.transition(State.COMPLETED, result)
                    self.last_response = result
                    self.publish("tpm.result", result)
                else:
                    self.state_machine.transition(State.FAILED, result)
                    self.last_error = result.get("error")
                    self.publish("tpm.error", result)
                    
        except Exception as e:
            self.last_error = str(e)
            error_result = {"error": self.last_error, "id": message_id}
            self.publish("tpm.error", error_result)
            logging.error(f"Command processing failed: {e}")
        finally:
            self.state_machine.reset()

    async def handle_tpm_command_async(self, message: dict):
        """
        Process TPM commands asynchronously
        
        This runs the actual command execution in a thread pool to avoid
        blocking the event loop.
        """
        loop = asyncio.get_event_loop()
        # Run the synchronous handler in a thread pool
        await loop.run_in_executor(None, self.handle_tpm_command, message)

    def publish_command(self, command: str, args: List[str] = None) -> str:
        """
        Publish a TPM command to the message queue.
        
        Args:
            command: The TPM command to execute
            args: Command arguments list
            
        Returns:
            Message ID for tracking
        """
        if not self.channel:
            raise RuntimeError("No RabbitMQ channel available")
        
        # Generate a unique message ID
        message_id = str(uuid.uuid4())
        
        # Create the message payload
        message = {
            "action": command,
            "args": args or [],
            "id": message_id
        }
        
        # Publish the message
        routing_key = f"tpm.command.{command}"
        self.publish(routing_key, message)
        
        return message_id
    
    async def publish_command_async(self, command: str, args: List[str] = None) -> str:
        """Async version of publish_command"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.publish_command, command, args)