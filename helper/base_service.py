# services/base_service.py
import logging
import asyncio
from typing import Dict, Any, Optional, Union, List, Callable, Awaitable

# Configure logging
logger = logging.getLogger(__name__)

class BaseService:
    """
    Base service class that provides common functionality for different service types.
    
    This class serves as a foundation for specialized services, providing shared
    initialization, configuration, and state management.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the base service.
        
        Args:
            config: Configuration dictionary for the service
        """
        from helper.finite_state_machine import BaseStateMachine, State
        
        self.config = config or {}
        self.active = False
        self._event_listeners = {}
        self.state_machine = BaseStateMachine()
        logger.debug("Base service initialized with config")
        
        # Initialize synchronously to maintain backward compatibility
        self._initialize_sync()
    
    def _initialize_sync(self):
        """
        Initialize service-specific components synchronously.
        
        This method should be overridden by derived classes.
        """
        pass
        
    async def initialize_async(self):
        """
        Initialize the service asynchronously.
        
        This should be called for async operations.
        """
        return await self._initialize_async()
        
    async def _initialize_async(self):
        """
        Initialize service-specific components asynchronously. 
        
        This method should be overridden by derived classes if they need
        async initialization.
        """
        pass
        
    def start(self) -> bool:
        """
        Start the service synchronously.
        
        Returns:
            bool: True if started successfully, False otherwise
        """
        from helper.finite_state_machine import State
        
        if self.active:
            logger.warning(f"{self.__class__.__name__} already running")
            return True
            
        logger.info(f"Starting {self.__class__.__name__}")
        success = self.state_machine.transition(State.PROCESSING, {"action": "start"})
        if success:
            start_result = self._start_implementation()
            if start_result:
                self.active = True
                self.state_machine.transition(State.COMPLETED, {"action": "start", "completed": True})
                self.emit_event_sync("state_change", old_state=State.PROCESSING, new_state=State.COMPLETED)
                return True
            else:
                self.state_machine.transition(State.FAILED, {"action": "start", "error": "Start failed"})
                self.emit_event_sync("state_change", old_state=State.PROCESSING, new_state=State.FAILED)
                return False
        return success
    
    def _start_implementation(self) -> bool:
        """
        Actual implementation of start logic.
        
        Override this in derived classes.
        """
        return True
        
    async def start_async(self) -> bool:
        """
        Start the service asynchronously.
        
        Returns:
            bool: True if started successfully, False otherwise
        """
        from helper.finite_state_machine import State
        
        if self.active:
            logger.warning(f"{self.__class__.__name__} already running")
            return True
            
        logger.info(f"Starting {self.__class__.__name__} asynchronously")
        success = self.state_machine.transition(State.PROCESSING, {"action": "start"})
        if success:
            start_result = await self._start_async_implementation()
            if start_result:
                self.active = True
                self.state_machine.transition(State.COMPLETED, {"action": "start", "completed": True})
                await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.COMPLETED)
                return True
            else:
                self.state_machine.transition(State.FAILED, {"action": "start", "error": "Start failed"})
                await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.FAILED)
                return False
        return success
    
    async def _start_async_implementation(self) -> bool:
        """
        Actual implementation of async start logic.
        
        Override this in derived classes.
        """
        # Default implementation just calls the sync version in a thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._start_implementation)
        
    def stop(self) -> bool:
        """
        Stop the service synchronously.
        
        Returns:
            bool: True if stopped successfully, False otherwise
        """
        from helper.finite_state_machine import State
        
        if not self.active:
            logger.warning(f"{self.__class__.__name__} not running")
            return True
            
        logger.info(f"Stopping {self.__class__.__name__}")
        current_state = self.state_machine.state
        success = self.state_machine.transition(State.PROCESSING, {"action": "stop"})
        if success:
            stop_result = self._stop_implementation()
            self.active = False
            if stop_result:
                self.state_machine.transition(State.IDLE, {"action": "stop", "completed": True})
                self.emit_event_sync("state_change", old_state=State.PROCESSING, new_state=State.IDLE)
            else:
                self.state_machine.transition(State.FAILED, {"action": "stop", "error": "Stop failed"})
                self.emit_event_sync("state_change", old_state=State.PROCESSING, new_state=State.FAILED)
            return True
        return success
    
    def _stop_implementation(self) -> bool:
        """
        Actual implementation of stop logic.
        
        Override this in derived classes.
        """
        return True
        
    async def stop_async(self) -> bool:
        """
        Stop the service asynchronously.
        
        Returns:
            bool: True if stopped successfully, False otherwise
        """
        from helper.finite_state_machine import State
        
        if not self.active:
            logger.warning(f"{self.__class__.__name__} not running")
            return True
            
        logger.info(f"Stopping {self.__class__.__name__} asynchronously")
        current_state = self.state_machine.state
        success = self.state_machine.transition(State.PROCESSING, {"action": "stop"})
        if success:
            stop_result = await self._stop_async_implementation()
            self.active = False
            if stop_result:
                self.state_machine.transition(State.IDLE, {"action": "stop", "completed": True})
                await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.IDLE)
            else:
                self.state_machine.transition(State.FAILED, {"action": "stop", "error": "Stop failed"})
                await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.FAILED)
            return True
        return success
    
    async def _stop_async_implementation(self) -> bool:
        """
        Actual implementation of async stop logic.
        
        Override this in derived classes.
        """
        # Default implementation just calls the sync version in a thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._stop_implementation)
        
    def is_active(self) -> bool:
        """
        Check if the service is active.
        
        Returns:
            bool: True if active, False otherwise
        """
        return self.active
        
    def get_state(self):
        """
        Get the current state of the service.
        
        Returns:
            State: Current state from the state machine
        """
        return self.state_machine.state
        
    def add_event_listener(self, event_type: str, callback: Union[Callable, Awaitable]) -> bool:
        """
        Add an event listener for service events.
        
        Args:
            event_type: Type of event to listen for (e.g., 'state_change')
            callback: Callback function to call when event occurs (sync or async)
            
        Returns:
            bool: True if added successfully
        """
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
            
        self._event_listeners[event_type].append(callback)
        return True
    
    def emit_event_sync(self, event_type: str, *args, **kwargs) -> int:
        """
        Emit an event to all registered listeners synchronously.
        
        Args:
            event_type: Type of event to emit
            args, kwargs: Arguments to pass to listeners
            
        Returns:
            int: Number of listeners called
        """
        if event_type not in self._event_listeners:
            return 0
            
        count = 0
        for listener in self._event_listeners[event_type]:
            try:
                if not asyncio.iscoroutinefunction(listener):
                    # For synchronous listeners, just call directly
                    listener(*args, **kwargs)
                    count += 1
                # Skip async listeners in sync emission
            except Exception as e:
                logger.error(f"Error in event listener for {event_type}: {str(e)}")
                
        return count
        
    async def emit_event(self, event_type: str, *args, **kwargs) -> int:
        """
        Emit an event to all registered listeners asynchronously.
        
        Args:
            event_type: Type of event to emit
            args, kwargs: Arguments to pass to listeners
            
        Returns:
            int: Number of listeners called
        """
        if event_type not in self._event_listeners:
            return 0
            
        count = 0
        for listener in self._event_listeners[event_type]:
            try:
                if asyncio.iscoroutinefunction(listener):
                    # For async listeners, await them
                    await listener(*args, **kwargs)
                    count += 1
                else:
                    # For synchronous listeners, run in executor
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, lambda: listener(*args, **kwargs))
                    count += 1
            except Exception as e:
                logger.error(f"Error in event listener for {event_type}: {str(e)}")
                
        return count
    
    def reset_state(self) -> bool:
        """
        Reset the service state to IDLE.
        
        Returns:
            bool: True if reset was successful
        """
        from helper.finite_state_machine import State
        
        old_state = self.state_machine.state
        self.state_machine.reset()
        self.emit_event_sync("state_change", old_state=old_state, new_state=State.IDLE)
        return True
    
    async def reset_state_async(self) -> bool:
        """
        Reset the service state to IDLE asynchronously.
        
        Returns:
            bool: True if reset was successful
        """
        from helper.finite_state_machine import State
        
        old_state = self.state_machine.state
        self.state_machine.reset()
        await self.emit_event("state_change", old_state=old_state, new_state=State.IDLE)
        return True

    # Method for creating test fixtures or mocks with appropriate interfaces
    @classmethod
    def create_fixture(cls, config: Dict[str, Any] = None):
        """
        Create a fixture version of this service for testing.
        
        Args:
            config: Configuration to pass to the fixture
            
        Returns:
            BaseService: A properly configured instance for tests
        """
        return cls(config)
        
    @classmethod
    async def create_fixture_async(cls, config: Dict[str, Any] = None):
        """
        Create a fixture version of this service for testing asynchronously.
        
        Args:
            config: Configuration to pass to the fixture
            
        Returns:
            BaseService: A properly configured instance for tests
        """
        service = cls(config)
        await service.initialize_async()
        return service