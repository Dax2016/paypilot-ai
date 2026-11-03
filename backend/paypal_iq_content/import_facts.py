import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

BASE_URL = os.getenv("PAYPILOT_API_URL", "http://127.0.0.1:8001").rstrip("/")
TOKEN = os.getenv("PAYPILOT_ADMIN_TOKEN", "")
CONTENT_FILE = Path(__file__).with_name("facts.json")

REQUIRED_FIELDS = {
    "fact_code", "title", "fact_text", "explanation", "category",
    "country_scope", "source_url", "source_title", "source_type",
    "difficulty",
}

def validate_facts(facts):
    if not isinstance(facts, list) or not facts:
        raise ValueError("The content file must contain a non-empty facts list.")

    codes = set()

    for index, fact in enumerate(facts, start=1):
        missing = REQUIRED_FIELDS - fact.keys()
        if missing:
            raise ValueError(f"Fact {index} is missing: {sorted(missing)}")

        code = fact["fact_code"].strip().upper()
        if code in codes:
            raise ValueError(f"Duplicate fact_code: {code}")
        codes.add(code)

        if fact["country_scope"] not in ("GLOBAL", "COUNTRY"):
            raise ValueError(f"{code}: country_scope must be GLOBAL or COUNTRY.")

        if fact["country_scope"] == "GLOBAL" and fact.get("country_code"):
            raise ValueError(f"{code}: GLOBAL facts cannot have a country_code.")

        if fact["country_scope"] == "COUNTRY" and not fact.get("country_code"):
            raise ValueError(f"{code}: COUNTRY facts require a country_code.")

        if fact["difficulty"] not in ("BEGINNER", "INTERMEDIATE", "ADVANCED"):
            raise ValueError(f"{code}: invalid difficulty.")

        parsed = urlparse(fact["source_url"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"{code}: source_url must be a valid HTTPS URL.")

        fact["fact_code"] = code

    return facts

def main():
    if not TOKEN:
        sys.exit("Set PAYPILOT_ADMIN_TOKEN in this terminal before importing.")

    if not CONTENT_FILE.exists():
        sys.exit(f"Content file not found: {CONTENT_FILE}")

    try:
        data = json.loads(CONTENT_FILE.read_text(encoding="utf-8-sig"))
        facts = validate_facts(data["facts"])
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.exit(f"Content validation failed: {exc}")

    print(f"Validated {len(facts)} facts.")
    print("All facts will be created as drafts. Nothing will be published.")

    created = 0
    failed = 0

    for fact in facts:
        request = urllib.request.Request(
            f"{BASE_URL}/api/admin/paypal-iq/facts",
            data=json.dumps(fact).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Admin-Token": TOKEN,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                created += 1
                print(f"CREATED: {fact['fact_code']} | {result}")
        except urllib.error.HTTPError as exc:
            failed += 1
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"FAILED: {fact['fact_code']} | HTTP {exc.code} | {detail}")
        except urllib.error.URLError as exc:
            failed += 1
            print(f"FAILED: {fact['fact_code']} | {exc.reason}")
            break

    print(f"\nImport complete: {created} created, {failed} failed.")

if __name__ == "__main__":
    main()

