import logging
import asyncio
from typing import Dict, Any, Optional, Union, List, Callable, Awaitable

# Configure logging
logger = logging.getLogger(__name__)

class BaseService:
    """
    Base service class that provides common functionality for different service types.
    
    This class serves as a foundation for specialized services like EmercoinService
    and TPMService, providing shared initialization, configuration, and state management.
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
        
        # Allow derived classes to initialize their specific components
        # We don't call _initialize here since it's async and __init__ can't be async
        
    async def initialize(self):
        """
        Initialize the service (async version).
        
        This should be called after instantiation.
        """
        await self._initialize()
        
    async def _initialize(self):
        """
        Initialize service-specific components. 
        
        This method should be overridden by derived classes.
        """
        pass
        
    async def start(self) -> bool:
        """
        Start the service.
        
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
            self.active = True
            await self.emit_event("state_change", old_state=State.IDLE, new_state=State.PROCESSING)
            self.state_machine.transition(State.COMPLETED, {"action": "start", "completed": True})
            await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.COMPLETED)
        return success
        
    async def stop(self) -> bool:
        """
        Stop the service.
        
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
            self.active = False
            await self.emit_event("state_change", old_state=current_state, new_state=State.PROCESSING)
            self.state_machine.transition(State.IDLE, {"action": "stop", "completed": True})
            await self.emit_event("state_change", old_state=State.PROCESSING, new_state=State.IDLE)
        return success
        
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
                else:
                    # For synchronous listeners, run in executor
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, lambda: listener(*args, **kwargs))
                count += 1
            except Exception as e:
                logger.error(f"Error in event listener for {event_type}: {str(e)}")
                
        return count
    
    async def reset_state(self) -> bool:
        """
        Reset the service state to IDLE.
        
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
    async def create_fixture(cls, config: Dict[str, Any] = None):
        """
        Create a fixture version of this service for testing.
        
        Args:
            config: Configuration to pass to the fixture
            
        Returns:
            BaseService: A properly configured instance for tests
        """
        service = cls(config)
        await service.initialize()
        return service