#!/usr/bin/env python3
"""NFL quarter BTS PolyUS <-> FanDuel arb scanner (glance-only, no betting).

Ported/adapted from scan_arb_roi_fresh.py for local dashboard use.
v1 scope: NFL quarter Both-Teams-to-Score only. NCAA/tennis can be added later.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

FEE_COEF = 0.06
UA = "Mozilla/5.0 (compatible; arb-glance-dashboard/1.0)"
FD_AK = "FhMFpcPWXMeyZxOx"  # public odds read key (same pattern as scan scripts)
PMUS = "https://gateway.polymarket.us"
FD = "https://sbapi.nj.sportsbook.fanduel.com"

Q_TABS = {1: "1st-quarter", 2: "2nd-quarter", 3: "3rd-quarter", 4: "4th-quarter"}

# NFL slate — update as week rolls (label, away, home, poly_date, fd_event_id, kick note)
NFL_GAMES = [
    ("ATL@GB", "atl", "gb", "2026-09-24", 36076208, "Thu 9/24 8:15p ET TNF"),
    ("LAC@BUF", "lac", "buf", "2026-09-27", 36076211, "Sun 9/27 1:00p ET"),
    ("CAR@CLE", "car", "cle", "2026-09-27", 36076206, "Sun 9/27 1:00p ET"),
    ("NYJ@DET", "nyj", "det", "2026-09-27", 36076207, "Sun 9/27 1:00p ET"),
    ("HOU@IND", "hou", "ind", "2026-09-27", 36076210, "Sun 9/27 1:00p ET"),
    ("NE@JAX", "ne", "jax", "2026-09-27", 36076209, "Sun 9/27 1:00p ET"),
    ("KC@MIA", "kc", "mia", "2026-09-27", 36076212, "Sun 9/27 1:00p ET"),
    ("TEN@NYG", "ten", "nyg", "2026-09-27", 36076215, "Sun 9/27 1:00p ET"),
    ("CIN@PIT", "cin", "pit", "2026-09-27", 36076213, "Sun 9/27 1:00p ET"),
    ("SEA@WAS", "sea", "was", "2026-09-27", 36076214, "Sun 9/27 1:00p ET"),
    ("ARI@SF", "ari", "sf", "2026-09-27", 36076217, "Sun 9/27 4:05p ET"),
    ("MIN@TB", "min", "tb", "2026-09-27", 36076218, "Sun 9/27 4:05p ET"),
    ("BAL@DAL", "bal", "dal", "2026-09-27", 35601592, "Sun 9/27 4:25p ET Rio"),
    ("LV@NO", "lv", "no", "2026-09-27", 36070615, "Sun 9/27 4:25p ET"),
    ("LAR@DEN", "lar", "den", "2026-09-27", 36076216, "Sun 9/27 8:20p ET SNF"),
    ("PHI@CHI", "phi", "chi", "2026-09-28", 36076219, "Mon 9/28 8:15p ET MNF"),
]


def get_json(url: str, timeout: float = 25.0) -> tuple[int, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"error": body[:300]}
    except Exception as e:
        return 0, {"error": str(e)}


def am_to_cost(am) -> float | None:
    if am is None:
        return None
    am = float(am)
    if am > 0:
        return 100.0 / (am + 100.0)
    return abs(am) / (abs(am) + 100.0)


def poly_fee(p: float, coef: float = FEE_COEF) -> float:
    return coef * p * (1.0 - p)


def round_fd_stake(x: float) -> float:
    """Round FD stake to nearest whole dollar or .50."""
    if x is None or x <= 0:
        return 0.0
    return round(float(x) * 2) / 2.0


def parse_levels(levels: list) -> list[tuple[float, float]]:
    out = []
    for lv in levels or []:
        try:
            px = float(lv["px"]["value"])
            qty = float(lv["qty"])
            out.append((px, qty))
        except Exception:
            continue
    return out


def fetch_poly_book(slug: str) -> dict | None:
    code, data = get_json(f"{PMUS}/v1/markets/{slug}/book")
    if code != 200 or not isinstance(data, dict):
        return None
    md = data.get("marketData") or {}
    bids = parse_levels(md.get("bids") or [])
    offers = parse_levels(md.get("offers") or md.get("asks") or [])
    yes_bid = bids[0][0] if bids else None
    yes_bid_qty = bids[0][1] if bids else 0.0
    yes_ask = offers[0][0] if offers else None
    yes_ask_qty = offers[0][1] if offers else 0.0
    no_ask = round(1.0 - yes_bid, 4) if yes_bid is not None else None
    no_ask_qty = yes_bid_qty
    no_bid = round(1.0 - yes_ask, 4) if yes_ask is not None else None
    short = md.get("shortQuote")
    if short is not None:
        try:
            short_f = float(short.get("value") if isinstance(short, dict) else short)
            no_ask = short_f
        except Exception:
            pass
    pegged = False
    if yes_bid is not None and yes_ask is not None:
        pairs = [(0.69, 0.70), (0.68, 0.69), (0.31, 0.32), (0.30, 0.31)]
        for b, a in pairs:
            if abs(yes_bid - b) < 1e-6 and abs(yes_ask - a) < 1e-6:
                pegged = True
    return {
        "slug": slug,
        "bids": bids[:8],
        "offers": offers[:8],
        "yes_bid": yes_bid,
        "yes_bid_qty": yes_bid_qty,
        "yes_ask": yes_ask,
        "yes_ask_qty": yes_ask_qty,
        "no_ask": no_ask,
        "no_ask_qty": no_ask_qty,
        "no_bid": no_bid,
        "pegged": pegged,
    }


def extract_runner_am(r: dict):
    odds = (r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}
    am = odds.get("americanOdds")
    return am


def fetch_fd_event(event_id: int, tab: str | None = "popular") -> dict:
    q = f"&tab={tab}" if tab else ""
    url = (
        f"{FD}/api/event-page?_ak={FD_AK}&eventId={event_id}{q}"
        f"&useCombinedTouchdownsVirtualMarket=true&includePrices=true"
    )
    code, data = get_json(url)
    if code != 200 or not isinstance(data, dict):
        return {}
    return (data.get("attachments") or {}).get("markets") or {}


def find_fd_bts_q(markets: dict, q: int) -> dict | None:
    want_types = {
        1: "BOTH_TEAMS_TO_SCORE_-_QTR_1",
        2: "BOTH_TEAMS_TO_SCORE_-_QTR_2",
        3: "BOTH_TEAMS_TO_SCORE_-_QTR_3",
        4: "BOTH_TEAMS_TO_SCORE_-_QTR_4",
    }
    want_names = {
        1: "1st Quarter Both Teams to Score",
        2: "2nd Quarter Both Teams to Score",
        3: "3rd Quarter Both Teams to Score",
        4: "4th Quarter Both Teams to Score",
    }
    for mid, m in markets.items():
        mtype = m.get("marketType") or ""
        name = m.get("marketName") or ""
        if want_types[q] in mtype or name == want_names[q]:
            yes_am = no_am = None
            for r in m.get("runners") or []:
                rname = (r.get("runnerName") or "").lower()
                am = extract_runner_am(r)
                if rname in ("yes", "both teams to score"):
                    yes_am = am
                elif rname == "no":
                    no_am = am
            return {
                "market_id": mid,
                "market_name": name,
                "yes_am": yes_am,
                "no_am": no_am,
                "market_type": mtype,
            }
    return None


def best_yesno_arb(fd_yes_am, fd_no_am, poly: dict) -> dict | None:
    if not poly:
        return None
    fy = am_to_cost(fd_yes_am)
    fn = am_to_cost(fd_no_am)
    cands = []
    if fy is not None and poly.get("no_ask") is not None:
        p = float(poly["no_ask"])
        fee = poly_fee(p)
        cands.append(
            {
                "side": "FDY+PolyN",
                "fd_leg": "Yes",
                "fd_am": fd_yes_am,
                "fd_c": fy,
                "poly_side": "No",
                "poly_px": p,
                "poly_depth": float(poly.get("no_ask_qty") or 0),
                "fee": fee,
                "raw_sum": fy + p,
                "after_fee": fy + p + fee,
                "lock": (fy + p + fee) < 1.0,
            }
        )
    if fn is not None and poly.get("yes_ask") is not None:
        p = float(poly["yes_ask"])
        fee = poly_fee(p)
        cands.append(
            {
                "side": "FDN+PolyY",
                "fd_leg": "No",
                "fd_am": fd_no_am,
                "fd_c": fn,
                "poly_side": "Yes",
                "poly_px": p,
                "poly_depth": float(poly.get("yes_ask_qty") or 0),
                "fee": fee,
                "raw_sum": fn + p,
                "after_fee": fn + p + fee,
                "lock": (fn + p + fee) < 1.0,
            }
        )
    if not cands:
        return None
    cands.sort(key=lambda c: c["after_fee"])
    return cands[0]


def size_stakes(
    after_fee: float,
    fd_c: float,
    poly_px: float,
    depth: float,
    poly_cash: float,
    fd_cash: float,
    bank: float | None = None,
) -> dict:
    """Size both cash-fit and max-depth (book) stakes.

    Cash-fit: clamp to leftover Poly/FD cash + depth.
    Max-depth: clamp to book depth only; still report cash needed.
    FD stakes rounded to whole dollars or .50.
    """
    if after_fee <= 0 or after_fee >= 1 or fd_c <= 0 or poly_px <= 0:
        return {}
    if bank is None:
        bank = poly_cash + fd_cash
    fee_ps = poly_fee(poly_px)
    max_sh_by_depth = depth
    max_sh_by_bank = bank / after_fee if after_fee > 0 else 0
    max_sh_poly_cash = poly_cash / (poly_px + fee_ps) if poly_px > 0 else 0
    max_sh_fd_cash = fd_cash / fd_c if fd_c > 0 else 0

    def _rebalance(sh_cap: float, *, apply_cash: bool) -> dict:
        if sh_cap <= 0:
            return {
                "fd_stake": 0,
                "shares": 0,
                "poly_stake": 0,
                "fee": 0,
                "profit": 0,
                "cost": 0,
                "roi_pct": 0.0,
                "fits_cash": False,
            }
        fd_ideal = sh_cap * fd_c
        fd_rounded = round_fd_stake(fd_ideal)
        if fd_rounded < 0.5:
            fd_rounded = 0.0
        # Prefer at least $1 when ideal is near/above $1
        if fd_ideal >= 0.75 and fd_rounded < 1:
            fd_rounded = 1.0
        sh_r = fd_rounded / fd_c if fd_rounded > 0 else 0.0
        if sh_r > depth + 1e-9 and fd_c > 0:
            max_fd = depth * fd_c
            fd_rounded = round_fd_stake(math.floor(max_fd * 2) / 2.0)
            while fd_rounded >= 0.5 and (fd_rounded / fd_c) > depth + 1e-9:
                fd_rounded = round(fd_rounded - 0.5, 2)
            sh_r = fd_rounded / fd_c if fd_rounded >= 0.5 else 0.0
        if apply_cash:
            while fd_rounded >= 0.5 and (
                (fd_rounded / fd_c) * poly_px + fee_ps * (fd_rounded / fd_c) > poly_cash + 1e-6
                or fd_rounded > fd_cash + 1e-6
            ):
                fd_rounded = round(fd_rounded - 0.5, 2)
                sh_r = fd_rounded / fd_c if fd_rounded >= 0.5 else 0.0
                if fd_rounded < 0.5:
                    break
        if fd_rounded < 0.5:
            return {
                "fd_stake": 0,
                "shares": 0,
                "poly_stake": 0,
                "fee": 0,
                "profit": 0,
                "cost": 0,
                "roi_pct": 0.0,
                "fits_cash": False,
            }
        poly_stake_r = sh_r * poly_px
        fee_r = fee_ps * sh_r
        cost_r = poly_stake_r + fd_rounded + fee_r
        profit_r = sh_r - cost_r
        fits = (
            poly_stake_r + fee_r <= poly_cash + 0.01
            and fd_rounded <= fd_cash + 0.01
        )
        return {
            "fd_stake": fd_rounded,
            "shares": round(sh_r, 4),
            "poly_stake": round(poly_stake_r, 4),
            "fee": round(fee_r, 4),
            "profit": round(profit_r, 4),
            "cost": round(cost_r, 4),
            "roi_pct": round(100.0 * profit_r / cost_r, 2) if cost_r > 0 else 0.0,
            "fits_cash": fits,
        }

    sh_cash = min(max_sh_by_depth, max_sh_by_bank, max_sh_poly_cash, max_sh_fd_cash)
    cash = _rebalance(sh_cash, apply_cash=True)

    # Max depth: shares limited by book only (ignore free cash for sizing)
    sh_depth_only = max_sh_by_depth
    depth_sz = _rebalance(sh_depth_only, apply_cash=False)

    # Deep/low-ROI badge uses depth-sized economics
    depth_profit = float(depth_sz.get("profit") or 0)
    depth_roi = float(depth_sz.get("roi_pct") or 0)

    return {
        "shares_ideal": round(sh_cash, 4) if sh_cash > 0 else 0,
        "poly_stake_ideal": round(sh_cash * poly_px, 4) if sh_cash > 0 else 0,
        "fd_stake_ideal": round(sh_cash * fd_c, 4) if sh_cash > 0 else 0,
        "fee_ideal": round(fee_ps * sh_cash, 4) if sh_cash > 0 else 0,
        "profit_ideal": round(sh_cash - sh_cash * after_fee, 4) if sh_cash > 0 else 0,
        # Cash-fit (legacy field names)
        "fd_stake_rebalanced": cash["fd_stake"],
        "shares_rebalanced": cash["shares"],
        "poly_stake_rebalanced": cash["poly_stake"],
        "fee_rebalanced": cash["fee"],
        "profit_rebalanced": cash["profit"],
        "cost_rebalanced": cash["cost"],
        "fits_cash_rebalanced": cash["fits_cash"],
        "roi_rebalanced": round(cash["profit"] / cash["cost"], 6) if cash["cost"] > 0 else 0.0,
        "roi_pct_rebalanced": cash["roi_pct"],
        # Max-depth (book)
        "fd_stake_depth": depth_sz["fd_stake"],
        "shares_depth": depth_sz["shares"],
        "poly_stake_depth": depth_sz["poly_stake"],
        "fee_depth": depth_sz["fee"],
        "profit_depth": depth_sz["profit"],
        "cost_depth": depth_sz["cost"],
        "roi_pct_depth": depth_sz["roi_pct"],
        "cash_needed_poly": round(depth_sz["poly_stake"] + depth_sz["fee"], 2),
        "cash_needed_fd": round(depth_sz["fd_stake"], 2),
        "depth_profit_ideal": round(depth_profit, 4),
        "depth_roi_pct": round(depth_roi, 2),
        "insufficient": sh_cash <= 0 and depth_sz["shares"] <= 0,
    }


def scan_nfl_bts(poly_cash: float, fd_cash: float) -> list[dict]:
    """Live scan NFL quarter BTS PolyUS <-> FD. Returns raw rows including non-locks."""
    rows: list[dict] = []
    slugs = []
    for label, away, home, date, eid, kick in NFL_GAMES:
        for q in (1, 2, 3, 4):
            slug = f"astatc-nfl-{away}-{home}-{date}-bp{q}q-0pt5"
            slugs.append((label, away, home, date, eid, kick, q, slug))

    poly_map: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=14) as ex:
        futs = {ex.submit(fetch_poly_book, s[-1]): s[-1] for s in slugs}
        for fut in as_completed(futs):
            poly_map[futs[fut]] = fut.result()

    fd_map: dict[tuple, Any] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = []
        for label, away, home, date, eid, kick in NFL_GAMES:
            for q in (1, 2, 3, 4):
                futs.append(
                    ex.submit(
                        lambda e=eid, qq=q: ((e, qq), find_fd_bts_q(fetch_fd_event(e, Q_TABS[qq]), qq))
                    )
                )
        for fut in as_completed(futs):
            key, val = fut.result()
            fd_map[key] = val

    bank = poly_cash + fd_cash
    for label, away, home, date, eid, kick, q, slug in slugs:
        poly = poly_map.get(slug)
        fd = fd_map.get((eid, q))
        row: dict[str, Any] = {
            "category": "NFL_QBTS",
            "game": label,
            "q": q,
            "kick": kick,
            "slug": slug,
            "fd_event_id": eid,
            "market": f"Q{q} Both Teams to Score",
            "poly_ok": poly is not None,
            "fd_ok": bool(fd),
        }
        if not poly or not fd:
            rows.append(row)
            continue
        row["fd_yes_am"] = fd.get("yes_am")
        row["fd_no_am"] = fd.get("no_am")
        row["fd_market_id"] = fd.get("market_id")
        row["poly"] = {
            k: poly[k]
            for k in ("yes_bid", "yes_ask", "no_ask", "yes_ask_qty", "no_ask_qty", "pegged")
            if k in poly
        }
        arb = best_yesno_arb(fd.get("yes_am"), fd.get("no_am"), poly)
        if arb:
            row.update(arb)
            if arb.get("lock"):
                row["sizing"] = size_stakes(
                    arb["after_fee"],
                    arb["fd_c"],
                    arb["poly_px"],
                    arb["poly_depth"],
                    poly_cash=poly_cash,
                    fd_cash=fd_cash,
                    bank=bank,
                )
        rows.append(row)
    return rows


def locks_from_rows(
    rows: list[dict],
    min_depth: float = 0.0,
    sizing_mode: str = "cash_fit",
) -> list[dict]:
    """Filter to lock rows and shape for API/UI.

    sizing_mode:
      - cash_fit (default): only locks that fit Poly/FD cash; stakes = cash-sized
      - max_depth: all true locks; stakes = book-depth max; includes cash_needed_*
    """
    mode = (sizing_mode or "cash_fit").strip().lower()
    if mode not in ("cash_fit", "max_depth"):
        mode = "cash_fit"
    out = []
    for r in rows:
        if not r.get("lock"):
            continue
        depth = float(r.get("poly_depth") or 0)
        if depth < min_depth:
            continue
        sz = r.get("sizing") or {}
        pegged = bool((r.get("poly") or {}).get("pegged"))
        depth_flag = "THIN" if depth < 10 else ("OK" if depth < 50 else "DEEP")

        cash_fd = float(sz.get("fd_stake_rebalanced") or 0)
        cash_poly = float(sz.get("poly_stake_rebalanced") or 0) + float(sz.get("fee_rebalanced") or 0)
        cash_profit = float(sz.get("profit_rebalanced") or 0)
        cash_roi = float(sz.get("roi_pct_rebalanced") or 0)
        cash_cost = float(sz.get("cost_rebalanced") or 0)
        cash_shares = float(sz.get("shares_rebalanced") or 0)
        fits_cash = bool(sz.get("fits_cash_rebalanced"))

        depth_fd = float(sz.get("fd_stake_depth") or 0)
        depth_poly = float(sz.get("poly_stake_depth") or 0) + float(sz.get("fee_depth") or 0)
        depth_profit = float(sz.get("profit_depth") or sz.get("depth_profit_ideal") or 0)
        depth_roi = float(sz.get("roi_pct_depth") or sz.get("depth_roi_pct") or 0)
        depth_cost = float(sz.get("cost_depth") or 0)
        depth_shares = float(sz.get("shares_depth") or 0)
        cash_needed_poly = float(sz.get("cash_needed_poly") or depth_poly)
        cash_needed_fd = float(sz.get("cash_needed_fd") or depth_fd)

        if mode == "cash_fit":
            if not fits_cash or cash_fd <= 0:
                continue
            roi, profit, fd_stake, poly_stake, cost, shares = (
                cash_roi, cash_profit, cash_fd, cash_poly, cash_cost, cash_shares
            )
            label = "cash-fit"
        else:
            if depth_fd <= 0 and depth_shares <= 0:
                continue
            roi, profit, fd_stake, poly_stake, cost, shares = (
                depth_roi, depth_profit, depth_fd, depth_poly, depth_cost, depth_shares
            )
            label = "max-depth"

        highlight = roi >= 8.0 and profit >= 2.0
        deep_low_roi = (not highlight) and depth_profit >= 5.0 and depth >= 20 and depth_roi > 0
        out.append(
            {
                "market": f"{r.get('game')} {r.get('market')}",
                "game": r.get("game"),
                "q": r.get("q"),
                "side": r.get("side"),
                "roi_pct": roi,
                "profit": round(profit, 2),
                "fd_stake": round(fd_stake, 2),
                "poly_stake": round(poly_stake, 2),
                "poly_qty": round(shares, 4),
                "cost": round(cost, 2),
                "depth": round(depth, 2),
                "depth_flag": depth_flag,
                "fd_event_id": r.get("fd_event_id"),
                "fd_market_id": r.get("fd_market_id"),
                "poly_slug": r.get("slug"),
                "after_fee": round(float(r.get("after_fee") or 0), 4),
                "fd_am": r.get("fd_am"),
                "fd_leg": r.get("fd_leg"),
                "poly_side": r.get("poly_side"),
                "poly_px": r.get("poly_px"),
                "pegged": pegged,
                "fits_cash": fits_cash,
                "highlight": highlight,
                "deep_low_roi": deep_low_roi,
                "depth_profit_ideal": round(float(sz.get("depth_profit_ideal") or depth_profit), 2),
                "depth_roi_pct": float(sz.get("depth_roi_pct") or depth_roi),
                "kick": r.get("kick"),
                "sizing_mode": mode,
                "sizing_label": label,
                "cash_needed_poly": round(cash_needed_poly, 2),
                "cash_needed_fd": round(cash_needed_fd, 2),
                "cash_fit": {
                    "fd_stake": round(cash_fd, 2),
                    "poly_stake": round(cash_poly, 2),
                    "profit": round(cash_profit, 2),
                    "roi_pct": cash_roi,
                    "fits": fits_cash,
                },
                "max_depth": {
                    "fd_stake": round(depth_fd, 2),
                    "poly_stake": round(depth_poly, 2),
                    "profit": round(depth_profit, 2),
                    "roi_pct": depth_roi,
                    "cash_needed_poly": round(cash_needed_poly, 2),
                    "cash_needed_fd": round(cash_needed_fd, 2),
                },
            }
        )
    out.sort(key=lambda x: (-x["roi_pct"], -x["profit"]))
    return out


def run_scan(poly_cash: float, fd_cash: float, sizing_mode: str = "cash_fit") -> dict:
    """Run live NFL Q BTS scan and return summary + ranked locks."""
    rows = scan_nfl_bts(poly_cash, fd_cash)
    mode = (sizing_mode or "cash_fit").strip().lower()
    if mode not in ("cash_fit", "max_depth"):
        mode = "cash_fit"
    locks = locks_from_rows(rows, min_depth=0.0, sizing_mode=mode)
    # Also keep alternate view counts for UI badge
    locks_cash = locks_from_rows(rows, min_depth=0.0, sizing_mode="cash_fit")
    locks_depth = locks_from_rows(rows, min_depth=0.0, sizing_mode="max_depth")
    n_poly = sum(1 for r in rows if r.get("poly_ok"))
    n_fd = sum(1 for r in rows if r.get("fd_ok"))
    return {
        "scope": "NFL quarter BTS PolyUS<->FD (v1)",
        "note": "NCAA / tennis / ML / TD totals can be added later.",
        "sizing_mode": mode,
        "coverage": {
            "rows": len(rows),
            "poly_ok": n_poly,
            "fd_ok": n_fd,
            "raw_locks": sum(1 for r in rows if r.get("lock")),
            "locks_shown": len(locks),
            "locks_cash_fit": len(locks_cash),
            "locks_max_depth": len(locks_depth),
            "games": len(NFL_GAMES),
        },
        "locks": locks,
        "highlights": [L for L in locks if L["highlight"]],
        "deep_low_roi": [L for L in locks if L.get("deep_low_roi")],
        "_rows": rows,  # kept in-memory for mode switch without full rescan
    }
