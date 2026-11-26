# sonic-vs-local-5090-bench

Streaming latency benchmark comparing Cartesia Sonic v5 WebSockets (`tts.websocket()`) against a local workstation GPU HTTP TTS server (e.g. Kokoro or VoxCPM on an RTX 5090) across 20 realistic prompts: 10 conversational barge-in turns and 10 fast-paced short-form narration lines.

## Metrics Measured

1. **TTFA (Time to First Audio Byte, p50 / p95):** elapsed milliseconds from request dispatch until the first non-empty PCM chunk arrives.
2. **Narration RTF (Real-Time Factor, p50):** wall-clock generation time divided by rendered audio duration (`< 1.0` is faster than real time).
3. **Barge-In Cancel Latency (p50 / p95):** milliseconds to abort an active mid-utterance stream cleanly (`aclose()` / WebSocket teardown) after a simulated user interruption.

## Reproducible Loopback Harness Output (`--mode simulate`)

To keep CI and offline reproduction deterministic without burning API credits, `--mode simulate` runs the exact async PCM streaming and mid-utterance `aclose()` barge-in loop over a local loopback harness (`24 kHz` 16-bit mono PCM chunks):

| Backend | Prompts | TTFA p50 (ms) | TTFA p95 (ms) | Narration RTF p50 | Barge-In Cancel p50 (ms) | Barge-In Cancel p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| `cartesia_sonic_ws_sim` | 20 | 108.6 | 124.8 | 0.100 | 15.4 | 15.5 |
| `local_5090_http_sim` | 20 | 46.6 | 50.7 | 0.100 | 15.4 | 16.1 |

Run `--mode live` with `CARTESIA_API_KEY` and a local `LOCAL_TTS_URL` to measure live WebSocket vs local GPU hardware numbers on your own network.

## Cartesia Python SDK DX Note (`cartesia-python#123`)

When upgrading from Cartesia `2.x` to `4.x`/`5.x`, passing `speed` inside `__experimental_controls` can be silently ignored on newer WebSocket endpoints.
`build_cartesia_ws_payload()` in `src/voice_bench/backends.py` explicitly uses `generation_config={"speed": ...}` plus `add_timestamps=True` and verifies the wire payload in `tests/test_voice_bench.py`.

## Quickstart

```bash
pip install -e ".[dev]"

# 1. Run the 20-prompt offline loopback benchmark
python -m voice_bench.cli --mode simulate

# 2. Run live against Cartesia Sonic WebSockets + local RTX 5090 TTS server
pip install -e ".[live]"
export CARTESIA_API_KEY="your-key"
export LOCAL_TTS_URL="http://127.0.0.1:8880/v1/audio/speech"
python -m voice_bench.cli --mode live

# 3. Run tests (4/4 passing)
pytest -q
```
