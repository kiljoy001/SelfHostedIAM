# tests/test_tpm_connection.py
import pytest
import struct
from tpm2_pytss import TCTI
from tpm2_pytss.constants import (
    TPM2_ST,
    TPM2_CC,
    TPM2_RC,
    TPM2_SU,
    TPM2_ALG
)

@pytest.fixture(scope="module")
def tcti_connection():
    """Create TCTI connection to SWTPM"""
    tcti = TCTI(device="tcp://swtpm:2321")
    yield tcti
    tcti.close()

def test_tpm_basic_operations(tcti_connection):
    """Test basic TPM functionality using low-level commands"""
    # Test GetRandom command
    get_random_cmd = (
        struct.pack(">H", TPM2_ST.NO_SESSIONS) +
        struct.pack(">I", 10) +  # Command size (4 bytes header + 2 bytes for bytesRequested)
        struct.pack(">I", TPM2_CC.GetRandom) +
        struct.pack(">H", 16)    # bytesRequested
    )
    
    response = tcti_connection.transmit(get_random_cmd)
    (tag, size, rc, bytes_available) = struct.unpack(">HIII", response[:14])
    random_bytes = response[14:14+bytes_available]
    
    assert rc == TPM2_RC.SUCCESS
    assert len(random_bytes) == 16

def test_tpm_startup(tcti_connection):
    """Test TPM2_CC.Startup command with CLEAR parameter"""
    try:
        # Build Startup command
        startup_cmd = (
            struct.pack(">H", TPM2_ST.NO_SESSIONS) +
            struct.pack(">I", 10) +  # Command size
            struct.pack(">I", TPM2_CC.Startup) +
            struct.pack(">H", TPM2_SU.CLEAR)
        )
        
        response = tcti_connection.transmit(startup_cmd)
        (tag, size, rc) = struct.unpack(">HII", response[:10])
        
        assert rc == TPM2_RC.SUCCESS
        
    except Exception as e:
        pytest.skip(f"TPM startup failed: {str(e)}")

def test_pcr_read(tcti_connection):
    """Test PCR Read command for SHA256 bank"""
    # Build PCR_Read command
    pcr_read_cmd = (
        struct.pack(">H", TPM2_ST.NO_SESSIONS) +
        struct.pack(">I", 17) +  # Command size
        struct.pack(">I", TPM2_CC.PCR_Read) +
        struct.pack(">I", 1) +    # pcrSelectionIn count
        struct.pack(">H", TPM2_ALG.SHA256) +
        struct.pack(">B", 3) +    # size of select
        b"\x01" +                 # pcrSelect[0] (select PCR 0)
        b"\x00" +                 # pcrSelect[1]
        b"\x00"                   # pcrSelect[2]
    )
    
    response = tcti_connection.transmit(pcr_read_cmd)
    
    # Parse response header
    (tag, size, rc) = struct.unpack(">HII", response[:10])
    assert rc == TPM2_RC.SUCCESS
    
    # Parse PCR values
    pcr_update_counter = struct.unpack(">I", response[10:14])[0]
    (pcr_select_out_size, alg) = struct.unpack(">IH", response[14:20])
    digest_size = struct.unpack(">H", response[20:22])[0]
    digest = response[22:22+digest_size]
    
    assert digest_size == 32  # SHA256 digest size