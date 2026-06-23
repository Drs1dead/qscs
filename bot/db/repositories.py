from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.db.models import BroadcastJob, BroadcastStatus, Chat, ChatStatus, ExcludedChat, Log, Post, SendMode, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def upsert(
        self,
        user_id: int,
        *,
        username: str | None = None,
        full_name: str | None = None,
        is_super_admin: bool = False,
    ) -> User:
        user = await self.get(user_id)
        if user is None:
            user = User(
                id=user_id,
                username=username,
                full_name=full_name,
                is_super_admin=is_super_admin,
            )
            self.session.add(user)
        else:
            if username is not None:
                user.username = username
            if full_name is not None:
                user.full_name = full_name
            if is_super_admin:
                user.is_super_admin = True
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list_admins(self, *, offset: int = 0, limit: int = 50) -> list[User]:
        stmt = (
            select(User)
            .where(User.is_active.is_(True))
            .order_by(User.is_super_admin.desc(), User.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count_admins(self) -> int:
        stmt = select(func.count()).select_from(User).where(User.is_active.is_(True))
        return int(await self.session.scalar(stmt) or 0)

    async def deactivate(self, user_id: int) -> None:
        await self.session.execute(update(User).where(User.id == user_id).values(is_active=False))
        await self.session.commit()

    async def is_admin(self, user_id: int) -> bool:
        user = await self.get(user_id)
        return user is not None and user.is_active


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, chat_id: int, *, title: str, chat_type: str, bot_is_admin: bool = True) -> Chat:
        chat = await self.session.get(Chat, chat_id)
        if chat is None:
            chat = Chat(
                id=chat_id,
                title=title,
                chat_type=chat_type,
                bot_is_admin=bot_is_admin,
            )
            self.session.add(chat)
        else:
            chat.title = title
            chat.chat_type = chat_type
            chat.bot_is_admin = bot_is_admin
            chat.is_active = True
            chat.status = ChatStatus.ACTIVE.value
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def list_active(self, *, offset: int = 0, limit: int = 50) -> list[Chat]:
        stmt = (
            select(Chat)
            .where(Chat.is_active.is_(True), Chat.bot_is_admin.is_(True))
            .order_by(Chat.title.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count_active(self) -> int:
        stmt = select(func.count()).select_from(Chat).where(
            Chat.is_active.is_(True), Chat.bot_is_admin.is_(True)
        )
        return int(await self.session.scalar(stmt) or 0)

    async def deactivate(self, chat_id: int, *, status: str = ChatStatus.KICKED.value) -> None:
        await self.session.execute(
            update(Chat).where(Chat.id == chat_id).values(
                is_active=False,
                bot_is_admin=False,
                status=status,
            )
        )
        await self.session.commit()

    async def mark_problematic(self, chat_id: int, status: str) -> None:
        await self.deactivate(chat_id, status=status)

    async def reactivate(self, chat_id: int, *, title: str | None = None) -> None:
        values: dict = {
            "is_active": True,
            "bot_is_admin": True,
            "status": ChatStatus.ACTIVE.value,
        }
        if title:
            values["title"] = title
        await self.session.execute(update(Chat).where(Chat.id == chat_id).values(**values))
        await self.session.commit()

    async def list_all(self, *, offset: int = 0, limit: int = 50) -> list[Chat]:
        stmt = (
            select(Chat)
            .order_by(Chat.is_active.desc(), Chat.title.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count_all(self) -> int:
        stmt = select(func.count()).select_from(Chat)
        return int(await self.session.scalar(stmt) or 0)

    async def count_inactive(self) -> int:
        stmt = select(func.count()).select_from(Chat).where(Chat.is_active.is_(False))
        return int(await self.session.scalar(stmt) or 0)

    async def list_inactive(self) -> list[Chat]:
        stmt = select(Chat).where(Chat.is_active.is_(False)).order_by(Chat.title.asc())
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def list_for_monitoring(self) -> list[Chat]:
        stmt = select(Chat).order_by(Chat.id.asc())
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def delete_permanently(self, chat_id: int) -> None:
        await self.session.execute(update(Log).where(Log.chat_id == chat_id).values(chat_id=None))
        await self.session.execute(delete(Chat).where(Chat.id == chat_id))
        await self.session.commit()

    async def delete_all_inactive(self) -> int:
        stmt = select(Chat.id).where(Chat.is_active.is_(False))
        ids = list(await self.session.scalars(stmt))
        if not ids:
            return 0
        await self.session.execute(update(Log).where(Log.chat_id.in_(ids)).values(chat_id=None))
        result = await self.session.execute(delete(Chat).where(Chat.id.in_(ids)))
        await self.session.commit()
        return result.rowcount or len(ids)


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        owner_id: int,
        source_chat_id: int,
        source_message_ids: list[int],
        media_group_id: str | None,
        caption: str | None,
        parse_mode: str | None,
        content_type: str,
    ) -> Post:
        post = Post(
            owner_id=owner_id,
            source_chat_id=source_chat_id,
            source_message_ids=source_message_ids,
            media_group_id=media_group_id,
            caption=caption,
            parse_mode=parse_mode,
            content_type=content_type,
        )
        self.session.add(post)
        await self.session.commit()
        await self.session.refresh(post)
        return post

    async def get(self, post_id: int) -> Post | None:
        stmt = select(Post).where(Post.id == post_id).options(selectinload(Post.excluded_chats))
        return await self.session.scalar(stmt)

    async def list_by_owner(self, owner_id: int, *, offset: int = 0, limit: int = 20) -> list[Post]:
        stmt = (
            select(Post)
            .where(Post.owner_id == owner_id)
            .order_by(Post.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count_by_owner(self, owner_id: int) -> int:
        stmt = select(func.count()).select_from(Post).where(Post.owner_id == owner_id)
        return int(await self.session.scalar(stmt) or 0)

    async def set_interval(self, post_id: int, interval_seconds: int | None) -> None:
        await self.session.execute(
            update(Post).where(Post.id == post_id).values(interval_seconds=interval_seconds)
        )
        await self.session.commit()

    async def set_auto_broadcast(self, post_id: int, enabled: bool) -> None:
        await self.session.execute(
            update(Post).where(Post.id == post_id).values(auto_broadcast_enabled=enabled)
        )
        await self.session.commit()

    async def list_auto_broadcast(self) -> list[Post]:
        stmt = (
            select(Post)
            .where(Post.auto_broadcast_enabled.is_(True))
            .options(selectinload(Post.excluded_chats))
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def set_send_mode(self, post_id: int, send_mode: str) -> None:
        await self.session.execute(
            update(Post).where(Post.id == post_id).values(send_mode=send_mode)
        )
        await self.session.commit()

    async def set_copy_caption(self, post_id: int, copy_caption: str | None) -> None:
        await self.session.execute(
            update(Post).where(Post.id == post_id).values(copy_caption=copy_caption)
        )
        await self.session.commit()

    async def delete(self, post_id: int) -> None:
        await self.session.execute(delete(Post).where(Post.id == post_id))
        await self.session.commit()


class ExclusionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_excluded_ids(self, post_id: int) -> set[int]:
        stmt = select(ExcludedChat.chat_id).where(ExcludedChat.post_id == post_id)
        result = await self.session.scalars(stmt)
        return set(result.all())

    async def toggle(self, post_id: int, chat_id: int) -> bool:
        stmt = select(ExcludedChat).where(
            ExcludedChat.post_id == post_id, ExcludedChat.chat_id == chat_id
        )
        existing = await self.session.scalar(stmt)
        if existing:
            await self.session.delete(existing)
            await self.session.commit()
            return False
        self.session.add(ExcludedChat(post_id=post_id, chat_id=chat_id))
        await self.session.commit()
        return True


class LogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        user_id: int | None,
        action: str,
        chat_id: int | None = None,
        post_id: int | None = None,
        details: str | None = None,
        is_error: bool = False,
    ) -> Log:
        log = Log(
            user_id=user_id,
            chat_id=chat_id,
            post_id=post_id,
            action=action,
            details=details,
            is_error=is_error,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def recent(self, *, offset: int = 0, limit: int = 10) -> list[Log]:
        stmt = (
            select(Log)
            .options(selectinload(Log.user), selectinload(Log.chat))
            .order_by(Log.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count_all(self) -> int:
        stmt = select(func.count()).select_from(Log)
        return int(await self.session.scalar(stmt) or 0)

    async def count_today_sent(self) -> int:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count()).select_from(Log).where(
            Log.action == "broadcast_sent",
            Log.is_error.is_(False),
            Log.created_at >= today,
        )
        return int(await self.session.scalar(stmt) or 0)


class BroadcastJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, post_id: int, user_id: int, total_chats: int) -> BroadcastJob:
        job = BroadcastJob(
            post_id=post_id,
            user_id=user_id,
            total_chats=total_chats,
            status=BroadcastStatus.PENDING.value,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get(self, job_id: int) -> BroadcastJob | None:
        return await self.session.get(BroadcastJob, job_id)

    async def update_progress(
        self,
        job_id: int,
        *,
        sent_count: int | None = None,
        failed_count: int | None = None,
        status: str | None = None,
    ) -> None:
        values: dict = {}
        if sent_count is not None:
            values["sent_count"] = sent_count
        if failed_count is not None:
            values["failed_count"] = failed_count
        if status is not None:
            values["status"] = status
            if status == BroadcastStatus.RUNNING.value:
                values["started_at"] = datetime.now(timezone.utc)
            if status in (BroadcastStatus.COMPLETED.value, BroadcastStatus.STOPPED.value, BroadcastStatus.FAILED.value):
                values["completed_at"] = datetime.now(timezone.utc)
        if values:
            await self.session.execute(update(BroadcastJob).where(BroadcastJob.id == job_id).values(**values))
            await self.session.commit()


class AppSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> str | None:
        from bot.db.models import AppSetting

        row = await self.session.get(AppSetting, key)
        return row.value if row else None

    async def set(self, key: str, value: str) -> None:
        from bot.db.models import AppSetting

        row = await self.session.get(AppSetting, key)
        if row is None:
            self.session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
        await self.session.commit()

