import re
import logging
from typing import Any, Dict, List, Optional, Union
from emercoin.emercoin_connection_handler import EmercoinConnection, ConnectionError, AuthError, RPCError

# Configure logging
logger = logging.getLogger(__name__)

class EmercoinService:
    """
    Service for interacting with the Emercoin blockchain.
    
    This service provides high-level methods for common Emercoin operations,
    particularly those related to the name-value storage system.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Emercoin service.
        
        Args:
            config: Configuration dictionary for the Emercoin connection
        """
        self.config = config
        self.connection = EmercoinConnection(config)
        logger.info("Emercoin service initialized")
        
    def reconnect(self) -> None:
        """
        Reinitialize the connection to the Emercoin node.
        
        This can be useful after configuration changes or to recover from
        persistent connection issues.
        """
        logger.info("Reconnecting to Emercoin node")
        self.connection = EmercoinConnection(self.config)
        
    def get_blockchain_info(self) -> Dict[str, Any]:
        """
        Get general information about the Emercoin blockchain and node.
        
        Returns:
            Dictionary containing blockchain information
            
        Raises:
            ConnectionError: If connection to the node fails
            AuthError: If authentication fails
            RPCError: If the RPC call returns an error
        """
        try:
            logger.debug("Getting blockchain info")
            return self.connection.call('getinfo')
        except ConnectionError as e:
            logger.error(f"Connection error while getting blockchain info: {str(e)}")
            # Add contextual information
            raise ConnectionError(f"Failed to connect to Emercoin node: {str(e)}")
            
    def name_show(self, name: str) -> Dict[str, Any]:
        """
        Show the current value of a name in the Emercoin NVS.
        
        Args:
            name: The name to look up (e.g., "dns:example.com")
            
        Returns:
            Dictionary containing name record information
            
        Raises:
            ValueError: If the name is invalid
            ConnectionError: If connection to the node fails
            AuthError: If authentication fails
            RPCError: If the name doesn't exist or other error occurs
        """
        self._validate_name_required(name)
        
        if not self.validate_name(name):
            logger.warning(f"Invalid name format: {name}")
            raise ValueError(f"Invalid name format: {name}")
        
        logger.debug(f"Looking up name: {name}")
        try:
            return self.connection.call('name_show', [name])
        except ConnectionError as e:
            logger.error(f"Connection error while looking up name {name}: {str(e)}")
            raise ConnectionError(f"Failed to connect to Emercoin node: {str(e)}")
        except RPCError as e:
            # Add more context if the name wasn't found
            if e.code == -4:  # Name not found error code
                logger.info(f"Name not found: {name}")
                raise RPCError(e.code, f"Name '{name}' not found: {e.message}")
            logger.error(f"RPC error while looking up name {name}: {str(e)}")
            raise
            
    def name_history(self, name: str) -> List[Dict[str, Any]]:
        """
        Show the history of a name in the Emercoin NVS.
        
        Args:
            name: The name to look up (e.g., "dns:example.com")
            
        Returns:
            List of dictionaries containing historical name record information
            
        Raises:
            ValueError: If the name is invalid
            ConnectionError: If connection to the node fails
            AuthError: If authentication fails
            RPCError: If the name doesn't exist or other error occurs
        """
        self._validate_name_required(name)
        
        if not self.validate_name(name):
            logger.warning(f"Invalid name format: {name}")
            raise ValueError(f"Invalid name format: {name}")
        
        logger.debug(f"Getting history for name: {name}")
        try:
            return self.connection.call('name_history', [name])
        except ConnectionError as e:
            logger.error(f"Connection error while getting history for name {name}: {str(e)}")
            raise ConnectionError(f"Failed to connect to Emercoin node: {str(e)}")
        except RPCError as e:
            # Add more context if the name wasn't found
            if e.code == -4:  # Name not found error code
                logger.info(f"Name not found: {name}")
                raise RPCError(e.code, f"Name '{name}' not found: {e.message}")
            logger.error(f"RPC error while getting history for name {name}: {str(e)}")
            raise
            
    def name_filter(self, regex: str) -> List[Dict[str, Any]]:
        """
        List names matching a regular expression pattern.
        
        Args:
            regex: Regular expression to filter names
            
        Returns:
            List of dictionaries containing matching name records
            
        Raises:
            ConnectionError: If connection to the node fails
            AuthError: If authentication fails
            RPCError: If the RPC call returns an error
        """
        logger.debug(f"Filtering names with pattern: {regex}")
        try:
            return self.connection.call('name_filter', [regex])
        except ConnectionError as e:
            logger.error(f"Connection error while filtering names: {str(e)}")
            raise ConnectionError(f"Failed to connect to Emercoin node: {str(e)}")
        except RPCError as e:
            logger.error(f"RPC error while filtering names: {str(e)}")
            raise
            
    def name_new(self, name: str, value: str, options: Dict[str, Any] = None) -> str:
        """
        Create a new name in the Emercoin NVS.
        
        Args:
            name: The name to create (e.g., "dns:example.com")
            value: The value to associate with the name
            options: Dictionary of options (e.g., {'days': 30})
            
        Returns:
            Transaction ID of the name_new operation
            
        Raises:
            ValueError: If the name is invalid
            ConnectionError: If connection to the node fails
            AuthError: If authentication fails
            RPCError: If the RPC call returns an error (e.g., insufficient funds)
        """
        self._validate_name_required(name)
        
        if not self.validate_name(name):
            logger.warning(f"Invalid name format: {name}")
            raise ValueError(f"Invalid name format: {name}")
            
        if not options:
            options = {'days': 30}  # Default to 30 days
            
        logger.info(f"Creating new name: {name} with options: {options}")
        try:
            txid = self.connection.call('name_new', [name, value, options])
            logger.info(f"Created name {name} with transaction {txid}")
            return txid
        except ConnectionError as e:
            logger.error(f"Connection error while creating name {name}: {str(e)}")
            raise ConnectionError(f"Failed to connect to Emercoin node: {str(e)}")
        except RPCError as e:
            logger.error(f"RPC error while creating name {name}: {str(e)}")
            raise
            
    def name_update(self, name: str, value: str, options: Dict[str, Any] = None) -> str:
        """
        Update an existing name in the Emercoin NVS.
        
        Args:
            name: The name to update (e.g., "dns:example.com")
            value: The new value to associate with the name
            options: Dictionary of options (e.g., {'days': 30})
            
        Returns:
            Transaction ID of the name_update operation
            
        Raises:
            ValueError: If the name is invalid
            ConnectionError: If connection to the node fails
            AuthError: If authentication fails
            RPCError: If the RPC call returns an error (e.g., name not found)
        """
        self._validate_name_required(name)
        
        if not self.validate_name(name):
            logger.warning(f"Invalid name format: {name}")
            raise ValueError(f"Invalid name format: {name}")
            
        if not options:
            options = {'days': 30}  # Default to 30 days
            
        logger.info(f"Updating name: {name} with options: {options}")
        try:
            txid = self.connection.call('name_update', [name, value, options])
            logger.info(f"Updated name {name} with transaction {txid}")
            return txid
        except ConnectionError as e:
            logger.error(f"Connection error while updating name {name}: {str(e)}")
            raise ConnectionError(f"Failed to connect to Emercoin node: {str(e)}")
        except RPCError as e:
            # Add more context if the name wasn't found
            if e.code == -4:  # Name not found error code
                logger.info(f"Name not found for update: {name}")
                raise RPCError(e.code, f"Name '{name}' not found: {e.message}")
            logger.error(f"RPC error while updating name {name}: {str(e)}")
            raise
            
    def validate_name(self, name: str) -> bool:
        """
        Validate an Emercoin NVS name format.
        
        Args:
            name: The name to validate
            
        Returns:
            True if the name is valid, False otherwise
        """
        # Name should have a namespace prefix and value
        if not name or ':' not in name:
            return False
            
        # Split into namespace and value
        namespace, value = name.split(':', 1)
        
        # Both namespace and value should be non-empty
        if not namespace or not value:
            return False
            
        # Check overall length (maximum 255 characters)
        if len(name) > 255:
            return False
            
        # Valid namespaces (could be expanded as needed)
        valid_namespaces = ['dns', 'id', 'ssl', 'ssh', 'test', 'nx', 'dp', 'dpo']
        if namespace not in valid_namespaces and not namespace.startswith('x-'):
            logger.debug(f"Invalid namespace: {namespace}")
            return False
            
        # Additional validation for specific namespaces
        if namespace == 'dns':
            # Simple DNS validation (could be more comprehensive)
            if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-\.]{0,253}[a-zA-Z0-9])?$', value):
                return False
                
        return True
        
    def _validate_name_required(self, name: str) -> None:
        """
        Validate that a name is provided.
        
        Args:
            name: The name to validate
            
        Raises:
            ValueError: If the name is not provided
        """
        if not name:
            raise ValueError("Name is required")