from aiogram.types import Message

from bot.db.repositories import PostRepository
from bot.db.session import async_session_factory


def extract_message_meta(message: Message) -> dict:
    content_type = message.content_type
    caption = message.caption or message.text
    parse_mode = None
    if message.caption:
        parse_mode = "HTML" if message.caption_entities else None
    elif message.text and message.entities:
        parse_mode = "HTML"

    return {
        "content_type": content_type,
        "caption": caption,
        "parse_mode": parse_mode,
    }


async def save_post_from_messages(
    owner_id: int,
    messages: list[Message],
) -> int:
    first = messages[0]
    # Messages live in the chat where the bot received them (DM with admin).
    # forward_message uses these IDs to preserve Premium emoji and formatting.
    source_chat_id = first.chat.id

    message_ids = sorted(m.message_id for m in messages)
    media_group_id = first.media_group_id
    meta = extract_message_meta(first)

    async with async_session_factory() as session:
        repo = PostRepository(session)
        post = await repo.create(
            owner_id=owner_id,
            source_chat_id=source_chat_id,
            source_message_ids=message_ids,
            media_group_id=media_group_id,
            caption=meta["caption"],
            parse_mode=meta["parse_mode"],
            content_type=meta["content_type"],
        )
        return post.id
