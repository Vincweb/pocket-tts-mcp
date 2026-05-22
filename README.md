# pocket-tts-mcp

Local-only voice for Claude Code on macOS, via [Kyutai Pocket TTS](https://github.com/kyutai-labs/pocket-tts).
No cloud, no API keys, no rate limits.

- 🇫🇷 French (Estelle), 🇬🇧 English (Alba), plus Spanish, German, Italian, Portuguese
- ~5× real-time on Apple Silicon CPU — model stays warm in RAM between calls
- **Non-blocking** `speak()` (v0.3.0): audio plays in the background, Claude keeps working
- Bundled `/voice-mode` skill — Claude speaks summaries of its answers automatically
- Self-contained: bundles the Kyutai `pocket-tts` CLI as a dependency, no extra install

Ships as a Claude Code **plugin** (with a bundled MCP server + skill) and also
works as a standalone MCP server for users who don't use the plugin system.

## Requirements

- macOS (Apple Silicon recommended; Intel works too — model is CPU-only)
- [uv](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Claude Code (CLI, desktop app, or Cursor extension)

## Install — option A: Claude Code plugin (recommended)

```
/plugin marketplace add Vincweb/pocket-tts-mcp
/plugin install pocket-tts@vincweb-tools
```

That's it. The plugin ships the MCP server, the `/voice-mode` skill, and the
right wiring. Restart Claude Code; on first use, `uv run` materializes the
Python venv (~30 s) and the Kyutai model downloads from Hugging Face (~1 GB,
once per language). Subsequent runs are instant.

## Install — option B: standalone (no plugin system)

```bash
git clone https://github.com/Vincweb/pocket-tts-mcp.git
cd pocket-tts-mcp/plugin
./install.sh
```

The script:
1. `uv sync` materializes the venv at `plugin/.venv/` with both the MCP server
   and the `pocket-tts` CLI as dependencies
2. Prints the `.mcp.json` snippet to paste into your project

You'll need to manually:
- Add the printed `.mcp.json` entry to your project's `.mcp.json` (or `~/.claude.json`)
- Copy `plugin/skills/voice-mode/SKILL.md` to `~/.claude/skills/voice-mode/SKILL.md`

Then restart Claude Code.

## Use

In any conversation, type **`/voice-mode`** (or `/pocket-tts:voice-mode` if installed
as a plugin), or just say **"parle-moi"** / **"voice mode"**. Claude will:

- Reply with normal text (markdown, code, links — unchanged)
- Call `stop_speaking()` at the start of each turn to drop any audio still
  playing from the previous turn (prevents desync between text and voice)
- Call `speak()` with a short spoken summary of the turn (1–3 sentences,
  audio plays in the background while Claude continues with other work)
- Skip speaking pure code dumps / long diffs

Stop with **"mute"**, **"silence"**, **"stop talking"**, **"arrête de parler"**.

The first call after a Claude Code restart takes ~10–15 s (model load).
Subsequent generation calls are 0.2–1 s, audio plays asynchronously.

## MCP tools exposed

| Tool | Purpose |
|---|---|
| `speak(text, voice?)` | Generate audio for `text` and **queue it for background playback**. Returns immediately once the WAV is generated (~0.2–1 s). Multiple calls queue sequentially — no overlap. |
| `stop_speaking()` | Stop the currently-playing audio and drop everything queued behind it. Use at the start of a new turn to clear stale audio. |
| `status()` | Report daemon health, current queue depth, whether something is playing, and the last playback error (errors don't silently disappear). |

## Configuration

Set in the `env` block of the MCP entry (`.mcp.json`):

| Variable | Default | Notes |
|---|---|---|
| `POCKET_TTS_LANGUAGE` | `french_24l` | Also: `english`, `spanish_24l`, `german_24l`, `italian_24l`, `portuguese_24l` |
| `POCKET_TTS_PORT` | `8765` | Local port for the pocket-tts FastAPI daemon |
| `POCKET_TTS_STARTUP_TIMEOUT` | `120` | Seconds to wait for the daemon to become ready |

## Voices

Pass `voice="..."` in your conversation ("parle avec la voix de Rafael"):

| Voice | Language | Notes |
|---|---|---|
| `estelle` | French | default for French |
| `alba` | Multilingual | neutral, works in EN |
| `juergen` | German | |
| `lola` | Spanish | |
| `giovanni` | Italian | |
| `rafael` | Portuguese | |

You can also pass any Hugging Face voice URL (`hf://...`) or a path you exported
with `pocket-tts export-voice` for voice cloning.

## Architecture

```
Claude Code  ──MCP stdio──▶  pocket-tts-mcp (Python, FastMCP)
                                  │
                                  │  speak(text)
                                  ▼
                            POST /tts (multipart)
                                  │
                                  ▼
                            pocket-tts serve  ──▶  WAV bytes
                            (FastAPI, model in RAM)     │
                                                        ▼
                                                  playback queue
                                                        │
                                                        ▼
                                                  player thread
                                                        │
                                                        ▼
                                                      afplay
```

Key design choices:
- **MCP server spawns `pocket-tts serve` as a subprocess on first use**, keeps
  the model warm in RAM, tears it down on shutdown via `atexit`.
- **Async playback**: `speak()` writes the WAV to a temp file, pushes it onto
  a `queue.Queue` and returns. A daemon thread (`_player_loop`) consumes the
  queue and calls `afplay` via `subprocess.Popen`, so the playback handle is
  preserved for `stop_speaking()` to terminate.
- **No overlap**: queue is single-consumer, so audio plays sequentially even
  if Claude fires multiple `speak()` calls in rapid succession.

## Repo layout

```
pocket-tts-mcp/                          marketplace root
├── .claude-plugin/
│   └── marketplace.json                 declares the marketplace
├── plugin/                              plugin root
│   ├── .claude-plugin/plugin.json       plugin manifest
│   ├── .mcp.json                        MCP server wired with ${CLAUDE_PLUGIN_ROOT}
│   ├── skills/voice-mode/SKILL.md       /voice-mode skill
│   ├── src/pocket_tts_mcp/              Python MCP source
│   ├── pyproject.toml                   declares mcp + httpx + pocket-tts deps
│   ├── uv.lock
│   └── install.sh                       standalone installer (option B)
├── README.md
└── LICENSE
```

## Versioning

| Version | Highlights |
|---|---|
| **0.3.0** | Non-blocking `speak()` + internal playback queue + `stop_speaking()` tool. `status()` exposes queue depth and last error. Skill calls `stop_speaking()` at the start of every turn. |
| 0.2.0     | Bundles the `pocket-tts` CLI as a dependency — no separate `uv tool install` required. Pinned Python `>=3.10,<3.14` (PyTorch wheels). |
| 0.1.0     | Initial plugin form (manifest + marketplace + bundled MCP + skill). |

## Uninstall

If installed as a plugin:
```
/plugin uninstall pocket-tts@vincweb-tools
/plugin marketplace remove vincweb-tools
```

If installed standalone:
```bash
rm -rf ~/.claude/skills/voice-mode
# Remove the "pocket-tts" entry from your project's .mcp.json
rm -rf ~/path/to/pocket-tts-mcp   # the clone
```

## Why this and not the alternatives

| Path | Pros | Cons |
|---|---|---|
| ElevenLabs MCP | Best quality | Cloud, API key, costs |
| macOS `say` MCP | Free, instant | Robotic voice |
| Hook + regex extraction of `<speak>` tags | No MCP needed | Fragile: transcript parsing, race conditions, debugging hell |
| **This** | Local, free, real voices, non-blocking, packaged as a plugin | First-call latency ~10 s, voice synthetic (Kyutai's lightweight model — not ElevenLabs-grade) |

If you want higher voice quality and don't mind a heavier setup, the bigger
[Kyutai TTS 1.6B](https://huggingface.co/kyutai/tts-1.6b-en_fr) or
[Mistral Voxtral TTS](https://mistral.ai/news/voxtral-tts) are worth a look —
the same plugin architecture would adapt to them by swapping the daemon.

## License

MIT — see [LICENSE](LICENSE).

## Credits

- [Kyutai Labs](https://kyutai.org/) for Pocket TTS — the actual hard work
- [Anthropic](https://anthropic.com/) for Claude Code & the MCP spec
- This wrapper: just glue
