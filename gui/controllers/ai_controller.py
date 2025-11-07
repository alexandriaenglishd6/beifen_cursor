# -*- coding: utf-8 -*-
"""
AI控制器 - 连接视图和服务
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from gui.controllers.base_controller import BaseController
from events.event_bus import EventType, Event
from services.ai_service import AIService

if TYPE_CHECKING:
    from gui.views.ai_panel import AIPanel


class AIController(BaseController):
    """
    AI控制器
    
    职责：
    1. 处理用户交互（按钮点击等）
    2. 调用服务层执行AI处理
    3. 发布事件通知其他模块
    4. 更新视图状态
    """
    
    def __init__(self, view: AIPanel, config: dict):
        """
        初始化
        
        Args:
            view: AI面板视图
            config: 全局配置
        """
        self.view = view
        self.config = config
        self.service = AIService()
        self.last_run_dir: str = None
        
        super().__init__()
        
        # 统一初始化顺序由 InitializationManager 保证，这里同步初始化
        self._setup_button_bindings()
        self._setup_auto_save()
        self.load_config()
    
    def _setup_button_bindings(self):
        """设置按钮绑定（延迟执行，确保懒加载内容已创建）"""
        # 确保内容已加载（如果是懒加载模式）
        if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
            # 触发懒加载（如果尚未加载）
            self.view.accordion.get_content_frame()
        
        # 绑定按钮事件
        if hasattr(self.view, 'btn_run_ai'):
            self.view.btn_run_ai.config(command=self.run_ai_processing)
        # 若未存在，InitializationManager 已确保UI创建，这里不再重试
        
        # 绑定API Key验证按钮（如果存在）
        if hasattr(self.view, 'btn_test_api'):
            self.view.btn_test_api.config(command=self.test_api_key)
        
        # 绑定供应商切换事件（立即绑定，确保切换时能更新型号）
        if hasattr(self.view, 'cmb_provider'):
            self.view.cmb_provider.bind("<<ComboboxSelected>>", lambda e: self._on_provider_changed())
    
    def _setup_event_listeners(self):
        """设置事件监听"""
        # 监听主题变化
        self.event_bus.subscribe(EventType.THEME_CHANGED, self._on_theme_changed)
        
        # 监听下载完成事件（自动运行AI）
        self.event_bus.subscribe(EventType.DOWNLOAD_COMPLETED, self._on_download_completed)
    
    def _setup_auto_save(self):
        """设置自动保存（当配置变化时）"""
        # 获取root窗口
        try:
            root = self.view.winfo_toplevel()
        except:
            return  # 如果视图还未完全初始化，稍后再试
        
        # 确保内容已加载（如果是懒加载模式）
        if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
            # 触发懒加载（如果尚未加载）
            self.view.accordion.get_content_frame()
        
        # 检查必要的控件是否存在（InitializationManager已确保就绪）
        if not hasattr(self.view, 'ent_api_key') or not hasattr(self.view, 'cmb_provider'):
            print("[AIController] 警告: 必要控件缺失")
            return
        
        def _delayed_save():
            """延迟保存（500ms后）"""
            if hasattr(self, '_save_timer') and self._save_timer:
                try:
                    root.after_cancel(self._save_timer)
                except:
                    pass
            
            self._save_timer = root.after(500, self._auto_save_config)
        
        # API Key输入框失去焦点时保存
        self.view.ent_api_key.bind("<FocusOut>", lambda e: _delayed_save())
        
        # 供应商切换时保存（供应商切换已在__init__中绑定，这里只添加保存逻辑）
        # 注意：供应商切换的事件处理会在_on_provider_changed中执行，这里只添加保存
        def _on_provider_with_save(e):
            self._on_provider_changed()
            _delayed_save()
        
        # 移除旧绑定，添加新绑定（包含保存逻辑）
        try:
            self.view.cmb_provider.bind("<<ComboboxSelected>>", _on_provider_with_save)
        except:
            pass
        
        # 模型切换时保存
        self.view.cmb_model.bind("<<ComboboxSelected>>", lambda e: _delayed_save())
        
        # Base URL输入框失去焦点时保存（如果存在）
        if hasattr(self.view, 'ent_base_url'):
            self.view.ent_base_url.bind("<FocusOut>", lambda e: _delayed_save())
        
        # 复选框变化时保存
        try:
            self.view.var_ai_enabled.trace_add("write", lambda *args: _delayed_save())
            # 翻译功能已移至独立的"字幕翻译"面板，此处不再处理
            self.view.var_bilingual.trace_add("write", lambda *args: _delayed_save())
        except:
            pass
    
    def _auto_save_config(self):
        """自动保存配置"""
        try:
            view_config = self.view.get_config()
            config = {
                "enabled": view_config.get("ai_enabled", False),
                "provider": view_config.get("ai_provider", "GPT"),
                "model": view_config.get("ai_model", "gpt-5"),
                "api_key": view_config.get("ai_api_key", ""),
                "base_url": view_config.get("ai_base_url", ""),
                # 翻译功能已移至独立的"字幕翻译"面板，此处不再保存
                "bilingual_enabled": view_config.get("bilingual_enabled", False),
            }
            self._save_config(config)
        except Exception as e:
            # 静默失败，不干扰用户
            pass
    
    def _on_provider_changed(self):
        """
        供应商切换处理
        """
        provider = self.view.cmb_provider.get()
        
        # 如果是自定义API，显示Base URL输入框
        if provider == "自定义API":
            self.view.show_custom_api_fields(show=True)
            # 自定义API可以使用任意模型，允许用户手动输入或从列表选择
            common_models = ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", 
                            "claude-3-5-sonnet-20241022", "claude-3-opus-20240229",
                            "deepseek-chat", "qwen-plus", "custom"]
            self.view.cmb_model.config(state="normal")  # 允许编辑
            self.view.update_model_list(provider, common_models)
        else:
            self.view.show_custom_api_fields(show=False)
            self.view.cmb_model.config(state="readonly")  # 只读模式
            
            # 供应商-型号映射表
            model_map = {
                "GPT": ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4.1-mini"],
                "Claude": ["opus-4.1", "opus-4.0", "sonnet-4.5", "sonnet-4", "sonnet-3.7"],
                "Gemini": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
                "Perplexity": ["sonar-pro", "sonar-reasoning", "sonar-large", "sonar-medium"],
                "DeepSeek": ["deepseek-chat", "deepseek-reasoner"],
                "Kimi": ["kimi-k2-0711-preview", "kimi-k2-turbo-preview", "moonshot-v1-128k"],
                "Qwen": ["qwen-max", "qwen-plus", "qwen-turbo"],
                "GLM": ["glm-4", "glm-4-air", "glm-3-turbo"],
                "Grok": ["grok-1", "grok-beta"],
                "本地模型": ["custom", "ollama", "llama-2", "llama-3"]
            }
            
            models = model_map.get(provider, ["default"])
            self.view.update_model_list(provider, models)
        
        self._log(f"[AI] 供应商切换: {provider}")
    
    def run_ai_processing(self, run_dir: str = None):
        """
        运行AI处理
        
        Args:
            run_dir: 运行目录（可选，如果None则使用最近一次下载的目录）
        """
        if not run_dir:
            if not self.last_run_dir:
                self.view.show_error("请先完成下载任务，或指定运行目录")
                return
            run_dir = self.last_run_dir
        
        # 收集配置
        config = self._collect_ai_config()
        
        # 检查是否启用AI（注意：配置字典中使用的是"enabled"而不是"ai_enabled"）
        if not config.get("enabled"):
            self.view.show_error("请先启用AI摘要功能")
            return
        
        # 发布事件：AI处理开始
        self.event_bus.publish(Event(
            EventType.AI_PROCESSING_STARTED,
            {"run_dir": run_dir}
        ))
        
        # 启动AI处理
        success = self.service.run_ai_processing(
            run_dir=run_dir,
            ai_config=config,
            progress_callback=self._on_progress,
            completion_callback=self._on_completion
        )
        
        if not success:
            self.view.show_error("已有AI处理任务正在运行")
            self.event_bus.publish(Event(
                EventType.AI_PROCESSING_FAILED,
                {"reason": "任务冲突"}
            ))
    
    def _collect_ai_config(self) -> dict:
        """
        收集AI配置
        
        Returns:
            配置字典
        """
        view_config = self.view.get_config()
        
        config = {
            "enabled": view_config.get("ai_enabled", False),
            "provider": view_config.get("ai_provider", "GPT"),
            "model": view_config.get("ai_model", "gpt-5"),
            "api_key": view_config.get("ai_api_key", ""),
            "base_url": view_config.get("ai_base_url", ""),
            "workers": self.config.get("max_workers", 3),
            "max_chars_per_video": 30000,
            "translate_enabled": view_config.get("translate_enabled", False),
            "translate_langs": view_config.get("translate_langs", ["zh"]),
            "translate_engine": view_config.get("translate_engine", "Google"),
            "bilingual_enabled": view_config.get("bilingual_enabled", False),
            "bilingual_layout": view_config.get("bilingual_layout", "并排"),
            "bilingual_timeline": view_config.get("bilingual_timeline", True)
        }
        
        # 自动保存配置
        self._save_config(config)
        
        return config
    
    def _save_config(self, config: dict):
        """
        保存AI配置
        
        Args:
            config: 配置字典
        """
        try:
            from services.config_service import get_config_service
            config_service = get_config_service()
            config_service.save_ai_config(config)
            config_service.save()
        except Exception as e:
            # 保存失败不阻塞主流程
            print(f"[AIController] 保存配置失败: {e}")
    
    def load_config(self):
        """加载保存的配置到UI"""
        try:
            # 确保内容已加载（如果是懒加载模式）
            if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
                # 触发懒加载（如果尚未加载）
                self.view.accordion.get_content_frame()
        except:
            pass
        
        try:
            from services.config_service import get_config_service
            config_service = get_config_service()
            config = config_service.load_ai_config()
            
            # 调试：打印加载的配置
            print(f"[AIController] 加载AI配置: provider={config.get('provider')}, model={config.get('model')}, api_key={'***' if config.get('api_key') else '(空)'}")
            
            # 映射内部配置到UI配置格式
            ui_config = {
                "ai_enabled": config.get("enabled", False),
                "ai_provider": config.get("provider", "GPT"),
                "ai_model": config.get("model", "gpt-5"),
                "ai_api_key": config.get("api_key", ""),
                "ai_base_url": config.get("base_url", ""),
                "translate_enabled": config.get("translate_enabled", False),
                "translate_langs": config.get("translate_langs", ["zh", "en"]),
                "bilingual_enabled": config.get("bilingual_enabled", False),
            }
            self.view.load_config(ui_config)
            # 触发供应商切换以更新模型列表
            if hasattr(self, '_on_provider_changed'):
                self._on_provider_changed()
        except Exception as e:
            print(f"[AIController] 加载配置失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_progress(self, progress: dict):
        """
        进度回调
        
        Args:
            progress: 进度信息
        """
        # 发布进度事件
        self.event_bus.publish(Event(
            EventType.AI_PROCESSING_PROGRESS,
            progress
        ))
    
    def _on_completion(self, result: dict):
        """
        AI处理完成回调
        
        Args:
            result: 结果信息
        """
        if "error" in result:
            # AI处理失败
            self.event_bus.publish(Event(
                EventType.AI_PROCESSING_FAILED,
                {"reason": result["error"]}
            ))
            self._log(f"AI处理失败: {result['error']}", "ERROR")
        else:
            # AI处理成功
            total = result.get("total", 0)
            done = result.get("done", 0)
            html_path = result.get("html_path")
            
            self.event_bus.publish(Event(
                EventType.AI_PROCESSING_COMPLETED,
                result
            ))
            
            self._log(f"AI摘要完成: {done}/{total} 个视频", "SUCCESS")
            
            if html_path:
                self._log(f"HTML报告已生成: {html_path}", "SUCCESS")
    
    def _on_download_completed(self, event: Event):
        """
        下载完成处理（自动保存run_dir，供AI处理使用）
        
        Args:
            event: 下载完成事件
        """
        run_dir = event.data.get("run_dir", "")
        if run_dir:
            self.last_run_dir = run_dir
    
    def test_api_key(self):
        """
        测试API连接（支持所有供应商）
        """
        config = self._collect_ai_config()
        provider = config.get("provider", "")
        api_key = config.get("api_key", "").strip()
        base_url = config.get("base_url", "").strip()
        model = config.get("model", "").strip()
        
        if not api_key:
            self.view.show_error("请先输入API Key")
            return
        
        # 如果是自定义API，需要Base URL和模型名称
        if provider == "自定义API":
            if not base_url:
                self.view.show_error("请先输入Base URL")
                return
            if not model:
                self.view.show_error("请先输入或选择模型名称")
                return
        
        # 对于其他供应商，也需要模型名称
        if not model and provider != "自定义API":
            self.view.show_error("请先选择模型")
            return
        
        # 调用服务层测试API
        self._log(f"[AI] 开始测试API连接: {provider}", "INFO")
        try:
            result = self.service.test_api_key(
                provider=provider,
                api_key=api_key,
                base_url=base_url if provider == "自定义API" else "",
                model=model
            )
            
            if result.get("success"):
                from tkinter import messagebox
                latency = result.get('latency_ms', 0)
                provider_name = result.get('provider', provider)
                message = f"API连接测试成功！\n\n供应商: {provider}\n模型: {model}\n延迟: {latency:.0f}ms"
                if provider_name != provider:
                    message += f"\n实际提供者: {provider_name}"
                messagebox.showinfo("测试成功", message)
                self._log(f"✅ API连接测试成功: {result.get('message', '')}", "SUCCESS")
            else:
                error_msg = result.get("error", "未知错误")
                self.view.show_error(f"API连接测试失败:\n\n供应商: {provider}\n模型: {model}\n\n错误: {error_msg}")
                self._log(f"❌ API连接测试失败: {error_msg}", "ERROR")
        except Exception as e:
            self.view.show_error(f"测试过程中发生错误:\n{str(e)}")
            self._log(f"❌ 测试错误: {str(e)}", "ERROR")
    
    def _on_theme_changed(self, event: Event):
        """
        主题变化处理
        
        Args:
            event: 事件对象
        """
        theme = event.data.get("theme")
        self.view.update_theme(theme)


__all__ = ['AIController']

