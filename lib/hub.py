#!/usr/bin/env python3
"""YO AI — stylish launcher for every AI CLI on this machine."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import termios
import time
import tty
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
HUB_HOME = Path(os.environ.get("AI_HUB_HOME", Path(__file__).resolve().parent.parent))
CONFIG_PATH = HUB_HOME / "config.json"
HUB_LOG = HUB_HOME / "logs" / "hub.jsonl"
CACHE_PATH = HUB_HOME / "logs" / "which-cache.json"
SHARED_PROJECTS_DIR = HUB_HOME / "projects"
RESERVED = {
    "ai",
    "menu",
    "hub",
    "list",
    "status",
    "doctor",
    "logs",
    "open",
    "projects",
    "new",
    "here",
    "add",
    "rm",
    "remove",
    "help",
    "version",
    "--help",
    "-h",
    "--version",
    "-V",
    "--dump",
}

# Cyberpunk palette — matches Ghostty theme ~/.config/ghostty/themes/Cyberpunk
CYAN = "#21f6bc"
PINK = "#ff7092"
BLUE = "#00bfff"
PURPLE = "#df95ff"
YELLOW = "#fffa6a"
GREEN = "#00fbac"
ICE = "#86cbfe"
WHITE = "#e5e5e5"
MUTED = "#9b93b8"
DIMC = "#6e6588"
SEL_BG = "#4a3d73"
BAR = "#1a1430"
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
ITAL = "\x1b[3m"
HIDE = "\x1b[?25l"
SHOW = "\x1b[?25h"
ALT_ON = "\x1b[?1049h"
ALT_OFF = "\x1b[?1049l"
CLEAR = "\x1b[2J\x1b[H"
HOME = "\x1b[H"

TAGLINES = (
    "one command. every model.",
    "pick your fighter.",
    "models on deck.",
    "summon something dangerous.",
    "the switchboard for your agents.",
)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def fg(hex_color: str) -> str:
    r, g, b = _rgb(hex_color)
    return f"\x1b[38;2;{r};{g};{b}m"


def bg(hex_color: str) -> str:
    r, g, b = _rgb(hex_color)
    return f"\x1b[48;2;{r};{g};{b}m"


def paint(text: str, color: str, *, bold: bool = False, dim: bool = False, ital: bool = False) -> str:
    out = fg(color)
    if bold:
        out += BOLD
    if dim:
        out += DIM
    if ital:
        out += ITAL
    return f"{out}{text}{RESET}"


def visible_len(s: str) -> int:
    return len(re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", s))


def pad(s: str, width: int, align: str = "left") -> str:
    n = visible_len(s)
    if n >= width:
        return s
    gap = width - n
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def clip(s: str, width: int) -> str:
    if visible_len(s) <= width:
        return s
    raw = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", s)
    return raw[: max(0, width - 1)] + "…"


def term_size() -> tuple[int, int]:
    try:
        size = shutil.get_terminal_size(fallback=(80, 24))
        return max(60, size.columns), max(18, size.lines)
    except OSError:
        return 80, 24


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(ts: datetime | None = None) -> str:
    return (ts or now_utc()).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel_time(ts: str | None) -> str:
    if not ts:
        return "never"
    try:
        then = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return "—"
    sec = int((now_utc() - then).total_seconds())
    if sec < 10:
        return "just now"
    if sec < 60:
        return f"{sec}s ago"
    if sec < 3600:
        return f"{sec // 60}m ago"
    if sec < 86400:
        return f"{sec // 3600}h ago"
    days = sec // 86400
    return f"{days}d ago"


def tagline() -> str:
    return TAGLINES[datetime.now().timetuple().tm_yday % len(TAGLINES)]


@dataclass
class Tool:
    id: str
    name: str
    bin: str
    vendor: str
    tagline: str
    color: str
    enabled: bool = True
    path: str | None = None
    version: str = ""
    last_used: str | None = None
    projects: list[str] = field(default_factory=list)

    @property
    def live(self) -> bool:
        return bool(self.path) and self.enabled

    @property
    def root(self) -> Path:
        return HUB_HOME / self.id

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"


def default_tools() -> list[dict]:
    return [
        {
            "id": "grok",
            "name": "Grok Build",
            "bin": "grok",
            "vendor": "xAI",
            "tagline": "agents, skills, worktrees — the full TUI",
            "color": BLUE,
            "enabled": True,
        },
        {
            "id": "gemini",
            "name": "Gemini CLI",
            "bin": "gemini",
            "vendor": "Google",
            "tagline": "interactive Gemini, MCP, extensions",
            "color": ICE,
            "enabled": True,
        },
        {
            "id": "claude",
            "name": "Claude Code",
            "bin": "claude",
            "vendor": "Anthropic",
            "tagline": "terminal-native Claude agent",
            "color": "#d97706",
            "enabled": True,
        },
        {
            "id": "codex",
            "name": "Codex",
            "bin": "codex",
            "vendor": "OpenAI",
            "tagline": "OpenAI's coding agent in the shell",
            "color": GREEN,
            "enabled": True,
        },
        {
            "id": "kimi",
            "name": "Kimi Code",
            "bin": "kimi",
            "vendor": "Moonshot",
            "tagline": "the starting point for next-gen agents",
            "color": PURPLE,
            "enabled": True,
        },
        {
            "id": "agy",
            "name": "Antigravity",
            "bin": "agy",
            "vendor": "Antigravity",
            "tagline": "agent CLI with projects and modes",
            "color": PINK,
            "enabled": True,
        },
    ]


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            if isinstance(data, dict) and data.get("tools"):
                return data
        except json.JSONDecodeError:
            pass
    data = {"brand": "YO AI", "default_workspace": "ask", "tools": default_tools()}
    save_config(data)
    return data


def save_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n")


def ensure_layout(tools: list[Tool]) -> None:
    for sub in ("bin", "lib", "completions", "logs", "projects"):
        (HUB_HOME / sub).mkdir(parents=True, exist_ok=True)
    for tool in tools:
        tool.projects_dir.mkdir(parents=True, exist_ok=True)
        tool.logs_dir.mkdir(parents=True, exist_ok=True)
        (tool.root / "sessions").mkdir(parents=True, exist_ok=True)


def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2) + "\n")


def short_version(raw: str) -> str:
    if not raw:
        return "—"
    match = re.search(r"\d+\.\d+(?:\.\d+)?", raw)
    return match.group(0) if match else clip(raw, 12)


def probe_version(path: str) -> str:
    for flag in ("--version", "-V", "version"):
        try:
            proc = subprocess.run(
                [path, flag],
                capture_output=True,
                text=True,
                timeout=4.0,
                env={**os.environ, "NO_COLOR": "1"},
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        text = (proc.stdout or proc.stderr or "").strip()
        if not text:
            continue
        line = text.splitlines()[0].strip()
        if re.match(r"^[\w.-]+\s+\d", line):
            line = re.sub(r"^[\w.-]+\s+", "", line)
        return line[:64]
    return ""


def last_used_map() -> dict[str, str]:
    found: dict[str, str] = {}
    if not HUB_LOG.exists():
        return found
    try:
        for line in HUB_LOG.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            tool = row.get("tool")
            ts = row.get("ts")
            if tool and ts:
                found[tool] = ts
    except OSError:
        return found
    return found


def discover(cfg: dict) -> list[Tool]:
    cache = load_cache()
    used = last_used_map()
    now = time.time()
    tools: list[Tool] = []
    dirty = False
    for raw in cfg.get("tools", default_tools()):
        tool = Tool(
            id=raw["id"],
            name=raw.get("name", raw["id"]),
            bin=raw.get("bin", raw["id"]),
            vendor=raw.get("vendor", ""),
            tagline=raw.get("tagline", ""),
            color=raw.get("color", CYAN),
            enabled=raw.get("enabled", True),
        )
        path = shutil.which(tool.bin)
        tool.path = path
        entry = cache.get(tool.id, {})
        cached_ok = (
            path
            and entry.get("path") == path
            and entry.get("version")
            and now - entry.get("ts", 0) < 3600
        )
        if cached_ok:
            tool.version = entry.get("version", "")
        elif path:
            tool.version = probe_version(path)
            if tool.version:
                cache[tool.id] = {"path": path, "version": tool.version, "ts": now}
                dirty = True
        tool.last_used = used.get(tool.id)
        if tool.projects_dir.exists():
            tool.projects = sorted(
                p.name for p in tool.projects_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
            )
        tools.append(tool)
    if dirty:
        save_cache(cache)
    return tools


def find_tool(tools: list[Tool], ident: str) -> Tool | None:
    ident = ident.lower()
    for tool in tools:
        if tool.id.lower() == ident or tool.bin.lower() == ident:
            return tool
    return None


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def log_event(tool: Tool, argv: list[str], cwd: Path, *, exit_code: int | None, duration_s: float, pid: int) -> None:
    row = {
        "ts": iso(),
        "tool": tool.id,
        "bin": tool.bin,
        "argv": argv,
        "cwd": str(cwd),
        "exit": exit_code,
        "duration_s": round(duration_s, 3),
        "pid": pid,
    }
    append_jsonl(HUB_LOG, row)
    day = datetime.now().strftime("%Y-%m-%d")
    append_jsonl(tool.logs_dir / f"{day}.jsonl", row)


def read_log_rows(tool_id: str | None, limit: int = 20) -> list[dict]:
    rows: list[dict] = []
    if not HUB_LOG.exists():
        return rows
    for line in HUB_LOG.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if tool_id and row.get("tool") != tool_id:
            continue
        rows.append(row)
    return rows[-limit:]


# ── launch ──────────────────────────────────────────────────────────────────


def splash(tool: Tool, cwd: Path, argv: list[str]) -> None:
    cols, _ = term_size()
    width = min(72, cols)
    line = "─" * (width - 2)
    extra = " ".join(argv[1:]) if len(argv) > 1 else "interactive session"
    print()
    print(paint("  ╭" + line + "╮", tool.color))
    print(
        paint("  │", tool.color)
        + paint(pad(f"  YO AI  ·  launching {tool.name}", width - 2), WHITE, bold=True)
        + paint("│", tool.color)
    )
    print(paint("  │" + " " * (width - 2) + "│", tool.color))
    for label, value in (
        ("tool", f"{tool.vendor} · {tool.bin}"),
        ("bin ", tool.path or "—"),
        ("cwd ", str(cwd)),
        ("args", extra),
        ("log ", str(tool.logs_dir)),
    ):
        body = f"  {paint(label, MUTED)}  {paint(clip(value, width - 12), WHITE)}"
        print(paint("  │", tool.color) + pad(body, width - 2) + paint("│", tool.color))
    print(paint("  ╰" + line + "╯", tool.color))
    print()


def outro(tool: Tool, code: int, duration_s: float) -> None:
    mins, secs = divmod(int(duration_s), 60)
    clock = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
    tone = GREEN if code == 0 else PINK
    print()
    print(
        paint("  ┈ ", DIMC)
        + paint(tool.id, tool.color, bold=True)
        + paint(f"  exited {code}", tone)
        + paint(f"  ·  {clock}  ·  logged → {tool.logs_dir}", MUTED)
    )
    print()


def update_context_bridge(cwd: Path, tool: Tool) -> None:
    context_file = cwd / ".ai-context.md"
    git_status = ""
    try:
        proc = subprocess.run(["git", "status", "--short"], cwd=str(cwd), capture_output=True, text=True, timeout=2)
        git_status = proc.stdout.strip()
    except Exception:
        pass

    content = f"""# AI Handoff Context
- **Last Active Model**: {tool.name} ({tool.vendor})
- **Timestamp**: {iso()}
- **Project Directory**: `{cwd}`

## Workspace Git Status
```
{git_status if git_status else "No uncommitted git changes."}
```

> **Note for AI Assistant**: This project is managed by YO AI. You are continuing work on this codebase. Refer to git logs, existing files, and this document for context.
"""
    try:
        context_file.write_text(content)
    except OSError:
        pass


def launch(tool: Tool, extra: list[str], cwd: Path) -> int:
    if not tool.live:
        print(paint(f"yo: {tool.name} is not on PATH ({tool.bin})", PINK), file=sys.stderr)
        return 127
    cwd.mkdir(parents=True, exist_ok=True)
    update_context_bridge(cwd, tool)
    argv = [tool.path or tool.bin, *extra]
    env = os.environ.copy()
    env.update(
        {
            "AI_HUB_HOME": str(HUB_HOME),
            "AI_HUB_TOOL": tool.id,
            "AI_HUB_ROOT": str(tool.root),
            "AI_HUB_PROJECTS": str(tool.projects_dir),
            "AI_HUB_LOGS": str(tool.logs_dir),
        }
    )
    splash(tool, cwd, argv)
    started = time.time()
    pid = 0
    code = 0
    try:
        proc = subprocess.Popen(argv, cwd=str(cwd), env=env)
        pid = proc.pid
        code = proc.wait()
    except KeyboardInterrupt:
        code = 130
    except OSError as exc:
        print(paint(f"yo: failed to launch {tool.bin}: {exc}", PINK), file=sys.stderr)
        code = 126
    duration = time.time() - started
    log_event(tool, argv, cwd, exit_code=code, duration_s=duration, pid=pid)
    outro(tool, code, duration)
    return code


# ── TUI ─────────────────────────────────────────────────────────────────────


def banner_lines(width: int) -> list[str]:
    art = [
        r"  ██╗   ██╗ ██████╗      █████╗ ██╗",
        r"  ╚██╗ ██╔╝██╔═══██╗    ██╔══██╗██║",
        r"   ╚████╔╝ ██║   ██║    ███████║██║",
        r"    ╚██╔╝  ██║   ██║    ██╔══██║██║",
        r"     ██║   ╚██████╔╝    ██║  ██║██║",
        r"     ╚═╝    ╚═════╝     ╚═╝  ╚═╝╚═╝",
    ]
    colors = [CYAN, CYAN, BLUE, PURPLE, PINK, PINK]
    lines = []
    for i, row in enumerate(art):
        lines.append(pad(paint(row, colors[i], bold=True), width, "center"))
    lines.append("")
    lines.append(pad(paint(tagline(), ICE, ital=True), width, "center"))
    return lines


def frame_top(width: int, title: str) -> str:
    inner = width - 2
    label = f"  {title}  "
    rest = inner - len(label)
    left = rest // 2
    right = rest - left
    return (
        paint("╭", PURPLE)
        + paint("─" * left, DIMC)
        + paint(label, CYAN, bold=True)
        + paint("─" * right, DIMC)
        + paint("╮", PURPLE)
    )


def frame_bot(width: int) -> str:
    return paint("╰" + "─" * (width - 2) + "╯", PURPLE)


def frame_row(width: int, body: str) -> str:
    inner_w = width - 2
    if visible_len(body) > inner_w:
        body = clip(body, inner_w)
    return paint("│", PURPLE) + pad(body, inner_w) + paint("│", PURPLE)


def render_menu(tools: list[Tool], idx: int, width: int, height: int) -> str:
    inner = width
    lines: list[str] = [CLEAR]
    lines.extend(banner_lines(inner))
    lines.append("")
    box_w = min(inner - 4, 88)
    left_pad = max(0, (inner - box_w) // 2)
    gutter = " " * left_pad

    header = (
        "  "
        + pad(paint("#", MUTED), 4)
        + pad(paint("TOOL", MUTED), 16)
        + pad(paint("VENDOR", MUTED), 13)
        + pad(paint("VER", MUTED), 10)
        + pad(paint("STATUS", MUTED), 12)
        + paint("LAST", MUTED)
    )
    lines.append(gutter + frame_top(box_w, "YO AI  ·  select a tool"))
    lines.append(gutter + frame_row(box_w, header))
    lines.append(gutter + frame_row(box_w, paint("  " + "· " * ((box_w - 6) // 2), DIMC)))

    for i, tool in enumerate(tools):
        num = f"{i + 1}"
        status = paint("● live", GREEN) if tool.live else paint("○ missing", PINK)
        name = paint(clip(tool.name, 14), WHITE, bold=True) if tool.live else paint(clip(tool.name, 14), MUTED)
        row = (
            "  "
            + pad(paint(num, YELLOW if i == idx else MUTED, bold=i == idx), 4)
            + pad(name, 16)
            + pad(paint(clip(tool.vendor, 12), ICE if tool.live else DIMC), 13)
            + pad(paint(short_version(tool.version), MUTED), 10)
            + pad(status, 12)
            + paint(rel_time(tool.last_used), MUTED)
        )
        if i == idx:
            sel_row = pad(paint("▸ ", CYAN, bold=True) + row[2:], box_w - 2)
            filled = bg(SEL_BG) + sel_row + RESET
            lines.append(gutter + paint("│", PURPLE) + filled + paint("│", PURPLE))
            nproj = len(tool.projects)
            tag = paint("    " + clip(tool.tagline, box_w - 28), tool.color, ital=True)
            extra = paint(f"  {nproj} project" + ("s" if nproj != 1 else ""), MUTED)
            lines.append(gutter + frame_row(box_w, tag + extra))
        else:
            lines.append(gutter + frame_row(box_w, row))

    live_n = sum(1 for t in tools if t.live)
    foot = paint(f"  {live_n}/{len(tools)} online", GREEN) + paint(f"    hub {HUB_HOME}", DIMC)
    lines.append(gutter + frame_row(box_w, ""))
    lines.append(gutter + frame_row(box_w, foot))
    lines.append(gutter + frame_bot(box_w))
    lines.append("")
    hints = (
        paint(" ↑↓", CYAN, bold=True)
        + paint(" move   ", MUTED)
        + paint("⏎", CYAN, bold=True)
        + paint(" launch   ", MUTED)
        + paint("n", CYAN, bold=True)
        + paint(" new project   ", MUTED)
        + paint("o", CYAN, bold=True)
        + paint(" open folder   ", MUTED)
        + paint("l", CYAN, bold=True)
        + paint(" logs   ", MUTED)
        + paint("q", PINK, bold=True)
        + paint(" quit", MUTED)
    )
    lines.append(pad(hints, width, "center"))
    return "\r\n".join(lines) + "\r\n"


def render_workspace(tool: Tool, options: list[tuple[str, str, Path | None]], idx: int, width: int) -> str:
    box_w = min(width - 4, 80)
    left_pad = max(0, (width - box_w) // 2)
    gutter = " " * left_pad
    lines = [CLEAR]
    lines.append("")
    lines.append(pad(paint(f"where should {tool.name} work?", tool.color, bold=True), width, "center"))
    lines.append(pad(paint(tool.tagline, MUTED, ital=True), width, "center"))
    lines.append("")
    lines.append(gutter + frame_top(box_w, tool.id))
    for i, (key, label, path) in enumerate(options):
        loc = str(path) if path else ""
        body = pad(paint(label, WHITE, bold=True), 22) + paint(clip(loc, box_w - 30), MUTED)
        if i == idx:
            filled = bg(SEL_BG) + paint("▸ ", CYAN, bold=True) + pad(body, box_w - 4) + RESET
            lines.append(gutter + paint("│", PURPLE) + pad(filled, box_w - 2) + paint("│", PURPLE))
        else:
            lines.append(gutter + frame_row(box_w, "  " + body))
    lines.append(gutter + frame_bot(box_w))
    lines.append("")
    lines.append(pad(paint("↑↓ move   ⏎ choose   esc back   q quit", MUTED), width, "center"))
    return "\r\n".join(lines) + "\r\n"


def workspace_options(tool: Tool, here: Path, all_tools: list[Tool] | None = None) -> list[tuple[str, str, Path | None]]:
    opts: list[tuple[str, str, Path | None]] = [
        ("here", "this directory", here),
        ("hub", "shared projects", SHARED_PROJECTS_DIR),
        ("new", "new project…", None),
    ]
    seen_paths = {here.resolve(), SHARED_PROJECTS_DIR.resolve()}

    if SHARED_PROJECTS_DIR.exists():
        for p in sorted(SHARED_PROJECTS_DIR.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                opts.append(("project", f"{p.name} (shared)", p))
                seen_paths.add(p.resolve())

    if all_tools:
        for t in all_tools:
            if t.projects_dir.exists():
                for p in sorted(t.projects_dir.iterdir()):
                    if p.is_dir() and not p.name.startswith(".") and p.resolve() not in seen_paths:
                        label = f"{p.name}" if t.id == tool.id else f"{p.name} [{t.id}]"
                        opts.append(("project", label, p))
                        seen_paths.add(p.resolve())

    return opts


@contextmanager
def raw_terminal():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write(ALT_ON + HIDE)
        sys.stdout.flush()
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write(SHOW + ALT_OFF)
        sys.stdout.flush()


def read_key() -> str:
    ch = sys.stdin.read(1)
    if ch == "\x1b":
        rest = sys.stdin.read(1)
        if rest == "[":
            arrow = sys.stdin.read(1)
            return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(arrow, "esc")
        return "esc"
    if ch in ("\r", "\n"):
        return "enter"
    if ch == "\x03":
        return "ctrl-c"
    if ch == "\x7f":
        return "back"
    return ch


def cooked_input(prompt_text: str) -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    sys.stdout.write(SHOW)
    sys.stdout.flush()
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\r\n" + prompt_text)
        sys.stdout.flush()
        line = sys.stdin.readline()
        return line.strip()
    finally:
        tty.setcbreak(fd)
        sys.stdout.write(HIDE)
        sys.stdout.flush()


def valid_project_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name))


def tui(tools: list[Tool]) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return numbered_fallback(tools)
    idx = 0
    here = Path.cwd()
    selected: Tool | None = None
    ws_idx = 0
    mode = "menu"
    action: tuple[str, Tool | None, Path | None] | None = None

    def draw(frame: str) -> None:
        sys.stdout.write(HOME + frame)
        sys.stdout.flush()

    try:
        with raw_terminal():
            while True:
                cols, rows = term_size()
                if mode == "menu":
                    draw(render_menu(tools, idx, cols, rows))
                else:
                    assert selected is not None
                    opts = workspace_options(selected, here, tools)
                    ws_idx = max(0, min(ws_idx, len(opts) - 1))
                    draw(render_workspace(selected, opts, ws_idx, cols))

                key = read_key()
                if key in ("q", "ctrl-c"):
                    action = ("quit", None, None)
                    break
                if mode == "menu":
                    if key in ("up", "k"):
                        idx = (idx - 1) % len(tools)
                    elif key in ("down", "j"):
                        idx = (idx + 1) % len(tools)
                    elif key.isdigit() and key != "0":
                        n = int(key) - 1
                        if 0 <= n < len(tools):
                            idx = n
                    elif key == "o":
                        action = ("open", tools[idx], tools[idx].root)
                        break
                    elif key == "l":
                        action = ("logs", tools[idx], None)
                        break
                    elif key == "n":
                        selected = tools[idx]
                        if not selected.live:
                            continue
                        name = cooked_input(paint("  project name: ", CYAN))
                        if name and valid_project_name(name):
                            dest = SHARED_PROJECTS_DIR / name
                            dest.mkdir(parents=True, exist_ok=True)
                            action = ("launch", selected, dest)
                            break
                    elif key == "enter":
                        selected = tools[idx]
                        if not selected.live:
                            continue
                        mode = "workspace"
                        ws_idx = 0
                    elif key == "esc":
                        action = ("quit", None, None)
                        break
                else:
                    opts = workspace_options(selected, here, tools)  # type: ignore[arg-type]
                    if key in ("up", "k"):
                        ws_idx = (ws_idx - 1) % len(opts)
                    elif key in ("down", "j"):
                        ws_idx = (ws_idx + 1) % len(opts)
                    elif key in ("esc", "back"):
                        mode = "menu"
                    elif key == "enter":
                        key_id, _, path = opts[ws_idx]
                        if key_id == "new":
                            name = cooked_input(paint("  project name: ", CYAN))
                            if not name or not valid_project_name(name):
                                continue
                            dest = selected.projects_dir / name  # type: ignore[union-attr]
                            dest.mkdir(parents=True, exist_ok=True)
                            action = ("launch", selected, dest)
                            break
                        assert path is not None
                        action = ("launch", selected, path)
                        break
    except KeyboardInterrupt:
        return 0

    if action is None or action[0] == "quit":
        return 0
    kind, tool, path = action
    if kind == "open" and path is not None:
        return open_folder(path)
    if kind == "logs" and tool is not None:
        print_logs(tool.id, 20)
        return 0
    if kind == "launch" and tool is not None and path is not None:
        return launch(tool, [], path)
    return 0


def numbered_fallback(tools: list[Tool]) -> int:
    print(paint("YO AI", CYAN, bold=True) + paint("  ·  select a tool", MUTED))
    print()
    for i, tool in enumerate(tools, 1):
        mark = paint("●", GREEN) if tool.live else paint("○", PINK)
        print(f"  {paint(str(i), YELLOW, bold=True)}  {mark}  {tool.name}  {paint(tool.vendor, MUTED)}")
    print()
    try:
        choice = input(paint("  number (or q): ", CYAN)).strip()
    except EOFError:
        return 0
    if choice.lower() in {"q", "quit", ""}:
        return 0
    if not choice.isdigit() or not (1 <= int(choice) <= len(tools)):
        print(paint("yo: not a valid choice", PINK), file=sys.stderr)
        return 1
    tool = tools[int(choice) - 1]
    if not tool.live:
        print(paint(f"yo: {tool.name} is not on PATH", PINK), file=sys.stderr)
        return 127
    return launch(tool, [], Path.cwd())


def dump_menu(tools: list[Tool]) -> int:
    cols, rows = term_size()
    sys.stdout.write(render_menu(tools, 0, cols, rows))
    return 0


# ── subcommands ─────────────────────────────────────────────────────────────


HELP = f"""
{paint("YO AI", CYAN, bold=True)}  {paint("v" + VERSION, MUTED)}
  one command for every AI CLI on this machine.

{paint("usage", PURPLE, bold=True)}
  yo                 open the menu
  Yo AI              same thing (alias)
  yo <tool> [args]   launch a tool in the current directory
  yo here <tool>     launch in the current directory
  yo hub  <tool>     launch in ~/ai-hub/<tool>/projects
  yo new  <tool> <name>
  yo list            list tools
  yo status          versions, paths, last used
  yo logs [tool]     launch history
  yo projects [tool] list hub projects
  yo open [tool]     open folder in Finder
  yo add  <id> [--bin NAME] [--name NAME] [--vendor VENDOR]
  yo rm   <id>       unregister a tool
  yo doctor          health check
  yo help

{paint("tools on this box", PURPLE, bold=True)}
  grok   gemini   claude   codex   kimi   agy

{paint("folders", PURPLE, bold=True)}
  {HUB_HOME}/<tool>/projects
  {HUB_HOME}/<tool>/logs
  {HUB_HOME}/<tool>/sessions
  {HUB_HOME}/logs/hub.jsonl

{paint("keys in the menu", PURPLE, bold=True)}
  ↑↓ / j k     move          ⏎        launch
  1-9          jump          n        new project
  o            open folder   l        logs
  q            quit
""".lstrip("\n")


def cmd_help(_: list[str], tools: list[Tool]) -> int:
    sys.stdout.write(HELP)
    return 0


def cmd_version(_: list[str], tools: list[Tool]) -> int:
    print(f"yo {VERSION}  ·  {HUB_HOME}")
    return 0


def cmd_list(_: list[str], tools: list[Tool]) -> int:
    print(paint("YO AI", CYAN, bold=True) + paint("  registered tools", MUTED))
    print()
    for tool in tools:
        mark = paint("●", GREEN) if tool.live else paint("○", PINK)
        ver = paint(tool.version or "—", MUTED)
        print(f"  {mark}  {paint(tool.id, tool.color, bold=True)}  {tool.name}  {paint(tool.vendor, ICE)}  {ver}")
        print(f"      {paint(tool.path or 'not on PATH', DIMC)}")
    return 0


def cmd_status(_: list[str], tools: list[Tool]) -> int:
    print(paint("YO AI", CYAN, bold=True) + paint("  status", MUTED))
    print()
    print(f"  hub     {HUB_HOME}")
    print(f"  config  {CONFIG_PATH}")
    print(f"  log     {HUB_LOG}")
    print()
    for tool in tools:
        mark = paint("● live   ", GREEN) if tool.live else paint("○ missing", PINK)
        print(paint(f"  {tool.name}", WHITE, bold=True))
        print(f"    {mark}  {paint(tool.version or '—', MUTED)}")
        print(f"    bin    {tool.path or tool.bin}")
        print(f"    root   {tool.root}")
        print(f"    last   {rel_time(tool.last_used)}")
        print(f"    proj   {len(tool.projects)}")
        print()
    return 0


def cmd_doctor(_: list[str], tools: list[Tool]) -> int:
    print(paint("YO AI", CYAN, bold=True) + paint("  doctor", MUTED))
    print()
    ok = True

    def check(label: str, good: bool, detail: str) -> None:
        nonlocal ok
        mark = paint("ok  ", GREEN) if good else paint("fail", PINK)
        if not good:
            ok = False
        print(f"  {mark}  {label}  {paint(detail, MUTED)}")

    check("python3", True, sys.version.split()[0])
    check("hub home", HUB_HOME.is_dir(), str(HUB_HOME))
    check("config", CONFIG_PATH.is_file(), str(CONFIG_PATH))
    check("yo binary", (HUB_HOME / "bin" / "yo").is_file(), str(HUB_HOME / "bin" / "yo"))
    yo_on_path = shutil.which("yo")
    check("yo on PATH", bool(yo_on_path), yo_on_path or "not found — open a new shell")
    for tool in tools:
        check(tool.id, tool.live, tool.path or f"{tool.bin} not found")
        check(f"{tool.id} projects", tool.projects_dir.is_dir(), str(tool.projects_dir))
        check(f"{tool.id} logs", tool.logs_dir.is_dir(), str(tool.logs_dir))
    print()
    print(paint("  all good." if ok else "  some checks failed.", GREEN if ok else PINK))
    return 0 if ok else 1


def print_logs(tool_id: str | None, limit: int) -> None:
    rows = read_log_rows(tool_id, limit)
    title = tool_id or "all tools"
    print(paint("YO AI", CYAN, bold=True) + paint(f"  logs · {title}", MUTED))
    print()
    if not rows:
        print(paint("  no launches yet. open the menu with `yo`.", MUTED))
        return
    for row in rows:
        ts = row.get("ts", "")
        pretty = ts.replace("T", " ").replace("Z", "")
        code = row.get("exit")
        tone = GREEN if code == 0 else PINK
        dur = row.get("duration_s") or 0
        mins, secs = divmod(int(dur), 60)
        clock = f"{mins}m{secs:02d}s" if mins else f"{secs:.1f}s"
        print(
            f"  {paint(pretty, MUTED)}  {paint(row.get('tool', '?'), CYAN, bold=True)}"
            f"  {paint('exit ' + str(code), tone)}  {paint(clock, MUTED)}"
        )
        print(f"    {paint(row.get('cwd', ''), DIMC)}")


def cmd_logs(args: list[str], tools: list[Tool]) -> int:
    tool_id = None
    if args:
        tool = find_tool(tools, args[0])
        if not tool:
            print(paint(f"yo: unknown tool '{args[0]}'", PINK), file=sys.stderr)
            return 1
        tool_id = tool.id
    print_logs(tool_id, 30)
    return 0


def open_folder(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["open", str(path)], check=False)
    except OSError as exc:
        print(paint(f"yo: could not open {path}: {exc}", PINK), file=sys.stderr)
        return 1
    print(paint("  opened ", MUTED) + paint(str(path), CYAN))
    return 0


def cmd_open(args: list[str], tools: list[Tool]) -> int:
    if not args:
        return open_folder(HUB_HOME)
    tool = find_tool(tools, args[0])
    if not tool:
        print(paint(f"yo: unknown tool '{args[0]}'", PINK), file=sys.stderr)
        return 1
    return open_folder(tool.root)


def cmd_projects(args: list[str], tools: list[Tool]) -> int:
    subset = tools
    if args:
        tool = find_tool(tools, args[0])
        if not tool:
            print(paint(f"yo: unknown tool '{args[0]}'", PINK), file=sys.stderr)
            return 1
        subset = [tool]
    for tool in subset:
        print(paint(tool.name, tool.color, bold=True) + paint(f"  {tool.projects_dir}", MUTED))
        if not tool.projects:
            print(paint("  (empty — `yo new " + tool.id + " <name>`)", DIMC))
        for name in tool.projects:
            print(f"  {paint('▸', CYAN)} {name}")
        print()
    return 0


def cmd_new(args: list[str], tools: list[Tool]) -> int:
    if len(args) < 2:
        print("usage: yo new <tool> <project-name>", file=sys.stderr)
        return 2
    tool = find_tool(tools, args[0])
    if not tool:
        print(paint(f"yo: unknown tool '{args[0]}'", PINK), file=sys.stderr)
        return 1
    name = args[1]
    if not valid_project_name(name):
        print(paint("yo: project names should be letters, numbers, dot, dash, underscore", PINK), file=sys.stderr)
        return 2
    dest = tool.projects_dir / name
    dest.mkdir(parents=True, exist_ok=True)
    print(paint("  created ", GREEN) + paint(str(dest), WHITE))
    extra = args[2:]
    skip = "--no-launch" in extra
    extra = [a for a in extra if a != "--no-launch"]
    if skip or not tool.live:
        return 0
    return launch(tool, extra, dest)


def cmd_here(args: list[str], tools: list[Tool]) -> int:
    if not args:
        print("usage: yo here <tool> [args...]", file=sys.stderr)
        return 2
    tool = find_tool(tools, args[0])
    if not tool:
        print(paint(f"yo: unknown tool '{args[0]}'", PINK), file=sys.stderr)
        return 1
    return launch(tool, args[1:], Path.cwd())


def cmd_hub_launch(args: list[str], tools: list[Tool]) -> int:
    if not args:
        print("usage: yo hub <tool> [args...]", file=sys.stderr)
        return 2
    tool = find_tool(tools, args[0])
    if not tool:
        print(paint(f"yo: unknown tool '{args[0]}'", PINK), file=sys.stderr)
        return 1
    return launch(tool, args[1:], tool.projects_dir)


def cmd_add(args: list[str], tools: list[Tool]) -> int:
    if not args:
        print("usage: yo add <id> [--bin NAME] [--name NAME] [--vendor VENDOR] [--color #hex] [--tagline TEXT]", file=sys.stderr)
        return 2
    ident = args[0].lower()
    if ident in RESERVED:
        print(paint(f"yo: '{ident}' is reserved", PINK), file=sys.stderr)
        return 2
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", ident):
        print(paint("yo: id should be a short lowercase slug", PINK), file=sys.stderr)
        return 2
    kv: dict[str, str | bool] = {}
    rest = args[1:]
    i = 0
    while i < len(rest):
        flag = rest[i]
        mapping = {
            "--bin": "bin",
            "--name": "name",
            "--vendor": "vendor",
            "--color": "color",
            "--tagline": "tagline",
        }
        if flag in mapping and i + 1 < len(rest):
            kv[mapping[flag]] = rest[i + 1]
            i += 2
            continue
        print(paint(f"yo: unknown flag {flag}", PINK), file=sys.stderr)
        return 2
    cfg = load_config()
    existing_tools = cfg.get("tools", [])
    existing_tool = next((t for t in existing_tools if t.get("id") == ident), {})
    item = {
        "id": ident,
        "bin": existing_tool.get("bin", ident),
        "name": existing_tool.get("name", ident),
        "vendor": existing_tool.get("vendor", ""),
        "color": existing_tool.get("color", CYAN),
        "tagline": existing_tool.get("tagline", ""),
        "enabled": existing_tool.get("enabled", True),
        **kv,
    }
    updated_tools = [t for t in existing_tools if t.get("id") != ident]
    updated_tools.append(item)
    cfg["tools"] = updated_tools
    save_config(cfg)
    for sub in ("projects", "logs", "sessions"):
        (HUB_HOME / ident / sub).mkdir(parents=True, exist_ok=True)
    print(paint("  added ", GREEN) + paint(ident, CYAN, bold=True) + paint(f"  → {HUB_HOME / ident}", MUTED))
    return 0


def cmd_rm(args: list[str], tools: list[Tool]) -> int:
    if not args:
        print("usage: yo rm <id>", file=sys.stderr)
        return 2
    ident = args[0].lower()
    cfg = load_config()
    existing_tools = cfg.get("tools", [])
    new_tools = [t for t in existing_tools if t.get("id") != ident]
    if len(new_tools) == len(existing_tools):
        print(paint(f"yo: unknown tool '{ident}'", PINK), file=sys.stderr)
        return 1
    cfg["tools"] = new_tools
    save_config(cfg)
    print(paint("  removed ", GREEN) + paint(ident, CYAN, bold=True) + paint(" from config", MUTED))
    return 0


COMMANDS = {
    "help": cmd_help,
    "--help": cmd_help,
    "-h": cmd_help,
    "version": cmd_version,
    "--version": cmd_version,
    "-V": cmd_version,
    "list": cmd_list,
    "status": cmd_status,
    "doctor": cmd_doctor,
    "logs": cmd_logs,
    "open": cmd_open,
    "projects": cmd_projects,
    "new": cmd_new,
    "here": cmd_here,
    "hub": cmd_hub_launch,
    "add": cmd_add,
    "rm": cmd_rm,
    "remove": cmd_rm,
}


def main(argv: list[str]) -> int:
    cfg = load_config()
    tools = discover(cfg)
    ensure_layout(tools)

    if argv and argv[0] == "--dump":
        return dump_menu(tools)
    if not argv or argv[0].lower() in {"ai", "menu"}:
        if len(argv) >= 2 and argv[1] == "--dump":
            return dump_menu(tools)
        return tui(tools)

    head = argv[0]
    if head in COMMANDS:
        return COMMANDS[head](argv[1:], tools)

    tool = find_tool(tools, head)
    if tool:
        return launch(tool, argv[1:], Path.cwd())

    print(paint(f"yo: unknown command or tool '{head}'", PINK), file=sys.stderr)
    print(paint("    try  yo help   or   yo list", MUTED), file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
