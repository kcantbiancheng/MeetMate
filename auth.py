from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from database import get_connection, row_to_dict


CHINA_TZ = ZoneInfo("Asia/Shanghai")


def _now_text() -> str:
    return datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, digest = stored_hash.split("$", 1)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()
    return hmac.compare_digest(candidate, digest)


def register_user(username: str, password: str, nickname: str) -> tuple[bool, str]:
    username = username.strip()
    nickname = nickname.strip()
    if not username:
        return False, "用户名不能为空。"
    if not password:
        return False, "密码不能为空。"
    if not nickname:
        return False, "昵称不能为空。"

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            return False, "该用户名已被注册。"
        conn.execute(
            """
            INSERT INTO users (username, password_hash, nickname, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (username, hash_password(password), nickname, _now_text()),
        )
    return True, "注册成功，请登录。"


def login_user(username: str, password: str) -> tuple[bool, str, dict | None]:
    username = username.strip()
    if not username or not password:
        return False, "请输入用户名和密码。", None

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return False, "用户名或密码错误。", None
    user = row_to_dict(row)
    user.pop("password_hash", None)
    return True, "登录成功。", user


def change_password(user_id: int, old_password: str, new_password: str) -> tuple[bool, str]:
    if not old_password or not new_password:
        return False, "请输入旧密码和新密码。"
    with get_connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            return False, "用户不存在。"
        if not verify_password(old_password, user["password_hash"]):
            return False, "旧密码不正确。"
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )
    return True, "密码已更新。"
