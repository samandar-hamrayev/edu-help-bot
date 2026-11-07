"""Shared fixtures.

The Telegram API is never called: ``FakeBot`` overrides ``Bot.__call__`` (the
single choke point every aiogram API method goes through) and records calls.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetChatMember, TelegramMethod
from aiogram.types import CallbackQuery, Chat, ChatMemberMember, Message, Update, User
from asgiref.sync import sync_to_async
from django.db import connections

from bot import membership
from bot.dispatcher import build_dispatcher
from core.models import TelegramUser

ADMIN_ID = 1000
STUDENT_ID = 2000
OTHER_STUDENT_ID = 3000

_ids = itertools.count(1)


class FakeBot(Bot):
    def __init__(self) -> None:
        super().__init__(token="123456:TEST-TOKEN-NOT-REAL")
        self.calls: list[TelegramMethod] = []
        # Map method class -> value, exception instance, or callable(method) -> value.
        self.responses: dict[type, Any] = {}

    async def __call__(self, method: TelegramMethod, request_timeout: int | None = None) -> Any:
        self.calls.append(method)
        response = self.responses.get(type(method))
        if callable(response) and not isinstance(response, type):
            response = response(method)
        if isinstance(response, BaseException):
            raise response
        if response is not None:
            return response
        if isinstance(method, GetChatMember):
            return ChatMemberMember(user=User(id=method.user_id, is_bot=False, first_name="x"))
        return True

    def sent(self, method_type: type, chat_id: int | None = None) -> list[TelegramMethod]:
        return [c for c in self.calls if isinstance(c, method_type) and (chat_id is None or c.chat_id == chat_id)]

    def texts(self, chat_id: int | None = None) -> list[str]:
        from aiogram.methods import SendMessage

        return [c.text for c in self.sent(SendMessage, chat_id)]


@pytest.fixture(autouse=True)
async def _close_async_db_connections():
    """Async ORM calls run in asgiref's worker thread, which holds its own DB
    connection; close it after each test so the test DB can be dropped."""
    yield
    await sync_to_async(connections.close_all)()


@pytest.fixture
def bot() -> FakeBot:
    return FakeBot()


@pytest.fixture(scope="session")
def _dispatcher() -> Dispatcher:
    # aiogram routers are module-level singletons and can be attached only once.
    return build_dispatcher(MemoryStorage())


@pytest.fixture
def dp(_dispatcher: Dispatcher) -> Dispatcher:
    _dispatcher.storage.storage.clear()  # fresh FSM state for every test
    return _dispatcher


@pytest.fixture(autouse=True)
def _bot_settings(settings):
    settings.TELEGRAM_ADMINS = frozenset({ADMIN_ID})
    settings.REQUIRED_CHATS = []
    membership.clear_cache()
    yield
    membership.clear_cache()


def tg_user(user_id: int, first_name: str = "Ali", username: str | None = None) -> User:
    return User(id=user_id, is_bot=False, first_name=first_name, username=username, language_code="uz")


def make_message(user_id: int, text: str | None = None, **extra: Any) -> Message:
    return Message(
        message_id=next(_ids),
        date=datetime.now(UTC),
        chat=Chat(id=user_id, type="private"),
        from_user=tg_user(user_id),
        text=text,
        **extra,
    )


def make_callback(user_id: int, data: str) -> CallbackQuery:
    return CallbackQuery(
        id=str(next(_ids)),
        from_user=tg_user(user_id),
        chat_instance="test",
        data=data,
        message=make_message(user_id, "previous message"),
    )


@pytest.fixture
def send(dp: Dispatcher, bot: FakeBot) -> Callable:
    """Feed a message (str) or callback (via ``callback=``) through the full dispatcher."""

    async def _send(user_id: int, text: str | None = None, *, callback: str | None = None, **extra: Any):
        if callback is not None:
            update = Update(update_id=next(_ids), callback_query=make_callback(user_id, callback))
        else:
            update = Update(update_id=next(_ids), message=make_message(user_id, text, **extra))
        return await dp.feed_update(bot, update)

    return _send


@pytest.fixture
def make_user(db) -> Callable[..., TelegramUser]:
    def _make(telegram_id: int, **kwargs: Any) -> TelegramUser:
        kwargs.setdefault("first_name", f"User{telegram_id}")
        return TelegramUser.objects.create(telegram_id=telegram_id, **kwargs)

    return _make
