"""Tests for schema change detection."""

from unittest.mock import MagicMock, patch

from ingestion.ingestion import compare_schema, handle_schema_change


def test_compare_schema_detects_added_features() -> None:
    old_schema = ["age", "income", "score"]
    new_schema = ["age", "income", "score", "region"]

    added, removed = compare_schema(old_schema, new_schema)

    assert added == {"region"}
    assert removed == set()


def test_compare_schema_detects_removed_features() -> None:
    old_schema = ["age", "income", "score"]
    new_schema = ["age", "income"]

    added, removed = compare_schema(old_schema, new_schema)

    assert added == set()
    assert removed == {"score"}


def test_compare_schema_first_batch_has_only_additions() -> None:
    added, removed = compare_schema(None, ["a", "b"])

    assert added == {"a", "b"}
    assert removed == set()


@patch("ingestion.ingestion.send_slack_alert")
@patch("ingestion.ingestion.feature_removed")
@patch("ingestion.ingestion.feature_added")
def test_handle_schema_change_flags_metrics(
    mock_feature_added: MagicMock,
    mock_feature_removed: MagicMock,
    _mock_slack: MagicMock,
) -> None:
    mock_feature_added.inc = MagicMock()
    mock_feature_removed.inc = MagicMock()

    changed = handle_schema_change(added={"new_feat"}, removed={"old_feat"})

    assert changed is True
    mock_feature_added.inc.assert_called_once()
    mock_feature_removed.inc.assert_called_once()
