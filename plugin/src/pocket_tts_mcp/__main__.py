import atexit
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

PORT = int(os.environ.get("POCKET_TTS_PORT", "8765"))
LANGUAGE = os.environ.get("POCKET_TTS_LANGUAGE", "french_24l")
URL = f"http://127.0.0.1:{PORT}"
STARTUP_TIMEOUT = int(os.environ.get("POCKET_TTS_STARTUP_TIMEOUT", "120"))


def _pocket_tts_binary() -> str:
    # The pocket-tts CLI is shipped as a dependency, so it lives in the same
    # venv as this MCP server. Resolve it explicitly to avoid PATH issues when
    # spawned by Claude Code, then fall back to PATH for non-venv installs.
    venv_bin = Path(sys.executable).parent / "pocket-tts"
    if venv_bin.exists():
        return str(venv_bin)
    found = shutil.which("pocket-tts")
    if found:
        return found
    raise RuntimeError(
        "pocket-tts CLI not found. It should be installed as a dependency of "
        "this package — check your venv."
    )


mcp = FastMCP("pocket-tts")
_serve_proc: subprocess.Popen | None = None

# Playback queue: speak() generates the WAV synchronously, then enqueues the
# temp file path for a background thread to play sequentially via afplay.
_play_queue: "queue.Queue[str | None]" = queue.Queue()
_player_thread: threading.Thread | None = None
_player_lock = threading.Lock()
_current_play_proc: subprocess.Popen | None = None
_last_error: str | None = None


def _is_serve_up() -> bool:
    try:
        r = httpx.get(f"{URL}/health", timeout=1.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _ensure_serve() -> None:
    global _serve_proc
    if _is_serve_up():
        return
    log_path = Path(tempfile.gettempdir()) / "pocket-tts-serve.log"
    _serve_proc = subprocess.Popen(
        [_pocket_tts_binary(), "serve", "--language", LANGUAGE, "--port", str(PORT)],
        stdout=log_path.open("ab"),
        stderr=subprocess.STDOUT,
        start_new_session=False,
    )
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        if _is_serve_up():
            return
        if _serve_proc.poll() is not None:
            raise RuntimeError(
                f"pocket-tts serve exited (code={_serve_proc.returncode}). "
                f"See {log_path} for details."
            )
        time.sleep(0.5)
    raise RuntimeError(f"pocket-tts serve did not become ready within {STARTUP_TIMEOUT}s")


def _player_loop() -> None:
    global _current_play_proc, _last_error
    while True:
        wav_path = _play_queue.get()
        if wav_path is None:
            return
        try:
            with _player_lock:
                _current_play_proc = subprocess.Popen(["afplay", wav_path])
            ret = _current_play_proc.wait()
            with _player_lock:
                _current_play_proc = None
            # ret == -15 is SIGTERM from stop_speaking — not an error.
            if ret not in (0, -15):
                _last_error = f"afplay exited {ret} for {wav_path}"
        except Exception as e:  # noqa: BLE001
            _last_error = f"player thread error: {e}"
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass


def _ensure_player() -> None:
    global _player_thread
    if _player_thread is None or not _player_thread.is_alive():
        _player_thread = threading.Thread(target=_player_loop, daemon=True)
        _player_thread.start()


def _drain_queue() -> int:
    dropped = 0
    while True:
        try:
            wav = _play_queue.get_nowait()
        except queue.Empty:
            return dropped
        if wav is None:
            continue
        try:
            os.unlink(wav)
        except OSError:
            pass
        dropped += 1


def _cleanup() -> None:
    with _player_lock:
        if _current_play_proc and _current_play_proc.poll() is None:
            _current_play_proc.terminate()
    _drain_queue()
    if _serve_proc and _serve_proc.poll() is None:
        _serve_proc.terminate()
        try:
            _serve_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _serve_proc.kill()


atexit.register(_cleanup)


@mcp.tool()
def speak(text: str, voice: str | None = None) -> str:
    """Speak text aloud through Kyutai Pocket TTS (local, French by default).

    Returns as soon as the WAV is generated (~0.2-1 s for a typical sentence);
    audio plays in a background thread so you can continue working. Multiple
    speak() calls are queued and played sequentially — they never overlap.

    Use `stop_speaking()` at the start of a new conversational turn to drop
    any audio still queued from the previous turn.

    Args:
        text: Text to read aloud.
        voice: Optional built-in voice name ("estelle", "alba", "giovanni", ...)
               or a remote voice URL (http(s)://, hf://). Defaults to the
               language's built-in voice (estelle for French).
    """
    _ensure_serve()
    _ensure_player()
    files: dict[str, tuple[None, str]] = {"text": (None, text)}
    if voice:
        files["voice_url"] = (None, voice)
    response = httpx.post(f"{URL}/tts", files=files, timeout=120.0)
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(response.content)
        wav_path = f.name
    _play_queue.put(wav_path)
    return (
        f"queued {len(text)} chars "
        f"(voice={voice or 'default'}, queue depth ~{_play_queue.qsize()})"
    )


@mcp.tool()
def stop_speaking() -> str:
    """Stop the currently-playing audio and drop any audio queued behind it.

    Call this at the start of a new conversational turn if a previous turn's
    spoken summary may still be playing — it prevents the user from hearing
    audio that no longer matches what's on screen.
    """
    with _player_lock:
        killed = (
            _current_play_proc is not None
            and _current_play_proc.poll() is None
        )
        if killed:
            _current_play_proc.terminate()
    dropped = _drain_queue()
    return f"dropped {dropped} queued, {'killed' if killed else 'no'} current"


@mcp.tool()
def status() -> dict:
    """Report daemon health, queue depth, and last playback error."""
    with _player_lock:
        playing = (
            _current_play_proc is not None
            and _current_play_proc.poll() is None
        )
    return {
        "daemon_up": _is_serve_up(),
        "url": URL,
        "language": LANGUAGE,
        "managed_pid": _serve_proc.pid if _serve_proc and _serve_proc.poll() is None else None,
        "queue_depth": _play_queue.qsize(),
        "currently_playing": playing,
        "last_error": _last_error,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
