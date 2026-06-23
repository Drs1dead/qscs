import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.enums import ParseMode

from bot.config import get_settings
from bot.db.models import BroadcastStatus, Post, SendMode
from bot.db.repositories import BroadcastJobRepository, ChatRepository, LogRepository, PostRepository
from bot.db.session import async_session_factory
from bot.services.store_service import store_service

logger = logging.getLogger(__name__)
settings = get_settings()


class BroadcastService:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._running_tasks: dict[int, asyncio.Task] = {}

    async def start_broadcast(self, post_id: int, user_id: int) -> int:
        async with async_session_factory() as session:
            post_repo = PostRepository(session)
            chat_repo = ChatRepository(session)
            job_repo = BroadcastJobRepository(session)

            post = await post_repo.get(post_id)
            if post is None:
                raise ValueError(f"Post {post_id} not found")

            excluded = {e.chat_id for e in post.excluded_chats}
            all_chats = await chat_repo.list_active(limit=10000)
            target_chats = [c for c in all_chats if c.id not in excluded]

            job = await job_repo.create(post_id, user_id, len(target_chats))

        await store_service.set_broadcast_active(job.id, user_id)
        task = asyncio.create_task(self._run_broadcast(job.id, post, target_chats, user_id))
        self._running_tasks[job.id] = task
        task.add_done_callback(lambda t: self._running_tasks.pop(job.id, None))
        return job.id

    async def stop_broadcast(self, job_id: int, user_id: int) -> None:
        await store_service.request_stop(job_id)
        await store_service.clear_active_broadcast(user_id)

    async def _run_broadcast(
        self,
        job_id: int,
        post: Post,
        target_chats: list,
        user_id: int,
    ) -> None:
        interval = post.interval_seconds or await store_service.get_default_interval(settings.default_interval)
        sent = 0
        failed = 0
        mode_label = "forward" if post.send_mode == SendMode.FORWARD.value else "copy"

        async with async_session_factory() as session:
            job_repo = BroadcastJobRepository(session)
            await job_repo.update_progress(job_id, status=BroadcastStatus.RUNNING.value)

        try:
            for chat in target_chats:
                if await store_service.is_stop_requested(job_id):
                    async with async_session_factory() as session:
                        job_repo = BroadcastJobRepository(session)
                        log_repo = LogRepository(session)
                        await job_repo.update_progress(
                            job_id, sent_count=sent, failed_count=failed, status=BroadcastStatus.STOPPED.value
                        )
                        await log_repo.add(
                            user_id=user_id,
                            post_id=post.id,
                            action="broadcast_stopped",
                            details=f"Остановлено на {sent}/{len(target_chats)}",
                        )
                    break

                try:
                    await self._send_post(post, chat.id)
                    sent += 1
                    async with async_session_factory() as session:
                        log_repo = LogRepository(session)
                        await log_repo.add(
                            user_id=user_id,
                            post_id=post.id,
                            chat_id=chat.id,
                            action="broadcast_sent",
                            details=f"Отправлено ({mode_label}) в «{chat.title}»",
                        )
                except TelegramAPIError as exc:
                    failed += 1
                    logger.warning("Send failed chat=%s post=%s: %s", chat.id, post.id, exc)
                    async with async_session_factory() as session:
                        log_repo = LogRepository(session)
                        chat_repo = ChatRepository(session)
                        await log_repo.add(
                            user_id=user_id,
                            post_id=post.id,
                            chat_id=chat.id,
                            action="broadcast_error",
                            details=str(exc),
                            is_error=True,
                        )
                        if "bot was kicked" in str(exc).lower() or "not enough rights" in str(exc).lower():
                            await chat_repo.deactivate(chat.id)

                async with async_session_factory() as session:
                    job_repo = BroadcastJobRepository(session)
                    await job_repo.update_progress(job_id, sent_count=sent, failed_count=failed)

                if sent + failed < len(target_chats):
                    await asyncio.sleep(interval)
            else:
                async with async_session_factory() as session:
                    job_repo = BroadcastJobRepository(session)
                    await job_repo.update_progress(
                        job_id,
                        sent_count=sent,
                        failed_count=failed,
                        status=BroadcastStatus.COMPLETED.value,
                    )
        except Exception:
            logger.exception("Broadcast job %s crashed", job_id)
            async with async_session_factory() as session:
                job_repo = BroadcastJobRepository(session)
                await job_repo.update_progress(
                    job_id,
                    sent_count=sent,
                    failed_count=failed,
                    status=BroadcastStatus.FAILED.value,
                )
        finally:
            await store_service.clear_stop(job_id)
            await store_service.clear_active_broadcast(user_id)

    async def _send_post(self, post: Post, target_chat_id: int) -> None:
        if post.send_mode == SendMode.COPY.value:
            await self._copy_post(post, target_chat_id)
        else:
            await self._forward_post(post, target_chat_id)

    async def _forward_post(self, post: Post, target_chat_id: int) -> None:
        for message_id in post.source_message_ids:
            await self.bot.forward_message(
                chat_id=target_chat_id,
                from_chat_id=post.source_chat_id,
                message_id=message_id,
            )
            if len(post.source_message_ids) > 1:
                await asyncio.sleep(0.05)

    async def _copy_post(self, post: Post, target_chat_id: int) -> None:
        if post.content_type == "text" and post.copy_caption:
            await self.bot.send_message(
                target_chat_id,
                post.copy_caption,
                parse_mode=ParseMode.HTML,
            )
            return

        for index, message_id in enumerate(post.source_message_ids):
            kwargs: dict = {}
            if index == 0 and post.copy_caption:
                kwargs["caption"] = post.copy_caption
                kwargs["parse_mode"] = ParseMode.HTML
            await self.bot.copy_message(
                chat_id=target_chat_id,
                from_chat_id=post.source_chat_id,
                message_id=message_id,
                **kwargs,
            )
            if len(post.source_message_ids) > 1:
                await asyncio.sleep(0.05)
