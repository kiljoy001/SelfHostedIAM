# helper/message.py
import uuid
import time
import json
from typing import Dict, Any, Optional, List, ClassVar, Type
from dataclasses import dataclass, field, asdict

@dataclass
class BaseMessage:
    """Base class for all message types in the system"""
    
    # Message type identifier (to be overridden by subclasses)
    MESSAGE_TYPE: ClassVar[str] = "base"
    
    # Message ID for tracking
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Timestamp for when the message was created
    timestamp: float = field(default_factory=time.time)
    
    # Source service that created the message
    source: str = "unknown"
    
    # Optional correlation ID for request/response tracking
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary for serialization"""
        result = asdict(self)
        result["message_type"] = self.MESSAGE_TYPE
        return result
    
    def to_json(self) -> str:
        """Convert message to JSON string"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseMessage':
        """Create message instance from dictionary"""
        # Make a copy and filter out message_type
        data_copy = data.copy()
        data_copy.pop("message_type", None)
        
        # Create instance - ID will be preserved if provided
        return cls(**data_copy)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'BaseMessage':
        """Create message instance from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)


# Command message for service operations
@dataclass
class CommandMessage(BaseMessage):
    """Command to execute a specific operation"""
    MESSAGE_TYPE: ClassVar[str] = "command"
    
    # Command to execute
    command: str = ""
    
    # Command arguments
    args: List[Any] = field(default_factory=list)
    
    # Target service to execute the command
    target: str = ""


# Response message for operation results
@dataclass
class ResponseMessage(BaseMessage):
    """Response with operation results"""
    MESSAGE_TYPE: ClassVar[str] = "response"
    
    # Operation success flag
    success: bool = False
    
    # Result data (if successful)
    result: Dict[str, Any] = field(default_factory=dict)
    
    # Error information (if unsuccessful)
    error: Optional[str] = None


# Event message for system events
@dataclass
class EventMessage(BaseMessage):
    """Event notification message"""
    MESSAGE_TYPE: ClassVar[str] = "event"
    
    # Event type
    event_type: str = ""
    
    # Event data
    data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StateChangeMessage(EventMessage):
    """Message for state change notifications"""
    MESSAGE_TYPE: ClassVar[str] = "state_change"
    
    old_state: str = ""
    new_state: str = ""
    service: str = ""

# Factory for creating message objects from data
class MessageFactory:
    """Factory for creating message objects from data"""
    
    _message_types: Dict[str, Type[BaseMessage]] = {
        "base": BaseMessage,
        "command": CommandMessage,
        "response": ResponseMessage,
        "event": EventMessage
    }
    
    @classmethod
    def register_type(cls, message_type: str, message_class: Type[BaseMessage]) -> None:
        """Register a new message type"""
        cls._message_types[message_type] = message_class
    
    @classmethod
    def create_from_dict(cls, data: Dict[str, Any]) -> BaseMessage:
        """Create appropriate message object from dictionary"""
        if not data:
            raise ValueError("Cannot create message from empty dictionary")

        message_type = data.get("message_type")

        if not message_type:
            raise ValueError("Missing message_type in data")

        if message_type not in cls._message_types:
            raise ValueError(f"Unknown message type: {message_type}")

        message_class = cls._message_types[message_type]

        try:
            return message_class.from_dict(data)
        except TypeError as e:
            # Convert TypeError from initialization to ValueError for consistency
            raise ValueError(f"Invalid message data: {str(e)}")
    
    @classmethod
    def create_from_json(cls, json_str: str) -> BaseMessage:
        """Create appropriate message object from JSON string"""
        data = json.loads(json_str)
        return cls.create_from_dict(data)