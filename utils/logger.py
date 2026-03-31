"""
CloudWatch-compatible JSON logging configuration.

Provides structured JSON logging that CloudWatch can parse and display
with expandable/collapsible fields for easier debugging and monitoring.
"""

import os
import json
import logging


class CloudWatchJSONFormatter(logging.Formatter):
    """
    JSON formatter for CloudWatch Logs.
    Outputs structured JSON that CloudWatch can parse and display as expandable fields.
    
    Features:
    - Structured JSON output with timestamp, level, logger, message, etc.
    - Automatic exception stack trace inclusion
    - Support for custom fields (worker_id, visit_id, image_type, duration_ms, etc.)
    - CloudWatch-compatible format for log insights and filtering
    """
    
    def format(self, record):
        """
        Format log record as JSON.
        
        Args:
            record: LogRecord instance
            
        Returns:
            JSON string with log data
        """
        message = record.getMessage()

        # Detect JSON strings and parse back to dict to avoid double-encoding
        if message and ((message.startswith('{') and message.endswith('}')) or
                        (message.startswith('[') and message.endswith(']'))):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                pass  # Keep as string if not valid JSON

        log_data = {
            "timestamp": self.formatTime(record, datefmt='%Y-%m-%d %H:%M:%S.%f')[:-3],
            "level": record.levelname,
            "logger": record.name,
            "thread": record.threadName,
            "message": message,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add custom fields from record
        custom_fields = [
            'worker_id', 'visit_id', 'image_type', 'duration_ms',
            'shop_id', 'upload_id', 's3_key', 'receipt_handle',
            'model_name', 'confidence', 'detection_count'
        ]
        
        for field in custom_fields:
            if hasattr(record, field):
                log_data[field] = getattr(record, field)
        
        return json.dumps(log_data)


def setup_cloudwatch_logging(log_level: str = None):
    """
    Configure logging with CloudWatch JSON formatter.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                  Defaults to LOG_LEVEL env var or INFO
                  
    Returns:
        Configured logger instance
    """
    if log_level is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    
    # Create handler with JSON formatter
    handler = logging.StreamHandler()
    handler.setFormatter(CloudWatchJSONFormatter())
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level),
        handlers=[handler],
        force=True  # Override any existing configuration
    )
    
    # Silence noisy third-party libraries
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('s3transfer').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)


def get_logger(name: str = None):
    """
    Get a logger instance.
    
    Args:
        name: Logger name (defaults to caller's module name)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name or __name__)
