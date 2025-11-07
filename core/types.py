# -*- coding: utf-8 -*-
"""
core.types — 通用类型定义（提升类型安全）
"""
from typing import TypedDict, Optional, List, Dict, Any


class VideoMetadata(TypedDict, total=False):
    """视频元数据结构"""
    title: Optional[str]
    upload_date: Optional[str]  # "YYYYMMDD"
    duration: Optional[int]
    view_count: Optional[int]
    tags: List[str]
    channel: Optional[str]
    channel_id: Optional[str]


class DetectionResult(TypedDict):
    """检测结果结构"""
    url: str
    video_id: str
    status: str  # "has_subs" | "no_subs" | "error_*"
    manual_langs: List[str]
    auto_langs: List[str]
    all_langs: List[str]
    attempts: int
    latency_ms: float
    api_err: Optional[str]
    meta: VideoMetadata


class RunSummary(TypedDict):
    """运行摘要结构"""
    run_dir: str
    total: int
    downloaded: int
    errors: int
    last_seen: Optional[str]


class AIMetrics(TypedDict, total=False):
    """AI 调用指标"""
    provider: str
    model: str
    tokens: int
    cost_usd: float
    latency_ms: float
    error_type: Optional[str]


class AIResult(TypedDict):
    """AI 处理结果"""
    summary: str
    key_points: List[str]
    keywords: List[str]
    meta: AIMetrics


class ChapterItem(TypedDict):
    """章节条目"""
    title: str
    start: Optional[str]  # "HH:MM:SS"


class WebhookConfig(TypedDict, total=False):
    """Webhook 配置"""
    url: str
    timeout_sec: int
    max_retry: int
    secret: str
    enable: bool
    events: List[str]


class WebhookPayload(TypedDict):
    """Webhook 消息体"""
    event: str
    run_dir: str
    stats: Dict[str, Any]
    budget: Dict[str, Any]
    proxies: Dict[str, Any]
    ts: str


__all__ = [
    "VideoMetadata",
    "DetectionResult",
    "RunSummary",
    "AIMetrics",
    "AIResult",
    "ChapterItem",
    "WebhookConfig",
    "WebhookPayload",
]

