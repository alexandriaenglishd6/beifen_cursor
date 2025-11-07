# -*- coding: utf-8 -*-
"""
应用门面测试版 - 用于验证新架构
"""
import tkinter as tk
from gui.views.main_window_test import MainWindowTest
from gui.controllers.download_controller import DownloadController
from events.event_bus import event_bus, EventType
from config_store import load_config


class AppFacadeTest:
    """
    应用门面测试版
    
    职责：
    1. 创建主窗口
    2. 初始化控制器
    3. 绑定事件
    """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.event_bus = event_bus
        self.config = load_config()
        
        # 创建主窗口
        self.main_window = MainWindowTest(root)
        
        # 初始化控制器
        self.download_ctrl = DownloadController(
            self.main_window.download_panel,
            self.config
        )
        
        # 绑定按钮事件
        self._bind_buttons()
        
        # 绑定全局事件
        self._bind_global_events()
        
        # 初始化日志
        self.main_window.append_log("新架构测试版启动成功", "INFO")
        self.main_window.append_log("事件总线已初始化", "INFO")
        self.main_window.append_log("下载控制器已初始化", "INFO")
    
    def _bind_buttons(self):
        """绑定按钮事件"""
        # 检测按钮
        self.main_window.btn_detect.config(
            command=lambda: self.download_ctrl.start_download(dry_run=True)
        )
        
        # 下载按钮
        self.main_window.btn_download.config(
            command=lambda: self.download_ctrl.start_download(dry_run=False)
        )
        
        # 停止按钮
        self.main_window.btn_stop.config(
            command=self.download_ctrl.stop_download
        )
        
        # 清空按钮
        self.main_window.download_panel.btn_clear.config(
            command=self.download_ctrl.clear_urls
        )
    
    def _bind_global_events(self):
        """绑定全局事件"""
        # 监听日志事件
        self.event_bus.subscribe(EventType.LOG_MESSAGE, self._on_log_message)
        
        # 监听下载事件
        self.event_bus.subscribe(EventType.DOWNLOAD_STARTED, self._on_download_started)
        self.event_bus.subscribe(EventType.DOWNLOAD_PROGRESS, self._on_download_progress)
        self.event_bus.subscribe(EventType.DOWNLOAD_COMPLETED, self._on_download_completed)
        self.event_bus.subscribe(EventType.DOWNLOAD_FAILED, self._on_download_failed)
        self.event_bus.subscribe(EventType.DOWNLOAD_STOPPED, self._on_download_stopped)
    
    def _on_log_message(self, event):
        """处理日志消息"""
        message = event.data.get("message", "")
        level = event.data.get("level", "INFO")
        self.main_window.append_log(message, level)
    
    def _on_download_started(self, event):
        """处理下载开始事件"""
        count = event.data.get("count", 0)
        dry_run = event.data.get("dry_run", False)
        mode = "检测" if dry_run else "下载"
        self.main_window.append_log(f"开始{mode}，共 {count} 个任务", "INFO")
    
    def _on_download_progress(self, event):
        """处理下载进度事件"""
        phase = event.data.get("phase", "")
        current = event.data.get("current", 0)
        total = event.data.get("total", 0)
        message = event.data.get("message", "")
        
        if total > 0:
            percent = int((current / total) * 100)
            self.main_window.append_log(f"[{phase}] {percent}% - {message}", "INFO")
    
    def _on_download_completed(self, event):
        """处理下载完成事件"""
        self.main_window.append_log("下载任务完成", "INFO")
    
    def _on_download_failed(self, event):
        """处理下载失败事件"""
        reason = event.data.get("reason", "未知错误")
        self.main_window.append_log(f"下载失败: {reason}", "ERROR")
    
    def _on_download_stopped(self, event):
        """处理下载停止事件"""
        self.main_window.append_log("下载已停止", "WARN")
    
    def cleanup(self):
        """清理资源"""
        self.download_ctrl.cleanup()


__all__ = ['AppFacadeTest']

