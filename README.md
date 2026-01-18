# Plattera

Convert legal property descriptions into visual boundaries.

## Project Structure

```
Plattera/
├── backend/                 # Python FastAPI backend
│   ├── main.py             # FastAPI app entry point
│   ├── api/                # API routes and endpoints
│   ├── core/               # Core processing modules
│   └── requirements.txt    # Python dependencies
├── frontend/               # React frontend
│   ├── src/               # React source code
│   ├── package.json       # Node dependencies
│   └── vite.config.ts     # Vite configuration
└── project_plan.md        # Detailed project plan
```

## Quick Start

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
python main.py
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## Development

This is the basic skeleton structure. Core logic will be implemented in the `backend/core/` modules and connected through the API endpoints.

The frontend provides a basic interface for text input, processing status, and map visualization using React and Leaflet.

## Index Maintenance API

Backend endpoints mounted under `/api/index` provide safe diagnostics and bounded maintenance jobs:

- `GET /api/index/diagnose` â€” stable pool health report (optionally include slice diagnoses)
- `POST /api/index/execute` â€” enqueue a bounded maintenance job (missing_only | missing_and_stale)
- `GET /api/index/jobs/{job_id}` â€” poll job status and results
