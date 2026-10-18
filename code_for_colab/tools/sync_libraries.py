#!/usr/bin/env python3
"""Bulk download & sync official and community libraries for KiCad, Qucs-S, and SPICE models."""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / 'libraries'

REPOSITORIES = {
    'kicad-symbols': {
        'url': 'https://gitlab.com/kicad/libraries/kicad-symbols.git',
        'dest': LIB_DIR / 'kicad' / 'official' / 'symbols',
        'category': 'kicad'
    },
    'kicad-footprints': {
        'url': 'https://gitlab.com/kicad/libraries/kicad-footprints.git',
        'dest': LIB_DIR / 'kicad' / 'official' / 'footprints',
        'category': 'kicad'
    },
    'digikey-kicad-library': {
        'url': 'https://github.com/Digi-Key/digikey-kicad-library.git',
        'dest': LIB_DIR / 'kicad' / 'community' / 'digikey',
        'category': 'community'
    },
    'sparkfun-kicad-library': {
        'url': 'https://github.com/sparkfun/SparkFun-KiCad-Libraries.git',
        'dest': LIB_DIR / 'kicad' / 'community' / 'sparkfun',
        'category': 'community'
    },
    'seeed-opl-kicad-library': {
        'url': 'https://github.com/Seeed-Studio/OPL_Kicad_Library.git',
        'dest': LIB_DIR / 'kicad' / 'community' / 'seeed',
        'category': 'community'
    },
    'qucs-s': {
        'url': 'https://github.com/ra3xdh/qucs_s.git',
        'dest': LIB_DIR / 'qucs_s',
        'category': 'qucs'
    }
}

def sync_repo(name: str, config: dict):
    url = config['url']
    dest: Path = config['dest']
    dest.parent.mkdir(parents=True, exist_ok=True)
    if (dest / '.git').exists():
        print(f"[*] Updating {name} at {dest}...")
        res = subprocess.run(['git', '-C', str(dest), 'pull', '--ff-only'], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[!] Warning: git pull failed for {name}: {res.stderr.strip()}", file=sys.stderr)
        else:
            print(f"[+] Updated {name}")
    else:
        print(f"[*] Cloning {name} (shallow --depth 1) from {url}...")
        res = subprocess.run(['git', 'clone', '--depth', '1', url, str(dest)], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[!] Error cloning {name}: {res.stderr.strip()}", file=sys.stderr)
            return False
        print(f"[+] Successfully cloned {name} into {dest}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Bulk download electronic component libraries")
    parser.add_argument('--targets', nargs='*', choices=list(REPOSITORIES.keys()) + ['all', 'kicad', 'community', 'qucs'], default=['all'])
    args = parser.parse_args()

    targets_to_run = set()
    for t in args.targets:
        if t == 'all':
            targets_to_run.update(REPOSITORIES.keys())
        elif t in ['kicad', 'community', 'qucs']:
            targets_to_run.update(k for k, v in REPOSITORIES.items() if v['category'] == t)
        elif t in REPOSITORIES:
            targets_to_run.add(t)

    print(f"[*] Starting synchronization for targets: {', '.join(sorted(targets_to_run))}")
    for name in sorted(targets_to_run):
        sync_repo(name, REPOSITORIES[name])
    print("[*] Sync completed.")

if __name__ == '__main__':
    main()
