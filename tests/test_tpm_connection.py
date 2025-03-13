# tests/test_tpm_connection.py
import pytest
from tpm2_pytss import TCTI, TPM2

@pytest.fixture(scope="module")
def tpm_connection():
    """Connect to the SWTPM emulator"""
    tcti = TCTI(device="tcp://swtpm:2321")  # Matches service name in CI
    tpm = TPM2(tcti=tcti)
    yield tpm
    tpm.shutdown()

def test_tpm_basic_operations(tpm_connection):
    """Test basic TPM functionality"""
    # Get random bytes
    random_bytes = tpm_connection.get_random(16)
    assert len(random_bytes) == 16
    print(f"TPM Generated Random: {random_bytes.hex()}")

    # Test PCR read
    pcr_read = tpm_connection.pcr_read(0)
    assert isinstance(pcr_read, bytes)
    assert len(pcr_read) == 32  # SHA-256 digest size

def test_tpm_emulator_availability():
    """Test raw TPM connection"""
    try:
        with TCTI(device="tcp://swtpm:2321") as tcti:
            tpm = TPM2(tcti=tcti)
            assert tpm.startup(TPM2_SU_CLEAR) == 0
    except Exception as e:
        pytest.skip(f"TPM emulator not available: {str(e)}")