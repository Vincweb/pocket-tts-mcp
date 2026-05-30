# kyutai-tts-mcp

Local-only voice for any MCP client (Claude Code, Claude Desktop, Cursor,
etc.) via [Kyutai Pocket TTS](https://github.com/kyutai-labs/pocket-tts).
No cloud, no API keys, no rate limits.

- 🇫🇷 French (Estelle), 🇬🇧 English (Alba), plus Spanish, German, Italian, Portuguese
- **TTFA ~80–200 ms** thanks to native streaming via the pocket-tts Python API
- **Multi-language at runtime** — pass `language=` per `speak()` call, models load lazily and cache
- ~4-5× real-time generation on Apple Silicon / Intel CPU
- Non-blocking `speak()`, gap-free playback via `sounddevice` write-mode
- ~600 MB venv, ~1 GB model cache per language

## Install

```bash
uvx kyutai-tts-mcp --help
```

Or persistent:

```bash
uv tool install kyutai-tts-mcp
```

Then add to your MCP client's `.mcp.json`:

```json
{
  "mcpServers": {
    "kyutai-tts": {
      "command": "uvx",
      "args": ["kyutai-tts-mcp", "--language", "french_24l"]
    }
  }
}
```

Replace `french_24l` with `english`, `spanish_24l`, `german_24l`,
`italian_24l`, or `portuguese_24l` for your default language. Per-call
`language=` overrides this default.

## MCP tools

| Tool | Purpose |
|---|---|
| `speak(text, voice?, language?, interrupt?)` | Generate audio for `text` and queue it for background playback. Returns immediately, streaming generation. By default, calls queue and play sequentially (including across turns). Pass `interrupt=True` to abort current playback and clear the queue first. Pass `language=` to switch model on the fly. |
| `stop_speaking()` | Stop current playback, drop queue, cancel in-flight generation. Use for explicit "mute" requests. For mid-turn interruption + new speech, use `speak(..., interrupt=True)` instead. |
| `status()` | Report loaded languages, queue depths, sample rate, last error. |

## Configuration

The default language is set via `--language` (CLI) or `KYUTAI_TTS_LANGUAGE`
(env var). Other knobs (all env):

- `KYUTAI_TTS_VOICE` — default voice name
- `KYUTAI_TTS_DEVICE` — PyTorch device (default `cpu`; `mps` not supported)
- `KYUTAI_TTS_QUANTIZE` — set to `1` for int8 quantization
- `KYUTAI_TTS_MAX_TOKENS` — max tokens per streaming chunk (default `50`)

## Claude Code users

If you're on Claude Code (CLI, desktop, or via Cursor), you can install
the bundled plugin (MCP wiring + `/voice-mode` skill) in one shot:

```
/plugin marketplace add Vincweb/kyutai-tts-mcp
/plugin install kyutai-tts@vincweb-tools
```

See the [main repo](https://github.com/Vincweb/kyutai-tts-mcp) for
architecture details, voice catalog, and a side-by-side comparison with
[voxtral-mcp](https://github.com/Vincweb/voxtral-mcp).

## Requirements

- macOS (Apple Silicon recommended; Intel works — the model is CPU-only)
- Python 3.10 – 3.13
- ~1 GB free RAM per loaded language

## License

MIT. Kyutai pocket-tts itself is under its own permissive licence (see
[upstream](https://github.com/kyutai-labs/pocket-tts)).
