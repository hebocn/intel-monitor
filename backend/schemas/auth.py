# intel-monitor/backend/schemas/auth.py
from pydantic import BaseModel, Field


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SetupStatusResponse(BaseModel):
    needs_setup: bool


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=4, max_length=100)
