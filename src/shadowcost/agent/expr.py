"""A small, safe expression language for agent specs.

Specs are drafted by an LLM, so they must not be able to run arbitrary code.
Expressions are parsed with Python's ``ast`` and only a whitelist is
evaluated: the names ``row``, ``event`` and ``today``, field access on
``row``/``event``, number and string constants, ``+``/``-``/``*``, and the
functions in ``FUNCTIONS``. Anything else is rejected before it runs.

Templates embed expressions in ``{{ }}``: ``"Invoice {{row.invoice_id}} for
{{money(row.amount)}}"``.

Spreadsheet values are text, so arithmetic converts numeric text to numbers:
``row.reminders_sent + 1`` is 1 when the cell holds "0".
"""

from __future__ import annotations

import ast
import re
from datetime import date, timedelta
from typing import Any

# An expression may not contain "}}", so "{{a}} and {{b}}" is two expressions, not one.
_TEMPLATE = re.compile(r"\{\{((?:(?!\}\}).)*)\}\}", re.DOTALL)
NAMES = {"row", "event", "today"}


class ExpressionError(ValueError):
    pass


def to_number(value: Any) -> int | float:
    if isinstance(value, bool):
        raise ExpressionError(f"not a number: {value!r}")
    if isinstance(value, int | float):
        return value
    text = re.sub(r"[,$£€\s]", "", str(value))
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            raise ExpressionError(f"not a number: {value!r}") from None


def to_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ExpressionError(f"not a date: {value!r}") from None


def _money(value: Any) -> str:
    return f"${to_number(value):,.2f}"


def _format_date(value: Any) -> str:
    return to_date(value).strftime("%d %b %Y")


def _add_days(value: Any, days: Any) -> str:
    return (to_date(value) + timedelta(days=int(to_number(days)))).isoformat()


def _round(value: Any, digits: Any = 0) -> int | float:
    return round(to_number(value), int(to_number(digits)))


# days_since is bound per evaluation because it depends on ``today``.
FUNCTIONS = {
    "money": _money,
    "format_date": _format_date,
    "add_days": _add_days,
    "round": _round,
    "int": lambda v: int(to_number(v)),
    "days_since": None,
}


def check(expression: str, columns: set[str] | None = None) -> list[str]:
    """Problems that would stop ``expression`` from evaluating, without running it."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as err:
        return [f"syntax error in {expression!r}: {err.msg}"]
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in NAMES and node.id not in FUNCTIONS:
            problems.append(f"unknown name {node.id!r} in {expression!r}")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                problems.append(f"unknown function in {expression!r}")
            if node.keywords:
                problems.append(f"keyword arguments are not allowed in {expression!r}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                problems.append(f"private attribute {node.attr!r} is not allowed in {expression!r}")
            elif not (isinstance(node.value, ast.Name) and node.value.id in {"row", "event"}):
                problems.append(
                    f"only row.<column> and event.<field> are allowed in {expression!r}"
                )
            elif node.value.id == "row" and columns is not None and node.attr not in columns:
                problems.append(f"unknown column {node.attr!r} in {expression!r}")
        elif not isinstance(node, _ALLOWED_NODES):
            problems.append(f"{type(node).__name__} is not allowed in {expression!r}")
    return problems


def evaluate(expression: str, context: dict[str, Any]) -> Any:
    problems = check(expression)
    if problems:
        raise ExpressionError("; ".join(problems))
    today = to_date(context["today"])
    functions = dict(FUNCTIONS, days_since=lambda v: (today - to_date(v)).days)
    return _eval(ast.parse(expression.strip(), mode="eval").body, context, functions)


def render(template: str, context: dict[str, Any]) -> Any:
    """Fill a template's ``{{ }}`` expressions.

    A template that is exactly one expression returns its value as is (so
    numbers stay numbers); otherwise the result is a string.
    """
    whole = _TEMPLATE.fullmatch(template.strip())
    if whole:
        return evaluate(whole.group(1), context)
    return _TEMPLATE.sub(lambda m: format_value(evaluate(m.group(1), context)), template)


def template_problems(template: str, columns: set[str] | None = None) -> list[str]:
    return [p for m in _TEMPLATE.finditer(template) for p in check(m.group(1), columns)]


def format_value(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


_ALLOWED_NODES = (
    ast.Expression, ast.Constant, ast.Name, ast.Load, ast.Attribute, ast.Subscript,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.UnaryOp, ast.USub, ast.Call,
)  # fmt: skip


def _eval(node: ast.AST, context: dict[str, Any], functions: dict) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id == "today":
            return to_date(context["today"])
        return context.get(node.id, {})
    if isinstance(node, ast.Attribute):
        return _field(_eval(node.value, context, functions), node.attr)
    if isinstance(node, ast.Subscript):
        key = _eval(node.slice, context, functions)
        return _field(_eval(node.value, context, functions), str(key))
    if isinstance(node, ast.UnaryOp):
        return -to_number(_eval(node.operand, context, functions))
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, context, functions)
        right = _eval(node.right, context, functions)
        if isinstance(node.op, ast.Add) and isinstance(left, str) and isinstance(right, str):
            try:
                return to_number(left) + to_number(right)
            except ExpressionError:
                return left + right
        a, b = to_number(left), to_number(right)
        return (
            a + b
            if isinstance(node.op, ast.Add)
            else a - b
            if isinstance(node.op, ast.Sub)
            else a * b
        )
    if isinstance(node, ast.Call):
        args = [_eval(arg, context, functions) for arg in node.args]
        return functions[node.func.id](*args)
    raise ExpressionError(f"cannot evaluate {type(node).__name__}")


def _field(record: Any, name: str) -> Any:
    if not isinstance(record, dict) or name not in record:
        raise ExpressionError(f"no field {name!r}")
    return record[name]
