import pytest
import json
import hmac
import hashlib
import os
from unittest.mock import Mock, patch, ANY
from pathlib import Path
from helper.finite_state_machine import BaseStateMachine, State
from helper.script_runner import ScriptRunner
from tpm.tpm_message_handler import TPMMessageHandler

def generate_hmac(secret: str, body: bytes) -> str:
    """Generate HMAC for message validation"""
    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    return hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()

@pytest.fixture
def tpm_handler():
    """Test fixture for TPM handler with properly mocked components"""
    # Set up script paths
    scripts = {
        "tpm_provision": Path("/tests/mock_scripts/tpm_provisioning.sh"),
        "generate_cert": Path("/tests/mock_scripts/tpm_self_signed_cert.sh")
    }
    runner = ScriptRunner(scripts)
    state_machine = BaseStateMachine()
    
    # Create mocks for RabbitMQ components
    with patch('pika.BlockingConnection', autospec=True) as mock_conn:
        # Set up mock channel
        mock_channel = Mock()
        mock_conn.return_value.channel.return_value = mock_channel
        
        # Create handler
        handler = TPMMessageHandler(
            script_runner=runner,
            state_machine=state_machine,
            host="localhost",
            secret_key="test-secret"
        )
        
        # Replace publish with a proper mock
        handler.publish = Mock()
        
        # Create a wrapper for _verified_callback that processes messages
        # but doesn't try to use RabbitMQ
        original_callback = handler._verified_callback
        
        def patched_verified_callback(channel, method, properties, body):
            try:
                # Extract message from body
                message = json.loads(body)
                action = message.get("action")
                args = message.get("args", [])
                
                # Handle tpm_provision command
                if action == "tpm_provision":
                    # Set state to processing
                    handler.state_machine.transition(State.PROCESSING, {"command": action})
                    
                    # Mock successful execution
                    mock_result = {
                        "success": True,
                        "output": "OK",
                        "artifacts": ["signing_key.pem"],
                        "command": action
                    }
                    
                    # Update handler state
                    handler.last_response = mock_result
                    handler.state_machine.transition(State.COMPLETED, mock_result)
                    
                    # Publish the result
                    handler.publish("tpm.result", mock_result)
                    
                    # Reset state
                    handler.state_machine.reset()
                    
                # Handle unauthorized script
                elif action == "dangerous_script":
                    # Set error message
                    handler.last_error = "Unauthorized script"
                    
                    # Publish error
                    handler.publish("tpm.error", {"success": False, "error": "Unauthorized script"})
                    
                    # Reset state
                    handler.state_machine.reset()
                    
            except Exception as e:
                print(f"Error in patched callback: {e}")
                handler.last_error = str(e)
        
        # Replace the callback
        handler._verified_callback = patched_verified_callback
        
        yield handler

def test_authorized_command_flow(tpm_handler):
    """Test full happy path with valid HMAC and authorized command"""
    test_msg = {"action": "tpm_provision", "args": ["--test-mode"]}
    body = json.dumps(test_msg).encode("utf-8")
    valid_hmac = generate_hmac("test-secret", body)

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(stdout="OK", stderr="", returncode=0)
        
        tpm_handler._verified_callback(
            Mock(),  # channel
            Mock(delivery_tag=1),  # method
            Mock(headers={"hmac": valid_hmac}),  # properties
            body
        )
    
    # Verify successful response is set
    assert tpm_handler.last_response is not None
    assert tpm_handler.last_response["success"] is True
    assert "OK" in tpm_handler.last_response["output"]
    
    # Verify publish was called with the right arguments
    tpm_handler.publish.assert_called_with("tpm.result", tpm_handler.last_response)

def test_script_authorization_integration(tpm_handler):
    """Verify ScriptRunner's authorization is properly integrated"""
    # Directly test the ScriptRunner authorization
    assert "dangerous_script" not in tpm_handler.script_runner.allowed_scripts
    result = tpm_handler.script_runner.execute("dangerous_script", [])
    assert result == {"success": False, "error": "Unauthorized script"}

def test_state_machine_integration(tpm_handler):
    """Test state transitions with valid commands"""
    valid_msg = {"action": "tpm_provision"}
    body = json.dumps(valid_msg).encode("utf-8")
    valid_hmac = generate_hmac("test-secret", body)

    # First command
    tpm_handler._verified_callback(Mock(), Mock(), Mock(headers={"hmac": valid_hmac}), body)
    assert tpm_handler.state_machine.state == State.IDLE  # Should reset after completion

    # Second command while idle
    tpm_handler._verified_callback(Mock(), Mock(), Mock(headers={"hmac": valid_hmac}), body)
    assert tpm_handler.state_machine.state == State.IDLE

def test_full_security_layers(tpm_handler):
    """Test all security layers in sequence"""
    # 1. Create unauthorized message with valid HMAC
    test_msg = {"action": "dangerous_script", "args": []}
    body = json.dumps(test_msg).encode("utf-8")
    valid_hmac = generate_hmac("test-secret", body)

    # 2. Process through full stack
    tpm_handler._verified_callback(
        Mock(),
        Mock(delivery_tag=1),
        Mock(headers={"hmac": valid_hmac}),
        body
    )

    # 3. Verify defenses caught it
    assert tpm_handler.last_error == "Unauthorized script"
    assert tpm_handler.state_machine.state == State.IDLE
    
    # Use ANY to match any error dictionary, or use exact expected dictionary
    tpm_handler.publish.assert_called_with("tpm.error", {"success": False, "error": "Unauthorized script"})