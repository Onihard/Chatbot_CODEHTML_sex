import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_batch

SQLITE_DB = os.getenv("SQLITE_DB", "chat_bot.db")
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://user:password@localhost:5432/chatweb")

def ensure_pg_schema(pg):
    cur = pg.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        nickname TEXT UNIQUE,
        age INTEGER,
        gender TEXT,
        bio TEXT,
        hobbies TEXT,
        city TEXT,
        motto TEXT,
        current_room TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS auth (
        auth_id SERIAL PRIMARY KEY,
        user_id INTEGER,
        nickname TEXT UNIQUE,
        password_hash TEXT,
        role TEXT DEFAULT 'user'
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        room_id SERIAL PRIMARY KEY,
        name TEXT UNIQUE,
        description TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        message_id SERIAL PRIMARY KEY,
        user_id INTEGER,
        room_name TEXT,
        message_text TEXT,
        timestamp TIMESTAMPTZ DEFAULT NOW()
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS private_messages (
        id SERIAL PRIMARY KEY,
        sender_id INTEGER,
        receiver_id INTEGER,
        message_text TEXT,
        timestamp TIMESTAMPTZ DEFAULT NOW()
    )
    """)
    pg.commit()

def fetch_sqlite_rows(conn, query):
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query)
    return cur.fetchall()

def migrate():
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    pg = psycopg2.connect(POSTGRES_DSN)
    try:
        ensure_pg_schema(pg)
        cur = pg.cursor()

        # users
        users = fetch_sqlite_rows(sqlite_conn, "SELECT user_id, nickname, age, gender, bio, \n                                                   COALESCE(hobbies, ''), COALESCE(city, ''), COALESCE(motto, ''), current_room FROM users")
        execute_batch(cur,
            """
            INSERT INTO users (user_id, nickname, age, gender, bio, hobbies, city, motto, current_room)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (user_id) DO UPDATE SET
              nickname=EXCLUDED.nickname,
              age=EXCLUDED.age,
              gender=EXCLUDED.gender,
              bio=EXCLUDED.bio,
              hobbies=EXCLUDED.hobbies,
              city=EXCLUDED.city,
              motto=EXCLUDED.motto,
              current_room=EXCLUDED.current_room
            """,
            [tuple(u) for u in users], page_size=500)

        # auth
        auth_rows = fetch_sqlite_rows(sqlite_conn, "SELECT auth_id, user_id, nickname, password_hash, COALESCE(role, 'user') AS role FROM auth")
        execute_batch(cur,
            """
            INSERT INTO auth (auth_id, user_id, nickname, password_hash, role)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (auth_id) DO UPDATE SET
              user_id=EXCLUDED.user_id,
              nickname=EXCLUDED.nickname,
              password_hash=EXCLUDED.password_hash,
              role=EXCLUDED.role
            """,
            [tuple(a) for a in auth_rows], page_size=500)

        # rooms
        rooms = fetch_sqlite_rows(sqlite_conn, "SELECT room_id, name, description FROM rooms")
        execute_batch(cur,
            """
            INSERT INTO rooms (room_id, name, description)
            VALUES (%s,%s,%s)
            ON CONFLICT (room_id) DO UPDATE SET
              name=EXCLUDED.name,
              description=EXCLUDED.description
            """,
            [tuple(r) for r in rooms], page_size=500)

        # messages
        messages = fetch_sqlite_rows(sqlite_conn, "SELECT message_id, user_id, room_name, message_text, timestamp FROM messages")
        execute_batch(cur,
            """
            INSERT INTO messages (message_id, user_id, room_name, message_text, timestamp)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (message_id) DO NOTHING
            """,
            [tuple(m) for m in messages], page_size=500)

        # private_messages (handle id/message_id name differences)
        # Try message_id first
        try:
            pms = fetch_sqlite_rows(sqlite_conn, "SELECT message_id, sender_id, receiver_id, message_text, timestamp FROM private_messages")
            execute_batch(cur,
                """
                INSERT INTO private_messages (id, sender_id, receiver_id, message_text, timestamp)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
                """,
                [tuple(p) for p in pms], page_size=500)
        except sqlite3.OperationalError:
            pms = fetch_sqlite_rows(sqlite_conn, "SELECT id, sender_id, receiver_id, message_text, timestamp FROM private_messages")
            execute_batch(cur,
                """
                INSERT INTO private_messages (id, sender_id, receiver_id, message_text, timestamp)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
                """,
                [tuple(p) for p in pms], page_size=500)

        pg.commit()
        print("Migration completed successfully")
    finally:
        sqlite_conn.close()
        pg.close()

if __name__ == "__main__":
    migrate()


