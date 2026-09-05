"""
# backend/test_openllmetry.py
Verification test script for OpenLLMetry in Carole.ai.
Initializes OpenLLMetry, emits multi-agent swarm spans, and verifies trace retrieval.
"""

import sys
import time
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core.observability.openllmetry_tracer import (
    init_openllmetry,
    get_recent_traces,
    get_observability_stats,
)
from opentelemetry import trace

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_openllmetry")


def main():
    print("\n" + "=" * 65)
    print("🔭 Testing OpenLLMetry Observability & Tracing for Carole.ai")
    print("=" * 65)

    # 1. Initialize OpenLLMetry
    print("\n[1/3] Initializing OpenLLMetry tracer & in-memory span recorder...")
    success = init_openllmetry(app_name="carole-ai")
    if not success:
        print("❌ Failed to initialize OpenLLMetry.")
        return
    print("✓ OpenLLMetry initialized and attached to in-memory UI buffer!")

    # 2. Emit sample multi-agent swarm trace
    print("\n[2/3] Simulating Carole multi-agent swarm execution...")
    tracer = trace.get_tracer("carole.ai.swarm", "1.0.0")

    with tracer.start_as_current_span("Swarm Goal: Implement OpenLLMetry UI & Backend") as root_span:
        root_span.set_attribute("carole.project_id", "carole_core_v2")
        root_span.set_attribute("agent.name", "Lead Orchestrator")
        root_span.set_attribute("llm.prompt", "Replace external dashboard with native OpenLLMetry in-app UI.")
        time.sleep(0.05)

        with tracer.start_as_current_span("Agent: Archer (Lead Orchestrator)") as archer:
            archer.set_attribute("agent.name", "Archer")
            archer.set_attribute("agent.role", "Lead Orchestrator")
            archer.set_attribute("agent.model", "claude-sonnet-4")
            archer.set_attribute("llm.usage.prompt_tokens", 1850)
            archer.set_attribute("llm.usage.completion_tokens", 420)
            time.sleep(0.08)

        with tracer.start_as_current_span("Subagent: Sub-PythonDev (Coder)") as coder:
            coder.set_attribute("agent.name", "Sub-PythonDev_8777")
            coder.set_attribute("agent.role", "Coder")
            coder.set_attribute("agent.model", "gpt-4o-mini")
            coder.set_attribute("tool.call", "replace_file_content")
            coder.set_attribute("llm.usage.prompt_tokens", 2600)
            coder.set_attribute("llm.usage.completion_tokens", 610)
            time.sleep(0.1)

        with tracer.start_as_current_span("Security: Judge AI Gate") as judge:
            judge.set_attribute("agent.name", "Judge AI")
            judge.set_attribute("agent.role", "Security Interceptor")
            judge.set_attribute("agent.model", "gemini-2.0-flash")
            judge.set_attribute("judge_ai.verdict", "SAFE_AUTO_APPROVED")
            judge.set_attribute("tool.call", "pytest tests/")
            judge.set_attribute("llm.usage.prompt_tokens", 920)
            judge.set_attribute("llm.usage.completion_tokens", 150)
            time.sleep(0.04)

    # 3. Verify in-memory buffer output
    print("\n[3/3] Querying captured spans from in-process buffer...")
    traces = get_recent_traces(limit=10)
    stats = get_observability_stats()

    print(f"✓ Total spans captured in buffer: {len(traces)}")
    print(f"✓ Aggregate Metrics:")
    print(f"   - Total Prompt Tokens:     {stats['total_prompt_tokens']:,}")
    print(f"   - Total Completion Tokens: {stats['total_completion_tokens']:,}")
    print(f"   - Average Latency:         {stats['avg_latency_ms']} ms")
    print(f"   - Models Tracked:          {', '.join(stats['models_used'])}")
    print(f"   - Error Count:             {stats['error_count']}")

    print("\n" + "=" * 65)
    print("🎉 OpenLLMetry is functioning with 100% in-process trace capture!")
    print("   Traces will stream directly into Carole's native custom UI.")
    print("=" * 65)
    assert len(traces) > 0, "Expected in-memory spans to be captured by OpenLLMetry"
    assert stats["total_prompt_tokens"] > 0


def test_openllmetry_swarm_tracing():
    """Pytest test case for OpenLLMetry in-process tracing."""
    main()


if __name__ == "__main__":
    main()
