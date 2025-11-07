# -*- coding: utf-8 -*-
"""
调度器服务 - 纯业务逻辑
"""
from typing import List, Dict, Optional
from pathlib import Path

try:
    from core.scheduler import SchedulerEngine, SchedulerStorage
    from gui_scheduler_handler import SchedulerUI
    from core.scheduler.ticker import SchedulerTicker
    HAS_SCHEDULER = True
except ImportError:
    HAS_SCHEDULER = False
    print("[SchedulerService] Warning: Scheduler modules not found")


class SchedulerService:
    """
    调度器服务
    
    职责：
    1. 管理调度任务（增删改查）
    2. 启动/停止调度器
    3. 执行任务
    """
    
    def __init__(self, config: Dict):
        """
        初始化
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.scheduler_ui: Optional[SchedulerUI] = None
        self.scheduler_engine: Optional[SchedulerEngine] = None
        self.scheduler_storage: Optional[SchedulerStorage] = None
        self.scheduler_ticker: Optional[SchedulerTicker] = None
        
        if HAS_SCHEDULER:
            self._init_scheduler()
    
    def _init_scheduler(self):
        """初始化调度器"""
        try:
            # 获取配置
            scheduler_cfg = self.config.get("scheduler", {
                "enabled": True,
                "db_path": "scheduler.db",
                "default_jitter_sec": 90,
                "max_concurrency": 2,
                "notify_webhook": ""
            })
            
            # 初始化存储和引擎
            self.scheduler_storage = SchedulerStorage(scheduler_cfg.get("db_path", "scheduler.db"))
            self.scheduler_engine = SchedulerEngine(
                storage=self.scheduler_storage,
                max_concurrency=scheduler_cfg.get("max_concurrency", 2)
            )
            
            # 设置执行器（将在控制器中设置）
            # self.scheduler_engine.set_executor(...)
            
            # 初始化UI封装
            self.scheduler_ui = SchedulerUI(
                engine=self.scheduler_engine,
                storage=self.scheduler_storage,
                notify=lambda event, payload: print(f"[Scheduler] {event}: {payload}")
            )
            
            print("[SchedulerService] 调度器初始化成功")
            
        except Exception as e:
            print(f"[SchedulerService] 初始化失败: {e}")
            import traceback
            traceback.print_exc()
    
    def is_available(self) -> bool:
        """调度器是否可用"""
        return HAS_SCHEDULER and self.scheduler_ui is not None
    
    def list_jobs(self) -> List[Dict]:
        """
        列出所有任务
        
        Returns:
            任务列表
        """
        if not self.scheduler_ui:
            return []
        
        try:
            return self.scheduler_ui.list_jobs()
        except Exception as e:
            print(f"[SchedulerService] 列出任务失败: {e}")
            return []
    
    def create_job(self, form_data: Dict) -> int:
        """
        创建任务
        
        Args:
            form_data: 表单数据
        
        Returns:
            任务ID
        """
        if not self.scheduler_ui:
            raise RuntimeError("调度器未初始化")
        
        return self.scheduler_ui.create_job(form_data)
    
    def update_job(self, job_id: int, form_data: Dict):
        """
        更新任务
        
        Args:
            job_id: 任务ID
            form_data: 表单数据
        """
        if not self.scheduler_ui:
            raise RuntimeError("调度器未初始化")
        
        self.scheduler_ui.update_job(job_id, form_data)
    
    def delete_job(self, job_id: int):
        """
        删除任务
        
        Args:
            job_id: 任务ID
        """
        if not self.scheduler_ui:
            raise RuntimeError("调度器未初始化")
        
        self.scheduler_ui.delete_job(job_id)
    
    def toggle_job(self, job_id: int, enabled: bool):
        """
        切换任务状态
        
        Args:
            job_id: 任务ID
            enabled: 是否启用
        """
        if not self.scheduler_ui:
            raise RuntimeError("调度器未初始化")
        
        self.scheduler_ui.toggle_job(job_id, enabled)
    
    def run_job_once(self, job_id: int):
        """
        立即运行一次任务
        
        Args:
            job_id: 任务ID
        """
        if not self.scheduler_ui:
            raise RuntimeError("调度器未初始化")
        
        self.scheduler_ui.run_once(job_id)
    
    def start_scheduler(self) -> bool:
        """
        启动调度器
        
        Returns:
            是否成功
        """
        if not self.scheduler_engine:
            return False
        
        # 检查是否已有ticker在运行
        if self.scheduler_ticker and self.scheduler_ticker.is_running():
            return False
        
        try:
            # 初始化ticker（如果还没有）
            if not self.scheduler_ticker:
                self.scheduler_ticker = SchedulerTicker(
                    engine=self.scheduler_engine,
                    interval_sec=60  # 每60秒tick一次
                )
            
            # 启动ticker
            self.scheduler_ticker.start()
            return True
            
        except Exception as e:
            print(f"[SchedulerService] 启动失败: {e}")
            return False
    
    def stop_scheduler(self) -> bool:
        """
        停止调度器
        
        Returns:
            是否成功
        """
        if not self.scheduler_ticker:
            return False
        
        if not self.scheduler_ticker.is_running():
            return False
        
        try:
            self.scheduler_ticker.stop(timeout=5.0)
            return True
        except Exception as e:
            print(f"[SchedulerService] 停止失败: {e}")
            return False
    
    def is_running(self) -> bool:
        """
        调度器是否在运行
        
        Returns:
            是否运行中
        """
        if not self.scheduler_ticker:
            return False
        return self.scheduler_ticker.is_running()
    
    def get_tick_interval(self) -> int:
        """
        获取tick间隔（秒）
        
        Returns:
            tick间隔秒数，如果未初始化则返回60
        """
        if not self.scheduler_ticker:
            return 60
        return self.scheduler_ticker.interval
    
    def get_last_tick_time(self) -> Optional[float]:
        """
        获取上次tick时间（时间戳）
        
        Returns:
            上次tick时间戳，如果未运行则返回None
        """
        if not self.scheduler_ticker or not self.scheduler_ticker.is_running():
            return None
        # 注意：SchedulerTicker没有直接暴露last_tick_time
        # 这里返回None，由控制器自己跟踪
        return None


__all__ = ['SchedulerService']

