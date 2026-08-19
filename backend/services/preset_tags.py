# intel-monitor/backend/services/preset_tags.py
from sqlalchemy.ext.asyncio import AsyncSession

from models.tag import Tag

# 新用户初始预置标签（名称, 颜色）
PRESET_TAGS = [
    ("涉T账号", "#F43F5E"),
    ("涉Z账号", "#3B82F6"),
]


async def seed_preset_tags(db: AsyncSession, user_id: int) -> None:
    """为新用户写入初始预置标签。"""
    for name, color in PRESET_TAGS:
        db.add(Tag(user_id=user_id, name=name, color=color, is_preset=True))
    await db.flush()
