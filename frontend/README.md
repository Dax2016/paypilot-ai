# PayPilot AI

PayPilot AI is a React and FastAPI application for exploring AI-assisted commerce, seller management, marketplace shopping, and PayPal Sandbox checkout.

## Technology stack

- Frontend: React, TypeScript, Vite
- Backend: Python, FastAPI
- Database: SQLite
- Payments: PayPal Sandbox

## Prerequisites

- Node.js and npm
- Python with the backend dependencies installed
- PayPal Sandbox API credentials for payment-related features

## Run locally

### 1. Start the backend

Open a PowerShell terminal at the project root:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

Backend health check: http://127.0.0.1:8001/api/health

API documentation: http://127.0.0.1:8001/docs

### 2. Start the frontend

Open a second PowerShell terminal:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Open the local URL printed by Vite, normally http://localhost:5173.

## Tests

From the project root:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m pytest -v
```

Build the frontend:

```powershell
Set-Location .\frontend
npm run build
```

## Payment and security notes

- Payment integration is intended for PayPal Sandbox testing.
- Never commit `.env` files, API secrets, database files, or local virtual environments.
- Keep administrative endpoints protected and use secure authentication before deploying publicly.
- Configure HTTPS, production return URLs, and production-grade persistence and monitoring before a live launch.
- A successful local build or test suite does not by itself establish production readiness.

## Current scope

This repository is under active development. Features and API behavior may change as marketplace and payment workflows evolve.
