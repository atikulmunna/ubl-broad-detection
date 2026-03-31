"""Pipe JSON logs through this for human-readable local dev output.

Usage: python main.py 2>&1 | python scripts/devlog.py
"""
import sys, json

COLORS = {'DEBUG': '\033[90m', 'INFO': '\033[36m', 'WARNING': '\033[33m', 'ERROR': '\033[31m', 'CRITICAL': '\033[1;31m'}
RESET = '\033[0m'

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
        ts = d.get('timestamp', '')[11:]
        lvl = d.get('level', '')
        color = COLORS.get(lvl, '')
        msg = d.get('message', '')
        if isinstance(msg, dict):
            msg = json.dumps(msg, indent=2)
        print(f"{ts} {color}{lvl[:4]}{RESET} {msg}")
        if 'exception' in d:
            print(f"  {d['exception']}")
    except (json.JSONDecodeError, ValueError):
        print(line)
