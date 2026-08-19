# intel-monitor/backend/schemas/tag.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator

# 标签固定色板（与前端 components/TagPill.tsx 保持一致）
ALLOWED_TAG_COLORS = [
    "#22C55E", "#3B82F6", "#06B6D4", "#A78BFA",
    "#F59E0B", "#F43F5E", "#EC4899", "#94A3B8",
]


def _check_color(v: str) -> str:
    if v not in ALLOWED_TAG_COLORS:
        raise ValueError(f"颜色必须是色板中的值: {ALLOWED_TAG_COLORS}")
    return v


class TagBrief(BaseModel):
    id: int
    name: str
    color: str

    model_config = {"from_attributes": True}


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=10)
    color: str = Field(...)

    @field_validator("color")
    @classmethod
    def color_in_palette(cls, v: str) -> str:
        return _check_color(v)


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=10)
    color: Optional[str] = None

    @field_validator("color")
    @classmethod
    def color_in_palette(cls, v: Optional[str]) -> Optional[str]:
        return _check_color(v) if v else v


class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    is_preset: bool
    created_at: datetime
    target_count: int = 0

    model_config = {"from_attributes": True}


class TargetTagSetRequest(BaseModel):
    """单个账号：整体替换标签集合。"""
    tag_ids: list[int] = Field(default_factory=list)


class TargetTagBatchRequest(BaseModel):
    """批量：向多个账号添加/移除标签，至少一项非空。"""
    target_ids: list[int] = Field(..., min_length=1)
    add_tag_ids: list[int] = Field(default_factory=list)
    remove_tag_ids: list[int] = Field(default_factory=list)
