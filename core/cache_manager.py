# -*- coding: utf-8 -*-
"""
缓存管理器 - LRU清理、限额控制
"""
import os
import json
import logging
import hashlib
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class CacheManager:
    """ASR缓存管理器"""
    
    def __init__(self, cache_dir: str, config: Dict):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录
            config: 缓存配置
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 配置
        self.max_size_gb = config.get("max_size_gb", 10.0)
        self.max_entries = config.get("max_entries", 1000)
        self.ttl_days = config.get("ttl_days", 30)
        
        # 元数据文件
        self.meta_file = self.cache_dir / "cache_meta.json"
        self.meta = self._load_meta()
    
    def _load_meta(self) -> Dict:
        """加载缓存元数据"""
        if not self.meta_file.exists():
            return {}
        
        try:
            with open(self.meta_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"[CACHE] 加载元数据失败: {e}")
            return {}
    
    def _save_meta(self):
        """保存缓存元数据"""
        try:
            with open(self.meta_file, 'w', encoding='utf-8') as f:
                json.dump(self.meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"[CACHE] 保存元数据失败: {e}")
    
    def get(self, key: str) -> Optional[str]:
        """
        获取缓存文件路径
        
        Args:
            key: 缓存键
        
        Returns:
            缓存文件路径，不存在返回None
        """
        cache_file = self.cache_dir / f"{key}.srt"
        
        if not cache_file.exists():
            return None
        
        # 更新访问时间
        if key in self.meta:
            self.meta[key]["last_access"] = datetime.now().isoformat()
            self.meta[key]["hit_count"] = self.meta[key].get("hit_count", 0) + 1
            self._save_meta()
        
        logging.info(f"[CACHE] 命中: {key}")
        return str(cache_file)
    
    def put(self, key: str, file_path: str) -> bool:
        """
        添加缓存
        
        Args:
            key: 缓存键
            file_path: 源文件路径
        
        Returns:
            是否成功
        """
        try:
            cache_file = self.cache_dir / f"{key}.srt"
            
            # 复制文件
            shutil.copy2(file_path, cache_file)
            
            # 记录元数据
            file_size = cache_file.stat().st_size
            self.meta[key] = {
                "created": datetime.now().isoformat(),
                "last_access": datetime.now().isoformat(),
                "size_bytes": file_size,
                "hit_count": 0
            }
            self._save_meta()
            
            logging.info(f"[CACHE] 新增: {key} ({file_size} bytes)")
            
            # 检查是否需要清理
            self.prune_if_needed()
            
            return True
        
        except Exception as e:
            logging.error(f"[CACHE] 添加失败: {e}")
            return False
    
    def prune_if_needed(self):
        """根据限额清理缓存"""
        # 1. 删除过期项
        self._prune_expired()
        
        # 2. 检查条目数
        if len(self.meta) > self.max_entries:
            self._prune_by_lru(self.max_entries)
        
        # 3. 检查总大小
        total_size_gb = self._get_total_size_gb()
        if total_size_gb > self.max_size_gb:
            self._prune_by_size(self.max_size_gb)
    
    def _prune_expired(self):
        """删除过期缓存"""
        cutoff_date = datetime.now() - timedelta(days=self.ttl_days)
        expired_keys = []
        
        for key, meta in self.meta.items():
            created = datetime.fromisoformat(meta["created"])
            if created < cutoff_date:
                expired_keys.append(key)
        
        if expired_keys:
            logging.info(f"[CACHE] 删除{len(expired_keys)}个过期项（>{self.ttl_days}天）")
            for key in expired_keys:
                self._delete_entry(key)
    
    def _prune_by_lru(self, target_count: int):
        """按LRU清理到目标数量"""
        if len(self.meta) <= target_count:
            return
        
        # 按最后访问时间排序
        sorted_items = sorted(
            self.meta.items(),
            key=lambda x: x[1].get("last_access", ""),
            reverse=False  # 最早的在前
        )
        
        # 删除最老的
        to_delete = len(self.meta) - target_count
        deleted_keys = [key for key, _ in sorted_items[:to_delete]]
        
        logging.info(f"[CACHE] LRU清理{len(deleted_keys)}个旧项")
        for key in deleted_keys:
            self._delete_entry(key)
    
    def _prune_by_size(self, target_size_gb: float):
        """按大小清理"""
        # 按最后访问时间排序
        sorted_items = sorted(
            self.meta.items(),
            key=lambda x: x[1].get("last_access", ""),
            reverse=False
        )
        
        current_size_gb = self._get_total_size_gb()
        deleted_count = 0
        
        for key, meta in sorted_items:
            if current_size_gb <= target_size_gb:
                break
            
            size_bytes = meta.get("size_bytes", 0)
            self._delete_entry(key)
            current_size_gb -= size_bytes / (1024**3)
            deleted_count += 1
        
        if deleted_count > 0:
            logging.info(f"[CACHE] 大小清理{deleted_count}项，释放空间: {self._get_total_size_gb():.2f}GB")
    
    def _delete_entry(self, key: str):
        """删除缓存项"""
        try:
            cache_file = self.cache_dir / f"{key}.srt"
            if cache_file.exists():
                cache_file.unlink()
            
            if key in self.meta:
                del self.meta[key]
                self._save_meta()
        
        except Exception as e:
            logging.warning(f"[CACHE] 删除{key}失败: {e}")
    
    def _get_total_size_gb(self) -> float:
        """获取缓存总大小（GB）"""
        total_bytes = sum(meta.get("size_bytes", 0) for meta in self.meta.values())
        return total_bytes / (1024**3)
    
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        return {
            "entries": len(self.meta),
            "total_size_gb": self._get_total_size_gb(),
            "max_size_gb": self.max_size_gb,
            "max_entries": self.max_entries,
            "ttl_days": self.ttl_days,
            "oldest_entry": min(
                (meta.get("created", "") for meta in self.meta.values()),
                default="N/A"
            ),
            "total_hits": sum(meta.get("hit_count", 0) for meta in self.meta.values())
        }

