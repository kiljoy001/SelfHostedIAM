# app.py
import asyncio
import logging
import os
import signal
import sys
import threading
from typing import Dict, List, Any, Optional

# Import the service registry
from registry.service_registry import ServiceRegistry

# Import module factories
from tpm import create_tpm_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AsyncApplication:
    """Main application class that manages all services using async/await"""
    
    def __init__(self):
        """Initialize the application"""
        self.registry = ServiceRegistry()
        self.running = False
        self.services = {}
        self.main_event_loop = None
        self.shutdown_event = asyncio.Event()
        
        # Set up signal handlers
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown"""
        # Use the same handler for both signals
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_exit_signal)
    
    def _handle_exit_signal(self, signum, frame):
        """Handle termination signals"""
        logger.info(f"Received signal {signum}, initiating shutdown")
        if self.main_event_loop and self.shutdown_event:
            # Schedule the shutdown event in the event loop
            asyncio.run_coroutine_threadsafe(self._trigger_shutdown(), self.main_event_loop)
    
    async def _trigger_shutdown(self):
        """Trigger the shutdown event"""
        self.shutdown_event.set()
    
    async def initialize(self):
        """Initialize application services asynchronously"""
        logger.info("Initializing application")
        
        # Store the event loop for signal handling
        self.main_event_loop = asyncio.get_running_loop()
        
        # Create and register TPM service
        tpm_config = {
            'rabbitmq_host': os.getenv('RABBITMQ_HOST', 'localhost'),
            'secret_key': os.getenv('HMAC_SECRET', 'default_secret'),
            'exchange': 'app_events'
        }
        
        tpm_service = create_tpm_service(tpm_config, self.registry)
        self.services['tpm'] = tpm_service
        
        # Add more services as they are developed
        # Example:
        # from emercoin import create_emercoin_service
        # emercoin_service = create_emercoin_service(emercoin_config, self.registry)
        # self.services['emercoin'] = emercoin_service
        
        # Initialize any shared resources
        
        logger.info("Application initialized")
    
    async def start(self):
        """Start the application and all services asynchronously"""
        if self.running:
            logger.warning("Application already running")
            return
        
        logger.info("Starting application")
        
        # Start all services asynchronously
        results = await self.registry.start_all_services_async()
        
        success = all(results.values())
        if success:
            logger.info("All services started successfully")
            self.running = True
        else:
            logger.error("Some services failed to start")
            # Optionally shut down services that did start
            await self.stop()
        
        return success
    
    async def run(self):
        """Run the application until shutdown is requested"""
        # Start the application
        if not await self.start():
            logger.error("Application failed to start")
            return False
        
        logger.info("Application running, press Ctrl+C to stop")
        
        # Wait for shutdown event
        try:
            await self.shutdown_event.wait()
            logger.info("Shutdown event received")
        except asyncio.CancelledError:
            logger.info("Run task cancelled")
        finally:
            # Stop the application
            await self.stop()
        
        return True
    
    async def stop(self):
        """Stop the application and all services asynchronously"""
        if not self.running and not self.services:
            logger.warning("Application not running")
            return True
        
        logger.info("Stopping application")
        
        # Stop all services asynchronously
        results = await self.registry.stop_all_services_async()
        
        success = all(results.values())
        if success:
            logger.info("All services stopped successfully")
        else:
            logger.error("Some services failed to stop")
        
        self.running = False
        return success

async def main():
    """Async main function"""
    app = AsyncApplication()
    
    try:
        # Initialize and run the application
        await app.initialize()
        await app.run()
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    # Run the async main function
    exit_code = asyncio.run(main())
    sys.exit(exit_code)