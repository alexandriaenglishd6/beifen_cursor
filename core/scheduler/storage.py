# -*- coding: utf-8 -*-
"""
Day 3: 调度器存储层（SQLite）
"""
from __future__ import annotations
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from .models import Job, Run, Lock, JobFrequency, JobStatus, RunStatus


class SchedulerStorage:
    """调度器持久化存储"""
    
    def __init__(self, db_path: str = "scheduler.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        try:
            # jobs 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    frequency TEXT NOT NULL,
                    byhour INTEGER NOT NULL DEFAULT 0,
                    byminute INTEGER NOT NULL DEFAULT 0,
                    weekday INTEGER,
                    jitter_sec INTEGER NOT NULL DEFAULT 90,
                    output_root TEXT NOT NULL,
                    preferred_langs TEXT NOT NULL,
                    do_download INTEGER NOT NULL DEFAULT 1,
                    source_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # runs 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    scheduled_time TEXT NOT NULL,
                    start_time TEXT,
                    end_time TEXT,
                    status TEXT NOT NULL,
                    error_text TEXT,
                    run_dir TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                    UNIQUE(job_id, scheduled_time)
                )
            """)
            
            # locks 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS locks (
                    name TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            
            # 索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_job_id ON runs(job_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_locks_expires ON locks(expires_at)")
            
            conn.commit()
        finally:
            conn.close()
    
    def create_job(self, job: Job) -> int:
        """创建任务"""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                INSERT INTO jobs (name, enabled, frequency, byhour, byminute, weekday, 
                                jitter_sec, output_root, preferred_langs, do_download, 
                                source_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.name,
                1 if job.enabled else 0,
                job.frequency.value if isinstance(job.frequency, JobFrequency) else job.frequency,
                job.byhour,
                job.byminute,
                job.weekday,
                job.jitter_sec,
                job.output_root,
                json.dumps(job.preferred_langs),
                1 if job.do_download else 0,
                job.source_url,
                now,
                now
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def update_job(self, job: Job) -> bool:
        """更新任务"""
        if not job.id:
            return False
        
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                UPDATE jobs SET name=?, enabled=?, frequency=?, byhour=?, byminute=?, 
                              weekday=?, jitter_sec=?, output_root=?, preferred_langs=?, 
                              do_download=?, source_url=?, updated_at=?
                WHERE id=?
            """, (
                job.name,
                1 if job.enabled else 0,
                job.frequency.value if isinstance(job.frequency, JobFrequency) else job.frequency,
                job.byhour,
                job.byminute,
                job.weekday,
                job.jitter_sec,
                job.output_root,
                json.dumps(job.preferred_langs),
                1 if job.do_download else 0,
                job.source_url,
                now,
                job.id
            ))
            conn.commit()
            return True
        finally:
            conn.close()
    
    def delete_job(self, job_id: int) -> bool:
        """删除任务"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            conn.commit()
            return True
        finally:
            conn.close()
    
    def get_job(self, job_id: int) -> Optional[Job]:
        """获取任务"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            return self._row_to_job(row)
        finally:
            conn.close()
    
    def list_jobs(self, enabled_only: bool = False) -> List[Job]:
        """列出所有任务"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            sql = "SELECT * FROM jobs"
            if enabled_only:
                sql += " WHERE enabled=1"
            sql += " ORDER BY created_at DESC"
            
            rows = conn.execute(sql).fetchall()
            return [self._row_to_job(row) for row in rows]
        finally:
            conn.close()
    
    def create_run(self, run: Run) -> int:
        """创建运行记录"""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                INSERT INTO runs (job_id, scheduled_time, start_time, end_time, status, 
                                error_text, run_dir, retry_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run.job_id,
                run.scheduled_time.isoformat() if run.scheduled_time else now,
                run.start_time.isoformat() if run.start_time else None,
                run.end_time.isoformat() if run.end_time else None,
                run.status.value if isinstance(run.status, RunStatus) else run.status,
                run.error_text,
                run.run_dir,
                run.retry_count,
                now
            ))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # 同一scheduled_time已存在
            return 0
        finally:
            conn.close()
    
    def update_run(self, run: Run) -> bool:
        """更新运行记录"""
        if not run.id:
            return False
        
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                UPDATE runs SET start_time=?, end_time=?, status=?, error_text=?, 
                              run_dir=?, retry_count=?
                WHERE id=?
            """, (
                run.start_time.isoformat() if run.start_time else None,
                run.end_time.isoformat() if run.end_time else None,
                run.status.value if isinstance(run.status, RunStatus) else run.status,
                run.error_text,
                run.run_dir,
                run.retry_count,
                run.id
            ))
            conn.commit()
            return True
        finally:
            conn.close()
    
    def get_runs_for_job(self, job_id: int, limit: int = 100) -> List[Run]:
        """获取任务的运行记录（最新N条）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT * FROM runs WHERE job_id=? 
                ORDER BY created_at DESC LIMIT ?
            """, (job_id, limit)).fetchall()
            return [self._row_to_run(row) for row in rows]
        finally:
            conn.close()
    
    def cleanup_old_runs(self, job_id: int, keep_count: int = 100):
        """清理旧的运行记录（只保留最新N条）"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                DELETE FROM runs WHERE job_id=? AND id NOT IN (
                    SELECT id FROM runs WHERE job_id=? 
                    ORDER BY created_at DESC LIMIT ?
                )
            """, (job_id, job_id, keep_count))
            conn.commit()
        finally:
            conn.close()
    
    def acquire_lock(self, name: str, owner: str, ttl_seconds: int = 3600) -> bool:
        """获取锁"""
        now = datetime.now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        
        conn = sqlite3.connect(self.db_path)
        try:
            # 清理过期锁
            conn.execute("DELETE FROM locks WHERE expires_at < ?", (now.isoformat(),))
            
            # 尝试插入锁
            try:
                conn.execute("""
                    INSERT INTO locks (name, owner, expires_at, created_at)
                    VALUES (?, ?, ?, ?)
                """, (name, owner, expires_at.isoformat(), now.isoformat()))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # 锁已存在
                return False
        finally:
            conn.close()
    
    def release_lock(self, name: str, owner: str) -> bool:
        """释放锁"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM locks WHERE name=? AND owner=?", (name, owner))
            conn.commit()
            return True
        finally:
            conn.close()
    
    def _row_to_job(self, row: sqlite3.Row) -> Job:
        """将数据库行转换为Job对象"""
        return Job(
            id=row["id"],
            name=row["name"],
            enabled=bool(row["enabled"]),
            frequency=JobFrequency(row["frequency"]),
            byhour=row["byhour"],
            byminute=row["byminute"],
            weekday=row["weekday"],
            jitter_sec=row["jitter_sec"],
            output_root=row["output_root"],
            preferred_langs=json.loads(row["preferred_langs"]),
            do_download=bool(row["do_download"]),
            source_url=row["source_url"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )
    
    def _row_to_run(self, row: sqlite3.Row) -> Run:
        """将数据库行转换为Run对象"""
        return Run(
            id=row["id"],
            job_id=row["job_id"],
            scheduled_time=datetime.fromisoformat(row["scheduled_time"]) if row["scheduled_time"] else None,
            start_time=datetime.fromisoformat(row["start_time"]) if row["start_time"] else None,
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            status=RunStatus(row["status"]),
            error_text=row["error_text"] or "",
            run_dir=row["run_dir"] or "",
            retry_count=row["retry_count"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None
        )

