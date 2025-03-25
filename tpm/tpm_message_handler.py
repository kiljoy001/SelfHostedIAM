# tpm/tpm_message_handler.py
from helper.base_messenger import BaseMessageHandler
from helper.finite_state_machine import BaseStateMachine, State
import logging

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

        # State validation
        if self.state_machine.state != State.IDLE:
            self.last_error = "System busy"
            self.publish("tpm.error", {"error": self.last_error})
            return

        try:
            if self.state_machine.transition(State.PROCESSING, {"command": command}):
                result = self.script_runner.execute(command, args)
                
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
            self.publish("tpm.error", {"error": self.last_error})
            logging.error(f"Command processing failed: {e}")
        finally:
            self.state_machine.reset()