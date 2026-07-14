# intel-monitor/backend/models/intelligence_category.py
from sqlalchemy import Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class IntelligenceCategory(Base):
    __tablename__ = "intelligence_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 1/2/3
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("intelligence_categories.id"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Self-referential relationship for tree
    parent: Mapped["IntelligenceCategory | None"] = relationship(
        "IntelligenceCategory", remote_side="IntelligenceCategory.id", back_populates="children"
    )
    children: Mapped[list["IntelligenceCategory"]] = relationship(
        "IntelligenceCategory", back_populates="parent"
    )

    def to_tree_dict(self) -> dict:
        """递归输出树结构 JSON。"""
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "sort_order": self.sort_order,
            "children": sorted(
                [c.to_tree_dict() for c in self.children if c.is_active],
                key=lambda x: x["sort_order"],
            ),
        }


# ── 预设宗教领域分类 ──────────────────────────────────────────────────────

CATEGORY_SEEDS = [
    # (name, level, parent_index, sort_order)
    # parent_index: 1-based index in the seed list, or None for root
    ("宗教组织与教派研究", 1, None, 10),
    ("境外宗教组织对华渗透", 2, 1, 10),
    ("摩门教专项", 3, 2, 10),
    ("境内新兴宗教团体", 2, 1, 20),
    ("极端教派与异端追踪", 2, 1, 30),
    ("涉宗教物品与出版物流通", 1, None, 20),
    ("网络平台售卖涉宗教物品", 2, 6, 10),
    ("实体渠道流通", 2, 6, 20),
    ("宗教印刷品与数字出版物", 2, 6, 30),
    ("宗教传播与非法活动", 1, None, 30),
    ("非法传教活动", 2, 10, 10),
    ("公众人物/演艺明星宗教影响", 2, 10, 20),
    ("社交媒体宗教传播", 2, 10, 30),
    ("宗教与意识形态安全", 1, None, 40),
    ("宗教舆情事件", 2, 14, 10),
    ("宗教极端主义风险", 2, 14, 20),
    ("宗教干涉内政案例", 2, 14, 30),
    ("宗教政策与法规研究", 1, None, 50),
    ("国内外宗教政策对比", 2, 18, 10),
    ("宗教法律法规适用分析", 2, 18, 20),
]

CATEGORY_SEED_NAMES = [s[0] for s in CATEGORY_SEEDS]
