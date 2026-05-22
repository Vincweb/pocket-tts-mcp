# pocket-tts-mcp

Local-only voice for Claude Code on macOS, via [Kyutai Pocket TTS](https://github.com/kyutai-labs/pocket-tts).
No cloud, no API keys, no rate limits.

- 🇫🇷 French (Estelle), 🇬🇧 English (Alba), plus Spanish, German, Italian, Portuguese
- ~5× real-time on Apple Silicon CPU — model stays warm in RAM between calls
- One MCP tool: `speak(text, voice?)` — Claude calls it when you ask for spoken replies
- Bundled `/voice-mode` skill — Claude speaks summaries of its answers automatically

Ships as a Claude Code **plugin** (with a bundled MCP server + skill) and also
works as a standalone MCP server for users who don't use the plugin system.

## Requirements

- macOS (Apple Silicon recommended; Intel works too)
- [uv](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Claude Code (CLI, desktop app, or Cursor extension)

## Install — option A: Claude Code plugin (recommended)

```
/plugin marketplace add Vincweb/pocket-tts-mcp
/plugin install pocket-tts@vincweb-tools
```

That's it. The plugin ships the MCP server, the `/voice-mode` skill, and the
right wiring. The first `speak()` call will trigger `uv run` to materialize the
Python venv (~30 s on a fresh install), then it's fast.

## Install — option B: standalone (no plugin system)

```bash
git clone https://github.com/Vincweb/pocket-tts-mcp.git
cd pocket-tts-mcp/plugin
./install.sh
```

The script:
1. `uv tool install pocket-tts` (Kyutai CLI, model downloads lazily on first generate)
2. `uv sync` to materialize the MCP server's venv at `plugin/.venv/`
3. Prints the `.mcp.json` snippet to paste into your project

You'll need to manually:
- Add the printed `.mcp.json` entry to your project's `.mcp.json` (or `~/.claude.json`)
- Copy `plugin/skills/voice-mode/SKILL.md` to `~/.claude/skills/voice-mode/SKILL.md`

Then restart Claude Code.

## Use

In any conversation, type **`/voice-mode`** (or `/pocket-tts:voice-mode` if installed
as a plugin), or just say **"parle-moi"** / **"voice mode"**. Claude will:

- Reply with normal text (markdown, code, links — unchanged)
- *Also* call `speak()` with a short spoken summary of each turn
- Skip speaking pure code dumps / long diffs

Stop with **"mute"**, **"silence"**, **"stop talking"**, **"arrête de parler"**.

The first call after a Claude Code restart takes ~10–15 s (model load). Subsequent calls are <1 s.

## Configuration

Set in the `env` block of the MCP entry:

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
                                  │  POST /tts (multipart)
                                  ▼
                            pocket-tts serve  ──▶  WAV bytes
                            (FastAPI, model in RAM)     │
                                                        ▼
                                                      afplay
```

The MCP server **spawns `pocket-tts serve` as a subprocess on first use** and
tears it down on shutdown (via `atexit`). One model load per Claude Code session.

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
│   ├── pyproject.toml
│   ├── uv.lock
│   └── install.sh                       standalone installer (option B)
├── README.md
└── LICENSE
```

## Uninstall

If installed as a plugin:
```
/plugin uninstall pocket-tts@vincweb-tools
/plugin marketplace remove vincweb-tools
```

If installed standalone:
```bash
uv tool uninstall pocket-tts
rm -rf ~/.claude/skills/voice-mode
# Remove the "pocket-tts" entry from your .mcp.json
rm -rf ~/path/to/pocket-tts-mcp   # this repo
```

## Why this and not the alternatives

| Path | Pros | Cons |
|---|---|---|
| ElevenLabs MCP | Best quality | Cloud, API key, costs |
| macOS `say` MCP | Free, instant | Robotic voice |
| Hook + regex extraction of `<speak>` tags | No MCP needed | Fragile: transcript parsing, race conditions, debugging hell |
| **This** | Local, free, real voices, Claude controls when to speak, packaged as a plugin | First-call latency ~10 s |

## License

MIT — see [LICENSE](LICENSE).

## Credits

- [Kyutai Labs](https://kyutai.org/) for Pocket TTS — the actual hard work
- [Anthropic](https://anthropic.com/) for Claude Code & the MCP spec
- This wrapper: just glue
