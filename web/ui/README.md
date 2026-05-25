# SafeHarness Console UI

V0.1 React + Tailwind console for the local FastAPI SafeHarness backend.

## First-time setup

From the repository root:

```powershell
# Python deps (server + crawl4ai + playwright Python package)
pip install -r requirements.txt

# Playwright browser binary (needed by crawl4ai to render JS pages).
# Skipping this leaves the web_search pipeline unable to crawl modern
# news / baijiahao / NYT-style pages.
playwright install chromium
# or, equivalently:
#   crawl4ai-setup

# (Optional) test dependencies — needed for `python -m unittest` to
# exercise web/server.py via fastapi.testclient.
pip install -r requirements-dev.txt
```

Run the backend from the repository root:

```powershell
uvicorn web.server:app --reload --host 127.0.0.1 --port 8000
```

Run the frontend from `web/ui`:

```powershell
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`. The UI only calls backend APIs; it does not read or write local asset files directly.

## Verifying crawl4ai is ready

After `pip install -r requirements.txt` and `playwright install chromium`, hit:

```powershell
curl.exe http://127.0.0.1:8000/api/settings/crawl4ai/health
```

A working install reports `installed: true`, `playwright_module: installed`, and `playwright_browser: available`. If the browser line is missing, run `playwright install chromium` again.
