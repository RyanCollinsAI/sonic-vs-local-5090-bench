from __future__ import annotations

import asyncio
import os
import random
import time
from typing import Any, AsyncIterator

import httpx

from .metrics import SampleMetric

PCM_SAMPLE_RATE = 24000
PCM_BYTES_PER_SEC = PCM_SAMPLE_RATE * 2  # 16-bit mono PCM


def build_cartesia_ws_payload(
    text: str,
    voice_id: str,
    context_id: str,
    *,
    speed: float = 1.0,
    model_id: str = "sonic-3",
) -> dict[str, Any]:
    """Build Cartesia v4/v5 WebSocket request payload.

    Uses `generation_config.speed` instead of deprecated v2 `__experimental_controls.speed`,
    which is silently ignored in newer Cartesia SDK/API releases (cartesia-python#123).
    """
    return {
        "model_id": model_id,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "context_id": context_id,
        "output_format": {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": PCM_SAMPLE_RATE,
        },
        "generation_config": {"speed": speed},
        "add_timestamps": True,
    }


async def measure_stream(
    prompt: dict[str, Any],
    backend_name: str,
    stream_factory: Any,
) -> SampleMetric:
    """Measure TTFA, total generation time, RTF, and mid-stream barge-in cancel latency."""
    cancel_after = int(prompt.get("cancel_after_chunks") or 0)
    t0 = time.perf_counter()
    ttfa_ms: float | None = None
    cancel_ms: float | None = None
    chunks = 0
    total_bytes = 0

    stream = stream_factory(prompt)
    try:
        async for chunk in stream:
            if not chunk:
                continue
            now = time.perf_counter()
            if ttfa_ms is None:
                ttfa_ms = round((now - t0) * 1000.0, 1)
            chunks += 1
            total_bytes += len(chunk)
            if cancel_after and chunks >= cancel_after:
                t_cancel = time.perf_counter()
                await stream.aclose()
                cancel_ms = round((time.perf_counter() - t_cancel) * 1000.0, 1)
                break
    finally:
        if hasattr(stream, "aclose"):
            await stream.aclose()

    total_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    audio_sec = max(0.05, total_bytes / PCM_BYTES_PER_SEC)
    rtf = round((total_ms / 1000.0) / audio_sec, 4)
    return SampleMetric(
        prompt_id=prompt["id"],
        backend=backend_name,
        kind=prompt["kind"],
        ttfa_ms=ttfa_ms or total_ms,
        total_ms=total_ms,
        audio_sec=round(audio_sec, 2),
        rtf=rtf,
        barge_in_cancel_ms=cancel_ms,
        chunks=chunks,
        bytes_received=total_bytes,
    )


class LocalOpenAITTSBackend:
    """Streams audio from a local OpenAI-compatible TTS endpoint (e.g. Kokoro/VoxCPM on RTX 5090)."""

    name = "local_5090_http"

    def __init__(self, endpoint_url: str | None = None, voice: str = "af_heart") -> None:
        self.endpoint_url = endpoint_url or os.environ.get("LOCAL_TTS_URL", "http://127.0.0.1:8880/v1/audio/speech")
        self.voice = voice

    async def stream(self, prompt: dict[str, Any]) -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                self.endpoint_url,
                json={
                    "model": "kokoro",
                    "voice": self.voice,
                    "input": prompt["text"],
                    "response_format": "pcm",
                },
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    yield chunk


class CartesiaSonicBackend:
    """Live Cartesia Sonic v5 WebSocket streaming backend using generation_config."""

    name = "cartesia_sonic_ws"

    def __init__(self, api_key: str | None = None, voice_id: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("CARTESIA_API_KEY", "").strip()
        self.voice_id = voice_id or os.environ.get("CARTESIA_VOICE_ID", "a0e99841-438c-4a64-b679-ae501e7d6091")

    async def stream(self, prompt: dict[str, Any]) -> AsyncIterator[bytes]:
        if not self.api_key:
            raise RuntimeError("CARTESIA_API_KEY is not set; run with --mode simulate for offline loopback.")
        from cartesia import AsyncCartesia  # imported lazily for offline CI compatibility

        client = AsyncCartesia(api_key=self.api_key)
        ws = await client.tts.websocket()
        payload = build_cartesia_ws_payload(prompt["text"], self.voice_id, context_id=prompt["id"])
        try:
            async for out in await ws.send(**payload, stream=True):
                audio = out.get("audio") if isinstance(out, dict) else getattr(out, "audio", None)
                if audio:
                    yield audio
        finally:
            await ws.close()
            await client.close()


class LoopbackSimBackend:
    """Deterministic async PCM loopback harness for CI and offline benchmarking."""

    def __init__(
        self,
        name: str,
        *,
        base_ttfa_ms: float,
        jitter_ms: float,
        chunk_delay_ms: float,
        teardown_ms: float,
        seed: int = 2026,
    ) -> None:
        self.name = name
        self.base_ttfa_ms = base_ttfa_ms
        self.jitter_ms = jitter_ms
        self.chunk_delay_ms = chunk_delay_ms
        self.teardown_ms = teardown_ms
        self.rng = random.Random(seed)

    async def stream(self, prompt: dict[str, Any]) -> AsyncIterator[bytes]:
        # Scale synthetic chunk count by word count so narration RTF reflects prompt length
        words = max(4, len(prompt["text"].split()))
        n_chunks = max(4, min(14, words // 2))
        first_wait = max(0.002, (self.base_ttfa_ms + self.rng.uniform(0.0, self.jitter_ms)) / 1000.0)
        try:
            await asyncio.sleep(first_wait)
            for _ in range(n_chunks):
                yield b"\x00\x01" * 6000  # 12,000 bytes = 0.25s of 24kHz 16-bit mono PCM
                await asyncio.sleep(self.chunk_delay_ms / 1000.0)
        finally:
            await asyncio.sleep(self.teardown_ms / 1000.0)
