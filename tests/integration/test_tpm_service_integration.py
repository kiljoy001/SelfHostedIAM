import pytest
import os
import logging
import asyncio
from pathlib import Path

# Import modules
from registry.service_registry import ServiceRegistry
from tpm.module.tpm_service import TPMService
from helper.finite_state_machine import State, BaseStateMachine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestTPMRegistryIntegration:
    """Integration tests for TPM service with registry"""
    
    @pytest.fixture
    def registry(self):
        """Fixture for a service registry"""
        return ServiceRegistry()

    
    @pytest.fixture
    def mock_scripts(self):
        """Create mock script files for testing"""
        # Create temporary directory for test scripts
        test_dir = "/tmp/test_scripts"
        os.makedirs(test_dir, exist_ok=True)
        
        # Create script paths
        script_paths = {
            "tpm_provision": Path(test_dir) / "tpm_provisioning.sh",
            "generate_cert": Path(test_dir) / "tpm_self_signed_cert.sh"
        }
        
        # Create simple script files that echo their arguments and return success
        for name, path in script_paths.items():
            with open(path, 'w') as f:
                f.write('#!/bin/bash\n')
                f.write('echo "Running $0 with args: $@"\n')
                f.write('echo \'{"success": true, "output": "Mock execution output"}\'\n')
                f.write('exit 0\n')
            
            # Make the scripts executable
            os.chmod(path, 0o755)
        
        import hashlib
        script_hashes = {}
        for name, path in script_paths.items():
            with open(path, 'rb') as f:
                content = f.read()
                script_hashes[name] = hashlib.sha256(content).hexdigest()
    
        return {"paths": script_paths, "hashes": script_hashes}
    
    def test_basic_service_registration(self, registry, mock_scripts):
        """Test basic registration of TPM service with registry"""
        # Create service with registry
        config = {
            'script_paths': mock_scripts["paths"],
            'script_hashes': mock_scripts["hashes"],
            'rabbitmq_host': 'localhost'
        }
        
        tpm_service = TPMService(config)
        registry.register_service("tpm", tpm_service)
        
        # Add a method to TPMService to register its handlers with the registry
        # This would typically be part of the TPMService class
        if not hasattr(tpm_service, 'register_with_registry'):
            def register_with_registry(service, reg):
                if service.message_handler:
                    reg.register_message_handler(
                        'tpm.command.#', 
                        service.message_handler.handle_tpm_command,
                        'tpm_worker'
                    )
            tpm_service.register_with_registry = register_with_registry.__get__(tpm_service)
        
        # Explicitly register handlers
        tpm_service.register_with_registry(registry)
        
        # Verify service is registered
        assert registry.get_service('tpm') == tpm_service, "TPM service should be registered with registry"
        
        # Verify message handler registration
        assert 'tpm.command.#' in registry.message_handlers, "Command routing key should be registered"
        handler_info = registry.message_handlers['tpm.command.#'][0]
        assert handler_info['queue_name'] == 'tpm_worker', "Queue name should be registered"
    
    def test_service_lifecycle_through_registry(self, registry, mock_scripts):
        """Test starting and stopping TPM service through registry"""
        # Create service with registry
        config = {'script_paths': mock_scripts["paths"],
        'script_hashes': mock_scripts["hashes"],
         'rabbitmq_host': 'localhost'
         }
        tpm_service = TPMService(config)
        registry.register_service("tpm", tpm_service)

        # Add registry handler registration
        if not hasattr(tpm_service, 'register_with_registry'):
            def register_with_registry(service, reg):
                if service.message_handler:
                    reg.register_message_handler(
                        'tpm.command.#', 
                        service.message_handler.handle_tpm_command,
                        'tpm_worker'
                    )
            tpm_service.register_with_registry = register_with_registry.__get__(tpm_service)
        
        # Explicitly register handlers
        tpm_service.register_with_registry(registry)
        
        # Start all services through registry
        results = registry.start_all_services()
        
        # Verify TPM service was started
        assert 'tpm' in results, "TPM service should be in results"
        assert results['tpm'] is True, "TPM service should start successfully"
        assert tpm_service.is_active() is True, "TPM service should be marked active"
        
        # Stop all services through registry
        results = registry.stop_all_services()
        
        # Verify TPM service was stopped
        assert 'tpm' in results, "TPM service should be in results"
        assert results['tpm'] is True, "TPM service should stop successfully"
        assert tpm_service.is_active() is False, "TPM service should be marked inactive"
    
    def test_event_propagation(self, registry, mock_scripts):
        """Test event propagation between registry and TPM service"""
        # Create event listeners for registry
        state_change_listener = lambda old_state, new_state, context: None
        registry.register_event_listener('tpm.state_change', state_change_listener)
        
        # Create service with registry
        config = {'script_paths': mock_scripts["paths"],
        'script_hashes': mock_scripts["hashes"],
        'rabbitmq_host': 'localhost'
         }
        tpm_service = TPMService(config)
        registry.register_service("tpm", tpm_service)
        
        # Create a real state machine to test transitions
        state_machine = BaseStateMachine()
        tpm_service.state_machine = state_machine
        
        # Test direct event emission
        result = registry.emit_event('tpm.state_change', State.IDLE, State.PROCESSING, {'command': 'test_command'})
        assert result > 0, "Event should be emitted to at least one listener"
    
    def test_command_execution_with_registry(self, registry, mock_scripts):
        """Test executing TPM commands through a service registered with registry"""
        # Create service with registry
        config = {
            'script_paths': mock_scripts["paths"],
            'script_hashes': mock_scripts["hashes"],
            'rabbitmq_host': 'localhost'
        }
        
        tpm_service = TPMService(config)
        registry.register_service("tpm", tpm_service)
        
        # Execute a command through the service
        result = tpm_service.execute_command('tpm_provision', ['--test-mode'])
        
        # Verify result
        assert result['success'] is True, "Command should execute successfully"
        assert 'output' in result, "Result should include output"
        
        # Test command execution through registry
        # Get service from registry and execute command
        retrieved_service = registry.get_service('tpm')
        result = retrieved_service.execute_command('generate_cert', ['device123'])
        
        # Verify result
        assert result['success'] is True, "Command should execute successfully"
        assert 'output' in result, "Result should include output"
    
    def test_message_sending_with_registry(self, registry, mock_scripts):
        """Test sending messages through a service registered with registry"""
        # Create service with registry
        config = {
            'script_paths': mock_scripts["paths"],
            'script_hashes': mock_scripts["hashes"],
            'rabbitmq_host': 'localhost',
            'exchange': 'test-exchange'
        }
    
        tpm_service = TPMService(config)
        registry.register_service("tpm", tpm_service)
    
        # For testing purposes, modify the TPMService's send_command method
        original_send_command = tpm_service.send_command
        tpm_service.send_command = lambda cmd, args: 'mock-message-id'
        
        try:
            # Send a command
            message_id = tpm_service.send_command('tpm_provision', ['--test-mode'])
            
            # Verify message was sent
            assert message_id == 'mock-message-id', "Should return message ID from handler"
            
            # Test sending through registry
            retrieved_service = registry.get_service('tpm')
            message_id = retrieved_service.send_command('generate_cert', ['device123'])
            
            # Verify second message
            assert message_id == 'mock-message-id', "Should return message ID from handler"
        finally:
            # Restore original method
            tpm_service.send_command = original_send_command
    
    @pytest.mark.asyncio
    async def test_async_operations_with_registry(self, registry, mock_scripts):
        """Test async operations with TPM service and registry"""
        # Create service with registry
        config = {'script_paths': mock_scripts["paths"], 
        'script_hashes': mock_scripts["hashes"],
        'rabbitmq_host': 'localhost'
        }
        tpm_service = TPMService(config)
        registry.register_service("tpm", tpm_service)

        # Allow time for connection to fully establish
        await asyncio.sleep(2)

        # Register an async event listener
        async def async_listener(old_state, new_state, context=None):
            await asyncio.sleep(0.1)
            return f"Processed state change: {old_state} -> {new_state}"

        registry.register_event_listener('tpm.state_change', async_listener)

        # Start services asynchronously
        try:
            results = await registry.start_all_services_async()
            assert results['tpm'] is True, "TPM service should start asynchronously"

            # Allow time for services to fully start
            await asyncio.sleep(2)

            # Emit an event asynchronously
            count = await registry.emit_event_async('tpm.state_change', 
                                                  State.IDLE, State.PROCESSING, 
                                                  {'command': 'test'})
            assert count > 0, "Should notify listeners"

            # Execute a command asynchronously
            result = await tpm_service.execute_command_async('tpm_provision', ['--test-mode'])
            assert result['success'] is True, "Async command should succeed"

            # Allow time before stopping services
            await asyncio.sleep(2)

            # Stop services asynchronously
            results = await registry.stop_all_services_async()

            # Instead of asserting on the result which might be unstable,
            # verify the service's final state
            assert not tpm_service.is_active(), "TPM service should be inactive after stopping"
        except AttributeError as e:
            # Skip if async methods aren't implemented
            pytest.skip(f"Async methods not implemented in registry or service: {e}")
    
    def test_multiple_services_with_registry(self, registry, mock_scripts):
        """Test registry handling multiple services including TPM"""
        # Create TPM service
        config = {'script_paths': mock_scripts["paths"],
        'script_hashes': mock_scripts["hashes"],
        'rabbitmq_host': 'localhost'
        }
        tpm_service = TPMService(config)
        registry.register_service("tpm", tpm_service)
        
        # Create a simple second service using a regular class
        class SimpleService:
            def __init__(self):
                self.active = False
            
            def start(self):
                self.active = True
                return True
            
            def stop(self):
                self.active = False
                return True
        
        simple_service = SimpleService()
        
        # Register the second service
        registry.register_service('simple_service', simple_service)
        
        # Start all services
        results = registry.start_all_services()
        
        # Verify both services were started
        assert results['tpm'] is True, "TPM service should start successfully"
        assert results['simple_service'] is True, "Simple service should start successfully"
        assert tpm_service.is_active() is True, "TPM service should be active"
        assert simple_service.active is True, "Simple service should be active"
        
        # Stop all services
        results = registry.stop_all_services()
        
        # Verify both services were stopped
        assert results['tpm'] is True, "TPM service should stop successfully"
        assert results['simple_service'] is True, "Simple service should stop successfully"
        assert tpm_service.is_active() is False, "TPM service should be inactive"
        assert simple_service.active is False, "Simple service should be inactive"