# tests/test_tpm_handler.py
import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from your_module import TPMMessageHandler, BaseStateMachine, ScriptRunner

@pytest.fixture
def tpm_handler():
    scripts = {
        "tpm_provision": Path("tests/mock_scripts/provision.sh"),
        "generate_cert": Path("tests/mock_scripts/generate_cert.sh")
    }
    runner = ScriptRunner(scripts)
    state_machine = BaseStateMachine()
    
    return TPMMessageHandler(
        script_runner=runner,
        state_machine=state_machine,
        host="localhost"
    )

def test_valid_command(tpm_handler):
    """Test successful command execution"""
    test_msg = {
        "action": "tpm_provision",
        "args": ["--test-mode"]
    }
    
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(stdout="OK", stderr="", returncode=0)
        tpm_handler.handle_tpm_command(test_msg)
        
    assert tpm_handler.state_machine.state == State.IDLE
    assert "OK" in tpm_handler.messaging.last_response

def test_unauthorized_command(tpm_handler):
    """Test blocked command execution"""
    test_msg = {
        "action": "dangerous_script",
        "args": []
    }
    
    tpm_handler.handle_tpm_command(test_msg)
    
    assert "not allowed" in tpm_handler.messaging.last_error
    assert tpm_handler.state_machine.state == State.IDLE

def test_concurrent_commands(tpm_handler):
    """Test state machine blocking"""
    msg1 = {"action": "tpm_provision"}
    msg2 = {"action": "generate_cert"}
    
    tpm_handler.handle_tpm_command(msg1)
    tpm_handler.handle_tpm_command(msg2)
    
    assert "busy" in tpm_handler.messaging.last_error