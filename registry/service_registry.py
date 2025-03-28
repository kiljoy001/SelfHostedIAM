# registry/service_registry.py
import asyncio
import logging
import threading
from typing import Dict, Any, Callable, Optional, List, Union, Awaitable, Coroutine

logger = logging.getLogger(__name__)

class ServiceRegistry:
    """
    Service registry to manage and coordinate system modules.
    Supports both synchronous and asynchronous operations.
    """
    
    def __init__(self):
        """Initialize the service registry"""
        self.services = {}
        self.message_handlers = {}
        self.event_listeners = {}
        self._lock = threading.RLock()  # Thread-safe operations
        self.loop = None  # AsyncIO event loop for async operations
        
        # Try to get the current event loop or create a new one
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in this thread, create a new one
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
    
    def register_service(self, service_name: str, service: Any) -> bool:
        """
        Register a service with the registry.
        
        Args:
            service_name: Name to register the service under
            service: Service instance
            
        Returns:
            True if registration was successful
        """
        with self._lock:
            if service_name in self.services:
                logger.warning(f"Service '{service_name}' already registered")
                return False
            
            logger.info(f"Registering service: {service_name}")
            self.services[service_name] = service
            return True
    
    async def register_service_async(self, service_name: str, service: Any) -> bool:
        """Async version of register_service"""
        return self.register_service(service_name, service)
    
    def get_service(self, service_name: str) -> Any:
        """Get a service by name"""
        with self._lock:
            return self.services.get(service_name)
    
    async def get_service_async(self, service_name: str) -> Any:
        """Async version of get_service"""
        return self.get_service(service_name)
    
    def register_message_handler(self, routing_key: str, handler: Callable, 
                                queue_name: Optional[str] = None) -> bool:
        """Register a message handler for a routing key"""
        with self._lock:
            if routing_key not in self.message_handlers:
                self.message_handlers[routing_key] = []
            
            # Check if handler is already registered
            for existing in self.message_handlers[routing_key]:
                if existing["handler"] == handler:
                    logger.warning(f"Handler already registered for {routing_key}")
                    return False
            
            self.message_handlers[routing_key].append({
                "handler": handler,
                "queue_name": queue_name,
                "is_async": asyncio.iscoroutinefunction(handler)
            })
            
            logger.info(f"Registered message handler for {routing_key}")
            return True
    
    async def register_message_handler_async(self, routing_key: str, handler: Callable,
                                           queue_name: Optional[str] = None) -> bool:
        """Async version of register_message_handler"""
        return self.register_message_handler(routing_key, handler, queue_name)
    
    def register_event_listener(self, event_type: str, 
                           listener: Union[Callable, Coroutine]) -> bool:
     """Register an event listener"""
     with self._lock:
         if event_type not in self.event_listeners:
             self.event_listeners[event_type] = []
         
         # Check if listener is already registered
         for existing_listener_info in self.event_listeners[event_type]:
             if existing_listener_info["listener"] == listener:
                 logger.warning(f"Listener already registered for {event_type}")
                 return False
         
         self.event_listeners[event_type].append({
             "listener": listener,
             "is_async": asyncio.iscoroutinefunction(listener)
         })
         logger.info(f"Registered event listener for {event_type}")
         return True
    
    async def register_event_listener_async(self, event_type: str, 
                                          listener: Union[Callable, Coroutine]) -> bool:
        """Async version of register_event_listener"""
        return self.register_event_listener(event_type, listener)
    
    def emit_event(self, event_type: str, *args, **kwargs) -> int:
        """
        Emit an event to all registered listeners.
        
        Returns:
            Number of listeners notified
        """
        with self._lock:
            if event_type not in self.event_listeners:
                return 0
            
            listeners = list(self.event_listeners[event_type])
        
        # Notify listeners (outside lock to avoid deadlocks)
        count = 0
        for listener_info in listeners:
            listener = listener_info["listener"]
            is_async = listener_info["is_async"]
            
            try:
                if is_async:
                    # For async listeners, we need to schedule them
                    if self.loop is None or self.loop.is_closed():
                        # Ensure we have a valid loop
                        try:
                            self.loop = asyncio.get_event_loop()
                        except RuntimeError:
                            # Create a new loop if none is available
                            self.loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(self.loop)
                    
                    # Schedule the async callback
                    asyncio.run_coroutine_threadsafe(
                        listener(*args, **kwargs), self.loop
                    )
                else:
                    # For synchronous listeners, just call directly
                    listener(*args, **kwargs)
                count += 1
            except Exception as e:
                logger.error(f"Error in listener for {event_type}: {e}")
        
        return count
    
    async def emit_event_async(self, event_type: str, *args, **kwargs) -> int:
        """
        Asynchronously emit an event to all registered listeners.
        Async listeners will be awaited properly.
        
        Returns:
            Number of listeners notified
        """
        with self._lock:
            if event_type not in self.event_listeners:
                return 0
            
            listeners = list(self.event_listeners[event_type])
        
        # Notify listeners
        count = 0
        for listener_info in listeners:
            listener = listener_info["listener"]
            is_async = listener_info["is_async"]
            
            try:
                if is_async:
                    # Await async listeners
                    await listener(*args, **kwargs)
                else:
                    # Run sync listeners in the executor to avoid blocking
                    await asyncio.get_event_loop().run_in_executor(
                        None, listener, *args, **kwargs
                    )
                count += 1
            except Exception as e:
                logger.error(f"Error in listener for {event_type}: {e}")
        
        return count
    
    def start_all_services(self) -> Dict[str, bool]:
        """
        Start all registered services.
        
        Returns:
            Dictionary mapping service names to start success
        """
        results = {}
        with self._lock:
            services = list(self.services.items())
        
        for name, service in services:
            if hasattr(service, 'start') and callable(service.start):
                try:
                    logger.info(f"Starting service: {name}")
                    success = service.start()
                    results[name] = success
                except Exception as e:
                    logger.error(f"Error starting service {name}: {e}")
                    results[name] = False
            else:
                logger.warning(f"Service {name} has no start method")
                results[name] = False
        
        return results
    
    async def start_all_services_async(self) -> Dict[str, bool]:
        """
        Start all registered services asynchronously.
        
        Returns:
            Dictionary mapping service names to start success
        """
        results = {}
        with self._lock:
            services = list(self.services.items())
        
        # Start services in parallel
        start_tasks = []
        
        for name, service in services:
            if hasattr(service, 'start_async') and asyncio.iscoroutinefunction(service.start_async):
                # If the service has an async start method, use it
                start_tasks.append(self._start_service_async(name, service))
            elif hasattr(service, 'start') and callable(service.start):
                # If the service has a sync start method, run it in an executor
                start_tasks.append(self._start_service_sync(name, service))
            else:
                logger.warning(f"Service {name} has no start method")
                results[name] = False
        
        # Wait for all services to start
        if start_tasks:
            service_results = await asyncio.gather(*start_tasks, return_exceptions=True)
            
            # Process results
            for i, (name, _) in enumerate(services):
                if i < len(service_results):
                    if isinstance(service_results[i], Exception):
                        logger.error(f"Error starting service {name}: {service_results[i]}")
                        results[name] = False
                    else:
                        results[name] = service_results[i]
        
        return results
    
    async def _start_service_async(self, name, service):
        """Helper to start a service asynchronously"""
        try:
            logger.info(f"Starting service asynchronously: {name}")
            return await service.start_async()
        except Exception as e:
            logger.error(f"Error in async start of service {name}: {e}")
            raise
    
    async def _start_service_sync(self, name, service):
        """Helper to start a synchronous service in an executor"""
        try:
            logger.info(f"Starting service in executor: {name}")
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, service.start)
        except Exception as e:
            logger.error(f"Error in sync start of service {name}: {e}")
            raise
    
    def stop_all_services(self) -> Dict[str, bool]:
        """
        Stop all registered services.
        
        Returns:
            Dictionary mapping service names to stop success
        """
        results = {}
        with self._lock:
            # Reverse order to stop dependent services first
            services = list(reversed(list(self.services.items())))
        
        for name, service in services:
            if hasattr(service, 'stop') and callable(service.stop):
                try:
                    logger.info(f"Stopping service: {name}")
                    success = service.stop()
                    results[name] = success
                except Exception as e:
                    logger.error(f"Error stopping service {name}: {e}")
                    results[name] = False
            else:
                logger.warning(f"Service {name} has no stop method")
                results[name] = False
        
        return results
    
    async def stop_all_services_async(self) -> Dict[str, bool]:
        """
        Stop all registered services asynchronously.
        
        Returns:
            Dictionary mapping service names to stop success
        """
        results = {}
        with self._lock:
            # Reverse order to stop dependent services first
            services = list(reversed(list(self.services.items())))
        
        # Stop services in parallel
        stop_tasks = []
        
        for name, service in services:
            if hasattr(service, 'stop_async') and asyncio.iscoroutinefunction(service.stop_async):
                # If the service has an async stop method, use it
                stop_tasks.append(self._stop_service_async(name, service))
            elif hasattr(service, 'stop') and callable(service.stop):
                # If the service has a sync stop method, run it in an executor
                stop_tasks.append(self._stop_service_sync(name, service))
            else:
                logger.warning(f"Service {name} has no stop method")
                results[name] = False
        
        # Wait for all services to stop
        if stop_tasks:
            service_results = await asyncio.gather(*stop_tasks, return_exceptions=True)
            
            # Process results
            for i, (name, _) in enumerate(services):
                if i < len(service_results):
                    if isinstance(service_results[i], Exception):
                        logger.error(f"Error stopping service {name}: {service_results[i]}")
                        results[name] = False
                    else:
                        results[name] = service_results[i]
        
        return results
    
    async def _stop_service_async(self, name, service):
        """Helper to stop a service asynchronously"""
        try:
            logger.info(f"Stopping service asynchronously: {name}")
            return await service.stop_async()
        except Exception as e:
            logger.error(f"Error in async stop of service {name}: {e}")
            raise
    
    async def _stop_service_sync(self, name, service):
        """Helper to stop a synchronous service in an executor"""
        try:
            logger.info(f"Stopping service in executor: {name}")
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, service.stop)
        except Exception as e:
            logger.error(f"Error in sync stop of service {name}: {e}")
            raise