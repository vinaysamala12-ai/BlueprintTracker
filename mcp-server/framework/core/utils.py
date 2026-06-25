"""Utility functions and logging setup."""

import logging
import sys
from typing import Any, Dict, Optional
from datetime import datetime
from pathlib import Path

from .config import app_config


# Custom exceptions
class MCPServerError(Exception):
    """Base exception for MCP server errors."""
    pass


class ToolExecutionError(MCPServerError):
    """Exception raised when a tool execution fails."""
    pass


class APIError(MCPServerError):
    """Exception raised when an external API call fails."""
    pass


class ValidationError(MCPServerError):
    """Exception raised when input validation fails."""
    pass


class DetailedCorrelationIdFormatter(logging.Formatter):
    """
    Custom formatter that includes correlation_id, file name, 
    line number, and function name in all log messages.
    
    Note: The correlation_id is now injected by CorrelationIdFilter,
    so this formatter just needs to format the message.
    """
    
    def __init__(self, fmt=None, include_location=True, include_function=True):
        self.include_location = include_location
        self.include_function = include_function
        
        # Build the format string based on options
        base_format = "%(asctime)s - %(name)s - %(levelname)s"
        
        if include_location and include_function:
            format_string = f"{base_format} - %(filename)s:%(lineno)d:%(funcName)s() - [%(correlation_id)s] %(message)s"
        elif include_location:
            format_string = f"{base_format} - %(filename)s:%(lineno)d - [%(correlation_id)s] %(message)s"
        elif include_function:
            format_string = f"{base_format} - %(funcName)s() - [%(correlation_id)s] %(message)s"
        else:
            format_string = f"{base_format} - [%(correlation_id)s] %(message)s"
        
        super().__init__(format_string)


# Logging setup
def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    include_location: bool = True,
    include_function: bool = True
) -> logging.Logger:
    """
    Set up logging configuration with enhanced correlation_id and location tracking.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
        log_format: Optional custom log format (ignored when using enhanced formatter)
        include_location: Whether to include file name and line number
        include_function: Whether to include function name
        
    Returns:
        Configured logger instance
    """
    # Import the filter here to avoid circular imports
    from .logging_filter import CorrelationIdFilter
    
    # Convert log level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure root logger to use the same level from .env
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Configure Uvicorn loggers to use the same level from .env
    uvicorn_loggers = [
        "uvicorn",
        "uvicorn.access", 
        "uvicorn.error",
        "uvicorn.asgi"
    ]
    
    for logger_name in uvicorn_loggers:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.setLevel(numeric_level)
    
    # Create main application logger
    logger = logging.getLogger("mcp_server")
    logger.setLevel(numeric_level)
    
    # Prevent propagation to root logger to avoid duplicate messages
    logger.propagate = False
    
    # Remove existing handlers and filters
    logger.handlers.clear()
    logger.filters.clear()
    
    # Add correlation ID filter to inject correlation_id into all log records
    correlation_filter = CorrelationIdFilter()
    logger.addFilter(correlation_filter)
    
    # Create enhanced formatter
    enhanced_formatter = DetailedCorrelationIdFormatter(
        include_location=include_location,
        include_function=include_function
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(enhanced_formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(enhanced_formatter)
        logger.addHandler(file_handler)
    
    # Apply LOG_LEVELS overrides last so they win over root/uvicorn defaults
    # (e.g. silence noisy third-party loggers while keeping LOG_LEVEL=DEBUG).
    # Warn here (not in Config) so messages flow through the configured
    # handler/formatter rather than Python's bare `lastResort` stderr.
    for err in app_config.log_levels_errors:
        logger.warning("Invalid LOG_LEVELS entry %s; skipping", err)
    for name, level in app_config.log_levels.items():
        logging.getLogger(name).setLevel(level)

    # Add a debug message to verify the logger is working
    logger.debug(f"Enhanced logger configured with level: {log_level.upper()} (numeric: {numeric_level})")
    logger.debug(f"Root logger and Uvicorn loggers configured to use level: {log_level.upper()}")

    return logger


# Server start time for uptime calculation
SERVER_START_TIME = datetime.now()

# Application-level globals for config and logger
_app_config: Dict[str, Any] = {}
_app_logger: Optional[logging.Logger] = None


def get_uptime_seconds() -> float:
    """Calculate server uptime in seconds."""
    return (datetime.now() - SERVER_START_TIME).total_seconds()


def get_app_config() -> Dict[str, Any]:
    """Get the application-level configuration."""
    return _app_config


def set_app_config(config: Dict[str, Any]):
    """Set the application-level configuration."""
    global _app_config
    _app_config = config

def get_app_logger() -> logging.Logger:
    """Get the application-level logger."""
    return _app_logger

def set_app_logger(logger: logging.Logger):
    """Set the application-level logger."""
    global _app_logger
    _app_logger = logger

def get_project_metadata() -> Dict[str, Any]:
    """
    Read project metadata from pyproject.toml.

    Returns:
        A dictionary containing the project metadata.
    """
    try:
        # Import tomllib locally to avoid loading it unless needed
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
            
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            pyproject_data = tomllib.load(f)
        return pyproject_data.get("project", {})
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}
