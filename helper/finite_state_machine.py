from enum import Enum
from typing import Dict, Optional

class State(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class BaseStateMachine:
    def __init__(self):
        self._state = State.IDLE
        self._transitions: Dict[State, set] = {
            State.IDLE: {State.PROCESSING},
            State.PROCESSING: {State.COMPLETED, State.FAILED},
            State.FAILED: {State.IDLE}
        }
        self.current_context: Optional[dict] = None

    @property
    def state(self) -> State:
        return self._state

    def transition(self, new_state: State, context: dict = None) -> bool:
        if new_state in self._transitions.get(self._state, set()):
            self._state = new_state
            self.current_context = context or {}
            return True
        return False

    def reset(self):
        self._state = State.IDLE
        self.current_context = None