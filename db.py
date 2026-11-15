import aiosqlite
import asyncio

DB_NAME = "userdata.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("""
                CREATE TABLE IF NOT EXISTS userdata (
                tg_id INTEGER NOT NULL,
                steam_id TEXT NOT NULL,
                PRIMARY KEY (tg_id, steam_id)
                    )
                """)
        await conn.commit()

async def add_link(tg_id, steam_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        try:
            await conn.execute("""
                INSERT INTO userdata (tg_id, steam_id)
                    VALUES (?,?)
            """,
                           (tg_id, steam_id))
            await conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def get_links(tg_id):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT steam_id FROM userdata WHERE tg_id = ?", (tg_id,)) as cursor:
            rows = await cursor.fetchall()
            ids = [row[0] for row in rows]
            return ids

async def main():
    await init_db()

if __name__ == '__main__':
    asyncio.run(main())