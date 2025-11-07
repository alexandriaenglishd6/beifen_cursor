# -*- coding: utf-8 -*-
"""
旗舰模式 Phase 1: 自动化调度中心
无人值守的任务调度系统
"""
from __future__ import annotations
import os
import json
import time
import threading
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"       # 等待执行
    RUNNING = "running"       # 执行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    PAUSED = "paused"         # 暂停
    CANCELLED = "cancelled"   # 取消


class ScheduleType(Enum):
    """调度类型"""
    ONCE = "once"         # 单次执行
    HOURLY = "hourly"     # 每小时
    DAILY = "daily"       # 每天
    WEEKLY = "weekly"     # 每周


@dataclass
class ScheduledTask:
    """调度任务"""
    task_id: str
    name: str
    url: str                    # 频道/播放列表 URL
    schedule_type: str          # 调度类型
    interval: int = 1           # 间隔（小时/天/周）
    next_run: str = ""          # 下次执行时间 (ISO格式)
    last_run: str = ""          # 上次执行时间
    status: str = "pending"
    run_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    config: Dict[str, Any] = None  # 任务配置
    created_at: str = ""
    updated_at: str = ""
    error_msg: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if self.config is None:
            self.config = {}


class TaskScheduler:
    """
    任务调度器（旗舰版核心）
    
    特性：
    - 支持多种调度类型（一次/小时/天/周）
    - 任务状态持久化
    - 自动重试机制
    - 异常恢复
    - 线程安全
    """
    
    def __init__(self, storage_path: str = "config/scheduler.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        
        # 加载已有任务
        self._load_tasks()
        
        logging.info("[SCHEDULER] 调度器初始化完成")
    
    def _load_tasks(self):
        """从存储加载任务"""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for task_data in data.get("tasks", []):
                task = ScheduledTask(**task_data)
                self.tasks[task.task_id] = task
            
            logging.info(f"[SCHEDULER] 已加载 {len(self.tasks)} 个任务")
        
        except Exception as e:
            logging.warning(f"[SCHEDULER] 加载任务失败: {e}")
    
    def _save_tasks(self):
        """保存任务到存储"""
        try:
            data = {
                "tasks": [asdict(task) for task in self.tasks.values()],
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logging.error(f"[SCHEDULER] 保存任务失败: {e}")
    
    def add_task(
        self,
        name: str,
        url: str,
        schedule_type: str = "daily",
        interval: int = 1,
        config: Dict[str, Any] = None
    ) -> str:
        """
        添加调度任务
        
        Args:
            name: 任务名称
            url: 频道/播放列表 URL
            schedule_type: 调度类型 (once/hourly/daily/weekly)
            interval: 间隔
            config: 任务配置
        
        Returns:
            task_id
        """
        with self.lock:
            # 生成任务 ID
            task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.tasks)}"
            
            # 计算下次执行时间
            next_run = self._calculate_next_run(schedule_type, interval)
            
            # 创建任务
            task = ScheduledTask(
                task_id=task_id,
                name=name,
                url=url,
                schedule_type=schedule_type,
                interval=interval,
                next_run=next_run,
                config=config or {}
            )
            
            self.tasks[task_id] = task
            self._save_tasks()
            
            logging.info(f"[SCHEDULER] 已添加任务: {task_id} - {name}")
            
            return task_id
    
    def remove_task(self, task_id: str) -> bool:
        """删除任务"""
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
                self._save_tasks()
                logging.info(f"[SCHEDULER] 已删除任务: {task_id}")
                return True
            return False
    
    def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.PAUSED.value
                self.tasks[task_id].updated_at = datetime.now().isoformat()
                self._save_tasks()
                return True
            return False
    
    def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.PENDING.value
                self.tasks[task_id].updated_at = datetime.now().isoformat()
                self._save_tasks()
                return True
            return False
    
    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """获取任务"""
        return self.tasks.get(task_id)
    
    def list_tasks(self, status: str = None) -> List[ScheduledTask]:
        """列出所有任务"""
        if status:
            return [t for t in self.tasks.values() if t.status == status]
        return list(self.tasks.values())
    
    def _calculate_next_run(self, schedule_type: str, interval: int) -> str:
        """计算下次执行时间"""
        now = datetime.now()
        
        if schedule_type == "once":
            return now.isoformat()
        
        elif schedule_type == "hourly":
            next_run = now + timedelta(hours=interval)
        
        elif schedule_type == "daily":
            next_run = now + timedelta(days=interval)
        
        elif schedule_type == "weekly":
            next_run = now + timedelta(weeks=interval)
        
        else:
            next_run = now + timedelta(days=1)
        
        return next_run.isoformat()
    
    def start(self, executor_callback: Callable[[ScheduledTask], bool]):
        """
        启动调度器
        
        Args:
            executor_callback: 任务执行回调函数，返回 True 表示成功
        """
        if self.running:
            logging.warning("[SCHEDULER] 调度器已在运行")
            return
        
        self.running = True
        self.executor_callback = executor_callback
        
        # 启动调度线程
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="SchedulerThread"
        )
        self.scheduler_thread.start()
        
        logging.info("[SCHEDULER] 调度器已启动")
    
    def stop(self):
        """停止调度器"""
        self.running = False
        
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        logging.info("[SCHEDULER] 调度器已停止")
    
    def _scheduler_loop(self):
        """调度循环（运行在独立线程）"""
        logging.info("[SCHEDULER] 调度循环开始")
        
        while self.running:
            try:
                # 检查待执行任务
                now = datetime.now()
                
                for task_id, task in list(self.tasks.items()):
                    # 跳过非待执行状态
                    if task.status not in [TaskStatus.PENDING.value]:
                        continue
                    
                    # 检查是否到执行时间
                    if task.next_run:
                        next_run_time = datetime.fromisoformat(task.next_run)
                        if now < next_run_time:
                            continue
                    
                    # 执行任务
                    self._execute_task(task)
                
                # 休眠 30 秒后再检查
                time.sleep(30)
            
            except Exception as e:
                logging.error(f"[SCHEDULER] 调度循环错误: {e}")
                time.sleep(60)  # 出错后休眠 1 分钟
        
        logging.info("[SCHEDULER] 调度循环结束")
    
    def _execute_task(self, task: ScheduledTask):
        """执行单个任务"""
        logging.info(f"[SCHEDULER] 开始执行任务: {task.task_id} - {task.name}")
        
        # 更新状态
        with self.lock:
            task.status = TaskStatus.RUNNING.value
            task.last_run = datetime.now().isoformat()
            task.run_count += 1
            self._save_tasks()
        
        # 执行任务（在独立线程中）
        def run_task():
            try:
                success = self.executor_callback(task)
                
                with self.lock:
                    if success:
                        task.status = TaskStatus.COMPLETED.value
                        task.success_count += 1
                        task.error_msg = ""
                    else:
                        task.status = TaskStatus.FAILED.value
                        task.fail_count += 1
                        task.error_msg = "执行失败"
                    
                    # 计算下次执行时间
                    if task.schedule_type != "once":
                        task.next_run = self._calculate_next_run(
                            task.schedule_type,
                            task.interval
                        )
                        task.status = TaskStatus.PENDING.value
                    
                    task.updated_at = datetime.now().isoformat()
                    self._save_tasks()
                
                logging.info(f"[SCHEDULER] 任务完成: {task.task_id} - {'成功' if success else '失败'}")
            
            except Exception as e:
                logging.error(f"[SCHEDULER] 任务执行异常: {task.task_id} - {e}")
                
                with self.lock:
                    task.status = TaskStatus.FAILED.value
                    task.fail_count += 1
                    task.error_msg = str(e)
                    task.updated_at = datetime.now().isoformat()
                    self._save_tasks()
        
        # 在独立线程中执行
        task_thread = threading.Thread(target=run_task, daemon=True)
        task_thread.start()


# 全局调度器实例
_global_scheduler: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    """获取全局调度器实例"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = TaskScheduler()
    return _global_scheduler


# 导出接口
__all__ = [
    'TaskScheduler',
    'ScheduledTask',
    'TaskStatus',
    'ScheduleType',
    'get_scheduler'
]

