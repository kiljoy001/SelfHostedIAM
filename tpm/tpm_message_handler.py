# tpm/tpm_message_handler.py
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
    
    def emit_state_change(self, old_state: State, new_state: State, context: dict = None):
        """Emit a state change event message"""
        state_msg = StateChangeMessage(
            event_type="state_change",
            source="tpm",
            old_state=old_state.value,
            new_state=new_state.value,
            data=context or {}
        )
        self.publish("tpm.state_change", state_msg.to_dict())

    def handle_tpm_command(self, message: dict):
        """Process validated TPM commands"""
        self.last_response = None
        self.last_error = None
        
        try:
            # Convert to typed message
            cmd_message = MessageFactory.create_from_dict(message)
            
            logging.debug(f"Processing message: {cmd_message.id}")
            command = cmd_message.command
            args = cmd_message.args
            message_id = cmd_message.id

            # State validation
            current_state = self.state_machine.state
            if current_state != State.IDLE:
                self.last_error = f"System busy (current state: {current_state.value})"
                error_msg = TPMResponseMessage(
                    correlation_id=message_id,
                    success=False,
                    error=self.last_error
                )
                self.publish("tpm.error", error_msg.to_dict())
                return

            # Transition to processing state
            old_state = self.state_machine.state
            if self.state_machine.transition(State.PROCESSING, {"command": command, "args": args}):
                # Emit state change event
                self.emit_state_change(old_state, State.PROCESSING, {"command": command})
                
                # Execute the command
                result = self.script_runner.execute(command, args)
                
                # Create response message
                response = TPMResponseMessage(
                    correlation_id=message_id,
                    success=result.get("success", False),
                    result=result,
                    error=result.get("error")
                )
                
                # Transition based on result
                old_state = self.state_machine.state
                if result["success"]:
                    self.state_machine.transition(State.COMPLETED, result)
                    self.emit_state_change(old_state, State.COMPLETED, result)
                    self.last_response = response
                    self.publish("tpm.result", response.to_dict())
                else:
                    self.state_machine.transition(State.FAILED, result)
                    self.emit_state_change(old_state, State.FAILED, result)
                    self.last_error = response.error
                    self.publish("tpm.error", response.to_dict())
                
        except Exception as e:
            # Handle any unexpected errors
            message_id = message.get("id", "unknown") if isinstance(message, dict) else "unknown"
            self.last_error = str(e)
            
            # Transition to failed state
            old_state = self.state_machine.state
            context = {"error": str(e), "message_id": message_id}
            self.state_machine.transition(State.FAILED, context)
            self.emit_state_change(old_state, State.FAILED, context)
            
            # Send error response
            error_msg = TPMResponseMessage(
                correlation_id=message_id,
                success=False,
                error=str(e)
            )
            self.publish("tpm.error", error_msg.to_dict())
            logging.error(f"Command processing failed: {e}")
        finally:
            # Reset state or transition back to IDLE
            old_state = self.state_machine.state
            if old_state != State.IDLE:
                self.state_machine.reset()
                self.emit_state_change(old_state, State.IDLE, {})