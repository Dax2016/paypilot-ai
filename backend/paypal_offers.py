"""Verified PayPal offer data and validation for PayPilot AI.

This module does not scrape PayPal, call payment APIs, or invent promotions.
Only offers supplied by a trusted source should be marked verified.
"""

from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


OfferStatus = Literal["verified_active", "check_official_page"]


class PayPalOffer(BaseModel):
    """A sourced offer or an official page shoppers can check."""

    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    country_codes: list[str] = Field(min_length=1)
    status: OfferStatus
    source_url: HttpUrl
    terms_url: HttpUrl | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    last_verified_at: datetime | None = None
    eligibility_notes: str = Field(min_length=1, max_length=1000)
    discount_claim: str | None = Field(default=None, max_length=200)

    @field_validator("country_codes")
    @classmethod
    def normalize_country_codes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().upper() for value in values]
        if any(len(value) != 2 or not value.isalpha() for value in normalized):
            raise ValueError("Country codes must be two-letter ISO-style codes.")
        return sorted(set(normalized))

    @field_validator("source_url", "terms_url")
    @classmethod
    def require_official_paypal_https(cls, value):
        if value is None:
            return value
        parsed = urlparse(str(value))
        if parsed.scheme != "https" or not (
            parsed.hostname == "paypal.com"
            or parsed.hostname.endswith(".paypal.com")
        ):
            raise ValueError("Offer links must use an official PayPal HTTPS domain.")
        return value

    @model_validator(mode="after")
    def validate_verification(self):
        if self.status == "verified_active":
            if self.last_verified_at is None:
                raise ValueError("Verified offers need a verification timestamp.")
            if not self.discount_claim:
                raise ValueError("Verified offers need a sourced offer claim.")
        return self


def list_offers(
    offers: list[PayPalOffer],
    country_code: str,
    *,
    now: datetime | None = None,
) -> list[PayPalOffer]:
    """Filter offers by country and dates without upgrading their trust status."""
    country = country_code.strip().upper()
    if len(country) != 2 or not country.isalpha():
        raise ValueError("country_code must be a two-letter country code.")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now must include a timezone.")

    results = []
    for offer in offers:
        if country not in offer.country_codes:
            continue
        if offer.starts_at and offer.starts_at > current_time:
            continue
        if offer.expires_at and offer.expires_at <= current_time:
            continue
        results.append(offer)
    return results
