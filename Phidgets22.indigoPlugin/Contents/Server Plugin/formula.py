# -*- coding: utf-8 -*-

"""Restricted mathematical expressions shared by plugin features."""

import ast
import math
import operator


def _clamp(value, minimum, maximum):
    if minimum > maximum:
        raise ValueError("clamp minimum must not exceed maximum")
    return max(minimum, min(maximum, value))


FUNCTIONS = {
    "abs": abs, "min": min, "max": max,
    "round": round, "clamp": _clamp,
    "sqrt": math.sqrt, "exp": math.exp,
    "log": math.log, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "floor": math.floor, "ceil": math.ceil,
}
CONSTANTS = {"pi": math.pi, "e": math.e}
BINARY_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
COMPARISON_OPERATORS = {
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
}


class Formula(object):
    def __init__(self, expression):
        self.expression = str(expression or "").strip()
        if not self.expression:
            raise ValueError("Enter a formula using x")
        if len(self.expression) > 200:
            raise ValueError("The formula must be 200 characters or fewer")
        try:
            self.tree = ast.parse(self.expression, mode="eval").body
        except SyntaxError:
            raise ValueError("The formula is not valid mathematical syntax")
        self._validate(self.tree)

    @staticmethod
    def _numericLiteral(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if (isinstance(node, ast.UnaryOp) and
                type(node.op) in UNARY_OPERATORS and
                isinstance(node.operand, ast.Constant) and
                type(node.operand.value) in (int, float)):
            return UNARY_OPERATORS[type(node.op)](node.operand.value)
        raise ValueError

    def _validate(self, node):
        if isinstance(node, ast.Constant):
            if type(node.value) is bool:
                return
            if type(node.value) not in (int, float):
                raise ValueError("Formula constants must be numbers")
            if abs(node.value) > 1e12:
                raise ValueError("Formula constants are too large")
            return
        if isinstance(node, ast.Name):
            if node.id not in set(["x"] + list(CONSTANTS)):
                raise ValueError("Unknown formula name '%s'" % node.id)
            return
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPERATORS:
            if isinstance(node.op, ast.Pow):
                try:
                    exponent = self._numericLiteral(node.right)
                except ValueError:
                    exponent = 101
                if abs(exponent) > 100:
                    raise ValueError(
                        "Formula exponents must be constants from -100 through 100")
            self._validate(node.left)
            self._validate(node.right)
            return
        if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPERATORS:
            self._validate(node.operand)
            return
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            self._validate(node.operand)
            return
        if (isinstance(node, ast.Compare) and node.ops and
                all(type(item) in COMPARISON_OPERATORS for item in node.ops)):
            self._validate(node.left)
            for comparator in node.comparators:
                self._validate(comparator)
            return
        if (isinstance(node, ast.BoolOp) and
                isinstance(node.op, (ast.And, ast.Or))):
            for value in node.values:
                self._validate(value)
            return
        if isinstance(node, ast.IfExp):
            self._validate(node.test)
            self._validate(node.body)
            self._validate(node.orelse)
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id not in FUNCTIONS or node.keywords:
                raise ValueError("Unknown or unsupported formula function")
            if node.func.id == "round":
                if len(node.args) not in (1, 2):
                    raise ValueError("round accepts a value and optional digits")
                if len(node.args) == 2:
                    try:
                        digits = self._numericLiteral(node.args[1])
                    except ValueError:
                        raise ValueError(
                            "round digits must be a whole number from -15 through 15")
                    if type(digits) is not int or not -15 <= digits <= 15:
                        raise ValueError(
                            "round digits must be a whole number from -15 through 15")
            if node.func.id == "clamp" and len(node.args) != 3:
                raise ValueError("clamp requires value, minimum, and maximum")
            for argument in node.args:
                self._validate(argument)
            return
        raise ValueError("The formula contains an unsupported operation")

    def _evaluate(self, node, x):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return x if node.id == "x" else CONSTANTS[node.id]
        if isinstance(node, ast.BinOp):
            return BINARY_OPERATORS[type(node.op)](
                self._evaluate(node.left, x), self._evaluate(node.right, x))
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not bool(self._evaluate(node.operand, x))
            return UNARY_OPERATORS[type(node.op)](self._evaluate(node.operand, x))
        if isinstance(node, ast.Compare):
            left = self._evaluate(node.left, x)
            for operation, comparator in zip(node.ops, node.comparators):
                right = self._evaluate(comparator, x)
                if not COMPARISON_OPERATORS[type(operation)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(bool(self._evaluate(value, x))
                           for value in node.values)
            return any(bool(self._evaluate(value, x))
                       for value in node.values)
        if isinstance(node, ast.IfExp):
            branch = node.body if self._evaluate(node.test, x) else node.orelse
            return self._evaluate(branch, x)
        return FUNCTIONS[node.func.id](
            *[self._evaluate(argument, x) for argument in node.args])

    def evaluate(self, x):
        value = float(self._evaluate(self.tree, float(x)))
        if not math.isfinite(value):
            raise ValueError("Formula result is not finite")
        return value
