# -*- coding: utf-8 -*-
"""
导出服务 - 纯业务逻辑，不依赖UI
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
from export_manager import ExportManager


class ExportService:
    """
    导出服务
    
    职责：
    1. 导出调度任务
    2. 导出订阅列表
    3. 导出日志内容
    4. 导出通用数据
    """
    
    def export_scheduler_jobs(
        self,
        jobs: List[Dict[str, Any]],
        format: str = "excel",
        output_path: Optional[Path] = None
    ) -> Path:
        """
        导出调度任务
        
        Args:
            jobs: 任务列表
            format: 导出格式 ('excel', 'csv', 'json', 'markdown')
            output_path: 输出路径（可选）
        
        Returns:
            输出文件路径
        """
        return ExportManager.export_scheduler_jobs(
            jobs=jobs,
            format=format,
            output_path=output_path
        )
    
    def export_subscriptions(
        self,
        subscriptions: List[Dict[str, Any]],
        format: str = "excel",
        output_path: Optional[Path] = None
    ) -> Path:
        """
        导出订阅列表
        
        Args:
            subscriptions: 订阅列表
            format: 导出格式
            output_path: 输出路径（可选）
        
        Returns:
            输出文件路径
        """
        return ExportManager.export_subscriptions(
            subscriptions=subscriptions,
            format=format,
            output_path=output_path
        )
    
    def export_logs(
        self,
        log_content: str,
        format: str = "txt",
        output_path: Optional[Path] = None
    ) -> Path:
        """
        导出日志内容
        
        Args:
            log_content: 日志文本内容
            format: 导出格式（'txt', 'markdown'）
            output_path: 输出路径（可选）
        
        Returns:
            输出文件路径
        """
        return ExportManager.export_logs(
            log_content=log_content,
            format=format,
            output_path=output_path
        )


__all__ = ['ExportService']

