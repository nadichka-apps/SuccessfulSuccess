"""Mailer Lambda handler.

Triggered by S3 ObjectCreated events for `reports/*.csv`, reads the CSV artifact
(read-only access), applies persistent DynamoDB email deduplication, and sends
the report as a MIME attachment via Amazon SES.
"""

import logging
import os
import urllib.parse
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import boto3

from app.config import settings
from app.reports.dedup import DeduplicationManager

logger = logging.getLogger("meetings.reports.mailer")


def create_report_email(
    sender: str,
    recipient: str,
    week: str,
    csv_bytes: bytes,
    filename: str,
) -> MIMEMultipart:
    """Build a multipart MIME email with message body and CSV attachment."""
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"[SuccessfulSuccess] Weekly Meetings Report — {week}"
    msg["From"] = sender
    msg["To"] = recipient

    body_html = f"""
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1f2937;">
        <div style="max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e5e7eb; border-radius: 12px;">
          <h2 style="color: #7d2ae8; margin-top: 0;">SuccessfulSuccess Meetings</h2>
          <p>Hello,</p>
          <p>
            Please find attached your weekly meetings summary report for <strong>{week}</strong>
            (application timezone: <code>{settings.app_timezone}</code>).
          </p>
          <div style="background-color: #f9fafb; padding: 16px; border-radius: 8px; margin: 16px 0;">
            <p style="margin: 0; font-size: 14px; color: #4b5563;">
              The attached CSV includes week-over-week meeting trends, duration analysis,
              the top 5 longest meetings, and organiser/member breakdowns.
            </p>
          </div>
          <p style="font-size: 13px; color: #6b7280; margin-bottom: 0;">
            Report file: <code>{filename}</code> ({len(csv_bytes)} bytes)
          </p>
        </div>
      </body>
    </html>
    """

    body_part = MIMEText(body_html, "html", "utf-8")
    msg.attach(body_part)

    attachment = MIMEApplication(csv_bytes, _subtype="csv")
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    return msg


def send_email_via_ses(
    sender: str,
    recipient: str,
    week: str,
    csv_bytes: bytes,
    filename: str,
    ses_client: Any = None,
) -> str:
    """Send MIME email via Amazon SES and return the MessageId."""
    client = ses_client or boto3.client("ses", region_name=settings.aws_region)
    mime_msg = create_report_email(sender, recipient, week, csv_bytes, filename)

    response = client.send_raw_email(
        Source=sender,
        Destinations=[recipient],
        RawMessage={"Data": mime_msg.as_bytes()},
    )
    message_id = response.get("MessageId", "unknown")
    logger.info(
        "Sent weekly report email to %s for %s via SES (MessageId: %s)",
        recipient,
        week,
        message_id,
    )
    return message_id


def process_report_delivery(
    bucket: str,
    key: str,
    s3_client: Any = None,
    ses_client: Any = None,
    dedup_mgr: DeduplicationManager | None = None,
    override_recipient: str | None = None,
) -> dict[str, Any]:
    """Fetch report from S3, perform deduplication, and deliver via SES."""
    if not key.startswith("reports/") or not key.endswith(".csv"):
        logger.warning("Ignoring object %s: must match reports/*.csv", key)
        return {"status": "skipped", "reason": "unmatched_key", "key": key}

    # Extract week identifier (e.g. reports/2026-W40.csv -> 2026-W40)
    filename = key.split("/")[-1]
    week = filename.removesuffix(".csv")

    sender = settings.reports_sender_email or os.environ.get("REPORTS_SENDER_EMAIL")
    recipient = (
        override_recipient
        or settings.reports_recipient_email
        or os.environ.get("REPORTS_RECIPIENT_EMAIL")
    )

    if not sender or not recipient:
        logger.warning("Missing email configuration: sender=%s, recipient=%s", sender, recipient)
        return {
            "status": "skipped",
            "reason": "missing_email_config",
            "sender": sender,
            "recipient": recipient,
            "key": key,
        }

    dedup = dedup_mgr or DeduplicationManager()

    # Attempt to acquire deduplication lock
    if not dedup.acquire_delivery_lock(key, recipient, week):
        logger.info(
            "Deduplication check: %s already delivered or currently locked for %s", key, recipient
        )
        return {
            "status": "skipped",
            "reason": "duplicate_suppressed",
            "key": key,
            "recipient": recipient,
        }

    # Fetch report from S3 (Read-Only)
    s3 = s3_client or boto3.client("s3", region_name=settings.aws_region)
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        csv_bytes = response["Body"].read()
    except Exception as exc:
        logger.error("Failed to read s3://%s/%s: %s", bucket, key, exc)
        dedup.mark_failed(key, recipient, str(exc))
        raise

    # Deliver via SES
    try:
        message_id = send_email_via_ses(
            sender, recipient, week, csv_bytes, filename, ses_client=ses_client
        )
        dedup.mark_delivered(key, recipient, message_id)
        return {
            "status": "delivered",
            "key": key,
            "recipient": recipient,
            "week": week,
            "message_id": message_id,
        }
    except Exception as exc:
        logger.error("Failed to send email via SES for %s: %s", key, exc)
        dedup.mark_failed(key, recipient, str(exc))
        raise


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for Mailer."""
    logger.info("Mailer invoked with event keys: %s", list(event.keys()))

    # Case 1: S3 Notification Event
    records = event.get("Records")
    if records and isinstance(records, list):
        results = []
        for record in records:
            s3_data = record.get("s3", {})
            bucket = s3_data.get("bucket", {}).get("name")
            key_raw = s3_data.get("object", {}).get("key", "")
            key = urllib.parse.unquote_plus(key_raw)

            logger.info(
                "Processing S3 event for s3://%s/%s (trigger: s3_object_created)", bucket, key
            )
            if bucket and key:
                res = process_report_delivery(bucket, key)
                results.append(res)

        return {"status": "ok", "processed": len(results), "deliveries": results}

    # Case 2: Direct / On-Demand Invocation
    bucket = event.get("bucket") or settings.reports_bucket_name
    key = event.get("key", "")
    override_recipient = event.get("recipient")

    logger.info("Processing direct mailer invocation for key: %s (trigger: direct_invocation)", key)
    if not bucket or not key:
        return {"status": "error", "message": "bucket and key are required for direct invocation"}

    res = process_report_delivery(bucket, key, override_recipient=override_recipient)
    return {"status": "ok", "delivery": res}
