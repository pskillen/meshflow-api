"""Tests for the export_traceroutes_to_neo4j management command."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError

import pytest


class TestExportTraceroutesToNeo4jCommand:
    """Cover --clear / --yes / --async flag interactions (neo4j is mocked)."""

    def test_clear_yes_runs_clear_then_export(self):
        with (
            patch(
                "traceroute_analytics.management.commands.export_traceroutes_to_neo4j.clear_all_routed_to_edges",
                return_value=7,
            ) as mock_clear,
            patch(
                "traceroute_analytics.management.commands.export_traceroutes_to_neo4j.export_all_traceroutes_to_neo4j",
                return_value={"total": 10, "exported": 10},
            ) as mock_export,
        ):
            out = StringIO()
            call_command("export_traceroutes_to_neo4j", "--clear", "--yes", stdout=out)

        mock_clear.assert_called_once()
        mock_export.assert_called_once()
        output = out.getvalue()
        assert "Cleared 7 ROUTED_TO relationships" in output
        assert "Exported 10 of 10 traceroutes" in output

    def test_clear_without_yes_prompts_and_aborts_on_no(self):
        with (
            patch(
                "traceroute_analytics.management.commands.export_traceroutes_to_neo4j.clear_all_routed_to_edges",
            ) as mock_clear,
            patch(
                "traceroute_analytics.management.commands.export_traceroutes_to_neo4j.export_all_traceroutes_to_neo4j",
            ) as mock_export,
            patch("builtins.input", return_value="no"),
        ):
            out = StringIO()
            call_command("export_traceroutes_to_neo4j", "--clear", stdout=out)

        mock_clear.assert_not_called()
        mock_export.assert_not_called()
        assert "Aborted" in out.getvalue()

    def test_clear_with_async_errors_without_touching_neo4j(self):
        with (
            patch(
                "traceroute_analytics.management.commands.export_traceroutes_to_neo4j.clear_all_routed_to_edges",
            ) as mock_clear,
            patch(
                "traceroute_analytics.management.commands.export_traceroutes_to_neo4j.export_all_traceroutes_to_neo4j",
            ) as mock_export,
        ):
            with pytest.raises(CommandError):
                call_command("export_traceroutes_to_neo4j", "--clear", "--async", "--yes")

        mock_clear.assert_not_called()
        mock_export.assert_not_called()
