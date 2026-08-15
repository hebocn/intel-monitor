# intel-monitor/backend/routers/weather.py
"""台风/极端天气数据接口（免认证，只读公开数据）。"""
from fastapi import APIRouter

from schemas.weather import (
    TyphoonDetail,
    TyphoonListResponse,
    WarningsResponse,
)
from services import weather

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/typhoons", response_model=TyphoonListResponse)
async def get_typhoons():
    """活跃台风（NMC）+ 存档台风（本地库）列表。免认证（只读公开数据）。"""
    return await weather.get_typhoons()


@router.get("/typhoons/{typhoon_id}", response_model=TyphoonDetail)
async def get_typhoon_detail(typhoon_id: str):
    """单台风轨迹 + 风圈详情。NMC 优先，失败回退本地存档。"""
    return await weather.get_typhoon_detail(typhoon_id)


@router.get("/warnings", response_model=WarningsResponse)
async def get_warnings():
    """当前生效极端天气预警列表（含经纬度）。"""
    return await weather.get_warnings()
