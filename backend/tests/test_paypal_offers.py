from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from paypal_offers import PayPalOffer, list_offers


NOW = datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)


def make_offer(**overrides):
    data = {
        "id": "za-example",
        "title": "Example PayPal offer",
        "description": "Example offer for validation tests.",
        "country_codes": ["za"],
        "status": "verified_active",
        "source_url": "https://www.paypal.com/za/",
        "terms_url": "https://www.paypal.com/za/",
        "last_verified_at": NOW - timedelta(minutes=5),
        "eligibility_notes": "Eligibility must be confirmed on the official page.",
        "discount_claim": "Example claim supplied by a verified source",
        "expires_at": NOW + timedelta(days=1),
    }
    data.update(overrides)
    return PayPalOffer(**data)


def test_country_codes_are_normalized():
    offer = make_offer(country_codes=["za", "ZA"])
    assert offer.country_codes == ["ZA"]


def test_offer_is_returned_for_eligible_country():
    offer = make_offer()
    assert list_offers([offer], "ZA", now=NOW) == [offer]
    assert list_offers([offer], "US", now=NOW) == []


def test_expired_offer_is_excluded():
    offer = make_offer(expires_at=NOW - timedelta(seconds=1))
    assert list_offers([offer], "ZA", now=NOW) == []


def test_future_offer_is_excluded():
    offer = make_offer(starts_at=NOW + timedelta(hours=1))
    assert list_offers([offer], "ZA", now=NOW) == []


def test_unverified_page_does_not_need_discount_claim():
    offer = make_offer(
        status="check_official_page",
        last_verified_at=None,
        discount_claim=None,
    )
    assert offer.status == "check_official_page"


def test_verified_offer_requires_verification_timestamp():
    with pytest.raises(ValidationError):
        make_offer(last_verified_at=None)


def test_non_paypal_source_url_is_rejected():
    with pytest.raises(ValidationError):
        make_offer(source_url="https://example.com/promo")


def test_invalid_country_code_is_rejected():
    with pytest.raises(ValidationError):
        make_offer(country_codes=["South Africa"])


def test_naive_current_time_is_rejected():
    offer = make_offer()
    with pytest.raises(ValueError, match="timezone"):
        list_offers([offer], "ZA", now=datetime(2026, 10, 29, 10, 0))
