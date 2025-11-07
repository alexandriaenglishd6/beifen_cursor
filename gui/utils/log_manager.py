# -*- coding: utf-8 -*-
"""
日志管理器 - 管理日志数据，支持搜索、过滤、导出
"""
import re
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class LogEntry:
    """日志条目"""
    
    def __init__(self, timestamp: str, level: str, message: str):
        self.timestamp = timestamp
        self.level = level
        self.message = message
        self.datetime = self._parse_timestamp(timestamp)
    
    def _parse_timestamp(self, timestamp: str) -> Optional[datetime]:
        """解析时间戳字符串"""
        try:
            # 格式: "HH:MM:SS"
            time_parts = timestamp.split(":")
            if len(time_parts) == 3:
                hour, minute, second = map(int, time_parts)
                today = datetime.now().date()
                return datetime.combine(today, datetime.min.time().replace(
                    hour=hour, minute=minute, second=second
                ))
        except:
            pass
        return None
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message
        }
    
    def to_string(self) -> str:
        """转换为字符串"""
        return f"[{self.timestamp}] [{self.level}] {self.message}"


class LogManager:
    """日志管理器"""
    
    def __init__(self, max_entries: int = 10000):
        """
        初始化日志管理器
        
        Args:
            max_entries: 最大保留日志条数，超过后自动清理
        """
        self.logs: List[LogEntry] = []
        self.max_entries = max_entries
        self._search_pos = 0  # 当前搜索位置
    
    def add_log(self, message: str, level: str = "INFO"):
        """
        添加日志
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = LogEntry(timestamp, level, message)
        self.logs.append(entry)
        
        # 自动清理：保留最近N条
        if len(self.logs) > self.max_entries:
            # 保留后 max_entries 条
            self.logs = self.logs[-self.max_entries:]
    
    def clear(self):
        """清空所有日志"""
        self.logs.clear()
        self._search_pos = 0
    
    def filter_logs(self, level: Optional[str] = None, 
                    keyword: Optional[str] = None,
                    use_regex: bool = False,
                    start_time: Optional[datetime] = None,
                    end_time: Optional[datetime] = None) -> List[LogEntry]:
        """
        过滤日志
        
        Args:
            level: 日志级别过滤（None表示不过滤）
            keyword: 关键词过滤（None表示不过滤）
            use_regex: 是否使用正则表达式
            start_time: 开始时间（None表示不过滤）
            end_time: 结束时间（None表示不过滤）
        
        Returns:
            过滤后的日志列表
        """
        filtered = self.logs
        
        # 级别过滤
        if level and level != "ALL":
            filtered = [log for log in filtered if log.level == level]
        
        # 关键词过滤
        if keyword:
            if use_regex:
                try:
                    pattern = re.compile(keyword, re.IGNORECASE)
                    filtered = [log for log in filtered if pattern.search(log.message)]
                except re.error:
                    # 正则表达式错误，回退到普通搜索
                    keyword_lower = keyword.lower()
                    filtered = [log for log in filtered if keyword_lower in log.message.lower()]
            else:
                keyword_lower = keyword.lower()
                filtered = [log for log in filtered if keyword_lower in log.message.lower()]
        
        # 时间范围过滤
        if start_time:
            filtered = [log for log in filtered 
                       if log.datetime and log.datetime >= start_time]
        
        if end_time:
            filtered = [log for log in filtered 
                       if log.datetime and log.datetime <= end_time]
        
        return filtered
    
    def search(self, keyword: str, use_regex: bool = False, 
              start_pos: int = 0) -> List[Tuple[int, LogEntry]]:
        """
        搜索日志，返回匹配的索引和条目
        
        Args:
            keyword: 搜索关键词
            use_regex: 是否使用正则表达式
            start_pos: 开始搜索的位置
        
        Returns:
            [(索引, LogEntry), ...] 列表
        """
        matches = []
        
        if use_regex:
            try:
                pattern = re.compile(keyword, re.IGNORECASE)
                for i, log in enumerate(self.logs[start_pos:], start=start_pos):
                    if pattern.search(log.message):
                        matches.append((i, log))
            except re.error:
                # 正则表达式错误，回退到普通搜索
                keyword_lower = keyword.lower()
                for i, log in enumerate(self.logs[start_pos:], start=start_pos):
                    if keyword_lower in log.message.lower():
                        matches.append((i, log))
        else:
            keyword_lower = keyword.lower()
            for i, log in enumerate(self.logs[start_pos:], start=start_pos):
                if keyword_lower in log.message.lower():
                    matches.append((i, log))
        
        return matches
    
    def export_txt(self, file_path: str, 
                  level: Optional[str] = None,
                  keyword: Optional[str] = None,
                  use_regex: bool = False,
                  start_time: Optional[datetime] = None,
                  end_time: Optional[datetime] = None) -> int:
        """
        导出日志为TXT格式
        
        Args:
            file_path: 输出文件路径
            level: 日志级别过滤
            keyword: 关键词过滤
            use_regex: 是否使用正则表达式
            start_time: 开始时间
            end_time: 结束时间
        
        Returns:
            导出的日志条数
        """
        filtered = self.filter_logs(level, keyword, use_regex, start_time, end_time)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            for log in filtered:
                f.write(log.to_string() + '\n')
        
        return len(filtered)
    
    def export_json(self, file_path: str,
                   level: Optional[str] = None,
                   keyword: Optional[str] = None,
                   use_regex: bool = False,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None) -> int:
        """
        导出日志为JSON格式
        
        Args:
            file_path: 输出文件路径
            level: 日志级别过滤
            keyword: 关键词过滤
            use_regex: 是否使用正则表达式
            start_time: 开始时间
            end_time: 结束时间
        
        Returns:
            导出的日志条数
        """
        filtered = self.filter_logs(level, keyword, use_regex, start_time, end_time)
        
        data = {
            "export_time": datetime.now().isoformat(),
            "total_logs": len(self.logs),
            "filtered_logs": len(filtered),
            "filters": {
                "level": level,
                "keyword": keyword,
                "use_regex": use_regex,
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None
            },
            "logs": [log.to_dict() for log in filtered]
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return len(filtered)
    
    def get_statistics(self) -> Dict:
        """
        获取日志统计信息
        
        Returns:
            统计信息字典
        """
        total = len(self.logs)
        by_level = {}
        
        for log in self.logs:
            by_level[log.level] = by_level.get(log.level, 0) + 1
        
        return {
            "total": total,
            "by_level": by_level
        }
    
    def get_all_logs(self) -> List[LogEntry]:
        """获取所有日志"""
        return self.logs.copy()

