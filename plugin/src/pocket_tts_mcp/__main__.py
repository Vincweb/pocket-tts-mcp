"""MCP server wrapping Kyutai Pocket TTS via its native Python streaming API.

Replaces the v0.3.x architecture (which shelled out to `pocket-tts serve`
and POSTed full WAVs to it). The new pipeline:

  speak() request
      └─► generation thread: tts_model.generate_audio_stream(...) yields
          ~80 ms PCM chunks of torch.Tensor
              └─► audio queue (numpy float32)
                      └─► writer thread: stream.write(chunk) in blocking
                          write-mode sounddevice OutputStream
                              └─► CoreAudio

No external daemon, no HTTP, no temp WAV files, no afplay. First audio
in ~200 ms (Kyutai's claim), playback is gap-free thanks to PortAudio's
internal buffer (Python never runs in the realtime audio thread).
"""
import atexit
import os
import queue
import threading
from typing import Any

import numpy as np
import sounddevice as sd
from mcp.server.fastmcp import FastMCP

LANGUAGE = os.environ.get("POCKET_TTS_LANGUAGE", "french_24l")
DEFAULT_VOICE = os.environ.get("POCKET_TTS_VOICE")  # None → language default
QUANTIZE = os.environ.get("POCKET_TTS_QUANTIZE", "0") == "1"
DEVICE = os.environ.get("POCKET_TTS_DEVICE", "cpu")
MAX_TOKENS = int(os.environ.get("POCKET_TTS_MAX_TOKENS", "50"))

mcp = FastMCP("pocket-tts")

_model: Any = None
_model_lock = threading.Lock()
_model_load_error: str | None = None
_sample_rate: int | None = None  # discovered from model.config.mimi.sample_rate

# Per-voice state cache. Built lazily on first use of a voice.
_voice_states: dict[str, Any] = {}
_voice_states_lock = threading.Lock()

# Audio queue: generation thread puts numpy chunks, writer thread calls
# stream.write() in blocking mode. PortAudio handles all realtime concerns.
_audio_q: "queue.Queue[np.ndarray | None]" = queue.Queue()
_writer_thread: threading.Thread | None = None
_stream: sd.OutputStream | None = None
_stream_lock = threading.Lock()

# Generation queue (FIFO of speak requests).
_gen_q: "queue.Queue[tuple[str, str | None] | None]" = queue.Queue()
_gen_thread: threading.Thread | None = None
_cancel_event = threading.Event()
_gen_in_flight = threading.Event()

_last_error: str | None = None


def _ensure_model() -> Any:
    global _model, _model_load_error, _sample_rate
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from pocket_tts.models.tts_model import TTSModel  # heavy import
            model = TTSModel.load_model(language=LANGUAGE, quantize=QUANTIZE)
            model.to(DEVICE)
            _sample_rate = int(model.config.mimi.sample_rate)
            _model = model
            return _model
        except Exception as e:  # noqa: BLE001
            _model_load_error = f"{type(e).__name__}: {e}"
            raise


def _resolve_voice(voice: str | None) -> str:
    if voice:
        return voice
    if DEFAULT_VOICE:
        return DEFAULT_VOICE
    from pocket_tts.main import get_default_voice_for_language
    return get_default_voice_for_language(LANGUAGE)


def _voice_state_for(voice: str) -> Any:
    with _voice_states_lock:
        if voice in _voice_states:
            return _voice_states[voice]
    model = _ensure_model()
    state = model.get_state_for_audio_prompt(voice)
    with _voice_states_lock:
        _voice_states[voice] = state
    return state


def _ensure_stream() -> None:
    global _stream
    sr = _sample_rate or 24000
    with _stream_lock:
        if _stream is None or _stream.closed:
            _stream = sd.OutputStream(
                samplerate=sr,
                channels=1,
                dtype="float32",
            )
            _stream.start()
        elif _stream.stopped:
            _stream.start()


def _close_stream() -> None:
    global _stream
    with _stream_lock:
        if _stream is not None and not _stream.closed:
            try:
                _stream.abort()
                _stream.close()
            except Exception:  # noqa: BLE001
                pass
            _stream = None


def _writer_loop() -> None:
    global _last_error
    while True:
        chunk = _audio_q.get()
        if chunk is None:
            return
        if _cancel_event.is_set():
            continue
        try:
            stream = _stream
            if stream is None or stream.closed:
                continue
            stream.write(chunk)
        except Exception as e:  # noqa: BLE001
            _last_error = f"writer: {type(e).__name__}: {e}"


def _ensure_writer() -> None:
    global _writer_thread
    if _writer_thread is None or not _writer_thread.is_alive():
        _writer_thread = threading.Thread(target=_writer_loop, daemon=True)
        _writer_thread.start()


def _chunk_to_float32(chunk: Any) -> np.ndarray:
    # pocket-tts yields torch.Tensor on CPU. Defensive: support numpy too.
    try:
        import torch  # noqa: F401
        if hasattr(chunk, "detach"):
            chunk = chunk.detach().cpu().numpy()
    except ImportError:
        pass
    arr = np.asarray(chunk).astype(np.float32, copy=False)
    if arr.ndim > 1:
        arr = arr.squeeze()
    return arr


def _generation_loop() -> None:
    global _last_error
    while True:
        req = _gen_q.get()
        if req is None:
            return
        text, voice_arg = req
        _cancel_event.clear()
        _gen_in_flight.set()
        try:
            model = _ensure_model()
            voice = _resolve_voice(voice_arg)
            voice_state = _voice_state_for(voice)
            opened_stream = False
            for chunk in model.generate_audio_stream(
                model_state=voice_state,
                text_to_generate=text,
                max_tokens=MAX_TOKENS,
            ):
                if _cancel_event.is_set():
                    break
                arr = _chunk_to_float32(chunk)
                if arr.size == 0:
                    continue
                if not opened_stream:
                    _ensure_stream()
                    _ensure_writer()
                    opened_stream = True
                _audio_q.put(arr)
        except Exception as e:  # noqa: BLE001
            _last_error = f"generation: {type(e).__name__}: {e}"
        finally:
            _gen_in_flight.clear()


def _ensure_gen_thread() -> None:
    global _gen_thread
    if _gen_thread is None or not _gen_thread.is_alive():
        _gen_thread = threading.Thread(target=_generation_loop, daemon=True)
        _gen_thread.start()


def _drain_audio_q() -> int:
    dropped = 0
    while True:
        try:
            x = _audio_q.get_nowait()
        except queue.Empty:
            return dropped
        if x is None:
            continue
        dropped += 1


def _drain_gen_q() -> int:
    dropped = 0
    while True:
        try:
            x = _gen_q.get_nowait()
        except queue.Empty:
            return dropped
        if x is None:
            continue
        dropped += 1


def _cleanup() -> None:
    _cancel_event.set()
    _drain_audio_q()
    _drain_gen_q()
    _close_stream()


atexit.register(_cleanup)


@mcp.tool()
def speak(text: str, voice: str | None = None) -> str:
    """Speak text aloud through Kyutai Pocket TTS (local, streaming, ~200ms TTFA).

    Returns immediately. The text is queued for streaming generation in a
    background thread; chunks are pushed into a continuous sounddevice
    OutputStream as they're produced. Multiple speak() calls queue and
    play sequentially — they never overlap.

    Use `stop_speaking()` at the start of a new conversational turn to drop
    any audio still playing/queued from the previous turn AND cancel any
    in-flight generation.

    Args:
        text: Text to read aloud. The model language is fixed at startup
              via POCKET_TTS_LANGUAGE (default `french_24l`).
        voice: Built-in voice name (e.g. "estelle", "alba", "giovanni",
               "juergen", "lola", "rafael"), or a path to a wav file for
               voice cloning, or a `hf://` URL. Defaults to the language's
               built-in voice.
    """
    _ensure_gen_thread()
    _gen_q.put((text, voice))
    return (
        f"enqueued {len(text)} chars (voice={voice or 'default'}, "
        f"gen_pending={_gen_q.qsize()}, audio_buffer={_audio_q.qsize()})"
    )


@mcp.tool()
def stop_speaking() -> str:
    """Stop the currently-playing audio, drop pending audio chunks, AND
    cancel any in-flight generation.

    Call this at the start of a new conversational turn so the previous
    turn's audio doesn't bleed into the new one.
    """
    _cancel_event.set()
    dropped_gen = _drain_gen_q()
    dropped_audio = _drain_audio_q()
    with _stream_lock:
        if _stream is not None and not _stream.closed:
            try:
                _stream.abort()
            except Exception:  # noqa: BLE001
                pass
    return (
        f"cancelled generation, dropped {dropped_audio} audio chunks "
        f"+ {dropped_gen} pending requests, aborted current playback"
    )


@mcp.tool()
def status() -> dict:
    """Report model load state, queue depths, and last error."""
    with _stream_lock:
        stream_active = (
            _stream is not None
            and not _stream.closed
            and not _stream.stopped
        )
    return {
        "language": LANGUAGE,
        "model_loaded": _model is not None,
        "model_load_error": _model_load_error,
        "sample_rate": _sample_rate,
        "cached_voices": list(_voice_states.keys()),
        "gen_pending": _gen_q.qsize(),
        "gen_in_flight": _gen_in_flight.is_set(),
        "audio_buffer": _audio_q.qsize(),
        "stream_active": stream_active,
        "last_error": _last_error,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
