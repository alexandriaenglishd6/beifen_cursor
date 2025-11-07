# -*- coding: utf-8 -*-
"""
主窗口测试版 - 用于验证新架构
"""
import tkinter as tk
from tkinter import ttk
from gui.views.download_panel import DownloadPanel


class MainWindowTest(tk.Frame):
    """
    主窗口测试版
    
    只包含下载功能，用于验证新架构
    """
    
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.root = master
        
        # 创建顶部工具栏
        self._build_toolbar()
        
        # 创建下载面板
        self.download_panel = DownloadPanel(self)
        self.download_panel.pack(fill='both', expand=True, padx=10, pady=5)
        
        # 创建日志区
        self._build_log_area()
        
        self.pack(fill='both', expand=True)
    
    def _build_toolbar(self):
        """构建工具栏"""
        toolbar = tk.Frame(self)
        toolbar.pack(fill='x', padx=10, pady=8)
        
        ttk.Label(toolbar, text="🎬 YouTube字幕工具 (新架构测试)", 
                 font=("Segoe UI", 14, "bold")).pack(side='left')
        
        # 按钮区
        btn_frame = tk.Frame(toolbar)
        btn_frame.pack(side='right')
        
        self.btn_detect = ttk.Button(btn_frame, text="🔍 检测", width=10)
        self.btn_detect.pack(side='left', padx=5)
        
        self.btn_download = ttk.Button(btn_frame, text="▶️ 下载", width=10)
        self.btn_download.pack(side='left', padx=5)
        
        self.btn_stop = ttk.Button(btn_frame, text="■ 停止", width=10)
        self.btn_stop.pack(side='left', padx=5)
    
    def _build_log_area(self):
        """构建日志区"""
        log_frame = tk.Frame(self)
        log_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        ttk.Label(log_frame, text="执行日志:", font=("Segoe UI", 14, "bold")).pack(anchor='w')
        
        # 日志文本框
        self.txt_log = tk.Text(log_frame, height=10, font=("Consolas", 10))
        self.txt_log.pack(fill='both', expand=True, pady=5)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(self.txt_log)
        scrollbar.pack(side='right', fill='y')
        self.txt_log.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.txt_log.yview)
    
    def append_log(self, message: str, level: str = "INFO"):
        """
        添加日志
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        self.txt_log.insert("end", f"[{level}] {message}\n")
        self.txt_log.see("end")


__all__ = ['MainWindowTest']

