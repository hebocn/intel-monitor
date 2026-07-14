from pydantic import BaseModel
from datetime import datetime


# --- HotTopicSource schemas ---

class HotTopicSourceCreate(BaseModel):
    platform: str
    cron_schedule: str | None = None
    item_limit: int = 30


class HotTopicSourceUpdate(BaseModel):
    is_active: bool | None = None
    cron_schedule: str | None = None
    item_limit: int | None = None


class HotTopicSourceResponse(BaseModel):
    id: int
    platform: str
    is_active: bool
    cron_schedule: str | None
    item_limit: int
    created_at: datetime | None

    model_config = {"from_attributes": True}


# --- HotTopic schemas ---

class HotTopicResponse(BaseModel):
    id: int
    source_id: int
    platform: str
    title: str
    url: str | None
    rank: int | None
    hot_value: str | None
    extra: str | None
    fetched_at: datetime | None

    model_config = {"from_attributes": True}


class FetchRequest(BaseModel):
    source_id: int | None = None
    platforms: list[str] | None = None
