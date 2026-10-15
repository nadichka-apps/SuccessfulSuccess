"""Unit tests for DynamoDB deduplication manager."""

import time
from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from app.reports.dedup import DeduplicationManager


def test_dedup_local_in_memory_lifecycle():
    mgr = DeduplicationManager(table_name=None)

    key = "reports/2026-W40.csv"
    # 1. First lock acquisition succeeds
    assert mgr.acquire_delivery_lock(key, "alice@example.com", "2026-W40") is True

    # 2. Duplicate active acquisition fails
    assert mgr.acquire_delivery_lock(key, "alice@example.com", "2026-W40") is False

    # 3. Different recipient succeeds
    assert mgr.acquire_delivery_lock(key, "bob@example.com", "2026-W40") is True

    # 4. Mark delivered
    mgr.mark_delivered(key, "alice@example.com", "msg-12345")
    assert mgr.acquire_delivery_lock(key, "alice@example.com", "2026-W40") is False

    # 5. Mark failed allows immediate retry
    mgr.mark_failed(key, "bob@example.com", "SES rate limit exceeded")
    assert mgr.acquire_delivery_lock(key, "bob@example.com", "2026-W40") is True


def test_dedup_stale_lock_recovery():
    mgr = DeduplicationManager(table_name=None)
    key = "reports/2026-W40.csv"
    dedup_id = f"{key}#charlie@example.com"

    # Simulate expired stale lock (lock_expiry in the past)
    mgr._local_records[dedup_id] = {
        "status": "PENDING",
        "lock_expiry": int(time.time()) - 10,
        "week": "2026-W40",
        "recipient": "charlie@example.com",
    }

    # Stale lock must be reclaimed
    assert mgr.acquire_delivery_lock(key, "charlie@example.com", "2026-W40") is True


def test_dedup_dynamodb_conditional_check_failed():
    mock_dynamo = MagicMock()
    mock_dynamo.put_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "Item exists"}},
        "PutItem",
    )

    mgr = DeduplicationManager(table_name="test-table", dynamodb_client=mock_dynamo)
    result = mgr.acquire_delivery_lock("reports/2026-W40.csv", "dave@example.com", "2026-W40")
    assert result is False
    mock_dynamo.put_item.assert_called_once()
