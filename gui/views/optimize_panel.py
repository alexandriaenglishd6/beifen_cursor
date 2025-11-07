# -*- coding: utf-8 -*-
"""
字幕优化面板视图 - 纯UI，不包含业务逻辑
"""
import tkinter as tk
from tkinter import ttk
from gui.views.base_view import BaseView
from ui_components import Accordion, ModuleTitle


class OptimizePanel(BaseView):
    """
    字幕优化面板
    
    职责：
    1. 展示字幕优化配置UI
    2. 提供配置获取接口
    3. 更新UI状态
    """
    
    def _build_ui(self):
        """构建UI"""
        # 创建手风琴（懒加载模式，默认折叠）
        self.accordion = Accordion(
            parent=self,
            title="✨ 字幕优化",
            expanded=False,  # 默认折叠，实现懒加载
            lazy_load=True,
            lazy_load_callback=self._build_content
        )
        self.accordion.pack(fill='both', expand=True)
    
    def _build_content(self, content):
        """构建内容（懒加载回调）"""
        # === 后处理优化 ===
        ModuleTitle(content, "后处理优化").pack(fill='x', pady=(0, 5))
        
        # 启用后处理
        postprocess_frame = tk.Frame(content)
        postprocess_frame.pack(fill='x', pady=(0, 5))
        
        self.var_postprocess_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(postprocess_frame, text="启用后处理优化",
                       variable=self.var_postprocess_enabled).pack(side='left')
        
        # 后处理选项（横置）
        options_frame1 = tk.Frame(content)
        options_frame1.pack(fill='x', pady=(0, 5))
        
        self.var_merge_short_lines = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame1, text="合并短行",
                       variable=self.var_merge_short_lines).pack(side='left', padx=(0, 15))
        
        self.var_dedupe_duplicates = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame1, text="去重相邻重复",
                       variable=self.var_dedupe_duplicates).pack(side='left', padx=(0, 15))
        
        self.var_strip_nonspeech = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame1, text="去除非语音标签",
                       variable=self.var_strip_nonspeech).pack(side='left', padx=(0, 15))
        
        self.var_normalize_whitespace = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame1, text="规范化空白",
                       variable=self.var_normalize_whitespace).pack(side='left')
        
        # 短行长度阈值
        short_line_frame = tk.Frame(content)
        short_line_frame.pack(fill='x', pady=(0, 10))
        
        tk.Label(short_line_frame, text="短行长度阈值:", font=("Segoe UI", 12)).pack(
            side='left', padx=(0, 5))
        
        self.spin_short_line_len = ttk.Spinbox(short_line_frame, from_=5, to=50, width=6)
        self.spin_short_line_len.set(12)
        self.spin_short_line_len.pack(side='left', padx=(0, 5))
        
        tk.Label(short_line_frame, text="字符", font=("Segoe UI", 12)).pack(side='left')
        
        # === 质量优化 ===
        ModuleTitle(content, "质量优化（中文）").pack(fill='x', pady=(0, 5))
        
        # 启用质量优化
        quality_frame = tk.Frame(content)
        quality_frame.pack(fill='x', pady=(0, 5))
        
        self.var_quality_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(quality_frame, text="启用质量优化",
                       variable=self.var_quality_enabled).pack(side='left')
        
        # 质量优化说明
        quality_hint = tk.Label(
            content,
            text="💡 质量优化包括：去噪（移除[Music]、[笑声]等）、标点规范化（半角→全角）、合并短句",
            font=("Segoe UI", 10),
            justify='left',
            fg='gray',
            wraplength=600
        )
        quality_hint.pack(anchor='w', pady=(0, 10))
        
        # === 质量警告 ===
        ModuleTitle(content, "质量警告").pack(fill='x', pady=(0, 5))
        
        # 启用质量警告
        warn_frame = tk.Frame(content)
        warn_frame.pack(fill='x', pady=(0, 5))
        
        self.var_quality_warn_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(warn_frame, text="启用质量警告",
                       variable=self.var_quality_warn_enabled).pack(side='left', padx=(0, 15))
        
        # 警告阈值
        threshold_frame = tk.Frame(content)
        threshold_frame.pack(fill='x', pady=(0, 10))
        
        tk.Label(threshold_frame, text="警告阈值:", font=("Segoe UI", 12)).pack(
            side='left', padx=(0, 5))
        
        self.spin_warn_threshold = ttk.Spinbox(threshold_frame, from_=0, to=100, width=6)
        self.spin_warn_threshold.set(60)
        self.spin_warn_threshold.pack(side='left', padx=(0, 5))
        
        tk.Label(threshold_frame, text="（低于此分数将显示警告）", font=("Segoe UI", 10), fg='gray').pack(side='left')
    
    def get_config(self) -> dict:
        """
        获取字幕优化配置
        
        Returns:
            配置字典
        """
        return {
            "postprocess": {
                "enabled": self.var_postprocess_enabled.get(),
                "merge_short_lines": self.var_merge_short_lines.get(),
                "dedupe_near_duplicates": self.var_dedupe_duplicates.get(),
                "strip_nonspeech": self.var_strip_nonspeech.get(),
                "normalize_whitespace": self.var_normalize_whitespace.get(),
                "short_line_len": int(self.spin_short_line_len.get())
            },
            "quality": {
                "enabled": self.var_quality_enabled.get(),
                "warn_threshold": int(self.spin_warn_threshold.get()),
                "warn_enabled": self.var_quality_warn_enabled.get()
            }
        }
    
    def load_config(self, config: dict):
        """
        加载配置到UI
        
        Args:
            config: 配置字典
        """
        if not config:
            return
        
        # 后处理配置
        if "postprocess" in config:
            pp_config = config["postprocess"]
            self.var_postprocess_enabled.set(pp_config.get("enabled", True))
            self.var_merge_short_lines.set(pp_config.get("merge_short_lines", True))
            self.var_dedupe_duplicates.set(pp_config.get("dedupe_near_duplicates", True))
            self.var_strip_nonspeech.set(pp_config.get("strip_nonspeech", False))
            self.var_normalize_whitespace.set(pp_config.get("normalize_whitespace", True))
            self.spin_short_line_len.set(str(pp_config.get("short_line_len", 12)))
        
        # 质量配置
        if "quality" in config:
            q_config = config["quality"]
            self.var_quality_enabled.set(q_config.get("enabled", True))
            self.var_quality_warn_enabled.set(q_config.get("warn_enabled", q_config.get("enabled", True)))
            self.spin_warn_threshold.set(str(q_config.get("warn_threshold", 60)))


__all__ = ['OptimizePanel']

