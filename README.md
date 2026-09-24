# Arb Glance Pages (read-only · GitHub-hosted)

Static **PUBLIC · read-only** glance of PolyUS ↔ FanDuel NFL quarter BTS locks.

- **Hosted on GitHub Pages** — scanners run on **GitHub Actions** (no PC tunnel required).
- **Cloudflare** = DNS / custom domain / Access only (optional orange-cloud proxy).
- Same glance UX as `arb-glance-public`: cash-fit / max-depth toggle, ROI/profit sort, package summary.
- **No** Take Poly, **no** agent, **no** FD event IDs / full poly slugs.

Private booking dashboard (`arb-glance-dashboard`) is **not** part of this repo.

## Local preview

```powershell
cd C:\Users\klaca\arb-glance-pages
python scripts/scan_to_json.py --out site/data/locks.json --allow-empty
cd site
python -m http.server 8765
```

Open http://127.0.0.1:8765

## Push to GitHub

See **[HOSTING.md](HOSTING.md)** for create-repo → push → Pages → Cloudflare DNS/Access.

Quick push (after creating empty GitHub repo `arb-glance-pages`):

```powershell
cd C:\Users\klaca\arb-glance-pages
git init
git add .
git commit -m "Initial GitHub Pages arb glance"
git branch -M main
git remote add origin https://github.com/YOUR_USER/arb-glance-pages.git
git push -u origin main
```

Then: repo **Settings → Pages → Build and deployment → Source: Deploy from a branch → `gh-pages` / root** (the workflow publishes `site/` to `gh-pages`).

## Layout

| Path | Purpose |
|------|---------|
| `site/index.html` | Static UI (fetches `data/locks.json`) |
| `site/data/locks.json` | Sanitized scan output (seeded locally; refreshed by Actions) |
| `scanner.py` | Live Poly/FD NFL Q-BTS scanner |
| `scripts/scan_to_json.py` | Writes both `locks_cash_fit` + `locks_max_depth` |
| `.github/workflows/scan-and-deploy.yml` | Cron every 15m + `workflow_dispatch` → deploy `gh-pages` |

## Cash / sizing on Pages

Actions size locks with defaults **Poly $50 / FD $50** (override via repo Actions variables `ARB_PAGES_POLY_CASH` / `ARB_PAGES_FD_CASH`).

The UI stores cash notes in **localStorage only** — changing inputs does **not** re-size stakes until the next Actions scan.

Toggle **Cash fit** vs **Max depth** switches which precomputed array from the JSON is shown.

## Optional local FastAPI (PC)

Keep using `C:\Users\klaca\arb-glance-public\` for live localhost / optional Cloudflare Tunnel backup — see `HOSTING-TUNNEL.md`.

## Safety

- Do **not** push secrets, booking tokens, or `arb-glance-dashboard` code here
- Do **not** expose `arb-local-agent` or Gradio placer
- Prefer Cloudflare Access in front of the custom domain
