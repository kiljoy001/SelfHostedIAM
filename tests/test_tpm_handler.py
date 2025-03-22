# tests/test_tpm_handler.py
import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from helper.finite_state_machine import BaseStateMachine, State
from helper.script_runner import ScriptRunner
from tpm.tpm_message_handler import TPMMessageHandler

@pytest.fixture
def tpm_handler():
    scripts = {
        "tpm_provision": Path("tests/mock_scripts/provision.sh"),
        "generate_cert": Path("tests/mock_scripts/generate_cert.sh")
    }
    runner = ScriptRunner(scripts)
    state_machine = BaseStateMachine()
    
    # Mock messaging infrastructure
    with patch('pika.BlockingConnection'):
        handler = TPMMessageHandler(
            script_runner=runner,
            state_machine=state_machine,
            host="localhost"
        )
        handler.publish = Mock()  # Disable actual message publishing
        yield handler

def test_valid_command(tpm_handler):
    """Test successful command execution"""
    test_msg = {
        "action": "tpm_provision",
        "args": ["--test-mode"]
    }
    
    # Mock ScriptRunner instead of subprocess
    with patch.object(tpm_handler.script_runner, 'execute') as mock_execute:
        mock_execute.return_value = {
            "success": True,
            "output": "OK",
            "error": ""
        }
        tpm_handler.handle_tpm_command(test_msg)
        
    assert tpm_handler.state_machine.state == State.IDLE
    assert "OK" in tpm_handler.last_response["output"]

def test_unauthorized_command(tpm_handler):
    """Test blocked command execution"""
    test_msg = {
        "action": "dangerous_script",
        "args": []
    }
    
    tpm_handler.handle_tpm_command(test_msg)
    
    assert "not allowed" in tpm_handler.last_error
    assert tpm_handler.state_machine.state == State.IDLE

def test_concurrent_commands(tpm_handler):
    """Test state machine blocking"""
    msg1 = {"action": "tpm_provision"}
    msg2 = {"action": "generate_cert"}
    
    # First command processing
    with patch.object(tpm_handler.script_runner, 'execute') as mock_execute:
        mock_execute.return_value = {"success": True}
        tpm_handler.handle_tpm_command(msg1)
    
    # Second command should be blocked
    tpm_handler.handle_tpm_command(msg2)
    
    assert "busy" in tpm_handler.last_error