from __future__ import annotations
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.environ.get("HOMEIQ_DB_PATH", "data/homeiq.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            salary REAL DEFAULT 50000,
            partner_salary REAL DEFAULT 0,
            budget REAL,
            deposit_pct REAL DEFAULT 15,
            job_type TEXT DEFAULT 'hybrid',
            priorities TEXT DEFAULT '[]',
            current_savings REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            profile_id INTEGER,
            search_type TEXT NOT NULL,
            query_params TEXT NOT NULL,
            results TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (profile_id) REFERENCES profiles(id)
        );

        CREATE TABLE IF NOT EXISTS saved_comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            profile_id INTEGER,
            regions TEXT NOT NULL,
            rankings TEXT NOT NULL,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT,
            messages TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()


def get_or_create_user(username: str) -> int:
    conn = get_connection()
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        user_id = row["id"]
    else:
        cur = conn.execute("INSERT INTO users (username) VALUES (?)", (username,))
        user_id = cur.lastrowid
        conn.commit()
    conn.close()
    return user_id


def save_profile(user_id: int, profile: dict) -> int:
    conn = get_connection()
    name = profile.get("name", "Default")
    existing = conn.execute(
        "SELECT id FROM profiles WHERE user_id = ? AND name = ? AND is_active = 1",
        (user_id, name),
    ).fetchone()
    conn.execute(
        "UPDATE profiles SET is_active = 0 WHERE user_id = ?", (user_id,)
    )
    if existing:
        conn.execute(
            """UPDATE profiles SET salary=?, partner_salary=?, budget=?,
               deposit_pct=?, job_type=?, priorities=?, current_savings=?, is_active=1
               WHERE id=?""",
            (
                int(profile.get("salary", 50000)),
                int(profile.get("partner_salary", 0)),
                int(profile["budget"]) if profile.get("budget") else None,
                int(profile.get("deposit_pct", 15)),
                profile.get("job_type", "hybrid"),
                json.dumps(profile.get("priorities", [])),
                int(profile.get("current_savings", 0)),
                existing[0],
            ),
        )
        conn.commit()
        profile_id = existing[0]
    else:
        cur = conn.execute(
            """INSERT INTO profiles (user_id, name, salary, partner_salary, budget,
               deposit_pct, job_type, priorities, current_savings)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id, name,
                int(profile.get("salary", 50000)),
                int(profile.get("partner_salary", 0)),
                int(profile["budget"]) if profile.get("budget") else None,
                int(profile.get("deposit_pct", 15)),
                profile.get("job_type", "hybrid"),
                json.dumps(profile.get("priorities", [])),
                int(profile.get("current_savings", 0)),
            ),
        )
        conn.commit()
        profile_id = cur.lastrowid
    conn.close()
    return profile_id


def get_active_profile(user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM profiles WHERE user_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "salary": row["salary"],
        "partner_salary": row["partner_salary"],
        "budget": row["budget"],
        "deposit_pct": row["deposit_pct"],
        "job_type": row["job_type"],
        "priorities": json.loads(row["priorities"]),
        "current_savings": row["current_savings"],
        "created_at": row["created_at"],
    }


def get_all_profiles(user_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM profiles WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "salary": r["salary"],
            "partner_salary": r["partner_salary"],
            "budget": r["budget"],
            "deposit_pct": r["deposit_pct"],
            "job_type": r["job_type"],
            "priorities": json.loads(r["priorities"]),
            "current_savings": r["current_savings"],
            "is_active": bool(r["is_active"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def set_active_profile(user_id: int, profile_id: int):
    conn = get_connection()
    conn.execute("UPDATE profiles SET is_active = 0 WHERE user_id = ?", (user_id,))
    conn.execute(
        "UPDATE profiles SET is_active = 1, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
        (profile_id, user_id),
    )
    conn.commit()
    conn.close()


def save_search(user_id: int, profile_id: int | None, search_type: str, query_params: dict, results: dict) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO searches (user_id, profile_id, search_type, query_params, results) VALUES (?, ?, ?, ?, ?)",
        (user_id, profile_id, search_type, json.dumps(query_params), json.dumps(results)),
    )
    conn.commit()
    search_id = cur.lastrowid
    conn.close()
    return search_id


def get_search_history(user_id: int, limit: int = 20) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM searches WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "search_type": r["search_type"],
            "query_params": json.loads(r["query_params"]),
            "results": json.loads(r["results"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def save_comparison(user_id: int, profile_id: int | None, regions: list, rankings: list, notes: str = "") -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO saved_comparisons (user_id, profile_id, regions, rankings, notes) VALUES (?, ?, ?, ?, ?)",
        (user_id, profile_id, json.dumps(regions), json.dumps(rankings), notes),
    )
    conn.commit()
    comp_id = cur.lastrowid
    conn.close()
    return comp_id


def get_saved_comparisons(user_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM saved_comparisons WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "regions": json.loads(r["regions"]),
            "rankings": json.loads(r["rankings"]),
            "notes": r["notes"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def save_chat_session(user_id: int, title: str, messages: list) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO chat_sessions (user_id, title, messages) VALUES (?, ?, ?)",
        (user_id, title, json.dumps(messages)),
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id


def update_chat_session(session_id: int, messages: list):
    conn = get_connection()
    conn.execute(
        "UPDATE chat_sessions SET messages = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(messages), session_id),
    )
    conn.commit()
    conn.close()


def get_chat_sessions(user_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "title": r["title"], "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows]


def get_chat_session(session_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "messages": json.loads(row["messages"]),
        "created_at": row["created_at"],
    }


def delete_profile(user_id: int, profile_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM profiles WHERE id = ? AND user_id = ?", (profile_id, user_id))
    conn.commit()
    conn.close()


def delete_comparison(user_id: int, comparison_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM saved_comparisons WHERE id = ? AND user_id = ?", (comparison_id, user_id))
    conn.commit()
    conn.close()
