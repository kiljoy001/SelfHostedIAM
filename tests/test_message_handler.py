# tests/test_message_handler.py
import pytest
from your_module import TPMMessageHandler, ScriptRunner, BaseStateMachine

@pytest.fixture
def tpm_handler():
    scripts = {
        "tpm_provision": Path("tests/mock_scripts/provision.sh"),
        "generate_cert": Path("tests/mock_scripts/generate_cert.sh")
    }
    
    handler = TPMMessageHandler(
        script_runner=ScriptRunner(scripts),
        state_machine=BaseStateMachine(),
        host="rabbitmq"
    )
    
    # Verify TPM connection during setup
    try:
        from tpm2_pytss import TCTI
        TCTI(device="tcp://swtpm:2321")
    except Exception as e:
        pytest.skip(f"TPM emulator not available: {str(e)}")
    
    return handler

def test_provision_flow(tpm_handler):
    result = tpm_handler.handle_tpm_command({
        "action": "tpm_provision",
        "args": ["--test-mode"]
    })
    
    assert result["success"] is True
    assert Path("signing_key.pem").exists()