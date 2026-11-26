from __future__ import annotations

import asyncio
import json
from pathlib import Path

from voice_bench.backends import LoopbackSimBackend, build_cartesia_ws_payload, measure_stream
from voice_bench.cli import run_suite
from voice_bench.metrics import format_markdown

PROMPTS = Path(__file__).resolve().parents[1] / "data" / "prompts_20.json"


def test_prompt_pack_has_ten_barge_in_and_ten_narration() -> None:
    items = json.loads(PROMPTS.read_text(encoding="utf-8"))
    assert len(items) == 20
    assert sum(1 for x in items if x["kind"] == "barge_in") == 10
    assert sum(1 for x in items if x["kind"] == "narration") == 10


def test_cartesia_payload_uses_generation_config_not_deprecated_controls() -> None:
    payload = build_cartesia_ws_payload("Hello world", "voice-123", "ctx-1", speed=1.15)
    assert payload["generation_config"] == {"speed": 1.15}
    assert "__experimental_controls" not in payload
    assert payload["add_timestamps"] is True


def test_barge_in_cancellation_stops_stream_early() -> None:
    backend = LoopbackSimBackend("fast_sim", base_ttfa_ms=5.0, jitter_ms=1.0, chunk_delay_ms=2.0, teardown_ms=2.0, seed=7)
    prompt = {"id": "p1", "kind": "barge_in", "cancel_after_chunks": 2, "text": "one two three four five six seven eight nine ten"}
    metric = asyncio.run(measure_stream(prompt, backend.name, backend.stream))
    assert metric.chunks == 2
    assert metric.barge_in_cancel_ms is not None and metric.barge_in_cancel_ms >= 0.0
    assert metric.ttfa_ms > 0.0


def test_full_20_prompt_simulated_suite() -> None:
    samples, summary = asyncio.run(run_suite(PROMPTS, mode="simulate"))
    assert len(samples) == 40
    assert len(summary) == 2
    for row in summary:
        assert row["prompts"] == 20
        assert row["ttfa_p50_ms"] > 0
        assert row["ttfa_p95_ms"] >= row["ttfa_p50_ms"]
        assert row["cancel_p50_ms"] > 0
    md = format_markdown(summary)
    assert "cartesia_sonic_ws_sim" in md
    assert "local_5090_http_sim" in md
