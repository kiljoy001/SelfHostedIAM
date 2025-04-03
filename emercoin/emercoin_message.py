import uuid
import time
from typing import Dict, Any, Optional, List, ClassVar, Type
from dataclasses import dataclass, field, asdict
from helper.message import BaseMessage, MessageFactory


@dataclass
class EmercoinBaseMessage(BaseMessage):
    """Base class for all Emercoin-related messages"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_base"
    
    # Target user ID for this operation
    user_id: Optional[str] = None


@dataclass
class EmercoinInfoRequestMessage(EmercoinBaseMessage):
    """Request for Emercoin blockchain information"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_info_request"


@dataclass
class EmercoinInfoResponseMessage(EmercoinBaseMessage):
    """Response with Emercoin blockchain information"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_info_response"
    
    # Blockchain information
    info: Dict[str, Any] = field(default_factory=dict)
    
    # Error information (if unsuccessful)
    error: Optional[Dict[str, Any]] = None


@dataclass
class EmercoinNameShowRequestMessage(EmercoinBaseMessage):
    """Request to show a name record"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_name_show_request"
    
    # Name to lookup
    name: str = ""


@dataclass
class EmercoinNameShowResponseMessage(EmercoinBaseMessage):
    """Response with name record information"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_name_show_response"
    
    # Name record information
    record: Optional[Dict[str, Any]] = None
    
    # Error information (if unsuccessful)
    error: Optional[Dict[str, Any]] = None


@dataclass
class EmercoinNameHistoryRequestMessage(EmercoinBaseMessage):
    """Request for name history"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_name_history_request"
    
    # Name to get history for
    name: str = ""


@dataclass
class EmercoinNameHistoryResponseMessage(EmercoinBaseMessage):
    """Response with name history information"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_name_history_response"
    
    # Name history records
    records: List[Dict[str, Any]] = field(default_factory=list)
    
    # Error information (if unsuccessful)
    error: Optional[Dict[str, Any]] = None


@dataclass
class EmercoinNameFilterRequestMessage(EmercoinBaseMessage):
    """Request to filter names by pattern"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_name_filter_request"
    
    # Pattern to filter names
    pattern: str = ""


@dataclass
class EmercoinNameFilterResponseMessage(EmercoinBaseMessage):
    """Response with filtered name records"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_name_filter_response"
    
    # Matching name records
    records: List[Dict[str, Any]] = field(default_factory=list)
    
    # Error information (if unsuccessful)
    error: Optional[Dict[str, Any]] = None


@dataclass
class EmercoinNameNewRequestMessage(EmercoinBaseMessage):
    """Request to create a new name"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_name_new_request"
    
    # Name to create
    name: str = ""
    
    # Value to associate with the name
    value: str = ""
    
    # Options for name creation (e.g. days)
    options: Dict[str, Any] = field(default_factory=dict)
    
    # Authentication token for verification
    auth_token: Optional[str] = None


@dataclass
class EmercoinNameNewResponseMessage(EmercoinBaseMessage):
    """Response for name creation operation"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_name_new_response"
    
    # Transaction ID of the operation
    txid: Optional[str] = None
    
    # Error information (if unsuccessful)
    error: Optional[Dict[str, Any]] = None


@dataclass
class EmercoinNameUpdateRequestMessage(EmercoinBaseMessage):
    """Request to update an existing name"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_name_update_request"
    
    # Name to update
    name: str = ""
    
    # New value to associate with the name
    value: str = ""
    
    # Options for name update (e.g. days)
    options: Dict[str, Any] = field(default_factory=dict)
    
    # Authentication token for verification
    auth_token: Optional[str] = None


@dataclass
class EmercoinNameUpdateResponseMessage(EmercoinBaseMessage):
    """Response for name update operation"""
    MESSAGE_TYPE: ClassVar[str] = "emercoin_name_update_response"
    
    # Transaction ID of the operation
    txid: Optional[str] = None
    
    # Error information (if unsuccessful)
    error: Optional[Dict[str, Any]] = None


# Register all message types with the factory
def register_message_types():
    """Register all Emercoin message types with the MessageFactory"""
    message_types = [
        EmercoinBaseMessage,
        EmercoinInfoRequestMessage,
        EmercoinInfoResponseMessage,
        EmercoinNameShowRequestMessage,
        EmercoinNameShowResponseMessage,
        EmercoinNameHistoryRequestMessage,
        EmercoinNameHistoryResponseMessage,
        EmercoinNameFilterRequestMessage,
        EmercoinNameFilterResponseMessage,
        EmercoinNameNewRequestMessage,
        EmercoinNameNewResponseMessage,
        EmercoinNameUpdateRequestMessage,
        EmercoinNameUpdateResponseMessage
    ]
    
    for msg_type in message_types:
        MessageFactory.register_type(msg_type.MESSAGE_TYPE, msg_type)