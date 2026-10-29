from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import main
from paypal_offers import PayPalOffer


NOW = datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)


def make_offer(**overrides):
    data = {
        "id": "za-context-test",
        "title": "Test PayPal promotion",
        "description": "A test record, not a real promotion.",
        "country_codes": ["ZA"],
        "status": "verified_active",
        "source_url": "https://www.paypal.com/za/",
        "terms_url": "https://www.paypal.com/za/",
        "last_verified_at": NOW - timedelta(minutes=5),
        "eligibility_notes": "Test eligibility text.",
        "discount_claim": "Test claim only.",
        "expires_at": NOW + timedelta(days=1),
    }
    data.update(overrides)
    return PayPalOffer(**data)


def test_assistant_request_defaults_to_south_africa():
    request = main.AssistantRequest(message="Find a laptop")
    assert request.country_code == "ZA"


def test_assistant_request_normalizes_country_code():
    request = main.AssistantRequest(message="Find a laptop", country_code="za")
    assert request.country_code == "ZA"


@pytest.mark.parametrize("country_code", ["INVALID", "Z", "12", ""])
def test_assistant_request_rejects_invalid_country_code(country_code):
    with pytest.raises(ValidationError):
        main.AssistantRequest(
            message="Find a laptop",
            country_code=country_code,
        )


def test_empty_offer_context_has_official_links(monkeypatch):
    monkeypatch.setattr(main, "PAYPAL_OFFERS", [])

    context = main.build_paypal_offer_context("za")

    assert context["country_code"] == "ZA"
    assert context["verified_offers"] == []
    assert context["offers_to_check"] == []
    assert context["count"] == 0
    assert "Do not claim a promotion exists" in context["message"]
    assert context["official_links"]["account"].startswith(
        "https://www.paypal.com/za/"
    )


def test_only_verified_active_offers_enter_verified_list(monkeypatch):
    verified = make_offer()
    unverified = make_offer(
        id="za-check-page",
        status="check_official_page",
        last_verified_at=None,
        discount_claim=None,
    )
    monkeypatch.setattr(main, "PAYPAL_OFFERS", [verified, unverified])

    context = main.build_paypal_offer_context("ZA")

    assert [item["id"] for item in context["verified_offers"]] == [
        "za-context-test"
    ]
    assert [item["id"] for item in context["offers_to_check"]] == [
        "za-check-page"
    ]
    assert context["count"] == 1


def test_offer_context_excludes_offers_for_other_countries(monkeypatch):
    us_offer = make_offer(
        id="us-context-test",
        country_codes=["US"],
    )
    monkeypatch.setattr(main, "PAYPAL_OFFERS", [us_offer])

    context = main.build_paypal_offer_context("ZA")

    assert context["verified_offers"] == []
    assert context["count"] == 0

def test_shopping_assistant_sends_offer_context_to_ai(monkeypatch):
    import json
    from types import SimpleNamespace

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query):
            return self

        def fetchall(self):
            return [{
                "id": "product-1",
                "name": "Test Laptop",
                "description": "A test laptop",
                "category": "Electronics",
                "price_minor": 100000,
                "currency": "ZAR",
                "inventory_quantity": 3,
                "seller_name": "Test Seller",
            }]

    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="No verified PayPal promotions are currently listed for South Africa."
                        )
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(
                completions=FakeCompletions()
            )

    monkeypatch.setattr(main, "database_connection", lambda: FakeConnection())
    monkeypatch.setattr(main, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(main, "PAYPAL_OFFERS", [])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    request = main.AssistantRequest(
        message="Are there any PayPal promotions?",
        country_code="ZA",
    )
    response = main.shopping_assistant(request)

    assert response["status"] == "answered_from_catalogue"
    assert response["payment_created"] is False
    assert response["country_code"] == "ZA"
    assert response["paypal_offer_context"]["verified_offers"] == []

    user_prompt = captured["messages"][1]["content"]
    assert "Shopper country: ZA" in user_prompt
    assert "PayPal offer context (authoritative)" in user_prompt

    context_text = user_prompt.split(
        "PayPal offer context (authoritative):\n", 1
    )[1]
    context = json.loads(context_text)
    assert context["country_code"] == "ZA"
    assert context["verified_offers"] == []
    assert context["official_links"]["account"].startswith(
        "https://www.paypal.com/za/"
    )

    system_prompt = captured["messages"][0]["content"]
    assert "Offers in offers_to_check are unconfirmed" in system_prompt
    assert "Do not claim a discount is automatically applied" in system_prompt

def test_shopping_assistant_empty_catalogue_returns_offer_context(monkeypatch):
    class EmptyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query):
            return self

        def fetchall(self):
            return []

    def unexpected_openai_call(*args, **kwargs):
        raise AssertionError("OpenAI must not be called for an empty catalogue.")

    monkeypatch.setattr(
        main,
        "database_connection",
        lambda: EmptyConnection(),
    )
    monkeypatch.setattr(main, "PAYPAL_OFFERS", [])
    monkeypatch.setattr(main, "OpenAI", unexpected_openai_call)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    request = main.AssistantRequest(
        message="Are there any promotions?",
        country_code="ZA",
    )

    response = main.shopping_assistant(request)

    assert response["status"] == "catalogue_empty"
    assert response["products"] == []
    assert response["payment_created"] is False
    assert response["country_code"] == "ZA"

    context = response["paypal_offer_context"]
    assert context["country_code"] == "ZA"
    assert context["verified_offers"] == []
    assert context["offers_to_check"] == []
    assert context["official_links"]["account"].startswith(
        "https://www.paypal.com/za/"
    )

