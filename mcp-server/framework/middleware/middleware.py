import time
from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware
from ..core.context import set_request_context, setup_correlation_id
from ..core.config import get_correlation_id_name
from ..core.utils import get_app_logger


class HeaderCaptureMiddleware(BaseHTTPMiddleware):
    """
    Middleware to capture request headers and set up correlation ID context.
    
    This middleware ensures that each request gets a unique correlation ID
    that persists throughout the request lifecycle.
    
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Process the request and set up correlation ID context.
        
        Args:
            request: The incoming HTTP request
            call_next: The next middleware or route handler
            
        Returns:
            The response from the next handler
        """
        headers = dict(request.headers)
        
        # Setup correlation ID from headers or generate new one
        correlation_id = setup_correlation_id(headers)
        
        # Create comprehensive request context
        context = {
            get_correlation_id_name(): correlation_id,
            'method': request.method,
            'url': str(request.url),
            'headers': headers,
            'client': request.client.host if request.client else None,
            'timestamp': time.time(),
        }
        
        # Set the request context for this request
        set_request_context(context)
        
        try:
            # Process the request
            response = await call_next(request)
            return response
            
        except Exception as e:
            # For SSE endpoints, skip error logging to avoid potential ASGI conflicts
            # if self._is_sse_endpoint(request):
            #     raise
                
            # Log error with correlation ID (only for unexpected errors on regular endpoints)
            logger = get_app_logger()
            if logger:
                processing_time = time.time() - context['timestamp']
                logger.error(f"[REQ] Request failed after {processing_time:.3f}s: {str(e)}")
            raise
