from pydantic import BaseModel
from typing import List, Optional, Any

class MessageItem(BaseModel):
    wa_num: str
    sender: str
    text: str
    message_type: str
    message_id: Optional[str] = None
    time: Optional[Any] = None

class StoreMessagesRequest(BaseModel):
    messages: List[MessageItem]

class GetTopMessagesRequest(BaseModel):
    wa_num: str
    top: Optional[int] = 10
