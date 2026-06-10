# MeetMate 数据库设计

系统使用 SQLite 作为本地持久化数据库。应用启动时会调用 `init_db()` 自动创建所需数据表和索引。

## users

保存用户账号信息。

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nickname TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

字段说明：

- `username`：登录用户名，唯一。
- `password_hash`：PBKDF2 哈希后的密码。
- `nickname`：页面展示昵称。
- `created_at`：创建时间。

## groups

保存 Group 基本信息。

```sql
CREATE TABLE groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    group_type TEXT,
    invite_code TEXT UNIQUE NOT NULL,
    owner_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
```

字段说明：

- `invite_code`：6 位随机邀请码。
- `owner_id`：Group 创建者用户 ID。

## group_members

保存 Group 与用户之间的成员关系。

```sql
CREATE TABLE group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    UNIQUE(group_id, user_id)
);
```

`role` 可取：

- `owner`
- `member`

## personal_events

保存用户个人日程，也保存确认后的 Group 活动同步记录。

```sql
CREATE TABLE personal_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    event_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    location TEXT,
    note TEXT,
    event_type TEXT NOT NULL,
    source_group_id INTEGER,
    source_activity_id INTEGER,
    created_at TEXT NOT NULL
);
```

`event_type` 可取：

- `personal`
- `group`

当 `event_type = group` 时，`source_group_id` 和 `source_activity_id` 用于避免重复同步。

## group_activities

保存 Group 内待排期或已确认活动。

```sql
CREATE TABLE group_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    candidate_start_date TEXT NOT NULL,
    candidate_end_date TEXT NOT NULL,
    daily_start_time TEXT NOT NULL,
    daily_end_time TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    location TEXT,
    note TEXT,
    status TEXT NOT NULL,
    final_date TEXT,
    final_start_time TEXT,
    final_end_time TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
```

`status` 可取：

- `pending`
- `confirmed`
- `cancelled`

## availability

保存成员对每个候选时间段的空闲状态。

```sql
CREATE TABLE availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    slot_start TEXT NOT NULL,
    slot_end TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(activity_id, user_id, slot_start, slot_end)
);
```

`status` 可取：

- `available`
- `maybe`
- `unavailable`

## 主要关系

1. 一个用户可以创建多个 Group。
2. 一个用户可以加入多个 Group。
3. 一个 Group 可以包含多个成员。
4. 一个 Group 可以创建多个活动。
5. 一个活动可以收集多个成员的空闲时间。
6. 一个已确认活动会同步为多个成员的个人日程。

## 索引设计

系统额外创建以下索引提高查询效率：

- `idx_events_user_date`：按用户和日期查询个人日程。
- `idx_group_members_user`：查询用户加入的 Group。
- `idx_activities_group`：按 Group 和状态查询活动。
- `idx_availability_activity`：按活动查询空闲时间。
