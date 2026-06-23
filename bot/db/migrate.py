from sqlalchemy import text



from bot.db.session import engine



MIGRATIONS = [

    "ALTER TABLE chats ADD COLUMN status VARCHAR(32) DEFAULT 'active'",

    "ALTER TABLE posts ADD COLUMN send_mode VARCHAR(16) DEFAULT 'forward'",

    "ALTER TABLE posts ADD COLUMN copy_caption TEXT",

    "ALTER TABLE posts ADD COLUMN auto_broadcast_enabled BOOLEAN DEFAULT 0",

]





async def run_migrations() -> None:

    async with engine.begin() as conn:

        for sql in MIGRATIONS:

            try:

                await conn.execute(text(sql))

            except Exception:

                pass

