"""Unit tests for Report Builder Lambda handler."""

import json
from unittest.mock import MagicMock, patch

from app.reports.builder import (
    get_previous_completed_iso_week,
    handler,
    resolve_report_week,
    upload_report_to_s3,
)


def test_get_previous_completed_iso_week_format():
    prev_week = get_previous_completed_iso_week()
    assert len(prev_week) == 8
    assert prev_week[4:6] == "-W"
    year = int(prev_week[:4])
    week = int(prev_week[6:])
    assert 2020 <= year <= 2030
    assert 1 <= week <= 53


def test_resolve_report_week_explicit_vs_default():
    assert resolve_report_week({"week": "2026-W35"}) == "2026-W35"
    assert resolve_report_week(None) == get_previous_completed_iso_week()
    assert resolve_report_week({}) == get_previous_completed_iso_week()


def test_upload_report_to_s3_exact_key():
    mock_s3 = MagicMock()
    csv_bytes = b"header\n1,2,3"

    key = upload_report_to_s3(csv_bytes, "2026-W40", bucket_name="test-bucket", s3_client=mock_s3)
    assert key == "reports/2026-W40.csv"

    mock_s3.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="reports/2026-W40.csv",
        Body=csv_bytes,
        ContentType="text/csv; charset=utf-8",
        Metadata={"week": "2026-W40"},
    )


@patch("app.reports.builder.upload_report_to_s3", return_value="reports/2026-W40.csv")
@patch("app.reports.builder.build_weekly_report", return_value=b"test_csv_bytes")
def test_handler_sqs_event(mock_build, mock_upload):
    sqs_event = {
        "Records": [
            {
                "messageId": "msg-999",
                "body": json.dumps({"week": "2026-W40"}),
            }
        ]
    }

    result = handler(sqs_event)
    assert result["status"] == "ok"
    assert result["processed"] == 1
    assert result["records"][0]["week"] == "2026-W40"
    assert result["records"][0]["s3_key"] == "reports/2026-W40.csv"
    mock_build.assert_called_once_with("2026-W40")


@patch("app.reports.builder.upload_report_to_s3", return_value="reports/2026-W40.csv")
@patch("app.reports.builder.build_weekly_report", return_value=b"test_csv_bytes")
def test_handler_direct_invocation(mock_build, mock_upload):
    direct_event = {"week": "2026-W40"}
    result = handler(direct_event)

    assert result["status"] == "ok"
    assert result["trigger_type"] == "direct_invocation"
    assert result["week"] == "2026-W40"
    assert result["s3_key"] == "reports/2026-W40.csv"
