"""账号与会话存取层（纯 stdlib，不引第三方鉴权依赖）。

- 密码：pbkdf2_hmac(sha256) + 每用户独立随机盐，迭代 20 万次；只存哈希，不存明文。
- 会话：登录成功后生成随机 token 写入 sessions 表；前端后续请求带
  Authorization: Bearer <token>，服务端按 token 反查用户名。token 仅存服务端、
  可随时吊销（登出），无需 JWT 密钥管理。

所有函数接受可选 db_path，测试时可指向临时库。
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from pathlib import Path

from app.db.sqlite_client import _connect

PBKDF2_ITERATIONS = 200_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
MIN_PASSWORD_LEN = 6


class UserExistsError(Exception):
    """注册时用户名已存在。"""


def validate_credentials(username: str, password: str) -> None:
    """校验用户名/密码格式；不合法抛 ValueError。"""
    if not isinstance(username, str) or not USERNAME_RE.match(username):
        raise ValueError("用户名需为 3-20 位字母、数字或下划线")
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"密码至少 {MIN_PASSWORD_LEN} 位")


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """返回 (salt_hex, password_hash_hex)；salt 缺省时随机生成。"""
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return salt.hex(), digest.hex()


def create_user(
    username: str, password: str, db_path: str | Path | None = None
) -> None:
    """创建账号；用户名已存在抛 UserExistsError，格式不合法抛 ValueError。"""
    validate_credentials(username, password)
    salt_hex, hash_hex = hash_password(password)
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing is not None:
            raise UserExistsError(f"用户名 {username} 已存在")
        conn.execute(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (username, hash_hex, salt_hex),
        )


def user_exists(username: str, db_path: str | Path | None = None) -> bool:
    with _connect(db_path) as conn:
        return (
            conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            is not None
        )


def verify_user(
    username: str, password: str, db_path: str | Path | None = None
) -> bool:
    """校验账号密码；用户不存在或密码错均返回 False（不区分，避免账号枚举）。"""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT password_hash, salt FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        # 仍做一次等长计算以降低计时侧信道（成本可忽略）
        hash_password(password)
        return False
    _, expected = hash_password(password, bytes.fromhex(row["salt"]))
    return hmac.compare_digest(expected, row["password_hash"])


# ------------------------------------------------------------
# 会话
# ------------------------------------------------------------

def create_session(username: str, db_path: str | Path | None = None) -> str:
    """为已登录用户创建会话，返回不透明随机 token。"""
    token = secrets.token_urlsafe(32)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (token, username) VALUES (?, ?)", (token, username)
        )
    return token


def get_session_user(
    token: str, db_path: str | Path | None = None
) -> str | None:
    """按 token 反查用户名；无效/已吊销返回 None。"""
    if not token:
        return None
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT username FROM sessions WHERE token = ?", (token,)
        ).fetchone()
    return row["username"] if row else None


def revoke_session(token: str, db_path: str | Path | None = None) -> None:
    """登出：删除会话 token。"""
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
