# Phase 2 — Deploy Backend to Render

Complete step-by-step checklist. Follow in order.

---

## Step 5 — Dockerfile + render.yaml (already done)

The following files are production-ready in this repo:

| File | What changed |
|---|---|
| `Dockerfile` | CPU-only torch (saves ~1.5 GB), non-root user, pre-downloads FaceNet weights at build time |
| `render.yaml` | All env vars listed, `autoDeploy: true` on `main` branch |
| `.dockerignore` | Excludes `.env`, `venv/`, `__pycache__`, local DBs from the image |
| `.github/workflows/ci.yml` | Lint + smoke tests + Docker build check on every push |
| `tests/test_health.py` | 7 tests covering health, auth flow, and route protection |

---

## Step 6 — Push to GitHub → connect Render

### 6a. Push to GitHub

```bash
cd face_attendance_v2

git init
git add .
git commit -m "chore: phase 2 — production Dockerfile, render.yaml, CI"

# Create a new repo on github.com first, then:
git remote add origin https://github.com/YOUR_USERNAME/face-attendance.git
git branch -M main
git push -u origin main
```

### 6b. Connect to Render

1. Go to [render.com](https://render.com) → **New** → **Blueprint**
2. Connect your GitHub account if not already done
3. Select the `face-attendance` repo — Render will detect `render.yaml` automatically
4. Click **Apply** — Render creates the service

### 6c. Set env vars in Render dashboard

Go to your service → **Environment** tab and fill in these (all marked `sync: false` in render.yaml):

| Key | Where to get it |
|---|---|
| `DATABASE_URL` | Supabase → Settings → Database → **Transaction** pooler URL (port 6543). Prefix with `postgresql+asyncpg://` |
| `JWT_SECRET` | Run: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SETUP_TOKEN` | Run: `python -c "import secrets; print(secrets.token_hex(16))"` — delete after first admin is created |
| `IMAGEKIT_PUBLIC_KEY` | ImageKit Dashboard → Developer Options → API Keys |
| `IMAGEKIT_PRIVATE_KEY` | Same as above |
| `IMAGEKIT_URL_ENDPOINT` | `https://ik.imagekit.io/YOUR_IMAGEKIT_ID` |
| `CORS_ORIGINS` | Leave blank for now — add Vercel URL in Phase 3 |

Click **Save Changes** → Render triggers a deploy automatically.

---

## Step 7 — CORS: allow Vercel preview URLs

The `CORS_ORIGINS` env var is comma-separated. After Phase 3 Vercel deploy, update it to:

```
https://face-attendance.vercel.app,https://face-attendance-*.vercel.app
```

The wildcard `*` in the second entry covers Vercel preview deployments (each PR gets a unique URL like `face-attendance-git-feat-login-yourname.vercel.app`).

> **Note:** FastAPI's `CORSMiddleware` does not support wildcard subdomains natively.
> For full wildcard support, add this to `app/main.py`:

```python
import re

class WildcardCORSMiddleware:
    """Allows Vercel preview URLs matching *.vercel.app."""
    def __init__(self, app, allowed_origins, allowed_pattern=None):
        from starlette.middleware.cors import CORSMiddleware as _CORS
        self._cors = _CORS(app, allow_origins=allowed_origins,
                           allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
        self._pattern = re.compile(allowed_pattern) if allowed_pattern else None

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self._pattern:
            headers = dict(scope.get("headers", []))
            origin = headers.get(b"origin", b"").decode()
            if self._pattern.match(origin):
                scope["headers"] = [
                    (k, v) for k, v in scope["headers"] if k != b"origin"
                ] + [(b"origin", next(iter(
                    [o.encode() for o in ALLOWED_ORIGINS if "*" not in o]
                ), b"https://face-attendance.vercel.app"))]
        await self._cors(scope, receive, send)
```
>
> Simpler alternative: add every Vercel preview URL explicitly to `CORS_ORIGINS`.

---

## Step 8 — Test all endpoints via Swagger /docs

Once deployed, your API is live at `https://face-attendance-api.onrender.com`.

### 8a. Open Swagger UI

```
https://face-attendance-api.onrender.com/docs
```

### 8b. Create your first admin

```bash
curl -X POST https://face-attendance-api.onrender.com/api/v1/auth/setup-admin \
  -H "Content-Type: application/json" \
  -H "X-Setup-Token: YOUR_SETUP_TOKEN" \
  -d '{"email": "admin@yourdomain.com", "password": "YourStrongPass123!"}'
```

Expected: `{"message": "Admin 'admin@yourdomain.com' created successfully."}`

> **Security:** After this succeeds, remove `SETUP_TOKEN` from Render env vars.
> The endpoint auto-disables once an admin exists, but removing the token is belt-and-suspenders.

### 8c. Login and get a token

```bash
curl -X POST https://face-attendance-api.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@yourdomain.com", "password": "YourStrongPass123!"}'
```

Copy the `access_token` from the response.

### 8d. Endpoint checklist

Use the token as `Authorization: Bearer <token>` for all protected routes.

| Endpoint | Method | Expected |
|---|---|---|
| `/health` | GET | `{"status":"ok"}` — no auth needed |
| `/docs` | GET | Swagger UI loads |
| `/api/v1/auth/me` | GET | Your admin user object |
| `/api/v1/employees` | GET | `[]` (empty list) |
| `/api/v1/attendance/stats` | GET | `{"total_employees":0,...}` |
| `/api/v1/attendance` | GET | `[]` |
| `/api/v1/unknown-faces` | GET | `[]` |

All of these should return `200`. If you get `500` on any DB call, check `DATABASE_URL` in Render dashboard.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Deploy fails at `pip install` | torch download timeout | Render has a 15-min build limit. CPU torch install takes ~8 min. Should be fine. |
| `500` on any DB endpoint | Wrong `DATABASE_URL` | Must use `postgresql+asyncpg://` prefix and port **6543** (pooler), not 5432 |
| `401` on protected routes | Missing/wrong JWT | Re-login, copy fresh token |
| Service sleeps after 15 min | Render free tier | Expected. Use [UptimeRobot](https://uptimerobot.com) free tier to ping `/health` every 5 min |
| `CORS` errors in browser | `CORS_ORIGINS` missing Vercel URL | Add your domain to the env var in Render dashboard |
| Build step `chown` fails | Running as root | Fixed in updated Dockerfile — non-root `appuser` created before `chown` |

---

## UptimeRobot setup (keep free Render service alive)

1. Create free account at [uptimerobot.com](https://uptimerobot.com)
2. New Monitor → **HTTP(s)**
3. URL: `https://face-attendance-api.onrender.com/health`
4. Interval: **5 minutes**
5. Save — your service stays warm 24/7

