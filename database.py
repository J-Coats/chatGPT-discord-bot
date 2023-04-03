import sqlite3
from src import log
from typing import Optional

logger = log.setup_logger(__name__)

# Database setup
con = sqlite3.connect("bot.db")
cur = con.cursor()
logger.info("Connected to file-based database at bot.db")
cur.execute("""
    CREATE TABLE IF NOT EXISTS user_tokens(
        snowflake INT PRIMARY KEY,
        api_key TEXT
    )
    """)


def update_token(snowflake: int, token: str):
    cur.execute("""
        INSERT OR REPLACE INTO user_tokens(snowflake, api_key)
        VALUES (?, ?)
        """, [snowflake, token])
    con.commit()


def query_token(snowflake: int) -> Optional[str]:
    r = cur.execute("""
        SELECT api_key FROM user_tokens WHERE snowflake=?
    """, [snowflake])
    r = r.fetchone()
    return r[0] if r else None
