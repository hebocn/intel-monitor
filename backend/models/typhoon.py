from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, UniqueConstraint, func
from database import Base


class TyphoonTrack(Base):
    """台风轨迹点存档表（每次抓取 upsert，台风活跃期间自然积累历史）。

    - 实况点 is_forecast=False，预报点 is_forecast=True（来自 NMC BABJ 机构预报）
    - obs_time 统一存 naive UTC（项目红线，源数据为北京时间，入库前减 8 小时）
    - 新表由 database.py 的 create_all 自动创建，不涉及现有表 ALTER
    """

    __tablename__ = "typhoon_tracks"
    __table_args__ = (
        UniqueConstraint("typhoon_id", "obs_time", "is_forecast", name="uq_typhoon_point"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    typhoon_id = Column(String(16), nullable=False, index=True)  # NMC 台风编号
    name = Column(String(64), nullable=True)                      # 中文名（无命名时为"热带低压"）
    obs_time = Column(DateTime, nullable=False)                   # naive UTC
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    pressure = Column(Float, nullable=True)                       # 中心气压 hPa
    wind_speed = Column(Float, nullable=True)                     # 最大风速 m/s
    level = Column(String(16), nullable=True)                     # TD/TS/STS/TY/STY/SuperTY
    is_forecast = Column(Boolean, default=False, nullable=False)
    radius7 = Column(Float, nullable=True)                        # 7 级风圈半径 km（四象限均值）
    radius10 = Column(Float, nullable=True)                       # 10 级风圈半径 km（四象限均值）
    created_at = Column(DateTime, server_default=func.now())
