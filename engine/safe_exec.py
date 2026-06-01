"""engine/safe_exec.py — AST-based security validator + restricted exec for strategy code."""
import ast
import builtins
from typing import Any


class CodeSecurityError(ValueError):
    pass


_BLOCKED_IMPORTS = frozenset({
    "os", "sys", "subprocess", "importlib", "shutil", "socket",
    "ctypes", "multiprocessing", "threading", "marshal", "pickle",
    "sqlite3", "zipfile", "tempfile", "pathlib", "glob", "signal",
    "pty", "atexit", "gc", "weakref", "resource", "mmap",
})

_BLOCKED_CALLS = frozenset({
    "exec", "eval", "compile", "__import__", "open", "input",
    "breakpoint", "vars", "dir", "getattr", "setattr", "delattr",
    "globals", "locals", "memoryview",
})

_SAFE_BUILTINS = {
    k: getattr(builtins, k)
    for k in (
        "abs", "all", "any", "bool", "dict", "divmod", "enumerate",
        "filter", "float", "frozenset", "int", "isinstance", "issubclass",
        "iter", "len", "list", "map", "max", "min", "next", "object",
        "pow", "print", "range", "repr", "reversed", "round", "set",
        "slice", "sorted", "str", "sum", "tuple", "type", "zip",
        "True", "False", "None",
        "ValueError", "TypeError", "KeyError", "IndexError",
        "AttributeError", "StopIteration", "RuntimeError", "Exception",
    )
}


class _SecurityVisitor(ast.NodeVisitor):
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in _BLOCKED_IMPORTS:
                raise CodeSecurityError(f"Blocked import: {alias.name!r}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            parts = node.module.split(".")
            for part in parts:
                if part in _BLOCKED_IMPORTS:
                    raise CodeSecurityError(f"Blocked import: {node.module!r}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALLS:
            raise CodeSecurityError(f"Blocked call: {node.func.id!r}")
        if isinstance(node.func, ast.Attribute) and node.func.attr in _BLOCKED_CALLS:
            raise CodeSecurityError(f"Blocked attribute call: {node.func.attr!r}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Block dunder attribute access used to escape sandbox
        if node.attr.startswith("__") and node.attr.endswith("__"):
            blocked = {"__class__", "__bases__", "__subclasses__", "__globals__",
                       "__code__", "__builtins__", "__dict__", "__import__",
                       "__loader__", "__spec__", "__cached__", "__builtins__"}
            if node.attr in blocked:
                raise CodeSecurityError(f"Blocked dunder attribute: {node.attr!r}")
        self.generic_visit(node)


def validate_strategy_code(code: str) -> None:
    """Parse and walk AST; raise CodeSecurityError if unsafe constructs found."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise CodeSecurityError(f"Syntax error in strategy code: {exc}") from exc
    _SecurityVisitor().visit(tree)


def safe_exec_strategy(code: str, strategy_id: str = "unknown") -> dict[str, Any]:
    """Validate and execute strategy code in a restricted namespace.

    Returns the resulting namespace dict so caller can extract agent_fn etc.
    Raises CodeSecurityError for policy violations, SyntaxError for bad code.
    """
    validate_strategy_code(code)
    ns: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
    try:
        exec(compile(code, f"strategy_{strategy_id}", "exec"), ns)  # noqa: S102
    except CodeSecurityError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Strategy code execution failed: {exc}") from exc
    return ns
