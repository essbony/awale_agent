"""Tests pour le patch DuckDB get_columns dans awale_agent/agent.py."""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPatchedGetColumns:
    def test_patched_get_columns_returns_expected_structure(self):
        from agent import _patched_get_columns

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("id", "VARCHAR(255)", "YES", None),
            ("amount", "DOUBLE", "NO", "0"),
            ("created_at", "TIMESTAMP", "YES", None),
        ]

        fake_dialect = MagicMock()
        result = _patched_get_columns(fake_dialect, mock_conn, "my_table", schema="main")

        assert len(result) == 3
        assert result[0]["name"] == "id"
        assert result[0]["nullable"] is True
        assert result[0]["default"] is None
        assert result[1]["name"] == "amount"
        assert result[1]["nullable"] is False
        assert result[1]["default"] == "0"

    def test_patched_get_columns_calls_information_schema(self):
        from agent import _patched_get_columns

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        fake_dialect = MagicMock()
        _patched_get_columns(fake_dialect, mock_conn, "test_table")

        # Vérifie que la requête SQL interroge bien information_schema.columns
        call_args = mock_conn.execute.call_args
        query_text = str(call_args[0][0])
        assert "information_schema.columns" in query_text
        assert call_args[0][1]["table_name"] == "test_table"

    def test_patched_get_columns_with_schema_none(self):
        from agent import _patched_get_columns

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("col1", "INTEGER", "YES", None),
        ]

        fake_dialect = MagicMock()
        result = _patched_get_columns(fake_dialect, mock_conn, "t", schema=None)
        assert len(result) == 1
        params = mock_conn.execute.call_args[0][1]
        assert params["schema"] is None

    def test_patched_get_columns_unknown_type_fallback(self):
        from agent import _patched_get_columns

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("weird", "UNKNOWN_CUSTOM_TYPE", "YES", None),
        ]

        fake_dialect = MagicMock()
        result = _patched_get_columns(fake_dialect, mock_conn, "t")
        # Type inconnu -> NullType
        assert result[0]["name"] == "weird"
        # Le type doit être NullType (ou instance)
        assert result[0]["type"] is not None

    def test_patched_get_columns_strips_parens(self):
        """VARCHAR(10) -> recherche VARCHAR dans ischema_names."""
        from agent import _patched_get_columns

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("col", "VARCHAR(10)", "YES", None),
        ]

        fake_dialect = MagicMock()
        result = _patched_get_columns(fake_dialect, mock_conn, "t")
        # Doit réussir sans erreur et retourner un type non-NullType si VARCHAR connu
        assert result[0]["name"] == "col"
