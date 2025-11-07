# -*- coding: utf-8 -*-
"""
core.queue — 队列与并行管理（多来源批处理）
"""
from __future__ import annotations
import json, logging, time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

QUEUE_STATE_FILE = "config/queue_state.json"

def _load_queue_state(path: str = QUEUE_STATE_FILE) -> dict:
    """加载队列状态"""
    try:
        p = Path(path)
        if not p.exists():
            return {"version": 1, "runs": []}
        data = json.loads(p.read_text("utf-8", errors="ignore"))
        if not isinstance(data, dict) or "runs" not in data:
            return {"version": 1, "runs": []}
        return data
    except Exception:
        return {"version": 1, "runs": []}

def _save_queue_state(data: dict, path: str = QUEUE_STATE_FILE):
    """保存队列状态（原子写）"""
    from .utils import safe_write_json
    safe_write_json(Path(path), data)

def _ts_now() -> str:
    """生成 ISO 格式时间戳"""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def enqueue_sources(sources: list[dict], tags: list[str] | None = None) -> str:
    """
    将来源加入队列
    
    sources: [{"id", "kind", "url"}, ...]
    tags: 可选标签
    
    返回：run_id
    """
    if not sources:
        return ""
    
    data = _load_queue_state()
    
    # 生成唯一 run_id
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    run_item = {
        "id": run_id,
        "sources": sources,
        "tags": tags or [],
        "status": "pending",
        "started_at": None,
        "ended_at": None,
        "summary": {"ok": 0, "fail": 0, "ai_guard_stop": 0}
    }
    
    data["runs"].append(run_item)
    _save_queue_state(data)
    
    logging.info(f"队列已添加：{run_id}，包含 {len(sources)} 个来源")
    return run_id

def list_queue() -> dict:
    """
    列出队列状态
    
    返回：{
        "total": int,
        "pending": int,
        "running": int,
        "done": int,
        "error": int,
        "runs": [...]
    }
    """
    data = _load_queue_state()
    runs = data["runs"]
    
    status_count = {
        "pending": 0,
        "running": 0,
        "done": 0,
        "error": 0,
        "stopped": 0
    }
    
    for run in runs:
        status = run.get("status", "pending")
        status_count[status] = status_count.get(status, 0) + 1
    
    return {
        "total": len(runs),
        **status_count,
        "runs": runs
    }

def run_queue(
    max_parallel: int = 2,
    run_opts: dict | None = None,
    stop_event=None,
    pause_event=None
) -> dict:
    """
    执行队列
    
    max_parallel: 并行任务数
    run_opts: 传递给 run_full_process 的选项
    
    返回：{"total": int, "success": int, "failed": int, "skipped": int}
    """
    from .orchestrator import run_full_process
    import random
    
    data = _load_queue_state()
    pending_runs = [r for r in data["runs"] if r.get("status") == "pending"]
    
    if not pending_runs:
        logging.info("队列为空，无需执行")
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0}
    
    logging.info(f"开始执行队列，待处理 {len(pending_runs)} 项，并行度 {max_parallel}")
    
    run_opts = run_opts or {}
    total = len(pending_runs)
    success = 0
    failed = 0
    skipped = 0
    
    def _run_one(run_item: dict) -> dict:
        """执行单个队列项"""
        run_id = run_item["id"]
        sources = run_item["sources"]
        
        # 检查中断
        if stop_event and stop_event.is_set():
            logging.info(f"队列已中断：{run_id}")
            return {"run_id": run_id, "status": "stopped", "summary": {}}
        
        # 更新状态为运行中
        run_item["status"] = "running"
        run_item["started_at"] = _ts_now()
        _save_queue_state(data)
        
        try:
            # 组合所有来源的 URLs
            all_urls = []
            for src in sources:
                url = src.get("url", "")
                if url:
                    all_urls.append(url)
            
            if not all_urls:
                logging.warning(f"队列项无有效 URL：{run_id}")
                return {"run_id": run_id, "status": "error", "summary": {"ok": 0, "fail": 0}}
            
            # 调用 run_full_process
            result = run_full_process(
                urls_override=all_urls,
                stop_event=stop_event,
                pause_event=pause_event,
                **run_opts
            )
            
            # 汇总结果
            summary = {
                "ok": result.get("downloaded", 0),
                "fail": result.get("errors", 0),
                "ai_guard_stop": 0,  # TODO: 从 result 中提取
                "run_dir": result.get("run_dir", "")
            }
            
            # 更新状态为完成
            run_item["status"] = "done"
            run_item["ended_at"] = _ts_now()
            run_item["summary"] = summary
            _save_queue_state(data)
            
            logging.info(f"队列项完成：{run_id}，成功 {summary['ok']}，失败 {summary['fail']}")
            return {"run_id": run_id, "status": "done", "summary": summary}
        
        except Exception as e:
            logging.error(f"队列项失败：{run_id}，错误：{e}")
            
            # 更新状态为错误
            run_item["status"] = "error"
            run_item["ended_at"] = _ts_now()
            run_item["summary"] = {"ok": 0, "fail": 1, "error": str(e)}
            _save_queue_state(data)
            
            return {"run_id": run_id, "status": "error", "summary": {}}
    
    # 并行执行
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = {}
        
        for run_item in pending_runs:
            # 检查中断
            if stop_event and stop_event.is_set():
                skipped += 1
                continue
            
            # 同一频道相邻任务加随机延迟（公平调度）
            time.sleep(random.uniform(0.1, 0.3))
            
            future = executor.submit(_run_one, run_item)
            futures[future] = run_item["id"]
        
        # 等待完成
        for future in as_completed(futures):
            result = future.result()
            status = result.get("status", "error")
            
            if status == "done":
                success += 1
            elif status == "stopped":
                skipped += 1
            else:
                failed += 1
    
    logging.info(f"队列执行完成，总计 {total}，成功 {success}，失败 {failed}，跳过 {skipped}")
    
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "skipped": skipped
    }

def clear_queue(mode: str = "done_only") -> int:
    """
    清理队列
    
    mode:
        - "done_only": 只清理已完成的
        - "all": 清理所有
        - "error_only": 只清理错误的
    
    返回：清理数量
    """
    data = _load_queue_state()
    original_count = len(data["runs"])
    
    if mode == "done_only":
        data["runs"] = [r for r in data["runs"] if r.get("status") != "done"]
    elif mode == "error_only":
        data["runs"] = [r for r in data["runs"] if r.get("status") != "error"]
    elif mode == "all":
        data["runs"] = []
    else:
        logging.warning(f"未知清理模式：{mode}")
        return 0
    
    cleared = original_count - len(data["runs"])
    
    if cleared > 0:
        _save_queue_state(data)
        logging.info(f"已清理队列 {cleared} 项（模式：{mode}）")
    
    return cleared

