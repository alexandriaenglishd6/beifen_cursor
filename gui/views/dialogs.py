# -*- coding: utf-8 -*-
"""
对话框组件 - 完整表单对话框
"""
import tkinter as tk
from tkinter import ttk
from typing import Optional, Dict


class SchedulerJobDialog(tk.Toplevel):
    """调度任务对话框（完整版）"""
    
    def __init__(self, parent, job=None):
        super().__init__(parent)
        
        self.result = None
        self.job = job
        
        # 窗口设置
        title = "编辑任务" if job else "添加任务"
        self.title(title)
        self.geometry("650x700")  # 增大窗口尺寸以显示全部内容
        self.transient(parent)
        self.grab_set()
        
        # 构建UI
        self._build_ui()
        
        # 居中显示
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f'+{x}+{y}')
    
    def _build_ui(self):
        """构建UI"""
        # 主容器
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # 任务名称
        ttk.Label(main_frame, text="任务名称:", font=("", 11, "bold")).grid(
            row=0, column=0, sticky='w', pady=(0, 5))
        self.ent_name = ttk.Entry(main_frame, width=50, font=("", 11))
        if self.job:
            self.ent_name.insert(0, self.job.name)
        self.ent_name.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 15))
        
        # URL
        ttk.Label(main_frame, text="频道/播放列表 URL:", font=("", 11, "bold")).grid(
            row=2, column=0, sticky='w', pady=(0, 5))
        self.ent_url = ttk.Entry(main_frame, width=50, font=("", 11))
        if self.job:
            self.ent_url.insert(0, self.job.source_url or "")
        self.ent_url.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(0, 15))
        
        # 频率和时间设置
        time_frame = ttk.LabelFrame(main_frame, text="调度设置", padding="10")
        time_frame.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(0, 15))
        
        # 频率
        ttk.Label(time_frame, text="频率:", font=("", 10)).grid(
            row=0, column=0, sticky='w', padx=(0, 10))
        self.cmb_frequency = ttk.Combobox(time_frame, 
            values=["hourly", "daily", "weekly"], state="readonly", width=12)
        self.cmb_frequency.set("daily" if not self.job else self.job.frequency.value)
        self.cmb_frequency.grid(row=0, column=1, sticky='w')
        
        # 小时
        ttk.Label(time_frame, text="小时 (0-23):", font=("", 10)).grid(
            row=1, column=0, sticky='w', padx=(0, 10), pady=(10, 0))
        self.spin_hour = ttk.Spinbox(time_frame, from_=0, to=23, width=12)
        self.spin_hour.set(str(self.job.byhour or 0) if self.job else "0")
        self.spin_hour.grid(row=1, column=1, sticky='w', pady=(10, 0))
        
        # 分钟
        ttk.Label(time_frame, text="分钟 (0-59):", font=("", 10)).grid(
            row=2, column=0, sticky='w', padx=(0, 10), pady=(10, 0))
        self.spin_minute = ttk.Spinbox(time_frame, from_=0, to=59, width=12)
        self.spin_minute.set(str(self.job.byminute or 0) if self.job else "0")
        self.spin_minute.grid(row=2, column=1, sticky='w', pady=(10, 0))
        
        # 星期（仅weekly时使用）
        ttk.Label(time_frame, text="星期 (0=周一):", font=("", 10)).grid(
            row=3, column=0, sticky='w', padx=(0, 10), pady=(10, 0))
        self.spin_weekday = ttk.Spinbox(time_frame, from_=0, to=6, width=12)
        self.spin_weekday.set(str(self.job.weekday or 0) if self.job else "0")
        self.spin_weekday.grid(row=3, column=1, sticky='w', pady=(10, 0))
        
        # 其他设置
        other_frame = ttk.LabelFrame(main_frame, text="其他设置", padding="10")
        other_frame.grid(row=5, column=0, columnspan=2, sticky='ew', pady=(0, 15))
        
        # 抖动
        ttk.Label(other_frame, text="抖动 (秒):", font=("", 10)).grid(
            row=0, column=0, sticky='w', padx=(0, 10))
        self.spin_jitter = ttk.Spinbox(other_frame, from_=60, to=180, width=12)
        self.spin_jitter.set(str(self.job.jitter_sec or 90) if self.job else "90")
        self.spin_jitter.grid(row=0, column=1, sticky='w')
        
        # 输出目录
        ttk.Label(other_frame, text="输出目录:", font=("", 10)).grid(
            row=1, column=0, sticky='w', padx=(0, 10), pady=(10, 0))
        self.ent_output = ttk.Entry(other_frame, width=30)
        self.ent_output.insert(0, self.job.output_root or "out" if self.job else "out")
        self.ent_output.grid(row=1, column=1, sticky='ew', pady=(10, 0))
        
        # 语言
        ttk.Label(other_frame, text="语言:", font=("", 10)).grid(
            row=2, column=0, sticky='w', padx=(0, 10), pady=(10, 0))
        self.ent_langs = ttk.Entry(other_frame, width=30)
        langs = ",".join(self.job.preferred_langs) if self.job and self.job.preferred_langs else "zh,en"
        self.ent_langs.insert(0, langs)
        self.ent_langs.grid(row=2, column=1, sticky='ew', pady=(10, 0))
        
        # 下载选项
        self.var_download = tk.BooleanVar(value=self.job.do_download if self.job else True)
        ttk.Checkbutton(other_frame, text="下载字幕", 
                       variable=self.var_download).grid(
            row=3, column=0, columnspan=2, sticky='w', pady=(10, 0))
        
        # 按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Button(btn_frame, text="确定", command=self._on_ok, width=12).pack(
            side='left', padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy, width=12).pack(
            side='left', padx=5)
        
        # 配置权重
        main_frame.columnconfigure(0, weight=1)
    
    def _on_ok(self):
        """确定按钮"""
        name = self.ent_name.get().strip()
        url = self.ent_url.get().strip()
        
        if not name:
            from tkinter import messagebox
            messagebox.showwarning("警告", "请输入任务名称", parent=self)
            return
        
        try:
            self.result = {
                "name": name,
                "source_url": url,
                "frequency": self.cmb_frequency.get(),
                "byhour": int(self.spin_hour.get()),
                "byminute": int(self.spin_minute.get()),
                "weekday": int(self.spin_weekday.get()) if self.cmb_frequency.get() == "weekly" else None,
                "jitter_sec": int(self.spin_jitter.get()),
                "output_root": self.ent_output.get().strip() or "out",
                "preferred_langs": [l.strip() for l in self.ent_langs.get().split(",") if l.strip()],
                "do_download": self.var_download.get()
            }
            self.destroy()
        except ValueError as e:
            from tkinter import messagebox
            messagebox.showerror("错误", f"输入值无效: {e}", parent=self)


class SubscriptionDialog(tk.Toplevel):
    """订阅对话框（完整版）"""
    
    def __init__(self, parent, subscription=None):
        super().__init__(parent)
        
        self.result = None
        self.subscription = subscription
        
        # 窗口设置
        title = "编辑订阅" if subscription else "添加订阅"
        self.title(title)
        self.geometry("600x400")
        self.transient(parent)
        self.grab_set()
        
        # 构建UI
        self._build_ui()
        
        # 居中显示
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f'+{x}+{y}')
    
    def _build_ui(self):
        """构建UI"""
        # 主容器
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # 订阅名称
        ttk.Label(main_frame, text="订阅名称:", font=("", 11, "bold")).grid(
            row=0, column=0, sticky='w', pady=(0, 5))
        self.ent_name = ttk.Entry(main_frame, width=50, font=("", 11))
        if self.subscription:
            self.ent_name.insert(0, self.subscription.get("name", ""))
        self.ent_name.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 15))
        
        # URL
        ttk.Label(main_frame, text="频道/播放列表 URL:", font=("", 11, "bold")).grid(
            row=2, column=0, sticky='w', pady=(0, 5))
        self.ent_url = ttk.Entry(main_frame, width=50, font=("", 11))
        if self.subscription:
            self.ent_url.insert(0, self.subscription.get("url", ""))
        self.ent_url.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(0, 15))
        
        # 设置框架
        settings_frame = ttk.LabelFrame(main_frame, text="订阅设置", padding="10")
        settings_frame.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(0, 15))
        
        # 检查间隔
        ttk.Label(settings_frame, text="检查间隔:", font=("", 10)).grid(
            row=0, column=0, sticky='w', padx=(0, 10))
        self.cmb_interval = ttk.Combobox(settings_frame, 
            values=["hourly", "daily", "weekly"], state="readonly", width=15)
        interval = "daily"
        if self.subscription:
            interval = self.subscription.get("check_interval", "daily")
        self.cmb_interval.set(interval)
        self.cmb_interval.grid(row=0, column=1, sticky='w')
        
        # 语言
        ttk.Label(settings_frame, text="下载语言:", font=("", 10)).grid(
            row=1, column=0, sticky='w', padx=(0, 10), pady=(10, 0))
        self.ent_langs = ttk.Entry(settings_frame, width=30)
        langs = "zh,en"
        if self.subscription:
            langs = ",".join(self.subscription.get("download_langs", ["zh", "en"]))
        self.ent_langs.insert(0, langs)
        self.ent_langs.grid(row=1, column=1, sticky='ew', pady=(10, 0))
        
        # 启用状态
        enabled = True
        if self.subscription:
            enabled = self.subscription.get("enabled", True)
        self.var_enabled = tk.BooleanVar(value=enabled)
        ttk.Checkbutton(settings_frame, text="启用此订阅", 
                       variable=self.var_enabled).grid(
            row=2, column=0, columnspan=2, sticky='w', pady=(10, 0))
        
        # 按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Button(btn_frame, text="确定", command=self._on_ok, width=12).pack(
            side='left', padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy, width=12).pack(
            side='left', padx=5)
        
        # 配置权重
        main_frame.columnconfigure(0, weight=1)
    
    def _on_ok(self):
        """确定按钮"""
        name = self.ent_name.get().strip()
        url = self.ent_url.get().strip()
        
        if not name:
            from tkinter import messagebox
            messagebox.showwarning("警告", "请输入订阅名称", parent=self)
            return
        
        if not url:
            from tkinter import messagebox
            messagebox.showwarning("警告", "请输入URL", parent=self)
            return
        
        self.result = {
            "name": name,
            "url": url,
            "check_interval": self.cmb_interval.get(),
            "download_langs": [l.strip() for l in self.ent_langs.get().split(",") if l.strip()],
            "enabled": self.var_enabled.get()
        }
        self.destroy()


__all__ = ['SchedulerJobDialog', 'SubscriptionDialog']

