# -*- coding: utf-8 -*-
"""
统一日志配置模块

提供统一的日志接口，支持:
1. Python标准logging模块
2. GUI日志管理器集成
3. 日志级别控制
"""
import logging
import sys
from typing import Optional
from pathlib import Path

# 全局GUI日志管理器引用（由主控制器设置）
_gui_log_manager: Optional[object] = None


def set_gui_log_manager(log_manager):
    """
    设置GUI日志管理器
    
    Args:
        log_manager: LogManager实例
    """
    global _gui_log_manager
    _gui_log_manager = log_manager


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    获取配置好的日志记录器
    
    Args:
        name: 日志记录器名称（通常是模块名）
        level: 日志级别（DEBUG/INFO/WARN/ERROR）
    
    Returns:
        配置好的Logger实例
    """
    logger = logging.getLogger(name)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # 创建控制台handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    
    # 创建格式器
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    # 添加handler
    logger.addHandler(console_handler)
    
    # 添加GUI日志handler（如果可用）
    if _gui_log_manager:
        gui_handler = GUILogHandler(_gui_log_manager)
        gui_handler.setLevel(log_level)
        logger.addHandler(gui_handler)
    
    return logger


class GUILogHandler(logging.Handler):
    """
    将日志输出到GUI日志管理器
    """
    
    def __init__(self, log_manager):
        """
        初始化GUI日志handler
        
        Args:
            log_manager: LogManager实例
        """
        super().__init__()
        self.log_manager = log_manager
    
    def emit(self, record: logging.LogRecord):
        """
        发送日志记录到GUI
        
        Args:
            record: 日志记录
        """
        try:
            # 格式化消息
            message = self.format(record)
            
            # 转换日志级别
            level_map = {
                logging.DEBUG: "DEBUG",
                logging.INFO: "INFO",
                logging.WARNING: "WARN",
                logging.ERROR: "ERROR",
                logging.CRITICAL: "ERROR"
            }
            level = level_map.get(record.levelno, "INFO")
            
            # 添加到GUI日志管理器
            if hasattr(self.log_manager, 'add_log'):
                self.log_manager.add_log(message, level)
        except Exception:
            # 避免日志系统自身出错导致程序崩溃
            pass


def configure_logging(config: Optional[dict] = None):
    """
    配置全局日志系统
    
    Args:
        config: 配置字典，包含:
            - level: 日志级别（DEBUG/INFO/WARN/ERROR）
            - file: 日志文件路径（可选）
            - max_bytes: 日志文件最大大小（可选）
            - backup_count: 备份文件数量（可选）
    """
    if config is None:
        config = {}
    
    # 获取日志级别
    level_str = config.get("level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除现有handlers
    root_logger.handlers.clear()
    
    # 创建控制台handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    
    # 创建格式器
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 如果配置了日志文件，添加文件handler
    log_file = config.get("file")
    if log_file:
        from logging.handlers import RotatingFileHandler
        
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        max_bytes = config.get("max_bytes", 10 * 1024 * 1024)  # 默认10MB
        backup_count = config.get("backup_count", 5)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

