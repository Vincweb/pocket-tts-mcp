# Roadmap — pocket-tts-mcp

Current state: v0.4.2 published on GitHub. In-process model, native streaming,
write-mode sounddevice. README and SKILL cleaned up; install order swapped to
MCP-first. No PyPI, no Docker, not submitted to any directory yet.

---

## 1. Publish on PyPI

**Why**: cleanest install UX — `uv tool install pocket-tts-mcp` or
`pipx install pocket-tts-mcp` everywhere. Removes the "clone the repo first"
friction.

**Effort**: ~20 min (account + token + pyproject metadata + `uv publish`).

**Steps**:

1. Create PyPI + TestPyPI accounts, generate API token.
2. In `plugin/pyproject.toml`, add:
   - `readme = "README.md"`
   - `license = { text = "MIT" }`
   - `authors = [{ name = "Vincent Caudron", email = "vincent@volume7.io" }]`
   - `keywords = ["mcp", "tts", "kyutai", "claude", "voice"]`
   - `classifiers = [...]` (Beta, MIT, OS Independent, Python 3.10+, Audio)
   - `[project.urls]` block (Homepage, Repository, Issues)
3. Verify name is free: `curl -sI https://pypi.org/pypi/pocket-tts-mcp/json` returns 404.
4. From `plugin/`: `uv build` then `uv publish --token "$PYPI_TOKEN"`.
5. Test from a fresh shell: `uv tool install pocket-tts-mcp` → `pocket-tts-mcp --help`.

**Then**: update the README to mention the PyPI path as Option A1 (even
simpler than `uv tool install` from git).

**Automate with GitHub Actions OIDC (Trusted Publishing)** once it's stable —
no token to manage, tag `v0.4.3` and CI publishes.

---

## 2. Docker image

**Why**: easy headless / Linux use cases. Pocket-tts is CPU-only PyTorch, so
Docker works fine — Intel/AMD/ARM Linux all good. Useful for non-Mac users
who want pocket-tts behind an MCP-compatible client (or via the FastAPI
serve daemon directly).

**Caveat**: the **MCP transport is stdio**, so a containerised MCP server
needs the client to attach to the container's stdio (`docker run -i ...`).
That's awkward in Claude Code. So Docker is mainly useful for two cases:

- Running `pocket-tts serve` (the HTTP daemon) in a container, then having
  the host-side MCP wrapper talk to it via HTTP. But we just *moved away*
  from that architecture in v0.4.0.
- A standalone REST/WS server image people can run as a microservice. Out
  of scope for this MCP repo but could be a separate `pocket-tts-server`
  repo if there's demand.

**Effort**: low for the image itself (~30 min), but the UX story isn't
clean for an MCP. **Defer** unless someone asks for it.

---

## 3. Use mcp-submit to register on directories

**Why**: passive discoverability. Glama auto-indexes from GitHub (give it a
week), but the long tail of directories (mcp.so, mcpservers.org, Smithery,
PulseMCP, etc.) needs explicit submission. The OSS tool [mcp-submit] pushes
to 10+ in one command.

**Effort**: ~15 min (install tool, run with repo URL, confirm submissions).

**Worth it once**:

- README has a demo (GIF or sample audio link).
- PyPI install is live (so the "install instructions" field in directory
  metadata is trivially fillable).

Otherwise the listings will look empty and unloved.

---

## 4. Make the repo more credible — minimum viable

Without overdoing it (no fake stars, no buzzword salad). Order by ROI:

- **Sample audio in the README** — host a 5-second `estelle.wav` in the
  repo and link to it as an `<audio>` element or via the GitHub raw URL.
  People judge a TTS project by what it sounds like in 5 seconds.
- **Shields.io badges**, restraint: version (PyPI once published), license
  (MIT), Python (3.10-3.13). Skip the build-status badge unless there's
  real CI.
- **CHANGELOG.md** generated from git log. Two lines per version max.
- **GIF or asciinema of `/voice-mode`** in action (Claude Code session).
  Highest signal/effort ratio.
- **One-line tagline in repo description on GitHub** (currently fine, but
  re-verify after PyPI).

Skip for now:

- ❌ Logo / branding (not worth it for a wrapper).
- ❌ A documentation site (README is enough until there's enough surface to
  warrant subpages).
- ❌ Hugging Face Space demo (Voxtral might benefit; pocket-tts is small
  enough that local install is the demo).
- ❌ Discord / community channel.

---

## Priority order (my current best guess)

1. **PyPI publish** — unlocks everything else.
2. **Sample audio + GIF in README** — credibility per-eyeball.
3. **mcp-submit run** — once #1 and #2 are done so listings have content.
4. **Docker** — only if someone asks.
5. **GH Actions OIDC release workflow** — nice once releases are routine.

---

## Open questions

- Should the repo description on GitHub mention "Claude Code plugin" or
  lead with "MCP server"? Currently leads with "Claude Code". Consider
  swapping after README install-order change is live.
- Worth adding a `CITATION.cff` so academic users can cite the wrapper?
  Probably not — they'd cite Kyutai pocket-tts, not the glue.
- Should we provide a tiny benchmark script under `bench/` so users can
  reproduce the TTFA numbers in the README? Yes if asked, no by default.
