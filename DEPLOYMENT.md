# Deploying

The system is three runtime pieces plus two external services:

| Piece | What it is | Where it runs |
|---|---|---|
| API | FastAPI (`backend/`), serves the Flutter app | a web service |
| Worker | Celery worker **with the Beat scheduler** (`--beat`) | a background worker |
| Database | PostgreSQL | Supabase (already in use) |
| Broker | Redis | Redis Cloud (already in use) |
| Mobile app | Flutter, built per environment | the staff's phones |

`backend/Dockerfile` builds one image used for both the API and the worker;
`render.yaml` describes both as a Render Blueprint. Railway works the same way
(two services from the same Dockerfile, the worker's start command overridden
to the one in `render.yaml`).

## What has and hasn't been verified

Be clear-eyed about this before relying on it:

| Item | Status |
|---|---|
| Backend runs and passes its tests against hosted Supabase + Redis | Verified (locally) |
| Alembic migrations apply to a real Postgres | Verified (every migration was applied to Supabase) |
| `Dockerfile` / `render.yaml` | **Written, not built or applied.** The development machine has no Docker, and no Render/Railway account was available. Expect to fix small things on first deploy. |
| HTTPS | Provided by the platform (Render/Railway terminate TLS). Never exercised, since nothing is deployed. |
| Celery worker + Beat running the scheduled jobs | The tasks, schedules and retry/alert logic are tested; a live worker process has **not** been run against the hosted Redis in this repo's history. |
| Push notifications (FCM) | Server and app code written and tested with the FCM call stubbed. **Never delivered to a real phone** (needs your Firebase project). |
| iOS build | Not built (needs a Mac). The deployment target is pinned to iOS 13.0. |

## 1. Backend (Render)

1. Push this repo to GitHub (already done).
2. Render dashboard -> **New -> Blueprint** -> pick the repo. It reads `render.yaml` and proposes the `restaurant-ops-api` web service and the `restaurant-ops-worker`.
3. Fill in the secrets it asks for (`sync: false` in the file):
   - `DATABASE_URL` -- the Supabase **pooler** URL, `postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres`. The direct `db.<ref>.supabase.co` host is IPv6-only (see README, "Free-tier cloud gotchas").
   - `REDIS_URL` -- from Redis Cloud.
4. `JWT_SECRET` is generated for you. `ENVIRONMENT=production` is set, which makes the API **refuse to start** if the secret is still the public default.
5. Deploy. The container runs `alembic upgrade head` and then serves. Check `https://<service>.onrender.com/health` and `/docs`.

### Environment variables

| Variable | Needed by | Notes |
|---|---|---|
| `DATABASE_URL` | API, worker | Supabase pooler URL |
| `REDIS_URL` | API (rate limiting), worker (broker) | Redis Cloud |
| `JWT_SECRET` | API | random, >= 32 chars; startup fails in production if left as the default |
| `ENVIRONMENT` | API, worker | `production` |
| `CORS_ALLOWED_ORIGINS` | API | empty for the mobile app; comma-separated origins for a web client |
| `FCM_CREDENTIALS_PATH` | API, worker | path to the Firebase service-account JSON; unset = no push |
| `LOGIN_RATE_LIMIT_ATTEMPTS`, `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | API | defaults 5 / 900 |

### The first account

Self-registration as Restaurant Manager or Owner only works **once** (the
bootstrap). Register the real Manager first, through the app's Register
screen, before anyone else. After that the Manager creates every other
account from the **Staff** screen. Do not run `scripts/seed_dev_data.py`
against a production database; it creates test accounts with a known password.

### Scaling and cost

- The API is stateless: add instances behind the platform's load balancer.
- Throughput for background work scales by adding worker instances, but
  **run exactly one Beat scheduler**. The Blueprint's single worker embeds it
  (`--beat`). If you add workers, split Beat into its own one-instance service
  and run the extra workers without `--beat`, or every scheduled job fires
  once per scheduler.
- Render's free tier has no free background workers, and a free web service
  sleeps when idle. The scheduled jobs (forecast training at 06:00, etc.) need
  the worker running, so a paid worker (or Railway's usage-based plan) is
  needed for the scheduled behaviour to actually happen.

## 2. Mobile app

The API address is baked in at build time:

```bash
cd frontend
flutter build apk --release --dart-define=API_BASE_URL=https://<service>.onrender.com
```

Use `https://` for anything real; the app talks plain `http://` only to a
local development server.

### Push notifications

1. Create a Firebase project and add an Android app with package
   `com.fyp.restaurantops.restaurant_ops`.
2. **Project settings -> Service accounts -> Generate new private key.** Upload
   the JSON to Render as a Secret File named `firebase-service-account.json`
   (it appears at `/etc/secrets/`, matching `FCM_CREDENTIALS_PATH`).
3. Take the four values from **Project settings -> General** and pass them at
   build time (no `google-services.json` is needed):

   ```bash
   flutter build apk --release \
     --dart-define=API_BASE_URL=https://<service>.onrender.com \
     --dart-define=FIREBASE_API_KEY=... \
     --dart-define=FIREBASE_APP_ID=... \
     --dart-define=FIREBASE_MESSAGING_SENDER_ID=... \
     --dart-define=FIREBASE_PROJECT_ID=...
   ```

Without these the app still works; notifications appear in its inbox but are
not pushed. Every notification is stored first and pushed second, and anything
that couldn't be pushed is retried every 15 minutes.

## 3. Checking a deployment

```bash
# From backend/, with the venv active, pointed at the deployed API
python scripts/measure_performance.py --api --base-url https://<service>.onrender.com
```

This times every main endpoint against the 2-second target. The figures in the
README were measured from a development laptop over a long hop to the hosted
database; a backend deployed in the same region as its database will be
considerably faster.
