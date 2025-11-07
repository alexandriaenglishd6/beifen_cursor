# -*- coding: utf-8 -*-
"""
调度看门狗 - 检测卡死、清理孤儿锁、失败隔离
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path


class SchedulerWatchdog:
    """调度器看门狗"""
    
    def __init__(self, storage, config: Dict):
        """
        初始化看门狗
        
        Args:
            storage: SchedulerStorage实例
            config: 看门狗配置
        """
        self.storage = storage
        self.enabled = config.get("enabled", True)
        self.stuck_timeout_multiplier = config.get("stuck_timeout_multiplier", 1.5)
        self.max_consecutive_failures = config.get("max_consecutive_failures", 3)
        self.event_log = Path(config.get("event_log", "logs/watchdog_events.jsonl"))
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
    
    def check_and_heal(self):
        """执行检查与自愈"""
        if not self.enabled:
            return
        
        logging.debug("[WATCHDOG] 开始巡检...")
        
        # 1. 检测卡死运行
        self._check_stuck_runs()
        
        # 2. 清理孤儿锁
        self._clean_orphan_locks()
        
        # 3. 检查连续失败
        self._check_consecutive_failures()
    
    def _check_stuck_runs(self):
        """检测卡死的运行"""
        try:
            # 获取所有running状态的runs
            conn = self.storage.conn
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, job_id, start_time
                FROM runs
                WHERE status = 'running'
            """)
            
            running_runs = cursor.fetchall()
            now = datetime.now()
            
            for run_id, job_id, start_time_str in running_runs:
                start_time = datetime.fromisoformat(start_time_str)
                elapsed = (now - start_time).total_seconds()
                
                # 获取job的timeout配置（假设默认1800秒）
                timeout = 1800  # 可以从job配置中读取
                
                if elapsed > timeout * self.stuck_timeout_multiplier:
                    logging.warning(f"[WATCHDOG] 检测到卡死运行: run_id={run_id}, elapsed={elapsed:.0f}s")
                    
                    # 标记为timeout
                    cursor.execute("""
                        UPDATE runs
                        SET status = 'timeout',
                            end_time = ?,
                            error = 'Stuck kill by watchdog'
                        WHERE id = ?
                    """, (now.isoformat(), run_id))
                    
                    # 释放锁
                    cursor.execute("DELETE FROM locks WHERE run_id = ?", (run_id,))
                    
                    conn.commit()
                    
                    # 记录事件
                    self._log_event({
                        "type": "stuck_kill",
                        "run_id": run_id,
                        "job_id": job_id,
                        "elapsed_sec": elapsed
                    })
        
        except Exception as e:
            logging.error(f"[WATCHDOG] 检查卡死运行失败: {e}")
    
    def _clean_orphan_locks(self):
        """清理孤儿锁"""
        try:
            conn = self.storage.conn
            cursor = conn.cursor()
            
            now = datetime.now()
            
            # 删除过期锁
            cursor.execute("""
                DELETE FROM locks
                WHERE expires_at < ?
            """, (now.isoformat(),))
            
            deleted_count = cursor.rowcount
            
            if deleted_count > 0:
                logging.info(f"[WATCHDOG] 清理{deleted_count}个过期锁")
                conn.commit()
                
                self._log_event({
                    "type": "orphan_lock_cleanup",
                    "count": deleted_count
                })
        
        except Exception as e:
            logging.error(f"[WATCHDOG] 清理孤儿锁失败: {e}")
    
    def _check_consecutive_failures(self):
        """检查连续失败的job"""
        try:
            conn = self.storage.conn
            cursor = conn.cursor()
            
            # 获取所有enabled的job
            cursor.execute("SELECT id, name FROM jobs WHERE enabled = 1")
            jobs = cursor.fetchall()
            
            for job_id, job_name in jobs:
                # 获取最近N次运行
                cursor.execute("""
                    SELECT status
                    FROM runs
                    WHERE job_id = ?
                    ORDER BY start_time DESC
                    LIMIT ?
                """, (job_id, self.max_consecutive_failures))
                
                recent_statuses = [row[0] for row in cursor.fetchall()]
                
                # 检查是否全部失败
                if len(recent_statuses) >= self.max_consecutive_failures:
                    if all(status in ['error', 'timeout'] for status in recent_statuses):
                        logging.error(f"[WATCHDOG] Job {job_name} 连续{len(recent_statuses)}次失败，建议暂停")
                        
                        # 可选：自动禁用job
                        # cursor.execute("UPDATE jobs SET enabled = 0 WHERE id = ?", (job_id,))
                        # conn.commit()
                        
                        self._log_event({
                            "type": "consecutive_failures",
                            "job_id": job_id,
                            "job_name": job_name,
                            "failure_count": len(recent_statuses)
                        })
        
        except Exception as e:
            logging.error(f"[WATCHDOG] 检查连续失败失败: {e}")
    
    def _log_event(self, event: Dict):
        """记录看门狗事件"""
        try:
            import json
            
            event["timestamp"] = datetime.now().isoformat()
            
            with open(self.event_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
        
        except Exception as e:
            logging.warning(f"[WATCHDOG] 记录事件失败: {e}")

