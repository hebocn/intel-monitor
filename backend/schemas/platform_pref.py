# intel-monitor/backend/schemas/platform_pref.py
from pydantic import BaseModel, Field


class PlatformPrefItem(BaseModel):
    platform: str = Field(..., min_length=1, max_length=20)
    sort_order: int = Field(..., ge=0)


class PlatformPrefSave(BaseModel):
    items: list[PlatformPrefItem] = Field(default_factory=list, max_length=32)
