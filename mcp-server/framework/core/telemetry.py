"""OpenTelemetry SDK wiring for the MCP server.

FastMCP 3.x emits spans natively via ``opentelemetry-api``. Those spans are
no-ops unless an OpenTelemetry SDK is configured — this module does that
configuration, driven by standard ``OTEL_*`` environment variables.

Design choices
--------------
* Entirely env-driven. If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset, this module
  is a no-op and the server has zero tracing overhead.
* Correlation IDs (the framework's existing per-request identifier) are
  enriched onto every started span via a ``SpanProcessor`` that reads from
  the request contextvar. This keeps the existing log output untouched while
  letting operators pivot from a correlation-id in logs to the span in a trace
  backend.
* Service name defaults to the project name from ``pyproject.toml``.

Supported env vars (standard OTel names unless noted):

* ``OTEL_EXPORTER_OTLP_ENDPOINT`` — required to enable tracing (e.g.
  ``http://localhost:4318``). Unset disables tracing entirely.
* ``OTEL_SERVICE_NAME`` — optional; defaults to the project name.
* ``OTEL_EXPORTER_OTLP_PROTOCOL`` — ``grpc`` or ``http/protobuf`` (default).
* ``OTEL_EXPORTER_OTLP_HEADERS`` — read by the OTel SDK directly.
* ``OTEL_RESOURCE_ATTRIBUTES`` — read by the OTel SDK directly.
"""

from __future__ import annotations

import atexit
import os

from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace.export import SpanExportResult, SpanExporter

from .context import get_correlation_id
from .utils import get_app_logger


_configured: bool = False
_provider = None  # opentelemetry.sdk.trace.TracerProvider when enabled
_atexit_registered: bool = False


class _CorrelationIdSpanProcessor(SpanProcessor):
    """Enrich every started span with the framework's correlation id.

    ``on_start`` fires exactly once per span, so any span started *before*
    the framework's correlation-id middleware populates the request context
    (e.g. very early transport-level spans) will not carry the attribute.
    Tool-call spans start well inside middleware and are always tagged.
    """

    def on_start(self, span, parent_context=None):
        correlation_id = get_correlation_id()
        if correlation_id:
            span.set_attribute("correlation.id", correlation_id)

    def on_end(self, span):
        pass

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


class _NoOpSpanExporter(SpanExporter):
    """Fallback exporter used when the OTLP exporter package is not installed."""

    def export(self, spans) -> SpanExportResult:
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


def _project_service_name() -> str:
    from .utils import get_project_metadata

    metadata = get_project_metadata()
    return metadata.get("name", "next-ai-mcp-server")


def setup_telemetry() -> bool:
    """Configure the OpenTelemetry SDK if an OTLP endpoint is set.

    Returns:
        ``True`` if tracing was enabled, ``False`` if this was a no-op.
    """
    global _configured, _provider, _atexit_registered

    if _configured:
        return True

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False

    # Imports are local so the module is cheap when tracing is disabled.
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service_name = os.getenv("OTEL_SERVICE_NAME", _project_service_name())
    resource = Resource.create({"service.name": service_name})

    provider = TracerProvider(resource=resource)

    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf").lower()
    try:
        if protocol == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
        exporter = OTLPSpanExporter()
    except ModuleNotFoundError as exc:
        if not (exc.name or "").startswith("opentelemetry.exporter"):
            raise
        exporter = _NoOpSpanExporter()
        logger = get_app_logger()
        if logger:
            logger.warning(
                "OTLP exporter package is not installed; tracing SDK enabled "
                "with a no-op span exporter"
            )

    # Correlation-id processor runs first so the attribute is present before
    # BatchSpanProcessor buffers the span for export.
    provider.add_span_processor(_CorrelationIdSpanProcessor())
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _provider = provider
    _configured = True

    if not _atexit_registered:
        atexit.register(shutdown_telemetry)
        _atexit_registered = True

    logger = get_app_logger()
    if logger:
        logger.info(
            f"OpenTelemetry tracing enabled — service_name={service_name!r}, "
            f"endpoint={endpoint!r}, protocol={protocol!r}"
        )
    return True


def shutdown_telemetry() -> None:
    """Flush and shut down the TracerProvider so buffered spans are exported.

    Safe to call when telemetry is disabled (no-op). Invoked via an ``atexit``
    handler registered by ``setup_telemetry``; callers can also invoke it
    directly from a server lifespan if they prefer deterministic shutdown.
    """
    global _configured, _provider

    provider = _provider
    if provider is None:
        return

    try:
        provider.shutdown()
    except Exception:
        # Shutdown errors from the SDK must not mask an in-progress server
        # shutdown — log and move on.
        logger = get_app_logger()
        if logger:
            logger.warning("OpenTelemetry TracerProvider shutdown raised", exc_info=True)
    finally:
        _provider = None
        _configured = False


def is_telemetry_enabled() -> bool:
    return _configured


def _reset_for_tests() -> None:
    """Test-only hook: clear module state and the global TracerProvider.

    OTel's ``trace.set_tracer_provider`` warns when the provider is replaced;
    tests that toggle telemetry on and off must reset the global so each case
    starts from a clean slate.
    """
    global _configured, _provider

    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception:
            pass
    _provider = None
    _configured = False

    # Reset opentelemetry-api globals so the next setup can install fresh.
    # These are private attributes of opentelemetry-api and may be renamed
    # across OTel versions; the try/except lets the hook degrade to a no-op
    # rather than break the suite if that happens. Update the pinned OTel
    # version range in requirements.txt together with this block.
    try:
        from opentelemetry import trace

        trace._TRACER_PROVIDER = None
        trace._TRACER_PROVIDER_SET_ONCE._done = False
    except Exception:
        pass
