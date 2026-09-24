# Deployment

Production layout:

- **Frontend** — Next.js static export (`output: "export"`) hosted on **Vercel**:
  `https://mustachar-ai.vercel.app` (project `mustachar-ai`).
- **Backend** — FastAPI running on the VPS (Hetzner `88.99.81.55`), port `8000`,
  exposed publicly through a **Cloudflare quick tunnel** so the browser can
  reach it over HTTPS/WSS from the Vercel page (browsers block plain
  `http://`/`ws://` from an HTTPS page — mixed-content rule).

```
Browser ──https──▶ Vercel (static Next.js, mustachar-ai.vercel.app)
                    │  NEXT_PUBLIC_API_URL / NEXT_PUBLIC_WS_URL
                    ▼  https+wss
              Cloudflare Tunnel (trycloudflare.com)
                    │  https://127.0.0.1:8000
                    ▼
              systemd: mustachar-backend (uvicorn :8000, VPS)
```

## Backend (VPS)

Managed as a systemd service.

```bash
systemctl status mustachar-backend      # state
systemctl restart mustachar-backend     # after a code update
journalctl -u mustachar-backend -f      # logs
```

Unit file: `/etc/systemd/system/mustachar-backend.service`
(runs `uvicorn mustachar.api.app:app --host 0.0.0.0 --port 8000` from
`/root/MustacharAI`, with `OMP_NUM_THREADS=1 …` for the low-RAM box).

The public URL is provided by a `cloudflared` quick tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate
```

⚠️ **Quick-tunnel URLs are ephemeral**: every restart of `cloudflared`
produces a **new** random `https://*.trycloudflare.com` URL. Because the
frontend bakes the URL into its static build, you must refresh Vercel after a
tunnel restart:

```bash
vercel env rm NEXT_PUBLIC_API_URL production --yes        # old value
vercel env rm NEXT_PUBLIC_WS_URL production --yes
printf 'https://NEW-TUNNEL-URL' | vercel env add NEXT_PUBLIC_API_URL production
printf 'wss://NEW-TUNNEL-URL/api/v1/stream' | vercel env add NEXT_PUBLIC_WS_URL production
# same for the "preview" scope, then:
vercel deploy --prod
```

For a stable URL, point a real domain at the VPS (A record → `88.99.81.55`)
and switch to Caddy (`https://<domain>` → `127.0.0.1:8000`, auto-HTTPS,
WebSocket supported natively).

## Frontend (Vercel)

- Project `mustachar-ai`, **Root Directory = `frontend`**, framework Next.js
  (`frontend/vercel.json`), deploy from the **repo root** so the upload respects
  `.vercelignore` (only `frontend/` is sent).
- Build-time env vars (Vercel project settings or CLI):
  | Variable | Value |
  |---|---|
  | `NEXT_PUBLIC_API_URL` | `https://<tunnel-url>` |
  | `NEXT_PUBLIC_WS_URL` | `wss://<tunnel-url>/api/v1/stream` |

- Deploy: `vercel deploy --prod` (from `/root/MustacharAI`).