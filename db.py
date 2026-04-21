import aiosqlite

DB_NAME = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            gender TEXT,
            target_gender TEXT,
            platform TEXT,
            goal TEXT,
            stage TEXT DEFAULT 'start',
            interest INTEGER DEFAULT 50
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        await db.commit()


async def save_user(user_id, data):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        INSERT OR REPLACE INTO users (user_id, gender, target_gender, platform, goal)
        VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            data.get("gender"),
            data.get("target_gender"),
            data.get("platform"),
            data.get("goal")
        ))
        await db.commit()


async def save_message(user_id, text):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO messages (user_id, text) VALUES (?, ?)",
            (user_id, text)
        )
        await db.commit()


async def get_last_messages(user_id, limit=10):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT text FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit))

        rows = await cursor.fetchall()
        return [r[0] for r in reversed(rows)]
