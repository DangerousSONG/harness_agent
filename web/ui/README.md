# SafeHarness Console UI

V0.1 React + Tailwind console for the local FastAPI SafeHarness backend.

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
