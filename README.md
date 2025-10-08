AI Image Editor Backend (FastAPI)

This is a small FastAPI backend that accepts an image and a text prompt, forwards the request to a fal.ai model for image edit/generation, and stores the result. It also exposes simple CRUD-like endpoints to check job status, list jobs, delete jobs, and download results.


## Quick links

- Health check: GET /health
- Create job: POST /api/jobs (multipart form: prompt + image)
- Get job: GET /api/jobs/{job_id}
- List jobs: GET /api/jobs
- Paginated list: GET /api/jobs/page?page=1&page_size=20&status=processing|done|error
- Delete job: DELETE /api/jobs/{job_id}
- Download result: GET /api/jobs/{job_id}/download


## Project structure

```
backend/
	.env                 # environment variables (see below)
	requirement.txt      # pinned dependencies
	app.db               # local SQLite (auto-created)
	app/
		config.py          # Pydantic settings, CORS config, fal.ai defaults
		db.py              # SQLModel engine + session + init_db()
		main.py            # FastAPI app, endpoints, fal.ai integration
		models.py          # SQLModel ORM models (Job)
		schemas.py         # Pydantic response schemas
	uploads/             # source images uploaded by clients
	static/              # generated/edited images saved for local dev
```


## Setup instructions

### Prerequisites

- Python 3.11+ (repo currently used Python 3.13 locally)
- A fal.ai account + API key
- Windows PowerShell (commands below are for Windows) or adapt for your shell

### 1) Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate
python -m pip install --upgrade pip
```

### 2) Install dependencies

```powershell
pip install -r requirement.txt
```

Note: The file is named requirement.txt (singular) in this repo.

### 3) Configure environment variables

Copy `.env` (already present) and set these keys as needed:

```
DATABASE_URL=sqlite:///./app.db
ALLOWED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8000,http://localhost:8000

# fal.ai
FAL_API_KEY=...your_key_here...
FAL_MODEL=fal-ai/seedream-v4
FAL_ENDPOINT=https://fal.run

# Optional tuning
# FAL_TIMEOUT=120
# POLL_INTERVAL=1.5
# POLL_MAX_WAIT=120
```

Dev convenience for Flutter/web dev servers on random ports:
- In code, `config.py` defines `ALLOWED_ORIGIN_REGEX` which you can enable in `app/main.py` if you want to allow any `localhost:*` automatically. By default this repo has very permissive CORS for local development.

### 4) Run the server (local)

From `backend/` directory:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit http://localhost:8000/health to verify.

### 5) Test an API call

Create a job (multipart/form-data):

```powershell
curl -X POST http://localhost:8000/api/jobs ^
	-F "prompt=make it vivid and cinematic" ^
	-F "image=@path\to\local_image.jpg"
```

Response:

```
{
	"job_id": "...uuid...",
	"status": "processing|done|error",
	"result_url": "/static/....png" | "https://...",
	"error": null,
	"created_at": "...",
	"updated_at": "...",
	"prompt": "..."
}
```

Then poll with `GET /api/jobs/{job_id}` until `status` is `done` or `error`.



## fal.ai model used

- Default in code (`app/config.py`): `FAL_MODEL = "fal-ai/seedream-v4"`
- You can override in `.env`. Example used during development: `fal-ai/bytedance/seedream/v4/edit`.
- Endpoint default: `FAL_ENDPOINT = https://fal.run`

Integration details (see `app/main.py`):
- Request body: `{ "prompt": "...", "image_urls": ["data:<mime>;base64,<...>"] }`
- If the POST returns 202, the code follows the `Location` (or JSON `poll_url`) header and polls until the job completes or times out.
- Success response is expected to contain `images[0].url`. The file is then downloaded and saved into `static/` for convenience.


## Architecture overview

- FastAPI app in `app/main.py` wires routes and CORS.
- Settings in `app/config.py` use `pydantic-settings` to load `.env` and provide sane defaults. CORS can be restricted by list (`ALLOWED_ORIGINS`) and optionally enabled by regex (`ALLOWED_ORIGIN_REGEX`) for dev scenarios.
- Persistence uses `SQLModel` (on top of SQLAlchemy). Database is SQLite by default. Tables are created at startup via `init_db()`.
- Job flow:
	1. Client POSTs `prompt` + `image` -> a Job row is created with status `processing`.
	2. A `BackgroundTask` calls fal.ai synchronously with polling.
	3. When done, the result image is downloaded to `static/` and Job is marked `done` with `result_url`.
	4. Errors are captured and stored on the Job (`status=error`, `error=...`).
- Filesystem:
	- `uploads/` stores raw uploaded files.
	- `static/` stores generated/edited results (served via `/static`).


## API reference (brief)

- `GET /health` → `{ ok: true, time: ... }`
- `POST /api/jobs` (multipart form)
	- Fields: `prompt` (text), `image` (file)
	- Response: `JobOut` with `job_id`, `status`, optional `result_url` and `error`.
- `GET /api/jobs/{job_id}` → `JobOut`
- `GET /api/jobs` → `[JobListItem...]`
- `GET /api/jobs/page?page=&page_size=&status=` → `{ page, page_size, total, items: [...] }`
- `DELETE /api/jobs/{job_id}` → `{ detail: "Job deleted" }`
- `GET /api/jobs/{job_id}/download` → Redirect or file download


## Optional features implemented

- Background processing using FastAPI `BackgroundTasks`.
- Static file download of results for easier local testing (`/static/...`).
- Pagination endpoint (`/api/jobs/page`).
- Delete endpoint cleans up files using a safe unlink helper.
- CORS dev-friendly defaults and optional regex to allow any `localhost:*`.


## Known issues / trade-offs

- BackgroundTasks + DB session: the current code passes the request-scoped `Session` into the background task. After the response returns, that session may be closed. It works on small/local setups but is fragile; for robustness, create a fresh Session inside the background function.
- CORS defaults are permissive for development (`allow_origins=["*"]` in the code). Tighten for production (restrict `ALLOWED_ORIGINS`, optionally disable `ALLOWED_ORIGIN_REGEX`).
- SQLite is great for dev, but not ideal for concurrency or scaling. Use Postgres for production.
- No rate limiting or auth on endpoints—add before exposing publicly.
- Minimal validation on uploaded files (type/size). Consider validating MIME types and limiting size.
- fal.ai contract: the code expects `images[0].url`. If the model changes response shape, adjust parsing.


## AI tools usage

- fal.ai is used to perform image edits/generation.
- Auth: `Authorization: Key <FAL_API_KEY>` header.
- Endpoint: `FAL_ENDPOINT` + `FAL_MODEL` (e.g., `https://fal.run/fal-ai/seedream-v4`).
- Request body example (built in code):

```json
{
	"prompt": "replace the background with a sunset beach",
	"image_urls": ["data:image/png;base64,iVBORw0KGgoAAA..."]
}
```

- Behavior:
	- `200` → parse response for `images[0].url`.
	- `202` → follow `Location` header or JSON `poll_url` until complete.
	- Non-2xx → raise error and store on Job.


## Development tips

- Update dependencies file:
	```powershell
	.\.venv\Scripts\python.exe -m pip freeze > requirement.txt
	```
- Run server:
	```powershell
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
	```
- Reset local DB (will drop data): stop the server and delete `app.db`, then restart to re-create tables.


## Implementation notes: AI‑assisted development (prompts & strategy)

This project intentionally leveraged AI coding assistants to accelerate development while keeping changes reviewable and safe. Here is how they were used and the guardrails followed:

### Tools used
- AI assistants: Copilot/ChatGPT-style prompts within the editor.
- Local runtime checks: uvicorn logs, simple curl requests, and browser DevTools (Network) for CORS and caching behavior.

### Prompting and implementation strategy
- Work in small, verifiable steps:
	- Gather context first (read code, identify entry points and settings).
	- Propose minimal edits with clear intent (e.g., “add allow_origin_regex for Flutter dev ports”).
	- Apply concise patches instead of large refactors to preserve readability and git history.
- Keep configuration centralized:
	- All environment variables flow through `app/config.py` (typed `Settings` with defaults), values supplied via `.env` or deployment env.
- Validate early:
	- Run local server and hit `/health` after changes.
	- Use `pip list` / `pip freeze` to pin dependencies in `requirement.txt`.
	- Inspect logs and HTTP responses (e.g., 304 explanation for static cache validation).
- Document as we go:
	- Added `.env.example` for safe secrets management.
	- Expanded README with setup, architecture, and deployment notes.

### Example prompts (summarized)
- “Diagnose Pydantic ValidationError extra_forbidden and align Settings with `.env` keys.”
- “Make CORS friendly for Flutter’s random dev ports; prefer allow_origin_regex.”
- “Add S3-compatible storage option so results persist on Render; return public URLs.”
- “Generate requirements from the venv and populate requirement.txt.”
- “Explain why a static file request returned 304 Not Modified.”

### Guardrails and best practices
- Secrets never committed:
	- Real keys live in `.env` (local) or Render environment variables.
	- `.env.example` documents required values without secrets.
- Principle of least change:
	- Minimal code edits, focused on specific outcomes (CORS fix, storage backend, README docs).
- Production readiness considerations:
	- SQLite only for local dev; prefer Postgres in production.
	- Object storage (S3/R2) for persistent results; local `static/` only for dev.
	- Restrict CORS in production to known frontend origins.
- Human review:
	- All generated code was reviewed and tested locally before considering deployment.

### Limitations
- AI suggestions can be confident but incomplete; every change was validated in a running app and adjusted when needed.
- Background task/session lifecycle and error paths should be revisited if workload or scale increases (move to a worker/queue if necessary).




