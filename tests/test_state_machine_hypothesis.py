import pytest
from hypothesis import given, strategies as st
from helper.finite_state_machine import BaseStateMachine, State

class TestStateMachineWithHypothesis:
    
    @given(transitions=st.lists(
        st.sampled_from([State.IDLE, State.PROCESSING, State.COMPLETED, State.FAILED]),
        min_size=1, max_size=20
    ))
    def test_state_machine_always_reaches_valid_state(self, transitions):
        """Test that state machine always ends in a valid state"""
        machine = BaseStateMachine()
        
        # Apply a sequence of transitions
        for state in transitions:
            machine.transition(state)
        
        # Verify final state is valid
        assert machine.state in list(State), f"Invalid final state: {machine.state}"
        
    @given(
        initial_transitions=st.lists(
            st.sampled_from([State.IDLE, State.PROCESSING, State.COMPLETED, State.FAILED]),
            min_size=1, max_size=10
        ),
        reset_position=st.integers(min_value=0, max_value=9)
    )
    def test_state_machine_reset(self, initial_transitions, reset_position):
        """Test that state machine reset works correctly"""
        if not initial_transitions:
            return  # Skip empty transition lists
            
        # Adjust reset position if it's out of bounds
        reset_position = min(reset_position, len(initial_transitions) - 1)
        
        machine = BaseStateMachine()
        
        # Apply initial transitions
        for i, state in enumerate(initial_transitions):
            machine.transition(state)
            
            # Reset at the designated position
            if i == reset_position:
                machine.reset()
                assert machine.state == State.IDLE, "Machine should reset to IDLE state"