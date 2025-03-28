import pytest
import os
import logging
from unittest.mock import Mock, MagicMock

# Import the ServiceRegistry class
from registry.service_registry import ServiceRegistry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestServiceRegistry:
    """Test suite for the ServiceRegistry"""

    def test_register_service(self):
        """Test registering a service"""
        registry = ServiceRegistry()
        mock_service = Mock()
        
        # Register the service
        result = registry.register_service("test_service", mock_service)
        
        # Verify the results
        assert result is True, "Service registration should succeed"
        assert "test_service" in registry.services, "Service should be in registry"
        assert registry.services["test_service"] == mock_service, "Service reference should be stored"
        
        # Test duplicate registration
        result = registry.register_service("test_service", Mock())
        assert result is False, "Duplicate registration should fail"
    
    def test_get_service(self):
        """Test retrieving a service"""
        registry = ServiceRegistry()
        mock_service = Mock()
        
        # Register the service
        registry.register_service("test_service", mock_service)
        
        # Get the service
        service = registry.get_service("test_service")
        assert service == mock_service, "Should retrieve the registered service"
        
        # Get nonexistent service
        service = registry.get_service("nonexistent")
        assert service is None, "Should return None for nonexistent service"
    
    def test_register_message_handler(self):
        """Test registering a message handler"""
        registry = ServiceRegistry()
        mock_handler = Mock()
        
        # Register the handler
        result = registry.register_message_handler("test.routing.key", mock_handler, "test_queue")
        
        # Verify results
        assert result is True, "Handler registration should succeed"
        assert "test.routing.key" in registry.message_handlers, "Routing key should be in registry"
        assert registry.message_handlers["test.routing.key"][0]["handler"] == mock_handler, "Handler should be stored"
        assert registry.message_handlers["test.routing.key"][0]["queue_name"] == "test_queue", "Queue name should be stored"
        
        # Test duplicate registration
        result = registry.register_message_handler("test.routing.key", mock_handler)
        assert result is False, "Duplicate handler registration should fail"
    
    def test_register_event_listener(self):
        """Test registering an event listener"""
        registry = ServiceRegistry()
        mock_listener = Mock()
        
        # Register the listener
        result = registry.register_event_listener("test_event", mock_listener)
        
        # Verify results
        assert result is True, "Listener registration should succeed"
        assert "test_event" in registry.event_listeners, "Event type should be in registry"
        assert registry.event_listeners["test_event"][0] == {'is_async': False, 'listener':mock_listener }, "Listener should be stored"
        
        # Test duplicate registration
        result = registry.register_event_listener("test_event", mock_listener)
        assert result is False, "Duplicate listener registration should fail"
    
    def test_emit_event(self):
        """Test emitting events to listeners"""
        registry = ServiceRegistry()
        mock_listener1 = Mock()
        mock_listener2 = Mock()
        
        # Register the listeners
        registry.register_event_listener("test_event", mock_listener1)
        registry.register_event_listener("test_event", mock_listener2)
        
        # Emit an event
        count = registry.emit_event("test_event", "arg1", "arg2", kwarg1="value1")
        
        # Verify results
        assert count == 2, "Should notify 2 listeners"
        mock_listener1.assert_called_once_with("arg1", "arg2", kwarg1="value1")
        mock_listener2.assert_called_once_with("arg1", "arg2", kwarg1="value1")
        
        # Test error handling
        mock_listener1.side_effect = Exception("Test exception")
        count = registry.emit_event("test_event")
        assert count == 1, "Should count only successful notifications"
    
    def test_start_all_services(self):
        """Test starting all services"""
        registry = ServiceRegistry()
        
        # Create mock services
        service1 = Mock()
        service1.start = Mock(return_value=True)
        
        service2 = Mock()
        service2.start = Mock(return_value=True)
        
        service3 = Mock(spec=[])  # Service without start method
        
        # Register the services
        registry.register_service("service1", service1)
        registry.register_service("service2", service2)
        registry.register_service("service3", service3)
        
        # Start all services
        results = registry.start_all_services()
        
        # Verify results
        assert results["service1"] is True, "Service1 should start successfully"
        assert results["service2"] is True, "Service2 should start successfully"
        assert results["service3"] is False, "Service3 should fail to start"
        
        service1.start.assert_called_once()
        service2.start.assert_called_once()
    
    def test_stop_all_services(self):
        """Test stopping all services"""
        registry = ServiceRegistry()
        
        # Create mock services
        service1 = Mock()
        service1.stop = Mock(return_value=True)
        
        service2 = Mock()
        service2.stop = Mock(return_value=True)
        
        service3 = Mock(spec=[])  # Service without stop method
        
        # Register the services
        registry.register_service("service1", service1)
        registry.register_service("service2", service2)
        registry.register_service("service3", service3)
        
        # Stop all services
        results = registry.stop_all_services()
        
        # Verify results
        assert results["service1"] is True, "Service1 should stop successfully"
        assert results["service2"] is True, "Service2 should stop successfully"
        assert results["service3"] is False, "Service3 should fail to stop"
        
        service1.stop.assert_called_once()
        service2.stop.assert_called_once()
    
    def test_service_error_handling(self):
        """Test error handling during service operations"""
        registry = ServiceRegistry()
        
        # Create mock service that raises an exception
        service = Mock()
        service.start = Mock(side_effect=Exception("Test exception"))
        service.stop = Mock(side_effect=Exception("Test exception"))
        
        # Register the service
        registry.register_service("error_service", service)
        
        # Test error handling in start
        results = registry.start_all_services()
        assert results["error_service"] is False, "Should handle start exception"
        
        # Test error handling in stop
        results = registry.stop_all_services()
        assert results["error_service"] is False, "Should handle stop exception"