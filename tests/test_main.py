from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from app.main import app, calculation_history

client = TestClient(app)


def setup_function() -> None:
    """Clear calculation history before each test."""
    calculation_history.clear()


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_add_endpoint() -> None:
    response = client.post("/add", json={"a": 12.5, "b": 7.5})
    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "add"
    assert data["result"] == 20.0
    assert "timestamp" in data


def test_subtract_endpoint() -> None:
    response = client.post("/subtract", json={"a": 10, "b": 15})
    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "subtract"
    assert data["result"] == -5.0


def test_multiply_endpoint() -> None:
    response = client.post("/multiply", json={"a": 6, "b": 7})
    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "multiply"
    assert data["result"] == 42.0


def test_divide_endpoint() -> None:
    response = client.post("/divide", json={"a": 22, "b": 4})
    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "divide"
    assert data["result"] == 5.5


def test_divide_by_zero_returns_400() -> None:
    response = client.post("/divide", json={"a": 10, "b": 0})
    assert response.status_code == 400
    data = response.json()
    assert "divide by zero" in data["detail"].lower()


def test_power_endpoint() -> None:
    response = client.post("/power", json={"a": 2, "b": 8})
    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "power"
    assert data["result"] == 256.0


def test_power_zero_negative_exponent_returns_400() -> None:
    response = client.post("/power", json={"a": 0, "b": -2})
    assert response.status_code == 400
    assert "divide by zero" in response.json()["detail"].lower()


def test_non_numbers_rejected_by_pydantic() -> None:
    # Strings instead of numbers should be rejected (422 Unprocessable Entity)
    resp_str = client.post("/add", json={"a": "not-a-number", "b": 5})
    assert resp_str.status_code == 422

    # Numeric strings should also be rejected by strict number validation
    resp_num_str = client.post("/multiply", json={"a": "10", "b": 2})
    assert resp_num_str.status_code == 422

    # Booleans should be rejected (even though bool subclasses int in Python)
    resp_bool = client.post("/subtract", json={"a": True, "b": 1})
    assert resp_bool.status_code == 422


def test_calculate_expression_precedence_and_parentheses() -> None:
    response = client.post("/calculate", json={"expression": "2 + 3 * 4"})
    assert response.status_code == 200
    assert response.json()["result"] == 14.0

    resp_parens = client.post("/calculate", json={"expression": "(2 + 3) * 4 - -5 + 2 ** 3"})
    assert resp_parens.status_code == 200
    assert resp_parens.json()["result"] == 33.0


def test_calculate_divide_by_zero_returns_400() -> None:
    response = client.post("/calculate", json={"expression": "10 / (5 - 5)"})
    assert response.status_code == 400
    assert "divide by zero" in response.json()["detail"].lower()


def test_calculate_rejects_unsafe_or_invalid_expressions() -> None:
    # Attempted function call / code injection must fail safely with 400
    resp_unsafe = client.post("/calculate", json={"expression": "__import__('os').system('ls')"})
    assert resp_unsafe.status_code == 400

    # Syntax error must return 400
    resp_syntax = client.post("/calculate", json={"expression": "2 + * 3"})
    assert resp_syntax.status_code == 400


def test_history_keeps_last_20_calculations() -> None:
    setup_function()
    for i in range(25):
        res = client.post("/add", json={"a": i, "b": 1})
        assert res.status_code == 200

    hist_resp = client.get("/history")
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    assert len(history) == 20
    # First 5 (0..4) should have been evicted; oldest remaining is i=5 (5 + 1 = 6.0)
    assert history[0]["expression"] == "5 + 1"
    assert history[0]["result"] == 6.0
    # Most recent is i=24 (24 + 1 = 25.0)
    assert history[-1]["expression"] == "24 + 1"
    assert history[-1]["result"] == 25.0


def test_ui_root_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "FastAPI Calculator" in response.text


if __name__ == "__main__":
    # Standalone test runner fallback when pytest binary is not installed in environment
    test_functions = [
        obj for name, obj in list(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    passed = 0
    for fn in test_functions:
        setup_function()
        fn()
        print(f"PASSED: {fn.__name__}")
        passed += 1
    print(f"\nAll {passed}/{len(test_functions)} tests passed successfully!")
