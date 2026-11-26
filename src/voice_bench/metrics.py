from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SampleMetric:
    prompt_id: str
    backend: str
    kind: str
    ttfa_ms: float
    total_ms: float
    audio_sec: float
    rtf: float
    barge_in_cancel_ms: float | None
    chunks: int
    bytes_received: int


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil((p / 100.0) * len(ordered)) - 1))
    return round(ordered[idx], 1)


def summarize(samples: list[SampleMetric]) -> list[dict]:
    backends = sorted({s.backend for s in samples})
    rows: list[dict] = []
    for backend in backends:
        group = [s for s in samples if s.backend == backend]
        ttfas = [s.ttfa_ms for s in group]
        rtfs = [s.rtf for s in group if s.kind == "narration"]
        cancels = [s.barge_in_cancel_ms for s in group if s.barge_in_cancel_ms is not None]
        rows.append(
            {
                "backend": backend,
                "prompts": len(group),
                "ttfa_p50_ms": percentile(ttfas, 50),
                "ttfa_p95_ms": percentile(ttfas, 95),
                "rtf_p50": round(percentile(rtfs, 50), 3) if rtfs else 0.0,
                "cancel_p50_ms": percentile(cancels, 50) if cancels else 0.0,
                "cancel_p95_ms": percentile(cancels, 95) if cancels else 0.0,
            }
        )
    return rows


def format_markdown(summary_rows: list[dict]) -> str:
    lines = [
        "| Backend | Prompts | TTFA p50 (ms) | TTFA p95 (ms) | Narration RTF p50 | Barge-In Cancel p50 (ms) | Barge-In Cancel p95 (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary_rows:
        lines.append(
            f"| `{r['backend']}` | {r['prompts']} | {r['ttfa_p50_ms']} | {r['ttfa_p95_ms']} | "
            f"{r['rtf_p50']:.3f} | {r['cancel_p50_ms']} | {r['cancel_p95_ms']} |"
        )
    return "\n".join(lines)
