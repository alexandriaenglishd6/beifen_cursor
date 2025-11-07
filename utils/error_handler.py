# -*- coding: utf-8 -*-
"""
错误处理工具 - 统一错误分类、消息格式化和恢复建议
"""
from typing import Dict, List, Tuple, Optional
from enum import Enum
from pathlib import Path
import json
from datetime import datetime


class ErrorCategory(Enum):
    """错误类别"""
    NETWORK = "network"  # 网络错误
    AUTHENTICATION = "authentication"  # 认证错误
    RATE_LIMIT = "rate_limit"  # 限流错误
    INPUT = "input"  # 输入错误（视频不存在、私有等）
    PARSE = "parse"  # 解析错误
    FILE = "file"  # 文件错误
    CONFIG = "config"  # 配置错误
    OTHER = "other"  # 其他错误


class ErrorHandler:
    """
    错误处理工具类
    
    职责：
    1. 错误分类和识别
    2. 友好的错误消息格式化
    3. 提供恢复建议
    4. 错误日志管理
    """
    
    # 错误类型映射（错误代码 -> (类别, 中文名称, 是否可重试, 恢复建议)）
    ERROR_TYPE_MAP = {
        # 网络错误（可重试）
        "error_timeout": (ErrorCategory.NETWORK, "请求超时", True, "请检查网络连接，稍后重试"),
        "error_429": (ErrorCategory.RATE_LIMIT, "请求过于频繁", True, "请稍后重试，或减少并发数量"),
        "error_503": (ErrorCategory.NETWORK, "服务不可用", True, "服务器暂时不可用，请稍后重试"),
        "error_network": (ErrorCategory.NETWORK, "网络错误", True, "请检查网络连接"),
        
        # 认证错误（不可重试，需要用户操作）
        "error_other": (ErrorCategory.AUTHENTICATION, "认证失败", False, "可能需要 Cookie 认证，请在设置中配置 Cookie 文件"),
        "YTDLP_SIGNIN": (ErrorCategory.AUTHENTICATION, "需要登录", False, "请在设置中配置 Cookie 文件以进行身份验证"),
        "HTTP_403": (ErrorCategory.AUTHENTICATION, "访问被拒绝", False, "可能需要 Cookie 认证或代理"),
        
        # 输入错误（不可重试）
        "error_private": (ErrorCategory.INPUT, "视频为私有", False, "该视频为私有视频，无法访问"),
        "error_geo": (ErrorCategory.INPUT, "地区限制", False, "该视频在您的地区不可用"),
        "VIDEO_UNAVAILABLE": (ErrorCategory.INPUT, "视频不可用", False, "视频可能已被删除或不可用"),
        "VIDEO_REMOVED": (ErrorCategory.INPUT, "视频已删除", False, "视频已被删除"),
        "NO_SUBS": (ErrorCategory.INPUT, "无字幕", False, "该视频没有字幕"),
        
        # 文件错误
        "FILE_NOT_FOUND": (ErrorCategory.FILE, "文件不存在", False, "请检查文件路径是否正确"),
        "FILE_PERMISSION": (ErrorCategory.FILE, "文件权限错误", False, "请检查文件权限"),
        
        # 配置错误
        "CONFIG_INVALID": (ErrorCategory.CONFIG, "配置无效", False, "请检查配置设置"),
        "COOKIE_INVALID": (ErrorCategory.CONFIG, "Cookie 无效", False, "请检查 Cookie 文件格式是否正确"),
    }
    
    @staticmethod
    def classify_error(error_code: str) -> Tuple[ErrorCategory, str, bool, str]:
        """
        分类错误
        
        Args:
            error_code: 错误代码（如 "error_other", "error_429"）
        
        Returns:
            (错误类别, 中文名称, 是否可重试, 恢复建议)
        """
        if error_code in ErrorHandler.ERROR_TYPE_MAP:
            return ErrorHandler.ERROR_TYPE_MAP[error_code]
        
        # 默认处理
        return (ErrorCategory.OTHER, "未知错误", False, "请查看详细错误信息")
    
    @staticmethod
    def format_error_message(
        error_code: str,
        error_detail: str = "",
        video_id: str = "",
        video_title: str = ""
    ) -> str:
        """
        格式化友好的错误消息
        
        Args:
            error_code: 错误代码
            error_detail: 错误详情
            video_id: 视频ID
            video_title: 视频标题
        
        Returns:
            格式化的错误消息
        """
        category, name, retryable, suggestion = ErrorHandler.classify_error(error_code)
        
        # 构建消息
        parts = []
        
        # 视频信息
        if video_title:
            parts.append(f"视频: {video_title[:50]}")
        elif video_id:
            parts.append(f"视频ID: {video_id}")
        
        # 错误名称
        parts.append(f"错误: {name}")
        
        # 错误详情（如果有）
        if error_detail:
            # 限制详情长度
            detail = error_detail[:100] if len(error_detail) > 100 else error_detail
            parts.append(f"详情: {detail}")
        
        # 恢复建议
        parts.append(f"建议: {suggestion}")
        
        # 可重试提示
        if retryable:
            parts.append("提示: 此错误可以重试")
        
        return " | ".join(parts)
    
    @staticmethod
    def get_recovery_suggestions(error_code: str) -> List[str]:
        """
        获取恢复建议列表
        
        Args:
            error_code: 错误代码
        
        Returns:
            恢复建议列表
        """
        _, _, _, suggestion = ErrorHandler.classify_error(error_code)
        
        suggestions = [suggestion]
        
        # 根据错误类型添加额外建议
        if error_code == "error_other" or "YTDLP_SIGNIN" in error_code:
            suggestions.extend([
                "1. 使用浏览器扩展 'Get cookies.txt LOCALLY' 导出 YouTube Cookie",
                "2. 在设置中配置 Cookie 文件路径",
                "3. 确保 Cookie 文件格式正确（Netscape 格式）"
            ])
        elif error_code == "error_429":
            suggestions.extend([
                "1. 减少并发数量（max_workers）",
                "2. 增加请求间隔时间",
                "3. 等待一段时间后重试"
            ])
        elif error_code == "error_timeout":
            suggestions.extend([
                "1. 检查网络连接",
                "2. 尝试使用代理",
                "3. 增加超时时间设置"
            ])
        elif error_code == "error_geo":
            suggestions.extend([
                "1. 使用 VPN 或代理",
                "2. 在设置中配置代理"
            ])
        
        return suggestions
    
    @staticmethod
    def format_error_summary(errors: List[Dict]) -> Dict[str, any]:
        """
        格式化错误摘要
        
        Args:
            errors: 错误列表，每个错误包含 error_code, video_id, error_detail 等
        
        Returns:
            错误摘要字典
        """
        summary = {
            "total": len(errors),
            "by_category": {},
            "by_type": {},
            "retryable_count": 0,
            "non_retryable_count": 0
        }
        
        for error in errors:
            error_code = error.get("error_code", "error_other")
            category, name, retryable, _ = ErrorHandler.classify_error(error_code)
            
            # 按类别统计
            category_name = category.value
            summary["by_category"][category_name] = summary["by_category"].get(category_name, 0) + 1
            
            # 按类型统计
            summary["by_type"][name] = summary["by_type"].get(name, 0) + 1
            
            # 可重试统计
            if retryable:
                summary["retryable_count"] += 1
            else:
                summary["non_retryable_count"] += 1
        
        return summary


class ErrorLogger:
    """
    错误日志管理器
    
    职责：
    1. 记录错误日志
    2. 导出错误日志
    3. 错误统计
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        """
        初始化错误日志管理器
        
        Args:
            log_dir: 日志目录，默认为项目根目录下的 errors 目录
        """
        if log_dir is None:
            log_dir = Path.cwd() / "errors"
        
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.errors: List[Dict] = []
    
    def log_error(
        self,
        error_code: str,
        error_detail: str = "",
        video_id: str = "",
        video_title: str = "",
        url: str = "",
        timestamp: Optional[datetime] = None
    ):
        """
        记录错误
        
        Args:
            error_code: 错误代码
            error_detail: 错误详情
            video_id: 视频ID
            video_title: 视频标题
            url: 视频URL
            timestamp: 时间戳，默认为当前时间
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        error_record = {
            "timestamp": timestamp.isoformat(),
            "error_code": error_code,
            "error_detail": error_detail,
            "video_id": video_id,
            "video_title": video_title,
            "url": url,
            "category": ErrorHandler.classify_error(error_code)[0].value,
            "retryable": ErrorHandler.classify_error(error_code)[2]
        }
        
        self.errors.append(error_record)
    
    def export_to_json(self, file_path: Optional[Path] = None) -> Path:
        """
        导出错误日志为JSON文件
        
        Args:
            file_path: 输出文件路径，默认为 errors/errors_YYYYMMDD_HHMMSS.json
        
        Returns:
            导出的文件路径
        """
        if file_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = self.log_dir / f"errors_{timestamp}.json"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({
                "export_time": datetime.now().isoformat(),
                "total_errors": len(self.errors),
                "errors": self.errors,
                "summary": ErrorHandler.format_error_summary(self.errors)
            }, f, ensure_ascii=False, indent=2)
        
        return file_path
    
    def export_to_text(self, file_path: Optional[Path] = None) -> Path:
        """
        导出错误日志为文本文件
        
        Args:
            file_path: 输出文件路径，默认为 errors/errors_YYYYMMDD_HHMMSS.txt
        
        Returns:
            导出的文件路径
        """
        if file_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = self.log_dir / f"errors_{timestamp}.txt"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("错误日志导出\n")
            f.write("=" * 60 + "\n")
            f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"错误总数: {len(self.errors)}\n")
            f.write("=" * 60 + "\n\n")
            
            # 错误摘要
            summary = ErrorHandler.format_error_summary(self.errors)
            f.write("错误摘要:\n")
            f.write(f"  总计: {summary['total']}\n")
            f.write(f"  可重试: {summary['retryable_count']}\n")
            f.write(f"  不可重试: {summary['non_retryable_count']}\n")
            f.write("\n按类别统计:\n")
            for category, count in summary['by_category'].items():
                f.write(f"  {category}: {count}\n")
            f.write("\n按类型统计:\n")
            for error_type, count in summary['by_type'].items():
                f.write(f"  {error_type}: {count}\n")
            f.write("\n" + "=" * 60 + "\n\n")
            
            # 详细错误列表
            for i, error in enumerate(self.errors, 1):
                f.write(f"错误 #{i}:\n")
                f.write(f"  时间: {error['timestamp']}\n")
                f.write(f"  错误代码: {error['error_code']}\n")
                f.write(f"  类别: {error['category']}\n")
                f.write(f"  可重试: {'是' if error['retryable'] else '否'}\n")
                if error.get('video_id'):
                    f.write(f"  视频ID: {error['video_id']}\n")
                if error.get('video_title'):
                    f.write(f"  视频标题: {error['video_title']}\n")
                if error.get('url'):
                    f.write(f"  URL: {error['url']}\n")
                if error.get('error_detail'):
                    f.write(f"  详情: {error['error_detail']}\n")
                
                # 恢复建议
                suggestions = ErrorHandler.get_recovery_suggestions(error['error_code'])
                f.write(f"  恢复建议:\n")
                for suggestion in suggestions:
                    f.write(f"    - {suggestion}\n")
                
                f.write("\n")
        
        return file_path
    
    def clear(self):
        """清空错误日志"""
        self.errors.clear()


__all__ = ['ErrorHandler', 'ErrorCategory', 'ErrorLogger']

