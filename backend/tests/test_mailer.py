"""Unit tests for Mailer Lambda handler."""

import io
from unittest.mock import MagicMock, patch

from app.reports.dedup import DeduplicationManager
from app.reports.mailer import (
    create_report_email,
    handler,
    process_report_delivery,
)


def test_create_report_email_mime_structure():
    msg = create_report_email(
        sender="reports@example.com",
        recipient="user@example.com",
        week="2026-W40",
        csv_bytes=b"sample,csv,data",
        filename="weekly_report_2026-W40.csv",
    )

    assert msg["Subject"] == "[SuccessfulSuccess] Weekly Meetings Report — 2026-W40"
    assert msg["From"] == "reports@example.com"
    assert msg["To"] == "user@example.com"

    # Verify attachment is present
    payloads = msg.get_payload()
    assert len(payloads) == 2
    attachment = payloads[1]
    assert attachment.get_filename() == "weekly_report_2026-W40.csv"
    assert attachment.get_payload(decode=True) == b"sample,csv,data"


def test_process_report_delivery_skips_unmatched_key():
    res = process_report_delivery("test-bucket", "documents/notes.txt")
    assert res["status"] == "skipped"
    assert res["reason"] == "unmatched_key"


def test_process_report_delivery_success():
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": io.BytesIO(b"col1,col2\nval1,val2")}

    mock_ses = MagicMock()
    mock_ses.send_raw_email.return_value = {"MessageId": "ses-msg-12345"}
    dedup = DeduplicationManager(table_name=None)

    env_patch = {
        "REPORTS_SENDER_EMAIL": "sender@example.com",
        "REPORTS_RECIPIENT_EMAIL": "recipient@example.com",
    }
    with patch.dict("os.environ", env_patch):
        res = process_report_delivery(
            bucket="test-bucket",
            key="reports/2026-W40.csv",
            s3_client=mock_s3,
            ses_client=mock_ses,
            dedup_mgr=dedup,
        )

    assert res["status"] == "delivered"
    assert res["message_id"] == "ses-msg-12345"
    assert res["week"] == "2026-W40"
    mock_s3.get_object.assert_called_once_with(Bucket="test-bucket", Key="reports/2026-W40.csv")
    mock_ses.send_raw_email.assert_called_once()


def test_process_report_delivery_suppresses_duplicate():
    mock_s3 = MagicMock()
    mock_ses = MagicMock()
    dedup = DeduplicationManager(table_name=None)
    # Pre-populate lock as already SENT
    dedup._local_records["reports/2026-W40.csv#recipient@example.com"] = {
        "status": "SENT",
        "lock_expiry": 9999999999,
        "week": "2026-W40",
    }

    env_patch = {
        "REPORTS_SENDER_EMAIL": "sender@example.com",
        "REPORTS_RECIPIENT_EMAIL": "recipient@example.com",
    }
    with patch.dict("os.environ", env_patch):
        res = process_report_delivery(
            bucket="test-bucket",
            key="reports/2026-W40.csv",
            s3_client=mock_s3,
            ses_client=mock_ses,
            dedup_mgr=dedup,
        )

    assert res["status"] == "skipped"
    assert res["reason"] == "duplicate_suppressed"
    mock_s3.get_object.assert_not_called()
    mock_ses.send_raw_email.assert_not_called()


@patch("app.reports.mailer.process_report_delivery")
def test_handler_s3_notification_event(mock_process):
    mock_process.return_value = {"status": "delivered", "message_id": "msg-001"}

    s3_event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "reports-bucket"},
                    "object": {"key": "reports/2026-W40.csv"},
                },
            }
        ]
    }

    result = handler(s3_event)
    assert result["status"] == "ok"
    assert result["processed"] == 1
    mock_process.assert_called_once_with("reports-bucket", "reports/2026-W40.csv")
