from pathlib import Path



from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine



from bot.config import get_settings



settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)





async def init_db() -> None:

    from bot.db.migrate import run_migrations

    from bot.db.models import Base



    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)



    async with engine.begin() as conn:

        await conn.run_sync(Base.metadata.create_all)



    await run_migrations()





async def close_db() -> None:

    await engine.dispose()

