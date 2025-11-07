# -*- coding: utf-8 -*-
"""
旗舰模式 Phase 1: 调度任务执行器
连接调度器与 orchestrator
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Any
from .scheduler import ScheduledTask


def execute_scheduled_task(task: ScheduledTask) -> bool:
    """
    执行调度任务
    
    Args:
        task: 调度任务对象
    
    Returns:
        True if 成功, False otherwise
    """
    try:
        from .orchestrator import run_full_process
        from .config import load_config
        
        logging.info(f"[SCHEDULER-EXEC] 开始执行: {task.name}")
        
        # 加载配置
        cfg = load_config()
        
        # 合并任务配置
        task_cfg = task.config or {}
        
        # 准备参数
        params = {
            "channel_or_playlist_url": task.url,
            "output_root": task_cfg.get("output_root", cfg.get("run", {}).get("output_root", "out")),
            "max_workers": task_cfg.get("max_workers", cfg.get("run", {}).get("max_workers", 20)),
            "do_download": task_cfg.get("do_download", True),
            "download_langs": task_cfg.get("download_langs") or cfg.get("run", {}).get("download_langs", ["zh", "en"]),
            "download_fmt": task_cfg.get("download_fmt", "srt"),
            "incremental_detect": task_cfg.get("incremental_detect", True),
            "incremental_download": task_cfg.get("incremental_download", True),
            "dry_run": False,
            "translate_config": cfg.get("translate", {}),
            "merge_bilingual": cfg.get("bilingual", {}).get("enabled", True)
        }
        
        # 执行任务
        result = run_full_process(**params)
        
        # 判断成功
        success = result.get("total", 0) > 0 and result.get("errors", 0) == 0
        
        logging.info(
            f"[SCHEDULER-EXEC] 完成: {task.name} - "
            f"total={result.get('total')}, downloaded={result.get('downloaded')}, errors={result.get('errors')}"
        )
        
        return success
    
    except Exception as e:
        logging.error(f"[SCHEDULER-EXEC] 执行失败: {task.name} - {e}")
        return False


__all__ = ['execute_scheduled_task']

