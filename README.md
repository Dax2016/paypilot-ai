# PayPilot AI

**Your AI-powered shopping and commerce assistant.**

Discover products, get catalogue-grounded recommendations, shop through PayPal Sandbox, manage a marketplace, and explore financial learning through PayPal IQ.

PayPilot AI brings together an AI shopping assistant, a product marketplace, seller workflows, PayPal checkout, promotional resources, and an integrated financial learning experience.

> **Project status:** Local development and hackathon prototype. PayPal payments use Sandbox credentials. Live payment processing and production deployment are not configured.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Customer Journey](#customer-journey)
- [PayPal IQ](#paypal-iq)
- [Technology Stack](#technology-stack)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Configuration](#environment-configuration)
- [Run the Application](#run-the-application)
- [Testing](#testing)
- [API Reference](#api-reference)
- [Demo Workflow](#demo-workflow)
- [Security and Limitations](#security-and-limitations)
- [Roadmap](#roadmap)
- [License](#license)

## Overview

PayPilot AI aims to make online shopping more helpful by connecting product discovery, conversational AI, marketplace commerce, and payment workflows.

Customers can browse available products, search listings, ask the AI shopping assistant for recommendations, compare marketplace options, manage a cart, and complete a Sandbox checkout. They can also use PayPal IQ to explore financial learning content, complete quizzes, and track learning progress.

Independent sellers can register stores and submit product listings. Administrative workflows support seller approval and product moderation before publication.

**Product vision:** An intelligent commerce ecosystem connecting customers, merchants, payments, and AI-powered experiences.

## Features

### AI shopping assistant

- Natural-language shopping conversations.
- Product discovery based on customer requirements.
- Recommendations grounded in the available marketplace catalogue.
- Product comparisons and shopping guidance.
- Support for budget and preference-related requests.
- Clear feedback when the shopping service is unavailable.

Recommendations are based on available marketplace listings. The assistant should not be treated as a guarantee of stock, product suitability, or seller performance.

### Product marketplace

- Browse published marketplace products.
- View product details and descriptions.
- Explore product categories.
- Search products and sellers.
- View seller and listing information.
- Add available products to the cart.
- Inventory-aware quantity controls.
- Seller listing moderation and publication workflows.

### Shopping cart and checkout

- Add products to the cart.
- Increase or decrease item quantities.
- Remove cart items.
- Track cart quantity and calculate totals.
- Check available inventory when adjusting quantities.
- Initiate PayPal Sandbox checkout.
- Capture approved PayPal orders through the backend.
- Confirm marketplace payment and order status.
- Handle checkout cancellation and unsuccessful verification.
- Preserve the cart when checkout is cancelled or payment cannot be confirmed.

### Customer accounts

- Customer registration and login.
- Authenticated account information.
- Current-user retrieval.
- Logout.
- Authenticated customer API operations.

### Seller registration and dashboard

- Register a seller/store.
- Retrieve seller profile and approval status.
- View seller product listings.
- Submit product listings after seller approval.
- View draft and listing status information.

New seller applications begin in a pending state. An administrator must approve a seller before the seller can submit listings for marketplace publication.

### Administrative review

Seller workflows:
- View seller applications.
- Approve seller applications.
- Activate approved sellers.

Product workflows:
- View submitted product listings.
- Review product submissions.
- Publish eligible listings.
- Reject product submissions.

PayPal IQ content workflows:
- Create learning facts and quiz questions.
- Review learning content.
- Publish approved facts and questions.
- Update learning facts.

Administrative endpoints use the configured administrator token.

### PayPal integration

- PayPal connection-status endpoint.
- Payment intent creation.
- PayPal order creation.
- PayPal order capture.
- Marketplace checkout and payment confirmation.
- Payment and order status tracking.
- Checkout cancellation handling.

**Payment environment: PayPal Sandbox.** This project does not claim to process live PayPal transactions.

### PayPal promotional offers

- Retrieve available promotional offers.
- Display official PayPal resources.
- Track promotional offer clicks.
- Display country information where supplied.

Click tracking does not mean that an offer has been redeemed or that a discount has been applied to a payment.

### Dashboard

The dashboard presents available account and transaction information, including:
- Account balance when available.
- Money received.
- Money sent.
- Pending payments.
- Recorded transaction information.

Displayed values depend on the connected PayPal environment and the records available to the application.

## Customer Journey

```text
REGISTER / LOG IN
        |
        v
     DASHBOARD
        |
        v
    MARKETPLACE
        |
        v
 AI SHOPPING ASSISTANT
        |
        v
 CATALOGUE-GROUNDED
   RECOMMENDATIONS
        |
        v
   PRODUCT REVIEW
        |
        v
    SHOPPING CART
        |
        v
    ORDER REVIEW
        |
        v
 PAYPAL SANDBOX CHECKOUT
        |
        v
   PAYMENT CAPTURE
        |
        v
 BACKEND CONFIRMATION
        |
        v
   ORDER HISTORY
```

Seller workflow:

```text
SELLER REGISTRATION
        |
        v
PENDING APPLICATION
        |
        v
ADMINISTRATOR APPROVAL
        |
        v
PRODUCT SUBMISSION
        |
        v
PRODUCT REVIEW
        |
        v
ADMIN PUBLICATION
        |
        v
PUBLIC MARKETPLACE
```

## PayPal IQ

PayPal IQ is the financial learning experience integrated into PayPilot AI. It combines short learning content, a knowledge library, interactive quizzes, explanations, and progress tracking.

### Learning experience

- Daily financial learning fact.
- Knowledge library of published facts.
- Learning categories.
- Individual fact details.
- Beginner, intermediate, and advanced quizzes.
- Multiple-choice answer submission.
- Correctness feedback and explanations after submission.
- Customer learning progress and streak tracking.

Quiz answers and explanations are evaluated and returned through the submission workflow rather than exposed as the answer to an unanswered question.

### Points

| Activity | Points |
|---|---:|
| Daily learning exposure | 2 |
| Correct beginner answer | 10 |
| Correct intermediate answer | 15 |
| Correct advanced answer | 20 |
| Incorrect answer | 0 |

Daily exposure points are awarded once per customer per South African local calendar date. Repeated attempts at the same quiz question are restricted.

### Progress tracking

PayPal IQ progress includes:
- Total points.
- Number of quiz attempts.
- Facts viewed.
- Current learning streak.
- Longest learning streak.
- Last activity date.

### Seeded country content

The current seeded and published content includes:

| Country | Facts | Quiz questions |
|---|---:|---:|
| South Africa (ZA) | 5 | 15 |
| United States (US) | 5 | 15 |
| **Total** | **10** | **30** |

The content model supports global and country-specific publishing. The figures above describe the currently seeded content, not a claim of comprehensive country coverage.

### PayPal IQ administration

Administrators can create, review, update, and publish learning facts and quiz questions. Content creation and review are separate from publication.

## Technology Stack

### Frontend

| Technology | Role |
|---|---|
| React 19 | User interface |
| TypeScript | Application logic and type safety |
| Vite | Development server and production build |
| Lucide React | Interface icons |
| Capacitor | Android integration foundation |

### Backend

| Technology | Role |
|---|---|
| Python | Backend application |
| FastAPI | REST API |
| Uvicorn | ASGI server |
| Pydantic | Data validation |
| SQLite | Local persistence |
| HTTPX | HTTP client |
| python-dotenv | Environment configuration |
| OpenAI Python SDK | AI integration |

### External services

- PayPal REST API (Sandbox).
- OpenAI API.

## Architecture

```text
+--------------------------------------+
|             REACT CLIENT             |
|                                      |
| Dashboard | Marketplace | Orders     |
| Shopping Assistant | Cart | PayPal IQ|
| Seller Dashboard                     |
+-------------------+------------------+
                    |
                 HTTP/JSON
                    |
+-------------------v------------------+
|             FASTAPI API              |
|                                      |
| Authentication | Dashboard           |
| Shopping Assistant | Marketplace     |
| Seller Management | Orders            |
| PayPal Integration | PayPal IQ        |
| Administrative Workflows              |
+-------------+------------------------+
              |
       +------+------+
       |             |
       v             v
+-------------+  +---------------------+
|   SQLITE    |  | EXTERNAL SERVICES   |
|             |  |                     |
| Users       |  | OpenAI API          |
| Sellers     |  | PayPal REST API     |
| Products    |  | PayPal Sandbox      |
| Orders      |  |                     |
| Payments    |  +---------------------+
| Learning    |
+-------------+
```

FastAPI interactive documentation is available while the backend is running:

- Swagger UI: `http://127.0.0.1:8001/docs`
- ReDoc: `http://127.0.0.1:8001/redoc`

## Project Structure

```text
paypilot-ai/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── tests/
│   └── paypal_iq_content/
│       ├── facts.json
│       └── import_facts.py
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── App.css
│   │   ├── api.ts
│   │   ├── index.css
│   │   └── main.tsx
│   └── package.json
├── .gitignore
├── LICENSE
└── README.md
```

## Getting Started

### Prerequisites

- Python
- Node.js and npm
- Git
- PayPal Developer account with Sandbox credentials
- OpenAI API access

### 1. Clone the repository

```bash
git clone https://github.com/Dax2016/paypilot-ai.git
cd paypilot-ai
```

### 2. Install backend dependencies

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, use an appropriate execution policy for your environment or invoke the environment's Python executable directly.

### 3. Configure environment variables

Create `backend/.env` using the following template. Replace every placeholder with your own values.

```env
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=YOUR_PAYPAL_SANDBOX_CLIENT_ID
PAYPAL_CLIENT_SECRET=YOUR_PAYPAL_SANDBOX_CLIENT_SECRET

OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_MODEL=gpt-4.1-mini

PAYPILOT_ADMIN_TOKEN=YOUR_STRONG_ADMIN_TOKEN
PAYPILOT_FRONTEND_URL=http://localhost:5173
```

Use the exact variable names expected by the local application configuration. Never commit `.env` files, API keys, PayPal secrets, or administrator tokens.

### 4. Install frontend dependencies

Open another terminal at the repository root:

```powershell
cd frontend
npm ci
```

## Run the Application

### Start the backend

From `backend/`, with the virtual environment activated:

```powershell
uvicorn main:app --reload --port 8001
```

Backend base URL: `http://127.0.0.1:8001`

Health check: `http://127.0.0.1:8001/api/health`

API documentation: `http://127.0.0.1:8001/docs`

### Start the frontend

From `frontend/`:

```powershell
npm run dev
```

Open the local URL printed by Vite, normally `http://localhost:5173`.

Keep both frontend and backend processes running while using the application.

## Testing

### Backend

From the repository root:

```powershell
python -m pytest backend\tests -q
```

Or from `backend/`:

```powershell
python -m pytest tests -q
```

### Frontend production build

From `frontend/`:

```powershell
npm run build
```

### Frontend lint

```powershell
npm run lint
```

A previous verification run passed 71 backend tests and the frontend production build. Run the commands above against the current checkout to verify its latest state.

## API Reference

Base URL: `http://127.0.0.1:8001`

### Health and dashboard

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Backend root |
| GET | `/api/health` | Health check |
| GET | `/api/dashboard` | Dashboard and transaction overview |
| GET | `/api/paypal/status` | PayPal connection status |

### Customer authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/signup` | Register a customer |
| POST | `/api/auth/login` | Authenticate a customer |
| GET | `/api/auth/me` | Retrieve the authenticated customer |
| POST | `/api/auth/logout` | Log out |

### Marketplace and AI

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/products` | Retrieve marketplace products |
| GET | `/api/products/{product_id}` | Retrieve product details |
| GET | `/api/marketplace/categories` | Retrieve marketplace categories |
| POST | `/api/assistant` | AI assistant endpoint |
| POST | `/api/shopping-assistant` | AI shopping assistant |

### Sellers

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/sellers` | Register a seller |
| GET | `/api/sellers/{seller_id}` | Retrieve seller profile |
| GET | `/api/sellers/{seller_id}/products` | Retrieve seller listings |
| POST | `/api/sellers/{seller_id}/products` | Submit a product listing |

### Administrative seller and product review

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/admin/sellers` | Retrieve seller applications |
| POST | `/api/admin/sellers/{seller_id}/approve` | Approve a seller |
| GET | `/api/admin/products` | Retrieve product submissions |
| POST | `/api/admin/products/{product_id}/reject` | Reject a product |
| POST | `/api/admin/products/{product_id}/publish` | Publish a product |

### PayPal and promotional offers

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/payment-intents` | Create a payment intent |
| POST | `/api/paypal/orders` | Create a PayPal order |
| POST | `/api/paypal/orders/{order_id}/capture` | Capture a PayPal order |
| GET | `/api/paypal/offers` | Retrieve promotional offers |
| POST | `/api/paypal/promo-clicks` | Record promotional offer clicks |

### Marketplace orders

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/marketplace/orders` | Create a marketplace order |
| GET | `/api/marketplace/orders` | Retrieve marketplace orders |
| POST | `/api/marketplace/orders/{local_order_id}/cancel` | Cancel a marketplace order |
| POST | `/api/marketplace/orders/{order_id}/capture` | Capture a marketplace payment |

### PayPal IQ customer endpoints

Customer learning endpoints require customer authentication.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/paypal-iq/daily` | Retrieve daily learning content |
| GET | `/api/paypal-iq/facts` | Retrieve published learning facts |
| GET | `/api/paypal-iq/facts/{fact_id}` | Retrieve an individual fact |
| GET | `/api/paypal-iq/categories` | Retrieve learning categories |
| GET | `/api/paypal-iq/quiz` | Retrieve quiz questions |
| POST | `/api/paypal-iq/quiz/submit` | Submit quiz answers |
| GET | `/api/paypal-iq/progress` | Retrieve learning progress |

### PayPal IQ administrative endpoints

These administrative learning-content endpoints use the `X-Admin-Token` header.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/admin/paypal-iq/facts` | Create a learning fact |
| PATCH | `/api/admin/paypal-iq/facts/{fact_id}` | Update a learning fact |
| POST | `/api/admin/paypal-iq/facts/{fact_id}/review` | Review a learning fact |
| POST | `/api/admin/paypal-iq/facts/{fact_id}/publish` | Publish a learning fact |
| POST | `/api/admin/paypal-iq/questions` | Create a quiz question |
| POST | `/api/admin/paypal-iq/questions/{question_id}/review` | Review a quiz question |
| POST | `/api/admin/paypal-iq/questions/{question_id}/publish` | Publish a quiz question |

Use the running Swagger UI for request schemas, response formats, and interactive endpoint testing.

## Demo Workflow

A suggested demonstration:

1. Start the backend and frontend.
2. Register a customer account or log in.
3. Explore the dashboard.
4. Open Marketplace and browse available products.
5. Ask the AI shopping assistant for recommendations.
6. Compare available listings.
7. Add a product to the cart.
8. Review quantities and the order total.
9. Start PayPal Sandbox checkout.
10. Approve the payment using a PayPal Sandbox buyer account.
11. Return to PayPilot AI and verify the marketplace order.
12. Open Orders to review recorded purchases.
13. Open PayPal IQ and explore the daily fact and knowledge library.
14. Complete a quiz and review feedback and points.
15. Demonstrate seller registration and administrative review using test data.

## Security and Limitations

PayPilot AI is a development and hackathon prototype. It is not represented as a production-ready financial or commerce platform.

- Payments are configured for PayPal Sandbox, not live processing.
- Multi-seller payouts and automated commission settlement are not implemented.
- Seller authentication and server-side seller ownership enforcement require further development. The current seller dashboard includes a demo seller-ID workflow; seller IDs are not proof of ownership.
- Do not use the demo seller workflow to manage real seller accounts or sensitive seller data.
- SQLite is currently used for local persistence; production database infrastructure remains future work.
- Production hosting, monitoring, backups, and deployment hardening remain outstanding.
- AI recommendations are assistance, not guarantees of inventory, product availability, or suitability.
- Promotional offer click tracking does not constitute offer redemption.
- Sandbox credentials and administrator tokens must remain private.
- Customer authentication, payment authorization, and administrative access require a full production security review before public deployment.

Never commit secrets or personal payment credentials to the repository.

## Roadmap

The long-term product direction is to grow PayPilot AI through these stages. These are planned capabilities, not claims that every feature is already implemented.

### Stage 1 — Intelligent storefront

- Improve customer shopping journeys.
- Strengthen catalogue-grounded AI recommendations.
- Improve product discovery and comparisons.
- Refine checkout and order management.
- Expand PayPal IQ learning experiences.

### Stage 2 — Merchant SaaS

- Strong seller authentication.
- Server-side seller ownership and authorization.
- Merchant management tools.
- Store analytics.
- Inventory management.
- Subscription plans.

### Stage 3 — Multi-seller marketplace

- Secure multi-seller order allocation.
- Seller payout infrastructure.
- Commission management.
- Merchant onboarding improvements.
- Dispute and refund workflows.

### Stage 4 — AI commerce ecosystem

- More advanced shopping agents.
- Personalized shopping experiences.
- Intelligent merchant tools.
- Expanded financial learning.
- Broader commerce integrations.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Project

**PayPilot AI** — AI-powered shopping, marketplace commerce, PayPal integration, and financial learning.

GitHub: [Dax2016/paypilot-ai](https://github.com/Dax2016/paypilot-ai)

**Discover. Compare. Shop. Learn.**


