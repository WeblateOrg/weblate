# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helpers shared by the Fluent file format and quality checks."""

from __future__ import annotations

from fluent.syntax import ast

# Keeps the recursive parser well within the stack limit, so stored strings can
# always be read back. This allows about seven nested select expressions.
MAX_FLUENT_AST_DEPTH = 32
# Each select expression is processed for every variant.
MAX_FLUENT_SELECT_EXPRESSIONS = 64


def fluent_ast_is_too_complex(root: ast.BaseNode) -> bool:
    """Check whether a Fluent AST is beyond the limits, without recursing."""
    selectors = 0
    stack: list[tuple[ast.BaseNode, int]] = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_FLUENT_AST_DEPTH:
            return True
        if isinstance(node, ast.SelectExpression):
            selectors += 1
            if selectors > MAX_FLUENT_SELECT_EXPRESSIONS:
                return True
        for value in vars(node).values():
            stack.extend(
                (child, depth + 1)
                for child in (value if isinstance(value, list) else (value,))
                if isinstance(child, ast.BaseNode)
            )
    return False
