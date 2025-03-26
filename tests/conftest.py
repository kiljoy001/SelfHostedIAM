# tests/conftest.py (additions for async support)
import pytest
import asyncio

@pytest.fixture
async def async_tpm_service():
    """Async fixture for TPM service testing"""
    from tpm import create_tpm_service
    
    # Create a service with test config
    service = create_tpm_service({
        'rabbitmq_host': 'localhost',
        'script_paths': {
            "tpm_provision": "/tests/mock_scripts/tpm_provisioning.sh",
            "generate_cert": "/tests/mock_scripts/tpm_self_signed_cert.sh",
            "get_random": "/tests/mock_scripts/tpm_random_number.sh"
        }
    })
    
    # Initialize but don't start consuming messages
    yield service
    
    # Clean up
    await service.stop_async()

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()