# -*- coding: utf-8 -*-
"""
Day 3: 调度引擎（核心）
"""
from __future__ import annotations
import logging
import random
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Callable
from .models import Job, Run, JobFrequency, RunStatus
from .storage import SchedulerStorage


class SchedulerEngine:
    """调度引擎"""
    
    def __init__(self, storage: SchedulerStorage, max_concurrency: int = 2):
        self.storage = storage
        self.max_concurrency = max_concurrency
        self._running_count = 0
        self._running_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._executor_func: Optional[Callable] = None
        
    def set_executor(self, func: Callable):
        """设置执行器函数（orchestrator.run_full_process）"""
        self._executor_func = func
    
    def tick(self, now: Optional[datetime] = None):
        """
        调度tick - 检查并触发到期任务
        
        Args:
            now: 当前时间（测试时可注入）
        """
        if now is None:
            now = datetime.now()
        
        # 获取所有启用的任务
        jobs = self.storage.list_jobs(enabled_only=True)
        
        logging.debug(f"[SCHEDULER] tick at {now.strftime('%H:%M:%S')}, checking {len(jobs)} jobs")
        
        for job in jobs:
            # 计算下次运行时间
            next_run = self._calculate_next_run(job, now)
            
            logging.debug(f"[SCHEDULER] Job {job.id} '{job.name}': next_run={next_run}, now={now}")
            
            # 如果到期，尝试调度
            if next_run and next_run <= now:
                # 检查是否已有该时间点的运行记录（避免重复调度）
                runs = self.storage.get_runs_for_job(job.id, limit=1)
                if runs and runs[0].scheduled_time >= next_run:
                    logging.debug(f"[SCHEDULER] Job {job.id} already ran recently, skip")
                    continue
                
                logging.info(f"[SCHEDULER] Dispatching job {job.id} '{job.name}' (next_run={next_run})")
                self._try_dispatch(job, next_run, now)
    
    def run_once(self, job_id: int):
        """立即运行一次任务（不改变计划）"""
        job = self.storage.get_job(job_id)
        if not job:
            logging.error(f"[SCHEDULER] Job {job_id} not found")
            return
        
        now = datetime.now()
        scheduled_time = now
        
        # 创建run记录
        run = Run(
            job_id=job.id,
            scheduled_time=scheduled_time,
            status=RunStatus.QUEUED
        )
        
        run_id = self.storage.create_run(run)
        if run_id == 0:
            logging.warning(f"[SCHEDULER] Run already exists for job {job_id} at {scheduled_time}")
            return
        
        run.id = run_id
        
        # 在后台线程执行
        thread = threading.Thread(target=self._execute_run, args=(job, run))
        thread.daemon = True
        thread.start()
    
    def _try_dispatch(self, job: Job, scheduled_time: datetime, now: datetime):
        """尝试调度任务"""
        # 检查锁
        lock_name = f"job:{job.id}"
        owner = f"scheduler_{threading.current_thread().ident}"
        
        if not self.storage.acquire_lock(lock_name, owner, ttl_seconds=3600):
            logging.debug(f"[SCHEDULER] Job {job.id} is locked, skip")
            return
        
        try:
            # 检查并发限制
            with self._running_lock:
                if self._running_count >= self.max_concurrency:
                    logging.debug(f"[SCHEDULER] Max concurrency reached, skip job {job.id}")
                    return
                self._running_count += 1
            
            # 添加抖动
            jitter = random.randint(0, job.jitter_sec)
            actual_time = now + timedelta(seconds=jitter)
            
            # 创建run记录
            run = Run(
                job_id=job.id,
                scheduled_time=scheduled_time,
                status=RunStatus.QUEUED
            )
            
            run_id = self.storage.create_run(run)
            if run_id == 0:
                logging.debug(f"[SCHEDULER] Run already exists for job {job.id}")
                with self._running_lock:
                    self._running_count -= 1
                return
            
            run.id = run_id
            
            # 延迟执行（抖动）
            if jitter > 0:
                time.sleep(jitter)
            
            # 在后台线程执行
            thread = threading.Thread(target=self._execute_run_with_cleanup, 
                                     args=(job, run, lock_name, owner))
            thread.daemon = True
            thread.start()
        
        except Exception as e:
            logging.error(f"[SCHEDULER] Dispatch error: {e}")
            with self._running_lock:
                self._running_count -= 1
            self.storage.release_lock(lock_name, owner)
    
    def _execute_run_with_cleanup(self, job: Job, run: Run, lock_name: str, owner: str):
        """执行run并清理资源"""
        try:
            self._execute_run(job, run)
        finally:
            with self._running_lock:
                self._running_count -= 1
            self.storage.release_lock(lock_name, owner)
    
    def _execute_run(self, job: Job, run: Run):
        """执行单次运行"""
        logging.info(f"[SCHEDULER] Starting run {run.id} for job {job.id} ({job.name})")
        
        # 更新状态为running
        run.status = RunStatus.RUNNING
        run.start_time = datetime.now()
        self.storage.update_run(run)
        
        max_retries = 3
        retry_delays = [60, 120, 240]  # 秒
        
        for attempt in range(max_retries + 1):
            try:
                # 调用执行器
                if self._executor_func is None:
                    raise Exception("Executor not set")
                
                result = self._executor_func(
                    source_url=job.source_url,
                    output_root=job.output_root,
                    preferred_langs=job.preferred_langs,
                    do_download=job.do_download
                )
                
                # 成功
                run.status = RunStatus.SUCCESS
                run.end_time = datetime.now()
                run.run_dir = result.get("run_dir", "")
                run.error_text = ""
                self.storage.update_run(run)
                
                logging.info(f"[SCHEDULER] Run {run.id} succeeded")
                
                # 清理旧记录
                self.storage.cleanup_old_runs(job.id, keep_count=100)
                
                # 通知webhook（占位）
                self._notify_webhook("job_finished", {
                    "job_id": job.id,
                    "job_name": job.name,
                    "run_id": run.id,
                    "status": "success",
                    "run_dir": run.run_dir
                })
                
                return
            
            except Exception as e:
                error_msg = str(e)
                
                # 判断是否需要重试
                if self._should_retry(error_msg) and attempt < max_retries:
                    delay = retry_delays[attempt]
                    logging.warning(f"[SCHEDULER] Run {run.id} failed (attempt {attempt + 1}/{max_retries}), retry in {delay}s: {error_msg[:100]}")
                    
                    run.retry_count = attempt + 1
                    self.storage.update_run(run)
                    
                    time.sleep(delay)
                else:
                    # 最终失败
                    run.status = RunStatus.ERROR
                    run.end_time = datetime.now()
                    run.error_text = error_msg[:500]  # 截断
                    run.retry_count = attempt
                    self.storage.update_run(run)
                    
                    logging.error(f"[SCHEDULER] Run {run.id} failed after {attempt + 1} attempts: {error_msg[:200]}")
                    
                    # 通知webhook
                    self._notify_webhook("job_failed", {
                        "job_id": job.id,
                        "job_name": job.name,
                        "run_id": run.id,
                        "status": "error",
                        "error": error_msg[:200]
                    })
                    
                    return
    
    def _should_retry(self, error_msg: str) -> bool:
        """判断错误是否应该重试"""
        retry_keywords = [
            "429", "403", "5", "network", "timeout", 
            "connection", "temporarily unavailable"
        ]
        error_lower = error_msg.lower()
        return any(kw in error_lower for kw in retry_keywords)
    
    def _calculate_next_run(self, job: Job, now: datetime) -> Optional[datetime]:
        """
        计算下次运行时间
        
        注意：这里计算的是"应该运行的时间点"，即使已经过期，也返回那个时间点，
        由tick中的逻辑来判断是否应该立即触发。
        """
        if job.frequency == JobFrequency.HOURLY:
            # 每小时的指定分钟
            next_run = now.replace(minute=job.byminute, second=0, microsecond=0)
            # 如果这个时间点已经过了很久（超过10分钟），则跳到下一小时
            if (now - next_run).total_seconds() > 600:  # 10分钟
                next_run += timedelta(hours=1)
            return next_run
        
        elif job.frequency == JobFrequency.DAILY:
            # 每天的指定时间
            next_run = now.replace(hour=job.byhour, minute=job.byminute, second=0, microsecond=0)
            # 如果这个时间点已经过了很久（超过1小时），则跳到明天
            if (now - next_run).total_seconds() > 3600:  # 1小时
                next_run += timedelta(days=1)
            return next_run
        
        elif job.frequency == JobFrequency.WEEKLY:
            # 每周指定星期的指定时间
            if job.weekday is None:
                return None
            
            current_weekday = now.weekday()
            days_ahead = job.weekday - current_weekday
            
            if days_ahead < 0 or (days_ahead == 0 and now.hour * 60 + now.minute >= job.byhour * 60 + job.byminute + 60):
                days_ahead += 7
            
            next_run = now + timedelta(days=days_ahead)
            next_run = next_run.replace(hour=job.byhour, minute=job.byminute, second=0, microsecond=0)
            return next_run
        
        return None
    
    def _notify_webhook(self, event: str, payload: dict):
        """发送webhook通知（占位）"""
        # 占位实现，后续可扩展
        pass
    
    def stop(self):
        """停止引擎"""
        self._stop_event.set()
        logging.info("[SCHEDULER] Engine stopping...")

