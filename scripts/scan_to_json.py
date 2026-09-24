#!/usr/bin/env python3
"""Run NFL Q-BTS scanner and write sanitized locks.json for GitHub Pages.

Usage (from repo root):
  python scripts/scan_to_json.py
  python scripts/scan_to_json.py --out site/data/locks.json --poly 50 --fd 50

Env overrides:
  ARB_PAGES_POLY_CASH, ARB_PAGES_FD_CASH
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scanner import run_scan, locks_from_rows  # noqa: E402

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

PUBLIC_LOCK_KEYS = (
    "market",
    "game",
    "q",
    "side",
    "roi_pct",
    "profit",
    "cost",
    "fd_stake",
    "poly_stake",
    "poly_px",
    "poly_side",
    "fd_leg",
    "fd_am",
    "depth",
    "depth_flag",
    "depth_profit_ideal",
    "depth_roi_pct",
    "highlight",
    "deep_low_roi",
    "pegged",
    "fits_cash",
    "sizing_mode",
    "sizing_label",
    "cash_needed_poly",
    "cash_needed_fd",
    "kick",
    "game_label",
)

BANNED = (
    "poly_slug",
    "fd_event_id",
    "fd_market_id",
    "slug",
    "poly_qty",
    "lock_id",
    "cash_fit",
    "max_depth",
)


def now_et_str() -> str:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S ET")
        except Exception:
            pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S local")


def game_label(lock: dict) -> str:
    game = (lock.get("game") or "").strip()
    kick = (lock.get("kick") or "").strip()
    q = lock.get("q")
    parts = []
    if game:
        parts.append(game)
    if q is not None and str(q).strip() != "":
        parts.append(f"Q{q}")
    if kick:
        parts.append(kick)
    if parts:
        return " · ".join(parts)
    return (lock.get("market") or "").strip() or "—"


def sanitize_lock(lock: dict) -> dict:
    out = {k: lock[k] for k in PUBLIC_LOCK_KEYS if k in lock}
    out["game_label"] = game_label(lock)
    for banned in BANNED:
        out.pop(banned, None)
    return out


def sanitize_locks(locks: list | None) -> list:
    return [sanitize_lock(L) for L in (locks or []) if isinstance(L, dict)]


def empty_payload(poly: float, fd: float, err: str | None = None) -> dict:
    return {
        "ok": True,
        "public": True,
        "read_only": True,
        "hosting": "github-pages",
        "last_refresh": now_et_str(),
        "last_error": err,
        "scan_duration_sec": None,
        "sizing_mode_default": "cash_fit",
        "sort_by_default": "roi",
        "cash_default": {"poly": poly, "fd": fd, "dk": 0.0},
        "scope": "NFL quarter BTS PolyUS<->FD (v1)",
        "note": "NCAA / tennis / ML / TD totals can be added later.",
        "coverage": {
            "rows": 0,
            "poly_ok": 0,
            "fd_ok": 0,
            "raw_locks": 0,
            "locks_shown": 0,
            "locks_cash_fit": 0,
            "locks_max_depth": 0,
            "games": 0,
        },
        "locks_cash_fit": [],
        "locks_max_depth": [],
        "deep_low_roi": [],
        "highlights": [],
    }


def build_payload(poly: float, fd: float) -> dict:
    t0 = time.time()
    result = run_scan(poly_cash=poly, fd_cash=fd, sizing_mode="cash_fit")
    dur = round(time.time() - t0, 2)
    rows = result.get("_rows") or []
    locks_cash = sanitize_locks(locks_from_rows(rows, sizing_mode="cash_fit"))
    locks_depth = sanitize_locks(locks_from_rows(rows, sizing_mode="max_depth"))
    # Deep notables from max-depth projection (same as live public server)
    deep = sanitize_locks([L for L in locks_depth if L.get("deep_low_roi")])
    highlights = sanitize_locks([L for L in locks_cash if L.get("highlight")])
    cov = dict(result.get("coverage") or {})
    cov["locks_cash_fit"] = len(locks_cash)
    cov["locks_max_depth"] = len(locks_depth)
    cov["locks_shown"] = len(locks_cash)
    return {
        "ok": True,
        "public": True,
        "read_only": True,
        "hosting": "github-pages",
        "last_refresh": now_et_str(),
        "last_error": None,
        "scan_duration_sec": dur,
        "sizing_mode_default": "cash_fit",
        "sort_by_default": "roi",
        "cash_default": {"poly": poly, "fd": fd, "dk": 0.0},
        "scope": result.get("scope") or "NFL quarter BTS PolyUS<->FD (v1)",
        "note": result.get("note"),
        "coverage": cov,
        "locks_cash_fit": locks_cash,
        "locks_max_depth": locks_depth,
        "deep_low_roi": deep,
        "highlights": highlights,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan arbs → sanitized locks.json for Pages")
    parser.add_argument(
        "--out",
        default=str(ROOT / "site" / "data" / "locks.json"),
        help="Output path (default: site/data/locks.json)",
    )
    parser.add_argument("--poly", type=float, default=None, help="Poly cash default for sizing")
    parser.add_argument("--fd", type=float, default=None, help="FD cash default for sizing")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="On scan failure, still write empty schema JSON (exit 0)",
    )
    args = parser.parse_args()

    poly = args.poly
    if poly is None:
        poly = float(os.environ.get("ARB_PAGES_POLY_CASH") or 50)
    fd = args.fd
    if fd is None:
        fd = float(os.environ.get("ARB_PAGES_FD_CASH") or 50)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        payload = build_payload(poly, fd)
        print(
            f"OK scan {payload['scan_duration_sec']}s · "
            f"cash_fit={len(payload['locks_cash_fit'])} "
            f"max_depth={len(payload['locks_max_depth'])} "
            f"→ {out_path}",
            flush=True,
        )
    except Exception as e:
        print(f"SCAN FAILED: {e}", file=sys.stderr, flush=True)
        if not args.allow_empty:
            return 1
        payload = empty_payload(poly, fd, err=str(e))
        print(f"Wrote empty schema with error note → {out_path}", flush=True)

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
