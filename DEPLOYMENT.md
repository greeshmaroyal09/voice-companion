# Deploy FastAPI, then review a Vercel preview

Only the frontend is currently deployed. FastAPI at `http://127.0.0.1:8000` is reachable from this computer, not from Vercel. The working tree was clean before this preparation. No backend application code, provider integration, `.env`, frontend API wrapper, or local Vite proxy was changed.

**Keep the existing frontend project and its exact submitted production URL: `https://voice-companion-khaki.vercel.app/`. Do not create or rename a Vercel project, remove this domain, or substitute a preview URL as the submitted URL.** Preview deployments are temporary review addresses within that same project.

## 1. Account and backend deployment

Use a **Render account**, signed in with the GitHub account that can access `greeshmaroyal09/voice-companion`. Keep the existing **Vercel account/project** for the frontend. No new GitHub repository, database, or provider account is needed; your existing Gnani account/key must have STT/TTS access and credits. Gemini is optional.

The deployment files are prepared locally. Before following these steps, commit `.python-version`, `render.yaml`, and this guide to a **new deployment-preparation branch**, then push that branch. Do not push to `main` or merge it yet, because Vercel may automatically update production from `main`. Include `deployment/`, `.vercelignore`, and the `.gitignore` changes on that branch for the later preview. Do not commit `.env` or generated `deployment/vercel.preview.json`.

From this repository in PowerShell (choose a different branch name if this one already exists):

```powershell
git switch -c deploy/backend-routing
git add .python-version render.yaml .vercelignore .gitignore deployment DEPLOYMENT.md
git commit -m "Prepare backend deployment and preview routing"
git push -u origin deploy/backend-routing
```

This may trigger an automatic **branch preview** in Vercel. Its API routing is not ready until the real backend URL is added later. It does not replace production. Select `deploy/backend-routing` as the Render branch below.

In the [Render Dashboard](https://dashboard.render.com/):

1. Sign up/sign in. Choose **New + → Web Service**.
2. Choose the Git repository deployment option, connect GitHub if needed, and authorize access to **`greeshmaroyal09/voice-companion`**. Choose that repository and **Connect**. If it is not listed, adjust the GitHub integration's repository selection to include it.
3. Configure the service as follows:

   | Setting | Exact value |
   | --- | --- |
   | Name | `voice-companion-api` (choose another available name if necessary) |
   | Region | Singapore, or your preferred available region |
   | Branch | The deployment-preparation branch you just pushed |
   | Root Directory | **Leave empty**: commands must run from the repository root |
   | Language / Runtime | **Python 3** |
   | Build Command | `python -m pip install -r backend/requirements.txt` |
   | Start Command | `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1` |
   | Health Check Path | `/api/health` |
   | Instances | **1**; do not enable autoscaling |
   | Auto-Deploy | **Off** during review |

4. Choose **Free** if you want a no-cost demonstration deployment. It can sleep after inactivity and take time to wake. If you choose paid compute for continuous availability, review its displayed price first. Keep one instance regardless of plan. The included `render.yaml` uses Free, one instance, Singapore, and auto-deploy off.
5. Under **Environment Variables**, enter the names in the following table. Paste actual secrets directly into Render's environment/secret fields. Do not put keys in chat, Git, frontend source, a `VITE_` variable, or Vercel project environment variables.
6. Choose **Deploy Web Service**. Inspect **Logs** until Uvicorn reports successful startup and Render reports the service as live.
7. Under the service's **Settings**, confirm the health path is `/api/health`, auto-deploy is off, and there is one instance. If the creation screen did not expose a field, set it here.
8. Copy the service's actual HTTPS URL from Render, then open `<that URL>/api/health`. It must return JSON with `"status":"ok"` and `"gnani_configured":true`. The actual assigned hostname is authoritative; the service name does not guarantee a particular hostname.

The root `.python-version` contains `3.12`. Render supports this format and selects the latest corresponding Python patch. Do not override it with a different `PYTHON_VERSION` setting.

### Backend environment variable names

| Name | Requirement | Where/value |
| --- | --- | --- |
| `GNANI_API_KEY` | **Required for voice and reply audio** | Render secret setting; your actual existing key |
| `GEMINI_API_KEY` | Optional | Render secret setting, only if you want Gemini interpretation; local deterministic conversation still works without it |
| `GEMINI_MODEL` | Optional, non-secret | Set your provider-supported model ID if overriding the app's existing default |
| `PORT` | Required by the start command | Render supplies it automatically; do not replace it with a local port |
| `WEB_CONCURRENCY` | Recommended | `1`; the start command also explicitly fixes `--workers 1` |
| `PYTHONUNBUFFERED` | Recommended | `1`, so logs appear promptly |
| `SSL_CERT_FILE` | Only for a host requiring an administrator-approved custom CA | Absolute path to a valid PEM bundle **on that host**. Do not copy a Windows path to Render. Otherwise leave unset; never disable certificate verification. |

There are **no required frontend environment variables**. Do not copy your local `.env` into the host or upload it to Vercel. Render injects the secret settings into the Python process; the existing app already reads them.

Alternative: Render's **New + → Blueprint** flow can use the included `render.yaml` from the preparation branch. It prompts for `GNANI_API_KEY` (`sync: false`). Add optional Gemini settings directly to the resulting service's Environment page. The manual Web Service flow above is sufficient; do not create a second backend service as well.

### Session limitation

`backend/conversation.py` holds sessions in Python memory for one hour of inactivity. **One Uvicorn worker and one host instance are required.** Restarting, redeploying, or sleeping can clear sessions. Multiple workers/instances can cause intermittent expired-session and missing-turn errors. A persistent/shared session store would be a separate backend change; it was not introduced here.

## 2. Once you have the actual backend URL

Send only the HTTPS base URL back in chat, not a key. The next step is to verify its health and generate the Vercel rewrite:

```powershell
.\.venv\Scripts\python.exe -m deployment.prepare_preview https://ACTUAL-ASSIGNED-BACKEND-HOST
```

Substitute Render's actual HTTPS origin, with no `/api` suffix. The command refuses loopback, private IPs, documentation/placeholder domains, non-HTTPS origins, credentials in URLs, and an unhealthy/unconfigured backend. It writes **`deployment/vercel.preview.json`** only after health succeeds. HTTPS certificate validation stays enabled.

Continue only if the generator succeeds. Review the generated config, then copy it to root `vercel.json` **on the preparation branch only**, so remote rebuilds and later Git deployments retain the same reviewed rewrite:

```powershell
Copy-Item -LiteralPath deployment/vercel.preview.json -Destination vercel.json
```

There is currently no root `vercel.json`. If someone adds one before this step, merge its settings instead of blindly overwriting it. Commit this generated root config on the preparation branch, not `main`, before creating the preview.

The generated config has this order:

```json
"rewrites": [
  {
    "source": "/api/:path*",
    "destination": "https://ACTUAL-ASSIGNED-BACKEND-HOST/api/:path*"
  },
  { "source": "/(.*)", "destination": "/index.html" }
]
```

The `/api` prefix is preserved. API responses are marked `no-store`, and external rewrite caching is disabled. `deployment/vercel.template.json` is deliberately inactive and contains a reserved `.invalid` hostname. **Do not deploy the template.** No root `vercel.json` with a guessed host was created.

The frontend continues to call relative `/api/...` paths. Local Vite continues to proxy `/api` to `http://127.0.0.1:8000`. A browser-side backend URL or CORS change is unnecessary with the same-origin Vercel rewrite.

## 3. Create a preview only

After health validation, use your Vercel account to link this checkout to the existing **voice-companion** project. The prepared `.vercelignore` limits CLI uploads to the frontend and routing config and excludes backend files, `.env` files, and key/certificate files.

If Vercel CLI is not installed, these commands run it from the official npm package:

```powershell
npx.cmd vercel@latest login
npx.cmd vercel@latest link
```

In the prompts, select the team/account containing `voice-companion-khaki.vercel.app` and **the existing `voice-companion` project**. Do not create a duplicate frontend project. If the project is not visible, use the account that owns it.

In that project's **Settings → Domains**, confirm that **`voice-companion-khaki.vercel.app`** is already attached. Leave the project name and domain settings unchanged.

Check Vercel **Project → Settings → Environment Variables** for Preview and Production. Neither environment should contain `GNANI_API_KEY`, `GEMINI_API_KEY`, or any `VITE_` copy of those keys. Enter provider keys only on Render. No provider keys are needed by this frontend build.

Create the preview with the generated config:

```powershell
npx.cmd vercel@latest deploy --environment=preview --local-config deployment/vercel.preview.json
```

This command targets **Preview**. Do not use `--prod`, promote a deployment, or change production aliases. Record the resulting unique preview URL. The production domain must remain unchanged during this review.

## 4. Verify through that Vercel preview

```powershell
.\.venv\Scripts\python.exe -m deployment.verify_preview https://ACTUAL-VERCEL-PREVIEW-HOST
```

The checker:

- Confirms `/api/health` JSON, backend key presence as a Boolean, `Cache-Control: no-store`, and request-ID propagation.
- Confirms a nonexistent `/api` route returns FastAPI's JSON 404 instead of frontend HTML.
- Sends a synthetic SBI account-opening message and one follow-up using the same session.
- Requests reply audio for the saved turn and validates a nonempty 24 kHz mono 16-bit WAV.
- Restores both turns and clears only that synthetic session afterward.
- Logs statuses and request IDs without printing keys, response bodies, or the bypass secret. It refuses the known production domain.

If the preview is protected, the script will report the HTTP failure. For automation, Vercel's deployment-protection bypass secret can be supplied to the checker process as `VERCEL_AUTOMATION_BYPASS_SECRET`; it is sent only as the bypass header and is never printed. It is **not** a provider key or a frontend build variable. Do not disable protection just to make a test pass.

On failure, use the printed request ID to find the matching Render log. A Vercel plain-text 404 means the rewrite was not included; FastAPI JSON 404 with an expired session indicates memory/session lifetime or scaling; a FastAPI 502/504 after a Gnani log identifies a provider/transport problem. No provider body or key needs to be shared to diagnose it.

## 5. Promote the reviewed fix while retaining the submitted URL

Do this **only after the preview journey passes and you approve the preview**. These instructions do not perform a promotion now.

1. Open the **existing** Vercel `voice-companion` project → **Deployments**.
2. Find the exact preview deployment you tested. Open its **…** menu → **Promote to Production**.
3. Check the confirmation's destination domains. It must include **`voice-companion-khaki.vercel.app`**. If it does not, cancel and check that you selected the original project; do not rename/create a project or move domains.
4. Confirm **Promote to Production**. Vercel rebuilds a Preview deployment using Production settings, so wait for the resulting production deployment to be **Ready / Current**. Provider keys still belong only on Render; no provider-key changes on Vercel are required.
5. Verify the original URL using the checks below. Retain the tested root `vercel.json` in the production branch after approval, so a later Git deployment does not remove the fix.

Optional CLI equivalent, from the checkout linked to that same existing project:

```powershell
npx.cmd vercel@latest promote https://ACTUAL-TESTED-PREVIEW-HOST
```

Read the confirmation rather than passing `--yes`. When promoting a Preview build, the CLI creates a new production deployment and may return before its build finishes. Wait in the dashboard or run `npx.cmd vercel@latest inspect https://NEW-PRODUCTION-DEPLOYMENT-HOST --wait` using the deployment URL it prints. That generated URL is not a replacement for the submitted domain.

### Verify the original submitted domain

Open **`https://voice-companion-khaki.vercel.app/api/health`**. It must return HTTP 200 JSON:

```json
{"status":"ok","gnani_configured":true}
```

For a status/content-type check in PowerShell, avoiding the `curl` alias:

```powershell
curl.exe --fail-with-body --include https://voice-companion-khaki.vercel.app/api/health
```

Expect HTTP 200, `Content-Type: application/json`, and `Cache-Control: no-store`, not Vercel's plain-text `NOT_FOUND` or frontend HTML. Then open **`https://voice-companion-khaki.vercel.app/`**, start a new synthetic conversation, and listen to its reply. The submitted URL stays exactly the same; only the backend routing behind it changes.

If production verification fails, use the existing project's Deployments menu to roll back to its previous production deployment and inspect the failing request's ID in Render logs. Do not replace or rename the frontend project. No promotion or rollback is performed by the preparation scripts.

## Current status

- Confirmed by you: frontend only on Vercel; backend is local and has no hosted URL.
- Prepared: native Python 3.12 deployment, one-worker/one-instance configuration, inactive rewrite template, health-gated preview config generator, preview smoke checker, and upload exclusions.
- Not performed: backend account creation, hosted secret configuration, backend deployment, Vercel preview deployment, preview health/text/audio checks, or production change.
- **Immediate next step:** create the Render Web Service using section 1, enter `GNANI_API_KEY` there, and return the actual HTTPS backend URL.

Local validation: `python -m pytest backend deployment -q` passed **109 tests**, including mocked rewrite/health/session/WAV checks. This does not claim that a real hosted backend or Vercel preview has been deployed or exercised.

## Official references

- [Render FastAPI deployment](https://render.com/docs/deploy-fastapi)
- [Render Python version selection](https://render.com/docs/python-version)
- [Render Blueprint specification and secret fields](https://render.com/docs/blueprint-spec)
- [Vercel external rewrites](https://vercel.com/docs/routing/rewrites)
- [Vercel CLI deploy](https://vercel.com/docs/cli/deploy)
- [Vercel CLI global options](https://vercel.com/docs/cli/global-options)
- [Vercel promotion workflow](https://vercel.com/docs/deployments/promoting-a-deployment)
- [Vercel CLI promote](https://vercel.com/docs/cli/promote)
