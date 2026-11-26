from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from .backends import (
    CartesiaSonicBackend,
    LocalOpenAITTSBackend,
    LoopbackSimBackend,
    measure_stream,
)
from .metrics import SampleMetric, format_markdown, summarize


async def run_suite(prompts_path: Path, mode: str = "simulate") -> tuple[list[SampleMetric], list[dict]]:
    prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    if mode == "simulate":
        backends = [
            LoopbackSimBackend("cartesia_sonic_ws_sim", base_ttfa_ms=92.0, jitter_ms=26.0, chunk_delay_ms=14.0, teardown_ms=6.0, seed=101),
            LoopbackSimBackend("local_5090_http_sim", base_ttfa_ms=38.0, jitter_ms=9.0, chunk_delay_ms=10.0, teardown_ms=4.0, seed=202),
        ]
    else:
        backends = [CartesiaSonicBackend(), LocalOpenAITTSBackend()]

    samples: list[SampleMetric] = []
    for backend in backends:
        for prompt in prompts:
            samples.append(await measure_stream(prompt, backend.name, backend.stream))
    return samples, summarize(samples)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Benchmark Cartesia Sonic v5 WebSocket streaming vs local GPU TTS")
    ap.add_argument("--prompts", type=Path, default=Path("data/prompts_20.json"))
    ap.add_argument("--mode", choices=["simulate", "live"], default="simulate")
    ap.add_argument("--out", type=Path, default=Path("artifacts/voice_bench_results.json"))
    args = ap.parse_args(argv)

    samples, summary = asyncio.run(run_suite(args.prompts, mode=args.mode))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"mode": args.mode, "summary": summary, "samples": [asdict(s) for s in samples]}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(format_markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
