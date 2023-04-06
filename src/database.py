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

cur.execute("""
CREATE TABLE IF NOT EXISTS user_metrics(
    snowflake INT PRIMARY KEY,
    prompts INT
)
""")


def increment_user_prompt_counter(snowflake: int):
    r = cur.execute("SELECT prompts FROM user_metrics WHERE snowflake=?", [snowflake])
    r = r.fetchone()
    new_count = r[0] + 1 if r else 1
    cur.execute("""
    INSERT OR REPLACE INTO user_metrics(snowflake, prompts)
    VALUES (?, ?)
    """, [snowflake, new_count])
    con.commit()


def query_leaderboard():
    r = cur.execute("SELECT * FROM user_metrics ORDER BY prompts DESC LIMIT 10")
    r = r.fetchall()
    return r if r else []


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
