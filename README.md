# pocket-tts-mcp

Local-only voice for Claude Code on macOS, via [Kyutai Pocket TTS](https://github.com/kyutai-labs/pocket-tts).
No cloud, no API keys, no rate limits.

- 🇫🇷 French (Estelle), 🇬🇧 English (Alba), plus Spanish, German, Italian, Portuguese
- **TTFA ~80–200 ms** thanks to native streaming via the pocket-tts Python API
- ~4-5× real-time generation on Apple Silicon / Intel CPU — model stays warm in RAM
- Non-blocking `speak()`, gap-free playback via `sounddevice` write-mode
- Bundled `/voice-mode` skill — Claude speaks summaries of its answers automatically
- ~600 MB venv, ~1 GB model cache — lightweight relative to bigger TTS models

> 💡 Companion plugin: [**voxtral-mcp**](https://github.com/Vincweb/voxtral-mcp)
> wraps Mistral Voxtral 4B (more natural voice but 5× more RAM and Apple Silicon
> only). See the [comparison table](#pocket-tts-mcp-vs-voxtral-mcp) below — both
> plugins share the same MCP API and `/voice-mode` skill.

## Requirements

- macOS (Apple Silicon recommended; Intel works too — model is CPU-only)
- [uv](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Claude Code (CLI, desktop app, or Cursor extension)

## Install — option A: Claude Code plugin (recommended)

```
/plugin marketplace add Vincweb/pocket-tts-mcp
/plugin install pocket-tts@vincweb-tools
```

Restart Claude Code. On first use, `uv run` materializes the Python venv (~30 s)
and the Kyutai model downloads from Hugging Face (~1 GB, once per language).
Subsequent runs are instant.

## Install — option B: standalone (no plugin system)

```bash
git clone https://github.com/Vincweb/pocket-tts-mcp.git
cd pocket-tts-mcp/plugin
./install.sh
```

The script `uv sync`'s the venv and prints the `.mcp.json` snippet to paste
into your project. You'll also need to copy `plugin/skills/voice-mode/SKILL.md`
to `~/.claude/skills/voice-mode/SKILL.md`. Then restart Claude Code.

## Use

In any conversation, type **`/voice-mode`** or say **"parle-moi"** / **"voice mode"**.
Claude will:

- Reply with normal text (markdown, code, links — unchanged)
- Call `stop_speaking()` at the start of each turn to drop any audio still
  playing from the previous turn (prevents desync between text and voice)
- Call `speak()` with a short spoken summary of the turn (1–3 sentences,
  audio plays in the background while Claude continues with other work)
- Skip speaking pure code dumps / long diffs

Stop with **"mute"**, **"silence"**, **"stop talking"**, **"arrête de parler"**.

The first call after a Claude Code restart takes ~3–5 s (model load).
Subsequent calls have **~80–200 ms TTFA** thanks to native streaming — you
hear the start of the audio almost immediately, even on long texts.

## MCP tools exposed

| Tool | Purpose |
|---|---|
| `speak(text, voice?)` | Generate audio for `text` and **queue it for background playback**. Returns immediately; streaming generation feeds the audio stream while you keep working. Multiple calls queue and play sequentially — no overlap. |
| `stop_speaking()` | Stop the currently-playing audio, drop everything queued behind it, and cancel any in-flight generation. Use at the start of a new turn to clear stale audio. |
| `status()` | Report model load state, sample rate, cached voices, queue depths, last error. |

## Configuration

Set in the `env` block of the MCP entry (`.mcp.json`):

| Variable | Default | Notes |
|---|---|---|
| `POCKET_TTS_LANGUAGE` | `french_24l` | Also: `english`, `english_2026-01`, `english_2026-04`, `spanish_24l`, `german_24l`, `italian_24l`, `portuguese_24l` |
| `POCKET_TTS_VOICE` | (language default) | Built-in voice name to use when `speak()` is called without an explicit `voice` arg |
| `POCKET_TTS_DEVICE` | `cpu` | PyTorch device. Stick with `cpu` on Apple Silicon — `mps` is unsupported by the pocket-tts model. |
| `POCKET_TTS_QUANTIZE` | `0` | Set to `1` for int8 quantization (smaller RAM, slightly slower). |
| `POCKET_TTS_MAX_TOKENS` | `50` | Max tokens per streaming chunk. |

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

You can also pass any Hugging Face voice URL (`hf://...`) or a path to a `.wav` file
for voice cloning — pocket-tts builds the voice state from the audio prompt on first
use, then caches it for subsequent calls.

## Architecture (v0.4.0)

```
Claude Code  ──MCP stdio──▶  pocket-tts-mcp (Python, FastMCP)
                                  │
                                  │  speak(text)
                                  ▼
                              gen queue
                                  │
                                  ▼
                       generation thread
                            tts_model.generate_audio_stream(...)
                            yields torch.Tensor chunks (~80 ms each)
                                  │
                                  ▼
                          audio_q (numpy float32)
                                  │
                                  ▼
                       writer thread → stream.write() blocking
                                  │
                                  ▼
                       sounddevice OutputStream (write-mode)
                                  │
                                  ▼
                              CoreAudio
```

Key design choices:

- **In-process model**: pocket-tts is loaded directly via `TTSModel.load_model()`.
  No external daemon, no HTTP, no temp WAVs, no `afplay` subprocess.
- **Native streaming**: chunks are produced by `generate_audio_stream` as the
  model generates — first chunk arrives in ~80–200 ms, the rest stream in
  while playback is already happening.
- **Write-mode sounddevice**: the OutputStream is opened WITHOUT a callback,
  so a Python writer thread calls `stream.write(chunk)` in blocking mode.
  PortAudio's internal buffer absorbs all timing variation, and Python never
  has to meet realtime deadlines — yielding clean, gap-free playback.
- **Voice state cache**: `_voice_states` maps voice name → state, so the
  expensive `get_state_for_audio_prompt` call only runs once per voice.

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
│   ├── pyproject.toml                   declares mcp + pocket-tts + sounddevice deps
│   ├── uv.lock
│   └── install.sh                       standalone installer (option B)
├── README.md
└── LICENSE
```

## Versioning

| Version | Highlights |
|---|---|
| **0.4.0** | **In-process model + native streaming + write-mode sounddevice.** Drops the `pocket-tts serve` HTTP daemon entirely. TTFA drops from ~3 s to ~80–200 ms. Mirrors the [voxtral-mcp](https://github.com/Vincweb/voxtral-mcp) v0.4.0 architecture. |
| 0.3.0     | Non-blocking `speak()` + internal playback queue + `stop_speaking()` tool (still daemon-backed). |
| 0.2.0     | Bundles the `pocket-tts` CLI as a dependency. Pinned Python `>=3.10,<3.14`. |
| 0.1.0     | Initial plugin form (marketplace + plugin manifest + bundled MCP + skill). |

## pocket-tts-mcp vs voxtral-mcp

Both plugins ship with the same MCP API (`speak`, `stop_speaking`, `status`),
the same `/voice-mode` skill, and the same in-process Python + sounddevice
write-mode pipeline (v0.4.0 on both sides). They differ in the model they
wrap:

|   | **pocket-tts-mcp** | [**voxtral-mcp**](https://github.com/Vincweb/voxtral-mcp) |
|---|---|---|
| Model | Kyutai Pocket TTS | Mistral Voxtral 4B |
| Parameters | ~100 M | 4 B (40× larger) |
| Voice quality | Synthetic but intelligible | More natural prosody |
| **TTFA** (post-load) | **~80–200 ms** ⭐ | ~2 s |
| Generation speed | ~4–5× real-time | ~2.4× real-time |
| Resident RAM | ~1 GB | ~3 GB |
| Disk (model cache) | ~1 GB | ~2.5 GB |
| Apple Silicon required | No (works on Intel too) | Yes (MLX-only) |
| Languages | EN, FR, ES, DE, IT, PT | EN, FR, ES, DE, IT, PT, NL, HI, AR |
| Model licence | Permissive (Kyutai) | CC BY-NC 4.0 (non-commercial) |
| Architecture | In-process via PyTorch | In-process via mlx-audio |

**When to pick which:**

- **pocket-tts-mcp** for snappy short summaries (TTFA matters more than
  prosody on 1–3 sentences), low RAM footprint, multi-project workflows
  where Cursor might hold multiple MCP instances, permissive licensing,
  Intel Macs.
- **voxtral-mcp** for long narration where the voice quality difference
  is audible and you can spare 3 GB of RAM.

You can install **both** plugins side-by-side — the MCP server names
differ (`pocket-tts` vs `voxtral`) so the tools won't collide. The shared
`/voice-mode` skill defaults to voxtral when both are available; you can
override at runtime by asking Claude to "use pocket-tts" or "use voxtral".

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
# Optionally delete the cached model:
rm -rf ~/.cache/huggingface/hub/models--kyutai--pocket-tts
```

## Why this and not the alternatives

| Path | Pros | Cons |
|---|---|---|
| ElevenLabs MCP | Best quality | Cloud, API key, costs |
| macOS `say` MCP | Free, instant | Robotic voice |
| Hook + regex extraction of `<speak>` tags | No MCP needed | Fragile: transcript parsing, race conditions, debugging hell |
| [voxtral-mcp](https://github.com/Vincweb/voxtral-mcp) | More natural voice, 9 languages | 3× the RAM, ~10× slower TTFA, non-commercial licence, Apple Silicon only |
| **This (pocket-tts-mcp)** | Local, free, fastest local TTFA, permissive licence, ~1 GB total footprint | Voice is synthetic — not ElevenLabs / Voxtral level |

## License

MIT — see [LICENSE](LICENSE).

## Credits

- [Kyutai Labs](https://kyutai.org/) for Pocket TTS — the actual hard work
- [Anthropic](https://anthropic.com/) for Claude Code & the MCP spec
- This wrapper: just glue
