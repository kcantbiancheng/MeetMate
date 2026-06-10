from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any


STATUS_SCORE = {
    "available": 1.0,
    "maybe": 0.5,
    "unavailable": 0.0,
}

STATUS_LABEL = {
    "available": "有空",
    "maybe": "不确定",
    "unavailable": "没空",
}


def _value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_time(value: str | time) -> time:
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    return datetime.strptime(value[:5], "%H:%M").time()


def parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(second=0, microsecond=0)
    return datetime.strptime(value[:16], "%Y-%m-%d %H:%M")


def combine_date_time(day: str | date, clock: str | time) -> datetime:
    return datetime.combine(parse_date(day), parse_time(clock))


def format_time(value: str | time) -> str:
    return parse_time(value).strftime("%H:%M")


def format_date(value: str | date) -> str:
    return parse_date(value).strftime("%Y-%m-%d")


def format_slot(slot: dict) -> str:
    return f"{slot['date']} {slot['start_time']}-{slot['end_time']}"


def generate_candidate_slots(
    start_date: str | date,
    end_date: str | date,
    daily_start_time: str | time,
    daily_end_time: str | time,
    duration_minutes: int,
) -> list[dict]:
    start_day = parse_date(start_date)
    end_day = parse_date(end_date)
    day_start = parse_time(daily_start_time)
    day_end = parse_time(daily_end_time)
    duration = timedelta(minutes=int(duration_minutes))

    if duration <= timedelta(0) or end_day < start_day:
        return []

    slots: list[dict] = []
    current_day = start_day
    while current_day <= end_day:
        cursor = datetime.combine(current_day, day_start)
        day_limit = datetime.combine(current_day, day_end)
        while cursor + duration <= day_limit:
            slot_end = cursor + duration
            slot = {
                "date": current_day.strftime("%Y-%m-%d"),
                "start_time": cursor.strftime("%H:%M"),
                "end_time": slot_end.strftime("%H:%M"),
                "slot_start": cursor.strftime("%Y-%m-%d %H:%M"),
                "slot_end": slot_end.strftime("%Y-%m-%d %H:%M"),
            }
            slot["label"] = format_slot(slot)
            slots.append(slot)
            cursor = slot_end
        current_day += timedelta(days=1)
    return slots


def has_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


def event_conflicts_with_slot(event: Any, slot_start: datetime, slot_end: datetime) -> bool:
    event_start = combine_date_time(_value(event, "event_date"), _value(event, "start_time"))
    event_end = combine_date_time(_value(event, "event_date"), _value(event, "end_time"))
    return has_overlap(slot_start, slot_end, event_start, event_end)


def find_event_conflicts(events: list[Any]) -> list[tuple[Any, Any]]:
    conflicts: list[tuple[Any, Any]] = []
    ordered = sorted(
        events,
        key=lambda row: (
            _value(row, "event_date", ""),
            _value(row, "start_time", ""),
            _value(row, "end_time", ""),
        ),
    )
    for idx, current in enumerate(ordered):
        current_start = combine_date_time(_value(current, "event_date"), _value(current, "start_time"))
        current_end = combine_date_time(_value(current, "event_date"), _value(current, "end_time"))
        for other in ordered[idx + 1 :]:
            if _value(current, "event_date") != _value(other, "event_date"):
                continue
            other_start = combine_date_time(_value(other, "event_date"), _value(other, "start_time"))
            other_end = combine_date_time(_value(other, "event_date"), _value(other, "end_time"))
            if has_overlap(current_start, current_end, other_start, other_end):
                conflicts.append((current, other))
    return conflicts


def _reason(row: dict, total_members: int) -> str:
    if row["conflict_count"] == 0 and row["available_count"] == total_members and total_members > 0:
        return "全部成员有空，且没有检测到个人日程冲突。"
    if row["conflict_count"] == 0 and row["available_count"] >= max(1, total_members // 2):
        return "多数成员有空，且没有检测到个人日程冲突。"
    if row["conflict_count"] > 0:
        return f"有 {row['conflict_count']} 位成员存在个人日程冲突，建议谨慎选择。"
    if row["missing_count"] > 0:
        return f"仍有 {row['missing_count']} 位成员未提交空闲时间，可作为备选。"
    return "该时间段可行，但成员空闲度不是最高。"


def compute_recommendations(
    activity: Any,
    members: list[Any],
    availability_rows: list[Any],
    personal_events: list[Any],
) -> list[dict]:
    slots = generate_candidate_slots(
        _value(activity, "candidate_start_date"),
        _value(activity, "candidate_end_date"),
        _value(activity, "daily_start_time"),
        _value(activity, "daily_end_time"),
        int(_value(activity, "duration_minutes", 0)),
    )
    activity_id = int(_value(activity, "id", 0))

    availability_map: dict[tuple[int, str, str], str] = {}
    for row in availability_rows:
        availability_map[
            (
                int(_value(row, "user_id")),
                _value(row, "slot_start"),
                _value(row, "slot_end"),
            )
        ] = _value(row, "status")

    events_by_user: dict[int, list[Any]] = {}
    for event in personal_events:
        if _value(event, "source_activity_id") == activity_id:
            continue
        events_by_user.setdefault(int(_value(event, "user_id")), []).append(event)

    results: list[dict] = []
    for slot in slots:
        available_count = 0
        maybe_count = 0
        unavailable_count = 0
        missing_count = 0
        conflict_members: list[str] = []
        score = 0.0
        slot_start_dt = parse_datetime(slot["slot_start"])
        slot_end_dt = parse_datetime(slot["slot_end"])

        for member in members:
            user_id = int(_value(member, "user_id"))
            status = availability_map.get((user_id, slot["slot_start"], slot["slot_end"]))
            if status == "available":
                available_count += 1
            elif status == "maybe":
                maybe_count += 1
            elif status == "unavailable":
                unavailable_count += 1
            else:
                missing_count += 1
            score += STATUS_SCORE.get(status, 0.0)

            has_conflict = any(
                event_conflicts_with_slot(event, slot_start_dt, slot_end_dt)
                for event in events_by_user.get(user_id, [])
            )
            if has_conflict:
                conflict_members.append(_value(member, "nickname", "成员"))

        conflict_count = len(conflict_members)
        final_score = score - conflict_count
        row = {
            "date": slot["date"],
            "start_time": slot["start_time"],
            "end_time": slot["end_time"],
            "slot_start": slot["slot_start"],
            "slot_end": slot["slot_end"],
            "slot_label": slot["label"],
            "score": round(final_score, 2),
            "available_count": available_count,
            "maybe_count": maybe_count,
            "unavailable_count": unavailable_count,
            "missing_count": missing_count,
            "conflict_count": conflict_count,
            "conflict_members": "、".join(conflict_members) if conflict_members else "无",
        }
        row["reason"] = _reason(row, len(members))
        results.append(row)

    results.sort(
        key=lambda item: (
            -item["score"],
            item["conflict_count"],
            -item["available_count"],
            item["slot_start"],
        )
    )
    return results
