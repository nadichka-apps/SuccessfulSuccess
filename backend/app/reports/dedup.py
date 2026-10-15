"""Persistent concurrency-safe DynamoDB email deduplication manager."""

import logging
import time
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger("meetings.reports.dedup")

LOCK_TIMEOUT_SECONDS = 300  # 5 minutes stale lock window
RETENTION_DAYS = 90  # 90-day DynamoDB TTL


class DeduplicationManager:
    """Manages idempotent delivery states in DynamoDB to prevent duplicate email transmissions."""

    def __init__(
        self,
        table_name: str | None = None,
        dynamodb_client: Any = None,
        region_name: str | None = None,
    ):
        self.table_name = table_name or settings.reports_dedup_table
        self.region_name = region_name or settings.aws_region
        self._dynamodb = dynamodb_client
        # In-memory storage for test/offline environments when no table is configured
        self._local_records: dict[str, dict[str, Any]] = {}

    @property
    def dynamodb(self):
        if self._dynamodb is None:
            self._dynamodb = boto3.client("dynamodb", region_name=self.region_name)
        return self._dynamodb

    def acquire_delivery_lock(self, report_key: str, recipient: str, week: str) -> bool:
        """Attempt to acquire a delivery lock for (report_key, recipient).

        Returns:
            True if lock was acquired (proceed with sending).
            False if already sent or an active lock is held (skip sending).
        """
        dedup_id = f"{report_key}#{recipient}"
        now_epoch = int(time.time())
        lock_expiry = now_epoch + LOCK_TIMEOUT_SECONDS
        ttl = now_epoch + (RETENTION_DAYS * 86400)
        now_iso = datetime.now(UTC).isoformat()

        if not self.table_name:
            # Local in-memory fallback for test environments
            existing = self._local_records.get(dedup_id)
            if existing:
                if existing["status"] == "SENT":
                    logger.info("Local dedup: %s already SENT. Skipping.", dedup_id)
                    return False
                if existing["status"] == "PENDING" and existing["lock_expiry"] > now_epoch:
                    logger.info("Local dedup: %s PENDING active lock. Skipping.", dedup_id)
                    return False
            self._local_records[dedup_id] = {
                "status": "PENDING",
                "lock_expiry": lock_expiry,
                "week": week,
                "recipient": recipient,
                "created_at": now_iso,
            }
            return True

        try:
            # Conditional put: succeed only if item doesn't exist, was marked FAILED, or lock expired
            self.dynamodb.put_item(
                TableName=self.table_name,
                Item={
                    "report_key": {"S": dedup_id},
                    "base_report_key": {"S": report_key},
                    "recipient": {"S": recipient},
                    "week": {"S": week},
                    "status": {"S": "PENDING"},
                    "lock_expiry": {"N": str(lock_expiry)},
                    "ttl": {"N": str(ttl)},
                    "created_at": {"S": now_iso},
                    "updated_at": {"S": now_iso},
                },
                ConditionExpression=(
                    "attribute_not_exists(report_key) OR "
                    "#st = :failed OR "
                    "(#st = :pending AND lock_expiry < :now)"
                ),
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":failed": {"S": "FAILED"},
                    ":pending": {"S": "PENDING"},
                    ":now": {"N": str(now_epoch)},
                },
            )
            logger.info("Acquired delivery lock for %s", dedup_id)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                logger.info("Delivery already in progress or completed for %s. Skipping duplicate.", dedup_id)
                return False
            logger.error("DynamoDB error while acquiring delivery lock: %s", e)
            raise

    def mark_delivered(self, report_key: str, recipient: str, message_id: str | None = None) -> None:
        """Mark delivery as successfully completed."""
        dedup_id = f"{report_key}#{recipient}"
        now_iso = datetime.now(UTC).isoformat()

        if not self.table_name:
            if dedup_id in self._local_records:
                self._local_records[dedup_id]["status"] = "SENT"
                self._local_records[dedup_id]["message_id"] = message_id or ""
                self._local_records[dedup_id]["updated_at"] = now_iso
            return

        try:
            self.dynamodb.update_item(
                TableName=self.table_name,
                Key={"report_key": {"S": dedup_id}},
                UpdateExpression="SET #st = :sent, message_id = :mid, updated_at = :now",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":sent": {"S": "SENT"},
                    ":mid": {"S": message_id or "UNKNOWN"},
                    ":now": {"S": now_iso},
                },
            )
            logger.info("Marked %s as SENT with MessageId %s", dedup_id, message_id)
        except ClientError as e:
            logger.error("Failed to mark delivery as SENT for %s: %s", dedup_id, e)
            raise

    def mark_failed(self, report_key: str, recipient: str, error_message: str) -> None:
        """Mark delivery as failed so retries can acquire the lock immediately."""
        dedup_id = f"{report_key}#{recipient}"
        now_iso = datetime.now(UTC).isoformat()

        if not self.table_name:
            if dedup_id in self._local_records:
                self._local_records[dedup_id]["status"] = "FAILED"
                self._local_records[dedup_id]["error"] = error_message
                self._local_records[dedup_id]["updated_at"] = now_iso
            return

        try:
            self.dynamodb.update_item(
                TableName=self.table_name,
                Key={"report_key": {"S": dedup_id}},
                UpdateExpression="SET #st = :failed, error_message = :err, updated_at = :now",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":failed": {"S": "FAILED"},
                    ":err": {"S": error_message[:1000]},
                    ":now": {"S": now_iso},
                },
            )
            logger.warning("Marked %s as FAILED: %s", dedup_id, error_message)
        except ClientError as e:
            logger.error("Failed to mark delivery as FAILED for %s: %s", dedup_id, e)
