"""
# backend/core/observability/openllmetry_tracer.py

OpenLLMetry (Traceloop) observability & OpenTelemetry tracing integration for Carole.ai.
Captures LLM calls, multi-agent swarm spans, tool executions, token metrics, and latency.
Provides an in-process telemetry buffer so Carole's frontend can display native trace visualizations.
"""

import os
import time
import logging
from typing import Dict, List, Any, Optional
from collections import deque
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SimpleSpanProcessor

logger = logging.getLogger("carole.observability")

_OPENLLMETRY_INITIALIZED = False
_MAX_BUFFER_SIZE = 500

# Thread-safe in-memory ring buffer for native UI telemetry
_TRACE_BUFFER: deque = deque(maxlen=_MAX_BUFFER_SIZE)


class InMemorySpanRecorder(SpanExporter):
    """
    OpenTelemetry SpanExporter that records spans into Carole's in-memory telemetry buffer.
    Powering the native, dark-themed Observability panel in the Carole.ai UI.
    """

    def export(self, spans: List[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            try:
                duration_ms = 0.0
                if span.end_time and span.start_time:
                    duration_ms = round((span.end_time - span.start_time) / 1_000_000, 2)

                attrs = dict(span.attributes) if span.attributes else {}

                # Extract LLM & agent metadata
                span_record = {
                    "trace_id": f"{span.context.trace_id:032x}" if span.context else "",
                    "span_id": f"{span.context.span_id:016x}" if span.context else "",
                    "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else None,
                    "name": span.name,
                    "status": span.status.status_code.name if span.status else "UNSET",
                    "start_time": datetime.fromtimestamp(span.start_time / 1_000_000_000, tz=timezone.utc).isoformat() if span.start_time else None,
                    "end_time": datetime.fromtimestamp(span.end_time / 1_000_000_000, tz=timezone.utc).isoformat() if span.end_time else None,
                    "duration_ms": duration_ms,
                    "attributes": {str(k): str(v) for k, v in attrs.items()},
                    # Extracted convenience fields for UI rendering
                    "agent_name": str(attrs.get("agent.name", attrs.get("agent_name", ""))),
                    "agent_role": str(attrs.get("agent.role", attrs.get("agent_role", ""))),
                    "model": str(attrs.get("llm.model_name", attrs.get("gen_ai.response.model", attrs.get("agent.model", "")))),
                    "prompt_tokens": int(attrs.get("llm.usage.prompt_tokens", attrs.get("gen_ai.usage.input_tokens", attrs.get("llm.input_tokens", 0)))),
                    "completion_tokens": int(attrs.get("llm.usage.completion_tokens", attrs.get("gen_ai.usage.output_tokens", attrs.get("llm.output_tokens", 0)))),
                    "tool_name": str(attrs.get("tool.name", attrs.get("tool.call", ""))),
                }
                _TRACE_BUFFER.appendleft(span_record)
            except Exception as e:
                logger.debug("Error processing span for buffer: %s", e)

        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


def init_openllmetry(app_name: str = "carole-ai", otlp_endpoint: Optional[str] = None) -> bool:
    """
    Initializes OpenLLMetry (Traceloop) SDK and registers the in-memory span recorder.
    """
    global _OPENLLMETRY_INITIALIZED

    if _OPENLLMETRY_INITIALIZED:
        return True

    enabled = os.getenv("ENABLE_OPENLLMETRY", "true").lower() in ("true", "1", "yes")
    if not enabled:
        logger.info("ℹ️ [OpenLLMetry] Tracing is disabled via ENABLE_OPENLLMETRY=false")
        return False

    try:
        from traceloop.sdk import Traceloop

        # 1. Initialize Traceloop SDK with custom local in-memory processor
        recorder = InMemorySpanRecorder()
        Traceloop.init(
            app_name=app_name,
            disable_batch=True,
            processor=SimpleSpanProcessor(recorder),
            endpoint_is_traceloop=False,
            telemetry_enabled=False,
            api_endpoint="http://localhost:0",
        )
        logger.info("🔭 [OpenLLMetry] Traceloop SDK initialized successfully with local in-memory buffer!")

        _OPENLLMETRY_INITIALIZED = True
        return True
    except ImportError:
        # Fallback to standard OpenTelemetry if traceloop-sdk isn't installed
        try:
            from opentelemetry.sdk.trace import TracerProvider
            provider = TracerProvider()
            provider.add_span_processor(SimpleSpanProcessor(InMemorySpanRecorder()))
            trace.set_tracer_provider(provider)
            logger.info("📡 [OpenLLMetry] Fallback: Standard OpenTelemetry TracerProvider initialized.")
            _OPENLLMETRY_INITIALIZED = True
            return True
        except Exception as e:
            logger.warning("Could not initialize OpenLLMetry tracer provider: %s", e)
            return False
    except Exception as ex:
        logger.warning("OpenLLMetry initialization warning: %s", ex)
        return False


def get_recent_traces(limit: int = 50, filter_agent: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns the most recent traces stored in the in-memory ring buffer."""
    traces = list(_TRACE_BUFFER)
    if filter_agent:
        traces = [t for t in traces if filter_agent.lower() in t.get("agent_name", "").lower()]
    return traces[:limit]


def get_observability_stats() -> Dict[str, Any]:
    """Calculates aggregate metrics across captured traces."""
    traces = list(_TRACE_BUFFER)
    total_spans = len(traces)
    if total_spans == 0:
        return {
            "total_spans": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "avg_latency_ms": 0.0,
            "error_count": 0,
            "models_used": [],
            "status": "active" if _OPENLLMETRY_INITIALIZED else "idle",
        }

    total_prompt_tokens = sum(t.get("prompt_tokens", 0) for t in traces)
    total_completion_tokens = sum(t.get("completion_tokens", 0) for t in traces)
    total_duration = sum(t.get("duration_ms", 0.0) for t in traces)
    avg_latency = round(total_duration / total_spans, 2) if total_spans > 0 else 0.0
    error_count = sum(1 for t in traces if t.get("status") == "ERROR")
    models = list(set(t.get("model") for t in traces if t.get("model")))

    return {
        "total_spans": total_spans,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "avg_latency_ms": avg_latency,
        "error_count": error_count,
        "models_used": models,
        "status": "active" if _OPENLLMETRY_INITIALIZED else "idle",
    }


def clear_traces():
    """Clears the in-memory telemetry buffer."""
    _TRACE_BUFFER.clear()


# =====================================================================
# Official OpenLLMetry Decorators for Agentic Workflows
# =====================================================================
try:
    from traceloop.sdk.decorators import workflow, agent, task, tool
except ImportError:
    def workflow(name=None, **kwargs):
        def decorator(fn): return fn
        return decorator

    def agent(name=None, **kwargs):
        def decorator(fn): return fn
        return decorator

    def task(name=None, **kwargs):
        def decorator(fn): return fn
        return decorator

    def tool(name=None, **kwargs):
        def decorator(fn): return fn
        return decorator
