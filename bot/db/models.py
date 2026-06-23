from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class BroadcastStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatStatus(StrEnum):
    ACTIVE = "active"
    KICKED = "kicked"
    NOT_FOUND = "not_found"
    NO_RIGHTS = "no_rights"


class SendMode(StrEnum):
    FORWARD = "forward"
    COPY = "copy"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    posts: Mapped[list["Post"]] = relationship(back_populates="owner")
    logs: Mapped[list["Log"]] = relationship(back_populates="user")


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(512), default="Без названия")
    chat_type: Mapped[str] = mapped_column(String(32), default="unknown")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    bot_is_admin: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default=ChatStatus.ACTIVE.value)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    source_chat_id: Mapped[int] = mapped_column(BigInteger)
    source_message_ids: Mapped[list] = mapped_column(JSON, default=list)
    media_group_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_type: Mapped[str] = mapped_column(String(32), default="text")
    send_mode: Mapped[str] = mapped_column(String(16), default=SendMode.FORWARD.value)
    copy_caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_broadcast_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship(back_populates="posts")
    excluded_chats: Mapped[list["ExcludedChat"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    logs: Mapped[list["Log"]] = relationship(back_populates="post")


class ExcludedChat(Base):
    __tablename__ = "excluded_chats"
    __table_args__ = (UniqueConstraint("post_id", "chat_id", name="uq_post_chat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), index=True)

    post: Mapped["Post"] = relationship(back_populates="excluded_chats")
    chat: Mapped["Chat"] = relationship()


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True, index=True)
    post_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("posts.id"), nullable=True, index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("chats.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    user: Mapped["User | None"] = relationship(back_populates="logs")
    post: Mapped["Post | None"] = relationship(back_populates="logs")
    chat: Mapped["Chat | None"] = relationship()


class BroadcastJob(Base):
    __tablename__ = "broadcast_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default=BroadcastStatus.PENDING.value, index=True)
    total_chats: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))
