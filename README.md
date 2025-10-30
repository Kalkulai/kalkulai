# Kalkulai Monorepo

Unified workspace that hosts the FastAPI backend (LLM powered offer builder) and the React/Vite frontend. The repo is optimised for local development, HF Spaces deployment for the backend, and Cloudflare Pages for the frontend.

## Repository layout
- `backend/` – FastAPI application, LangChain integrations, PDF rendering, Space Dockerfile.
- `frontend/` – React + Vite SPA that talks to the backend via REST.
- `.github/workflows/` – CI/CD pipelines for Hugging Face Spaces (`backend-deploy-hf.yml`) and Cloudflare Pages (`frontend-deploy-cf.yml`).

## Prerequisites
- Python 3.11+
- Node.js 20+ (managed via `nvm` recommended)
- For LLM access: either an OpenAI API key or a locally running Ollama instance.

## Backend setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # adjust values as needed
uvicorn main:app --reload
```

Key environment variables (see `backend/.env.example` for the full list):
- `MODEL_PROVIDER` – `openai` or `ollama`.
- `OPENAI_API_KEY` / `OLLAMA_BASE_URL` – credentials or local base URL.
- `FRONTEND_ORIGINS` – comma separated list of allowed origins for CORS (include your Cloudflare Pages domain).
- `SKIP_LLM_SETUP` – set to `1` to boot the API without hitting LLM providers (handy for smoke tests).

Generated assets:
- Vector store is written to `backend/chroma_db/` by default.
- Generated PDFs land in `backend/outputs/` and are served via `/outputs/...`.

## Frontend setup
```bash
cd frontend
npm ci
cp .env.example .env.local  # set VITE_API_BASE to your backend URL
npm run dev
```

`VITE_API_BASE` should point to the backend origin (omit trailing slash). Leave it empty when running behind the same domain with a reverse proxy.

## Testing & linting
- Backend: `python -m venv .venv && source .venv/bin/activate` then `pip install -r backend/requirements-dev.txt` and run `pytest backend/testing`.
- Frontend: `npm run test` (Vitest) and `npm run lint`.

## Deployment pipelines
1. **Hugging Face Space (backend)** – pushes to `main` touching `backend/**` or the workflow file trigger the Space upload via `backend-deploy-hf.yml`. Requires `HF_TOKEN` and `HF_SPACE_ID` repository secrets.
2. **Cloudflare Pages (frontend)** – PR validation runs build CI; pushes to `main` deploy using `frontend-deploy-cf.yml`. Requires `CF_API_TOKEN`, `CF_ACCOUNT_ID`, and `CF_PROJECT_NAME` secrets.
3. **Smoke Tests** – `smoke-tests.yml` runs backend pytest smoke checks and the frontend build/test on every PR and on pushes to `main`.
4. **Main branch guard** – `block-direct-main.yml` rewinds `main` to the previous commit when someone pushes directly (außer PR-Merges/Bots) und markiert den Workflow als fehlgeschlagen. Direkte Pushes gehen dadurch sofort verloren – nutzt bitte PRs.

## Local-development tips
- When running both services locally, start the backend first so the frontend can reach it at `http://localhost:8000`.
- To avoid LLM costs while iterating on the UI, run the backend with `SKIP_LLM_SETUP=1`. Only the health/reset endpoints stay live in that mode.
- The backend exposes a `/api/session/reset` endpoint that the frontend calls on mount to clear conversation state.

## Next steps
- Add automated tests for critical backend flows (chat to offer, PDF generation).
- Introduce a shared `.env` loader or configuration module to keep environment management DRY.
- Expand documentation around the dataset files in `backend/data/` and how they are updated.
