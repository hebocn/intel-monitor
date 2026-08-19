# intel-monitor/backend/schemas/account_pref.py
from pydantic import BaseModel, Field


class AccountPrefItem(BaseModel):
    target_id: int
    sort_order: int = Field(..., ge=0)


class AccountPrefSave(BaseModel):
    platform: str = Field(..., min_length=1, max_length=20)
    items: list[AccountPrefItem] = Field(default_factory=list, max_length=500)


class AccountPrefResponse(BaseModel):
    target_id: int
    platform: str
    sort_order: int