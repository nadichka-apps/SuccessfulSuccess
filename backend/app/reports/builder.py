"""Report Builder Lambda handler.

Consumes SQS messages or direct invocation payloads, builds the weekly meetings
report CSV, and uploads it to S3 at `reports/{week}.csv` via the S3 Gateway VPC endpoint.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import boto3

from app.config import settings
from app.reports.weekly import build_weekly_report, parse_iso_week

logger = logging.getLogger("meetings.reports.builder")


def get_previous_completed_iso_week() -> str:
    """Return the previous completed ISO week string (e.g. '2026-W40') in Europe/Kyiv."""
    now = datetime.now(settings.tz)
    # The week completed prior to the current Monday was active 7 days ago
    completed_date = now.date() - timedelta(days=7)
    year, week, _ = completed_date.isocalendar()
    return f"{year:04d}-W{week:02d}"


def resolve_report_week(payload: dict[str, Any] | None) -> str:
    """Resolve target ISO week from incoming payload or default to previous completed week."""
    if not payload:
        return get_previous_completed_iso_week()

    week_param = payload.get("week")
    if week_param and isinstance(week_param, str):
        # Validate format
        parse_iso_week(week_param)
        return week_param.strip()

    return get_previous_completed_iso_week()


def upload_report_to_s3(
    csv_bytes: bytes,
    week: str,
    bucket_name: str | None = None,
    s3_client: Any = None,
) -> str:
    """Upload the weekly CSV report to S3 at `reports/{week}.csv` (idempotent overwrite)."""
    bucket = bucket_name or settings.reports_bucket_name
    if not bucket:
        raise ValueError("REPORTS_BUCKET_NAME is not configured")

    client = s3_client or boto3.client("s3", region_name=settings.aws_region)
    key = f"reports/{week}.csv"

    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=csv_bytes,
        ContentType="text/csv; charset=utf-8",
        Metadata={"week": week},
    )
    logger.info("Uploaded weekly report to s3://%s/%s (%d bytes)", bucket, key, len(csv_bytes))
    return key


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for Report Builder."""
    logger.info("Report Builder invoked with event keys: %s", list(event.keys()))

    # Case 1: SQS Event
    records = event.get("Records")
    if records and isinstance(records, list):
        results = []
        for record in records:
            message_id = record.get("messageId", "unknown")
            body_raw = record.get("body", "{}")
            logger.info("Processing SQS message %s (trigger_type: sqs)", message_id)

            payload = {}
            if body_raw:
                try:
                    payload = json.loads(body_raw)
                except json.JSONDecodeError:
                    # Treat non-JSON body as potential week string
                    payload = {"week": body_raw.strip()}

            target_week = resolve_report_week(payload)
            logger.info(
                "Building report for week %s (trigger: sqs, message_id: %s)",
                target_week,
                message_id,
            )

            csv_bytes = build_weekly_report(target_week)
            s3_key = upload_report_to_s3(csv_bytes, target_week)
            results.append({"message_id": message_id, "week": target_week, "s3_key": s3_key})

        return {"status": "ok", "processed": len(results), "records": results}

    # Case 2: Direct Invocation or Scheduled Event
    trigger_type = "scheduled" if event.get("source") == "aws.scheduler" else "direct_invocation"
    target_week = resolve_report_week(event)
    logger.info("Building report for week %s (trigger_type: %s)", target_week, trigger_type)

    csv_bytes = build_weekly_report(target_week)
    s3_key = upload_report_to_s3(csv_bytes, target_week)

    return {
        "status": "ok",
        "trigger_type": trigger_type,
        "week": target_week,
        "s3_key": s3_key,
        "bucket": settings.reports_bucket_name,
    }
