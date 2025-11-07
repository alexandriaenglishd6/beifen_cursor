# -*- coding: utf-8 -*-
"""
字幕翻译控制器 - 连接视图和配置管理
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from gui.controllers.base_controller import BaseController
from events.event_bus import EventType, Event
from services.config_service import get_config_service

if TYPE_CHECKING:
    from gui.views.translate_panel import TranslatePanel


class TranslateController(BaseController):
    """
    字幕翻译控制器
    
    职责：
    1. 处理字幕翻译设置
    2. 管理配置持久化
    """
    
    def __init__(self, view: TranslatePanel, config: dict):
        """
        初始化
        
        Args:
            view: 字幕翻译面板视图
            config: 全局配置
        """
        self.view = view
        self.config = config
        
        super().__init__()
        
        # 统一初始化顺序由 InitializationManager 保证，这里同步初始化
        self.load_config()
        self._setup_auto_save()
    
    def _setup_event_listeners(self):
        """设置事件监听（基类要求）"""
        # 字幕翻译控制器目前不需要监听特定事件
        pass
    
    def _setup_auto_save(self):
        """设置自动保存绑定"""
        # 确保内容已加载（如果是懒加载模式）
        if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
            self.view.accordion.expand()  # 强制展开以确保所有控件被创建
            self.view.update_idletasks()  # 强制更新UI
        
        # 绑定所有控件的变更事件
        self.view.var_translate_enabled.trace_add("write", lambda *args: self._on_config_change())
        self.view.cmb_src_lang.bind("<<ComboboxSelected>>", lambda e: self._on_config_change())
        self.view.cmb_tgt_lang.bind("<<ComboboxSelected>>", lambda e: self._on_config_change())
        self.view.cmb_provider.bind("<<ComboboxSelected>>", lambda e: self._on_config_change())
        self.view.cmb_format.bind("<<ComboboxSelected>>", lambda e: self._on_config_change())
        self.view.var_postprocess.trace_add("write", lambda *args: self._on_config_change())
        
        self._log("[TranslateController] ✓ 自动保存绑定完成")
    
    def _on_config_change(self):
        """配置变更时自动保存"""
        new_config = self.view.get_config()
        
        # 通过配置服务统一保存
        try:
            cfg = get_config_service()
            # 直接更新 translate 段
            cfg.update("translate", new_config)
            cfg.save()
        except Exception as e:
            self._log(f"保存字幕翻译配置失败: {e}", "ERROR")
        self._log("[TranslateController] ✓ 字幕翻译配置已自动保存")
        
        # 发布配置保存事件（使用CONFIG_SAVED而不是CONFIG_UPDATED）
        # 注意：CONFIG_UPDATED不存在，使用CONFIG_SAVED
        try:
            self.event_bus.publish(Event(EventType.CONFIG_SAVED, {"section": "translate"}))
        except Exception:
            # 如果事件类型不存在，静默忽略（不影响功能）
            pass
    
    def load_config(self):
        """加载配置到UI"""
        translate_config = self.config.get("translate", {})
        self.view.load_config(translate_config)
        self._log("[TranslateController] ✓ 字幕翻译配置已加载到UI")
    
    def get_config(self) -> dict:
        """
        获取翻译配置
        
        Returns:
            配置字典
        """
        return self.view.get_config()


__all__ = ['TranslateController']

