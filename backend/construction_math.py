"""Deterministic construction quantities. The LLM never evaluates money or formulas."""

import ast
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from backend.business import DomainError


LENGTH_UNITS = {"мм": Decimal("0.001"), "см": Decimal("0.01"), "м": Decimal(1), "м.п.": Decimal(1)}
UNITS = frozenset((*LENGTH_UNITS, "м²", "м³", "шт.", "компл.", "кг", "т", "л", "ч", "чел.-ч", "маш.-ч"))
KINDS = ("work", "material", "equipment", "service", "other")


def decimal_value(value, label, minimum=Decimal(0), maximum=Decimal("1000000000")):
    if isinstance(value, bool) or value is None:
        raise DomainError(400, f"Неверное значение: {label}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise DomainError(400, f"Неверное значение: {label}") from None
    if not number.is_finite() or not minimum <= number <= maximum:
        raise DomainError(400, f"Неверное значение: {label}")
    return number


def length_in_metres(value, unit):
    if unit not in LENGTH_UNITS:
        raise DomainError(400, "Для длины выберите мм, см или м")
    return decimal_value(value, "Длина") * LENGTH_UNITS[unit]


def evaluate(expression, variables):
    if not isinstance(expression, str) or not 1 <= len(expression) <= 160:
        raise DomainError(400, "Формула должна содержать от 1 до 160 символов")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError):
        raise DomainError(400, "Неверная формула") from None
    if sum(1 for _ in ast.walk(tree)) > 50:
        raise DomainError(400, "Формула слишком сложная")

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return decimal_value(node.value, "Число")
        if isinstance(node, ast.Name) and node.id in variables:
            return decimal_value(variables[node.id], node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            else:
                if right == 0:
                    raise DomainError(400, "Деление на ноль")
                value = left / right
            if abs(value) > Decimal("1000000000"):
                raise DomainError(400, "Объём слишком велик")
            return value
        raise DomainError(400, "В формуле разрешены только числа, переменные, +, −, ×, ÷ и скобки")

    result = walk(tree)
    if not result.is_finite() or result < 0:
        raise DomainError(400, "Расчётный объём не может быть отрицательным")
    return result.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def zone_values(length, width, height, openings=0):
    length = decimal_value(length, "Длина")
    width = decimal_value(width, "Ширина")
    height = decimal_value(height, "Высота")
    openings = decimal_value(openings, "Проёмы")
    return {
        "length": length, "width": width, "height": height,
        "area": length * width, "perimeter": (length + width) * 2,
        "volume": length * width * height, "openings": openings,
    }


def money(quantity, price_kopecks):
    if isinstance(price_kopecks, bool) or not isinstance(price_kopecks, int) or not 0 <= price_kopecks <= 100_000_000_000:
        raise DomainError(400, "Неверная расценка")
    amount = (decimal_value(quantity, "Объём") * price_kopecks).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    if amount > 100_000_000_000:
        raise DomainError(400, "Стоимость слишком велика")
    return int(amount)
