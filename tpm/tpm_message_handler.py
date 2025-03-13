from helper.base_messenger import BaseMessageHandler
from helper.finite_state_machine import BaseStateMachine
from helper.script_runner import ScriptRunner

class TPMMessageHandler(BaseMessageHandler):
    def __init__(self, script_runner: ScriptRunner, state_machine: BaseStateMachine, **kwargs):
        super().__init__(**kwargs)
        self.script_runner = script_runner
        self.state_machine = state_machine
        # Subscribe to TPM commands
        self.subscribe(
            routing_key="tpm.command.#",  # Wildcard for all TPM commands
            queue_name="tpm_worker",
            callback=self.handle_tpm_command
        )

    def handle_tpm_command(self, message: dict):
        """Process TPM-related commands"""
        command = message.get("action")
        args = message.get("args", [])

        if self.state_machine.state != State.IDLE:
            self.publish("tpm.error", {"error": "System busy"})
            return

        # Transition state and execute
        if self.state_machine.transition(State.PROCESSING, {"command": command}):
            try:
                result = self.script_runner.execute(command, args)
                if result["success"]:
                    self.state_machine.transition(State.COMPLETED, result)
                    self.publish("tpm.result", result)
                else:
                    self.state_machine.transition(State.FAILED, result)
                    self.publish("tpm.error", result)
            except Exception as e:
                self.publish("tpm.error", {"error": str(e)})
            finally:
                self.state_machine.reset()