#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_settings
from src.pipeline import run_scan


def main():
    parser = argparse.ArgumentParser(description="Run the daily JLaw Edge scan")
    parser.add_argument("--demo", action="store_true", help="Use deterministic offline demo data")
    args = parser.parse_args()
    result = run_scan(load_settings(), demo=args.demo)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] and result["succeeded"] == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

