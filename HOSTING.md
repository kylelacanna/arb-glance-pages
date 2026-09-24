# Hosting Arb Glance on GitHub Pages + Cloudflare (no PC tunnel)

**Recommended path:** GitHub Actions scans → GitHub Pages static site → Cloudflare DNS + Access on your custom domain.

Your PC does **not** need to be on. `cloudflared` tunnel is **optional backup only** (see [HOSTING-TUNNEL.md](HOSTING-TUNNEL.md)).

Assumes: GitHub account + Cloudflare account with a domain already on Cloudflare DNS.

Suggested hostname: `arb.YOURDOMAIN.com`

---

## 1. Create the GitHub repo

1. GitHub → **New repository** → name `arb-glance-pages`
2. **Visibility:**
   - **Public** (recommended on free plan) + Cloudflare Access in front, **or**
   - **Private** only if you have GitHub Pro/Team (private Pages needs a paid plan)
3. Do **not** add a README/license on GitHub if you will push this local folder as the first commit.

---

## 2. Push this folder

```powershell
cd C:\Users\klaca\arb-glance-pages
git init
git add .
git commit -m "Initial GitHub Pages arb glance"
git branch -M main
git remote add origin https://github.com/YOUR_USER/arb-glance-pages.git
git push -u origin main
```

Replace `YOUR_USER` with your GitHub username or org.

`gh` CLI is optional — browser + HTTPS remote is fine. If Windows asks for credentials, use a Personal Access Token with `repo` + `workflow` scopes (or GitHub Login via Git Credential Manager).

---

## 3. Enable Actions + Pages

1. Repo → **Actions** → enable workflows if prompted
2. Open **Actions** → **Scan and deploy Pages** → **Run workflow** (first seed)
3. Repo → **Settings → Pages**:
   - **Source:** Deploy from a branch
   - **Branch:** `gh-pages` / `/ (root)`
   - Save

   (The workflow uses `peaceiris/actions-gh-pages` to publish `./site` to the `gh-pages` branch. Main stays clean — scan results are **not** committed to `main`.)

4. After the first green run, open:
   - User site style (if you used a user/org `*.github.io` repo — uncommon here), **or**
   - Project site: `https://YOUR_USER.github.io/arb-glance-pages/`

---

## 4. Custom domain on GitHub

1. Repo → **Settings → Pages → Custom domain** → `arb.YOURDOMAIN.com`
2. GitHub will show DNS instructions and may ask for a **TXT** verification record
3. Enable **Enforce HTTPS** after DNS verifies (can take minutes)

### Project Pages DNS note

For a **project** site (`YOUR_USER.github.io/arb-glance-pages`), custom domains still CNAME to `YOUR_USER.github.io` (not to the `/arb-glance-pages` path). GitHub routes by Host header + Pages custom domain setting.

| Type  | Name | Target                 | Proxy (Cloudflare) |
|-------|------|------------------------|--------------------|
| CNAME | arb  | `YOUR_USER.github.io`  | Proxied (orange) **or** DNS-only while verifying |

Optional apex (`YOURDOMAIN.com`): use A/AAAA records GitHub documents for Pages — prefer a subdomain (`arb`) for simplicity.

### User site vs project site

| Kind | Repo name | Default URL |
|------|-----------|-------------|
| User/org site | `YOUR_USER.github.io` | `https://YOUR_USER.github.io/` |
| Project site (this repo) | `arb-glance-pages` | `https://YOUR_USER.github.io/arb-glance-pages/` |

This folder is built as a **project site**. Custom domain removes the `/arb-glance-pages` path from the URL users type.

---

## 5. Cloudflare DNS

Cloudflare Dashboard → your zone → **DNS → Records**:

| Type  | Name | Content                | Proxy |
|-------|------|------------------------|-------|
| CNAME | arb  | `YOUR_USER.github.io`  | Proxied (orange cloud) |

Also add any **TXT** verification record GitHub Pages shows (often `_github-pages-challenge-…`).

### SSL / TLS mode

Cloudflare → **SSL/TLS**:

- Prefer **Full** (GitHub Pages presents a valid cert on `*.github.io` / custom domain after HTTPS enforce).
- Avoid **Flexible** long-term (HTTP to origin).
- **Full (strict)** is fine once GitHub HTTPS is active on the custom domain.

---

## 6. Cloudflare Access (strongly recommended)

Without Access, anyone who finds the URL can see the glance (still no booking, but market intel).

1. https://one.dash.cloudflare.com/ → **Access → Applications → Add → Self-hosted**
2. Name: `Arb Glance Pages`
3. Domain: `arb.YOURDOMAIN.com`
4. Identity: One-time PIN (email) and/or Google
5. Policy **Allow Kyle**: Include → Emails → your address(es)
6. Save — visit the hostname; Access login should appear before the UI

---

## 7. Confirm PC is not required

- Scans run on **GitHub-hosted `ubuntu-latest` runners** every **15 minutes** (`*/15 * * * *`) plus **workflow_dispatch**
- Site files are static HTML/JS + `data/locks.json`
- You can shut the PC / leave `arb-glance-public` stopped — Pages still updates

Optional: keep `arb-glance-public` for live local refresh or as tunnel backup ([HOSTING-TUNNEL.md](HOSTING-TUNNEL.md)).

---

## 8. Actions variables (optional)

Repo → **Settings → Secrets and variables → Actions → Variables**:

| Variable | Default | Meaning |
|----------|---------|---------|
| `ARB_PAGES_POLY_CASH` | `50` | Poly $ used for cash_fit sizing in the scan |
| `ARB_PAGES_FD_CASH` | `50` | FD $ used for cash_fit sizing in the scan |

UI cash inputs are **browser localStorage only** and do not re-size until the next scan with new defaults.

---

## 9. Caveats / scan-from-Actions risks

| Risk | What happens | Mitigation |
|------|----------------|------------|
| **FanDuel / Polymarket block GitHub IPs** | `poly_ok` / `fd_ok` stay 0; empty locks | Re-run **workflow_dispatch**; check Actions log warnings; temporarily use local FastAPI + tunnel backup; later option: Cloudflare Worker relay |
| **Actions lag** | Data up to ~15 minutes stale vs live PC | Tighten cron (burns minutes) or keep local public app for trading moments |
| **Free-tier minutes** | Heavy cron can exhaust minutes | `*/15` is usually fine; widen to `*/30` or limit with cron hours if needed |
| **Private repo Pages** | Needs paid GitHub plan | Use **public** repo + Cloudflare Access |
| **No Take Poly on Pages** | By design | Booking stays on private dashboard localhost |

If a scan fails, the workflow still deploys the UI shell with `--allow-empty` and writes `last_error` into JSON so the page can show the failure.

---

## 10. Chat-ready checklist

1. Create public GitHub repo `arb-glance-pages`
2. Push `C:\Users\klaca\arb-glance-pages`
3. Run workflow **Scan and deploy Pages** once
4. Settings → Pages → branch `gh-pages` / root
5. Cloudflare DNS: CNAME `arb` → `YOUR_USER.github.io` (proxied)
6. GitHub Pages custom domain `arb.YOURDOMAIN.com` + HTTPS
7. Cloudflare Access allowlist your email
8. Open `https://arb.YOURDOMAIN.com` — badge **PUBLIC · read-only**, no PC required

Do **not** tunnel private dashboard (:8790), `arb-local-agent` (:8787), or Gradio (:7860).
