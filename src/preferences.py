import asyncio
import json
import sqlite3
from pathlib import Path
from google.genai import types
from database import get_collection, genai_client

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "vote.db"
REFRESH_THRESHOLD = 50

def _get_conn():
    conn= sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS member_preferences (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            likes_json TEXT DEFAULT '[]',
            dislikes_json TEXT DEFAULT '[]',
            msg_count INTERGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def _fetch_user_messages(aliases: list[str], user_id: str = None) -> tuple[int, list[str]]:
    collection = get_collection