# -*- coding: utf-8 -*-
"""
控制器基类
"""
from abc import ABC, abstractmethod
from events.event_bus import EventBus, event_bus


class BaseController(ABC):
    """
    控制器基类
    
    所有控制器都应继承此类
    提供：
    1. 事件总线访问
    2. 生命周期管理
    3. 统一的清理接口
    """
    
    def __init__(self):
        """初始化控制器"""
        self.event_bus = event_bus
        self._setup_event_listeners()
    
    @abstractmethod
    def _setup_event_listeners(self):
        """
        设置事件监听器
        
        子类必须实现此方法，订阅需要的事件
        
        示例：
            self.event_bus.subscribe(EventType.THEME_CHANGED, self._on_theme_changed)
        """
        pass
    
    def cleanup(self):
        """
        清理资源
        
        子类可以重写此方法来清理特定资源
        """
        pass
    
    def _log(self, message: str, level: str = "INFO"):
        """
        记录日志（通过事件总线）
        
        Args:
            message: 日志消息
            level: 日志级别 (INFO/WARN/ERROR)
        """
        from events.event_bus import Event, EventType
        self.event_bus.publish(Event(
            EventType.LOG_MESSAGE,
            {"message": message, "level": level}
        ))


__all__ = ['BaseController']

