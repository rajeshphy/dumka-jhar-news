#!/usr/bin/env python3
"""Generate an English Dumka and Jharkhand daily news brief."""
from __future__ import annotations

import argparse
import os
import sys

try:
    from .ai import fallback_summary, gemini_summary
    from .common import ROOT, SOURCE_CONFIG, parse_simple_yaml, read_env_file
    from .fetch import collect_news
    from .markdown import build_post
except ImportError:
    from ai import fallback_summary, gemini_summary
    from common import ROOT, SOURCE_CONFIG, parse_simple_yaml, read_env_file
    from fetch import collect_news
    from markdown import build_post


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Dumka and Jharkhand news brief.")
    parser.add_argument("--no-ai", action="store_true", help="Use fallback headline digest instead of Gemini.")
    return parser.parse_args()


def main() -> None:
    read_env_file()
    args = parse_args()
    config = parse_simple_yaml(ROOT / SOURCE_CONFIG)
    settings = config.get("settings", {})
    items = collect_news(config)

    if not items:
        raise RuntimeError("No fresh Dumka/Jharkhand news items found after filtering and direct-link resolution.")

    points_per_section = int(settings.get("final_points_per_section", settings.get("points_per_section", 5)))
    api_key = os.environ.get("GEMINI_API_KEY", "")

    used_ai = False
    if api_key and not args.no_ai:
        try:
            summary = gemini_summary(items, api_key, points_per_section, settings)
            used_ai = True
        except Exception as exc:
            print(f"Warning: Gemini failed, using fallback summary: {exc}", file=sys.stderr)
            summary = fallback_summary(items, points_per_section, settings)
    else:
        summary = fallback_summary(items, points_per_section, settings)

    post_path = build_post(summary, items, used_ai, points_per_section)
    print(f"Wrote {post_path}")


if __name__ == "__main__":
    main()
