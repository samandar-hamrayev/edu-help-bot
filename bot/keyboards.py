from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def parse_id(callback_data: str | None) -> int | None:
    """Extract the trailing integer from callback data like ``qdetail_42``.

    Callback data comes from the client, so never trust it to be well-formed.
    """
    try:
        return int((callback_data or "").rsplit("_", 1)[-1])
    except ValueError:
        return None


def paginated_keyboard(
    items: list[tuple[str, str]], *, page: int, total: int, page_size: int, nav_prefix: str
) -> InlineKeyboardMarkup:
    """Two buttons per row plus prev/next navigation."""
    buttons = [InlineKeyboardButton(text=text, callback_data=data) for text, data in items]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"{nav_prefix}{page - 1}"))
    if page * page_size < total:
        nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"{nav_prefix}{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)
