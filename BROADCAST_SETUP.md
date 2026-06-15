# Public status broadcast — setup

Architecture: the **control app runs only on this PC** (it drives a real Chrome).
The backend periodically pushes a sanitized `status.json` to a **public GitHub
repo**, and a **read-only page on Vercel** reads that file. No tunnel, no open ports.

```
This PC (private, full control)         Public (read-only)
 FastAPI :8000 + real Chrome             Vercel page  ──fetch──┐
 publisher job ──push every 30m──▶  GitHub repo: status.json ◀┘
```

## One-time setup

### 1. Create a public repo for the snapshot
- New **public** GitHub repo, e.g. `dashboard-status`, default branch `main`.
- Add any placeholder `status.json` (e.g. `{}`) so the branch exists.

### 2. Create a token (least privilege)
- GitHub → Settings → Developer settings → **Fine-grained tokens**.
- Repository access: **Only** `dashboard-status`.
- Permissions: **Contents → Read and write**. Nothing else.
- Copy the token.

### 3. Configure the backend (`.env`)
```
GITHUB_TOKEN=github_pat_xxx
STATUS_REPO=YOUR_USER/dashboard-status
# STATUS_BRANCH / STATUS_PATH / PUBLISH_INTERVAL_MINUTES already defaulted
```
Restart the backend. You should see a log line:
`[publisher] every 30m -> YOUR_USER/dashboard-status/status.json`
and within a few seconds `status.json` updates in the repo.

### 4. Point Vercel at the snapshot
Either edit `frontend/.env.production` (replace `OWNER/REPO`) **or** set in
Vercel → Settings → Environment Variables:
```
VITE_PUBLIC_MODE = true
VITE_STATUS_URL  = https://raw.githubusercontent.com/YOUR_USER/dashboard-status/main/status.json
```
Redeploy. The Vercel site now shows the read-only board (no login, no controls).

## Daily use

- **Control everything locally:** run the backend (`uvicorn`), then
  `cd frontend && npm run dev` → open `http://localhost:5173`, log in. Full buttons.
- **Check status from anywhere:** open the Vercel URL. Shows "Live / updated Xm ago"
  while this PC is publishing, and "Offline / last updated …" when it's asleep/off.

## Keep it fresh
For the board to stay current this PC must be on, awake, and logged in (Chrome runs
headed). Set the power plan to never sleep and auto-start the backend at logon.

## Note
`status.json` is **fully public** — it intentionally includes real @handles and all
analytics. It never contains tokens, the password hash, draft tweet bodies, target
URLs, or screenshots.
