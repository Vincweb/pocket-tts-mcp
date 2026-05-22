#!/usr/bin/env bash
# One-shot installer for pocket-tts-mcp on macOS.
# - Installs Kyutai pocket-tts (CPU, Apple Silicon friendly)
# - Syncs the MCP server's Python venv
# - Copies the voice-mode skill into ~/.claude/skills/
# - Prints the .mcp.json snippet to add to your project
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

bold "1. Checking prerequisites"

if ! command -v uv >/dev/null 2>&1; then
  warn "uv is not installed. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
ok "uv $(uv --version | awk '{print $2}')"

if ! command -v afplay >/dev/null 2>&1; then
  warn "afplay not found — are you on macOS? This MCP plays audio via afplay."
  exit 1
fi
ok "afplay (macOS audio)"

bold "2. Installing Kyutai pocket-tts (model downloads on first generate)"
uv tool install --python 3.13 pocket-tts >/dev/null
ok "pocket-tts CLI installed"

bold "3. Syncing the MCP server's Python venv (in $REPO_DIR)"
(cd "$REPO_DIR" && uv sync >/dev/null)
ok "venv ready at $REPO_DIR/.venv"
ok "binary: $REPO_DIR/.venv/bin/pocket-tts-mcp"

bold "4. Installing the voice-mode skill"
mkdir -p "$HOME/.claude/skills/voice-mode"
cp "$REPO_DIR/skills/voice-mode/SKILL.md" "$HOME/.claude/skills/voice-mode/SKILL.md"
ok "skill copied to ~/.claude/skills/voice-mode/SKILL.md"

bold "5. Next step — add to your project's .mcp.json"
cat <<EOF

Add this entry to the "mcpServers" object of your project's .mcp.json
(or ~/.claude.json for global use):

{
  "mcpServers": {
    "pocket-tts": {
      "command": "$REPO_DIR/.venv/bin/pocket-tts-mcp",
      "env": {
        "POCKET_TTS_LANGUAGE": "french_24l",
        "POCKET_TTS_PORT": "8765"
      }
    }
  }
}

Then restart Claude Code / Cursor. In any conversation, say "parle-moi" or
type /voice-mode to activate spoken replies.

Available languages: english, french_24l, spanish_24l, german_24l,
                     portuguese_24l, italian_24l
EOF
