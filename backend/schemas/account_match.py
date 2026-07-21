# intel-monitor/backend/schemas/account_match.py
from datetime import datetime
from pydantic import BaseModel, Field, model_validator


class AccountMatchSearchRequest(BaseModel):
    target_name: str = Field(..., min_length=1, max_length=200)
    platforms: list[str] = Field(..., min_length=1)
    match_mode: str = Field(default="nickname", description="'profile' or 'nickname'")
    anchor_platform: str | None = Field(default=None, description="When match_mode='profile', the platform of the anchor user ('weibo' or 'x')")


class AccountMatchCandidateResponse(BaseModel):
    id: int
    task_id: int
    platform: str
    platform_uid: str
    nickname: str
    avatar_url: str | None
    bio: str | None
    followers_count: int
    profile_url: str | None
    profile_json: str | None
    posts_json: str | None
    match_score: float = 0.0
    score_detail_json: str | None = None
    matched_with: str | None = None

    @model_validator(mode='before')
    @classmethod
    def coerce_nulls(cls, data: dict) -> dict:
        if isinstance(data, dict):
            for fld in ('match_score', 'score_detail_json', 'matched_with'):
                if data.get(fld) is None:
                    if fld == 'match_score':
                        data[fld] = 0.0
                    elif fld == 'score_detail_json':
                        data[fld] = '{}'
                    else:
                        data[fld] = ''
        elif hasattr(data, '__dict__'):
            # Handle ORM object
            if hasattr(data, 'match_score') and data.match_score is None:
                data.match_score = 0.0
            if hasattr(data, 'score_detail_json') and data.score_detail_json is None:
                data.score_detail_json = '{}'
            if hasattr(data, 'matched_with') and data.matched_with is None:
                data.matched_with = ''
        return data

    model_config = {"from_attributes": True}


class AccountMatchResultResponse(BaseModel):
    id: int
    task_id: int
    group_label: str
    confidence_score: float
    account_ids_json: str
    ai_analysis: str | None
    score_detail: str | None = None

    model_config = {"from_attributes": True}


class AccountMatchTaskResponse(BaseModel):
    id: int
    target_name: str
    platforms: str
    status: str
    match_mode: str | None = "nickname"
    total_candidates: int
    total_groups: int
    error_log: str | None
    anchor_profile_json: str | None = None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class AccountMatchTaskDetailResponse(AccountMatchTaskResponse):
    candidates: list[AccountMatchCandidateResponse]
    results: list[AccountMatchResultResponse]


class AccountMatchTaskListResponse(BaseModel):
    tasks: list[AccountMatchTaskResponse]
    total: int
