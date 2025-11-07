# -*- coding: utf-8 -*-
"""
core.__init__.py — 统一对外接口（冻结UI对接面）
"""

from .detection import detect_links
from .download import download_subtitles
from .orchestrator import run_full_process
from .ai_pipeline import run_ai_pipeline, reprocess_ai_errors
from .reporting import export_run_html, export_run_md

# 订阅管理（批次5）
from .subscription import (
    subscribe_add, subscribe_remove, subscribe_list, subscribe_update,
    subscribe_import, subscribe_export, build_run_plan_from_subscriptions
)

# 队列管理（批次6）
from .queue import enqueue_sources, list_queue, run_queue, clear_queue

# 导出（批次7）
from .exports import export_run_csv, export_runs_excel

__all__ = [
    # 核心功能
    "detect_links",
    "download_subtitles",
    "run_full_process",
    "run_ai_pipeline",
    "reprocess_ai_errors",
    "export_run_html",
    "export_run_md",
    # 订阅管理
    "subscribe_add",
    "subscribe_remove",
    "subscribe_list",
    "subscribe_update",
    "subscribe_import",
    "subscribe_export",
    "build_run_plan_from_subscriptions",
    # 队列管理
    "enqueue_sources",
    "list_queue",
    "run_queue",
    "clear_queue",
    # 导出
    "export_run_csv",
    "export_runs_excel",
]

