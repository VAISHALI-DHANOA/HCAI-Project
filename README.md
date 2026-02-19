# Multi-Agent Playground Full-Stack App

## Folder Structure

```text
.
├── backend
│   ├── app
│   │   ├── __init__.py
│   │   ├── agent_factory.py
│   │   ├── ids.py
│   │   ├── metrics.py
│   │   ├── models.py
│   │   ├── safety.py
│   │   ├── selection.py
│   │   ├── simulation.py
│   │   └── state.py
│   ├── main.py
│   └── requirements.txt
└── frontend
    ├── index.html
    ├── package.json
    ├── tsconfig.app.json
    ├── tsconfig.json
    ├── tsconfig.node.json
    ├── vite.config.ts
    └── src
        ├── App.tsx
        ├── api.ts
        ├── main.tsx
        ├── styles.css
        ├── types.ts
        ├── vite-env.d.ts
        └── ws.ts
```

## Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on [http://localhost:5173](http://localhost:5173). Backend runs on [http://localhost:8000](http://localhost:8000).
