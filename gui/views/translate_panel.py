# -*- coding: utf-8 -*-
"""
字幕翻译面板视图 - 纯UI，不包含业务逻辑
"""
import tkinter as tk
from tkinter import ttk
from gui.views.base_view import BaseView
from ui_components import Accordion, ModuleTitle


class TranslatePanel(BaseView):
    """
    字幕翻译面板
    
    职责：
    1. 展示字幕翻译UI
    2. 提供配置获取接口
    3. 更新UI状态
    """
    
    def _build_ui(self):
        """构建UI"""
        self.accordion = Accordion(
            parent=self,
            title="🌐 字幕翻译",
            expanded=False,
            lazy_load=True,
            lazy_load_callback=self._build_content
        )
        self.accordion.pack(fill='both', expand=True)
    
    def _build_content(self, content):
        """构建内容（懒加载回调）"""
        # === 基本设置 ===
        ModuleTitle(content, "基本设置").pack(fill='x', pady=(0, 5))
        
        basic_frame = tk.Frame(content)
        basic_frame.pack(fill='x', pady=(0, 10))
        
        self.var_translate_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(basic_frame, text="启用翻译",
                       variable=self.var_translate_enabled).pack(side='left', padx=(0, 15))
        
        # === 源语言和目标语言 ===
        ModuleTitle(content, "语言设置").pack(fill='x', pady=(10, 5))
        
        lang_frame = tk.Frame(content)
        lang_frame.pack(fill='x', pady=(0, 10))
        
        tk.Label(lang_frame, text="源语言:", font=("Segoe UI", 12)).pack(side='left', padx=(0, 5))
        self.cmb_src_lang = ttk.Combobox(
            lang_frame,
            values=["auto", "zh", "en", "ja", "ko", "fr", "de", "es", "ru"],
            state="readonly",
            width=10
        )
        self.cmb_src_lang.set("auto")
        self.cmb_src_lang.pack(side='left', padx=(0, 15))
        
        tk.Label(lang_frame, text="目标语言:", font=("Segoe UI", 12)).pack(side='left', padx=(0, 5))
        self.cmb_tgt_lang = ttk.Combobox(
            lang_frame,
            values=["zh", "en", "ja", "ko", "fr", "de", "es", "ru"],
            state="readonly",
            width=10
        )
        self.cmb_tgt_lang.set("zh")
        self.cmb_tgt_lang.pack(side='left')
        
        # === 翻译提供商 ===
        ModuleTitle(content, "翻译提供商").pack(fill='x', pady=(10, 5))
        
        provider_frame = tk.Frame(content)
        provider_frame.pack(fill='x', pady=(0, 10))
        
        tk.Label(provider_frame, text="提供商:", font=("Segoe UI", 12)).pack(side='left', padx=(0, 5))
        self.cmb_provider = ttk.Combobox(
            provider_frame,
            values=["mock", "openai", "google", "deepl", "baidu"],
            state="readonly",
            width=12
        )
        self.cmb_provider.set("mock")
        self.cmb_provider.pack(side='left', padx=(0, 15))
        
        # 提示信息
        info_label = tk.Label(
            provider_frame,
            text="提示：mock=测试模式，google=免费(需安装googletrans)，openai=需要API Key",
            font=("Segoe UI", 9),
            foreground="#64748b"
        )
        info_label.pack(side='left', padx=(10, 0))
        
        # === 输出格式 ===
        ModuleTitle(content, "输出格式").pack(fill='x', pady=(10, 5))
        
        format_frame = tk.Frame(content)
        format_frame.pack(fill='x', pady=(0, 10))
        
        tk.Label(format_frame, text="格式:", font=("Segoe UI", 12)).pack(side='left', padx=(0, 5))
        self.cmb_format = ttk.Combobox(
            format_frame,
            values=["srt", "vtt", "txt"],
            state="readonly",
            width=8
        )
        self.cmb_format.set("srt")
        self.cmb_format.pack(side='left', padx=(0, 15))
        
        # === 后处理选项 ===
        ModuleTitle(content, "后处理选项").pack(fill='x', pady=(10, 5))
        
        postprocess_frame = tk.Frame(content)
        postprocess_frame.pack(fill='x', pady=(0, 10))
        
        self.var_postprocess = tk.BooleanVar(value=True)
        ttk.Checkbutton(postprocess_frame, text="启用后处理（清洗与术语统一）",
                       variable=self.var_postprocess).pack(side='left', padx=(0, 15))
    
    def get_config(self) -> dict:
        """获取翻译配置"""
        return {
            "enabled": self.var_translate_enabled.get(),
            "src": self.cmb_src_lang.get(),
            "tgt": self.cmb_tgt_lang.get(),
            "format": self.cmb_format.get(),
            "provider": self.cmb_provider.get(),
            "postprocess": self.var_postprocess.get()
        }
    
    def load_config(self, config: dict):
        """加载配置到UI"""
        self.var_translate_enabled.set(config.get("enabled", False))
        self.cmb_src_lang.set(config.get("src", "auto"))
        self.cmb_tgt_lang.set(config.get("tgt", "zh"))
        self.cmb_format.set(config.get("format", "srt"))
        self.cmb_provider.set(config.get("provider", "mock"))
        self.var_postprocess.set(config.get("postprocess", True))


__all__ = ['TranslatePanel']

