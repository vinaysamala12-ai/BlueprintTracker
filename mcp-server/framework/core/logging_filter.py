"""Logging filter for correlation ID injection."""

import logging
from typing import Optional
from .context import get_correlation_id


class CorrelationIdFilter(logging.Filter):
    """
    Logging filter that injects correlation ID into all log records.
    
    This filter ensures that every log record has a correlation_id attribute,
    either from the current request context or a default value.
    """
    
    def __init__(self, default_correlation_id: str = "no-correlation"):
        """
        Initialize the correlation ID filter.
        
        Args:
            default_correlation_id: Default value when no correlation ID is available
        """
        super().__init__()
        self.default_correlation_id = default_correlation_id
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add correlation ID to the log record.
        
        Args:
            record: The log record to process
            
        Returns:
            bool: Always True to allow the record to be processed
        """
        # Try to get correlation ID from context
        try:
            correlation_id = get_correlation_id()
        except Exception:
            # Fallback if context is not available
            correlation_id = None
        
        # Set correlation_id attribute on the record
        record.correlation_id = correlation_id or self.default_correlation_id
        
        return True
