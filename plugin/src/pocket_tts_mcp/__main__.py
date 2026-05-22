import atexit
import os
import shutil
import subprocess
import sys
import tempfile
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


def _cleanup() -> None:
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

    The first call starts a local pocket-tts daemon if it isn't running; it
    keeps the model warm in RAM for subsequent calls. Audio is played via
    macOS `afplay`.

    Args:
        text: Text to read aloud.
        voice: Optional built-in voice name ("estelle", "alba", "giovanni", ...)
               or a remote voice URL (http(s)://, hf://). Defaults to the
               language's built-in voice (estelle for French).
    """
    _ensure_serve()
    files: dict[str, tuple[None, str]] = {"text": (None, text)}
    if voice:
        files["voice_url"] = (None, voice)
    response = httpx.post(f"{URL}/tts", files=files, timeout=120.0)
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(response.content)
        wav_path = f.name
    try:
        subprocess.run(["afplay", wav_path], check=False)
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
    return f"spoke {len(text)} chars (voice={voice or 'default'})"


@mcp.tool()
def status() -> dict:
    """Report whether the local pocket-tts daemon is running and on which port."""
    return {
        "daemon_up": _is_serve_up(),
        "url": URL,
        "language": LANGUAGE,
        "managed_pid": _serve_proc.pid if _serve_proc and _serve_proc.poll() is None else None,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
