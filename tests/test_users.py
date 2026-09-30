"""账号/会话层测试：注册、验证、会话、哈希安全与跨账号数据隔离。"""

from __future__ import annotations

import pytest
from app.db.models import Profile
from app.db.sqlite_client import ensure_tables, load_profile, save_profile
from app.db.users import (
    UserExistsError,
    create_session,
    create_user,
    get_session_user,
    hash_password,
    revoke_session,
    user_exists,
    verify_user,
)


@pytest.fixture
def db(tmp_path):
    path = ensure_tables(tmp_path / "users.db")
    return path


def _profile(age: int) -> Profile:
    return Profile(
        sex="male",
        age=age,
        height_cm=175.0,
        weight_kg=70.0,
        goal="muscle_gain",
        days_per_week=3,
        equipment=["dumbbell"],
    )


def test_register_then_verify(db):
    create_user("alice", "secret123", db_path=db)
    assert user_exists("alice", db_path=db)
    assert verify_user("alice", "secret123", db_path=db)
    assert not verify_user("alice", "wrongpass", db_path=db)


def test_verify_nonexistent_user_false(db):
    assert not verify_user("ghost", "whatever", db_path=db)


def test_duplicate_registration_raises(db):
    create_user("alice", "secret123", db_path=db)
    with pytest.raises(UserExistsError):
        create_user("alice", "another456", db_path=db)


def test_invalid_credentials_raise(db):
    with pytest.raises(ValueError):
        create_user("ab", "secret123", db_path=db)  # 用户名太短
    with pytest.raises(ValueError):
        create_user("valid_name", "12", db_path=db)  # 密码太短
    with pytest.raises(ValueError):
        create_user("有中文", "secret123", db_path=db)  # 非法字符


def test_password_not_stored_in_plaintext(db):
    password = "secret123"
    create_user("alice", password, db_path=db)
    import sqlite3

    conn = sqlite3.connect(db)
    stored = conn.execute("SELECT password_hash, salt FROM users").fetchone()
    conn.close()
    hash_value, salt = stored
    assert password not in hash_value
    # 用同样的盐可复现哈希（验证哈希算法自洽）
    _, expected = hash_password(password, bytes.fromhex(salt))
    assert hash_value == expected


def test_session_lifecycle(db):
    create_user("alice", "secret123", db_path=db)
    token = create_session("alice", db_path=db)
    assert get_session_user(token, db_path=db) == "alice"
    revoke_session(token, db_path=db)
    assert get_session_user(token, db_path=db) is None


def test_invalid_session_token(db):
    assert get_session_user("", db_path=db) is None
    assert get_session_user("nope", db_path=db) is None


def test_profiles_isolated_between_accounts(db):
    create_user("alice", "secret123", db_path=db)
    create_user("bob", "secret456", db_path=db)
    save_profile(_profile(30), "alice", db_path=db)
    save_profile(_profile(40), "bob", db_path=db)

    alice = load_profile("alice", db_path=db)
    bob = load_profile("bob", db_path=db)
    assert alice is not None and alice.age == 30
    assert bob is not None and bob.age == 40
    # 未填画像的账号读取为 None，不会拿到别人的数据
    assert load_profile("carol", db_path=db) is None
