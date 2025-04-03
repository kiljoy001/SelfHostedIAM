import logging
import os
from typing import Dict, Any, Optional

from helper.base_messenger import BaseMessageHandler
from emercoin.emercoin_message import (
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
    EmercoinNameUpdateResponseMessage,
    register_message_types
)

# Module-level logger for tests to patch
logger = logging.getLogger("EmercoinHandler")

class SecurityError(Exception):
    """Exception raised for security-related errors with message verification"""
    pass

class EmercoinMessageHandler(BaseMessageHandler):
    """Handler for Emercoin blockchain operations via RabbitMQ"""
    
    def __init__(
        self,
        emercoin_service,
        auth_service=None,
        host: str = None,
        secret_key: str = None,
        exchange: str = "app_events"
    ):
        """Initialize EmercoinMessageHandler with dependencies"""
        super().__init__(host=host, secret_key=secret_key, exchange=exchange)
        
        # Register message types
        register_message_types()
        
        # Store service references
        self.emercoin_service = emercoin_service
        self.auth_service = auth_service
        
        # Queue names
        self.request_queue = 'emercoin_requests'
        self.response_queue = 'emercoin_responses'
        
        # Declare queues if channel exists
        if self.channel:
            self.channel.queue_declare(queue=self.request_queue, durable=True)
            self.channel.queue_declare(queue=self.response_queue, durable=True)
    
    def start(self):
        """Start processing Emercoin messages"""
        if not self.channel:
            logger.error("Cannot start: No RabbitMQ channel available")
            return False
            
        logger.info("Starting Emercoin message handler")
        
        # Subscribe to request queue
        self.subscribe(
            routing_key="emercoin.request.*",
            queue_name=self.request_queue,
            callback=self._process_message
        )
        
        # Start consuming messages
        return self.start_consuming(non_blocking=True)
    
    def _process_message(self, message_data: dict):
        """Process received message"""
        from helper.message import MessageFactory
        
        try:
            # Create message from data
            message = MessageFactory.create_from_dict(message_data)
            
            if not isinstance(message, EmercoinBaseMessage):
                logger.warning(f"Received non-Emercoin message: {message.MESSAGE_TYPE}")
                return
            
            # Process the message based on type
            response = self._handle_message(message)
            
            # Send response
            if response:
                self.publish("emercoin.response", response.to_dict())
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
            # Try to send error response if we have a message ID
            try:
                if 'id' in message_data:
                    error_response = {
                        "message_type": "response",
                        "correlation_id": message_data["id"],
                        "success": False,
                        "error": str(e)
                    }
                    self.publish("emercoin.response", error_response)
            except Exception as send_error:
                logger.error(f"Error sending error response: {send_error}")
    
    def _handle_message(self, message: EmercoinBaseMessage):
        """Handle specific message types"""
        if isinstance(message, EmercoinInfoRequestMessage):
            return self._handle_info_request(message)
        elif isinstance(message, EmercoinNameShowRequestMessage):
            return self._handle_name_show(message)
        elif isinstance(message, EmercoinNameHistoryRequestMessage):
            return self._handle_name_history(message)
        elif isinstance(message, EmercoinNameFilterRequestMessage):
            return self._handle_name_filter(message)
        elif isinstance(message, EmercoinNameNewRequestMessage):
            return self._handle_name_new(message)
        elif isinstance(message, EmercoinNameUpdateRequestMessage):
            return self._handle_name_update(message)
        else:
            logger.warning(f"Unknown message type: {message.MESSAGE_TYPE}")
            raise ValueError(f"Unsupported message type: {message.MESSAGE_TYPE}")
    
    def _handle_info_request(self, message: EmercoinInfoRequestMessage) -> EmercoinInfoResponseMessage:
        """Handle getinfo request"""
        try:
            info = self.emercoin_service.get_blockchain_info()
            return EmercoinInfoResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                info=info
            )
        except Exception as e:
            return EmercoinInfoResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                error={"code": -1000, "message": str(e)}
            )
    
    def _handle_name_show(self, message: EmercoinNameShowRequestMessage) -> EmercoinNameShowResponseMessage:
        """Handle name_show request"""
        try:
            record = self.emercoin_service.name_show(message.name)
            return EmercoinNameShowResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                record=record
            )
        except Exception as e:
            return EmercoinNameShowResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                error={"code": -1000, "message": str(e)}
            )
    
    def _handle_name_history(self, message: EmercoinNameHistoryRequestMessage) -> EmercoinNameHistoryResponseMessage:
        """Handle name_history request"""
        try:
            records = self.emercoin_service.name_history(message.name)
            return EmercoinNameHistoryResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                records=records
            )
        except Exception as e:
            return EmercoinNameHistoryResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                error={"code": -1000, "message": str(e)}
            )
    
    def _handle_name_filter(self, message: EmercoinNameFilterRequestMessage) -> EmercoinNameFilterResponseMessage:
        """Handle name_filter request"""
        try:
            records = self.emercoin_service.name_filter(message.pattern)
            return EmercoinNameFilterResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                records=records
            )
        except Exception as e:
            return EmercoinNameFilterResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                error={"code": -1000, "message": str(e)}
            )
    
    def _handle_name_new(self, message: EmercoinNameNewRequestMessage) -> EmercoinNameNewResponseMessage:
        """Handle name_new request - requires authentication"""
        try:
            # Verify authentication if available
            if self.auth_service and message.auth_token:
                if not self.auth_service.verify_token(message.auth_token, message.user_id, "write"):
                    raise SecurityError("Unauthorized access or invalid token")
            elif self.auth_service:
                raise SecurityError("Missing authentication token for write operation")
            
            # Process request
            days = message.options.get("days", 30)
            txid = self.emercoin_service.name_new(message.name, message.value, days)
            
            return EmercoinNameNewResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                txid=txid
            )
        except Exception as e:
            return EmercoinNameNewResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                error={"code": -1000, "message": str(e)}
            )
    
    def _handle_name_update(self, message: EmercoinNameUpdateRequestMessage) -> EmercoinNameUpdateResponseMessage:
        """Handle name_update request - requires authentication"""
        try:
            # Verify authentication if available
            if self.auth_service and message.auth_token:
                if not self.auth_service.verify_token(message.auth_token, message.user_id, "write"):
                    raise SecurityError("Unauthorized access or invalid token")
            elif self.auth_service:
                raise SecurityError("Missing authentication token for write operation")
            
            # Process request
            days = message.options.get("days", 30)
            txid = self.emercoin_service.name_update(message.name, message.value, days)
            
            return EmercoinNameUpdateResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                txid=txid
            )
        except Exception as e:
            return EmercoinNameUpdateResponseMessage(
                user_id=message.user_id,
                correlation_id=message.id,
                error={"code": -1000, "message": str(e)}
            )