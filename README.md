# URL Shortener API (Advanced, FastAPI)

A production-style URL shortener REST API built with **FastAPI**, featuring:

- 🔗 Random or custom short codes
- 🔐 JWT authentication (optional — anonymous links work too)
- ⏰ Link expiration
- 📊 Click analytics (IP, user-agent, referrer, timestamp)
- 🚦 Rate limiting (10 requests/minute on link creation)
- ⚡ In-memory caching for fast redirects
- 📱 QR code generation for every short link
- 📘 Auto-generated interactive docs (Swagger UI)

---

## 1. Project Structure

```
url-shortener/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app & all routes
│   ├── models.py         # SQLAlchemy ORM models (User, ShortLink, ClickEvent)
│   ├── schemas.py        # Pydantic request/response schemas
│   ├── database.py       # DB engine/session setup
│   ├── auth.py            # Password hashing + JWT logic
│   ├── utils.py            # Short code generator, QR code, cache
│   └── static/
│       └── index.html      # Visual frontend demo (served at "/")
├── requirements.txt
├── render.yaml              # Render deployment config (optional, for one-click deploy)
├── .gitignore
├── .env.example
└── README.md
```

## 2. Setup — Step by Step

### Step 1: Make sure you have Python 3.10+
```bash
python3 --version
```

### Step 2: Create a virtual environment (recommended)
```bash
cd url-shortener
python3 -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate
```

### Step 3: Install dependencies
```bash
pip install -r requirements.txt
```

### Step 4: (Optional) Set environment variables
Copy `.env.example` to `.env` and adjust if you want a custom secret key or a different database:
```bash
cp .env.example .env
```
By default, it uses a local SQLite file (`shortener.db`) — no extra setup needed.

### Step 5: Run the server
```bash
uvicorn app.main:app --reload
```

You should see:
```
Uvicorn running on http://127.0.0.1:8000
```

### Step 6: Open the app
Go to **http://127.0.0.1:8000/** in your browser. This loads a small visual frontend (`app/static/index.html`) — you can paste a URL, shorten it, see the QR code, copy the link, sign up/log in, and manage your own links, all without touching the command line.

For the raw API reference (useful when you want to test endpoints directly, or for your lab report), go to **http://127.0.0.1:8000/docs**.

---

## 3. How to Use the Frontend (Visual Demo)

The frontend is a single static HTML/CSS/JS file served directly by the FastAPI backend — there's no separate frontend server to run, no npm install, nothing extra. It talks to the same backend using plain `fetch()` calls.

1. Open **http://127.0.0.1:8000/**
2. Paste a long URL into the box and click **Shorten** — a short link and QR code appear instantly
3. Click **Sign up** (top right) to create an account, or **Log in** if you already have one
4. Once logged in, links you create are tied to your account and show up in the **Your links** table below, where you can delete them
5. Click **Copy** to copy the short link, or **Refresh clicks** to see the live click count update after you visit the link

This is intentionally a single plain HTML file (no React/build step) so it's easy to read top-to-bottom and easy to modify — open `app/static/index.html` in any text editor to change colors, text, or add fields.

---

## 4. How to Use the API Directly

### Register a user (optional — links can also be created anonymously)
```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "deepanshu", "password": "mypassword123"}'
```

### Login to get a JWT token
```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -d "username=deepanshu&password=mypassword123"
```
Response:
```json
{"access_token": "eyJhbGciOi...", "token_type": "bearer"}
```

### Create a short link
```bash
curl -X POST http://127.0.0.1:8000/links \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_token>" \
  -d '{"original_url": "https://example.com/a/very/long/path", "expires_in_days": 7}'
```

### Create a short link with a custom alias (e.g. short.ly/my-event)
```bash
curl -X POST http://127.0.0.1:8000/links \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com", "custom_alias": "myevent"}'
```

### Visit the short link (redirects to original)
Just open in a browser: `http://127.0.0.1:8000/myevent`

### Get click analytics for a link
```bash
curl http://127.0.0.1:8000/links/myevent/stats
```

### Get a QR code for a link
```bash
curl http://127.0.0.1:8000/links/myevent/qrcode
```

### List all your own links (requires login)
```bash
curl http://127.0.0.1:8000/links/mine \
  -H "Authorization: Bearer <your_token>"
```

### Delete a link (must be the owner)
```bash
curl -X DELETE http://127.0.0.1:8000/links/myevent \
  -H "Authorization: Bearer <your_token>"
```

---

## 5. How It Works Internally (Architecture)

1. **`POST /links`** — Validates the URL (Pydantic's `HttpUrl`), generates a Base62 random short code (or uses your custom alias), checks for collisions, saves a `ShortLink` row, and optionally links it to the logged-in user.
2. **`GET /{short_code}`** — This is the hot path. It:
   - Checks an in-memory TTL cache first
   - Looks up the DB for the real redirect target
   - Logs a `ClickEvent` row (IP, user-agent, referrer) for analytics
   - Increments the link's `click_count`
   - Returns an HTTP 302 redirect
3. **JWT auth** is optional on link creation (so anonymous users can shorten links too) but required for `/links/mine` and deleting links — this demonstrates mixed optional/required auth dependencies in FastAPI.
4. **Rate limiting** via `slowapi` protects the creation endpoint from abuse (10 requests/minute per IP).
5. **SQLite** is the default database for easy local setup; swapping `DATABASE_URL` in `.env` to a PostgreSQL URL works with zero code changes thanks to SQLAlchemy.

---

## 6. Deploying It Live (Free, on Render)

This takes your project from "only runs on my laptop" to "has a real public URL anyone can open." We'll use **Render** because it has a free tier and doesn't require a credit card for basic web services.

> **One important thing to know first:** the free setup below uses SQLite, a file-based database. Render's free tier does **not** keep files between deploys/restarts — so your links will reset occasionally. This is totally fine for a demo/portfolio project. If you want permanent storage later, see the note at the end of this section about switching to Render's free PostgreSQL database.

### Step 1: Put your project on GitHub
If you haven't already:
1. Go to [github.com](https://github.com) and create a free account if you don't have one
2. Click **New repository**, name it something like `url-shortener-api`, keep it Public, and click **Create repository**
3. On your computer, inside the `url-shortener` folder, run:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/url-shortener-api.git
   git push -u origin main
   ```
   (Replace `YOUR_USERNAME` with your actual GitHub username — the exact remote URL is also shown on your new repo's GitHub page.)

### Step 2: Create a Render account
1. Go to [render.com](https://render.com) and sign up — the easiest way is "Sign up with GitHub," which also connects your repos automatically
2. Authorize Render to access your GitHub account when prompted

### Step 3: Create a new Web Service
1. On your Render dashboard, click **New +** → **Web Service**
2. Find and select your `url-shortener-api` repository, then click **Connect**
3. Render will try to auto-detect settings. Fill in / confirm these fields:
   - **Name**: `snip-url-shortener` (or anything you like — this becomes part of your URL)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
4. Scroll to **Environment Variables** and add:
   - `SECRET_KEY` → any long random string (e.g. `kj3h4k5jh3k4jh5k3j4h5k`)
   - `DATABASE_URL` → `sqlite:///./shortener.db`
5. Click **Create Web Service**

> If your repo includes the `render.yaml` file from this project, Render can detect it automatically and pre-fill most of this for you via "New + → Blueprint" instead of "Web Service."

### Step 4: Wait for the build
Render will install your dependencies and start the server. You'll see live logs — wait until you see something like `Uvicorn running` in the log output and the status turns **Live**.

### Step 5: Open your live app
Render gives you a public URL that looks like:
```
https://snip-url-shortener.onrender.com
```
Open it in your browser — you'll see the same frontend you ran locally, except now it's live on the internet. Share this link with anyone.

### (Optional) Alternative: Deploying on Railway instead
The steps are nearly identical:
1. Go to [railway.app](https://railway.app) and sign up with GitHub
2. Click **New Project** → **Deploy from GitHub repo** → select your repo
3. Under the service's **Settings**, set:
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Under **Variables**, add `SECRET_KEY` and `DATABASE_URL` the same way as above
5. Railway auto-deploys and gives you a public `*.up.railway.app` URL under the **Settings → Networking** tab (click **Generate Domain**)

### (Optional) Making data permanent with a real database
Render's free tier includes a free PostgreSQL database for 90 days (paid after that). If you want your short links to survive restarts long-term:
1. On Render, click **New +** → **PostgreSQL**, create a free instance
2. Copy its **Internal Database URL**
3. Go back to your web service → **Environment** → set `DATABASE_URL` to that copied value (it will look like `postgresql://user:pass@host/dbname`)
4. Add `psycopg2-binary` to `requirements.txt` (needed for PostgreSQL support) and redeploy

No code changes are needed beyond that — this works because the project already reads `DATABASE_URL` from the environment via SQLAlchemy.

---

## 7. Ideas to Extend This Further

- Swap the in-memory cache for **Redis** for multi-server deployments
- Add a simple frontend (HTML/React) to create and manage links visually
- Add link **password protection** (require a password to redirect)
- Add **bulk URL shortening** (upload a CSV of URLs)
- Deploy it to **Render/Railway/Fly.io** and get a real public short domain
- Add **geo-location** lookup on click events (using the IP address)

---

## 8. Running Tests Manually

A quick Python smoke test (no pytest setup needed) — paste this into a `test_api.py` and run `python test_api.py`:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

r = client.post("/links", json={"original_url": "https://www.google.com"})
print(r.json())

code = r.json()["short_code"]
r = client.get(f"/{code}", follow_redirects=False)
print(r.status_code, r.headers["location"])
```
