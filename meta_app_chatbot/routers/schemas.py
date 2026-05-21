from typing import Any

from pydantic import BaseModel


class MessageItem(BaseModel):
    wa_num: str
    sender: str
    text: str
    message_type: str
    message_id: str | None = None
    time: Any | None = None


class StoreMessagesRequest(BaseModel):
    messages: list[MessageItem]


class GetTopMessagesRequest(BaseModel):
    wa_num: str
    top: int | None = 10
