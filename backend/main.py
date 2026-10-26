from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import FastAPI
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException, Header

load_dotenv(Path(__file__).with_name(".env"))

PAYPAL_MODE = os.getenv("PAYPAL_MODE", "").strip().lower()
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "").strip()
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
PAYPAL_API_BASE = "https://api-m.sandbox.paypal.com"
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI


# Local transaction persistence. Keep this file out of version control.
DATABASE_PATH = Path(__file__).with_name("paypilot.db")


@contextmanager
def database_connection():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database():
    with database_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                paypal_order_id TEXT NOT NULL UNIQUE,
                paypal_capture_id TEXT UNIQUE,
                description TEXT NOT NULL,
                amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS sellers (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'ACTIVE', 'SUSPENDED')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                seller_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'General',
                price_minor INTEGER NOT NULL CHECK (price_minor > 0),
                currency TEXT NOT NULL DEFAULT 'USD',
                image_url TEXT,
                inventory_quantity INTEGER NOT NULL DEFAULT 0
                    CHECK (inventory_quantity >= 0),
                status TEXT NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (seller_id) REFERENCES sellers(id)
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_products_status_category
            ON products(status, category)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_products_seller
            ON products(seller_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_status
            ON transactions(status)
        """)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save_pending_transaction(order_id: str, description: str, amount: Decimal):
    now = utc_now()
    amount_minor = int(amount * 100)

    with database_connection() as connection:
        connection.execute("""
            INSERT INTO transactions (
                id, paypal_order_id, description, amount_minor,
                currency, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'USD', 'PENDING', ?, ?)
            ON CONFLICT(paypal_order_id) DO NOTHING
        """, (
            str(uuid4()), order_id, description, amount_minor, now, now
        ))


def complete_transaction(order_id: str, capture_id: str | None):
    now = utc_now()

    with database_connection() as connection:
        cursor = connection.execute("""
            UPDATE transactions
            SET status = 'COMPLETED',
                paypal_capture_id = COALESCE(?, paypal_capture_id),
                updated_at = ?
            WHERE paypal_order_id = ?
        """, (capture_id, now, order_id))
        return cursor.rowcount > 0


def get_transaction(order_id: str):
    with database_connection() as connection:
        row = connection.execute("""
            SELECT * FROM transactions WHERE paypal_order_id = ?
        """, (order_id,)).fetchone()
        return dict(row) if row else None


init_database()

app = FastAPI(
    title="PayPilot AI API",
    description="Backend for the PayPilot AI payment copilot.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class PaymentIntentRequest(BaseModel):
    recipient: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: Literal["USD"] = "USD"
    description: str = Field(min_length=1, max_length=250)


class SellerRegistrationRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)


class ProductCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=3000)
    category: str = Field(default="General", min_length=2, max_length=80)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: Literal["USD"] = "USD"
    image_url: str | None = Field(default=None, max_length=1000)
    inventory_quantity: int = Field(ge=0, le=100000)




@app.get("/")
def root():
    return {
        "name": "PayPilot AI API",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "service": "paypilot-ai-api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }



@app.get("/api/paypal/status")
async def paypal_status():
    """Verify Sandbox credentials without creating a payment."""
    if PAYPAL_MODE != "sandbox":
        raise HTTPException(
            status_code=503,
            detail="PayPal is not configured for Sandbox mode.",
        )

    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="PayPal Sandbox credentials are not configured.",
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{PAYPAL_API_BASE}/v1/oauth2/token",
                auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
                headers={"Accept": "application/json"},
                data={"grant_type": "client_credentials"},
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=(
                    "PayPal Sandbox authentication failed. "
                    "Check your Sandbox app credentials."
                ),
            )

        token_data = response.json()
        if not token_data.get("access_token"):
            raise HTTPException(
                status_code=502,
                detail="PayPal returned an unexpected authentication response.",
            )

        return {
            "status": "connected",
            "mode": "sandbox",
            "message": "PayPal Sandbox authentication succeeded.",
            "payment_created": False,
        }

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not reach PayPal Sandbox. Check your network and try again.",
        )

@app.get("/api/dashboard")
def dashboard():
    with database_connection() as connection:
        rows = connection.execute("""
            SELECT paypal_order_id, paypal_capture_id, description,
                   amount_minor, currency, status, created_at, updated_at
            FROM transactions
            ORDER BY created_at DESC
            LIMIT 50
        """).fetchall()

        totals = connection.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status = 'COMPLETED'
                    THEN amount_minor ELSE 0 END), 0) AS money_sent_minor,
                SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END)
                    AS pending_payments
            FROM transactions
        """).fetchone()

    transactions = []
    for row in rows:
        item = dict(row)
        item["amount"] = f"{item['amount_minor'] / 100:.2f}"
        item["direction"] = "OUTGOING"
        transactions.append(item)

    return {
        "mode": "sandbox",
        "currency": "USD",
        "balance": None,
        "money_received": "0.00",
        "money_sent": f"{totals['money_sent_minor'] / 100:.2f}",
        "pending_payments": totals["pending_payments"] or 0,
        "transactions": transactions,
        "notice": "Sandbox test transactions only. Account balance is unavailable.",
    }


class ProductResponse(BaseModel):
    id: str
    seller_id: str
    seller_name: str
    name: str
    description: str
    category: str
    price_minor: int
    price: str
    currency: str
    image_url: str | None
    inventory_quantity: int




def require_admin_token(token: str | None):
    expected = os.getenv("PAYPILOT_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin actions are disabled until PAYPILOT_ADMIN_TOKEN is configured.",
        )
    if not token or not __import__("hmac").compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token.")


@app.post("/api/sellers", status_code=201)
def register_seller(request: SellerRegistrationRequest):
    """Register a seller for review; registration never activates the account."""
    display_name = request.display_name.strip()
    email = request.email.strip().lower()

    if len(display_name) < 2 or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Enter a valid display name and email address.")

    now = utc_now()
    seller_id = str(uuid4())

    try:
        with database_connection() as connection:
            connection.execute(
                """
                INSERT INTO sellers (id, display_name, email, status, created_at, updated_at)
                VALUES (?, ?, ?, 'PENDING', ?, ?)
                """,
                (seller_id, display_name, email, now, now),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A seller with this email is already registered.")

    return {
        "id": seller_id,
        "display_name": display_name,
        "email": email,
        "status": "PENDING",
        "message": "Registration received. Seller approval is required before publishing products.",
    }


@app.post("/api/sellers/{seller_id}/products", status_code=201)
def create_seller_product(seller_id: str, request: ProductCreateRequest):
    """Create a draft product for an active seller."""
    name = request.name.strip()
    category = request.category.strip()
    description = request.description.strip()

    if len(name) < 2 or len(category) < 2:
        raise HTTPException(status_code=422, detail="Product name and category are required.")

    if request.image_url:
        from urllib.parse import urlparse
        parsed = urlparse(request.image_url)
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise HTTPException(status_code=422, detail="Image URL must be a valid HTTP or HTTPS URL.")

    price_minor = int(request.price * 100)
    if price_minor <= 0:
        raise HTTPException(status_code=422, detail="Price must be at least 0.01.")

    now = utc_now()
    product_id = str(uuid4())

    with database_connection() as connection:
        seller = connection.execute(
            "SELECT id, status FROM sellers WHERE id = ?",
            (seller_id,),
        ).fetchone()

        if seller is None:
            raise HTTPException(status_code=404, detail="Seller not found.")
        if seller["status"] != "ACTIVE":
            raise HTTPException(status_code=403, detail="Seller must be approved before creating product listings.")

        connection.execute(
            """
            INSERT INTO products (
                id, seller_id, name, description, category, price_minor,
                currency, image_url, inventory_quantity, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?)
            """,
            (
                product_id, seller_id, name, description, category, price_minor,
                request.currency, request.image_url, request.inventory_quantity, now, now,
            ),
        )

    return {
        "id": product_id,
        "seller_id": seller_id,
        "name": name,
        "price": f"{price_minor / 100:.2f}",
        "currency": request.currency,
        "inventory_quantity": request.inventory_quantity,
        "status": "DRAFT",
        "message": "Product saved as a draft. An authorized admin must publish it.",
    }


@app.post("/api/admin/sellers/{seller_id}/approve")
def approve_seller(seller_id: str, x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    """Development admin action. Pass the token in the X-Admin-Token header."""
    require_admin_token(x_admin_token)
    now = utc_now()

    with database_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE sellers SET status = 'ACTIVE', updated_at = ?
            WHERE id = ? AND status = 'PENDING'
            """,
            (now, seller_id),
        )

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Pending seller not found.")

    return {"seller_id": seller_id, "status": "ACTIVE"}


@app.post("/api/admin/products/{product_id}/publish")
def publish_product(product_id: str, x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    """Development admin action. Only products belonging to active sellers can publish."""
    require_admin_token(x_admin_token)
    now = utc_now()

    with database_connection() as connection:
        row = connection.execute(
            """
            SELECT p.id, p.inventory_quantity, s.status AS seller_status
            FROM products p JOIN sellers s ON s.id = p.seller_id
            WHERE p.id = ? AND p.status = 'DRAFT'
            """,
            (product_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Draft product not found.")
        if row["seller_status"] != "ACTIVE":
            raise HTTPException(status_code=409, detail="Seller must be active before publishing.")
        if row["inventory_quantity"] < 1:
            raise HTTPException(status_code=409, detail="Product needs at least one item in stock.")

        connection.execute(
            "UPDATE products SET status = 'ACTIVE', updated_at = ? WHERE id = ?",
            (now, product_id),
        )

    return {"product_id": product_id, "status": "ACTIVE", "message": "Product published."}


@app.get("/api/products")
def list_products(
    search: str | None = None,
    category: str | None = None,
    limit: int = 24,
    offset: int = 0,
):
    """List published products from active sellers only."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    conditions = [
        "p.status = 'ACTIVE'",
        "s.status = 'ACTIVE'",
        "p.inventory_quantity > 0",
    ]
    params: list[object] = []

    if search and search.strip():
        term = "%" + search.strip()[:100] + "%"
        conditions.append(
            "(p.name LIKE ? OR p.description LIKE ? OR p.category LIKE ?)"
        )
        params.extend([term, term, term])

    if category and category.strip():
        conditions.append("p.category = ?")
        params.append(category.strip()[:80])

    where_clause = " AND ".join(conditions)

    with database_connection() as connection:
        count_row = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM products p
            JOIN sellers s ON s.id = p.seller_id
            WHERE {where_clause}
            """,
            params,
        ).fetchone()

        rows = connection.execute(
            f"""
            SELECT
                p.id, p.seller_id, s.display_name AS seller_name,
                p.name, p.description, p.category, p.price_minor,
                p.currency, p.image_url, p.inventory_quantity
            FROM products p
            JOIN sellers s ON s.id = p.seller_id
            WHERE {where_clause}
            ORDER BY p.created_at DESC, p.id
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

    products = []
    for row in rows:
        item = dict(row)
        item["price"] = f'{item["price_minor"] / 100:.2f}'
        products.append(item)

    return {
        "products": products,
        "total": count_row["total"],
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    """Return one published product from an active seller."""
    with database_connection() as connection:
        row = connection.execute(
            """
            SELECT
                p.id, p.seller_id, s.display_name AS seller_name,
                p.name, p.description, p.category, p.price_minor,
                p.currency, p.image_url, p.inventory_quantity
            FROM products p
            JOIN sellers s ON s.id = p.seller_id
            WHERE p.id = ?
              AND p.status = 'ACTIVE'
              AND s.status = 'ACTIVE'
              AND p.inventory_quantity > 0
            """,
            (product_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")

    item = dict(row)
    item["price"] = f'{item["price_minor"] / 100:.2f}'
    return item


@app.get("/api/marketplace/categories")
def list_marketplace_categories():
    """Return categories with currently available published products."""
    with database_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT p.category
            FROM products p
            JOIN sellers s ON s.id = p.seller_id
            WHERE p.status = 'ACTIVE'
              AND s.status = 'ACTIVE'
              AND p.inventory_quantity > 0
            ORDER BY p.category COLLATE NOCASE
            """
        ).fetchall()

    return {"categories": [row["category"] for row in rows]}


@app.post("/api/assistant")
def assistant(request: AssistantRequest):
    """Answer transaction questions from persisted PayPilot records."""
    import re

    message = request.message.strip()
    if not message:
        return {
            "status": "needs_input",
            "reply": "Ask me about a purchase, payment status, order ID, or spending total.",
            "payment_created": False,
        }

    normalized = message.casefold()

    # Look for a PayPal order ID in the user's question.
    order_match = re.search(r"\b[A-Z0-9]{12,20}\b", message.upper())
    order_id = order_match.group(0) if order_match else None

    with database_connection() as connection:
        if order_id:
            rows = connection.execute(
                """
                SELECT description, amount_minor, currency, status,
                       created_at, updated_at, paypal_order_id, paypal_capture_id
                FROM transactions
                WHERE UPPER(paypal_order_id) = ?
                """,
                (order_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT description, amount_minor, currency, status,
                       created_at, updated_at, paypal_order_id, paypal_capture_id
                FROM transactions
                ORDER BY created_at DESC
                LIMIT 100
                """
            ).fetchall()

        # Aggregate by currency: never add unlike currencies together.
        currency_totals = connection.execute(
            """
            SELECT currency,
                   COUNT(*) AS transaction_count,
                   COALESCE(SUM(CASE WHEN status = 'COMPLETED'
                       THEN amount_minor ELSE 0 END), 0) AS completed_minor,
                   COALESCE(SUM(CASE WHEN status = 'PENDING'
                       THEN amount_minor ELSE 0 END), 0) AS pending_minor,
                   SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END)
                       AS completed_count,
                   SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END)
                       AS pending_count
            FROM transactions
            GROUP BY currency
            ORDER BY currency
            """
        ).fetchall()

    transactions = [dict(row) for row in rows]

    def money(row):
        return f'{row["currency"]} {row["amount_minor"] / 100:.2f}'

    def describe(row):
        return (
            f'- {row["description"]}: {money(row)}, status {row["status"]}, '
            f'order {row["paypal_order_id"]}, created {row["created_at"]}, '
            f'last updated {row["updated_at"]}.'
        )

    if order_id:
        if transactions:
            reply = "Here are the details for that order:\n" + "\n".join(
                describe(row) for row in transactions
            )
        else:
            reply = (
                f"I couldn't find order {order_id} in this PayPilot AI database. "
                "It may belong to another environment or may not have been "
                "recorded by this application."
            )
        return {
            "status": "answered_from_transactions",
            "reply": reply,
            "payment_created": False,
            "requires_confirmation": False,
            "transaction_context": {"source": "local SQLite transactions table"},
        }

    wants_pending = any(term in normalized for term in (
        "pending", "not completed", "unfinished", "still processing",
    ))
    wants_completed = any(term in normalized for term in (
        "completed", "successful", "succeeded", "successfully", "went through",
    ))
    wants_totals = any(term in normalized for term in (
        "how much", "total", "spending", "spent", "sum",
    ))
    asks_history = any(term in normalized for term in (
        "transaction", "purchase", "bought", "buy", "order", "payment",
        "paid", "iphone", "recent", "history", "memory", "remember",
        "completed", "successful", "success", "pending", "spending",
        "spent", "total", "how much", "what did i",
    ))

    if asks_history:
        filtered = transactions

        if wants_pending:
            filtered = [r for r in filtered if r["status"] == "PENDING"]
        elif wants_completed:
            filtered = [r for r in filtered if r["status"] == "COMPLETED"]

        # Match a product description when the question names one.
        known_terms = {
            "iphone", "product", "agent specialist",
        }
        for term in known_terms:
            if term in normalized:
                filtered = [
                    r for r in filtered
                    if term in (r["description"] or "").casefold()
                ]
                break

        if wants_totals:
            if not currency_totals:
                reply = "There are no transactions recorded in this PayPilot AI database."
            else:
                lines = []
                for total in currency_totals:
                    lines.append(
                        f'- {total["currency"]}: completed '
                        f'{total["completed_count"] or 0} transaction(s), '
                        f'{total["completed_minor"] / 100:.2f}; pending '
                        f'{total["pending_count"] or 0} transaction(s), '
                        f'{total["pending_minor"] / 100:.2f}.'
                    )
                reply = (
                    "Here are your recorded totals, grouped by currency "
                    "so unlike currencies are not added together:\n"
                    + "\n".join(lines)
                )
        elif not filtered:
            if wants_pending:
                reply = "I couldn't find any pending transactions in the records I checked."
            elif wants_completed:
                reply = "I couldn't find any completed transactions matching that question."
            else:
                reply = (
                    "I couldn't find a matching transaction in the records I checked. "
                    "The purchase may have another description or may not be recorded here."
                )
        else:
            title = (
                "Completed transactions"
                if wants_completed else
                "Pending transactions"
                if wants_pending else
                "Matching transaction records"
            )
            reply = title + ":\n" + "\n".join(
                describe(row) for row in filtered[:20]
            )

        return {
            "status": "answered_from_transactions",
            "reply": reply,
            "payment_created": False,
            "requires_confirmation": False,
            "transaction_context": {
                "records_loaded": len(transactions),
                "source": "local SQLite transactions table",
                "currency_totals_grouped": True,
            },
        }

    return {
        "status": "needs_clarification",
        "reply": (
            "I can look up an order, list completed or pending transactions, "
            "or summarise spending by currency. What would you like to know? "
            "I haven't created or sent a payment."
        ),
        "payment_created": False,
        "requires_confirmation": True,
    }




@app.post("/api/shopping-assistant")
def shopping_assistant(request: AssistantRequest):
    """Answer shopping questions using OpenAI and real active catalogue records."""
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Please enter a shopping question.")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="The AI shopping assistant is not configured yet.",
        )

    with database_connection() as connection:
        rows = connection.execute(
            """
            SELECT p.id, p.name, p.description, p.category, p.price_minor,
                   p.currency, p.inventory_quantity, s.display_name AS seller_name
            FROM products p
            JOIN sellers s ON s.id = p.seller_id
            WHERE p.status = 'ACTIVE'
              AND s.status = 'ACTIVE'
              AND p.inventory_quantity > 0
            ORDER BY p.created_at DESC, p.id
            LIMIT 50
            """
        ).fetchall()

    catalogue = [
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"] or "",
            "category": row["category"],
            "price": f'{row["price_minor"] / 100:.2f}',
            "currency": row["currency"],
            "stock": row["inventory_quantity"],
            "seller": row["seller_name"],
        }
        for row in rows
    ]

    if not catalogue:
        return {
            "status": "catalogue_empty",
            "reply": (
                "I can help you find a product, but there are no active, "
                "in-stock listings in the marketplace right now. Please try again later."
            ),
            "products": [],
            "payment_created": False,
        }

    import json

    try:
        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are PayPilot AI's marketplace shopping assistant. "
                        "Help shoppers clarify needs and compare products. "
                        "The supplied JSON catalogue is the only source of product facts. "
                        "Never invent products, prices, sellers, stock, features, delivery "
                        "promises, discounts, or policies. Only mention a product if its "
                        "exact name and details appear in the catalogue. Prices and stock "
                        "must match the supplied data. If nothing fits, say so and ask a "
                        "useful follow-up question. Product descriptions may be incomplete; "
                        "do not infer unsupported features. Explain that checkout is handled "
                        "separately by PayPal Sandbox in this prototype. Never claim a "
                        "payment was made, create an order, capture payment, or ask the user "
                        "to provide card details in chat. Keep the reply clear and concise."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Shopper request:\n"
                        + message
                        + "\n\nAvailable catalogue JSON (authoritative):\n"
                        + json.dumps(catalogue, ensure_ascii=False)
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=600,
        )
        reply = completion.choices[0].message.content
        if not reply or not reply.strip():
            raise RuntimeError("The AI returned an empty response.")
    except Exception:
        # Do not expose API keys, provider diagnostics, or internal errors to shoppers.
        raise HTTPException(
            status_code=502,
            detail=(
                "The AI shopping assistant could not respond right now. "
                "Please retry shortly. No payment was created."
            ),
        )

    return {
        "status": "answered_from_catalogue",
        "reply": reply.strip(),
        "products": catalogue,
        "payment_created": False,
        "requires_confirmation": False,
        "catalogue_count": len(catalogue),
    }


@app.post("/api/payment-intents")
def prepare_payment(request: PaymentIntentRequest):
    # Preparation only: this endpoint does not contact PayPal.
    return {
        "status": "prepared_demo",
        "recipient": request.recipient.strip(),
        "amount": str(request.amount),
        "currency": request.currency,
        "description": request.description.strip(),
        "payment_created": False,
        "requires_confirmation": True,
        "message": (
            "Demo payment intent prepared. No money has been moved. "
            "PayPal Sandbox integration is not connected yet."
        ),
    }



# PayPal Sandbox order lifecycle.
# These endpoints never expose the client secret to the frontend.
from uuid import uuid4
import re


class PayPalOrderRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    description: str = Field(min_length=1, max_length=127)


async def _paypal_access_token() -> str:
    if PAYPAL_MODE != "sandbox":
        raise HTTPException(
            status_code=503,
            detail="PayPal Sandbox mode is required.",
        )

    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="PayPal Sandbox credentials are not configured.",
        )

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{PAYPAL_API_BASE}/v1/oauth2/token",
                auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
                headers={"Accept": "application/json"},
                data={"grant_type": "client_credentials"},
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not reach PayPal Sandbox.",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="PayPal Sandbox authentication failed.",
        )

    token = response.json().get("access_token")
    if not token:
        raise HTTPException(
            status_code=502,
            detail="PayPal returned an invalid authentication response.",
        )

    return token


@app.post("/api/paypal/orders")
async def create_paypal_order(request: PayPalOrderRequest):
    """Create a Sandbox order; the buyer must approve it on PayPal."""
    token = await _paypal_access_token()
    amount = f"{request.amount:.2f}"
    description = request.description.strip()

    if not description:
        raise HTTPException(
            status_code=422,
            detail="Description cannot be blank.",
        )

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": str(uuid4()),
                "description": description,
                "amount": {
                    "currency_code": "USD",
                    "value": amount,
                },
            }
        ],
        "application_context": {
            "brand_name": "PayPilot AI",
            "user_action": "PAY_NOW",
            "return_url": "http://localhost:5173/?paypal=return",
            "cancel_url": "http://localhost:5173/?paypal=cancel",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{PAYPAL_API_BASE}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "PayPal-Request-Id": str(uuid4()),
                },
                json=payload,
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not create an order with PayPal Sandbox.",
        )

    if response.status_code != 201:
        raise HTTPException(
            status_code=502,
            detail="PayPal Sandbox could not create the order.",
        )

    data = response.json()
    approval_url = next(
        (
            link["href"]
            for link in data.get("links", [])
            if link.get("rel") in ("approve", "payer-action")
        ),
        None,
    )

    if not data.get("id") or not approval_url:
        raise HTTPException(
            status_code=502,
            detail="PayPal returned an incomplete order response.",
        )

    save_pending_transaction(data["id"], description, request.amount)

    return {
        "status": "created",
        "order_id": data["id"],
        "approval_url": approval_url,
        "amount": amount,
        "currency": "USD",
        "message": "Sandbox order created. Buyer approval is still required.",
        "payment_captured": False,
    }


@app.post("/api/paypal/orders/{order_id}/capture")
async def capture_paypal_order(order_id: str):
    """Capture an approved Sandbox order."""
    if not re.fullmatch(r"[A-Z0-9-]{5,50}", order_id):
        raise HTTPException(
            status_code=422,
            detail="Invalid PayPal order ID.",
        )

    local_transaction = get_transaction(order_id)
    if not local_transaction:
        raise HTTPException(
            status_code=404,
            detail="This order was not created by this PayPilot AI instance.",
        )

    if local_transaction["status"] == "COMPLETED":
        return {
            "status": "COMPLETED",
            "order_id": order_id,
            "capture_ids": (
                [local_transaction["paypal_capture_id"]]
                if local_transaction["paypal_capture_id"] else []
            ),
            "payment_captured": True,
            "message": "This Sandbox payment was already recorded as completed.",
        }

    token = await _paypal_access_token()

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "PayPal-Request-Id": str(uuid4()),
                },
                json={},
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not reach PayPal Sandbox to capture the order.",
        )

    if response.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=(
                "PayPal could not capture this order. "
                "Confirm the buyer approved it and check its status."
            ),
        )

    data = response.json()
    captures = [
        capture
        for unit in data.get("purchase_units", [])
        for capture in unit.get("payments", {}).get("captures", [])
    ]
    completed = (
        data.get("status") == "COMPLETED"
        and any(capture.get("status") == "COMPLETED" for capture in captures)
    )

    if completed:
        first_capture_id = next(
            (
                capture.get("id")
                for capture in captures
                if capture.get("status") == "COMPLETED" and capture.get("id")
            ),
            None,
        )
        complete_transaction(order_id, first_capture_id)

    return {
        "status": data.get("status", "UNKNOWN"),
        "order_id": data.get("id"),
        "capture_ids": [c["id"] for c in captures if c.get("id")],
        "payment_captured": completed,
        "message": (
            "Sandbox payment captured successfully."
            if completed
            else "Capture is not confirmed as completed. Check the order status."
        ),
    }
