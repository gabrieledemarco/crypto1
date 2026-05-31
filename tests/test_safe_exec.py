"""Tests for engine/safe_exec.py — sandbox security."""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.safe_exec import safe_exec_strategy, CodeSecurityError


class TestSafeExec:
    def test_valid_strategy_returns_agent_fn(self):
        # Imports are blocked at runtime by the restricted builtins namespace.
        # Valid strategy code that doesn't import works fine.
        code = """
def agent_fn(df):
    df = df.copy()
    return df
"""
        ns = safe_exec_strategy(code, strategy_id="test")
        assert "agent_fn" in ns
        assert callable(ns["agent_fn"])

    def test_import_os_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("import os", strategy_id="test")

    def test_import_sys_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("import sys", strategy_id="test")

    def test_import_subprocess_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("import subprocess", strategy_id="test")

    def test_from_os_path_import_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("from os.path import join", strategy_id="test")

    def test_exec_call_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("exec('x=1')", strategy_id="test")

    def test_eval_call_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("eval('1+1')", strategy_id="test")

    def test_dunder_class_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("x = ().__class__", strategy_id="test")

    def test_numpy_and_pandas_ast_allowed(self):
        """numpy/pandas imports pass AST validation (not in _BLOCKED_IMPORTS).

        Note: actual execution raises RuntimeError because __import__ is not in
        _SAFE_BUILTINS. The AST validator itself does NOT block these imports.
        """
        from engine.safe_exec import validate_strategy_code
        # Should not raise CodeSecurityError at AST level
        code = """
import numpy as np
import pandas as pd
def agent_fn(df):
    return df
"""
        # validate_strategy_code must pass (no CodeSecurityError)
        validate_strategy_code(code)  # would raise if blocked

    def test_empty_code_no_agent_fn(self):
        ns = safe_exec_strategy("x = 1", strategy_id="test")
        assert "agent_fn" not in ns

    def test_import_socket_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("import socket", strategy_id="test")

    def test_import_pickle_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("import pickle", strategy_id="test")

    def test_open_call_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("open('file.txt')", strategy_id="test")

    def test_dunder_globals_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("x = fn.__globals__", strategy_id="test")

    def test_syntax_error_raises_security_error(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("def broken(: pass", strategy_id="test")

    def test_valid_code_executes_correctly(self):
        """Pure Python (no imports) executes correctly in sandbox."""
        code = """
def agent_fn(df):
    df = df.copy()
    df['signal'] = 0
    df['SL_dist'] = 1.0
    df['TP_dist'] = 2.0
    return df
"""
        ns = safe_exec_strategy(code, strategy_id="test")
        assert callable(ns["agent_fn"])

    def test_from_subprocess_import_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("from subprocess import run", strategy_id="test")

    def test_dunder_subclasses_blocked(self):
        with pytest.raises(CodeSecurityError):
            safe_exec_strategy("x = object.__subclasses__()", strategy_id="test")
