from __future__ import annotations

import secrets
import string
from datetime import date, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from database import get_connection, row_to_dict


CHINA_TZ = ZoneInfo("Asia/Shanghai")
GROUP_TYPES = ["学习小组", "工作团队", "项目组", "社团组织", "朋友聚会", "其他"]


def _now_text() -> str:
    return datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_date(value: str | date) -> str:
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def _normalize_time(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    return str(value)[:5]


def _invite_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


def get_user_by_id(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, nickname, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return row_to_dict(row)


def update_user_profile(user_id: int, nickname: str) -> tuple[bool, str]:
    nickname = nickname.strip()
    if not nickname:
        return False, "昵称不能为空。"
    with get_connection() as conn:
        conn.execute("UPDATE users SET nickname = ? WHERE id = ?", (nickname, user_id))
    return True, "个人信息已更新。"


def create_personal_event(
    user_id: int,
    title: str,
    event_date: str | date,
    start_time,
    end_time,
    location: str = "",
    note: str = "",
    event_type: str = "personal",
    source_group_id: int | None = None,
    source_activity_id: int | None = None,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO personal_events (
                user_id, title, event_date, start_time, end_time, location, note,
                event_type, source_group_id, source_activity_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                title.strip(),
                _normalize_date(event_date),
                _normalize_time(start_time),
                _normalize_time(end_time),
                location.strip(),
                note.strip(),
                event_type,
                source_group_id,
                source_activity_id,
                _now_text(),
            ),
        )
        return int(cursor.lastrowid)


def list_personal_events(
    user_id: int,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
) -> list[dict]:
    sql = "SELECT * FROM personal_events WHERE user_id = ?"
    params: list = [user_id]
    if start_date is not None:
        sql += " AND event_date >= ?"
        params.append(_normalize_date(start_date))
    if end_date is not None:
        sql += " AND event_date <= ?"
        params.append(_normalize_date(end_date))
    sql += " ORDER BY event_date ASC, start_time ASC"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def delete_personal_event(user_id: int, event_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM personal_events WHERE id = ? AND user_id = ?",
            (event_id, user_id),
        )


def get_upcoming_events(user_id: int, now: datetime, hours: int = 24) -> list[dict]:
    end_time = now + timedelta(hours=hours)
    rows = list_personal_events(user_id, now.date(), end_time.date())
    upcoming = []
    for row in rows:
        start_dt = datetime.strptime(
            f"{row['event_date']} {row['start_time']}", "%Y-%m-%d %H:%M"
        )
        start_dt = start_dt.replace(tzinfo=CHINA_TZ)
        if now <= start_dt <= end_time:
            upcoming.append(row)
    return upcoming


def count_events_between(user_id: int, start_day: date, end_day: date) -> int:
    return len(list_personal_events(user_id, start_day, end_day))


def create_group(
    owner_id: int,
    name: str,
    description: str,
    group_type: str,
) -> tuple[bool, str, int | None, str | None]:
    name = name.strip()
    if not name:
        return False, "Group 名称不能为空。", None, None
    if group_type not in GROUP_TYPES:
        group_type = "其他"

    with get_connection() as conn:
        for _ in range(30):
            code = _invite_code()
            if not conn.execute(
                'SELECT id FROM "groups" WHERE invite_code = ?', (code,)
            ).fetchone():
                break
        else:
            return False, "邀请码生成失败，请重试。", None, None

        cursor = conn.execute(
            """
            INSERT INTO "groups" (name, description, group_type, invite_code, owner_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, description.strip(), group_type, code, owner_id, _now_text()),
        )
        group_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO group_members (group_id, user_id, role, joined_at)
            VALUES (?, ?, 'owner', ?)
            """,
            (group_id, owner_id, _now_text()),
        )
    return True, f"Group 创建成功，邀请码为 {code}。", group_id, code


def update_group(
    group_id: int,
    owner_id: int,
    name: str,
    description: str,
    group_type: str,
) -> tuple[bool, str]:
    if not name.strip():
        return False, "Group 名称不能为空。"
    with get_connection() as conn:
        group = conn.execute(
            'SELECT owner_id FROM "groups" WHERE id = ?', (group_id,)
        ).fetchone()
        if group is None:
            return False, "Group 不存在。"
        if group["owner_id"] != owner_id:
            return False, "只有创建者可以修改 Group。"
        conn.execute(
            """
            UPDATE "groups"
            SET name = ?, description = ?, group_type = ?
            WHERE id = ?
            """,
            (name.strip(), description.strip(), group_type, group_id),
        )
    return True, "Group 信息已更新。"


def join_group_by_invite(user_id: int, invite_code: str) -> tuple[bool, str]:
    invite_code = invite_code.strip().upper()
    if not invite_code:
        return False, "请输入邀请码。"
    with get_connection() as conn:
        group = conn.execute(
            'SELECT id FROM "groups" WHERE invite_code = ?', (invite_code,)
        ).fetchone()
        if group is None:
            return False, "邀请码不存在。"
        try:
            conn.execute(
                """
                INSERT INTO group_members (group_id, user_id, role, joined_at)
                VALUES (?, ?, 'member', ?)
                """,
                (group["id"], user_id, _now_text()),
            )
        except Exception:
            return False, "你已经加入该 Group。"
    return True, "加入 Group 成功。"


def list_user_groups(user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                g.*,
                gm.role,
                (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) AS member_count,
                (
                    SELECT COUNT(*) FROM group_activities
                    WHERE group_id = g.id AND status = 'pending'
                ) AS pending_count
            FROM "groups" g
            JOIN group_members gm ON gm.group_id = g.id
            WHERE gm.user_id = ?
            ORDER BY g.created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_group_count(user_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM group_members WHERE user_id = ?", (user_id,)
        ).fetchone()
    return int(row["count"])


def get_group(group_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                g.*,
                u.nickname AS owner_name,
                (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) AS member_count
            FROM "groups" g
            JOIN users u ON u.id = g.owner_id
            WHERE g.id = ?
            """,
            (group_id,),
        ).fetchone()
    return row_to_dict(row)


def get_member_role(group_id: int, user_id: int) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT role FROM group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
    return row["role"] if row else None


def get_group_members(group_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                gm.user_id,
                gm.role,
                gm.joined_at,
                u.username,
                u.nickname
            FROM group_members gm
            JOIN users u ON u.id = gm.user_id
            WHERE gm.group_id = ?
            ORDER BY gm.role DESC, gm.joined_at ASC
            """,
            (group_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_activity(
    group_id: int,
    created_by: int,
    title: str,
    description: str,
    candidate_start_date: str | date,
    candidate_end_date: str | date,
    daily_start_time,
    daily_end_time,
    duration_minutes: int,
    location: str,
    note: str,
) -> tuple[bool, str, int | None]:
    if not title.strip():
        return False, "活动名称不能为空。", None
    if int(duration_minutes) <= 0:
        return False, "活动时长必须大于 0。", None
    role = get_member_role(group_id, created_by)
    group = get_group(group_id)
    if role is None or group is None:
        return False, "你不在该 Group 中。", None
    if group["owner_id"] != created_by:
        return False, "只有 Group 创建者可以创建活动。", None

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO group_activities (
                group_id, title, description, candidate_start_date, candidate_end_date,
                daily_start_time, daily_end_time, duration_minutes, location, note,
                status, created_by, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                group_id,
                title.strip(),
                description.strip(),
                _normalize_date(candidate_start_date),
                _normalize_date(candidate_end_date),
                _normalize_time(daily_start_time),
                _normalize_time(daily_end_time),
                int(duration_minutes),
                location.strip(),
                note.strip(),
                created_by,
                _now_text(),
            ),
        )
        activity_id = int(cursor.lastrowid)
    return True, "活动创建成功。", activity_id


def get_activity(activity_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                a.*,
                g.name AS group_name,
                g.invite_code,
                g.owner_id
            FROM group_activities a
            JOIN "groups" g ON g.id = a.group_id
            WHERE a.id = ?
            """,
            (activity_id,),
        ).fetchone()
    return row_to_dict(row)


def list_group_activities(group_id: int, status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM group_activities WHERE group_id = ?"
    params: list = [group_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def list_user_activities(user_id: int, status: str | None = None) -> list[dict]:
    sql = """
        SELECT
            a.*,
            g.name AS group_name,
            gm.role AS member_role
        FROM group_activities a
        JOIN "groups" g ON g.id = a.group_id
        JOIN group_members gm ON gm.group_id = g.id
        WHERE gm.user_id = ?
    """
    params: list = [user_id]
    if status:
        sql += " AND a.status = ?"
        params.append(status)
    sql += " ORDER BY a.created_at DESC"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def delete_activity(activity_id: int, user_id: int) -> tuple[bool, str]:
    activity = get_activity(activity_id)
    if activity is None:
        return False, "活动不存在。"
    if activity["owner_id"] != user_id:
        return False, "只有 Group 创建者可以删除活动。"
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM personal_events WHERE source_activity_id = ?",
            (activity_id,),
        )
        conn.execute("DELETE FROM group_activities WHERE id = ?", (activity_id,))
    return True, "活动已删除。"


def save_availability(activity_id: int, user_id: int, choices: Iterable[dict]) -> None:
    with get_connection() as conn:
        for choice in choices:
            conn.execute(
                """
                INSERT INTO availability (
                    activity_id, user_id, slot_start, slot_end, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(activity_id, user_id, slot_start, slot_end)
                DO UPDATE SET status = excluded.status, created_at = excluded.created_at
                """,
                (
                    activity_id,
                    user_id,
                    choice["slot_start"],
                    choice["slot_end"],
                    choice["status"],
                    _now_text(),
                ),
            )


def get_user_availability(activity_id: int, user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM availability
            WHERE activity_id = ? AND user_id = ?
            """,
            (activity_id, user_id),
        ).fetchall()
    return [dict(row) for row in rows]


def get_activity_availability(activity_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM availability WHERE activity_id = ?",
            (activity_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_personal_events_for_users(
    user_ids: list[int],
    start_date: str | date | None = None,
    end_date: str | date | None = None,
) -> list[dict]:
    if not user_ids:
        return []
    placeholders = ",".join("?" for _ in user_ids)
    sql = f"SELECT * FROM personal_events WHERE user_id IN ({placeholders})"
    params: list = list(user_ids)
    if start_date is not None:
        sql += " AND event_date >= ?"
        params.append(_normalize_date(start_date))
    if end_date is not None:
        sql += " AND event_date <= ?"
        params.append(_normalize_date(end_date))
    sql += " ORDER BY user_id ASC, event_date ASC, start_time ASC"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def confirm_activity(
    activity_id: int,
    user_id: int,
    final_date: str,
    final_start_time: str,
    final_end_time: str,
) -> tuple[bool, str, int]:
    activity = get_activity(activity_id)
    if activity is None:
        return False, "活动不存在。", 0
    if activity["owner_id"] != user_id:
        return False, "只有 Group 创建者可以确认活动。", 0

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE group_activities
            SET status = 'confirmed',
                final_date = ?,
                final_start_time = ?,
                final_end_time = ?
            WHERE id = ?
            """,
            (final_date, final_start_time, final_end_time, activity_id),
        )
        members = conn.execute(
            "SELECT user_id FROM group_members WHERE group_id = ?",
            (activity["group_id"],),
        ).fetchall()
        synced = 0
        for member in members:
            existing = conn.execute(
                """
                SELECT id FROM personal_events
                WHERE user_id = ? AND source_activity_id = ?
                """,
                (member["user_id"], activity_id),
            ).fetchone()
            payload = (
                f"{activity['group_name']}：{activity['title']}",
                final_date,
                final_start_time,
                final_end_time,
                activity["location"] or "",
                activity["note"] or activity["description"] or "",
                "group",
                activity["group_id"],
                activity_id,
            )
            if existing:
                conn.execute(
                    """
                    UPDATE personal_events
                    SET title = ?, event_date = ?, start_time = ?, end_time = ?,
                        location = ?, note = ?, event_type = ?,
                        source_group_id = ?, source_activity_id = ?
                    WHERE id = ?
                    """,
                    (*payload, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO personal_events (
                        user_id, title, event_date, start_time, end_time, location, note,
                        event_type, source_group_id, source_activity_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (member["user_id"], *payload, _now_text()),
                )
            synced += 1
    return True, f"活动已确认，并同步到 {synced} 位成员的个人日程。", synced
