from pydantic import BaseModel, HttpUrl, field_validator
from datetime import datetime
from typing import Optional


# ---------- Auth ----------
class UserCreate(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Links ----------
class LinkCreate(BaseModel):
    original_url: HttpUrl
    custom_alias: Optional[str] = None
    expires_in_days: Optional[int] = None

    @field_validator("custom_alias")
    @classmethod
    def alias_must_be_safe(cls, v):
        if v is not None:
            if not v.isalnum() or len(v) > 30:
                raise ValueError("custom_alias must be alphanumeric and <= 30 chars")
        return v


class LinkOut(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime]
    is_active: bool
    click_count: int

    class Config:
        from_attributes = True


class LinkStats(LinkOut):
    recent_clicks: list = []
