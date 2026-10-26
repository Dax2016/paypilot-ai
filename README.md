# PayPilot AI

**Your AI-powered shopping and commerce assistant.**

PayPilot AI combines an AI shopping assistant, a product marketplace, seller and product management, and PayPal Sandbox checkout in one application. Shoppers can explore available products and ask the assistant for catalogue-grounded recommendations, while the dashboard and backend provide commerce management capabilities.

> **Project status:** Working local prototype. Payments use PayPal Sandbox; live payment processing and production deployment are not configured.

## Features

- **AI shopping assistance:** Ask questions and compare products using the available marketplace catalogue.
- **Product marketplace:** API support for listing products and retrieving product details and categories.
- **Seller management:** Register sellers and approve sellers through administrative endpoints.
- **Product publishing:** Administrative endpoint for publishing products.
- **PayPal Sandbox checkout:** Create PayPal orders and capture approved Sandbox payments.
- **Dashboard:** Retrieve commerce dashboard data from the backend.
- **Local persistence:** SQLite database support for application data.
- **API documentation:** Explore backend endpoints through FastAPI's interactive documentation.

## Technology stack

| Layer | Technologies |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI, Uvicorn |
| AI | OpenAI API |
| Payments | PayPal REST API, Sandbox environment |
| Data | SQLite |
| API validation | Pydantic |

## Architecture

```text
Shopper
   |
   v
React + TypeScript frontend
   |
   v
FastAPI backend
   |--------------------|
   v                    v
OpenAI API         SQLite database
   |
   v
Catalogue-grounded shopping assistance

FastAPI backend
   |
   v
PayPal Sandbox API
   |
   v
Sandbox order creation and capture
```

The AI assistant helps shoppers understand the available catalogue. Payment operations are handled separately by the backend's PayPal integration, not by the assistant conversation.

## Requirements

- Python 3.13 or a compatible Python version
- Node.js and npm
- PayPal Sandbox REST API credentials for checkout testing
- An OpenAI API key for AI-powered assistant responses

## Run locally

### 1. Clone the repository

```bash
git clone https://github.com/Dax2016/paypilot-ai.git
cd paypilot-ai
```

### 2. Configure the backend

Open a terminal in the project root and run:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a file named `.env` inside the `backend` directory:

```dotenv
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=your_sandbox_client_id
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret
PAYPILOT_ADMIN_TOKEN=replace_with_a_long_random_admin_token
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
```

Replace the placeholders with your own credentials. Obtain PayPal credentials from your PayPal Developer Dashboard's Sandbox application settings.

`OPENAI_MODEL` is optional; the application defaults to `gpt-4.1-mini`.

Start the backend from the `backend` directory:

```powershell
uvicorn main:app --reload --port 8001
```

The API will be available at `http://127.0.0.1:8001`.

Interactive API documentation: http://127.0.0.1:8001/docs

Health check: http://127.0.0.1:8001/api/health

### 3. Start the frontend

Open a second terminal:

```powershell
cd C:\Users\Darchums\Projects\paypilot-ai\frontend
npm ci
npm run dev
```

Open the local URL printed by Vite, normally:

http://localhost:5173

Keep both development servers running while using the application.

### 4. Test PayPal Sandbox checkout

1. Configure your PayPal Sandbox client ID and secret in `backend/.env`.
2. Start the backend and frontend.
3. Use the application's payment flow to create a Sandbox order.
4. Approve the order through PayPal's Sandbox checkout flow.
5. Return to the application and allow the backend to capture the order and refresh the dashboard.

Use PayPal Sandbox buyer credentials for testing. Do not enter real payment credentials into the prototype.

### 5. Test the AI assistant

Add a valid `OPENAI_API_KEY` to `backend/.env` and restart the backend. The shopping assistant uses the configured OpenAI model and the available product catalogue to answer shopping questions.

If the API key is missing or invalid, AI-powered requests may fail. Catalogue and other backend functionality should be tested separately from AI responses.

## API overview

The FastAPI backend exposes endpoints including:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/paypal/status` | PayPal configuration status |
| GET | `/api/dashboard` | Dashboard data |
| POST | `/api/sellers` | Register a seller |
| POST | `/api/sellers/{seller_id}/products` | Create a seller product |
| POST | `/api/admin/sellers/{seller_id}/approve` | Approve a seller |
| POST | `/api/admin/products/{product_id}/publish` | Publish a product |
| GET | `/api/products` | Browse products |
| GET | `/api/products/{product_id}` | Retrieve a product |
| GET | `/api/marketplace/categories` | Retrieve marketplace categories |
| POST | `/api/assistant` | Send a message to the assistant |
| POST | `/api/shopping-assistant` | Request catalogue-based shopping assistance |
| POST | `/api/payment-intents` | Create a payment intent |
| POST | `/api/paypal/orders` | Create a PayPal Sandbox order |
| POST | `/api/paypal/orders/{order_id}/capture` | Capture an approved Sandbox order |

See `/docs` on the running backend for request schemas, responses, and the complete API specification.

## Development checks

From the `frontend` directory:

```bash
npm ci
npm run build
npm run lint
```

From the `backend` directory, with its virtual environment activated:

```bash
python -m py_compile main.py
python -m pip check
```

These commands check frontend compilation and linting, Python syntax, and installed Python package consistency. They do not replace end-to-end testing of checkout or AI requests.

## Security and limitations

- **Sandbox only:** The current PayPal integration targets the Sandbox API. Do not treat it as live payment processing.
- **Keep credentials private:** Never commit `.env` files, API keys, PayPal secrets, or real customer information.
- **Local database:** SQLite is suitable for local prototyping; a deployed multi-user service requires an appropriate production database and operational controls.
- **Administrative access:** Configure a strong `PAYPILOT_ADMIN_TOKEN`. Administrative endpoints and authentication must be reviewed before exposing the application publicly.
- **AI reliability:** The assistant is designed to ground product claims in the supplied catalogue, but AI output should still be evaluated.
- **Production readiness:** Deployment, production payment configuration, comprehensive authorization, monitoring, and end-to-end security testing are not claimed by this local prototype.

## Contributing

Issues and pull requests are welcome. When contributing, keep secrets out of source control and test both frontend and backend changes.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
