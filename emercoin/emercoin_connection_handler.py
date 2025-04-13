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
                - rpc_url: URL of the Emercoin node RPC endpoint (default: http://localhost:6662)
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
        self.config = config.copy()  # Create a copy to avoid modifying the original
        
        # Set default URL for Emercoin if not provided
        if 'rpc_url' not in self.config:
            self.config['rpc_url'] = 'http://localhost:6662'
            
        # Log initialization (without sensitive data)
        logger.info("Initializing Emercoin connection to %s", self.config['rpc_url'])
        
        # Initialize queue manager if needed
        self.queue_manager = None
        if self.config.get('use_queue', False):
            self.queue_manager = QueueManager(self.config)
            
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
        required_fields = ['rpc_user', 'rpc_password']
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
            'jsonrpc': '2.0',  # Emercoin uses JSON-RPC 2.0
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
                    raise AuthError(f"Authentication failed for Emercoin RPC: {response.status_code}")
                
                # Check for other HTTP errors
                response.raise_for_status()
                
                # Parse response
                try:
                    result = response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON response: {response.text[:200]}")
                    raise ConnectionError(f"Failed to decode JSON response: {str(e)}")
                
                # Check for RPC error
                if result.get('error') is not None and result['error'] is not None:
                    error = result['error']
                    if isinstance(error, dict):
                        error_code = error.get('code', -1)
                        error_message = error.get('message', 'Unknown RPC error')
                    else:
                        error_code = -1
                        error_message = str(error)
                    
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
            'jsonrpc': '2.0',  # Emercoin uses JSON-RPC 2.0
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
                            raise AuthError(f"Authentication failed for Emercoin RPC: {response.status}")
                        
                        # Check for other HTTP errors
                        response.raise_for_status()
                        
                        # Parse response
                        try:
                            result = await response.json()
                        except (json.JSONDecodeError, aiohttp.ContentTypeError) as e:
                            text = await response.text()
                            logger.error(f"Invalid JSON response: {text[:200]}")
                            raise ConnectionError(f"Failed to decode JSON response: {str(e)}")
                        
                        # Check for RPC error
                        if result.get('error') is not None and result['error'] is not None:
                            error = result['error']
                            if isinstance(error, dict):
                                error_code = error.get('code', -1)
                                error_message = error.get('message', 'Unknown RPC error')
                            else:
                                error_code = -1
                                error_message = str(error)
                            
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

    # Convenience methods for common Emercoin RPC calls
    
    def get_info(self) -> Dict[str, Any]:
        """Get general information about the Emercoin node."""
        return self.call('getinfo')
    
    def get_block_count(self) -> int:
        """Get the current block count."""
        return self.call('getblockcount')
    
    def get_balance(self) -> float:
        """Get the total balance of the wallet."""
        return self.call('getbalance')
    
    def get_new_address(self, account: str = "") -> str:
        """
        Get a new Emercoin address for receiving payments.
        
        Args:
            account: Account name (for compatibility with older wallets)
            
        Returns:
            str: The new address
        """
        if account:
            return self.call('getnewaddress', [account])
        return self.call('getnewaddress')
    
    def send_to_address(self, address: str, amount: float, comment: str = "", 
                       comment_to: str = "", subtractfeefromamount: bool = False) -> str:
        """
        Send an amount to a given address.
        
        Args:
            address: The Emercoin address to send to
            amount: The amount in EMC
            comment: A comment used to store what the transaction is for
            comment_to: A comment to store the name of the person or organization to which you're sending
            subtractfeefromamount: The fee will be deducted from the amount being sent
            
        Returns:
            str: The transaction id
        """
        params = [address, amount]
        if comment or comment_to or subtractfeefromamount:
            params.append(comment)
        if comment_to or subtractfeefromamount:
            params.append(comment_to)
        if subtractfeefromamount:
            params.append(subtractfeefromamount)
        return self.call('sendtoaddress', params)
    
    # NVS (Name-Value Storage) methods specific to Emercoin
    
    def name_new(self, name: str, value: str, days: int) -> str:
        """
        Create a new name-value pair in Emercoin's NVS.
        
        Args:
            name: Name to register (with prefix, e.g. 'dns:example.com')
            value: Value to store
            days: Number of days to keep the name registered
            
        Returns:
            str: Transaction ID
        """
        return self.call('name_new', [name, value, days])
    
    def name_update(self, name: str, value: str, days: int = 0) -> str:
        """
        Update an existing name-value pair in Emercoin's NVS.
        
        Args:
            name: Name to update
            value: New value to store
            days: Additional days to keep the name registered
            
        Returns:
            str: Transaction ID
        """
        return self.call('name_update', [name, value, days])
    
    def name_show(self, name: str) -> Dict[str, Any]:
        """
        Show the value of a name in Emercoin's NVS.
        
        Args:
            name: Name to look up
            
        Returns:
            dict: Information about the name
        """
        return self.call('name_show', [name])
    
    def name_history(self, name: str) -> List[Dict[str, Any]]:
        """
        Show the history of a name in Emercoin's NVS.
        
        Args:
            name: Name to look up
            
        Returns:
            list: History of the name
        """
        return self.call('name_history', [name])
    
    def name_filter(self, prefix: str = "", regex: str = "", max_results: int = 0) -> List[Dict[str, Any]]:
        """
        List names in Emercoin's NVS that match the given criteria.
        
        Args:
            prefix: Filter by prefix (e.g. 'dns:')
            regex: Filter by regular expression
            max_results: Maximum number of results to return (0 = unlimited)
            
        Returns:
            list: Matching names and their values
        """
        return self.call('name_filter', [prefix, regex, max_results])