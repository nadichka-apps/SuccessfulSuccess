"""Unit and integration tests for weekly meetings report generator."""

import csv
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models import Meeting, Participant, User
from app.reports.weekly import (
    build_weekly_report,
    build_weekly_report_async,
    calculate_allocated_duration,
    parse_iso_week,
    previous_iso_week,
    week_window,
)

KYIV = ZoneInfo("Europe/Kyiv")


def test_parse_iso_week_valid():
    assert parse_iso_week("2026-W40") == (2026, 40)
    assert parse_iso_week("2026-W01") == (2026, 1)
    assert parse_iso_week("2020-W53") == (2020, 53)  # 2020 has 53 ISO weeks


@pytest.mark.parametrize(
    "invalid_input",
    [
        "",
        "   ",
        "2026-40",
        "2026-W0",
        "2026-W00",
        "2026-W54",
        "2021-W53",  # 2021 has only 52 weeks
        "W40-2026",
        "random-string",
        12345,
        None,
    ],
)
def test_parse_iso_week_invalid(invalid_input):
    with pytest.raises(ValueError):
        parse_iso_week(invalid_input)


def test_previous_iso_week_calculation():
    # Normal in-year previous week
    assert previous_iso_week(2026, 40) == (2026, 39, "2026-W39")
    # Year boundary: 2026-W01 follows 2025-W52
    assert previous_iso_week(2026, 1) == (2025, 52, "2025-W52")
    # Year boundary after 53-week year: 2021-W01 follows 2020-W53
    assert previous_iso_week(2021, 1) == (2020, 53, "2020-W53")


def test_week_window_boundaries():
    start_dt, end_dt = week_window(2026, 40, KYIV)
    # 2026-W40 starts on Monday 2026-09-28 00:00:00 Kyiv
    assert start_dt.year == 2026
    assert start_dt.month == 9
    assert start_dt.day == 28
    assert start_dt.hour == 0
    assert start_dt.minute == 0
    assert start_dt.tzinfo == KYIV

    # Ends on Monday 2026-10-05 00:00:00 Kyiv
    assert end_dt.year == 2026
    assert end_dt.month == 10
    assert end_dt.day == 5
    assert end_dt.hour == 0
    assert (end_dt - start_dt) == timedelta(days=7)


def test_calculate_allocated_duration_clamping():
    win_start = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
    win_end = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)

    # Completely inside window (60 min)
    m_start = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
    m_end = datetime(2026, 9, 28, 11, 0, tzinfo=UTC)
    assert calculate_allocated_duration(m_start, m_end, win_start, win_end) == 60.0

    # Crossing start boundary: starts 30 min before, ends 30 min after -> 30 min inside
    m_start = datetime(2026, 9, 27, 23, 30, tzinfo=UTC)
    m_end = datetime(2026, 9, 28, 0, 30, tzinfo=UTC)
    assert calculate_allocated_duration(m_start, m_end, win_start, win_end) == 30.0

    # Crossing end boundary: starts 30 min before end, ends 30 min after -> 30 min inside
    m_start = datetime(2026, 10, 4, 23, 30, tzinfo=UTC)
    m_end = datetime(2026, 10, 5, 0, 30, tzinfo=UTC)
    assert calculate_allocated_duration(m_start, m_end, win_start, win_end) == 30.0


async def test_empty_week_report(session):
    report_bytes = await build_weekly_report_async("2026-W40", session=session)
    assert isinstance(report_bytes, bytes)
    text = report_bytes.decode("utf-8")

    assert "# REPORT METADATA" in text
    assert "# WEEK-OVER-WEEK SUMMARY" in text
    assert "# TOP 5 LONGEST MEETINGS" in text
    assert "# ORGANISER BREAKDOWN" in text
    assert "# MEMBER BREAKDOWN" in text

    reader = list(csv.reader(text.splitlines()))
    # Check that metadata section has week 2026-W40
    assert any(row and row[0] == "Report Week" and row[1] == "2026-W40" for row in reader)
    # Check total meetings is 0
    assert any(row and row[0] == "Total Meetings" and row[1] == "0" for row in reader)


async def test_week_over_week_metrics_and_deltas(session):
    # Setup test organiser
    user = User(id="user-org-1", email="organizer@example.com", name="Alex Organizer")
    session.add(user)
    await session.commit()

    # Week 2026-W39 window: 2026-09-21 to 2026-09-28
    # Week 2026-W40 window: 2026-09-28 to 2026-10-05

    # 1 meeting in W39 (60 min, 2 participants)
    m_prev = Meeting(
        owner_id="user-org-1",
        name="Sprint Review W39",
        starts_at=datetime(2026, 9, 22, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 9, 22, 11, 0, tzinfo=UTC),
        participants=[
            Participant(name="Alice", email="alice@example.com", position=0),
            Participant(name="Bob", email="bob@example.com", position=1),
        ],
    )
    session.add(m_prev)

    # 2 meetings in W40 (60 min each, 3 participants total)
    m_curr_1 = Meeting(
        owner_id="user-org-1",
        name="Sprint Planning W40",
        starts_at=datetime(2026, 9, 29, 9, 0, tzinfo=UTC),
        ends_at=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
        participants=[
            Participant(name="Alice", email="alice@example.com", position=0),
            Participant(name="Charlie", email="charlie@example.com", position=1),
        ],
    )
    m_curr_2 = Meeting(
        owner_id="user-org-1",
        name="Architecture Review W40",
        starts_at=datetime(2026, 9, 30, 14, 0, tzinfo=UTC),
        ends_at=datetime(2026, 9, 30, 15, 0, tzinfo=UTC),
        participants=[
            Participant(name="Alice", email="alice@example.com", position=0),
        ],
    )
    session.add_all([m_curr_1, m_curr_2])
    await session.commit()

    report_bytes = await build_weekly_report_async("2026-W40", session=session)
    text = report_bytes.decode("utf-8")
    rows = list(csv.reader(text.splitlines()))

    # Find Total Meetings row
    tm_row = next(r for r in rows if r and r[0] == "Total Meetings")
    assert tm_row[1] == "2"  # Selected week count
    assert tm_row[2] == "1"  # Previous week count
    assert tm_row[3] == "+1"  # Absolute change
    assert "+100.0%" in tm_row[4]  # Percentage change

    # Find Total Duration (Minutes)
    td_row = next(r for r in rows if r and r[0] == "Total Duration (Minutes)")
    assert td_row[1] == "120.0"
    assert td_row[2] == "60.0"
    assert td_row[3] == "+60.0"

    # Find Unique Participants
    up_row = next(r for r in rows if r and r[0] == "Unique Participants")
    assert up_row[1] == "2"  # Alice and Charlie
    assert up_row[2] == "2"  # Alice and Bob


async def test_meeting_spanning_week_boundary(session):
    start_dt, end_dt = week_window(2026, 40, KYIV)
    # start_dt is 2026-09-28 00:00:00 Kyiv (2026-09-27 21:00:00 UTC)
    boundary_utc = start_dt.astimezone(UTC)

    # Meeting starts 45 minutes before boundary and ends 45 minutes after boundary (90 min total)
    spanning_meeting = Meeting(
        name="Overnight Sync",
        starts_at=boundary_utc - timedelta(minutes=45),
        ends_at=boundary_utc + timedelta(minutes=45),
        participants=[Participant(name="Dev", email="dev@example.com", position=0)],
    )
    session.add(spanning_meeting)
    await session.commit()

    # Selected week: 2026-W40 (starts at boundary)
    report_w40 = await build_weekly_report_async("2026-W40", session=session)
    rows_w40 = list(csv.reader(report_w40.decode("utf-8").splitlines()))

    tm_row_w40 = next(r for r in rows_w40 if r and r[0] == "Total Meetings")
    assert tm_row_w40[1] == "1"  # Counted in W40
    assert tm_row_w40[2] == "1"  # Also counted in previous week (W39)

    td_row_w40 = next(r for r in rows_w40 if r and r[0] == "Total Duration (Minutes)")
    assert td_row_w40[1] == "45.0"  # Exactly 45 min allocated to W40
    assert td_row_w40[2] == "45.0"  # Exactly 45 min allocated to W39


async def test_top_5_longest_meetings(session):
    start_dt, _ = week_window(2026, 40, KYIV)
    base_utc = start_dt.astimezone(UTC) + timedelta(days=1)

    # Insert 6 meetings with durations: 10, 20, 30, 40, 50, 60 minutes
    for i in [10, 20, 30, 40, 50, 60]:
        session.add(
            Meeting(
                name=f"Meeting {i}m",
                starts_at=base_utc + timedelta(hours=i // 10),
                ends_at=base_utc + timedelta(hours=i // 10, minutes=i),
            )
        )
    await session.commit()

    report = await build_weekly_report_async("2026-W40", session=session)
    rows = list(csv.reader(report.decode("utf-8").splitlines()))

    top5_idx = next(i for i, r in enumerate(rows) if r and r[0] == "# TOP 5 LONGEST MEETINGS")
    # Header is at top5_idx + 1, data rows are top5_idx + 2 to top5_idx + 6
    top5_names = [rows[top5_idx + 2 + j][1] for j in range(5)]
    assert top5_names == [
        "Meeting 60m",
        "Meeting 50m",
        "Meeting 40m",
        "Meeting 30m",
        "Meeting 20m",
    ]
    # Meeting 10m is excluded from top 5
    assert "Meeting 10m" not in top5_names


async def test_organiser_and_member_breakdowns(session):
    user1 = User(id="org-1", name="Sarah Connor", email="sarah@resistance.org")
    user2 = User(id="org-2", name="John Connor", email="john@resistance.org")
    session.add_all([user1, user2])
    await session.commit()

    start_dt, _ = week_window(2026, 40, KYIV)
    base_utc = start_dt.astimezone(UTC) + timedelta(days=2)

    m1 = Meeting(
        owner_id="org-1",
        name="Tactical Briefing",
        starts_at=base_utc,
        ends_at=base_utc + timedelta(minutes=60),
        participants=[
            Participant(name="Kyle Reese", email="kyle@resistance.org", position=0),
            Participant(name="Marcus Wright", email=None, position=1),
        ],
    )
    m2 = Meeting(
        owner_id="org-2",
        name="Logistics",
        starts_at=base_utc + timedelta(hours=2),
        ends_at=base_utc + timedelta(hours=2, minutes=30),
        participants=[
            Participant(name="Kyle Reese", email="kyle@resistance.org", position=0),
        ],
    )
    session.add_all([m1, m2])
    await session.commit()

    report = await build_weekly_report_async("2026-W40", session=session)
    rows = list(csv.reader(report.decode("utf-8").splitlines()))

    # Check Organisers
    org_idx = next(i for i, r in enumerate(rows) if r and r[0] == "# ORGANISER BREAKDOWN")
    org_rows = [rows[org_idx + 2], rows[org_idx + 3]]
    assert any(r[0] == "Sarah Connor" and r[2] == "1" and r[3] == "60.0" for r in org_rows)
    assert any(r[0] == "John Connor" and r[2] == "1" and r[3] == "30.0" for r in org_rows)

    # Check Members (Kyle Reese attended 2 meetings for 90 total minutes)
    mem_idx = next(i for i, r in enumerate(rows) if r and r[0] == "# MEMBER BREAKDOWN")
    kyle_row = next(r for r in rows[mem_idx + 2 :] if r and r[0] == "Kyle Reese")
    assert kyle_row[1] == "kyle@resistance.org"
    assert kyle_row[2] == "2"  # 2 meetings attended
    assert kyle_row[3] == "90.0"  # 90.0 total minutes


async def test_build_weekly_report_sync_and_async_invocations(session):
    # Test that build_weekly_report returns bytes and can be awaited or read directly
    res_sync = build_weekly_report("2026-W40")
    assert isinstance(res_sync, bytes)
    assert b"# REPORT METADATA" in res_sync

    res_async = await build_weekly_report("2026-W40")
    assert isinstance(res_async, bytes)
    assert b"# REPORT METADATA" in res_async
