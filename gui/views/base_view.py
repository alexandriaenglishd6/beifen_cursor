# -*- coding: utf-8 -*-
"""
视图基类
"""
from abc import ABC
import tkinter as tk


class BaseView(tk.Frame, ABC):
    """
    视图基类
    
    所有视图面板都应继承此类
    提供：
    1. 统一的初始化接口
    2. 主题更新接口
    3. 清理接口
    """
    
    def __init__(self, parent):
        """
        初始化视图
        
        Args:
            parent: 父容器
        """
        super().__init__(parent)
        self._build_ui()
    
    def _build_ui(self):
        """
        构建UI
        
        子类应该实现此方法来构建具体的UI
        """
        pass
    
    def update_theme(self, theme_name: str):
        """
        更新主题
        
        Args:
            theme_name: 主题名称 (light/dark/blue)
        """
        pass
    
    def cleanup(self):
        """清理资源"""
        pass


__all__ = ['BaseView']

