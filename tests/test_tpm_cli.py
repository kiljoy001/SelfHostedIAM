# tests/test_tpm_cli.py
import subprocess

def test_tpm2_tools_installed():
    """Verify TPM2 tools are available"""
    result = subprocess.run(
        ["tpm2_getrandom", "--hex", "4"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert len(result.stdout.strip()) == 8  # 4 bytes in hex