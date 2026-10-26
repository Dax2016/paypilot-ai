
import asyncio
import uuid

import pytest

import main


ORDER_ID = "TESTORDER123"
CAPTURE_ID = "TESTCAPTURE123"


class FakePayPalResponse:
    status_code = 201

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def paypal_payload(
    *,
    order_id=ORDER_ID,
    status="COMPLETED",
    capture_status="COMPLETED",
    amount="29.99",
    currency="USD",
    capture_id=CAPTURE_ID,
):
    return {
        "id": order_id,
        "status": status,
        "purchase_units": [
            {
                "payments": {
                    "captures": [
                        {
                            "id": capture_id,
                            "status": capture_status,
                            "amount": {
                                "currency_code": currency,
                                "value": amount,
                            },
                        }
                    ]
                }
            }
        ],
    }


class FakeAsyncClient:
    payload = paypal_payload()
    status_code = 201
    requests = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.requests.append({"url": url, **kwargs})
        return FakePayPalResponseWithStatus(
            self.payload, self.status_code
        )


class FakePayPalResponseWithStatus(FakePayPalResponse):
    def __init__(self, payload, status_code):
        super().__init__(payload)
        self.status_code = status_code


@pytest.fixture
def checkout(monkeypatch, tmp_path):
    # Use a disposable database, never the real demo database.
    monkeypatch.setattr(
        main, "DATABASE_PATH", tmp_path / "paypilot_test.db"
    )
    main.init_database()

    now = main.utc_now()
    seller_id = str(uuid.uuid4())
    product_id = str(uuid.uuid4())
    local_order_id = str(uuid.uuid4())

    with main.database_connection() as connection:
        connection.execute(
            """
            INSERT INTO sellers (
                id, display_name, email, status, created_at, updated_at
            ) VALUES (?, ?, ?, 'ACTIVE', ?, ?)
            """,
            (seller_id, "Test Seller", f"{seller_id}@example.test", now, now),
        )
        connection.execute(
            """
            INSERT INTO products (
                id, seller_id, name, description, category,
                price_minor, currency, inventory_quantity, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, '', 'Test', 2999, 'USD', 10, 'ACTIVE', ?, ?)
            """,
            (product_id, seller_id, "Test Headphones", now, now),
        )
        connection.execute(
            """
            INSERT INTO marketplace_orders (
                id, paypal_order_id, amount_minor, currency, status,
                inventory_applied, created_at, updated_at
            ) VALUES (?, ?, 2999, 'USD', 'PENDING', 0, ?, ?)
            """,
            (local_order_id, ORDER_ID, now, now),
        )
        connection.execute(
            """
            INSERT INTO marketplace_order_items (
                id, order_id, product_id, product_name,
                unit_price_minor, quantity, line_total_minor
            ) VALUES (?, ?, ?, ?, 2999, 1, 2999)
            """,
            (
                str(uuid.uuid4()),
                local_order_id,
                product_id,
                "Test Headphones",
            ),
        )

    FakeAsyncClient.payload = paypal_payload()
    FakeAsyncClient.status_code = 201
    FakeAsyncClient.requests = []

    async def fake_access_token():
        return "fake-test-token"

    monkeypatch.setattr(main, "_paypal_access_token", fake_access_token)
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    return {"product_id": product_id, "local_order_id": local_order_id}


def inventory(product_id):
    with main.database_connection() as connection:
        row = connection.execute(
            "SELECT inventory_quantity FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        return row["inventory_quantity"]


def order_record():
    with main.database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM marketplace_orders WHERE paypal_order_id = ?",
            (ORDER_ID,),
        ).fetchone()
        return dict(row)


def test_successful_capture_deducts_inventory_once(checkout):
    result = asyncio.run(main.capture_marketplace_order(ORDER_ID))

    assert result["payment_captured"] is True
    assert result["status"] == "COMPLETED"
    assert inventory(checkout["product_id"]) == 9

    saved_order = order_record()
    assert saved_order["status"] == "COMPLETED"
    assert saved_order["inventory_applied"] == 1
    assert saved_order["paypal_capture_id"] == CAPTURE_ID


def test_retry_does_not_deduct_inventory_twice(checkout):
    first = asyncio.run(main.capture_marketplace_order(ORDER_ID))
    second = asyncio.run(main.capture_marketplace_order(ORDER_ID))

    assert first["payment_captured"] is True
    assert second["payment_captured"] is True
    assert inventory(checkout["product_id"]) == 9
    assert len(FakeAsyncClient.requests) == 1


@pytest.mark.parametrize(
    ("amount", "currency"),
    [
        ("19.99", "USD"),
        ("29.99", "EUR"),
    ],
)
def test_mismatched_capture_is_not_finalized(checkout, amount, currency):
    FakeAsyncClient.payload = paypal_payload(
        amount=amount, currency=currency
    )

    result = asyncio.run(main.capture_marketplace_order(ORDER_ID))

    assert result["payment_captured"] is False
    assert inventory(checkout["product_id"]) == 10

    saved_order = order_record()
    assert saved_order["status"] == "PENDING"
    assert saved_order["inventory_applied"] == 0


def test_incomplete_capture_leaves_inventory_unchanged(checkout):
    FakeAsyncClient.payload = paypal_payload(
        status="PENDING",
        capture_status="PENDING",
    )

    result = asyncio.run(main.capture_marketplace_order(ORDER_ID))

    assert result["payment_captured"] is False
    assert inventory(checkout["product_id"]) == 10

    saved_order = order_record()
    assert saved_order["status"] == "PENDING"
    assert saved_order["inventory_applied"] == 0



def test_insufficient_inventory_does_not_go_negative(checkout):
    # Simulate stock changing after the order was created.
    with main.database_connection() as connection:
        connection.execute(
            """
            UPDATE products
            SET inventory_quantity = 0
            WHERE id = ?
            """,
            (checkout["product_id"],),
        )

    with pytest.raises(main.HTTPException) as exc_info:
        asyncio.run(main.capture_marketplace_order(ORDER_ID))

    assert exc_info.value.status_code == 409
    assert inventory(checkout["product_id"]) == 0

    saved_order = order_record()
    assert saved_order["inventory_applied"] == 0
    assert saved_order["status"] == "PENDING"




def test_inventory_conflict_records_reconciliation_and_blocks_retry(checkout):
    # Simulate stock changing after order creation.
    with main.database_connection() as connection:
        connection.execute(
            "UPDATE products SET inventory_quantity = 0 WHERE id = ?",
            (checkout["product_id"],),
        )

    with pytest.raises(main.HTTPException) as exc_info:
        asyncio.run(main.capture_marketplace_order(ORDER_ID))

    assert exc_info.value.status_code == 409
    assert inventory(checkout["product_id"]) == 0

    saved_order = order_record()
    assert saved_order["status"] == "PENDING"
    assert saved_order["inventory_applied"] == 0
    assert saved_order["paypal_capture_id"] is None

    with main.database_connection() as connection:
        case = connection.execute(
            """
            SELECT * FROM marketplace_reconciliation
            WHERE order_id = ? AND status = 'OPEN'
            """,
            (checkout["local_order_id"],),
        ).fetchone()

    assert case is not None
    assert case["paypal_order_id"] == ORDER_ID
    assert case["paypal_capture_id"] == CAPTURE_ID
    assert "Inventory finalization failed" in case["reason"]
    assert len(FakeAsyncClient.requests) == 1

    retry = asyncio.run(main.capture_marketplace_order(ORDER_ID))

    assert retry["status"] == "RECONCILIATION_REQUIRED"
    assert retry["payment_captured"] is True
    assert len(FakeAsyncClient.requests) == 1
    assert inventory(checkout["product_id"]) == 0


def test_paypal_http_error_does_not_change_inventory(checkout):
    FakeAsyncClient.status_code = 500
    FakeAsyncClient.payload = {"error": "INTERNAL_SERVER_ERROR"}

    with pytest.raises(main.HTTPException) as exc_info:
        asyncio.run(main.capture_marketplace_order(ORDER_ID))

    assert exc_info.value.status_code == 502
    assert inventory(checkout["product_id"]) == 10

    saved_order = order_record()
    assert saved_order["status"] == "PENDING"
    assert saved_order["inventory_applied"] == 0


def test_paypal_network_error_does_not_change_inventory(
    checkout, monkeypatch
):
    class NetworkErrorClient(FakeAsyncClient):
        async def post(self, url, **kwargs):
            raise main.httpx.ConnectError("Simulated connection failure")

    monkeypatch.setattr(main.httpx, "AsyncClient", NetworkErrorClient)

    with pytest.raises(main.HTTPException) as exc_info:
        asyncio.run(main.capture_marketplace_order(ORDER_ID))

    assert exc_info.value.status_code == 502
    assert inventory(checkout["product_id"]) == 10

    saved_order = order_record()
    assert saved_order["status"] == "PENDING"
    assert saved_order["inventory_applied"] == 0
