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
        self._manual_tasks: dict[int, asyncio.Task] = {}
        self._auto_tasks: dict[int, asyncio.Task] = {}
        self._auto_stop_flags: set[int] = set()

    async def restore_auto_broadcasts(self) -> None:
        async with async_session_factory() as session:
            post_repo = PostRepository(session)
            posts = await post_repo.list_auto_broadcast()
        for post in posts:
            self._start_auto_task(post.id, post.owner_id)

    async def start_manual_broadcast(self, post_id: int, user_id: int) -> int:
        async with async_session_factory() as session:
            post_repo = PostRepository(session)
            chat_repo = ChatRepository(session)
            job_repo = BroadcastJobRepository(session)

            post = await post_repo.get(post_id)
            if post is None:
                raise ValueError(f"Post {post_id} not found")

            target_chats = await self._get_target_chats(post, chat_repo)
            job = await job_repo.create(post_id, user_id, len(target_chats))

        await store_service.set_manual_broadcast_active(job.id, user_id)
        task = asyncio.create_task(self._run_manual_broadcast(job.id, post_id, user_id))
        self._manual_tasks[job.id] = task
        task.add_done_callback(lambda t: self._manual_tasks.pop(job.id, None))
        return job.id

    async def stop_manual_broadcast(self, job_id: int, user_id: int) -> None:
        await store_service.request_manual_stop(job_id)
        await store_service.clear_manual_broadcast(user_id)

    async def start_auto_broadcast(self, post_id: int, user_id: int) -> None:
        async with async_session_factory() as session:
            post_repo = PostRepository(session)
            post = await post_repo.get(post_id)
            if post is None:
                raise ValueError(f"Post {post_id} not found")
            await post_repo.set_auto_broadcast(post_id, True)

        self._auto_stop_flags.discard(post_id)
        self._start_auto_task(post_id, user_id)

    async def stop_auto_broadcast(self, post_id: int) -> None:
        self._auto_stop_flags.add(post_id)
        task = self._auto_tasks.pop(post_id, None)
        if task and not task.done():
            task.cancel()
        async with async_session_factory() as session:
            post_repo = PostRepository(session)
            await post_repo.set_auto_broadcast(post_id, False)

    def is_auto_running(self, post_id: int) -> bool:
        task = self._auto_tasks.get(post_id)
        return task is not None and not task.done()

    def _start_auto_task(self, post_id: int, user_id: int) -> None:
        existing = self._auto_tasks.get(post_id)
        if existing and not existing.done():
            return
        self._auto_stop_flags.discard(post_id)
        task = asyncio.create_task(self._run_auto_loop(post_id, user_id))
        self._auto_tasks[post_id] = task
        task.add_done_callback(lambda t: self._auto_tasks.pop(post_id, None))

    async def _get_target_chats(self, post: Post, chat_repo: ChatRepository) -> list:
        excluded = {e.chat_id for e in post.excluded_chats}
        all_chats = await chat_repo.list_active(limit=10000)
        return [c for c in all_chats if c.id not in excluded]

    async def _run_manual_broadcast(self, job_id: int, post_id: int, user_id: int) -> None:
        async with async_session_factory() as session:
            post_repo = PostRepository(session)
            job_repo = BroadcastJobRepository(session)
            post = await post_repo.get(post_id)
            chat_repo = ChatRepository(session)
            target_chats = await self._get_target_chats(post, chat_repo)
            await job_repo.update_progress(job_id, status=BroadcastStatus.RUNNING.value)

        try:
            sent, failed, stopped = await self._send_round(
                post,
                target_chats,
                user_id,
                job_id=job_id,
                log_action="broadcast_sent",
            )
            async with async_session_factory() as session:
                job_repo = BroadcastJobRepository(session)
                status = BroadcastStatus.STOPPED.value if stopped else BroadcastStatus.COMPLETED.value
                await job_repo.update_progress(
                    job_id, sent_count=sent, failed_count=failed, status=status
                )
        except Exception:
            logger.exception("Manual broadcast job %s crashed", job_id)
            async with async_session_factory() as session:
                job_repo = BroadcastJobRepository(session)
                await job_repo.update_progress(job_id, status=BroadcastStatus.FAILED.value)
        finally:
            await store_service.clear_manual_stop(job_id)
            await store_service.clear_manual_broadcast(user_id)

    async def _run_auto_loop(self, post_id: int, user_id: int) -> None:
        logger.info("Auto broadcast started for post #%s", post_id)
        try:
            while post_id not in self._auto_stop_flags:
                async with async_session_factory() as session:
                    post_repo = PostRepository(session)
                    post = await post_repo.get(post_id)
                    if post is None or not post.auto_broadcast_enabled:
                        break
                    chat_repo = ChatRepository(session)
                    target_chats = await self._get_target_chats(post, chat_repo)

                if not target_chats:
                    logger.warning("Auto broadcast post #%s: no target chats", post_id)
                else:
                    await self._send_round(
                        post,
                        target_chats,
                        user_id,
                        log_action="auto_broadcast_sent",
                    )

                if post_id in self._auto_stop_flags:
                    break

                interval = post.interval_seconds or await store_service.get_default_interval(
                    settings.default_interval
                )
                logger.info("Auto broadcast post #%s: next round in %ss", post_id, interval)
                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    break

                async with async_session_factory() as session:
                    post_repo = PostRepository(session)
                    post = await post_repo.get(post_id)
                    if post is None or not post.auto_broadcast_enabled:
                        break
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Auto broadcast post #%s crashed", post_id)
        finally:
            self._auto_stop_flags.discard(post_id)
            async with async_session_factory() as session:
                post_repo = PostRepository(session)
                await post_repo.set_auto_broadcast(post_id, False)
            logger.info("Auto broadcast stopped for post #%s", post_id)

    async def _send_round(
        self,
        post: Post,
        target_chats: list,
        user_id: int,
        *,
        job_id: int | None = None,
        log_action: str = "broadcast_sent",
    ) -> tuple[int, int, bool]:
        sent = 0
        failed = 0
        stopped = False
        mode_label = "forward" if post.send_mode == SendMode.FORWARD.value else "copy"
        chat_delay = settings.chat_send_delay

        for chat in target_chats:
            if job_id is not None and await store_service.is_manual_stop_requested(job_id):
                stopped = True
                async with async_session_factory() as session:
                    log_repo = LogRepository(session)
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
                        action=log_action,
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

            if job_id is not None:
                async with async_session_factory() as session:
                    job_repo = BroadcastJobRepository(session)
                    await job_repo.update_progress(job_id, sent_count=sent, failed_count=failed)

            if sent + failed < len(target_chats):
                await asyncio.sleep(chat_delay)

        return sent, failed, stopped

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
