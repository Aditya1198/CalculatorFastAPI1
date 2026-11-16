from __future__ import annotations

import ast
from collections import deque
from datetime import datetime, timezone
import math
import operator
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, StrictFloat, StrictInt

try:
    # Pydantic v2
    from pydantic import ConfigDict, field_validator
    PYDANTIC_V2 = True
except ImportError:
    # Pydantic v1 fallback
    from pydantic import Extra, validator
    PYDANTIC_V2 = False

app = FastAPI(
    title="Calculator API",
    description="FastAPI Calculator with safe AST expression parser, in-memory history, and interactive web UI.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for the last 20 calculations
HISTORY_MAX_LEN = 20
calculation_history: Deque[Dict[str, Any]] = deque(maxlen=HISTORY_MAX_LEN)

NumberType = Union[StrictInt, StrictFloat]


def _validate_finite_number(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError("Input must be a valid number (int or float), not a string or boolean.")
    if math.isnan(v) or math.isinf(v):
        raise ValueError("Input must be a finite number.")
    return float(v)


def _validate_expression_str(v: Any) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError("Expression must be a non-empty string.")
    return v.strip()


if PYDANTIC_V2:
    class TwoNumbersRequest(BaseModel):
        """Request schema for binary arithmetic endpoints (/add, /subtract, /multiply, /divide, /power)."""

        model_config = ConfigDict(extra="forbid")

        a: NumberType
        b: NumberType

        @field_validator("a", "b", mode="before")
        @classmethod
        def check_numbers(cls, v: Any) -> float:
            return _validate_finite_number(v)

    class ExpressionRequest(BaseModel):
        """Request schema for the safe expression evaluator (/calculate)."""

        model_config = ConfigDict(extra="forbid")

        expression: str

        @field_validator("expression", mode="before")
        @classmethod
        def check_expression(cls, v: Any) -> str:
            return _validate_expression_str(v)
else:
    class TwoNumbersRequest(BaseModel):
        """Request schema for binary arithmetic endpoints (/add, /subtract, /multiply, /divide, /power)."""

        a: NumberType
        b: NumberType

        class Config:
            extra = Extra.forbid

        @validator("a", "b", pre=True)
        def check_numbers(cls, v: Any) -> float:
            return _validate_finite_number(v)

    class ExpressionRequest(BaseModel):
        """Request schema for the safe expression evaluator (/calculate)."""

        expression: str

        class Config:
            extra = Extra.forbid

        @validator("expression", pre=True)
        def check_expression(cls, v: Any) -> str:
            return _validate_expression_str(v)


class CalculationResponse(BaseModel):
    operation: str
    expression: str
    result: float
    timestamp: str


def _model_to_dict(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


# Safe AST-based mathematical parser (no eval)
_ALLOWED_BIN_OPS: Dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}

_ALLOWED_UNARY_OPS: Dict[type, Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def safe_eval_expression(expression: str) -> float:
    """Safely parse and evaluate a mathematical expression string using Python's ast module (no eval)."""
    if not isinstance(expression, str) or not expression.strip():
        raise HTTPException(status_code=400, detail="Expression cannot be empty.")

    normalized = expression.strip()

    try:
        parsed = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid syntax in expression '{expression}'.",
        ) from exc

    def _eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)

        if isinstance(node, ast.Constant):
            val = node.value
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise HTTPException(
                    status_code=400,
                    detail="Only numeric constants (int or float) are allowed.",
                )
            return float(val)

        if hasattr(ast, "Num") and isinstance(node, getattr(ast, "Num")):
            n_val = getattr(node, "n")
            if isinstance(n_val, bool) or not isinstance(n_val, (int, float)):
                raise HTTPException(status_code=400, detail="Only numeric constants are allowed.")
            return float(n_val)

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_UNARY_OPS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported unary operator: {op_type.__name__}",
                )
            operand = _eval_node(node.operand)
            return float(_ALLOWED_UNARY_OPS[op_type](operand))

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_BIN_OPS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported binary operator: {op_type.__name__}",
                )
            left = _eval_node(node.left)
            right = _eval_node(node.right)

            if op_type in (ast.Div, ast.Mod) and right == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot divide by zero.",
                )

            if op_type is ast.Pow:
                if left == 0 and right < 0:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot divide by zero (zero raised to a negative power).",
                    )
                if abs(right) > 10000:
                    raise HTTPException(
                        status_code=400,
                        detail="Exponent is too large to compute safely.",
                    )
                if left < 0 and not float(right).is_integer():
                    raise HTTPException(
                        status_code=400,
                        detail="Negative base with fractional exponent results in a complex number.",
                    )

            try:
                res = _ALLOWED_BIN_OPS[op_type](left, right)
            except OverflowError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Calculation resulted in numeric overflow.",
                ) from exc
            except ZeroDivisionError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot divide by zero.",
                ) from exc

            if isinstance(res, complex) or math.isnan(res) or math.isinf(res):
                raise HTTPException(
                    status_code=400,
                    detail="Calculation resulted in a non-finite or complex number.",
                )
            return float(res)

        raise HTTPException(
            status_code=400,
            detail=f"Disallowed or unsupported expression element: {type(node).__name__}",
        )

    return _eval_node(parsed)


def _record_calculation(operation: str, expression: str, result: float) -> CalculationResponse:
    clean_result = 0.0 if result == 0 else float(result)
    entry = CalculationResponse(
        operation=operation,
        expression=expression,
        result=clean_result,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    calculation_history.append(_model_to_dict(entry))
    return entry


def _format_num(n: Union[float, int]) -> str:
    if isinstance(n, float) and n.is_integer():
        return str(int(n))
    return str(n)


@app.get("/health", tags=["System"])
def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/add", response_model=CalculationResponse, tags=["Operations"])
def add_numbers(payload: TwoNumbersRequest) -> CalculationResponse:
    """Add two numbers (a + b)."""
    res = float(payload.a + payload.b)
    return _record_calculation("add", f"{_format_num(payload.a)} + {_format_num(payload.b)}", res)


@app.post("/subtract", response_model=CalculationResponse, tags=["Operations"])
def subtract_numbers(payload: TwoNumbersRequest) -> CalculationResponse:
    """Subtract second number from first number (a - b)."""
    res = float(payload.a - payload.b)
    return _record_calculation("subtract", f"{_format_num(payload.a)} - {_format_num(payload.b)}", res)


@app.post("/multiply", response_model=CalculationResponse, tags=["Operations"])
def multiply_numbers(payload: TwoNumbersRequest) -> CalculationResponse:
    """Multiply two numbers (a * b)."""
    res = float(payload.a * payload.b)
    return _record_calculation("multiply", f"{_format_num(payload.a)} * {_format_num(payload.b)}", res)


@app.post("/divide", response_model=CalculationResponse, tags=["Operations"])
def divide_numbers(payload: TwoNumbersRequest) -> CalculationResponse:
    """Divide first number by second number (a / b). Returns 400 on division by zero."""
    if payload.b == 0:
        raise HTTPException(status_code=400, detail="Cannot divide by zero.")
    res = float(payload.a / payload.b)
    return _record_calculation("divide", f"{_format_num(payload.a)} / {_format_num(payload.b)}", res)


@app.post("/power", response_model=CalculationResponse, tags=["Operations"])
def power_numbers(payload: TwoNumbersRequest) -> CalculationResponse:
    """Raise first number to the power of the second number (a ** b)."""
    if payload.a == 0 and payload.b < 0:
        raise HTTPException(status_code=400, detail="Cannot divide by zero (zero raised to a negative power).")
    if abs(payload.b) > 10000:
        raise HTTPException(status_code=400, detail="Exponent is too large to compute safely.")
    if payload.a < 0 and not float(payload.b).is_integer():
        raise HTTPException(status_code=400, detail="Negative base with fractional exponent is not supported.")
    try:
        res = float(payload.a ** payload.b)
    except OverflowError as exc:
        raise HTTPException(status_code=400, detail="Calculation resulted in numeric overflow.") from exc
    if math.isnan(res) or math.isinf(res):
        raise HTTPException(status_code=400, detail="Calculation resulted in a non-finite number.")
    return _record_calculation("power", f"{_format_num(payload.a)} ** {_format_num(payload.b)}", res)


@app.post("/calculate", response_model=CalculationResponse, tags=["Operations"])
def calculate_expression(payload: ExpressionRequest) -> CalculationResponse:
    """Safely evaluate an arithmetic expression string like '2 + 3 * 4' without eval()."""
    result = safe_eval_expression(payload.expression)
    return _record_calculation("calculate", payload.expression, result)


@app.get("/history", response_model=List[CalculationResponse], tags=["History"])
def get_history() -> List[Dict[str, Any]]:
    """Return the last 20 calculations kept in memory."""
    return list(calculation_history)


@app.delete("/history", tags=["History"])
def clear_history() -> Dict[str, str]:
    """Clear the in-memory calculation history."""
    calculation_history.clear()
    return {"message": "History cleared."}


UI_FILE = Path(__file__).parent / "static" / "index.html"


@app.get("/", response_class=HTMLResponse, tags=["UI"])
def serve_calculator_ui() -> HTMLResponse:
    """Serve the single-page Calculator HTML/JS application."""
    if UI_FILE.exists():
        return HTMLResponse(content=UI_FILE.read_text(encoding="utf-8"), status_code=200)
    return HTMLResponse(content="<h1>Calculator UI not found</h1>", status_code=404)
