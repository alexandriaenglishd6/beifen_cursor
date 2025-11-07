# -*- coding: utf-8 -*-
"""
Day 3: 调度器数据模型
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum


class JobFrequency(str, Enum):
    """任务频率"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


class JobStatus(str, Enum):
    """任务状态"""
    ENABLED = "enabled"
    DISABLED = "disabled"


class RunStatus(str, Enum):
    """运行状态"""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class Job:
    """调度任务"""
    id: Optional[int] = None
    name: str = ""
    enabled: bool = True
    frequency: JobFrequency = JobFrequency.HOURLY
    byhour: int = 0  # 0-23
    byminute: int = 0  # 0-59
    weekday: Optional[int] = None  # 0-6 (Monday=0), weekly专用
    jitter_sec: int = 90
    output_root: str = "out"
    preferred_langs: List[str] = field(default_factory=lambda: ["zh", "en"])
    do_download: bool = True
    source_url: str = ""  # 频道/播放列表URL
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    next_run: Optional[datetime] = None  # 下次运行时间（计算得出）
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "frequency": self.frequency.value if isinstance(self.frequency, JobFrequency) else self.frequency,
            "byhour": self.byhour,
            "byminute": self.byminute,
            "weekday": self.weekday,
            "jitter_sec": self.jitter_sec,
            "output_root": self.output_root,
            "preferred_langs": self.preferred_langs,
            "do_download": self.do_download,
            "source_url": self.source_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
        }


@dataclass
class Run:
    """运行记录"""
    id: Optional[int] = None
    job_id: int = 0
    scheduled_time: Optional[datetime] = None  # 计划运行时间
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: RunStatus = RunStatus.QUEUED
    error_text: str = ""
    run_dir: str = ""
    retry_count: int = 0
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value if isinstance(self.status, RunStatus) else self.status,
            "error_text": self.error_text,
            "run_dir": self.run_dir,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class Lock:
    """锁记录"""
    name: str
    owner: str
    expires_at: datetime
    created_at: Optional[datetime] = None

