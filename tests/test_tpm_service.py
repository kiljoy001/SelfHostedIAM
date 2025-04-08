import pytest
import os
import json
import logging
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path

# Import the TPM service
from tpm.module.tpm_service import TPMService
from helper.finite_state_machine import State, BaseStateMachine
from helper.base_service import BaseService

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

    @pytest.mark.asyncio
    @patch('tpm.module.tpm_service.ScriptRunner')
    @patch('tpm.module.tpm_service.BaseStateMachine')
    @patch('tpm.module.tpm_service.TPMMessageHandler')
    async def test_initialization(self, mock_handler_class, mock_state_class, mock_runner_class, 
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
        
        # Now we need to initialize the async service explicitly
        await service.initialize()
        
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

    @pytest.mark.asyncio
    async def test_start_stop(self, mock_message_handler):
        """Test starting and stopping the service"""
        # Create a service with mocked components
        service = TPMService({})
        
        # Mock the state machine and _run_in_executor methods
        service.state_machine = Mock()
        service._run_in_executor = AsyncMock(side_effect=lambda f: f())
        service.emit_event = AsyncMock()
        
        # Set up the message handler mock
        service.message_handler = mock_message_handler
        
        # Test starting
        result = await service.start()
        assert result is True, "Service should start successfully"
        assert service.active is True, "Service should be marked active"
        mock_message_handler.start_consuming.assert_called_once_with(non_blocking=True)
        
        # Test starting when already active
        mock_message_handler.start_consuming.reset_mock()
        service.active = True
        result = await service.start()
        assert result is True, "Starting an active service should return True"
        mock_message_handler.start_consuming.assert_not_called()
        
        # Test stopping
        result = await service.stop()
        assert result is True, "Service should stop successfully"
        assert service.active is False, "Service should be marked inactive"
        service._run_in_executor.assert_called()
        
        # Test stopping when already inactive
        service._run_in_executor.reset_mock()
        service.active = False
        result = await service.stop()
        assert result is True, "Stopping an inactive service should return True"
        service._run_in_executor.assert_not_called()
        
        # Test failure handling
        service._run_in_executor = AsyncMock(side_effect=Exception("Test exception"))
        service.active = True
        result = await service.stop()
        assert result is True, "Should handle exceptions during stop"
        assert service.active is False, "Service should be marked inactive even after exceptions"

    @pytest.mark.asyncio
    async def test_execute_command(self, mock_script_runner):
        """Test executing commands directly"""
        # Create a service with mocked components
        service = TPMService({})
        service.script_runner = mock_script_runner
        service.state_machine = Mock()
        service.emit_event = AsyncMock()
        
        # Test the synchronous version
        result = service.execute_command("tpm_provision", ["--test-mode"])
        
        # Verify results
        mock_script_runner.execute.assert_called_once_with("tpm_provision", ["--test-mode"])
        assert result["success"] is True, "Command should execute successfully"
        assert result["command"] == "tpm_provision", "Command name should be included"
        
        # Test the async version
        mock_script_runner.execute.reset_mock()
        service._run_in_executor = AsyncMock(return_value={"success": True, "async": True})
        
        result = await service.execute_command_async("tpm_provision", ["--test-mode"])
        
        # Verify results
        assert result["success"] is True, "Async command should execute successfully"
        assert result["async"] is True, "Should return result from executor"
        service.emit_event.assert_awaited()
        
        # Test error handling
        service.script_runner = None
        with pytest.raises(RuntimeError):
            service.execute_command("tpm_provision")

    @pytest.mark.asyncio
    async def test_send_command(self, mock_message_handler):
        """Test sending commands through message queue"""
        # Create a service with mocked components
        service = TPMService({})
        service.message_handler = mock_message_handler
        service.state_machine = Mock()
        service.emit_event = AsyncMock()
        service._run_in_executor = AsyncMock(return_value="mock-message-id")
        
        # Test sending a command synchronously
        message_id = service.send_command("tpm_provision", ["--test-mode"])
        
        # Verify results
        mock_message_handler.publish_command.assert_called_once_with("tpm_provision", ["--test-mode"])
        assert message_id == "mock-message-id", "Should return message ID from handler"
        
        # Test sending a command asynchronously
        mock_message_handler.publish_command.reset_mock()
        
        message_id = await service.send_command_async("tpm_provision", ["--test-mode"])
        
        assert message_id == "mock-message-id", "Should return message ID from handler"
        service.emit_event.assert_awaited()
        
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

    def test_is_active(self):
        """Test checking if service is active"""
        service = TPMService({})
        service.active = True
        
        assert service.is_active() is True, "Should return active status"
        
        service.active = False
        assert service.is_active() is False, "Should return inactive status"

    @pytest.mark.asyncio
    async def test_event_listeners(self):
        """Test adding and triggering event listeners"""
        service = TPMService({})
        
        # Create mock listeners
        mock_sync_listener = Mock()
        mock_async_listener = AsyncMock()
        
        # Add listeners
        service.add_event_listener("test_event", mock_sync_listener)
        service.add_event_listener("test_event", mock_async_listener)
        
        # Use a loop for the _run_in_executor method
        loop = asyncio.get_event_loop()
        service._run_in_executor = AsyncMock(
            side_effect=lambda func: loop.run_in_executor(None, func)
        )
        
        # Emit event
        count = await service.emit_event("test_event", "arg1", key="value")
        
        # Verify results
        assert count == 2, "Should notify both listeners"
        mock_sync_listener.assert_called_once_with("arg1", key="value")
        mock_async_listener.assert_awaited_once_with("arg1", key="value")
        
        # Test emitting to nonexistent event
        count = await service.emit_event("nonexistent")
        assert count == 0, "Should handle nonexistent events"
        
        # Test error in listener
        mock_sync_listener.side_effect = Exception("Test exception")
        count = await service.emit_event("test_event")
        assert count == 1, "Should only count successful notifications"