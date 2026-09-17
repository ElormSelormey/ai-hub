# YO AI (`ai-hub`) ⚡

> **One command. Every model.**  
> A terminal-native hub, workspace router, and interactive Cyberpunk TUI dashboard for managing all your AI CLI coding assistants.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-purple)

---

## ✨ Features

- 🎛️ **Cyberpunk TUI Launcher**: Interactive terminal dashboard matching modern terminal themes (e.g. Ghostty). Keyboard navigation (`↑↓` / `jk`), instant model selection, project creation, and log viewing.
- 🔄 **Cross-Model Project Continuity**: Rate-limited on Gemini? Open `yo`, pick Grok or Claude, and launch directly inside the exact same codebase directory!
- 🌉 **Automatic Context Bridge (`.ai-context.md`)**: Automatically writes workspace metadata, timestamp, and git status summary when switching between models so incoming AI agents pick up right where the last one left off.
- 🚀 **Auto-Discovery & Fast Version Probing**: Scans system `PATH` for binaries (`grok`, `gemini`, `claude`, `codex`, `kimi`, `agy`), probes version strings asynchronously, and caches results.
- 📊 **Execution Logging & Auditing**: Tracks execution durations, exit codes, process IDs, and command arguments in centralized `logs/hub.jsonl` and tool-specific daily logs.
- ⚡ **Zsh Autocompletions**: Full tab-completion support for commands, tools, and subcommands.

---

## 🛠️ Supported AI CLI Assistants

| Tool ID | Name | Vendor |
| :--- | :--- | :--- |
| **`grok`** | Grok Build | xAI |
| **`gemini`** | Gemini CLI | Google |
| **`claude`** | Claude Code | Anthropic |
| **`codex`** | Codex | OpenAI |
| **`kimi`** | Kimi Code | Moonshot |
| **`agy`** | Antigravity | Antigravity |

*Custom tools can also be registered dynamically via `yo add`.*

---

## 🚀 Quick Start

### Installation

Clone the repository to `~/ai-hub` and add `bin/` to your shell `PATH`:

```bash
git clone https://github.com/ElormSelormey/ai-hub.git ~/ai-hub
export PATH="$HOME/ai-hub/bin:$PATH"
```

### Usage

```bash
# Open interactive Cyberpunk TUI menu
yo

# Launch an AI CLI directly in current directory
yo grok
yo claude
yo gemini

# Workspaces & Projects
yo here claude      # Launch Claude in current directory
yo hub claude       # Launch Claude in shared projects hub
yo new claude myapp # Create a new project directory & launch

# Management & Health Check
yo doctor           # Run environment & executable health check
yo list             # List registered tools, versions, and paths
yo status           # Display system status & project counts
yo logs [tool]      # View launch history and execution times
yo add <id> [flags] # Register a new custom AI CLI tool
yo rm <id>          # Unregister a tool
```

---

## 🧪 Testing

Run the automated unit test suite:

```bash
python3 tests/test_hub.py
```
or
```bash
python3 -m unittest discover -s tests
```

---

## 📄 License

MIT License.
