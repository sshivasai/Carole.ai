"""
# backend/core/observability/phoenix_tracer.py

Arize Phoenix & OpenTelemetry observability integration for Carole.ai.
Enables distributed tracing, token tracking, latency analysis, and local visual flame graphs.
100% in-process and zero-Docker.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("carole.observability")

_PHOENIX_INITIALIZED = False
_PHOENIX_SESSION = None


def init_phoenix(project_name: str = "carole-ai", launch_ui: Optional[bool] = None, port: int = 6006) -> bool:
    """
    Initializes Arize Phoenix OpenTelemetry tracing.
    If launch_ui is True, starts an in-process web dashboard at http://localhost:<port>.
    """
    global _PHOENIX_INITIALIZED, _PHOENIX_SESSION

    if _PHOENIX_INITIALIZED:
        return True

    enabled = os.getenv("ENABLE_PHOENIX", "false").lower() in ("true", "1", "yes")
    if not enabled and launch_ui is None:
        return False

    should_launch_ui = launch_ui if launch_ui is not None else (os.getenv("PHOENIX_LAUNCH_UI", "false").lower() in ("true", "1", "yes"))
    target_port = int(os.getenv("PHOENIX_PORT", str(port)))

    try:
        # Launch in-process dashboard if requested
        if should_launch_ui:
            try:
                import phoenix as px
                _PHOENIX_SESSION = px.launch_app(port=target_port)
                logger.info("🔥 [Phoenix] Local Observability UI launched at http://localhost:%d", target_port)
            except Exception as e:
                logger.warning("Could not launch Phoenix UI dashboard: %s", e)

        # Register OpenTelemetry tracer provider
        try:
            from phoenix.otel import register
            register(
                project_name=project_name,
                endpoint=f"http://localhost:{target_port}/v1/traces" if should_launch_ui else None,
            )
            logger.info("📡 [Phoenix] OpenTelemetry tracer registered for project '%s'", project_name)
        except Exception:
            # Fallback to standard OTel
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            trace.set_tracer_provider(TracerProvider())
            logger.info("📡 [OpenTelemetry] Standard tracer provider initialized.")

        _PHOENIX_INITIALIZED = True
        return True
    except Exception as ex:
        logger.debug("Phoenix initialization skipped or failed: %s", ex)
        return False


def get_phoenix_url() -> Optional[str]:
    """Returns the URL of the active Phoenix UI session, or None."""
    global _PHOENIX_SESSION
    if _PHOENIX_SESSION and hasattr(_PHOENIX_SESSION, "url"):
        return str(_PHOENIX_SESSION.url)
    return None
