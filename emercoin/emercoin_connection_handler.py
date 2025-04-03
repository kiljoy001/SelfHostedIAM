import json
import time
import uuid
import logging
import requests
import asyncio
import aiohttp
from typing import Any, Dict, List, Optional, Union

# Configure logging
logger = logging.getLogger(__name__)


class ConnectionError(Exception):
    """Exception raised for connection-related errors."""
    pass


class AuthError(Exception):
    """Exception raised for authentication failures."""
    pass


class RPCError(Exception):
    """Exception raised for RPC-specific errors."""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"RPC Error {code}: {message}")


class QueueManager:
    """
    Manages message queuing for asynchronous RPC operations.
    This is a placeholder implementation that would integrate with RabbitMQ.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # In a real implementation, this would establish a connection to RabbitMQ
        logger.info("Initializing Queue Manager with configuration: %s", 
                   {k: v for k, v in config.items() if k != 'rpc_password'})
        
    def publish(self, queue_name: str, message: Dict[str, Any]) -> str:
        """
        Publish a message to the specified queue.
        
        Args:
            queue_name: The name of the queue to publish to
            message: The message to publish
            
        Returns:
            str: A message ID for tracking
        """
        message_id = str(uuid.uuid4())
        # In a real implementation, this would publish to RabbitMQ
        logger.info(f"Published message {message_id} to queue {queue_name}")
        return message_id


class EmercoinConnection:
    """
    Provides a connection to an Emercoin node with support for both
    direct RPC calls and queue-based operations.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the connection with the provided configuration.
        
        Args:
            config: A dictionary containing configuration options:
                - rpc_url: URL of the Emercoin node RPC endpoint
                - rpc_user: RPC username
                - rpc_password: RPC password
                - timeout: Request timeout in seconds (default: 30)
                - max_retries: Maximum number of retry attempts (default: 3)
                - retry_delay: Delay between retries in seconds (default: 1)
                - use_queue: Whether to use queue-based operations (default: False)
        
        Raises:
            ValueError: If required configuration options are missing
        """
        self._validate_config(config)
        self.config = config
        
        # Log initialization (without sensitive data)
        logger.info("Initializing Emercoin connection to %s", config['rpc_url'])
        
        # Initialize queue manager if needed
        self.queue_manager = None
        if config.get('use_queue', False):
            self.queue_manager = QueueManager(config)
            
        # Request counter for message IDs
        self.request_counter = 0
        
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate the provided configuration.
        
        Args:
            config: Configuration dictionary
            
        Raises:
            ValueError: If required configuration options are missing
        """
        required_fields = ['rpc_url', 'rpc_user', 'rpc_password']
        missing_fields = [field for field in required_fields if not config.get(field)]
        
        if missing_fields:
            raise ValueError(f"Missing required configuration: {', '.join(missing_fields)}")
    
    def call(self, method: str, params: List[Any] = None) -> Any:
        """
        Make an RPC call to the Emercoin node.
        
        If use_queue is enabled in the configuration, the call will be queued
        for asynchronous processing. Otherwise, a direct RPC call will be made.
        
        Args:
            method: The RPC method to call
            params: Parameters for the RPC method (optional)
            
        Returns:
            The result from the RPC call
            
        Raises:
            ConnectionError: If the connection to the node fails
            AuthError: If authentication fails
            RPCError: If the RPC call returns an error
        """
        if params is None:
            params = []
            
        logger.debug(f"RPC call: {method} with params {params}")
            
        # If queue mode is enabled, publish to queue
        if self.config.get('use_queue', False) and self.queue_manager:
            return self._queue_call(method, params)
            
        # Otherwise, make a direct RPC call
        return self._direct_call(method, params)
    
    def _queue_call(self, method: str, params: List[Any]) -> str:
        """
        Queue an RPC call for asynchronous processing.
        
        Args:
            method: The RPC method to call
            params: Parameters for the RPC method
            
        Returns:
            str: A message ID for tracking the queued call
        """
        message = {
            'method': method,
            'params': params
        }
        
        return self.queue_manager.publish('emercoin_rpc', message)
    
    def _direct_call(self, method: str, params: List[Any]) -> Any:
        """
        Make a direct RPC call to the Emercoin node.
        
        Args:
            method: The RPC method to call
            params: Parameters for the RPC method
            
        Returns:
            The result from the RPC call
            
        Raises:
            ConnectionError: If the connection to the node fails
            AuthError: If authentication fails
            RPCError: If the RPC call returns an error
        """
        # Get configuration values
        rpc_url = self.config['rpc_url']
        rpc_user = self.config['rpc_user']
        rpc_password = self.config['rpc_password']
        timeout = self.config.get('timeout', 30)
        max_retries = self.config.get('max_retries', 3)
        retry_delay = self.config.get('retry_delay', 1)
        
        # Increment request counter for unique ID
        self.request_counter += 1
        
        # Prepare request payload
        payload = {
            'method': method,
            'params': params,
            'jsonrpc': '2.0',
            'id': self.request_counter
        }
        
        # Try to make the request, with retries
        retry_count = 0
        last_exception = None
        
        while retry_count <= max_retries:
            try:
                response = requests.post(
                    url=rpc_url,
                    data=json.dumps(payload),
                    auth=(rpc_user, rpc_password),
                    headers={'Content-Type': 'application/json'},
                    timeout=timeout
                )
                
                # Check for authentication errors
                if response.status_code in (401, 403):
                    logger.error(f"Authentication failed for RPC call to {rpc_url}")
                    raise AuthError("Authentication failed for Emercoin RPC")
                
                # Check for other HTTP errors
                response.raise_for_status()
                
                # Parse response
                result = response.json()
                
                # Check for RPC error
                if result.get('error'):
                    error = result['error']
                    error_code = error.get('code', -1)
                    error_message = error.get('message', 'Unknown RPC error')
                    logger.error(f"RPC error {error_code}: {error_message}")
                    raise RPCError(error_code, error_message)
                
                # Return result
                return result.get('result')
                
            except (requests.exceptions.RequestException, requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout) as e:
                last_exception = e
                retry_count += 1
                
                if retry_count <= max_retries:
                    logger.warning(f"RPC call failed, retrying ({retry_count}/{max_retries}): {str(e)}")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"RPC call failed after {max_retries} retries: {str(e)}")
                    break
        
        # If we've exhausted retries, raise the last exception
        if last_exception:
            raise ConnectionError(f"Failed to connect to Emercoin node: {str(last_exception)}")
        
        # This should never happen, but just in case
        raise ConnectionError("Unknown error occurred during RPC call")
    
    async def async_call(self, method: str, params: List[Any] = None) -> Any:
        """
        Make an asynchronous RPC call to the Emercoin node.
        
        Args:
            method: The RPC method to call
            params: Parameters for the RPC method (optional)
            
        Returns:
            The result from the RPC call
            
        Raises:
            ConnectionError: If the connection to the node fails
            AuthError: If authentication fails
            RPCError: If the RPC call returns an error
        """
        if params is None:
            params = []
            
        # If queue mode is enabled, publish to queue
        if self.config.get('use_queue', False) and self.queue_manager:
            return self._queue_call(method, params)
        
        # Get configuration values
        rpc_url = self.config['rpc_url']
        rpc_user = self.config['rpc_user']
        rpc_password = self.config['rpc_password']
        timeout = self.config.get('timeout', 30)
        max_retries = self.config.get('max_retries', 3)
        retry_delay = self.config.get('retry_delay', 1)
        
        # Increment request counter for unique ID
        self.request_counter += 1
        
        # Prepare request payload
        payload = {
            'method': method,
            'params': params,
            'jsonrpc': '2.0',
            'id': self.request_counter
        }
        
        # Try to make the request, with retries
        retry_count = 0
        last_exception = None
        
        while retry_count <= max_retries:
            try:
                async with aiohttp.ClientSession() as session:
                    auth = aiohttp.BasicAuth(rpc_user, rpc_password)
                    
                    async with session.post(
                        url=rpc_url,
                        json=payload,
                        auth=auth,
                        headers={'Content-Type': 'application/json'},
                        timeout=timeout
                    ) as response:
                        # Check for authentication errors
                        if response.status in (401, 403):
                            logger.error(f"Authentication failed for async RPC call to {rpc_url}")
                            raise AuthError("Authentication failed for Emercoin RPC")
                        
                        # Check for other HTTP errors
                        response.raise_for_status()
                        
                        # Parse response
                        result = await response.json()
                        
                        # Check for RPC error
                        if result.get('error'):
                            error = result['error']
                            error_code = error.get('code', -1)
                            error_message = error.get('message', 'Unknown RPC error')
                            logger.error(f"Async RPC error {error_code}: {error_message}")
                            raise RPCError(error_code, error_message)
                        
                        # Return result
                        return result.get('result')
                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                retry_count += 1
                
                if retry_count <= max_retries:
                    logger.warning(f"Async RPC call failed, retrying ({retry_count}/{max_retries}): {str(e)}")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"Async RPC call failed after {max_retries} retries: {str(e)}")
                    break
        
        # If we've exhausted retries, raise the last exception
        if last_exception:
            raise ConnectionError(f"Failed to connect to Emercoin node: {str(last_exception)}")
        
        # This should never happen, but just in case
        raise ConnectionError("Unknown error occurred during async RPC call")