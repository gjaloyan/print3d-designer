"""Install the print3d-designer skill for one or more AI agents.

Usage:
    python install.py                          # Claude Code (~/.claude/skills), then the Python setup
    python install.py --agent codex --agent hermes-agent
    python install.py --dest PATH              # any other agent: the folder it loads skills from
    python install.py --list                   # the agents this script knows
    python install.py --no-setup               # copy the files only

Other options (--python, --home, --no-test) go to scripts/setup.py, which
builds one Python environment (~/.print3d/venv) for every agent. An existing
copy of the skill is moved to ~/.print3d/backups/ first; its machine-local
config/ folder is carried over. Agent folders follow the agent table of the
`skills` CLI (github.com/vercel-labs/skills).
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = ROOT / "skills" / "print3d-designer"
AGENTS = {  # agent id -> global skills folder
    "claude-code": "~/.claude/skills",
    "codex": "~/.agents/skills",
    "cursor": "~/.cursor/skills",
    "gemini-cli": "~/.gemini/skills",
    "github-copilot": "~/.copilot/skills",
    "opencode": "~/.config/opencode/skills",
    "windsurf": "~/.codeium/windsurf/skills",
    "hermes-agent": os.environ.get("HERMES_HOME", "~/.hermes") + "/skills/creative",
    "openclaw": "~/.openclaw/skills",
    "goose": "~/.config/goose/skills",
    "amp": "~/.config/agents/skills",
    "roo": "~/.roo/skills",
    "kiro-cli": "~/.kiro/skills",
}


def install(folder: Path) -> Path:
    target = folder / SKILL.name
    if target.resolve() == SKILL.resolve():
        raise SystemExit(f"{target} is this repository's own copy; pick another folder")
    config = None
    if target.exists() or target.is_symlink():
        backup = Path.home() / ".print3d" / "backups" / f"{SKILL.name}-{time.strftime('%Y%m%d-%H%M%S')}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(backup))
        print(f"  previous copy moved to {backup}")
        config = backup / "config" if (backup / "config").is_dir() else None
    shutil.copytree(SKILL, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if config:
        shutil.copytree(config, target / "config")
    return target


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the child processes
    parser = argparse.ArgumentParser(description="Install the print3d-designer skill for AI agents.")
    parser.add_argument("--agent", action="append", choices=sorted(AGENTS), metavar="ID",
                        help="agent to install for (repeatable; --list shows them). Default: claude-code")
    parser.add_argument("--dest", action="append", type=Path, default=[],
                        help="another agent's skills folder (repeatable)")
    parser.add_argument("--list", action="store_true", help="show the known agents and their folders")
    parser.add_argument("--no-setup", action="store_true", help="copy the files only, skip scripts/setup.py")
    args, setup_args = parser.parse_known_args()

    if args.list:
        for agent, folder in AGENTS.items():
            print(f"{agent:15} {Path(folder).expanduser()}")
        return 0
    agents = args.agent or ([] if args.dest else ["claude-code"])
    for folder in [Path(AGENTS[a]).expanduser() for a in agents] + [d.expanduser() for d in args.dest]:
        folder.mkdir(parents=True, exist_ok=True)
        print(f"installed {install(folder)}")
    if args.no_setup:
        print(f"Python setup skipped; run it later: python {SKILL / 'scripts' / 'setup.py'}")
        return 0
    return subprocess.run([sys.executable, str(SKILL / "scripts" / "setup.py"), *setup_args]).returncode


if __name__ == "__main__":
    sys.exit(main())
