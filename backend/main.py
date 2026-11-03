from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from fastapi import Request

from datetime import datetime, timezone
from hashlib import pbkdf2_hmac, sha256
import hmac
import json
import secrets
from datetime import timedelta
from zoneinfo import ZoneInfo
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
from pydantic import BaseModel, Field, field_validator
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
            CREATE TABLE IF NOT EXISTS paypal_promo_clicks (
                id TEXT PRIMARY KEY,
                resource_key TEXT NOT NULL
                    CHECK (resource_key IN ('account', 'business', 'sign_in')),
                country_code TEXT NOT NULL,
                session_id TEXT,
                clicked_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_paypal_promo_clicks_date
            ON paypal_promo_clicks(clicked_at)
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

        connection.execute("""
            CREATE TABLE IF NOT EXISTS marketplace_orders (
                id TEXT PRIMARY KEY,
                paypal_order_id TEXT NOT NULL UNIQUE,
                paypal_capture_id TEXT UNIQUE,
                amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
                currency TEXT NOT NULL DEFAULT 'USD',
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'COMPLETED', 'CANCELLED')),
                inventory_applied INTEGER NOT NULL DEFAULT 0
                    CHECK (inventory_applied IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS marketplace_order_items (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                unit_price_minor INTEGER NOT NULL CHECK (unit_price_minor > 0),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                line_total_minor INTEGER NOT NULL CHECK (line_total_minor > 0),
                FOREIGN KEY (order_id) REFERENCES marketplace_orders(id)
            )
        """)

        item_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(marketplace_order_items)"
            ).fetchall()
        }
        if "seller_id" not in item_columns:
            connection.execute(
                "ALTER TABLE marketplace_order_items ADD COLUMN seller_id TEXT"
            )

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_marketplace_order_items_seller
            ON marketplace_order_items(seller_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_marketplace_orders_status
            ON marketplace_orders(status)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_marketplace_order_items_order
            ON marketplace_order_items(order_id)
        """)


        connection.execute("""
            CREATE TABLE IF NOT EXISTS marketplace_reconciliation (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL UNIQUE,
                paypal_order_id TEXT NOT NULL,
                paypal_capture_id TEXT,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN', 'RESOLVED')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (order_id) REFERENCES marketplace_orders(id)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_marketplace_reconciliation_status
            ON marketplace_reconciliation(status)
        """)


        connection.execute("""
            CREATE TABLE IF NOT EXISTS customer_accounts (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS customer_sessions (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY (account_id) REFERENCES customer_accounts(id)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_customer_sessions_account
            ON customer_sessions(account_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_customer_sessions_expiry
            ON customer_sessions(expires_at)
        """)


        # ============================================================
        # PAYPAL IQ ? KNOWLEDGE AND LEARNING DATABASE
        # ============================================================

        connection.execute("""
            CREATE TABLE IF NOT EXISTS paypal_iq_facts (
                id TEXT PRIMARY KEY,
                fact_code TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                fact_text TEXT NOT NULL,
                explanation TEXT NOT NULL,
                category TEXT NOT NULL,
                country_scope TEXT NOT NULL
                    CHECK (country_scope IN ('GLOBAL', 'COUNTRY')),
                country_code TEXT,
                source_url TEXT NOT NULL,
                source_title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_excerpt TEXT,
                difficulty TEXT NOT NULL DEFAULT 'BEGINNER'
                    CHECK (difficulty IN ('BEGINNER', 'INTERMEDIATE', 'ADVANCED')),
                status TEXT NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT', 'REVIEW', 'PUBLISHED', 'ARCHIVED')),
                verified_at TEXT,
                review_at TEXT,
                fact_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (
                    (country_scope = 'GLOBAL' AND country_code IS NULL)
                    OR
                    (country_scope = 'COUNTRY' AND country_code IS NOT NULL)
                )
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_paypal_iq_facts_status_category
            ON paypal_iq_facts(status, category)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_paypal_iq_facts_country
            ON paypal_iq_facts(country_scope, country_code, status)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_paypal_iq_facts_review
            ON paypal_iq_facts(review_at)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS paypal_iq_questions (
                id TEXT PRIMARY KEY,
                fact_id TEXT NOT NULL,
                question TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_option TEXT NOT NULL,
                explanation TEXT NOT NULL,
                difficulty TEXT NOT NULL DEFAULT 'BEGINNER'
                    CHECK (difficulty IN ('BEGINNER', 'INTERMEDIATE', 'ADVANCED')),
                status TEXT NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (fact_id) REFERENCES paypal_iq_facts(id)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_paypal_iq_questions_fact_status
            ON paypal_iq_questions(fact_id, status)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS paypal_iq_daily_exposures (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                fact_id TEXT NOT NULL,
                exposure_date TEXT NOT NULL,
                viewed_at TEXT NOT NULL,
                UNIQUE(customer_id, exposure_date),
                FOREIGN KEY (customer_id) REFERENCES customer_accounts(id),
                FOREIGN KEY (fact_id) REFERENCES paypal_iq_facts(id)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_paypal_iq_exposures_customer
            ON paypal_iq_daily_exposures(customer_id, exposure_date)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS paypal_iq_quiz_attempts (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                attempt_date TEXT NOT NULL,
                selected_option TEXT NOT NULL,
                is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
                points_awarded INTEGER NOT NULL DEFAULT 0
                    CHECK (points_awarded >= 0),
                submitted_at TEXT NOT NULL,
                UNIQUE(customer_id, question_id, attempt_date),
                FOREIGN KEY (customer_id) REFERENCES customer_accounts(id),
                FOREIGN KEY (question_id) REFERENCES paypal_iq_questions(id)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_paypal_iq_attempts_customer
            ON paypal_iq_quiz_attempts(customer_id, submitted_at)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS paypal_iq_user_progress (
                customer_id TEXT PRIMARY KEY,
                total_points INTEGER NOT NULL DEFAULT 0
                    CHECK (total_points >= 0),
                quizzes_completed INTEGER NOT NULL DEFAULT 0
                    CHECK (quizzes_completed >= 0),
                facts_viewed INTEGER NOT NULL DEFAULT 0
                    CHECK (facts_viewed >= 0),
                current_streak INTEGER NOT NULL DEFAULT 0
                    CHECK (current_streak >= 0),
                longest_streak INTEGER NOT NULL DEFAULT 0
                    CHECK (longest_streak >= 0),
                last_activity_date TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customer_accounts(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS paypal_iq_question_reviews (
                id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL,
                reviewer_id TEXT NOT NULL,
                review_status TEXT NOT NULL
                    CHECK (review_status IN ('APPROVED', 'REJECTED')),
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (question_id)
                    REFERENCES paypal_iq_questions(id)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_paypal_iq_question_reviews_latest
            ON paypal_iq_question_reviews(question_id, created_at)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS paypal_iq_fact_reviews (
                id TEXT PRIMARY KEY,
                fact_id TEXT NOT NULL,
                reviewer_id TEXT,
                review_status TEXT NOT NULL
                    CHECK (review_status IN ('APPROVED', 'REJECTED', 'NEEDS_UPDATE')),
                notes TEXT,
                source_checked_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (fact_id) REFERENCES paypal_iq_facts(id),
                FOREIGN KEY (reviewer_id) REFERENCES customer_accounts(id)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_paypal_iq_reviews_fact
            ON paypal_iq_fact_reviews(fact_id, created_at)
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


from paypal_offers import PayPalOffer, list_offers


# No live promotion feed has been configured yet. Keep this empty until
# offers can be verified against an authoritative source.
PAYPAL_OFFERS: list[PayPalOffer] = []


@app.get("/api/paypal/offers")
def paypal_offers_endpoint(country_code: str = "ZA"):
    """Return country-eligible offers without inventing promotions."""
    try:
        offers = list_offers(PAYPAL_OFFERS, country_code)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    normalized_country = country_code.strip().upper()
    if normalized_country == "ZA":
        official_links = {
            "account": "https://www.paypal.com/za/webapps/mpp/account-selection",
            "business": "https://www.paypal.com/za/business/open-business-account",
            "sign_in": "https://www.paypal.com/signin",
        }
    else:
        official_links = {
            "account": "https://www.paypal.com/",
            "business": "https://www.paypal.com/",
            "sign_in": "https://www.paypal.com/signin",
        }

    verified_offers = [
        offer for offer in offers
        if offer.status == "verified_active"
    ]
    offers_to_check = [
        offer for offer in offers
        if offer.status == "check_official_page"
    ]

    if verified_offers:
        status = "offers_available"
        message = "Verified offers are listed below. Check each offer's eligibility and terms."
    elif offers_to_check:
        status = "offers_require_verification"
        message = (
            "No verified offers are available for this country. "
            "Some offer records require checking on the official PayPal page; "
            "they are not confirmed active promotions."
        )
    else:
        status = "no_verified_offers"
        message = (
            "PayPilot AI has no verified offers for this country right now. "
            "Check PayPal's official website for current promotions and eligibility."
        )

    return {
        "country_code": normalized_country,
        "status": status,
        "message": message,
        "offers": [offer.model_dump(mode="json") for offer in offers],
        "count": len(offers),
        "verified_count": len(verified_offers),
        "unverified_count": len(offers_to_check),
        "live_feed_configured": False,
        "official_links": official_links,
    }


def build_paypal_offer_context(country_code: str = "ZA") -> dict:
    """Build safe, country-aware context for confirmed offers and official links."""
    normalized_country = country_code.strip().upper()
    try:
        eligible_offers = list_offers(PAYPAL_OFFERS, normalized_country)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    verified_offers = [
        offer.model_dump(mode="json")
        for offer in eligible_offers
        if offer.status == "verified_active"
    ]
    offers_to_check = [
        offer.model_dump(mode="json")
        for offer in eligible_offers
        if offer.status == "check_official_page"
    ]

    endpoint_data = paypal_offers_endpoint(normalized_country)

    return {
        "country_code": normalized_country,
        "verified_offers": verified_offers,
        "offers_to_check": offers_to_check,
        "count": len(verified_offers),
        "message": (
            "Only verified_offers may be described as confirmed promotions. "
            "offers_to_check are unconfirmed and must never be presented as active discounts."
            if verified_offers or offers_to_check
            else "No offers are configured for this country. Do not claim a promotion exists; direct the shopper to the official PayPal links."
        ),
        "official_links": endpoint_data["official_links"],
    }


PAYPILOT_FRONTEND_URL = os.getenv(
    "PAYPILOT_FRONTEND_URL",
    "http://localhost:5173",
).rstrip("/")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "PAYPILOT_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Token", "Authorization"],
)


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    country_code: str = Field(default="ZA", min_length=2, max_length=2)

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalpha() or len(normalized) != 2:
            raise ValueError("country_code must be a two-letter country code.")
        return normalized


class PayPalPromoClickRequest(BaseModel):
    resource_key: Literal["account", "business", "sign_in"]
    country_code: str = Field(default="ZA", min_length=2, max_length=2)
    session_id: str | None = Field(default=None, max_length=80)

    @field_validator("country_code")
    @classmethod
    def validate_promo_country_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalpha() or len(normalized) != 2:
            raise ValueError("country_code must be a two-letter country code.")
        return normalized


@app.post("/api/paypal/promo-clicks", status_code=201)
def record_paypal_promo_click(request: PayPalPromoClickRequest):
    """Record an interaction with an approved official PayPal resource."""
    session_id = request.session_id.strip() if request.session_id else None

    with database_connection() as connection:
        connection.execute(
            """
            INSERT INTO paypal_promo_clicks (
                id, resource_key, country_code, session_id, clicked_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                secrets.token_hex(16),
                request.resource_key,
                request.country_code,
                session_id or None,
                utc_now(),
            ),
        )

    return {"status": "recorded", "resource_key": request.resource_key}


class PayPalIQFactCreateRequest(BaseModel):
    fact_code: str = Field(min_length=3, max_length=80)
    title: str = Field(min_length=5, max_length=180)
    fact_text: str = Field(min_length=10, max_length=2000)
    explanation: str = Field(min_length=10, max_length=3000)
    category: str = Field(min_length=2, max_length=80)
    country_scope: Literal["GLOBAL", "COUNTRY"]
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    source_url: str = Field(min_length=10, max_length=1000)
    source_title: str = Field(min_length=3, max_length=250)
    source_type: str = Field(min_length=2, max_length=50)
    source_excerpt: str | None = Field(default=None, max_length=2000)
    difficulty: Literal["BEGINNER", "INTERMEDIATE", "ADVANCED"] = "BEGINNER"
    review_at: str | None = None

    @field_validator("fact_code")
    @classmethod
    def normalize_fact_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.replace("-", "").replace("_", "").isalnum():
            raise ValueError("fact_code may contain only letters, numbers, hyphens and underscores.")
        return normalized

    @field_validator("country_code")
    @classmethod
    def normalize_fact_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("country_code must be a two-letter country code.")
        return normalized

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("https://"):
            raise ValueError("PayPal IQ sources must use HTTPS.")
        return normalized

    @field_validator("category", "source_title", "source_type")
    @classmethod
    def trim_fact_metadata(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field cannot be blank.")
        return normalized


class PayPalIQQuestionCreateRequest(BaseModel):
    fact_id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=10, max_length=1000)
    options: list[str] = Field(min_length=2, max_length=6)
    correct_option: str = Field(min_length=1, max_length=10)
    explanation: str = Field(min_length=10, max_length=2000)
    difficulty: Literal["BEGINNER", "INTERMEDIATE", "ADVANCED"] = "BEGINNER"

    @field_validator("options")
    @classmethod
    def validate_question_options(cls, value: list[str]) -> list[str]:
        normalized = [option.strip() for option in value]
        if any(not option for option in normalized):
            raise ValueError("Quiz options cannot be blank.")
        if len({option.casefold() for option in normalized}) != len(normalized):
            raise ValueError("Quiz options must be unique.")
        if any(len(option) > 300 for option in normalized):
            raise ValueError("Each quiz option must be 300 characters or fewer.")
        return normalized

    @field_validator("correct_option")
    @classmethod
    def normalize_correct_option(cls, value: str) -> str:
        return value.strip().upper()


class PayPalIQQuizSubmitRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=80)
    selected_option: str = Field(min_length=1, max_length=10)

    @field_validator("selected_option")
    @classmethod
    def normalize_selected_option(cls, value: str) -> str:
        return value.strip().upper()

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



@app.post("/api/admin/paypal-iq/facts", status_code=201)
def create_paypal_iq_fact(
    request: PayPalIQFactCreateRequest,
    admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Create an unpublished PayPal IQ fact for administrator review."""
    require_admin_token(admin_token)

    if request.country_scope == "GLOBAL" and request.country_code is not None:
        raise HTTPException(
            status_code=422,
            detail="Global facts must not specify a country_code.",
        )

    if request.country_scope == "COUNTRY" and not request.country_code:
        raise HTTPException(
            status_code=422,
            detail="Country-specific facts require a country_code.",
        )

    from urllib.parse import urlparse

    parsed_source = urlparse(request.source_url)
    if (
        parsed_source.scheme != "https"
        or not parsed_source.netloc
        or not parsed_source.hostname
    ):
        raise HTTPException(
            status_code=422,
            detail="A valid HTTPS source URL is required.",
        )

    fact_id = secrets.token_hex(16)
    now = utc_now()

    try:
        with database_connection() as connection:
            connection.execute(
                """
                INSERT INTO paypal_iq_facts (
                    id, fact_code, title, fact_text, explanation,
                    category, country_scope, country_code,
                    source_url, source_title, source_type, source_excerpt,
                    difficulty, status, verified_at, review_at,
                    fact_version, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT',
                        NULL, NULL, 1, ?, ?)
                """,
                (
                    fact_id,
                    request.fact_code,
                    request.title.strip(),
                    request.fact_text.strip(),
                    request.explanation.strip(),
                    request.category.strip(),
                    request.country_scope,
                    request.country_code,
                    request.source_url,
                    request.source_title.strip(),
                    request.source_type.strip(),
                    request.source_excerpt.strip()
                    if request.source_excerpt else None,
                    request.difficulty,
                    now,
                    now,
                ),
            )
    except sqlite3.IntegrityError as exc:
        if "fact_code" in str(exc).lower() or "unique" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail="A fact with this fact_code already exists.",
            ) from exc
        raise

    return {
        "status": "created",
        "fact_id": fact_id,
        "fact_code": request.fact_code,
        "fact_status": "DRAFT",
        "message": "Fact created and awaiting source review.",
    }

class PayPalIQFactReviewRequest(BaseModel):
    review_status: Literal["APPROVED", "REJECTED", "NEEDS_UPDATE"]
    notes: str | None = Field(default=None, max_length=2000)
    review_at: str | None = None


@app.post("/api/admin/paypal-iq/facts/{fact_id}/review")
def review_paypal_iq_fact(
    fact_id: str,
    request: PayPalIQFactReviewRequest,
    admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Record an administrator's source review without publishing the fact."""
    require_admin_token(admin_token)

    now = utc_now()

    with database_connection() as connection:
        fact = connection.execute(
            "SELECT id, status FROM paypal_iq_facts WHERE id = ?",
            (fact_id,),
        ).fetchone()

        if fact is None:
            raise HTTPException(status_code=404, detail="PayPal IQ fact not found.")

        if fact["status"] in ("PUBLISHED", "ARCHIVED"):
            raise HTTPException(
                status_code=409,
                detail="Published or archived facts cannot be reviewed through this endpoint.",
            )

        review_id = secrets.token_hex(16)

        connection.execute(
            """
            INSERT INTO paypal_iq_fact_reviews (
                id, fact_id, reviewer_id, review_status,
                notes, source_checked_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                fact_id,
                "admin",
                request.review_status,
                request.notes.strip() if request.notes else None,
                now,
                now,
            ),
        )

        if request.review_status == "APPROVED":
            review_at = request.review_at or (
                datetime.now(timezone.utc) + timedelta(days=90)
            ).isoformat()

            connection.execute(
                """
                UPDATE paypal_iq_facts
                SET status = 'REVIEW',
                    verified_at = ?,
                    review_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, review_at, now, fact_id),
            )
        else:
            connection.execute(
                """
                UPDATE paypal_iq_facts
                SET status = 'DRAFT',
                    verified_at = NULL,
                    review_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, fact_id),
            )

    return {
        "status": "review_recorded",
        "fact_id": fact_id,
        "review_id": review_id,
        "review_status": request.review_status,
        "fact_status": "REVIEW" if request.review_status == "APPROVED" else "DRAFT",
        "message": (
            "Fact approved for publishing review."
            if request.review_status == "APPROVED"
            else "Fact remains unpublished and requires attention."
        ),
    }

@app.post("/api/admin/paypal-iq/facts/{fact_id}/publish")
def publish_paypal_iq_fact(
    fact_id: str,
    admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Publish a fact only after an explicit approved source review."""
    require_admin_token(admin_token)

    from urllib.parse import urlparse

    with database_connection() as connection:
        fact = connection.execute(
            """
            SELECT id, status, source_url, source_title, source_type,
                   verified_at, review_at
            FROM paypal_iq_facts
            WHERE id = ?
            """,
            (fact_id,),
        ).fetchone()

        if fact is None:
            raise HTTPException(status_code=404, detail="PayPal IQ fact not found.")

        if fact["status"] != "REVIEW":
            raise HTTPException(
                status_code=409,
                detail="Only facts in REVIEW status can be published.",
            )

        latest_review = connection.execute(
            """
            SELECT review_status
            FROM paypal_iq_fact_reviews
            WHERE fact_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (fact_id,),
        ).fetchone()

        if latest_review is None or latest_review["review_status"] != "APPROVED":
            raise HTTPException(
                status_code=409,
                detail="The latest fact review must be APPROVED before publishing.",
            )

        if not fact["verified_at"] or not fact["review_at"]:
            raise HTTPException(
                status_code=409,
                detail="The fact must have verification and review dates.",
            )

        parsed_source = urlparse(fact["source_url"] or "")
        if (
            parsed_source.scheme != "https"
            or not parsed_source.netloc
            or not parsed_source.hostname
            or not fact["source_title"]
            or not fact["source_type"]
        ):
            raise HTTPException(
                status_code=422,
                detail="The fact must have complete, valid HTTPS source metadata.",
            )

        now = utc_now()
        connection.execute(
            """
            UPDATE paypal_iq_facts
            SET status = 'PUBLISHED',
                updated_at = ?
            WHERE id = ?
            """,
            (now, fact_id),
        )

    return {
        "status": "published",
        "fact_id": fact_id,
        "fact_status": "PUBLISHED",
        "message": "Fact published and eligible for customer-facing PayPal IQ experiences.",
    }

@app.post("/api/admin/paypal-iq/questions", status_code=201)
def create_paypal_iq_question(
    request: PayPalIQQuestionCreateRequest,
    admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Create an unpublished quiz question for a published PayPal IQ fact."""
    require_admin_token(admin_token)

    if len(request.options) < 2 or len(request.options) > 6:
        raise HTTPException(
            status_code=422,
            detail="Quiz questions require between 2 and 6 answer options.",
        )

    valid_labels = [
        chr(65 + index) for index in range(len(request.options))
    ]

    if request.correct_option not in valid_labels:
        raise HTTPException(
            status_code=422,
            detail=(
                "correct_option must match an available option label: "
                + ", ".join(valid_labels)
            ),
        )

    now = utc_now()
    question_id = secrets.token_hex(16)

    with database_connection() as connection:
        fact = connection.execute(
            """
            SELECT id, status
            FROM paypal_iq_facts
            WHERE id = ?
            """,
            (request.fact_id,),
        ).fetchone()

        if fact is None:
            raise HTTPException(
                status_code=404,
                detail="PayPal IQ fact not found.",
            )

        if fact["status"] != "PUBLISHED":
            raise HTTPException(
                status_code=409,
                detail="Quiz questions can only be created for published facts.",
            )

        connection.execute(
            """
            INSERT INTO paypal_iq_questions (
                id, fact_id, question, options_json,
                correct_option, explanation, difficulty,
                status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?)
            """,
            (
                question_id,
                request.fact_id,
                request.question.strip(),
                json.dumps(request.options),
                request.correct_option,
                request.explanation.strip(),
                request.difficulty,
                now,
                now,
            ),
        )

    return {
        "status": "created",
        "question_id": question_id,
        "fact_id": request.fact_id,
        "question_status": "DRAFT",
        "message": "Quiz question created and awaiting review.",
    }

class PayPalIQQuestionReviewRequest(BaseModel):
    review_status: Literal["APPROVED", "REJECTED"]
    notes: str | None = Field(default=None, max_length=2000)


@app.post("/api/admin/paypal-iq/questions/{question_id}/review")
def review_paypal_iq_question(
    question_id: str,
    request: PayPalIQQuestionReviewRequest,
    admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Record an approval or rejection without changing the question status."""
    require_admin_token(admin_token)

    now = utc_now()

    with database_connection() as connection:
        question = connection.execute(
            """
            SELECT q.id, q.status, f.status AS fact_status
            FROM paypal_iq_questions q
            JOIN paypal_iq_facts f ON f.id = q.fact_id
            WHERE q.id = ?
            """,
            (question_id,),
        ).fetchone()

        if question is None:
            raise HTTPException(
                status_code=404,
                detail="PayPal IQ question not found.",
            )

        if question["status"] == "PUBLISHED":
            raise HTTPException(
                status_code=409,
                detail="Published questions cannot be reviewed through this endpoint.",
            )

        if question["fact_status"] != "PUBLISHED":
            raise HTTPException(
                status_code=409,
                detail="The question's associated fact must be published first.",
            )

        connection.execute(
            """
            INSERT INTO paypal_iq_question_reviews (
                id, question_id, reviewer_id, review_status, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                secrets.token_hex(16),
                question_id,
                "admin",
                request.review_status,
                request.notes,
                now,
            ),
        )

    return {
        "status": "review_recorded",
        "question_id": question_id,
        "review_status": request.review_status,
        "question_status": "DRAFT",
        "message": (
            "Question approved and is ready for the publishing step."
            if request.review_status == "APPROVED"
            else "Question rejected and remains a draft."
        ),
    }


@app.post("/api/admin/paypal-iq/questions/{question_id}/publish")
def publish_paypal_iq_question(
    question_id: str,
    admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Publish a question only after its latest review approves it."""
    require_admin_token(admin_token)

    now = utc_now()

    with database_connection() as connection:
        question = connection.execute(
            """
            SELECT q.id, q.status, f.status AS fact_status
            FROM paypal_iq_questions q
            JOIN paypal_iq_facts f ON f.id = q.fact_id
            WHERE q.id = ?
            """,
            (question_id,),
        ).fetchone()

        if question is None:
            raise HTTPException(
                status_code=404,
                detail="PayPal IQ question not found.",
            )

        if question["status"] == "PUBLISHED":
            raise HTTPException(
                status_code=409,
                detail="This question is already published.",
            )

        if question["status"] != "DRAFT":
            raise HTTPException(
                status_code=409,
                detail="Only draft questions can be published.",
            )

        if question["fact_status"] != "PUBLISHED":
            raise HTTPException(
                status_code=409,
                detail="The question's associated fact must be published first.",
            )

        latest_review = connection.execute(
            """
            SELECT review_status
            FROM paypal_iq_question_reviews
            WHERE question_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (question_id,),
        ).fetchone()

        if latest_review is None or latest_review["review_status"] != "APPROVED":
            raise HTTPException(
                status_code=409,
                detail="The latest question review must be APPROVED before publishing.",
            )

        connection.execute(
            """
            UPDATE paypal_iq_questions
            SET status = 'PUBLISHED', updated_at = ?
            WHERE id = ? AND status = 'DRAFT'
            """,
            (now, question_id),
        )

    return {
        "status": "published",
        "question_id": question_id,
        "question_status": "PUBLISHED",
        "message": "PayPal IQ question published successfully.",
    }


class CustomerSignupRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)


class CustomerLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def _customer_password_hash(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    derived = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
    return derived.hex()



def _create_customer_session(account_id: str, connection=None) -> dict:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=24)

    def insert_session(db_connection):
        db_connection.execute(
            """
            INSERT INTO customer_sessions
                (id, account_id, token_hash, created_at, expires_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (
                secrets.token_hex(16),
                account_id,
                sha256(token.encode("utf-8")).hexdigest(),
                now.isoformat(),
                expires.isoformat(),
            ),
        )

    if connection is None:
        with database_connection() as db_connection:
            insert_session(db_connection)
    else:
        insert_session(connection)

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires.isoformat(),
    }



def _get_authenticated_customer(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")

    token = authorization[7:].strip()
    if not token or len(token) > 512:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    token_hash = sha256(token.encode("utf-8")).hexdigest()
    with database_connection() as connection:
        row = connection.execute(
            """
            SELECT a.id, a.email, a.created_at, s.expires_at
            FROM customer_sessions s
            JOIN customer_accounts a ON a.id = s.account_id
            WHERE s.token_hash = ? AND s.revoked_at IS NULL
            """,
            (token_hash,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    if expires <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    return {
        "id": row["id"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


@app.post("/api/auth/signup", status_code=201)
def customer_signup(request: CustomerSignupRequest):
    email = request.email.strip().lower()
    if (
        "@" not in email
        or email.startswith("@")
        or "." not in email.rsplit("@", 1)[-1]
        or any(character.isspace() for character in email)
    ):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")

    salt_hex = secrets.token_hex(16)
    password_hash = _customer_password_hash(request.password, salt_hex)
    account_id = secrets.token_hex(16)
    now = utc_now()

    try:
        with database_connection() as connection:
            connection.execute(
                """
                INSERT INTO customer_accounts
                    (id, email, password_salt, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (account_id, email, salt_hex, password_hash, now, now),
            )
            session = _create_customer_session(account_id, connection)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="An account with that email already exists.",
        )
    return {
        **session,
        "account": {"id": account_id, "email": email, "created_at": now},
    }


# Development-stage login rate limiter.
# Production should use shared storage or an API gateway.
LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW_SECONDS = 60
MAX_TRACKED_LOGIN_IPS = 10_000

_login_attempts = defaultdict(deque)
_login_attempts_lock = Lock()


def check_login_rate_limit(client_ip: str) -> tuple[bool, int]:
    """Apply a bounded, in-memory sliding-window login rate limit."""
    now = monotonic()

    with _login_attempts_lock:
        # Remove expired attempts and empty IP entries.
        expired_ips = []

        for ip, attempts in _login_attempts.items():
            while (
                attempts
                and now - attempts[0] >= LOGIN_RATE_WINDOW_SECONDS
            ):
                attempts.popleft()

            if not attempts:
                expired_ips.append(ip)

        for ip in expired_ips:
            del _login_attempts[ip]

        attempts = _login_attempts.get(client_ip)

        # Fail closed if the tracking capacity is exhausted.
        if attempts is None:
            if len(_login_attempts) >= MAX_TRACKED_LOGIN_IPS:
                return False, LOGIN_RATE_WINDOW_SECONDS

            attempts = deque()
            _login_attempts[client_ip] = attempts

        if len(attempts) >= LOGIN_RATE_LIMIT:
            retry_after = max(
                1,
                int(
                    LOGIN_RATE_WINDOW_SECONDS
                    - (now - attempts[0])
                    + 0.999
                ),
            )
            return False, retry_after

        attempts.append(now)
        return True, 0
@app.post("/api/auth/login")
def customer_login(
    request: CustomerLoginRequest,
    http_request: Request,
):
    client_ip = (
        http_request.client.host
        if http_request.client is not None
        else "unknown"
    )

    allowed, retry_after = check_login_rate_limit(client_ip)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    email = request.email.strip().lower()

    with database_connection() as connection:
        account = connection.execute(
            """
            SELECT id, email, password_salt, password_hash, created_at
            FROM customer_accounts
            WHERE email = ?
            """,
            (email,),
        ).fetchone()

    # Use the same public error for unknown emails and incorrect passwords.
    if not account:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    candidate_hash = _customer_password_hash(
        request.password, account["password_salt"]
    )
    if not hmac.compare_digest(candidate_hash, account["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    session = _create_customer_session(account["id"])
    return {
        **session,
        "account": {
            "id": account["id"],
            "email": account["email"],
            "created_at": account["created_at"],
        },
    }


@app.get("/api/auth/me")
def customer_me(authorization: str | None = Header(default=None, alias="Authorization")):
    account = _get_authenticated_customer(authorization)
    return {"authenticated": True, "account": account}


@app.post("/api/auth/logout")
def customer_logout(authorization: str | None = Header(default=None, alias="Authorization")):
    # Logout is idempotent for missing, invalid, or already revoked sessions.
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token and len(token) <= 512:
            token_hash = sha256(token.encode("utf-8")).hexdigest()
            with database_connection() as connection:
                connection.execute(
                    """
                    UPDATE customer_sessions
                    SET revoked_at = ?
                    WHERE token_hash = ? AND revoked_at IS NULL
                    """,
                    (utc_now(), token_hash),
                )
    return {"status": "logged_out"}


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



@app.get("/api/sellers/{seller_id}")
def get_seller(seller_id: str):
    """Return seller profile and approval status for the local demo."""
    with database_connection() as connection:
        seller = connection.execute(
            """
            SELECT id, display_name, email, status, created_at, updated_at
            FROM sellers
            WHERE id = ?
            """,
            (seller_id,),
        ).fetchone()

    if seller is None:
        raise HTTPException(status_code=404, detail="Seller not found.")

    return dict(seller)


@app.get("/api/sellers/{seller_id}/products")
def get_seller_products(seller_id: str, limit: int = 100):
    """List products belonging to a seller, including drafts and archived items."""
    limit = max(1, min(limit, 100))

    with database_connection() as connection:
        seller = connection.execute(
            "SELECT id FROM sellers WHERE id = ?",
            (seller_id,),
        ).fetchone()

        if seller is None:
            raise HTTPException(status_code=404, detail="Seller not found.")

        rows = connection.execute(
            """
            SELECT id, seller_id, name, description, category, price_minor,
                   currency, image_url, inventory_quantity, status,
                   created_at, updated_at
            FROM products
            WHERE seller_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (seller_id, limit),
        ).fetchall()

    items = []
    for row in rows:
        item = dict(row)
        item["price"] = f"{item['price_minor'] / 100:.2f}"
        items.append(item)

    return {"seller_id": seller_id, "products": items, "total": len(items)}


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


@app.get("/api/admin/sellers")
def list_admin_sellers(
    status: str = "PENDING",
    limit: int = 100,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """List seller applications for authorized admin review."""
    require_admin_token(x_admin_token)

    status = status.strip().upper()
    if status not in ("PENDING", "ACTIVE", "SUSPENDED", "ALL"):
        raise HTTPException(
            status_code=422,
            detail="Status must be PENDING, ACTIVE, SUSPENDED, or ALL.",
        )

    limit = max(1, min(limit, 100))

    with database_connection() as connection:
        if status == "ALL":
            rows = connection.execute(
                """
                SELECT id, display_name, email, status, created_at, updated_at
                FROM sellers
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, display_name, email, status, created_at, updated_at
                FROM sellers
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()

    sellers = [dict(row) for row in rows]
    return {"sellers": sellers, "total": len(sellers), "status": status}


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


@app.get("/api/admin/products")
def list_admin_products(
    status: str = "DRAFT",
    limit: int = 100,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """List product submissions for authorized admin review."""
    require_admin_token(x_admin_token)

    if status not in {"DRAFT", "ACTIVE", "ARCHIVED"}:
        raise HTTPException(status_code=400, detail="Unsupported product status.")

    limit = max(1, min(limit, 100))

    with database_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                p.id, p.seller_id, p.name, p.description, p.category,
                p.price_minor, p.currency, p.image_url, p.inventory_quantity,
                p.status, p.created_at, s.display_name AS seller_name,
                s.email AS seller_email, s.status AS seller_status
            FROM products p
            JOIN sellers s ON s.id = p.seller_id
            WHERE p.status = ?
            ORDER BY p.created_at DESC
            LIMIT ?
            """,
            (status, limit),
        ).fetchall()

    return {
        "products": [
            {
                "id": row["id"],
                "seller_id": row["seller_id"],
                "seller_name": row["seller_name"],
                "seller_email": row["seller_email"],
                "seller_status": row["seller_status"],
                "name": row["name"],
                "description": row["description"],
                "category": row["category"],
                "price_minor": row["price_minor"],
                "price": f"{row['price_minor'] / 100:.2f}",
                "currency": row["currency"],
                "image_url": row["image_url"],
                "inventory_quantity": row["inventory_quantity"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ],
        "total": len(rows),
        "status": status,
    }


@app.post("/api/admin/products/{product_id}/reject")
def reject_product(
    product_id: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Archive a draft product that should not be published."""
    require_admin_token(x_admin_token)
    now = utc_now()

    with database_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE products
            SET status = 'ARCHIVED', updated_at = ?
            WHERE id = ? AND status = 'DRAFT'
            """,
            (now, product_id),
        )

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Draft product not found.")

    return {
        "product_id": product_id,
        "status": "ARCHIVED",
        "message": "Product submission rejected and archived.",
    }


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


def _build_semantic_response(
    intent: str,
    answer: str,
    *,
    key_points: list | None = None,
    evidence: list | None = None,
    recommendations: list | None = None,
    next_action: str | None = None,
) -> dict:
    """Create a consistent, machine-readable assistant response."""
    return {
        "intent": intent,
        "answer": answer,
        "key_points": key_points or [],
        "evidence": evidence or [],
        "recommendations": recommendations or [],
        "next_action": next_action,
    }


@app.post("/api/assistant")
def assistant(request: AssistantRequest):
    """Answer transaction questions from persisted PayPilot records."""
    import re

    message = request.message.strip()
    if not message:
        return {
            "status": "needs_input",
            "reply": "Ask me about a purchase, payment status, order ID, or spending total.",
            "semantic_response": _build_semantic_response(
                "needs_input",
                "Ask me about a purchase, payment status, order ID, or spending total.",
                next_action="Enter a transaction question.",
            ),
            "payment_created": False,
        }

    normalized = message.casefold()

    # Look for a PayPal order ID in the user's question.
    order_match = re.fullmatch(r"\s*([A-Z0-9]{12,20})\s*", message.upper())
    if not order_match:
        order_match = re.search(
            r"\b(?:paypal\s+)?order(?:\s+(?:id|number))?\s*[:#-]?\s*([A-Z0-9]{12,20})\b",
            message,
            re.IGNORECASE,
        )
    order_id = order_match.group(1) if order_match else None

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
            "semantic_response": _build_semantic_response(
                "transaction_lookup",
                reply,
                key_points=[f"Matching order records: {len(transactions)}"],
                evidence=[{
                    "source": "local SQLite transactions table",
                    "record_count": len(transactions),
                    "order_id": order_id,
                }],
                next_action=None if transactions else "Verify the order ID and environment.",
            ),
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
            "semantic_response": _build_semantic_response(
                "transaction_summary",
                reply,
                key_points=[
                    f"Transaction records examined: {len(transactions)}",
                    "Totals are grouped by currency where applicable.",
                ],
                evidence=[{
                    "source": "local SQLite transactions table",
                    "record_count": len(transactions),
                    "currency_totals_grouped": True,
                }],
            ),
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
        "semantic_response": _build_semantic_response(
            "needs_clarification",
            "I can look up an order, list completed or pending transactions, or summarise spending by currency. What would you like to know? I haven't created or sent a payment.",
            next_action="Ask about an order, transaction status, or spending total.",
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

    offer_context = build_paypal_offer_context(request.country_code)

    if not catalogue:
        return {
            "status": "catalogue_empty",
            "reply": (
                "I can help you find a product, but there are no active, "
                "in-stock listings in the marketplace right now. Please try again later."
            ),
            "semantic_response": _build_semantic_response(
                "product_discovery",
                "I can help you find a product, but there are no active, in-stock listings in the marketplace right now. Please try again later.",
                evidence=[{
                    "source": "active marketplace catalogue",
                    "available_product_count": 0,
                }],
                next_action="Try again later or check the marketplace catalogue.",
            ),
            "products": [],
            "recommended_product_ids": [],
            "country_code": offer_context["country_code"],
            "paypal_offer_context": offer_context,
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
                        "do not infer unsupported features. "
                        "Use the supplied PayPal offer context as the only source for "
                        "PayPal promotions. Describe an offer as a confirmed promotion only "
                        "when it appears in verified_offers with status verified_active. "
                        "Offers in offers_to_check are unconfirmed: do not describe them as "
                        "active discounts or promise eligibility. Never invent an offer, "
                        "discount amount, expiry date, or eligibility rule. Do not claim a "
                        "discount is automatically applied. If no verified offer is available, "
                        "say that PayPilot AI has no verified offer for the shopper's country "
                        "and provide relevant official PayPal links from the context. "
                        "Explain that checkout is handled separately by PayPal Sandbox in "
                        "this prototype. Never claim a payment was made, create an order, "
                        "capture payment, or ask the user to provide card details in chat. "
                        "Return a JSON object with exactly two fields: "
                        '"reply" and "recommended_product_ids". '
                        '"reply" must contain the concise, shopper-friendly answer. '
                        '"recommended_product_ids" must be an array containing at most '
                        "four product IDs selected only from the supplied authoritative "
                        "catalogue. Recommend only products relevant to the shopper request. "
                        "Use an empty array when no product is a suitable match. "
                        "Never invent or modify product IDs. Do not include Markdown fences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Shopper country: "
                        + request.country_code
                        + "\n\nShopper request:\n"
                        + message
                        + "\n\nAvailable catalogue JSON (authoritative):\n"
                        + json.dumps(catalogue, ensure_ascii=False)
                        + "\n\nPayPal offer context (authoritative):\n"
                        + json.dumps(offer_context, ensure_ascii=False)
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=600,
        )
        raw_content = completion.choices[0].message.content

        if not raw_content or not raw_content.strip():
            raise RuntimeError("The AI returned an empty response.")

        # Preserve compatibility with existing plain-text AI responses.
        reply = raw_content.strip()
        recommended_product_ids = []

        try:
            parsed_response = json.loads(raw_content)

            if isinstance(parsed_response, dict):
                structured_reply = parsed_response.get("reply")
                raw_recommendations = parsed_response.get(
                    "recommended_product_ids",
                    [],
                )

                if (
                    isinstance(structured_reply, str)
                    and structured_reply.strip()
                ):
                    reply = structured_reply.strip()

                    allowed_product_ids = {
                        str(product["id"])
                        for product in catalogue
                    }

                    if isinstance(raw_recommendations, list):
                        seen_ids = set()

                        for product_id in raw_recommendations:
                            if not isinstance(product_id, str):
                                continue

                            if (
                                product_id in allowed_product_ids
                                and product_id not in seen_ids
                            ):
                                recommended_product_ids.append(product_id)
                                seen_ids.add(product_id)

                            if len(recommended_product_ids) >= 4:
                                break

        except (json.JSONDecodeError, TypeError, ValueError):
            pass
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
        "reply": reply,
        "recommended_product_ids": recommended_product_ids,
        "semantic_response": _build_semantic_response(
            "product_discovery",
            reply,
            key_points=[f"Available catalogue products: {len(catalogue)}"],
            evidence=[{
                "source": "active, in-stock marketplace catalogue",
                "available_product_count": len(catalogue),
                "product_ids": [product["id"] for product in catalogue],
            }],
            recommendations=[],
            next_action="Review product details and use the separate checkout flow if desired.",
        ),
        "products": catalogue,
        "payment_created": False,
        "requires_confirmation": False,
        "catalogue_count": len(catalogue),
        "country_code": offer_context["country_code"],
        "paypal_offer_context": offer_context,
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
from uuid import UUID, uuid4
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
            "return_url": f"{PAYPILOT_FRONTEND_URL}/?paypal=return",
            "cancel_url": f"{PAYPILOT_FRONTEND_URL}/?paypal=cancel",
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

# Marketplace checkout uses its own endpoints and return URL.
class MarketplaceCartLine(BaseModel):
    product_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=1000)


class MarketplaceOrderRequest(BaseModel):
    items: list[MarketplaceCartLine] = Field(min_length=1, max_length=50)


@app.post("/api/marketplace/orders")
async def create_marketplace_order(request: MarketplaceOrderRequest):
    """Create a PayPal Sandbox order from current marketplace catalogue prices."""
    product_ids = [item.product_id for item in request.items]
    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(
            status_code=422,
            detail="Each product must appear only once in the cart.",
        )

    placeholders = ",".join("?" for _ in product_ids)
    with database_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT p.id, p.seller_id, p.name, p.description, p.price_minor,
                   p.currency, p.inventory_quantity
            FROM products p
            JOIN sellers s ON s.id = p.seller_id
            WHERE p.id IN ({placeholders})
              AND p.status = 'ACTIVE'
              AND s.status = 'ACTIVE'
            """,
            product_ids,
        ).fetchall()

    products_by_id = {row["id"]: dict(row) for row in rows}
    if len(products_by_id) != len(product_ids):
        raise HTTPException(
            status_code=409,
            detail="A cart item is no longer available. Refresh the marketplace.",
        )

    item_snapshots = []
    total_minor = 0

    for line in request.items:
        product = products_by_id[line.product_id]
        if product["currency"] != "USD":
            raise HTTPException(
                status_code=409,
                detail="Marketplace checkout currently supports USD products only.",
            )
        if line.quantity > product["inventory_quantity"]:
            raise HTTPException(
                status_code=409,
                detail=f"Not enough stock available for {product['name']}.",
            )

        line_total = product["price_minor"] * line.quantity
        total_minor += line_total
        item_snapshots.append({
            "product_id": product["id"],
            "seller_id": product["seller_id"],
            "product_name": product["name"],
            "unit_price_minor": product["price_minor"],
            "quantity": line.quantity,
            "line_total_minor": line_total,
        })

    if total_minor <= 0:
        raise HTTPException(status_code=422, detail="Order total must be positive.")

    amount = f"{total_minor // 100}.{total_minor % 100:02d}"
    local_order_id = str(uuid4())
    token = await _paypal_access_token()

    paypal_items = []
    for item in item_snapshots:
        unit_minor = item["unit_price_minor"]
        paypal_items.append({
            "name": item["product_name"][:127],
            "quantity": str(item["quantity"]),
            "unit_amount": {
                "currency_code": "USD",
                "value": f"{unit_minor // 100}.{unit_minor % 100:02d}",
            },
        })

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": local_order_id,
            "description": f"PayPilot marketplace order {local_order_id[:8]}",
            "amount": {
                "currency_code": "USD",
                "value": amount,
                "breakdown": {
                    "item_total": {
                        "currency_code": "USD",
                        "value": amount,
                    },
                },
            },
            "items": paypal_items,
        }],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "brand_name": "PayPilot AI",
                    "user_action": "PAY_NOW",
                    "return_url": f"{PAYPILOT_FRONTEND_URL}/?marketplace_paypal=return",
                    "cancel_url": (
                        f"{PAYPILOT_FRONTEND_URL}/?marketplace_paypal=cancel"
                        f"&local_order_id={local_order_id}"
                    ),
                },
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{PAYPAL_API_BASE}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "PayPal-Request-Id": local_order_id,
                },
                json=payload,
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not reach PayPal Sandbox to create the marketplace order.",
        )

    if response.status_code not in (200, 201):
        try:
            paypal_error = response.json()
        except ValueError:
            paypal_error = {"message": response.text[:1000]}

        print(
            "PayPal marketplace order creation failed:",
            {
                "status_code": response.status_code,
                "error": paypal_error,
            },
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "PayPal Sandbox rejected marketplace order creation.",
                "paypal_status": response.status_code,
                "paypal_error": paypal_error,
            },
        )

    paypal_data = response.json()
    if not paypal_data.get("id"):
        raise HTTPException(
            status_code=502,
            detail="PayPal returned an order without an order ID.",
        )

    payer_action_url = next(
        (
            link.get("href")
            for link in paypal_data.get("links", [])
            if link.get("rel") == "payer-action"
            and isinstance(link.get("href"), str)
            and link["href"].startswith("https://")
        ),
        None,
    )

    if not payer_action_url:
        raise HTTPException(
            status_code=502,
            detail="PayPal did not return a valid checkout URL.",
        )
    experience_context = (
        payload.get("payment_source", {})
        .get("paypal", {})
        .get("experience_context", {})
    )
    print(
        "Marketplace PayPal redirect diagnostic:",
        {
            "order_id": paypal_data.get("id"),
            "sent_return_url": experience_context.get("return_url"),
            "sent_cancel_url": experience_context.get("cancel_url"),
            "paypal_response_status": paypal_data.get("status"),
        },
    )
    paypal_order_id = paypal_data.get("id")
    approval_url = next(
        (
            link["href"]
            for link in paypal_data.get("links", [])
            if link.get("rel") in ("approve", "payer-action")
        ),
        None,
    )

    if not paypal_order_id or not approval_url:
        raise HTTPException(
            status_code=502,
            detail="PayPal returned an incomplete marketplace order response.",
        )

    now = utc_now()
    with database_connection() as connection:
        connection.execute(
            """
            INSERT INTO marketplace_orders (
                id, paypal_order_id, amount_minor, currency, status,
                inventory_applied, created_at, updated_at
            ) VALUES (?, ?, ?, 'USD', 'PENDING', 0, ?, ?)
            """,
            (local_order_id, paypal_order_id, total_minor, now, now),
        )
        for item in item_snapshots:
            connection.execute(
                """
                INSERT INTO marketplace_order_items (
                    id, order_id, product_id, seller_id, product_name,
                    unit_price_minor, quantity, line_total_minor
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()), local_order_id, item["product_id"],
                    item["seller_id"], item["product_name"],
                    item["unit_price_minor"], item["quantity"],
                    item["line_total_minor"],
                ),
            )

    return {
        "status": "created",
        "order_id": paypal_order_id,
        "approval_url": approval_url,
        "amount": amount,
        "currency": "USD",
        "message": "Marketplace order created. Buyer approval is required.",
        "payment_captured": False,
    }



@app.post("/api/marketplace/orders/{local_order_id}/cancel")
async def cancel_marketplace_order(local_order_id: str):
    """Mark an uncaptured marketplace order cancelled after checking PayPal."""
    try:
        local_order_id = str(UUID(local_order_id))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=422,
            detail="Invalid marketplace order ID.",
        )

    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM marketplace_orders WHERE id = ?",
            (local_order_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Marketplace order not found.",
            )

        order = dict(row)

    if order["status"] == "COMPLETED" or order["inventory_applied"]:
        return {
            "status": order["status"],
            "cancelled": False,
            "message": "This order is already completed and cannot be cancelled here.",
        }

    if order["status"] == "CANCELLED":
        return {
            "status": "CANCELLED",
            "cancelled": True,
            "message": "This order is already cancelled.",
        }

    token = await _paypal_access_token()

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{PAYPAL_API_BASE}/v2/checkout/orders/"
                f"{order['paypal_order_id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not verify the order with PayPal. Its status was not changed.",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="PayPal could not verify the order. Its status was not changed.",
        )

    paypal_order = response.json()

    if paypal_order.get("id") != order["paypal_order_id"]:
        raise HTTPException(
            status_code=502,
            detail="PayPal returned a different order. Its status was not changed.",
        )

    paypal_status = paypal_order.get("status")
    captures = [
        capture
        for unit in paypal_order.get("purchase_units", [])
        for capture in unit.get("payments", {}).get("captures", [])
    ]

    if (
        paypal_status not in ("CREATED", "VOIDED")
        or any(capture.get("status") == "COMPLETED" for capture in captures)
    ):
        return {
            "status": order["status"],
            "cancelled": False,
            "paypal_status": paypal_status,
            "message": (
                "PayPal has not confirmed a safely cancellable order. "
                "The local order remains unchanged."
            ),
        }

    now = utc_now()

    with database_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        current_row = connection.execute(
            "SELECT * FROM marketplace_orders WHERE id = ?",
            (local_order_id,),
        ).fetchone()

        if current_row is None:
            raise HTTPException(
                status_code=404,
                detail="Marketplace order not found.",
            )

        current = dict(current_row)

        if current["status"] != "PENDING" or current["inventory_applied"]:
            return {
                "status": current["status"],
                "cancelled": False,
                "message": "The order changed while cancellation was being checked.",
            }

        connection.execute(
            """
            UPDATE marketplace_orders
            SET status = 'CANCELLED', updated_at = ?
            WHERE id = ? AND status = 'PENDING' AND inventory_applied = 0
            """,
            (now, local_order_id),
        )

    return {
        "status": "CANCELLED",
        "cancelled": True,
        "message": "The uncaptured marketplace order was cancelled locally.",
    }

@app.post("/api/marketplace/orders/{order_id}/capture")
async def capture_marketplace_order(order_id: str):
    """Capture an order and safely reconcile inventory conflicts."""
    if not re.fullmatch(r"[A-Z0-9-]{5,50}", order_id):
        raise HTTPException(status_code=422, detail="Invalid PayPal order ID.")

    with database_connection() as connection:
        order_row = connection.execute(
            "SELECT * FROM marketplace_orders WHERE paypal_order_id = ?",
            (order_id,),
        ).fetchone()
        if order_row is None:
            raise HTTPException(
                status_code=404,
                detail="Marketplace order was not found in this PayPilot AI instance.",
            )

        order = dict(order_row)
        if order["status"] == "CANCELLED":
            raise HTTPException(
                status_code=409,
                detail="This marketplace order was cancelled and cannot be captured.",
            )
        items = [
            dict(row) for row in connection.execute(
                "SELECT * FROM marketplace_order_items WHERE order_id = ?",
                (order["id"],),
            ).fetchall()
        ]
        open_case_row = connection.execute(
            """
            SELECT * FROM marketplace_reconciliation
            WHERE order_id = ? AND status = 'OPEN'
            """,
            (order["id"],),
        ).fetchone()
        open_case = dict(open_case_row) if open_case_row else None

    if order["status"] == "COMPLETED" and order["inventory_applied"]:
        return {
            "status": "COMPLETED",
            "order_id": order_id,
            "payment_captured": True,
            "message": "Marketplace order was already completed.",
        }

    if open_case:
        return {
            "status": "RECONCILIATION_REQUIRED",
            "order_id": order_id,
            "payment_captured": True,
            "capture_ids": [open_case["paypal_capture_id"]]
                if open_case["paypal_capture_id"] else [],
            "message": (
                "This payment has already been captured and is awaiting inventory "
                "reconciliation. Do not retry payment."
            ),
        }

    token = await _paypal_access_token()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "PayPal-Request-Id": order["id"],
                },
                json={},
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not reach PayPal Sandbox to capture this order.",
        )

    if response.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail="PayPal could not capture this order. Confirm buyer approval and retry.",
        )

    data = response.json()
    captures = [
        capture
        for unit in data.get("purchase_units", [])
        for capture in unit.get("payments", {}).get("captures", [])
    ]
    completed_capture = next(
        (capture for capture in captures if capture.get("status") == "COMPLETED"),
        None,
    )

    expected_amount = (
        f"{order['amount_minor'] // 100}.{order['amount_minor'] % 100:02d}"
    )
    capture_amount = (
        completed_capture.get("amount", {}) if completed_capture else {}
    )
    verified = (
        data.get("id") == order_id
        and data.get("status") == "COMPLETED"
        and completed_capture is not None
        and bool(completed_capture.get("id"))
        and capture_amount.get("currency_code") == order["currency"]
        and capture_amount.get("value") == expected_amount
    )

    if not verified:
        return {
            "status": data.get("status", "UNKNOWN"),
            "order_id": data.get("id"),
            "payment_captured": False,
            "message": (
                "PayPal has not returned a capture matching this marketplace order. "
                "The order was not marked completed and inventory was not changed."
            ),
        }

    capture_id = completed_capture["id"]
    now = utc_now()
    inventory_conflict_reason = None

    # Serialize finalization. A savepoint lets us roll back every stock change
    # while still committing a reconciliation record in the outer transaction.
    with database_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        current_row = connection.execute(
            "SELECT * FROM marketplace_orders WHERE id = ?",
            (order["id"],),
        ).fetchone()

        if current_row is None:
            raise HTTPException(status_code=404, detail="Marketplace order not found.")

        current = dict(current_row)
        if current["status"] == "COMPLETED" and current["inventory_applied"]:
            return {
                "status": "COMPLETED",
                "order_id": order_id,
                "payment_captured": True,
                "message": "Marketplace order was already completed.",
            }

        open_case_row = connection.execute(
            """
            SELECT * FROM marketplace_reconciliation
            WHERE order_id = ? AND status = 'OPEN'
            """,
            (order["id"],),
        ).fetchone()
        if open_case_row:
            open_case = dict(open_case_row)
            return {
                "status": "RECONCILIATION_REQUIRED",
                "order_id": order_id,
                "payment_captured": True,
                "capture_ids": [open_case["paypal_capture_id"]]
                    if open_case["paypal_capture_id"] else [],
                "message": (
                    "This payment is already awaiting reconciliation. "
                    "Do not retry payment."
                ),
            }

        connection.execute("SAVEPOINT inventory_apply")

        for item in items:
            cursor = connection.execute(
                """
                UPDATE products
                SET inventory_quantity = inventory_quantity - ?, updated_at = ?
                WHERE id = ? AND status = 'ACTIVE'
                  AND inventory_quantity >= ?
                """,
                (
                    item["quantity"], now, item["product_id"],
                    item["quantity"],
                ),
            )
            if cursor.rowcount != 1:
                inventory_conflict_reason = (
                    f"Inventory finalization failed for product "
                    f"{item['product_name']!r}; stock may be insufficient "
                    "or the product may no longer be active."
                )
                break

        if inventory_conflict_reason:
            connection.execute("ROLLBACK TO SAVEPOINT inventory_apply")
            connection.execute("RELEASE SAVEPOINT inventory_apply")

            connection.execute(
                """
                INSERT INTO marketplace_reconciliation (
                    id, order_id, paypal_order_id, paypal_capture_id,
                    reason, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    paypal_order_id = excluded.paypal_order_id,
                    paypal_capture_id = excluded.paypal_capture_id,
                    reason = excluded.reason,
                    status = 'OPEN',
                    updated_at = excluded.updated_at
                """,
                (
                    str(uuid4()), order["id"], order_id, capture_id,
                    inventory_conflict_reason, now, now,
                ),
            )
        else:
            connection.execute("RELEASE SAVEPOINT inventory_apply")
            connection.execute(
                """
                UPDATE marketplace_orders
                SET status = 'COMPLETED', paypal_capture_id = ?,
                    inventory_applied = 1, updated_at = ?
                WHERE id = ? AND inventory_applied = 0
                """,
                (capture_id, now, order["id"]),
            )

    if inventory_conflict_reason:
        raise HTTPException(
            status_code=409,
            detail=(
                "PayPal reports a successful capture, but inventory could not be "
                "finalized. A reconciliation case was recorded. Do not retry payment."
            ),
        )

    return {
        "status": "COMPLETED",
        "order_id": order_id,
        "capture_ids": [capture_id],
        "payment_captured": True,
        "message": "Marketplace payment captured and inventory updated.",
    }

@app.get("/api/marketplace/orders")
def list_marketplace_orders(
    limit: int = 50,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """List recent marketplace orders for the internal/demo workspace.

    This is not a private customer order-history endpoint. Buyer ownership
    and account authorization must be implemented before public deployment.
    """
    require_admin_token(x_admin_token)
    limit = max(1, min(limit, 100))

    with database_connection() as connection:
        orders = connection.execute(
            """
            SELECT id, paypal_order_id, paypal_capture_id,
                   amount_minor, currency, status, created_at, updated_at
            FROM marketplace_orders
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        results = []
        for order in orders:
            items = connection.execute(
                """
                SELECT product_id, product_name, unit_price_minor,
                       quantity, line_total_minor
                FROM marketplace_order_items
                WHERE order_id = ?
                ORDER BY rowid
                """,
                (order["id"],),
            ).fetchall()

            results.append({
                "id": order["id"],
                "paypal_order_id": order["paypal_order_id"],
                "paypal_capture_id": order["paypal_capture_id"],
                "amount_minor": order["amount_minor"],
                "currency": order["currency"],
                "status": order["status"],
                "created_at": order["created_at"],
                "updated_at": order["updated_at"],
                "items": [dict(item) for item in items],
            })

    return {"orders": results, "count": len(results)}














def paypal_iq_local_date():
    """Return the current calendar date in South Africa."""
    return datetime.now(ZoneInfo("Africa/Johannesburg")).date().isoformat()



# ---------------------------------------------------------------------------
# PayPal IQ — authenticated customer API
# ---------------------------------------------------------------------------

def _paypal_iq_progress(connection, customer_id):
    row = connection.execute(
        "SELECT * FROM paypal_iq_user_progress WHERE customer_id = ?",
        (customer_id,),
    ).fetchone()
    if row:
        return dict(row)
    return {
        "customer_id": customer_id,
        "total_points": 0,
        "quizzes_completed": 0,
        "facts_viewed": 0,
        "current_streak": 0,
        "longest_streak": 0,
        "last_activity_date": None,
        "updated_at": None,
    }


def _paypal_iq_record_activity(
    connection, customer_id, today, points=0, fact_viewed=False
):
    from datetime import date, timedelta

    row = connection.execute(
        "SELECT * FROM paypal_iq_user_progress WHERE customer_id = ?",
        (customer_id,),
    ).fetchone()

    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    now = datetime.now(timezone.utc).isoformat()

    if row is None:
        streak = 1
        connection.execute(
            """
            INSERT INTO paypal_iq_user_progress (
                customer_id, total_points, facts_viewed,
                current_streak, longest_streak,
                last_activity_date, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (customer_id, points, int(fact_viewed), streak, streak, today, now),
        )
        return

    streak = row["current_streak"]
    if row["last_activity_date"] != today:
        streak = streak + 1 if row["last_activity_date"] == yesterday else 1

    connection.execute(
        """
        UPDATE paypal_iq_user_progress
        SET total_points = total_points + ?,
            facts_viewed = facts_viewed + ?,
            current_streak = ?,
            longest_streak = MAX(longest_streak, ?),
            last_activity_date = ?,
            updated_at = ?
        WHERE customer_id = ?
        """,
        (points, int(fact_viewed), streak, streak, today, now, customer_id),
    )


_PAYPAL_IQ_ELIGIBLE = """
    f.status = 'PUBLISHED'
    AND (
        f.country_scope = 'GLOBAL'
        OR (f.country_scope = 'COUNTRY' AND f.country_code = 'ZA')
    )
"""


def _paypal_iq_fact_dict(row):
    return {
        "id": row["id"],
        "fact_code": row["fact_code"],
        "title": row["title"],
        "fact_text": row["fact_text"],
        "explanation": row["explanation"],
        "category": row["category"],
        "country_scope": row["country_scope"],
        "country_code": row["country_code"],
        "source_url": row["source_url"],
        "source_title": row["source_title"],
        "source_type": row["source_type"],
        "source_excerpt": row["source_excerpt"],
        "difficulty": row["difficulty"],
        "verified_at": row["verified_at"],
        "review_at": row["review_at"],
        "fact_version": row["fact_version"],
    }


@app.get("/api/paypal-iq/daily")
def paypal_iq_daily(authorization: str | None = Header(default=None)):
    customer = _get_authenticated_customer(authorization)
    customer_id = customer["id"]
    today = paypal_iq_local_date()

    with database_connection() as connection:
        exposure = connection.execute(
            """
            SELECT f.*
            FROM paypal_iq_daily_exposures e
            JOIN paypal_iq_facts f ON f.id = e.fact_id
            WHERE e.customer_id = ? AND e.exposure_date = ?
            """,
            (customer_id, today),
        ).fetchone()

        if exposure is None:
            fact = connection.execute(
                f"""
                SELECT f.* FROM paypal_iq_facts f
                WHERE {_PAYPAL_IQ_ELIGIBLE}
                AND NOT EXISTS (
                    SELECT 1 FROM paypal_iq_daily_exposures e
                    WHERE e.customer_id = ? AND e.fact_id = f.id
                )
                ORDER BY RANDOM() LIMIT 1
                """,
                (customer_id,),
            ).fetchone()

            if fact is None:
                fact = connection.execute(
                    f"SELECT f.* FROM paypal_iq_facts f WHERE {_PAYPAL_IQ_ELIGIBLE} ORDER BY RANDOM() LIMIT 1"
                ).fetchone()

            if fact is None:
                return {
                    "fact": None,
                    "message": "No published PayPal IQ facts are available yet.",
                    "progress": _paypal_iq_progress(connection, customer_id),
                }

            now = datetime.now(timezone.utc).isoformat()
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO paypal_iq_daily_exposures
                    (id, customer_id, fact_id, exposure_date, viewed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (secrets.token_hex(16), customer_id, fact["id"], today, now),
            )
            if cursor.rowcount:
                _paypal_iq_record_activity(
                    connection, customer_id, today, points=2, fact_viewed=True
                )

            exposure = connection.execute(
                """
                SELECT f.* FROM paypal_iq_daily_exposures e
                JOIN paypal_iq_facts f ON f.id = e.fact_id
                WHERE e.customer_id = ? AND e.exposure_date = ?
                """,
                (customer_id, today),
            ).fetchone()

        return {
            "fact": _paypal_iq_fact_dict(exposure),
            "points_awarded": 2 if exposure else 0,
            "progress": _paypal_iq_progress(connection, customer_id),
        }


@app.get("/api/paypal-iq/facts")
def paypal_iq_facts(
    category: str | None = None,
    difficulty: str | None = None,
    limit: int = 20,
    offset: int = 0,
    authorization: str | None = Header(default=None),
):
    _get_authenticated_customer(authorization)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    clauses = [_PAYPAL_IQ_ELIGIBLE]
    params = []

    if category:
        clauses.append("LOWER(f.category) = LOWER(?)")
        params.append(category.strip())
    if difficulty:
        normalized = difficulty.strip().upper()
        if normalized not in {"BEGINNER", "INTERMEDIATE", "ADVANCED"}:
            raise HTTPException(status_code=400, detail="Invalid difficulty.")
        clauses.append("f.difficulty = ?")
        params.append(normalized)

    where = " AND ".join(clauses)
    with database_connection() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM paypal_iq_facts f WHERE {where}", params
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT f.* FROM paypal_iq_facts f
            WHERE {where}
            ORDER BY f.category, f.title
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()

    return {
        "items": [_paypal_iq_fact_dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/paypal-iq/facts/{fact_id}")
def paypal_iq_fact_detail(
    fact_id: str, authorization: str | None = Header(default=None)
):
    _get_authenticated_customer(authorization)
    with database_connection() as connection:
        row = connection.execute(
            f"SELECT f.* FROM paypal_iq_facts f WHERE f.id = ? AND {_PAYPAL_IQ_ELIGIBLE}",
            (fact_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Fact not found.")
    return {"fact": _paypal_iq_fact_dict(row)}


@app.get("/api/paypal-iq/categories")
def paypal_iq_categories(authorization: str | None = Header(default=None)):
    _get_authenticated_customer(authorization)
    with database_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT DISTINCT f.category FROM paypal_iq_facts f
            WHERE {_PAYPAL_IQ_ELIGIBLE}
            ORDER BY f.category
            """
        ).fetchall()
    return {"categories": [row["category"] for row in rows]}


@app.get("/api/paypal-iq/quiz")
def paypal_iq_quiz(authorization: str | None = Header(default=None)):
    customer = _get_authenticated_customer(authorization)
    today = paypal_iq_local_date()

    with database_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT q.id, q.fact_id, q.question, q.options_json,
                   q.difficulty, f.title AS fact_title, f.category
            FROM paypal_iq_questions q
            JOIN paypal_iq_facts f ON f.id = q.fact_id
            WHERE q.status = 'PUBLISHED'
              AND {_PAYPAL_IQ_ELIGIBLE}
              AND NOT EXISTS (
                  SELECT 1 FROM paypal_iq_quiz_attempts a
                  WHERE a.customer_id = ? AND a.question_id = q.id
                    AND a.attempt_date = ?
              )
            ORDER BY RANDOM()
            LIMIT 3
            """,
            (customer["id"], today),
        ).fetchall()

    return {
        "questions": [
            {
                "id": row["id"],
                "fact_id": row["fact_id"],
                "question": row["question"],
                "options": json.loads(row["options_json"]),
                "difficulty": row["difficulty"],
                "fact_title": row["fact_title"],
                "category": row["category"],
            }
            for row in rows
        ],
        "available_count": len(rows),
        "daily_question_limit": 3,
    }


@app.post("/api/paypal-iq/quiz/submit")
def paypal_iq_quiz_submit(
    payload: PayPalIQQuizSubmitRequest,
    authorization: str | None = Header(default=None),
):
    customer = _get_authenticated_customer(authorization)
    customer_id = customer["id"]
    today = paypal_iq_local_date()

    with database_connection() as connection:
        row = connection.execute(
            f"""
            SELECT q.* FROM paypal_iq_questions q
            JOIN paypal_iq_facts f ON f.id = q.fact_id
            WHERE q.id = ? AND q.status = 'PUBLISHED'
              AND {_PAYPAL_IQ_ELIGIBLE}
            """,
            (payload.question_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Question not found.")

        options = json.loads(row["options_json"])
        valid_labels = {
            chr(ord("A") + index) for index in range(len(options))
        }
        stored_values = {
            str(option).strip().upper() for option in options
        }
        if (
            payload.selected_option not in valid_labels
            and payload.selected_option not in stored_values
        ):
            raise HTTPException(status_code=400, detail="Invalid answer option.")

        correct = payload.selected_option == row["correct_option"]
        points = (
            {"BEGINNER": 10, "INTERMEDIATE": 15, "ADVANCED": 20}.get(
                row["difficulty"], 10
            )
            if correct else 0
        )
        now = datetime.now(timezone.utc).isoformat()

        try:
            connection.execute(
                """
                INSERT INTO paypal_iq_quiz_attempts (
                    id, customer_id, question_id, attempt_date,
                    selected_option, is_correct, points_awarded, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    secrets.token_hex(16), customer_id, row["id"], today,
                    payload.selected_option, int(correct), points, now,
                ),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409,
                detail="You have already answered this question today.",
            )

        _paypal_iq_record_activity(
            connection, customer_id, today, points=points
        )

        completed_today = connection.execute(
            """
            SELECT COUNT(*) FROM paypal_iq_quiz_attempts
            WHERE customer_id = ? AND attempt_date = ?
            """,
            (customer_id, today),
        ).fetchone()[0]

        if completed_today == 3:
            connection.execute(
                """
                UPDATE paypal_iq_user_progress
                SET quizzes_completed = quizzes_completed + 1
                WHERE customer_id = ?
                """,
                (customer_id,),
            )

        return {
            "question_id": row["id"],
            "selected_option": payload.selected_option,
            "is_correct": correct,
            "correct_option": row["correct_option"],
            "explanation": row["explanation"],
            "points_awarded": points,
            "questions_answered_today": completed_today,
            "quiz_completed_today": completed_today >= 3,
            "progress": _paypal_iq_progress(connection, customer_id),
        }


@app.get("/api/paypal-iq/progress")
def paypal_iq_progress(authorization: str | None = Header(default=None)):
    customer = _get_authenticated_customer(authorization)
    with database_connection() as connection:
        progress = _paypal_iq_progress(connection, customer["id"])
        today = paypal_iq_local_date()
        attempts = connection.execute(
            """
            SELECT COUNT(*) FROM paypal_iq_quiz_attempts
            WHERE customer_id = ? AND attempt_date = ?
            """,
            (customer["id"], today),
        ).fetchone()[0]
    return {
        "progress": progress,
        "questions_answered_today": attempts,
        "daily_question_limit": 3,
    }


class PayPalIQFactUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=180)
    fact_text: str | None = Field(default=None, min_length=10, max_length=2000)
    explanation: str | None = Field(default=None, min_length=10, max_length=3000)
    category: str | None = Field(default=None, min_length=2, max_length=80)
    country_scope: Literal["GLOBAL", "COUNTRY"] | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    source_url: str | None = Field(default=None, min_length=10, max_length=1000)
    source_title: str | None = Field(default=None, min_length=3, max_length=250)
    source_type: str | None = Field(default=None, min_length=2, max_length=50)
    source_excerpt: str | None = Field(default=None, max_length=2000)
    difficulty: Literal["BEGINNER", "INTERMEDIATE", "ADVANCED"] | None = None


@app.patch("/api/admin/paypal-iq/facts/{fact_id}")
def update_paypal_iq_fact(
    fact_id: str,
    request: PayPalIQFactUpdateRequest,
    admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    require_admin_token(admin_token)

    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fact fields supplied.")

    if "country_code" in updates and updates["country_code"]:
        updates["country_code"] = updates["country_code"].strip().upper()

    if "country_scope" in updates or "country_code" in updates:
        with database_connection() as connection:
            current = connection.execute(
                "SELECT country_scope, country_code, status FROM paypal_iq_facts WHERE id = ?",
                (fact_id,),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="PayPal IQ fact not found.")
            scope = updates.get("country_scope", current["country_scope"])
            code = updates.get("country_code", current["country_code"])
            if (scope == "GLOBAL" and code is not None) or (scope == "COUNTRY" and not code):
                raise HTTPException(status_code=400, detail="Country scope and country code are inconsistent.")
            if current["status"] == "PUBLISHED":
                raise HTTPException(status_code=409, detail="Published facts cannot be edited.")

    if "source_url" in updates:
        from urllib.parse import urlparse
        parsed = urlparse(updates["source_url"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise HTTPException(status_code=422, detail="Source URL must use HTTPS.")

    updates["status"] = "DRAFT"
    updates["verified_at"] = None
    updates["review_at"] = None
    updates["updated_at"] = utc_now()

    assignments = ", ".join(f"{field} = ?" for field in updates)
    with database_connection() as connection:
        cursor = connection.execute(
            f"UPDATE paypal_iq_facts SET {assignments}, fact_version = fact_version + 1 WHERE id = ? AND status != 'PUBLISHED'",
            (*updates.values(), fact_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Editable fact not found.")

    return {"status": "updated", "fact_id": fact_id, "fact_status": "DRAFT"}


