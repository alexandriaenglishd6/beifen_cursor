# -*- coding: utf-8 -*-
"""
core.subscription — 订阅管理（持久化、增删改查、导入导出）
"""
from __future__ import annotations
import json, uuid, logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

SUBSCRIPTION_FILE = "config/subscriptions.json"

def _load_subscriptions(path: str = SUBSCRIPTION_FILE) -> dict:
    """加载订阅数据"""
    try:
        p = Path(path)
        if not p.exists():
            return {"version": 1, "items": []}
        data = json.loads(p.read_text("utf-8", errors="ignore"))
        if not isinstance(data, dict) or "items" not in data:
            return {"version": 1, "items": []}
        return data
    except Exception:
        return {"version": 1, "items": []}

def _save_subscriptions(data: dict, path: str = SUBSCRIPTION_FILE):
    """保存订阅数据（原子写）"""
    from .utils import safe_write_json
    safe_write_json(Path(path), data)

def _ts_now() -> str:
    """生成 ISO 格式时间戳"""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def subscribe_add(url: str, kind: str = "channel", title: str = "", 
                  tags: list[str] | None = None, notes: str = "") -> dict:
    """
    添加订阅
    
    kind: "channel" | "playlist" | "url"
    
    返回：{"success": bool, "item": dict | None, "message": str}
    """
    if not url or not url.strip():
        return {"success": False, "item": None, "message": "URL 不能为空"}
    
    url = url.strip()
    data = _load_subscriptions()
    
    # 检查重复
    for item in data["items"]:
        if item["url"] == url:
            return {"success": False, "item": None, "message": "URL 已存在"}
    
    # 生成 ID
    item_id = str(uuid.uuid4())[:8]
    
    # 创建订阅项
    item = {
        "id": item_id,
        "kind": kind,
        "url": url,
        "title": title or "",
        "active": True,
        "tags": tags or [],
        "added_at": _ts_now(),
        "last_seen": None,
        "notes": notes or ""
    }
    
    data["items"].append(item)
    _save_subscriptions(data)
    
    logging.info(f"订阅已添加：{item_id} - {url}")
    return {"success": True, "item": item, "message": "添加成功"}

def subscribe_remove(ids: list[str]) -> int:
    """
    移除订阅
    
    返回：删除的数量
    """
    if not ids:
        return 0
    
    data = _load_subscriptions()
    original_count = len(data["items"])
    
    data["items"] = [item for item in data["items"] if item["id"] not in ids]
    removed = original_count - len(data["items"])
    
    if removed > 0:
        _save_subscriptions(data)
        logging.info(f"已删除 {removed} 个订阅")
    
    return removed

def subscribe_list(active_only: bool = True, tag_filter: list[str] | None = None) -> list[dict]:
    """
    列出订阅
    
    active_only: 只返回启用的订阅
    tag_filter: 标签过滤（包含任一标签即返回）
    
    返回：订阅列表
    """
    data = _load_subscriptions()
    items = data["items"]
    
    # 过滤激活状态
    if active_only:
        items = [item for item in items if item.get("active", True)]
    
    # 过滤标签
    if tag_filter:
        items = [
            item for item in items
            if any(tag in item.get("tags", []) for tag in tag_filter)
        ]
    
    return items

def subscribe_update(item_id: str, **fields) -> dict:
    """
    更新订阅
    
    可更新字段：active, tags, title, notes, last_seen
    
    返回：{"success": bool, "item": dict | None, "message": str}
    """
    data = _load_subscriptions()
    
    for item in data["items"]:
        if item["id"] == item_id:
            # 更新允许的字段
            for key in ["active", "tags", "title", "notes", "last_seen"]:
                if key in fields:
                    item[key] = fields[key]
            
            _save_subscriptions(data)
            logging.info(f"订阅已更新：{item_id}")
            return {"success": True, "item": item, "message": "更新成功"}
    
    return {"success": False, "item": None, "message": f"未找到订阅：{item_id}"}

def subscribe_import(path: str) -> dict:
    """
    导入订阅
    
    支持格式：JSON, CSV
    CSV 格式：url,kind,title,tags(分号分隔)
    
    返回：{"success": bool, "imported": int, "skipped": int, "errors": list[str]}
    """
    import_path = Path(path)
    if not import_path.exists():
        return {"success": False, "imported": 0, "skipped": 0, "errors": ["文件不存在"]}
    
    errors = []
    imported = 0
    skipped = 0
    
    try:
        if import_path.suffix.lower() == ".json":
            # JSON 导入
            import_data = json.loads(import_path.read_text("utf-8"))
            items = import_data.get("items", []) if isinstance(import_data, dict) else import_data
            
            for item in items:
                url = item.get("url", "").strip()
                if not url:
                    skipped += 1
                    continue
                
                result = subscribe_add(
                    url=url,
                    kind=item.get("kind", "channel"),
                    title=item.get("title", ""),
                    tags=item.get("tags", []),
                    notes=item.get("notes", "")
                )
                
                if result["success"]:
                    imported += 1
                else:
                    skipped += 1
        
        elif import_path.suffix.lower() == ".csv":
            # CSV 导入
            import csv
            with import_path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get("url", "").strip()
                    if not url:
                        skipped += 1
                        continue
                    
                    tags_str = row.get("tags", "")
                    tags = [t.strip() for t in tags_str.split(";") if t.strip()] if tags_str else []
                    
                    result = subscribe_add(
                        url=url,
                        kind=row.get("kind", "channel"),
                        title=row.get("title", ""),
                        tags=tags,
                        notes=row.get("notes", "")
                    )
                    
                    if result["success"]:
                        imported += 1
                    else:
                        skipped += 1
        else:
            return {"success": False, "imported": 0, "skipped": 0, "errors": ["不支持的文件格式"]}
    
    except Exception as e:
        errors.append(str(e))
        return {"success": False, "imported": imported, "skipped": skipped, "errors": errors}
    
    return {"success": True, "imported": imported, "skipped": skipped, "errors": errors}

def subscribe_export(path: str, fmt: str = "json") -> str:
    """
    导出订阅
    
    fmt: "json" | "csv"
    
    返回：导出文件路径
    """
    data = _load_subscriptions()
    export_path = Path(path)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if fmt.lower() == "json":
            from .utils import safe_write_json
            safe_write_json(export_path, data)
        
        elif fmt.lower() == "csv":
            import csv
            with export_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["url", "kind", "title", "tags", "active", "notes"])
                writer.writeheader()
                
                for item in data["items"]:
                    writer.writerow({
                        "url": item.get("url", ""),
                        "kind": item.get("kind", ""),
                        "title": item.get("title", ""),
                        "tags": ";".join(item.get("tags", [])),
                        "active": item.get("active", True),
                        "notes": item.get("notes", "")
                    })
        else:
            raise ValueError(f"不支持的格式：{fmt}")
        
        logging.info(f"订阅已导出：{export_path}")
        return str(export_path)
    
    except Exception as e:
        logging.error(f"导出失败：{e}")
        return ""

def build_run_plan_from_subscriptions(
    active_only: bool = True,
    tag_filter: list[str] | None = None,
    max_items_per_source: int | None = None
) -> dict:
    """
    从订阅生成执行计划
    
    返回：{
        "total_sources": int,
        "total_urls": int,
        "sources": [{"id", "kind", "url", "count_est"}],
        "urls": [...]  # 可直接传给 run_full_process(urls_override=...)
    }
    """
    from .detection import extract_all_video_urls_from_channel_or_playlist
    
    items = subscribe_list(active_only=active_only, tag_filter=tag_filter)
    
    sources = []
    all_urls = []
    
    for item in items:
        url = item["url"]
        kind = item.get("kind", "channel")
        
        try:
            if kind in ("channel", "playlist"):
                # 展开频道/播放列表
                urls = extract_all_video_urls_from_channel_or_playlist(url, max_items=max_items_per_source)
                count = len(urls)
                all_urls.extend(urls)
            else:
                # 单个URL
                urls = [url]
                count = 1
                all_urls.append(url)
            
            sources.append({
                "id": item["id"],
                "kind": kind,
                "url": url,
                "count_est": count
            })
        
        except Exception as e:
            logging.warning(f"展开订阅失败 {url}: {e}")
            sources.append({
                "id": item["id"],
                "kind": kind,
                "url": url,
                "count_est": 0
            })
    
    return {
        "total_sources": len(sources),
        "total_urls": len(all_urls),
        "sources": sources,
        "urls": all_urls
    }

