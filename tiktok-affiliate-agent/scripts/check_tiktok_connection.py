#!/usr/bin/env python3
"""Check local TikTok Developer connection readiness without printing secrets."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"


REQUIRED_BASE = [
    "TIKTOK_CLIENT_KEY",
    "TIKTOK_CLIENT_SECRET",
    "TIKTOK_REDIRECT_URI",
]

REQUIRED_AUTH = [
    "TIKTOK_ACCESS_TOKEN",
    "TIKTOK_REFRESH_TOKEN",
    "TIKTOK_OPEN_ID",
]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def is_set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def status_line(name: str) -> str:
    return f"[{'ok' if is_set(name) else 'missing'}] {name}"


def main() -> None:
    load_dotenv(ROOT / ".env")
    mode = os.environ.get("TIKTOK_POSTING_MODE", "draft").strip() or "draft"

    print("TikTok Developer connection readiness")
    print(f"Project: {ROOT}")
    print(f"Posting mode: {mode}")
    print()

    print("App settings")
    for name in REQUIRED_BASE:
        print(status_line(name))

    print()
    print("Authorized account tokens")
    for name in REQUIRED_AUTH:
        print(status_line(name))

    print()
    if all(is_set(name) for name in REQUIRED_BASE + REQUIRED_AUTH):
        print("Ready for API smoke testing. Do not run public posting until approval gates pass.")
    elif all(is_set(name) for name in REQUIRED_BASE):
        print("Developer app settings are present. Next step: authorize @thatslife6969 via OAuth.")
    else:
        print(f"Not ready yet. Copy {ENV_EXAMPLE.name} to .env and fill the TikTok Developer app values.")


if __name__ == "__main__":
    main()

