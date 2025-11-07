# -*- coding: utf-8 -*-
"""
AI面板视图 - 纯UI，不包含业务逻辑
"""
import tkinter as tk
from tkinter import ttk
from gui.views.base_view import BaseView
from ui_components import Accordion, ModuleTitle


class AIPanel(BaseView):
    """
    AI处理面板
    
    职责：
    1. 展示AI配置UI
    2. 提供数据获取接口
    3. 更新UI状态
    """
    
    def _build_ui(self):
        """构建UI"""
        # 创建手风琴（懒加载模式，默认折叠）
        self.accordion = Accordion(
            parent=self,
            title="🤖 AI处理",
            expanded=False,  # 默认折叠，实现懒加载
            lazy_load=True,
            lazy_load_callback=self._build_content
        )
        self.accordion.pack(fill='both', expand=True)
    
    def _build_content(self, content):
        """构建内容（懒加载回调）"""
        # === AI摘要 ===
        ModuleTitle(content, "AI摘要").pack(fill='x', pady=(0, 5))
        
        # 启用AI摘要
        ai_enable_frame = tk.Frame(content)
        ai_enable_frame.pack(fill='x', pady=(0, 5))
        
        self.var_ai_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(ai_enable_frame, text="启用AI摘要",
                       variable=self.var_ai_enabled).pack(side='left')
        
        # 供应商和型号（横置）
        ai_model_frame = tk.Frame(content)
        ai_model_frame.pack(fill='x', pady=(0, 5))
        
        tk.Label(ai_model_frame, text="供应商:", font=("Segoe UI", 14, "bold")).pack(
            side='left', padx=(0, 5))
        
        self.cmb_provider = ttk.Combobox(
            ai_model_frame,
            values=["GPT", "Claude", "Gemini", "Perplexity", "DeepSeek", 
                   "Kimi", "Qwen", "GLM", "Grok", "自定义API", "本地模型"],
            state="readonly",
            width=10
        )
        self.cmb_provider.set("GPT")
        self.cmb_provider.pack(side='left', padx=(0, 8))
        
        tk.Label(ai_model_frame, text="型号:", font=("Segoe UI", 14, "bold")).pack(
            side='left', padx=(0, 5))
        
        self.cmb_model = ttk.Combobox(
            ai_model_frame,
            values=["gpt-5", "gpt-5-mini", "gpt-5-nano"],
            state="readonly",
            width=28
        )
        self.cmb_model.set("gpt-5")
        self.cmb_model.pack(side='left')
        
        # API Key
        ai_key_frame = tk.Frame(content)
        ai_key_frame.pack(fill='x', pady=(0, 5))
        
        tk.Label(ai_key_frame, text="Key:", font=("Segoe UI", 14, "bold")).pack(
            side='left', padx=(0, 5))
        
        self.ent_api_key = ttk.Entry(ai_key_frame, show="*", width=20)
        self.ent_api_key.pack(side='left', fill='x', expand=True)
        
        # Base URL（仅在自定义API时显示）
        self.ai_base_url_frame = tk.Frame(content)
        tk.Label(self.ai_base_url_frame, text="Base URL:", font=("Segoe UI", 14, "bold")).pack(
            side='left', padx=(0, 5))
        
        self.ent_base_url = ttk.Entry(self.ai_base_url_frame, width=40)
        self.ent_base_url.insert(0, "https://api.openai.com/v1")
        self.ent_base_url.pack(side='left', fill='x', expand=True)
        
        # 测试API按钮（所有供应商都显示）
        self.ai_test_frame = tk.Frame(content)
        self.btn_test_api = ttk.Button(self.ai_test_frame, text="🔍 测试API连接")
        self.btn_test_api.pack(side='left', padx=5)
        
        # 初始隐藏Base URL（只有自定义API时显示），但显示测试按钮
        self.ai_base_url_frame.pack_forget()
        self.ai_test_frame.pack(fill='x', pady=(0, 10))
        
        # === 双语对照 ===
        # 注意：翻译功能已移至独立的"字幕翻译"面板，此处不再显示
        ModuleTitle(content, "双语对照").pack(fill='x', pady=(10, 5))
        
        bilingual_frame = tk.Frame(content)
        bilingual_frame.pack(fill='x', pady=(0, 5))
        
        self.var_bilingual = tk.BooleanVar(value=False)
        ttk.Checkbutton(bilingual_frame, text="生成双语TXT",
                       variable=self.var_bilingual).pack(side='left', padx=(0, 8))
        
        tk.Label(bilingual_frame, text="排版:", font=("Segoe UI", 14, "bold")).pack(
            side='left', padx=(0, 5))
        
        self.cmb_bilingual_layout = ttk.Combobox(
            bilingual_frame,
            values=["并排", "上下"],
            state="readonly",
            width=5
        )
        self.cmb_bilingual_layout.set("并排")
        self.cmb_bilingual_layout.pack(side='left', padx=(0, 8))
        
        tk.Label(bilingual_frame, text="时间轴:", font=("Segoe UI", 14, "bold")).pack(
            side='left', padx=(0, 5))
        
        self.var_bilingual_timeline = tk.BooleanVar(value=True)
        ttk.Checkbutton(bilingual_frame, text="保留",
                       variable=self.var_bilingual_timeline).pack(side='left')
        
        # AI处理按钮
        btn_frame = tk.Frame(content)
        btn_frame.pack(fill='x', pady=(10, 0))
        
        self.btn_run_ai = ttk.Button(btn_frame, text="🚀 运行AI摘要")
        self.btn_run_ai.pack(side='left', padx=5)
    
    def get_config(self) -> dict:
        """
        获取AI配置
        
        Returns:
            配置字典
        """
        # 获取API Key
        try:
            api_key = self.ent_api_key.get()
            api_key = api_key.strip() if api_key else ""
        except:
            api_key = ""
        
        # 调试：打印获取的值
        print(f"[AIPanel.get_config] API Key长度: {len(api_key)}, 前10字符: {api_key[:10] if api_key else '(空)'}")
        
        config = {
            "ai_enabled": self.var_ai_enabled.get(),
            "ai_provider": self.cmb_provider.get(),
            "ai_model": self.cmb_model.get(),
            "ai_api_key": api_key,
            # 翻译功能已移至独立的"字幕翻译"面板，此处不再保存
            "bilingual_enabled": self.var_bilingual.get(),
            "bilingual_layout": self.cmb_bilingual_layout.get(),
            "bilingual_timeline": self.var_bilingual_timeline.get()
        }
        
        # 添加base_url（如果存在）
        if hasattr(self, 'ent_base_url'):
            config["ai_base_url"] = self.ent_base_url.get().strip()
        else:
            config["ai_base_url"] = ""
        
        return config
    
    def show_custom_api_fields(self, show: bool = True):
        """
        显示/隐藏自定义API字段
        
        Args:
            show: 是否显示Base URL字段（测试按钮始终显示）
        """
        if show:
            # 显示Base URL输入框（仅自定义API需要）
            self.ai_base_url_frame.pack(fill='x', pady=(0, 5), after=self.ent_api_key.master)
        else:
            # 隐藏Base URL输入框（测试按钮保持显示）
            self.ai_base_url_frame.pack_forget()
    
    def update_model_list(self, provider: str, models: list):
        """
        更新模型列表
        
        Args:
            provider: 供应商名称
            models: 模型列表
        """
        self.cmb_model['values'] = models
        if models:
            self.cmb_model.set(models[0])
    
    def load_config(self, config: dict):
        """
        加载配置到UI
        
        Args:
            config: 配置字典
        """
        if not config:
            return
        
        # AI摘要开关
        if "ai_enabled" in config:
            self.var_ai_enabled.set(config.get("ai_enabled", False))
        elif "enabled" in config:
            self.var_ai_enabled.set(config.get("enabled", False))
        
        # 供应商
        if "ai_provider" in config:
            provider = config.get("ai_provider", "GPT")
            if provider in self.cmb_provider["values"]:
                self.cmb_provider.set(provider)
        elif "provider" in config:
            provider = config.get("provider", "GPT")
            # 将内部名称映射回UI名称
            provider_map = {
                "openai": "GPT",
                "anthropic": "Claude",
                "gemini": "Gemini",
                "perplexity": "Perplexity",
                "deepseek": "DeepSeek",
                "moonshot": "Kimi",
                "qwen": "Qwen",
                "custom": "自定义API"
            }
            ui_provider = provider_map.get(provider, provider)
            if ui_provider in self.cmb_provider["values"]:
                self.cmb_provider.set(ui_provider)
        
        # 模型
        if "ai_model" in config:
            model = config.get("ai_model", "gpt-5")
            self.cmb_model.set(model)
        elif "model" in config:
            model = config.get("model", "gpt-5")
            self.cmb_model.set(model)
        
        # API Key（加载时自动填充）
        api_key = None
        if "ai_api_key" in config:
            api_key = config.get("ai_api_key", "")
        elif "api_key" in config:
            api_key = config.get("api_key", "")
        
        if api_key:
            self.ent_api_key.delete(0, "end")
            self.ent_api_key.insert(0, api_key)
            print(f"[AIPanel] API Key已加载: {api_key[:10]}...")  # 只显示前10个字符用于调试
        
        # Base URL
        if "ai_base_url" in config or "base_url" in config:
            base_url = config.get("ai_base_url") or config.get("base_url", "")
            if hasattr(self, 'ent_base_url') and base_url:
                self.ent_base_url.delete(0, "end")
                self.ent_base_url.insert(0, base_url)
        
        # 翻译功能已移至独立的"字幕翻译"面板，此处不再加载
        
        # 双语开关
        if "bilingual_enabled" in config:
            self.var_bilingual.set(config.get("bilingual_enabled", False))
        
        # 双语布局
        if "bilingual_layout" in config:
            layout = config.get("bilingual_layout", "并排")
            if layout in self.cmb_bilingual_layout["values"]:
                self.cmb_bilingual_layout.set(layout)
        
        # 双语时间轴
        if "bilingual_timeline" in config:
            self.var_bilingual_timeline.set(config.get("bilingual_timeline", True))
    
    def show_error(self, message: str):
        """
        显示错误消息
        
        Args:
            message: 错误消息
        """
        from tkinter import messagebox
        messagebox.showerror("错误", message)


__all__ = ['AIPanel']

