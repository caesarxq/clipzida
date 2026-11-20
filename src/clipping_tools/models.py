"""Typed stage contracts for the clipping pipeline (Pydantic v2, explicit context)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Platform(str, Enum):
    TWITCH = "twitch"
    KICK = "kick"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    X = "x"
    FACEBOOK = "facebook"


class Angle(str, Enum):
    FUNNY = "funny"
    HYPE = "hype"
    NEWS = "news"


class GateStatus(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    FAIL = "fail"


class ClipCandidate(BaseModel):
    source_platform: Platform
    external_id: str
    url: str
    title: str = ""
    broadcaster_id: str = ""
    broadcaster_name: str = ""
    creator_name: str = ""
    view_count: int = 0
    duration: float = 0.0
    language: str = ""
    created_at: datetime
    thumbnail_url: str = ""
    video_id: str = ""
    vod_offset: int | None = None
    score: float = 0.0
    angle: Angle | None = None


class Word(BaseModel):
    word: str
    start: float
    end: float


class EnergyPeak(BaseModel):
    t: float
    rms: float


class AnalysisResult(BaseModel):
    clip_id: int
    words: list[Word] = []
    energy_peaks: list[EnergyPeak] = []
    model: str = ""


class MomentSelection(BaseModel):
    start: float
    end: float
    hook_title: str
    hook_text: str = ""
    reason: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    spoiler_flags: list[str] = []
    angle: Angle = Angle.FUNNY

    @property
    def duration(self) -> float:
        return self.end - self.start


class ComplianceVerdict(BaseModel):
    rights: GateStatus = GateStatus.FAIL
    rockstar: GateStatus = GateStatus.FAIL
    campaign: GateStatus = GateStatus.FAIL
    platform: GateStatus = GateStatus.FAIL
    reasons: list[str] = []

    @property
    def ok(self) -> bool:
        return all(g == GateStatus.PASS for g in (self.rights, self.rockstar, self.campaign, self.platform))

    @property
    def needs_review(self) -> bool:
        return not self.ok and any(g == GateStatus.REVIEW for g in (self.rights, self.rockstar, self.campaign, self.platform)) and not any(g == GateStatus.FAIL for g in (self.rights, self.rockstar, self.campaign, self.platform))


class RenderSpec(BaseModel):
    clip_id: int
    layout: str = "gaming-split"
    style: str = "classic"
    start: float
    end: float
    variants: list[str] = ["tiktok", "youtube", "instagram", "x"]


class PostDraft(BaseModel):
    render_id: int
    campaign_id: int | None = None
    platform: Platform
    account: str
    caption: str
    hashtags: list[str] = []
    attribution: str = ""
    scheduled_at: datetime | None = None
    idempotency_key: str


class PublishResult(BaseModel):
    post_id: int
    platform: Platform
    status: str
    external_post_id: str | None = None
    url: str | None = None
    error: str | None = None


class MetricsSnapshot(BaseModel):
    post_id: int
    fetched_at: datetime
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    approved_views: int = 0
    payout: float = 0.0