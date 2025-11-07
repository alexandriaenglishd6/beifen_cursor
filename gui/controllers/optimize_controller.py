# -*- coding: utf-8 -*-
"""
字幕优化控制器 - 连接视图和配置管理
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from gui.controllers.base_controller import BaseController
from services.config_service import ConfigService

if TYPE_CHECKING:
    from gui.views.optimize_panel import OptimizePanel


class OptimizeController(BaseController):
    """
    字幕优化控制器
    
    职责：
    1. 处理字幕优化配置
    2. 管理配置持久化
    3. 处理配置变更事件
    """
    
    def __init__(self, view: OptimizePanel, config: dict):
        """
        初始化
        
        Args:
            view: 字幕优化面板视图
            config: 全局配置
        """
        self.view = view
        self.config = config
        self.config_service = ConfigService()
        
        super().__init__()
        
        # 统一初始化顺序由 InitializationManager 保证，这里同步初始化
        self.load_config()
        self._setup_auto_save()
    
    def _setup_event_listeners(self):
        """设置事件监听（基类要求）"""
        # 字幕优化控制器目前不需要监听特定事件
        pass
    
    def load_config(self):
        """加载配置到UI"""
        try:
            # 确保内容已加载（如为懒加载，主动触发）
            if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
                self.view.accordion.get_content_frame()
            
            # 从配置服务获取优化配置
            postprocess_config = self.config.get("postprocess", {})
            quality_config = self.config.get("quality", {})
            
            # 构建配置字典
            optimize_config = {
                "postprocess": postprocess_config,
                "quality": quality_config
            }
            
            # 加载到视图
            self.view.load_config(optimize_config)
            
            print(f"[OptimizeController] ✓ 字幕优化配置已加载到UI")
        except Exception as e:
            print(f"[OptimizeController] 加载配置失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _setup_auto_save(self):
        """设置自动保存（延迟执行，确保视图完全构建）"""
        try:
            # 确保内容已加载（如为懒加载，主动触发）
            if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
                self.view.accordion.get_content_frame()
            
            # 绑定配置变更事件（自动保存）
            self.view.var_postprocess_enabled.trace_add("write", lambda *args: self._save_config())
            self.view.var_merge_short_lines.trace_add("write", lambda *args: self._save_config())
            self.view.var_dedupe_duplicates.trace_add("write", lambda *args: self._save_config())
            self.view.var_strip_nonspeech.trace_add("write", lambda *args: self._save_config())
            self.view.var_normalize_whitespace.trace_add("write", lambda *args: self._save_config())
            self.view.var_quality_enabled.trace_add("write", lambda *args: self._save_config())
            self.view.var_quality_warn_enabled.trace_add("write", lambda *args: self._save_config())
            
            # Spinbox 需要特殊处理（使用 validatecommand 或绑定 <FocusOut>）
            self.view.spin_short_line_len.bind("<FocusOut>", lambda e: self._save_config())
            self.view.spin_short_line_len.bind("<Return>", lambda e: self._save_config())
            self.view.spin_warn_threshold.bind("<FocusOut>", lambda e: self._save_config())
            self.view.spin_warn_threshold.bind("<Return>", lambda e: self._save_config())
            
            print(f"[OptimizeController] ✓ 自动保存绑定完成")
        except Exception as e:
            print(f"[OptimizeController] 设置自动保存失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _save_config(self):
        """保存配置"""
        try:
            # 获取视图配置
            optimize_config = self.view.get_config()
            
            # 更新全局配置
            if "postprocess" in optimize_config:
                self.config["postprocess"] = optimize_config["postprocess"]
            
            if "quality" in optimize_config:
                # 合并质量配置（保留原有字段）
                quality_config = self.config.get("quality", {})
                quality_config.update(optimize_config["quality"])
                self.config["quality"] = quality_config
            
            # 保存到配置文件
            self.config_service.save()
            
            print(f"[OptimizeController] ✓ 字幕优化配置已保存")
        except Exception as e:
            print(f"[OptimizeController] 保存配置失败: {e}")
            import traceback
            traceback.print_exc()
    
    def get_config(self) -> dict:
        """
        获取字幕优化配置
        
        Returns:
            配置字典
        """
        return self.view.get_config()

