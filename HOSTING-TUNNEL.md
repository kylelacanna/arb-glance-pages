# Hosting Arb Glance Public with Cloudflare Tunnel (Windows)

Put **only** the read-only public app (`http://127.0.0.1:8791`) behind your domain.
Do **not** tunnel the private dashboard (:8790), `arb-local-agent` (:8787), or Gradio (:7860).

Assumes: Cloudflare account + a domain already on Cloudflare DNS.

Suggested public hostname: `arb.YOURDOMAIN.com` or `glance.YOURDOMAIN.com`.

---

## 0. Keep the public app running locally

```powershell
cd C:\Users\klaca\arb-glance-public
.\start-public.bat
```

Confirm http://127.0.0.1:8791 loads and shows **PUBLIC · read-only**.

If port **8791** is busy:

```powershell
netstat -ano | findstr :8791
```

Stop the other process, or change `"port"` in `config.json` and update the tunnel ingress below to match.

---

## 1. Install `cloudflared` (Windows)

**Option A — winget**

```powershell
winget install --id Cloudflare.cloudflared -e
```

**Option B — download**

1. Open https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
2. Download the Windows AMD64 installer / binary
3. Put `cloudflared.exe` on your PATH (or note its full path)

Check:

```powershell
cloudflared --version
```

---

## 2. Log in to Cloudflare

```powershell
cloudflared tunnel login
```

A browser window opens — pick the zone (domain) you want to use. This writes cert credentials under your user profile (typically `%USERPROFILE%\.cloudflared\`).

---

## 3. Create a named tunnel

```powershell
cloudflared tunnel create arb-glance
```

Note the **Tunnel ID** (UUID) printed. Credentials JSON lands in:

`%USERPROFILE%\.cloudflared\<TUNNEL_ID>.json`

List tunnels anytime:

```powershell
cloudflared tunnel list
```

---

## 4. Config YAML (point at localhost:8791)

Create folder if needed:

```powershell
mkdir $env:USERPROFILE\.cloudflared -Force
```

Create `%USERPROFILE%\.cloudflared\config.yml` (edit paths / subdomain / domain):

```yaml
tunnel: <TUNNEL_ID>
credentials-file: C:\Users\klaca\.cloudflared\<TUNNEL_ID>.json

ingress:
  # Public read-only glance only
  - hostname: arb.YOURDOMAIN.com
    service: http://127.0.0.1:8791
  # Catch-all required
  - service: http_status:404
```

Replace:

- `<TUNNEL_ID>` with the UUID from step 3
- `arb.YOURDOMAIN.com` with your chosen hostname
- Keep `service: http://127.0.0.1:8791` unless you changed the public app port

Validate:

```powershell
cloudflared tunnel ingress validate
```

---

## 5. DNS route (CNAME → tunnel)

```powershell
cloudflared tunnel route dns arb-glance arb.YOURDOMAIN.com
```

This creates a CNAME `arb` → `<TUNNEL_ID>.cfargotunnel.com` in Cloudflare DNS for your zone.

Or manually in Cloudflare Dashboard → DNS:

| Type  | Name | Target                         | Proxy |
|-------|------|--------------------------------|-------|
| CNAME | arb  | `<TUNNEL_ID>.cfargotunnel.com` | Proxied (orange cloud) |

---

## 6. Run the tunnel

### Quick test (foreground)

```powershell
cloudflared tunnel run arb-glance
```

Leave this open. With the public Python app also running, open:

`https://arb.YOURDOMAIN.com`

### Recommended: Windows service

From an **elevated** PowerShell (Run as Administrator):

```powershell
cloudflared service install
```

`cloudflared` installs a Windows service that uses `%USERPROFILE%\.cloudflared\config.yml` (or the system config path it prints). Then:

```powershell
Start-Service cloudflared
Get-Service cloudflared
```

To remove later:

```powershell
cloudflared service uninstall
```

### Alternative: Scheduled Task (logon)

1. Task Scheduler → Create Task
2. Trigger: At log on (your user)
3. Action: Start a program  
   - Program: full path to `cloudflared.exe`  
   - Arguments: `tunnel run arb-glance`
4. Settings: Run whether user is logged on or not (optional), restart on failure

Also keep **`python server.py`** (or `start-public.bat`) running — tunnel alone does nothing without the app.

### Keep the public app running

Options:

- Leave a terminal open with `start-public.bat`
- Or install as a service with [NSSM](https://nssm.cc/):  
  `nssm install ArbGlancePublic "C:\Users\klaca\arb-glance-public\.venv\Scripts\python.exe" "C:\Users\klaca\arb-glance-public\server.py"`  
  Start directory: `C:\Users\klaca\arb-glance-public`
- Or a Scheduled Task that runs `start-public.bat` at logon

---

## 7. Strongly recommend: Cloudflare Access (Zero Trust)

Without Access, anyone who finds `https://arb.YOURDOMAIN.com` can see your glance (still no booking, but still private-ish market intel). Prefer **Access**.

### Outline (Cloudflare Zero Trust dashboard)

1. Go to https://one.dash.cloudflare.com/ → **Access** → **Applications** → **Add an application** → **Self-hosted**
2. Application name: `Arb Glance Public`
3. Session duration: e.g. 24 hours
4. Application domain: `arb.YOURDOMAIN.com` (path `/` or leave default)
5. **Identity providers:** enable One-time PIN (email) and/or Google
6. **Create a policy** e.g. `Allow Kyle`:
   - Action: **Allow**
   - Include: Emails → your address(es), **or** Emails ending in `@yourcompany.com`, **or** Google Workspace group
7. Save. Visit `https://arb.YOURDOMAIN.com` — you should get an Access login before the glance UI.

Optional: keep the app’s `access_token` / `ARB_PUBLIC_TOKEN` **off** when Access is on (Access is stronger UX). Or enable both for defense in depth.

---

## 8. Optional app-level token (in addition to Access)

See README. Example:

```powershell
cd C:\Users\klaca\arb-glance-public
$env:ARB_PUBLIC_TOKEN = "long-random-secret"
.\.venv\Scripts\python.exe server.py
```

Then open `https://arb.YOURDOMAIN.com/?token=long-random-secret` once (UI stores it), or send header `X-Arb-Token`.

---

## 9. Security checklist

- [ ] Only tunnel **:8791** (`arb-glance-public`)
- [ ] Private glance stays on **:8790** localhost — **not** in tunnel ingress
- [ ] Do **not** expose `arb-local-agent` **:8787**
- [ ] Do **not** expose Gradio / `polyus-local-placer` **:7860**
- [ ] Public UI has **no** Take Poly / no agent calls / no FD event IDs or poly slugs
- [ ] Cloudflare Access (email OTP / Google allowlist) enabled — or app token set
- [ ] `config.json` host remains `127.0.0.1` (tunnel connects locally)
- [ ] Windows firewall need not open 8791 to the LAN/WAN; tunnel is outbound-only

---

## 10. Chat-ready quick start (summary)

1. Run public app: `C:\Users\klaca\arb-glance-public\start-public.bat` → http://127.0.0.1:8791  
2. `winget install Cloudflare.cloudflared`  
3. `cloudflared tunnel login`  
4. `cloudflared tunnel create arb-glance`  
5. Write `~\.cloudflared\config.yml` → hostname → `http://127.0.0.1:8791`  
6. `cloudflared tunnel route dns arb-glance arb.YOURDOMAIN.com`  
7. `cloudflared tunnel run arb-glance` (or install as Windows service)  
8. Add Cloudflare Access policy (email OTP / Google allowlist)  
9. Open `https://arb.YOURDOMAIN.com`

Private booking UI remains local-only at http://127.0.0.1:8790  
