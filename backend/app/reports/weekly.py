"""Weekly meetings report generator producing structured CSV output."""

import asyncio
import csv
import io
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionFactory
from app.models import Meeting, User

ISO_WEEK_PATTERN = re.compile(r"^(\d{4})-W(0[1-9]|[1-4]\d|5[0-3])$")


class CoroutineOrBytes(bytes):
    """A bytes subclass that can be awaited if called in an async context."""

    def __new__(cls, data: bytes = b"", coro: Any = None):
        instance = super().__new__(cls, data)
        instance._coro = coro
        return instance

    def __await__(self):
        if self._coro is not None:
            return self._coro.__await__()

        async def _ret():
            return bytes(self)

        return _ret().__await__()


def parse_iso_week(week: str) -> tuple[int, int]:
    """Validate and parse an ISO week string (e.g. '2026-W40').

    Raises:
        ValueError: If the format is invalid or week number does not exist in the year.
    """
    if not isinstance(week, str):
        raise ValueError(f"Week must be a string, got {type(week).__name__}")

    stripped = week.strip()
    match = ISO_WEEK_PATTERN.match(stripped)
    if not match:
        raise ValueError(
            f"Invalid ISO week format '{week}'. Expected format 'YYYY-Www', e.g. '2026-W40'."
        )

    year = int(match.group(1))
    week_num = int(match.group(2))

    try:
        # Validates that week_num is valid for the given ISO calendar year
        date.fromisocalendar(year, week_num, 1)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO week '{week}': {exc}") from exc

    return year, week_num


def week_window(year: int, week: int, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Return [start, end) datetime boundaries for an ISO week in the given timezone.

    ISO weeks run Monday 00:00:00 to Sunday 23:59:59.999999 (exclusive end is next Monday 00:00:00).
    """
    monday = date.fromisocalendar(year, week, 1)
    next_monday = monday + timedelta(days=7)

    start_dt = datetime.combine(monday, time.min, tzinfo=tz)
    end_dt = datetime.combine(next_monday, time.min, tzinfo=tz)
    return start_dt, end_dt


def previous_iso_week(year: int, week: int) -> tuple[int, int, str]:
    """Return (year, week_num, 'YYYY-Www') for the preceding ISO week."""
    curr_monday = date.fromisocalendar(year, week, 1)
    prev_monday = curr_monday - timedelta(days=7)
    p_year, p_week, _ = prev_monday.isocalendar()
    return p_year, p_week, f"{p_year:04d}-W{p_week:02d}"


def format_percentage_change(current: float, previous: float) -> str:
    """Format the percentage difference between two metrics."""
    if previous == 0.0:
        if current == 0.0:
            return "0.0%"
        return "+100.0%"
    change = ((current - previous) / previous) * 100.0
    return f"{change:+.1f}%"


def calculate_allocated_duration(
    starts_at: datetime, ends_at: datetime, window_start: datetime, window_end: datetime
) -> float:
    """Allocate the portion of meeting duration falling strictly in the window (minutes)."""
    clipped_start = max(starts_at, window_start)
    clipped_end = min(ends_at, window_end)
    return max(0.0, (clipped_end - clipped_start).total_seconds() / 60.0)


async def _fetch_week_data(
    session: AsyncSession, start_utc: datetime, end_utc: datetime
) -> tuple[list[Meeting], dict[str, User]]:
    """Query meetings overlapping the window and eager-load participants and owners."""
    stmt = (
        select(Meeting)
        .options(selectinload(Meeting.participants))
        .where(Meeting.starts_at < end_utc, Meeting.ends_at > start_utc)
        .order_by(Meeting.starts_at.asc(), Meeting.name.asc())
    )
    result = await session.scalars(stmt)
    meetings = list(result.all())

    owner_ids = {m.owner_id for m in meetings if m.owner_id}
    users_by_id: dict[str, User] = {}
    if owner_ids:
        users_stmt = select(User).where(User.id.in_(owner_ids))
        users_result = await session.scalars(users_stmt)
        users_by_id = {u.id: u for u in users_result.all()}

    return meetings, users_by_id


def _run_in_isolated_loop(coro_fn, *args):
    """Run an async database operation in an isolated event loop and thread."""
    async def _runner():
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        isolated_engine = create_async_engine(settings.database_url, poolclass=NullPool)
        isolated_sessionmaker = async_sessionmaker(
            isolated_engine, expire_on_commit=False, autoflush=False
        )
        try:
            async with isolated_sessionmaker() as session:
                return await coro_fn(*args, session=session)
        finally:
            await isolated_engine.dispose()

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _runner()).result()


async def build_weekly_report_async(
    week: str, session: AsyncSession | None = None
) -> bytes:
    """Generate the weekly meetings report CSV bytes asynchronously."""
    if session is not None:
        return await _generate_report(week, session)

    async with SessionFactory() as new_session:
        return await _generate_report(week, new_session)


def build_weekly_report(week: str, session: AsyncSession | None = None) -> bytes:
    """Build the weekly report CSV bytes for the specified ISO week (e.g. '2026-W40').

    Can be invoked synchronously or awaited in async contexts.
    """
    if session is not None:
        return CoroutineOrBytes(coro=build_weekly_report_async(week, session))

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Inside an existing event loop: run with isolated engine in worker thread
        data = _run_in_isolated_loop(_generate_report, week)
        return CoroutineOrBytes(data)

    data = asyncio.run(build_weekly_report_async(week))
    return CoroutineOrBytes(data)


async def _generate_report(week: str, session: AsyncSession) -> bytes:
    """Core report computation and CSV serialization."""
    year, week_num = parse_iso_week(week)
    tz = settings.tz

    # Window definitions
    start_tz, end_tz = week_window(year, week_num, tz)
    start_utc = start_tz.astimezone(UTC)
    end_utc = end_tz.astimezone(UTC)

    prev_year, prev_week_num, prev_week_str = previous_iso_week(year, week_num)
    prev_start_tz, prev_end_tz = week_window(prev_year, prev_week_num, tz)
    prev_start_utc = prev_start_tz.astimezone(UTC)
    prev_end_utc = prev_end_tz.astimezone(UTC)

    # Fetch data for selected week and previous week
    meetings, users_by_id = await _fetch_week_data(session, start_utc, end_utc)
    prev_meetings, _ = await _fetch_week_data(session, prev_start_utc, prev_end_utc)

    # 1. Compute Selected Week Metrics
    sel_count = len(meetings)
    sel_dur_m = sum(
        calculate_allocated_duration(m.starts_at, m.ends_at, start_utc, end_utc)
        for m in meetings
    )
    sel_dur_h = sel_dur_m / 60.0
    sel_avg_dur_m = (sel_dur_m / sel_count) if sel_count > 0 else 0.0

    sel_attendance = sum(len(m.participants) for m in meetings)
    sel_avg_attendance = (sel_attendance / sel_count) if sel_count > 0 else 0.0

    sel_unique_parts = {
        (p.name.strip().lower(), (p.email or "").strip().lower())
        for m in meetings
        for p in m.participants
    }
    sel_unique_count = len(sel_unique_parts)

    # 2. Compute Previous Week Metrics
    prev_count = len(prev_meetings)
    prev_dur_m = sum(
        calculate_allocated_duration(m.starts_at, m.ends_at, prev_start_utc, prev_end_utc)
        for m in prev_meetings
    )
    prev_dur_h = prev_dur_m / 60.0
    prev_avg_dur_m = (prev_dur_m / prev_count) if prev_count > 0 else 0.0

    prev_attendance = sum(len(m.participants) for m in prev_meetings)
    prev_avg_attendance = (prev_attendance / prev_count) if prev_count > 0 else 0.0

    prev_unique_parts = {
        (p.name.strip().lower(), (p.email or "").strip().lower())
        for m in prev_meetings
        for p in m.participants
    }
    prev_unique_count = len(prev_unique_parts)

    # 3. Top 5 Longest Meetings (ordered by total scheduled duration)
    top_5 = sorted(
        meetings,
        key=lambda m: ((m.ends_at - m.starts_at).total_seconds(), -m.starts_at.timestamp()),
        reverse=True,
    )[:5]

    # 4. Organiser Breakdown
    organiser_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "name": "Unassigned",
            "email": "",
            "meetings_count": 0,
            "total_duration_minutes": 0.0,
            "unique_participants": set(),
        }
    )

    for m in meetings:
        org_id = m.owner_id or "unassigned"
        user = users_by_id.get(m.owner_id) if m.owner_id else None
        name = "Unassigned"
        email = ""
        if user:
            name = user.name or user.email or user.id
            email = user.email or ""
        elif m.owner_id:
            name = m.owner_id

        stats = organiser_map[org_id]
        stats["name"] = name
        stats["email"] = email
        stats["meetings_count"] += 1
        stats["total_duration_minutes"] += calculate_allocated_duration(
            m.starts_at, m.ends_at, start_utc, end_utc
        )
        for p in m.participants:
            part_key = (p.name.strip().lower(), (p.email or "").strip().lower())
            stats["unique_participants"].add(part_key)

    sorted_organisers = sorted(
        organiser_map.values(),
        key=lambda o: (o["meetings_count"], o["total_duration_minutes"]),
        reverse=True,
    )

    # 5. Member / Participant Breakdown
    member_map: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "name": "",
            "email": "",
            "meetings_count": 0,
            "total_duration_minutes": 0.0,
        }
    )

    for m in meetings:
        dur = calculate_allocated_duration(m.starts_at, m.ends_at, start_utc, end_utc)
        for p in m.participants:
            pkey = (p.name.strip(), (p.email or "").strip())
            m_stat = member_map[pkey]
            m_stat["name"] = p.name.strip()
            m_stat["email"] = (p.email or "").strip()
            m_stat["meetings_count"] += 1
            m_stat["total_duration_minutes"] += dur

    sorted_members = sorted(
        member_map.values(),
        key=lambda m: (m["meetings_count"], m["total_duration_minutes"]),
        reverse=True,
    )

    # Serialize to CSV
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    now_utc = datetime.now(UTC)
    now_local = now_utc.astimezone(tz)

    # Section 1: Metadata
    writer.writerow(["# REPORT METADATA"])
    writer.writerow(["Report Week", week])
    writer.writerow(["Previous Week", prev_week_str])
    writer.writerow(["Timezone", settings.app_timezone])
    writer.writerow(["Week Start (Local)", start_tz.isoformat()])
    writer.writerow(["Week End (Local)", end_tz.isoformat()])
    writer.writerow(["Generated At (UTC)", now_utc.isoformat()])
    writer.writerow(["Generated At (Local)", now_local.isoformat()])
    writer.writerow([])

    # Section 2: Week-over-Week Metrics
    writer.writerow(["# WEEK-OVER-WEEK SUMMARY"])
    writer.writerow(
        [
            "Metric",
            f"Selected Week ({week})",
            f"Previous Week ({prev_week_str})",
            "Absolute Change",
            "Percentage Change",
        ]
    )

    metrics_rows = [
        (
            "Total Meetings",
            f"{sel_count}",
            f"{prev_count}",
            f"{sel_count - prev_count:+d}",
            format_percentage_change(sel_count, prev_count),
        ),
        (
            "Total Duration (Hours)",
            f"{sel_dur_h:.2f}",
            f"{prev_dur_h:.2f}",
            f"{sel_dur_h - prev_dur_h:+.2f}",
            format_percentage_change(sel_dur_h, prev_dur_h),
        ),
        (
            "Total Duration (Minutes)",
            f"{sel_dur_m:.1f}",
            f"{prev_dur_m:.1f}",
            f"{sel_dur_m - prev_dur_m:+.1f}",
            format_percentage_change(sel_dur_m, prev_dur_m),
        ),
        (
            "Average Meeting Duration (Minutes)",
            f"{sel_avg_dur_m:.1f}",
            f"{prev_avg_dur_m:.1f}",
            f"{sel_avg_dur_m - prev_avg_dur_m:+.1f}",
            format_percentage_change(sel_avg_dur_m, prev_avg_dur_m),
        ),
        (
            "Total Participant Attendance",
            f"{sel_attendance}",
            f"{prev_attendance}",
            f"{sel_attendance - prev_attendance:+d}",
            format_percentage_change(sel_attendance, prev_attendance),
        ),
        (
            "Average Participants Per Meeting",
            f"{sel_avg_attendance:.2f}",
            f"{prev_avg_attendance:.2f}",
            f"{sel_avg_attendance - prev_avg_attendance:+.2f}",
            format_percentage_change(sel_avg_attendance, prev_avg_attendance),
        ),
        (
            "Unique Participants",
            f"{sel_unique_count}",
            f"{prev_unique_count}",
            f"{sel_unique_count - prev_unique_count:+d}",
            format_percentage_change(sel_unique_count, prev_unique_count),
        ),
    ]
    for row in metrics_rows:
        writer.writerow(row)
    writer.writerow([])

    # Section 3: Top 5 Longest Meetings
    writer.writerow(["# TOP 5 LONGEST MEETINGS"])
    writer.writerow(
        [
            "Rank",
            "Meeting Name",
            f"Start Time ({settings.app_timezone})",
            f"End Time ({settings.app_timezone})",
            "Duration (Minutes)",
            "Organiser",
            "Participant Count",
        ]
    )

    if not top_5:
        writer.writerow(["None", "No meetings scheduled", "", "", "", "", ""])
    else:
        for idx, m in enumerate(top_5, start=1):
            dur_m = (m.ends_at - m.starts_at).total_seconds() / 60.0
            user = users_by_id.get(m.owner_id) if m.owner_id else None
            org_display = "Unassigned"
            if user:
                org_display = user.name or user.email or user.id
            elif m.owner_id:
                org_display = m.owner_id

            writer.writerow(
                [
                    idx,
                    m.name,
                    m.starts_at.astimezone(tz).isoformat(),
                    m.ends_at.astimezone(tz).isoformat(),
                    f"{dur_m:.1f}",
                    org_display,
                    len(m.participants),
                ]
            )
    writer.writerow([])

    # Section 4: Organiser Breakdown
    writer.writerow(["# ORGANISER BREAKDOWN"])
    writer.writerow(
        [
            "Organiser Name",
            "Email",
            "Meetings Count",
            "Total Duration (Minutes)",
            "Total Duration (Hours)",
            "Unique Participants",
        ]
    )

    if not sorted_organisers:
        writer.writerow(["None", "", "0", "0.0", "0.00", "0"])
    else:
        for org in sorted_organisers:
            dur_m = org["total_duration_minutes"]
            writer.writerow(
                [
                    org["name"],
                    org["email"],
                    org["meetings_count"],
                    f"{dur_m:.1f}",
                    f"{dur_m / 60.0:.2f}",
                    len(org["unique_participants"]),
                ]
            )
    writer.writerow([])

    # Section 5: Member Breakdown
    writer.writerow(["# MEMBER BREAKDOWN"])
    writer.writerow(
        [
            "Member Name",
            "Email",
            "Meetings Attended",
            "Total Duration (Minutes)",
            "Total Duration (Hours)",
        ]
    )

    if not sorted_members:
        writer.writerow(["None", "", "0", "0.0", "0.00"])
    else:
        for mem in sorted_members:
            dur_m = mem["total_duration_minutes"]
            writer.writerow(
                [
                    mem["name"],
                    mem["email"],
                    mem["meetings_count"],
                    f"{dur_m:.1f}",
                    f"{dur_m / 60.0:.2f}",
                ]
            )

    return output.getvalue().encode("utf-8")
