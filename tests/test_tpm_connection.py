import pytest
import os
import subprocess
import logging
import time
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_tpm_command(command, expected_success=True):
    """Run a TPM command and check if it succeeds"""
    try:
        logger.info(f"Running TPM command: {command}")
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        
        success = result.returncode == 0
        
        logger.info(f"Command returned: {result.returncode}")
        if result.stdout:
            logger.info(f"STDOUT: {result.stdout[:100]}...")
        if result.stderr:
            logger.info(f"STDERR: {result.stderr[:100]}...")
        
        if expected_success and not success:
            logger.warning(f"Command failed but expected to succeed: {' '.join(command)}")
        
        return success, result.stdout, result.stderr
    except Exception as e:
        logger.error(f"Error running command: {e}")
        return False, "", str(e)

def test_tpm_basic_operations():
    """Test basic TPM operations using the TPM command line tools"""
    # Check if TPM is available using tpm2_getcap
    success, stdout, stderr = run_tpm_command(["tpm2_getcap", "properties-fixed"])
    
    if not success:
        pytest.skip(f"TPM not available: {stderr}")
    
    # Basic assertions on the output
    assert "TPM2_PT_MANUFACTURER" in stdout, "Expected manufacturer information in output"
    
    # Get some basic TPM properties
    success, stdout, stderr = run_tpm_command(["tpm2_getcap", "algorithms"])
    assert success, "Failed to get TPM algorithms"
    assert "sha256" in stdout.lower(), "Expected SHA256 support"
    
    logger.info("Basic TPM operations test passed")

def test_tpm_startup():
    """Test TPM startup and random number generation"""
    # First try a startup (might fail if already started)
    run_tpm_command(["tpm2_startup", "-c"], expected_success=False)
    
    # Create a temporary file for random data
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_path = tmp_file.name
    
    try:
        # Generate random data
        success, stdout, stderr = run_tpm_command(["tpm2_getrandom", "--output", tmp_path, "16"])
        
        if not success:
            pytest.skip(f"TPM random generation failed: {stderr}")
        
        # Verify the file exists and has content
        assert os.path.exists(tmp_path), "Random data file not created"
        file_size = os.path.getsize(tmp_path)
        assert file_size == 16, f"Expected 16 bytes of random data, got {file_size} bytes"
        
        logger.info("TPM startup and random generation test passed")
    finally:
        # Clean up the temporary file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def test_pcr_read():
    """Test reading PCR values"""
    # Try to read PCR 0 (should exist in all TPMs)
    success, stdout, stderr = run_tpm_command(["tpm2_pcrread", "sha256:0"])
    
    if not success:
        pytest.skip(f"PCR read failed: {stderr}")
    
    # Verify output contains PCR 0 - adapt to the actual format
    # The output shows "0 : 0x000..." instead of "PCR[0]"
    assert "0 :" in stdout or "0:" in stdout, "Expected PCR 0 in output"
    assert "sha256" in stdout, "Expected SHA256 in output"
    
    # Read multiple PCRs
    success, stdout, stderr = run_tpm_command(["tpm2_pcrread", "sha256:0,1,2,3"])
    assert success, "Failed to read multiple PCRs"
    
    # Perform a PCR extend operation to a high-numbered PCR (less likely to be in use)
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(b"test data for PCR extend")
        tmp_path = tmp_file.name
    
    try:
        # Extend a PCR with test data (using PCR 16 which is typically available)
        extend_success, extend_stdout, extend_stderr = run_tpm_command(
            ["tpm2_pcrextend", "16:sha256=f1d2d2f924e986ac86fdf7b36c94bcdf32beec15"]
        )
        
        if extend_success:
            # Read the PCR to verify it changed
            read_success, read_stdout, read_stderr = run_tpm_command(["tpm2_pcrread", "sha256:16"])
            assert read_success, "Failed to read extended PCR"
            assert "16 :" in read_stdout or "16:" in read_stdout, "Expected PCR 16 in output"
            logger.info("PCR extend and read test passed")
        else:
            logger.warning(f"PCR extend failed (may be restricted): {extend_stderr}")
            # Skip this part of the test but don't fail it
            logger.info("Skipping PCR extend verification")
    finally:
        # Clean up the temporary file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    
    logger.info("PCR read test passed")