"""Request logging decorator for MCP server."""

import json
import logging
import time
from typing import Any, Dict, Optional
from functools import wraps

from ..core.context import get_request_context, set_request_context
from ..core.mcp_logging import emit_lifecycle_notification
from ..core.utils import get_app_logger
from ..core.config import get_mcp_master_api_key_name


def _get_token_claims_for_logging() -> Dict[str, str]:
    """Return safe token claims for logging when a validated token exists in context."""
    context = get_request_context()
    if not context or not context.get("authorization_token"):
        return {}

    claims: Dict[str, str] = {}
    for claim_name in ("coid", "email", "uoid"):
        claim_value = context.get(claim_name)
        if claim_value:
            claims[claim_name] = str(claim_value)

    issuer_environment = context.get("issuer_environment")
    if issuer_environment:
        claims["issuer_code"] = str(issuer_environment)
    return claims


def _format_token_claims_suffix(claims: Dict[str, str]) -> str:
    """Format non-PII routing context as a compact suffix for INFO-level log lines.

    User-identifying claims (``email``, ``uoid``) are deliberately excluded:
    INFO is the production default and these lines log on every successful
    call. Only company/environment routing context is emitted here; the full
    claim set remains available in the DEBUG request/response dumps.
    """
    if not claims:
        return ""
    ordered = [
        f"{name}={claims[name]}"
        for name in ("coid", "issuer_code")
        if name in claims
    ]
    if not ordered:
        return ""
    return f" [{' '.join(ordered)}]"

def log_request_details(
    method: str = "UNKNOWN",
    path: str = "UNKNOWN",
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[str] = None
):
    """
    Log detailed request information for debugging.
    
    Args:
        method: HTTP method
        path: Request path
        headers: Request headers
        params: Request parameters
        body: Request body
    """
    logger = get_app_logger()
    # Note: correlation_id is now automatically added by the enhanced formatter
    
    logger.debug("[REQ] === INCOMING REQUEST ===")
    logger.debug(f"[REQ] Method: {method}")
    logger.debug(f"[REQ] Path: {path}")

    token_claims = _get_token_claims_for_logging()
    if token_claims:
        logger.debug(f"[REQ] Token claims: {json.dumps(token_claims, separators=(',', ':'))}")
    
    # Log headers (sanitize sensitive information)
    if headers:
        sanitized_headers = {}
        api_key_header_name = get_mcp_master_api_key_name().lower()
        for key, value in headers.items():
            if key.lower() in ['authorization', api_key_header_name, 'cookie']:
                # Show only the last 4 characters for security
                sanitized_headers[key] = f"***{value[-4:] if len(value) > 4 else '***'}"
            else:
                sanitized_headers[key] = value
        logger.debug(f"[REQ] Headers: {json.dumps(sanitized_headers, indent=2)}")
    else:
        logger.debug("[REQ] Headers: None")
    
    # Log parameters
    if params:
        # Sanitize API keys in parameters
        logger.debug(f"[REQ] Parameters: {json.dumps(params, indent=2)}")
    else:
        logger.debug("[REQ] Parameters: None")
    
    # Log body (truncated if too long)
    if body:
        if len(body) > 1000:
            truncated_body = body[:1000] + "... (truncated)"
        else:
            truncated_body = body
        logger.debug(f"[REQ] Body: {truncated_body}")
    else:
        logger.debug("[REQ] Body: None")
    
    logger.debug("[REQ] === END REQUEST LOG ===")

def log_response_details(
    response: Any,
    status_code: int = 200,
    processing_time: Optional[float] = None
):
    """
    Log response details.
    
    Args:
        response: Response data
        status_code: HTTP status code
        processing_time: Time taken to process request
    """
    logger = get_app_logger()
    # Note: correlation_id is now automatically added by the enhanced formatter
    
    logger.debug("[RES] === RESPONSE ===")
    logger.debug(f"[RES] Status: {status_code}")

    token_claims = _get_token_claims_for_logging()
    if token_claims:
        logger.debug(f"[RES] Token claims: {json.dumps(token_claims, separators=(',', ':'))}")
    
    if processing_time:
        logger.debug(f"[RES] Processing time: {processing_time:.3f}s")
    
    # Log response (truncated if too long)
    if response:
        response_str = json.dumps(response, indent=2, default=str)
        if len(response_str) > 1000:
            truncated_response = response_str[:1000] + "... (truncated)"
        else:
            truncated_response = response_str
        logger.debug(f"[RES] Response: {truncated_response}")
    else:
        logger.debug("[RES] Response: None")
    
    logger.debug("[RES] === END RESPONSE LOG ===")

def log_requests(func):
    """
    Decorator to add request logging to MCP tool functions.
    
    This decorator logs the incoming request details before processing
    and the response details after processing. It optimizes performance
    by using different logging levels based on the current log level.
    """
    @wraps(func)
    async def wrapper(params):
        
        start_time = time.time()
        logger = get_app_logger()
        
        # Check if we should use detailed logging (DEBUG level)
        is_debug_logging = logger.isEnabledFor(logging.DEBUG)
        
        http_context = get_request_context()

        # Log based on level
        if is_debug_logging:
            # Full detailed logging for DEBUG level
            log_request_details(
                method="MCP_TOOL",
                path=f"/tool/{func.__name__}",
                headers=dict(http_context.get('headers', {})) if http_context else {},
                params=params.model_dump() if hasattr(params, 'model_dump') else {"raw": str(params)}
            )
        else:
            # Simplified logging for INFO and above - correlation_id added automatically by formatter
            logger.info(f"[TOOL] Executing tool: {func.__name__}")

        # Per-call diagnostic for the MCP client. Tagged ``logger="tool"`` so
        # AIS can split tool / prompt / resource notifications by source.
        await emit_lifecycle_notification(
            kind="tool", name=func.__name__, phase="start"
        )

        try:
            # Call the original function
            result = await func(params)

            # Log successful response
            processing_time = time.time() - start_time
            elapsed_ms = round(processing_time * 1000, 3)

            if is_debug_logging:
                # Full detailed response logging for DEBUG level
                log_response_details(
                    response=result,
                    status_code=200,
                    processing_time=processing_time
                )
            else:
                # Simplified success logging for INFO and above - correlation_id added automatically by formatter
                token_claims_suffix = _format_token_claims_suffix(_get_token_claims_for_logging())
                logger.info(
                    f"[TOOL] Tool {func.__name__} completed successfully in {processing_time:.3f}s{token_claims_suffix}"
                )

            await emit_lifecycle_notification(
                kind="tool",
                name=func.__name__,
                phase="end",
                status="ok",
                elapsed_ms=elapsed_ms,
            )

            return result

        except Exception as e:
            # Log timing and basic error info, let handle_exceptions decorator handle detailed error logging
            processing_time = time.time() - start_time

            if is_debug_logging:
                # Full detailed error logging for DEBUG level
                from starlette.exceptions import HTTPException as _HTTPException
                status_code = e.status_code if isinstance(e, _HTTPException) else 500
                error_response = {
                    "error": str(e),
                    "type": type(e).__name__
                }
                log_response_details(
                    response=error_response,
                    status_code=status_code,
                    processing_time=processing_time
                )
            else:
                # Simplified timing info for INFO and above - correlation_id added automatically by formatter
                token_claims_suffix = _format_token_claims_suffix(_get_token_claims_for_logging())
                logger.info(f"[TOOL] Tool {func.__name__} processing time: {processing_time:.3f}s{token_claims_suffix}")

            # The ERROR-level notifications/message is emitted by
            # ``handle_exceptions`` (which has the structured payload). Just
            # re-raise here so that decorator can stamp it.
            raise
    
    return wrapper
