import pytest
import os
import json
import logging
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Import the TPM service
from tpm.module.tpm_service import TPMService
from helper.finite_state_machine import State

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestTPMService:
    """Test suite for the TPM Service"""

    @pytest.fixture
    def mock_script_runner(self):
        """Fixture for a mocked script runner"""
        mock_runner = Mock()
        mock_runner.execute = Mock(return_value={
            "success": True,
            "output": "Mock command executed",
            "command": "tpm_provision",
            "args": ["--test-mode"]
        })
        return mock_runner

    @pytest.fixture
    def mock_state_machine(self):
        """Fixture for a mocked state machine"""
        mock_state = Mock()
        mock_state.state = State.IDLE
        mock_state.transition = Mock(return_value=True)
        mock_state.reset = Mock()
        return mock_state

    @pytest.fixture
    def mock_message_handler(self):
        """Fixture for a mocked message handler"""
        mock_handler = Mock()
        mock_handler.channel = Mock()
        mock_handler.publish = Mock(return_value=True)
        mock_handler.publish_command = Mock(return_value="mock-message-id")
        mock_handler.start_consuming = Mock(return_value=True)
        mock_handler.stop_consuming = Mock(return_value=True)
        return mock_handler

    @patch('tpm.module.tpm_service.ScriptRunner')
    @patch('tpm.module.tpm_service.BaseStateMachine')
    @patch('tpm.module.tpm_service.TPMMessageHandler')
    def test_initialization(self, mock_handler_class, mock_state_class, mock_runner_class, 
                           mock_script_runner, mock_state_machine, mock_message_handler):
        """Test TPM service initialization"""
        # Setup mocks
        mock_runner_class.return_value = mock_script_runner
        mock_state_class.return_value = mock_state_machine
        mock_handler_class.return_value = mock_message_handler
        
        # Configure test paths
        test_script_dir = "/tmp/test_scripts"
        os.makedirs(test_script_dir, exist_ok=True)
        
        # Create config
        config = {
            'rabbitmq_host': 'test-host',
            'secret_key': 'test-secret',
            'exchange': 'test-exchange',
            'script_dir': test_script_dir
        }
        
        # Initialize the service
        service = TPMService(config)
        
        # Verify initialization
        assert service.config == config, "Config should be stored"
        assert service.state_machine == mock_state_machine, "State machine should be initialized"
        assert service.script_runner == mock_script_runner, "Script runner should be initialized"
        assert service.message_handler == mock_message_handler, "Message handler should be initialized"
        assert service.active is False, "Service should start inactive"
        
        # Verify TPMMessageHandler initialization
        mock_handler_class.assert_called_once()
        handler_kwargs = mock_handler_class.call_args[1]
        assert handler_kwargs['script_runner'] == mock_script_runner
        assert handler_kwargs['state_machine'] == mock_state_machine
        assert handler_kwargs['host'] == 'test-host'
        assert handler_kwargs['secret_key'] == 'test-secret'
        assert handler_kwargs['exchange'] == 'test-exchange'

    def test_start_stop(self, mock_message_handler):
        """Test starting and stopping the service"""
        # Create a service with mocked components
        service = TPMService({})
        service.message_handler = mock_message_handler
        
        # Test starting
        result = service.start()
        assert result is True, "Service should start successfully"
        assert service.active is True, "Service should be marked active"
        mock_message_handler.start_consuming.assert_called_once_with(non_blocking=True)
        
        # Test starting when already active
        mock_message_handler.start_consuming.reset_mock()
        result = service.start()
        assert result is True, "Starting an active service should return True"
        mock_message_handler.start_consuming.assert_not_called()
        
        # Test stopping
        result = service.stop()
        assert result is True, "Service should stop successfully"
        assert service.active is False, "Service should be marked inactive"
        mock_message_handler.stop_consuming.assert_called_once()
        
        # Test stopping when already inactive
        mock_message_handler.stop_consuming.reset_mock()
        service.active = False
        result = service.stop()
        assert result is True, "Stopping an inactive service should return True"
        mock_message_handler.stop_consuming.assert_not_called()
        
        # Test failure handling
        mock_message_handler.stop_consuming.side_effect = Exception("Test exception")
        service.active = True
        result = service.stop()
        assert result is False, "Should handle exceptions during stop"

    def test_execute_command(self, mock_script_runner):
        """Test executing commands directly"""
        # Create a service with mocked components
        service = TPMService({})
        service.script_runner = mock_script_runner
        
        # Test executing a command
        result = service.execute_command("tpm_provision", ["--test-mode"])
        
        # Verify results
        mock_script_runner.execute.assert_called_once_with("tpm_provision", ["--test-mode"])
        assert result["success"] is True, "Command should execute successfully"
        assert result["command"] == "tpm_provision", "Command name should be included"
        
        # Test error handling
        service.script_runner = None
        with pytest.raises(RuntimeError):
            service.execute_command("tpm_provision")

    def test_send_command(self, mock_message_handler):
        """Test sending commands through message queue"""
        # Create a service with mocked components
        service = TPMService({})
        service.message_handler = mock_message_handler
        
        # Test sending a command
        message_id = service.send_command("tpm_provision", ["--test-mode"])
        
        # Verify results
        mock_message_handler.publish_command.assert_called_once_with("tpm_provision", ["--test-mode"])
        assert message_id == "mock-message-id", "Should return message ID from handler"
        
        # Test error handling
        service.message_handler = None
        with pytest.raises(RuntimeError):
            service.send_command("tpm_provision")

    def test_get_handler(self, mock_message_handler):
        """Test getting the message handler"""
        service = TPMService({})
        service.message_handler = mock_message_handler
        
        handler = service.get_handler()
        assert handler == mock_message_handler, "Should return the message handler"

    def test_get_state(self, mock_state_machine):
        """Test getting the current state"""
        service = TPMService({})
        service.state_machine = mock_state_machine
        mock_state_machine.state = State.IDLE
        
        state = service.get_state()
        assert state == State.IDLE, "Should return the current state"
        
        # Test with no state machine
        service.state_machine = None
        state = service.get_state()
        assert state is None, "Should return None if no state machine"

    def test_is_active(self):
        """Test checking if service is active"""
        service = TPMService({})
        service.active = True
        
        assert service.is_active() is True, "Should return active status"
        
        service.active = False
        assert service.is_active() is False, "Should return inactive status"

    def test_event_listeners(self):
        """Test adding and triggering event listeners"""
        service = TPMService({})
        
        # Create mock listeners
        mock_listener1 = Mock()
        mock_listener2 = Mock()
        
        # Add listeners
        service.add_event_listener("test_event", mock_listener1)
        service.add_event_listener("test_event", mock_listener2)
        
        # Emit event
        count = service.emit_event("test_event", "arg1", key="value")
        
        # Verify results
        assert count == 2, "Should notify both listeners"
        mock_listener1.assert_called_once_with("arg1", key="value")
        mock_listener2.assert_called_once_with("arg1", key="value")
        
        # Test emitting to nonexistent event
        count = service.emit_event("nonexistent")
        assert count == 0, "Should handle nonexistent events"
        
        # Test error in listener
        mock_listener1.side_effect = Exception("Test exception")
        count = service.emit_event("test_event")
        assert count == 1, "Should only count successful notifications"

    @pytest.mark.asyncio
    async def test_async_methods(self, mock_message_handler, mock_script_runner):
        """Test async methods of the service"""
        service = TPMService({})
        service.message_handler = mock_message_handler
        service.script_runner = mock_script_runner
        
        # Test async start
        result = await service.start_async()
        assert result is True, "Async start should succeed"
        assert service.active is True, "Service should be marked active"
        
        # Test async stop
        result = await service.stop_async()
        assert result is True, "Async stop should succeed"
        assert service.active is False, "Service should be marked inactive"
        
        # Test async command execution
        mock_script_runner.execute.return_value = {"success": True, "async": True}
        result = await service.execute_command_async("tpm_provision", ["--test-mode"])
        assert result["success"] is True, "Async command should execute successfully"
        assert result["async"] is True, "Should return result from script runner"
        
        # Test async command sending
        message_id = await service.send_command_async("tpm_provision", ["--test-mode"])
        assert message_id == "mock-message-id", "Should return message ID from handler"