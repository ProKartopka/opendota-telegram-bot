import aiosqlite
import asyncio
from config import log, DB_FILE

async def init_db():
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("""
                CREATE TABLE IF NOT EXISTS userdata (
                tg_id INTEGER NOT NULL,
                steam_id TEXT NOT NULL,
                name TEXT, 
                PRIMARY KEY (tg_id, steam_id)
                    )
                """)
        await conn.commit()

async def add_link(tg_id, steam_id):
    async with aiosqlite.connect(DB_FILE) as conn:
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
    async with aiosqlite.connect(DB_FILE) as conn:
        async with conn.execute("SELECT steam_id, name FROM userdata WHERE tg_id = ?", (tg_id,)) as cursor:
            idnames = await cursor.fetchall()
            return idnames

async def add_name(tg_id, steam_id, name):
    async with aiosqlite.connect(DB_FILE) as conn:
        cur = await conn.execute(
        "UPDATE userdata SET name = ? WHERE tg_id = ? AND steam_id = ?",
            (name, tg_id, steam_id),
        )
        await conn.commit()
        return cur.rowcount > 0

async def del_link(tg_id, steam_id):
    async with aiosqlite.connect(DB_FILE) as conn:
        try:
            cur = await conn.execute("""
            DELETE FROM userdata WHERE tg_id = ? AND steam_id = ?
            """, (tg_id, steam_id))
            await conn.commit()
            return cur.rowcount > 0
        except aiosqlite.Error as e:
            log.error(f"Ошибка при удалении! ({e})")
            return None

async def main():
    await init_db()

if __name__ == '__main__':
    asyncio.run(main())