import pytest
import asyncio
import os
import string
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple
from unittest.mock import patch, MagicMock, AsyncMock
from hypothesis import HealthCheck
from hypothesis import given, strategies as st, settings, assume
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant

from tpm.module.tpm_service import TPMService
from helper.finite_state_machine import BaseStateMachine
from helper.script_runner import ScriptRunner

# Disable logging during tests to reduce noise
logging.getLogger('tpm.module.tpm_service').setLevel(logging.ERROR)

@pytest.fixture(autouse=True)
def clean_mocks():
    """Clean up any lingering mocks before and after each test"""
    # Clean up before test
    patch.stopall()
    yield
    # Clean up after test
    patch.stopall()

# Define strategies for different test inputs
@st.composite
def service_configs(draw):
    """Strategy to generate valid TPMService configurations"""
    rabbitmq_host = draw(st.one_of(
        st.just('localhost'),
        st.sampled_from(['rabbitmq', '127.0.0.1', 'amqp.example.com'])
    ))
    
    secret_key = draw(st.text(
        alphabet=string.ascii_letters + string.digits + '_-.',
        min_size=8,
        max_size=64
    ))
    
    exchange = draw(st.text(
        alphabet=string.ascii_letters + string.digits + '_',
        min_size=1,
        max_size=32
    ))
    
    # Create a temporary directory for script testing
    script_dir = tempfile.mkdtemp()
    
    # Create some mock scripts for testing
    script_paths = {}
    for script_name in ['tpm_provision', 'generate_cert', 'get_random']:
        script_path = os.path.join(script_dir, f"{script_name}.sh")
        with open(script_path, 'w') as f:
            f.write("#!/bin/sh\necho 'Test script'\nexit 0")
        os.chmod(script_path, 0o755)
        script_paths[script_name] = script_path
    
    # Generate config
    config = {
        'rabbitmq_host': 'localhost',
        'secret_key': secret_key,
        'exchange': exchange,
        'script_dir': script_dir,
        'script_paths': script_paths,
        'script_hashes': {
            name: "dummy_hash_for_testing" for name in script_paths.keys()
        }
    }
    
    return config, script_dir

@st.composite
def tpm_commands(draw):
    """Strategy to generate valid TPM commands"""
    command = draw(st.sampled_from([
        'tpm_provision',
        'generate_cert',
        'get_random'
    ]))
    
    args = draw(st.lists(
        st.text(
            alphabet=string.ascii_letters + string.digits + '_-.',
            min_size=0,
            max_size=20
        ),
        min_size=0,
        max_size=5
    ))
    
    return command, args

# Test TPMService initialization with various configurations
@given(config_and_dir=service_configs())
@settings(max_examples=10)
def test_tpm_service_initialization(config_and_dir):
    """Test TPMService initialization with different configurations"""
    config, script_dir = config_and_dir
    
    try:
        # Initialize service
        service = TPMService(config)
        
        # Check that essential components are initialized
        assert service.script_runner is not None, "Script runner should be initialized"
        assert service.state_machine is not None, "State machine should be initialized"
        assert service.message_handler is not None, "Message handler should be initialized"
        assert service.active is False, "Service should not be active initially"
        
        # Verify config was properly processed
        assert service.config is not None, "Config should be set"
        assert service.config.get('rabbitmq_host') == config['rabbitmq_host'], "RabbitMQ host should match config"
    finally:
        # Clean up temporary directory
        import shutil
        if os.path.exists(script_dir):
            shutil.rmtree(script_dir)

# Test TPMService start/stop
@given(config_and_dir=service_configs())
@settings(max_examples=5, deadline=None)  # Remove deadline to avoid timing issues
def test_tpm_service_lifecycle(config_and_dir):
    """Test TPMService start and stop operations"""
    config, script_dir = config_and_dir
    
    try:
        # Clear any existing patches
        patch.stopall()
        
        # Create mock before importing/initializing TPMService
        with patch('tpm.tpm_message_handler.TPMMessageHandler') as mock_handler_cls:
            # Configure the mock handler
            mock_handler = MagicMock()
            mock_handler.channel = MagicMock()
            mock_handler.start_consuming.return_value = True
            mock_handler.stop_consuming.return_value = True
            mock_handler_cls.return_value = mock_handler
            
            # Now create the service
            service = TPMService(config)
            
            # Manually replace the service's message handler with our mock
            # This is crucial - the service creates its own instance during initialization
            service.message_handler = mock_handler
            
            # Test starting the service
            result = service.start()
            assert result is True, "Service should start successfully"
            assert service.active is True, "Service should be active after starting"
            mock_handler.start_consuming.assert_called_once_with(non_blocking=True)
            
            # Test stopping the service
            result = service.stop()
            assert result is True, "Service should stop successfully"
            assert service.active is False, "Service should be inactive after stopping"
            mock_handler.stop_consuming.assert_called_once()
    finally:
        # Clean up temporary directory
        import shutil
        if os.path.exists(script_dir):
            shutil.rmtree(script_dir)
        # Make sure all patches are stopped
        patch.stopall()

# Test TPMService command execution with mocked script runner
def test_tpm_service_execute_command():
    """Test TPMService direct command execution"""
    # Create a simple hard-coded config
    config = {
        'rabbitmq_host': 'localhost',
        'secret_key': 'test_secret',
        'exchange': 'test_exchange',
        'script_dir': '/tmp',
        'script_paths': {
            'tpm_provision': '/tmp/tpm_provision.sh',
            'generate_cert': '/tmp/generate_cert.sh',
            'get_random': '/tmp/get_random.sh'
        },
        'script_hashes': {
            'tpm_provision': 'dummy_hash_for_testing',
            'generate_cert': 'dummy_hash_for_testing',
            'get_random': 'dummy_hash_for_testing'
        }
    }
    
    # Test with a fixed command and args
    command = 'tpm_provision'
    args = ['--force']
    
    # Mock the script runner
    with patch('helper.script_runner.ScriptRunner') as mock_runner_cls, \
         patch('tpm.tpm_message_handler.TPMMessageHandler') as mock_handler_cls:
            
        # Configure the mock script runner
        mock_exec_result = {
            "success": True,
            "output": "Mock command output",
            "error": "",
            "command": command,
            "args": args
        }
        mock_runner = mock_runner_cls.return_value
        mock_runner.execute.return_value = mock_exec_result
        
        # Configure the mock message handler
        mock_handler = mock_handler_cls.return_value
        mock_handler.channel = MagicMock()
        mock_handler.publish_command.return_value = "mock-message-id"
        
        # Initialize service with mocked components
        service = TPMService(config)
        service.script_runner = mock_runner  # Replace with our mock
        service.message_handler = mock_handler  # Replace with our mock
        
        # Test direct command execution
        result = service.execute_command(command, args)
        assert result == mock_exec_result, "Execute command should return expected result"
        mock_runner.execute.assert_called_once_with(command, args)

def test_tpm_service_send_command():
    """Test TPMService command sending through message queue"""
    # Create a simple hard-coded config
    config = {
        'rabbitmq_host': 'localhost',
        'secret_key': 'test_secret',
        'exchange': 'test_exchange',
        'script_dir': '/tmp',
        'script_paths': {
            'tpm_provision': '/tmp/tpm_provision.sh',
            'generate_cert': '/tmp/generate_cert.sh',
            'get_random': '/tmp/get_random.sh'
        },
        'script_hashes': {
            'tpm_provision': 'dummy_hash_for_testing',
            'generate_cert': 'dummy_hash_for_testing',
            'get_random': 'dummy_hash_for_testing'
        }
    }
    
    # Test with a fixed command and args
    command = 'tpm_provision'
    args = ['--force']
    
    # Mock the message handler
    with patch('tpm.tpm_message_handler.TPMMessageHandler') as mock_handler_cls, \
         patch('helper.script_runner.ScriptRunner') as mock_runner_cls:
        
        # Configure the mock message handler
        mock_handler = mock_handler_cls.return_value
        mock_handler.channel = MagicMock()
        mock_handler.publish_command.return_value = "mock-message-id"
        
        # Initialize service with mocked components
        service = TPMService(config)
        service.message_handler = mock_handler  # Replace with our mock
        
        # Test sending command through message queue
        message_id = service.send_command(command, args)
        assert message_id == "mock-message-id", "Send command should return message ID"
        mock_handler.publish_command.assert_called_once_with(command, args)

# Test TPMService's async methods
@pytest.mark.asyncio
@given(
    config_and_dir=service_configs(),
    command_and_args=tpm_commands()
)
@settings(
    max_examples=5, 
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow, 
        HealthCheck.data_too_large, 
        HealthCheck.function_scoped_fixture,
        HealthCheck.filter_too_much
    ]
)
async def test_tpm_service_async_operations(config_and_dir, command_and_args):
    """Test TPMService async operations"""
    config, script_dir = config_and_dir
    command, args = command_and_args
    
    try:
        # Configure mock results
        mock_exec_result = {
            "success": True,
            "output": "Mock async command output",
            "error": "",
            "command": command,
            "args": args
        }
        
        # Patch both TPMMessageHandler and ScriptRunner
        with patch('tpm.tpm_message_handler.TPMMessageHandler') as mock_handler_cls, \
             patch('helper.script_runner.ScriptRunner') as mock_runner_cls:
            
            # Configure the mock script runner
            mock_runner = MagicMock()
            mock_runner.execute.return_value = mock_exec_result
            mock_runner_cls.return_value = mock_runner
            
            # Configure the mock message handler
            mock_handler = MagicMock()
            mock_handler.channel = MagicMock()
            mock_handler.start_consuming.return_value = True
            mock_handler.stop_consuming.return_value = True
            mock_handler.publish_command.return_value = "mock-message-id"
            mock_handler_cls.return_value = mock_handler
            
            # Initialize service with mocked components
            service = TPMService(config)
            service.script_runner = mock_runner  # Replace with our mock
            service.message_handler = mock_handler  # Replace with our mock
            
            # Test async start
            result = await service.start_async()
            assert result is True, "Async start should succeed"
            
            # Test async command execution
            result = await service.execute_command_async(command, args)
            assert result == mock_exec_result, "Async execute command should return expected result"
            
            # Test async message sending
            message_id = await service.send_command_async(command, args)
            assert message_id == "mock-message-id", "Async send command should return message ID"
            
            # Test async stop
            result = await service.stop_async()
            assert result is True, "Async stop should succeed"
    finally:
        # Clean up temporary directory
        import shutil
        if os.path.exists(script_dir):
            shutil.rmtree(script_dir)

# Test TPMService event system
@given(
    config_and_dir=service_configs(),
    event_type=st.text(
        alphabet=string.ascii_letters + string.digits + '_',
        min_size=1,
        max_size=20
    ),
    event_data=st.text(min_size=0, max_size=100)
)
@settings(max_examples=10, deadline=None)
def test_tpm_service_events(config_and_dir, event_type, event_data):
    """Test TPMService event system"""
    config, script_dir = config_and_dir
    
    try:
        # Patch the message handler to avoid actual connections
        with patch('tpm.tpm_message_handler.TPMMessageHandler', autospec=True):
            # Initialize service
            service = TPMService(config)
            
            # Create a listener mock
            listener_mock = MagicMock()
            
            # Add the listener and verify
            result = service.add_event_listener(event_type, listener_mock)
            assert result is True, "Adding event listener should succeed"
            
            # Emit an event and verify listener was called
            count = service.emit_event(event_type, event_data)
            assert count == 1, "Emit event should return count of notified listeners"
            listener_mock.assert_called_once_with(event_data)
            
            # Test with no registered listeners
            random_event_type = event_type + "_nonexistent"
            count = service.emit_event(random_event_type, event_data)
            assert count == 0, "Emit event with no listeners should return 0"
    finally:
        # Clean up temporary directory
        import shutil
        if os.path.exists(script_dir):
            shutil.rmtree(script_dir)

# Test error handling in TPMService
@given(config_and_dir=service_configs())
@settings(max_examples=5, deadline=None)  # Remove deadline to avoid timing issues
def test_tpm_service_error_handling(config_and_dir):
    """Test TPMService error handling"""
    config, script_dir = config_and_dir
    
    try:
        # Clear any existing patches
        patch.stopall()
        
        with patch('tpm.tpm_message_handler.TPMMessageHandler') as mock_handler_cls:
            # Configure the mock message handler to fail
            mock_handler = MagicMock()
            mock_handler.channel = None  # This should cause start() to fail
            mock_handler_cls.return_value = mock_handler
            
            # Initialize service
            service = TPMService(config)
            
            # Make sure our mock is being used
            service.message_handler = mock_handler
            
            # Test starting with no channel
            result = service.start()
            assert result is False, "Start with no channel should fail"
            assert service.active is False, "Service should remain inactive after failed start"
    finally:
        # Clean up temporary directory
        import shutil
        if os.path.exists(script_dir):
            shutil.rmtree(script_dir)
        # Make sure all patches are stopped
        patch.stopall()

# Stateful testing with RuleBasedStateMachine
def __init__(self):
    super().__init__()
    # Create a temporary directory for scripts
    self.script_dir = tempfile.mkdtemp()
    
    # Create mock scripts for testing
    # ... (your existing script setup code)
    
    # Basic config using localhost
    self.config = {
        'rabbitmq_host': 'localhost',
        'secret_key': 'test_secret',
        'exchange': 'test_exchange',
        'script_dir': self.script_dir,
        'script_paths': script_paths,
        'script_hashes': {
            name: "dummy_hash_for_testing" for name in script_paths.keys()
        }
    }
    
    # Stop any existing patches first
    patch.stopall()
    
    # Create mocks WITHOUT autospec
    self.mock_handler_patcher = patch('tpm.tpm_message_handler.TPMMessageHandler')
    self.mock_runner_patcher = patch('helper.script_runner.ScriptRunner')
    
    # Start patchers
    self.mock_handler_cls = self.mock_handler_patcher.start()
    self.mock_runner_cls = self.mock_runner_patcher.start()
    
    # Configure mock returns
    self.mock_handler = MagicMock()
    self.mock_handler.channel = MagicMock()
    self.mock_handler.start_consuming.return_value = True
    self.mock_handler.stop_consuming.return_value = True
    self.mock_handler.publish_command.return_value = "mock-message-id"
    self.mock_handler_cls.return_value = self.mock_handler
    
    self.mock_runner = MagicMock()
    self.mock_runner.execute.return_value = {
        "success": True,
        "output": "Mock command output",
        "error": "",
        "command": "test_command",
        "args": []
    }
    self.mock_runner_cls.return_value = self.mock_runner
    
    # Initialize service
    self.service = TPMService(self.config)
    
    # Explicitly replace service components with our mocks
    self.service.script_runner = self.mock_runner
    self.service.message_handler = self.mock_handler
    
    # State tracking
    self.started = False
    self.commands_executed = []
    self.commands_sent = []
    self.events = {}

def teardown(self):
    """Clean up after the test"""
    try:
        # Stop service if it's running
        if self.started and self.service:
            self.service.stop()
        
        # Stop all patchers
        if hasattr(self, 'mock_handler_patcher'):
            self.mock_handler_patcher.stop()
        if hasattr(self, 'mock_runner_patcher'):
            self.mock_runner_patcher.stop()
            
        # Stop any other patches that might be active
        patch.stopall()
            
    except Exception as e:
        print(f"Error in teardown: {e}")
    finally:
        # Clean up temporary directory
        import shutil
        if os.path.exists(self.script_dir):
            shutil.rmtree(self.script_dir)