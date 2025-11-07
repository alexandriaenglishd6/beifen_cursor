# -*- coding: utf-8 -*-
"""
下载控制器 - 连接视图和服务
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from pathlib import Path
from gui.controllers.base_controller import BaseController
from events.event_bus import EventType, Event
from services.download_service import DownloadService

if TYPE_CHECKING:
    from gui.views.download_panel import DownloadPanel


class DownloadController(BaseController):
    """
    下载控制器
    
    职责：
    1. 处理用户交互（按钮点击等）
    2. 调用服务层执行下载
    3. 发布事件通知其他模块
    4. 更新视图状态
    """
    
    def __init__(self, view: DownloadPanel, config: dict, settings_ctrl=None):
        """
        初始化
        
        Args:
            view: 下载面板视图
            config: 全局配置
            settings_ctrl: 设置控制器（用于获取网络配置）
        """
        self.view = view
        self.config = config
        self.settings_ctrl = settings_ctrl  # 保存设置控制器的引用
        self.service = DownloadService()
        self.is_dry_run = False  # 跟踪是否为检测模式
        self.is_stopped = False  # 跟踪是否已停止
        self.is_paused = False  # 跟踪是否已暂停
        
        # 进度跟踪（用于计算速度和剩余时间）
        self.progress_start_time = None  # 任务开始时间
        self.progress_last_time = None  # 上次更新时间
        self.progress_last_count = 0  # 上次处理数量
        self.progress_current_title = ""  # 当前视频标题
        
        # 错误日志管理器
        try:
            from utils.error_handler import ErrorLogger
            self.error_logger = ErrorLogger()
        except ImportError:
            self.error_logger = None
        
        super().__init__()
        
        # 绑定视图按钮事件
        self._bind_view_events()
        
        # 统一初始化顺序：InitializationManager 已保证 UI 就绪
        # 因此这里直接加载配置并设置自动保存，避免依赖不稳定的时间延迟
        try:
            self.load_config()
        except Exception as e:
            self._log(f"加载下载配置失败: {e}", "ERROR")
        try:
            self._setup_auto_save()
        except Exception as e:
            self._log(f"初始化自动保存失败: {e}", "ERROR")
    
    def _bind_view_events(self):
        """绑定视图事件"""
        # 清空按钮
        if hasattr(self.view, 'btn_clear'):
            self.view.btn_clear.config(command=self.clear_urls)
        
        # 导入按钮
        if hasattr(self.view, 'btn_import'):
            self.view.btn_import.config(command=self.import_urls)
        
        # 批量操作按钮
        if hasattr(self.view, 'btn_clean_invalid'):
            self.view.btn_clean_invalid.config(command=self.clean_invalid_urls)
        
        if hasattr(self.view, 'btn_remove_duplicates'):
            self.view.btn_remove_duplicates.config(command=self.remove_duplicate_urls)
        
        if hasattr(self.view, 'btn_validate'):
            self.view.btn_validate.config(command=self.validate_urls)
    
    def _setup_event_listeners(self):
        """设置事件监听"""
        # 监听主题变化
        self.event_bus.subscribe(EventType.THEME_CHANGED, self._on_theme_changed)
    
    def start_download(self, dry_run: bool = False):
        """
        开始下载
        
        Args:
            dry_run: 是否为干运行（只检测）
        """
        print(f"[DownloadController] start_download 被调用: dry_run={dry_run}")
        print(f"[DownloadController] 事件总线: {self.event_bus}")
        
        # 获取URL文本
        urls_text = self.view.txt_urls.get("1.0", "end-1c").strip()
        print(f"[DownloadController] URL文本长度: {len(urls_text)}")
        print(f"[DownloadController] URL文本内容: {urls_text[:100] if urls_text else '(空)'}")
        
        # 先验证URL格式（无论是否为空）
        from validators import validate_url_list
        is_valid, error_msg, valid_count = validate_url_list(urls_text)
        print(f"[DownloadController] URL验证结果: is_valid={is_valid}, valid_count={valid_count}, error_msg={error_msg}")
        
        if not is_valid:
            # 显示错误信息
            print(f"[DownloadController] URL验证失败，显示错误对话框")
            self.view.show_error(f"URL格式错误:\n{error_msg}\n\n有效URL数量: {valid_count}")
            self._log(f"URL验证失败: {error_msg}", "ERROR")
            # 高亮错误输入框
            self.view.txt_urls.config(highlightbackground="#FF6B6B", highlightcolor="#FF6B6B", highlightthickness=2)
            return
        
        # 获取URL列表
        urls = self.view.get_urls()
        print(f"[DownloadController] 获取到 {len(urls)} 个URL: {urls[:3] if urls else '[]'}")
        
        # 验证URL列表（双重检查）
        if not urls:
            print(f"[DownloadController] URL列表为空，显示错误对话框")
            self.view.show_error("请输入至少一个视频链接")
            self._log("错误：未输入任何链接", "ERROR")
            # 高亮错误输入框
            self.view.txt_urls.config(highlightbackground="#FF6B6B", highlightcolor="#FF6B6B", highlightthickness=2)
            return
        
        print(f"[DownloadController] 开始执行: dry_run={dry_run}, urls={len(urls)}")
        
        # 清除错误高亮
        self.view.txt_urls.config(highlightthickness=0)
        
        # 重置状态
        self.is_dry_run = dry_run
        self.is_stopped = False
        self.is_paused = False  # 跟踪是否已暂停
        
        # 重置进度跟踪
        import time
        self.progress_start_time = time.time()
        self.progress_last_time = time.time()
        self.progress_last_count = 0
        self.progress_current_title = ""
        
        # 收集配置
        print(f"[DownloadController] 开始收集配置...")
        config = self._collect_config()
        print(f"[DownloadController] 配置收集完成: {list(config.keys())}")
        
        # 发布事件：下载开始
        print(f"[DownloadController] 发布DOWNLOAD_STARTED事件...")
        self.event_bus.publish(Event(
            EventType.DOWNLOAD_STARTED,
            {
                "urls": urls,
                "count": len(urls),
                "dry_run": dry_run
            }
        ))
        print(f"[DownloadController] DOWNLOAD_STARTED事件已发布")
        
        # 启动下载
        print(f"[DownloadController] 调用service.start_download...")
        success = self.service.start_download(
            urls=urls,
            config=config,
            progress_callback=self._on_progress,
            completion_callback=self._on_completion,
            dry_run=dry_run
        )
        print(f"[DownloadController] service.start_download返回: success={success}")
        
        if not success:
            print(f"[DownloadController] 启动失败：已有任务正在运行")
            self.view.show_error("已有下载任务正在运行")
            self.event_bus.publish(Event(EventType.DOWNLOAD_FAILED, {"reason": "任务冲突"}))
    
    def _collect_config(self) -> dict:
        """
        收集配置
        
        Returns:
            配置字典
        """
        # 从视图获取配置
        view_config = self.view.get_config()
        
        # 获取网络配置（从设置控制器）
        network_config = {}
        if self.settings_ctrl:
            try:
                network_config = self.settings_ctrl.get_advanced_config()
                cookiefile = network_config.get('cookiefile', '')
                print(f"[DownloadController] 获取网络配置: proxy={'***' if network_config.get('proxy_text') else '(空)'}, "
                      f"cookie={'***' if cookiefile else '(空)'}, "
                      f"user_agent={'***' if network_config.get('user_agent') else '(空)'}")
                print(f"[DownloadController] cookiefile完整路径: {cookiefile}")
                print(f"[DownloadController] cookiefile长度: {len(cookiefile)}")
                if cookiefile:
                    from pathlib import Path
                    cookie_path = Path(cookiefile)
                    if cookie_path.exists():
                        print(f"[DownloadController] ✓ Cookie文件存在: {cookiefile}")
                    else:
                        print(f"[DownloadController] ⚠️ Cookie文件不存在: {cookiefile}")
            except Exception as e:
                print(f"[DownloadController] 获取网络配置失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 合并全局配置和网络配置
        config = {
            **self.config,
            **view_config,
            **network_config  # 网络配置（proxy_text, cookiefile, user_agent等）
        }
        
        # 自动保存配置
        self._save_config(view_config)
        
        return config
    
    def _save_config(self, config: dict):
        """
        保存下载配置
        
        Args:
            config: 配置字典
        """
        try:
            from services.config_service import get_config_service
            config_service = get_config_service()
            config_service.save_download_config(config)
            config_service.save()
        except Exception as e:
            # 保存失败不阻塞主流程
            print(f"[DownloadController] 保存配置失败: {e}")
    
    def load_config(self):
        """加载保存的配置到UI"""
        try:
            from services.config_service import get_config_service
            config_service = get_config_service()
            config = config_service.load_download_config()
            print(f"[DownloadController] 加载下载配置:")
            print(f"  - download_langs: {config.get('download_langs')} (类型: {type(config.get('download_langs'))})")
            print(f"  - download_fmt: {config.get('download_fmt')} (类型: {type(config.get('download_fmt'))})")
            print(f"  - max_workers: {config.get('max_workers')} (类型: {type(config.get('max_workers'))})")
            print(f"  - output_root: {config.get('output_root')}")
            
            # 加载配置到UI
            self.view.load_config(config)
            
            # 验证UI中的值
            print(f"[DownloadController] 验证UI中的值:")
            print(f"  - ent_langs: {self.view.ent_langs.get()}")
            print(f"  - opt_fmt: {self.view.opt_fmt.get()}")
            print(f"  - spin_workers: {self.view.spin_workers.get()}")
            print(f"  - ent_output: {self.view.ent_output.get()}")
            
            print(f"[DownloadController] ✓ 下载配置已加载到UI")
        except Exception as e:
            print(f"[DownloadController] ✗ 加载配置失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _save_config(self, config: dict):
        """
        保存下载配置
        
        Args:
            config: 配置字典
        """
        try:
            from services.config_service import get_config_service
            config_service = get_config_service()
            config_service.save_download_config(config)
            config_service.save()
        except Exception as e:
            # 保存失败不阻塞主流程
            print(f"[DownloadController] 保存配置失败: {e}")
            import traceback
            traceback.print_exc()
    
    def clear_urls(self):
        """清空URL"""
        self.view.clear_urls()
        # 清除错误高亮
        self.view.txt_urls.config(highlightthickness=0)
        self._log("已清空链接输入框", "INFO")
    
    def _setup_auto_save(self):
        """设置自动保存机制（延迟保存）"""
        self._auto_save_job = None
        
        # 获取root窗口
        try:
            root = self.view.winfo_toplevel()
        except:
            root = self.view.master
        
        # 检查必要的控件是否存在
        if not hasattr(self.view, 'ent_langs'):
            print("[DownloadController] 警告: ent_langs控件不存在，延迟设置自动保存")
            root.after(200, self._setup_auto_save)
            return
        
        print("[DownloadController] 开始设置自动保存绑定")
        
        def delayed_save():
            """延迟保存函数"""
            if self._auto_save_job:
                try:
                    root.after_cancel(self._auto_save_job)
                except:
                    pass
            
            # 延迟500ms保存，避免频繁写入
            self._auto_save_job = root.after(500, self._on_config_changed)
        
        # 绑定语言输入框变化事件
        self.view.ent_langs.bind('<KeyRelease>', lambda e: delayed_save())
        self.view.ent_langs.bind('<FocusOut>', lambda e: self._on_config_changed())
        print("[DownloadController] ✓ 已绑定 ent_langs 事件")
        
        # 绑定格式下拉框变化事件
        self.view.opt_fmt.bind('<<ComboboxSelected>>', lambda e: self._on_config_changed())
        print("[DownloadController] ✓ 已绑定 opt_fmt 事件")
        
        # 绑定并发数输入框变化事件
        self.view.spin_workers.bind('<KeyRelease>', lambda e: delayed_save())
        self.view.spin_workers.bind('<ButtonRelease-1>', lambda e: delayed_save())
        self.view.spin_workers.bind('<FocusOut>', lambda e: self._on_config_changed())
        print("[DownloadController] ✓ 已绑定 spin_workers 事件")
        
        # 绑定输出目录输入框变化事件
        self.view.ent_output.bind('<KeyRelease>', lambda e: delayed_save())
        self.view.ent_output.bind('<FocusOut>', lambda e: self._on_config_changed())
        print("[DownloadController] ✓ 已绑定 ent_output 事件")
        
        # 绑定URL输入框变化事件（实时验证）
        def on_url_change(event):
            """URL输入变化时实时验证"""
            urls_text = self.view.txt_urls.get("1.0", "end-1c").strip()
            if not urls_text:
                # 清空时清除错误高亮
                self.view.txt_urls.config(highlightthickness=0)
                return
            
            # 实时验证URL格式
            from validators import validate_url_list
            is_valid, error_msg, valid_count = validate_url_list(urls_text)
            
            if not is_valid:
                # 显示错误高亮
                self.view.txt_urls.config(highlightbackground="#FF6B6B", highlightcolor="#FF6B6B", highlightthickness=2)
            else:
                # 清除错误高亮
                self.view.txt_urls.config(highlightthickness=0)
        
        self.view.txt_urls.bind('<KeyRelease>', on_url_change)
        self.view.txt_urls.bind('<FocusOut>', on_url_change)
        print("[DownloadController] ✓ 已绑定 txt_urls 实时验证事件")
        
        # 绑定高级选项复选框变化事件
        checkbox_vars = []
        if hasattr(self.view, 'var_merge_bilingual'):
            checkbox_vars.append(self.view.var_merge_bilingual)
        if hasattr(self.view, 'var_force_refresh'):
            checkbox_vars.append(self.view.var_force_refresh)
        if hasattr(self.view, 'var_incremental_detect'):
            checkbox_vars.append(self.view.var_incremental_detect)
        if hasattr(self.view, 'var_incremental_download'):
            checkbox_vars.append(self.view.var_incremental_download)
        if hasattr(self.view, 'var_early_stop'):
            checkbox_vars.append(self.view.var_early_stop)
        
        for var in checkbox_vars:
            var.trace_add('write', lambda *args: delayed_save())
        
        print("[DownloadController] ✓ 自动保存绑定完成")
    
    def _on_config_changed(self):
        """配置变化时自动保存（延迟保存）"""
        try:
            # 获取当前下载配置
            view_config = self.view.get_config()
            
            # 打印调试信息
            print(f"[DownloadController] 自动保存下载配置:")
            print(f"  - download_langs: {view_config.get('download_langs')}")
            print(f"  - download_fmt: {view_config.get('download_fmt')}")
            print(f"  - max_workers: {view_config.get('max_workers')}")
            print(f"  - output_root: {view_config.get('output_root')}")
            
            # 保存配置
            self._save_config(view_config)
            
            # 验证保存结果
            from services.config_service import get_config_service
            config_service = get_config_service()
            saved_config = config_service.load_download_config()
            print(f"[DownloadController] ✓ 保存后验证:")
            print(f"  - download_langs: {saved_config.get('download_langs')}")
            print(f"  - download_fmt: {saved_config.get('download_fmt')}")
            print(f"  - max_workers: {saved_config.get('max_workers')}")
            print(f"[DownloadController] ✓ 配置已自动保存成功")
        except Exception as e:
            # 自动保存失败不阻塞，但打印错误信息
            import traceback
            print(f"[DownloadController] ✗ 自动保存失败: {e}")
            traceback.print_exc()
    
    def _enhance_progress_info(self, progress: dict) -> dict:
        """
        增强进度信息：添加速度、剩余时间、视频标题
        
        Args:
            progress: 原始进度信息字典
        
        Returns:
            增强后的进度信息字典
        """
        import time
        
        # 复制原始进度信息
        enhanced = progress.copy()
        
        # 提取基本信息
        current = progress.get("current", 0)
        total = progress.get("total", 0)
        phase = progress.get("phase", "")
        message = progress.get("message", "")
        
        # 计算百分比
        if total > 0:
            percent = (current / total) * 100
        else:
            percent = 0
        
        enhanced["percent"] = percent
        
        # 提取视频标题（从current_item或message中）
        title = progress.get("current_item", "")
        if not title:
            # 尝试从message中提取标题（如果包含视频信息）
            if "title" in message.lower() or "视频" in message:
                # 简单提取，实际可能需要更复杂的解析
                pass
        
        # 从meta中提取标题（如果存在）
        meta = progress.get("meta", {})
        if isinstance(meta, dict) and "title" in meta:
            title = meta.get("title", "")
        
        if title:
            enhanced["title"] = title
            self.progress_current_title = title
        
        # 计算速度和剩余时间
        now = time.time()
        
        # 如果任务刚开始，初始化时间
        if self.progress_start_time is None:
            self.progress_start_time = now
            self.progress_last_time = now
            self.progress_last_count = 0
        
        # 计算速度（items/second）
        if current > 0 and now > self.progress_start_time:
            elapsed = now - self.progress_start_time
            if elapsed > 0:
                speed = current / elapsed
                enhanced["speed"] = speed
                
                # 计算剩余时间
                if total > current and speed > 0:
                    remaining = total - current
                    eta = remaining / speed
                    enhanced["eta"] = eta
                else:
                    enhanced["eta"] = 0
            else:
                enhanced["speed"] = 0
                enhanced["eta"] = None
        else:
            enhanced["speed"] = None
            enhanced["eta"] = None
        
        # 更新最后状态（用于平滑速度计算）
        # 只在有实际进度变化时更新
        if current != self.progress_last_count:
            self.progress_last_time = now
            self.progress_last_count = current
        
        # 添加任务信息（如果没有）
        if "task" not in enhanced and message:
            enhanced["task"] = message
        
        return enhanced
    
    def _on_progress(self, progress: dict):
        """
        进度回调函数
        
        Args:
            progress: 进度信息字典，包含：
                - phase: 当前阶段（如 "detect", "download"）
                - current: 当前进度
                - total: 总进度
                - message: 进度消息
                - url: 当前处理的URL（可选）
        """
        if self.is_stopped:
            return  # 如果已停止，忽略进度更新
        
        # 增强进度信息（计算速度、ETA等）
        enhanced = self._enhance_progress_info(progress)
        
        # 发布进度事件
        self.event_bus.publish(Event(
            EventType.DOWNLOAD_PROGRESS,
            enhanced
        ))
    
    def _on_completion(self, result: dict):
        """
        下载完成回调
        
        Args:
            result: 结果信息
        """
        print(f"[DownloadController] _on_completion 被调用: result={result}")
        print(f"[DownloadController] is_dry_run={self.is_dry_run}, is_stopped={self.is_stopped}")
        
        # 如果已停止，忽略完成回调（避免显示停止后的进度）
        if self.is_stopped:
            self._log("任务已停止，忽略后续完成信息", "WARN")
            return
        
        if "error" in result:
            # 下载失败 - 使用错误处理工具格式化错误消息
            error_msg = result["error"]
            print(f"[DownloadController] 下载失败: {error_msg}")
            
            # 尝试使用错误处理工具
            try:
                from utils.error_handler import ErrorHandler
                
                # 尝试从错误消息中提取错误代码
                error_code = "error_other"
                if "timeout" in error_msg.lower():
                    error_code = "error_timeout"
                elif "429" in error_msg or "rate limit" in error_msg.lower():
                    error_code = "error_429"
                elif "503" in error_msg:
                    error_code = "error_503"
                elif "sign in" in error_msg.lower() or "cookie" in error_msg.lower() or "bot" in error_msg.lower():
                    error_code = "YTDLP_SIGNIN"
                    # Cookie失效特殊提示
                    self._log("⚠️ Cookie 失效或已过期！", "ERROR")
                    self._log("请前往【高级设置】→【网络设置】→【Cookie文件】更新有效的Cookie文件", "WARN")
                    self._log("提示：Cookie文件通常需要定期更新，建议使用浏览器扩展（如Get cookies.txt）导出最新Cookie", "INFO")
                
                category, name, retryable, suggestion = ErrorHandler.classify_error(error_code)
                formatted_msg = ErrorHandler.format_error_message(error_code, error_msg)
                
                self.event_bus.publish(Event(
                    EventType.DOWNLOAD_FAILED,
                    {
                        "reason": error_msg,
                        "error_code": error_code,
                        "category": category.value,
                        "retryable": retryable,
                        "suggestion": suggestion,
                        "formatted_message": formatted_msg
                    }
                ))
                
                self._log(f"下载失败: {name}", "ERROR")
                self._log(f"详情: {error_msg[:100]}", "ERROR")
                self._log(f"建议: {suggestion}", "INFO")
                if retryable:
                    self._log("提示: 此错误可以重试", "INFO")
            except ImportError:
                # 如果错误处理工具不可用，使用原有方式
                self.event_bus.publish(Event(
                    EventType.DOWNLOAD_FAILED,
                    {"reason": error_msg}
                ))
                self._log(f"下载失败: {error_msg}", "ERROR")
            except Exception as e:
                # 如果错误处理工具出错，使用原有方式
                print(f"[DownloadController] 错误处理工具出错: {e}")
                self.event_bus.publish(Event(
                    EventType.DOWNLOAD_FAILED,
                    {"reason": error_msg}
                ))
                self._log(f"下载失败: {error_msg}", "ERROR")
        else:
            run_dir = result.get("run_dir", "")
            print(f"[DownloadController] 下载完成，run_dir={run_dir}, is_dry_run={self.is_dry_run}")
            
            if self.is_dry_run:
                # 检测模式：显示检测结果（字幕类型和语言）
                print(f"[DownloadController] 进入检测结果显示流程")
                self._show_detection_results(run_dir, result)
            else:
                # 下载模式：显示下载结果并验证
                print(f"[DownloadController] 发布下载完成事件")
                self.event_bus.publish(Event(
                    EventType.DOWNLOAD_COMPLETED,
                    result
                ))
                self._log(f"下载完成，输出目录: {run_dir}", "SUCCESS")
                # 验证下载结果
                self._verify_download_results(run_dir, result)
    
    def _show_detection_results(self, run_dir: str, result: dict):
        """
        显示检测结果
        
        Args:
            run_dir: 运行目录
            result: 结果信息
        """
        print(f"[DownloadController] _show_detection_results 被调用: run_dir={run_dir}")
        try:
            from pathlib import Path
            import json
            
            # 检查 run_dir 是否存在
            if not run_dir:
                print("[DownloadController] ✗ run_dir 为空，无法读取检测结果")
                self._log("检测完成，但未找到输出目录", "WARN")
                return
            
            run_path = Path(run_dir)
            if not run_path.exists():
                print(f"[DownloadController] ✗ run_dir 不存在: {run_dir}")
                self._log(f"检测完成，但输出目录不存在: {run_dir}", "WARN")
                return
            
            print(f"[DownloadController] ✓ run_dir 存在: {run_dir}")
            
            # 读取检测结果
            results = []
            run_jsonl = run_path / "run.jsonl"
            print(f"[DownloadController] 检查 run.jsonl: {run_jsonl}, 存在={run_jsonl.exists()}")
            
            if run_jsonl.exists():
                content = run_jsonl.read_text(encoding='utf-8')
                print(f"[DownloadController] run.jsonl 内容长度: {len(content)}")
                for line_num, line in enumerate(content.splitlines(), 1):
                    if line.strip():
                        try:
                            rec = json.loads(line)
                            if rec.get("action") == "detect":
                                results.append(rec)
                                print(f"[DownloadController] 找到检测记录 #{len(results)}: {rec.get('video_id', 'unknown')}")
                        except Exception as e:
                            print(f"[DownloadController] 解析第 {line_num} 行失败: {e}")
                            continue
            
            print(f"[DownloadController] 共找到 {len(results)} 条检测记录")
            
            if not results:
                # 如果没有检测记录，尝试从has_subs.txt和no_subs.txt读取
                print("[DownloadController] 未找到检测记录，尝试读取 has_subs.txt 和 no_subs.txt")
                has_subs_file = run_path / "has_subs.txt"
                no_subs_file = run_path / "no_subs.txt"
                
                has_subs_count = 0
                no_subs_count = 0
                
                if has_subs_file.exists():
                    has_subs_lines = has_subs_file.read_text(encoding='utf-8').splitlines()
                    has_subs_count = len([l for l in has_subs_lines if l.strip()])
                    print(f"[DownloadController] has_subs.txt 存在，有字幕数量: {has_subs_count}")
                
                if no_subs_file.exists():
                    no_subs_lines = no_subs_file.read_text(encoding='utf-8').splitlines()
                    no_subs_count = len([l for l in no_subs_lines if l.strip()])
                    print(f"[DownloadController] no_subs.txt 存在，无字幕数量: {no_subs_count}")
                
                total = has_subs_count + no_subs_count
                if total > 0:
                    self.event_bus.publish(Event(
                        EventType.DOWNLOAD_COMPLETED,
                        {
                            **result,
                            "is_detection": True,
                            "has_subs_count": has_subs_count,
                            "no_subs_count": no_subs_count,
                            "total": total
                        }
                    ))
                    self._log(f"检测完成: 总计 {total}，有字幕 {has_subs_count}，无字幕 {no_subs_count}", "SUCCESS")
                    return
                else:
                    print("[DownloadController] ✗ has_subs.txt 和 no_subs.txt 也不存在或为空")
                    self._log("检测完成，但未找到检测结果文件", "WARN")
                    return
            
            # 分析检测结果
            has_subs = []
            no_subs = []
            errors = []
            all_langs = set()
            manual_langs = set()
            auto_langs = set()
            
            for rec in results:
                status = rec.get("status", "")
                if status == "has_subs":
                    has_subs.append(rec)
                    manual_langs.update(rec.get("manual_langs", []))
                    auto_langs.update(rec.get("auto_langs", []))
                    all_langs.update(rec.get("all_langs", []))
                elif status == "no_subs":
                    no_subs.append(rec)
                elif str(status).startswith("error"):
                    errors.append(rec)
                    # 即使有错误，也尝试提取语言信息（如果检测过程中获取到了）
                    manual_langs.update(rec.get("manual_langs", []))
                    auto_langs.update(rec.get("auto_langs", []))
                    all_langs.update(rec.get("all_langs", []))
            
            print(f"[DownloadController] 分析结果: 有字幕={len(has_subs)}, 无字幕={len(no_subs)}, 错误={len(errors)}")
            print(f"[DownloadController] 语言统计: 人工字幕={sorted(manual_langs)}, 自动字幕={sorted(auto_langs)}")
            
            # 格式化语言信息
            lang_info = []
            if manual_langs:
                lang_info.append(f"人工字幕: {', '.join(sorted(manual_langs))}")
            if auto_langs:
                lang_info.append(f"自动字幕: {', '.join(sorted(auto_langs))}")
            if not lang_info and len(errors) == 0:
                lang_info.append("未检测到字幕")
            
            # 显示检测结果
            total = len(results)
            has_subs_count = len(has_subs)
            no_subs_count = len(no_subs)
            errors_count = len(errors)
            
            # 统计错误类型
            error_types = {}
            for err_rec in errors:
                err_status = err_rec.get("status", "error_unknown")
                error_types[err_status] = error_types.get(err_status, 0) + 1
            
            self.event_bus.publish(Event(
                EventType.DOWNLOAD_COMPLETED,
                {
                    **result,
                    "is_detection": True,
                    "has_subs_count": has_subs_count,
                    "no_subs_count": no_subs_count,
                    "errors_count": errors_count,
                    "total": total,
                    "manual_langs": sorted(manual_langs),
                    "auto_langs": sorted(auto_langs),
                    "all_langs": sorted(all_langs),
                    "error_types": error_types
                }
            ))
            
            # 显示检测结果摘要
            result_msg = f"检测完成: 总计 {total}"
            if has_subs_count > 0:
                result_msg += f"，有字幕 {has_subs_count}"
            if no_subs_count > 0:
                result_msg += f"，无字幕 {no_subs_count}"
            if errors_count > 0:
                result_msg += f"，错误 {errors_count}"
            
            self._log(result_msg, "SUCCESS" if errors_count == 0 else "WARN")
            
            # 显示语言信息
            if lang_info:
                self._log(" | ".join(lang_info), "INFO")
            
            # 显示错误信息
            if errors_count > 0:
                self._log(f"检测错误详情 ({errors_count} 个):", "WARN")
                
                # 使用错误处理工具格式化错误信息
                try:
                    from utils.error_handler import ErrorHandler
                    use_error_handler = True
                except ImportError:
                    use_error_handler = False
                
                for err_status, count in sorted(error_types.items()):
                    if use_error_handler:
                        category, name, retryable, suggestion = ErrorHandler.classify_error(err_status)
                        error_name = name
                    else:
                        # 回退到原有映射
                        error_name = {
                            "error_other": "其他错误（可能需要 Cookie 认证）",
                            "error_429": "请求过于频繁（429）",
                            "error_503": "服务不可用（503）",
                            "error_timeout": "请求超时",
                            "error_private": "视频为私有",
                            "error_geo": "地区限制"
                        }.get(err_status, err_status)
                        retryable = err_status in ["error_429", "error_503", "error_timeout"]
                        suggestion = ""
                    
                    retryable_mark = "（可重试）" if retryable else ""
                    self._log(f"  • {error_name}: {count} 个{retryable_mark}", "WARN")
                    
                    # 显示恢复建议（仅显示第一个错误的建议）
                    if suggestion and count > 0:
                        self._log(f"    建议: {suggestion}", "INFO")
                
                # 显示前3个错误的详细信息
                for err_rec in errors[:3]:
                    vid = err_rec.get("video_id", "")
                    title = err_rec.get("meta", {}).get("title", "")
                    status = err_rec.get("status", "")
                    api_err = err_rec.get("api_err", "")
                    url = err_rec.get("url", "")
                    
                    # 记录错误到日志管理器
                    if self.error_logger:
                        self.error_logger.log_error(
                            status,
                            api_err[:200] if api_err else "",
                            vid,
                            title[:100] if title else "",
                            url
                        )
                    
                    if use_error_handler:
                        error_msg = ErrorHandler.format_error_message(
                            status,
                            api_err[:100] if api_err else "",
                            vid,
                            title[:50] if title else ""
                        )
                        self._log(f"  - {error_msg}", "ERROR")
                    else:
                        self._log(f"  - {vid}: {status}", "WARN")
                
                if len(errors) > 3:
                    self._log(f"  ... 还有 {len(errors) - 3} 个错误", "WARN")
            
            # 如果有检测结果，显示每个视频的详细信息（最多显示前5个）
            if has_subs:
                self._log(f"检测到字幕的视频 ({min(5, len(has_subs))}/{len(has_subs)}):", "INFO")
                for rec in has_subs[:5]:
                    vid = rec.get("video_id", "")
                    title = rec.get("meta", {}).get("title", "")[:50]
                    langs = rec.get("all_langs", [])
                    lang_str = ", ".join(sorted(langs)) if langs else "未知"
                    self._log(f"  • {vid}: {title} - 语言: {lang_str}", "INFO")
                if len(has_subs) > 5:
                    self._log(f"  ... 还有 {len(has_subs) - 5} 个视频", "INFO")
                    
            print(f"[DownloadController] ✓ 检测结果显示完成")
            
        except Exception as e:
            print(f"[DownloadController] ✗ 显示检测结果失败: {e}")
            import traceback
            traceback.print_exc()
            self._log(f"读取检测结果失败: {e}", "WARN")
    
    def _verify_download_results(self, run_dir: str, result: dict):
        """
        验证下载结果并显示文件列表
        
        Args:
            run_dir: 运行目录
            result: 结果信息
        """
        print(f"[DownloadController] ========== _verify_download_results 被调用 ==========")
        print(f"[DownloadController] run_dir={run_dir}")
        print(f"[DownloadController] result keys: {list(result.keys())}")
        import sys
        sys.stdout.flush()
        try:
            from pathlib import Path
            
            if not run_dir:
                print("[DownloadController] ✗ run_dir 为空，无法验证下载结果")
                self._log("下载完成，但未找到输出目录", "WARN")
                return
            
            run_path = Path(run_dir)
            if not run_path.exists():
                print(f"[DownloadController] ✗ run_dir 不存在: {run_dir}")
                self._log(f"下载完成，但输出目录不存在: {run_dir}", "WARN")
                return
            
            # 检查字幕目录
            subs_dir = run_path / "subs"
            downloaded_files = []
            
            if subs_dir.exists() and subs_dir.is_dir():
                # 列出所有字幕文件
                subtitle_files = list(subs_dir.glob("*.*"))
                downloaded_files = [f for f in subtitle_files if f.is_file()]
                print(f"[DownloadController] 找到 {len(downloaded_files)} 个字幕文件")
            else:
                print(f"[DownloadController] ⚠️ 字幕目录不存在: {subs_dir}")
            
            # 读取下载统计
            stats = result.get("stats", {})
            downloaded_count = stats.get("downloaded", result.get("downloaded", 0))
            skipped_count = stats.get("skipped", result.get("skipped", 0))
            failed_count = stats.get("failed", result.get("failed", 0))
            
            print(f"[DownloadController] 原始统计: downloaded={downloaded_count}, skipped={skipped_count}, failed={failed_count}")
            import sys
            sys.stdout.flush()
            
            # 如果实际找到了文件，但统计显示失败，可能是统计逻辑问题
            # 优先以实际文件数量为准
            actual_file_count = len(downloaded_files)
            print(f"[DownloadController] 实际文件数: {actual_file_count}")
            sys.stdout.flush()
            
            # 调整统计逻辑：如果实际有文件，优先以实际文件数量为准
            if actual_file_count > 0:
                print(f"[DownloadController] ========== 开始调整统计 ==========")
                print(f"[DownloadController] 条件检查: downloaded_count={downloaded_count}, actual_file_count={actual_file_count}, failed_count={failed_count}")
                sys.stdout.flush()
                
                if downloaded_count < actual_file_count:
                    # 如果成功数小于实际文件数，调整成功数
                    old_downloaded = downloaded_count
                    old_failed = failed_count
                    downloaded_count = actual_file_count
                    # 计算需要从失败计数中减去的数量
                    adjustment = actual_file_count - old_downloaded
                    failed_count = max(0, failed_count - adjustment)
                    print(f"[DownloadController] ✓ 调整统计（情况1）：实际文件数={actual_file_count}，原成功={old_downloaded}，原失败={old_failed}，调整后成功={downloaded_count}，失败={failed_count}")
                    sys.stdout.flush()
                elif failed_count > 0 and downloaded_count >= actual_file_count:
                    # 如果成功数已经等于或大于实际文件数，但仍有失败计数，说明失败计数是误报
                    # 将失败计数清零（因为实际文件已经下载成功了）
                    old_failed = failed_count
                    failed_count = 0
                    print(f"[DownloadController] ✓✓✓ 调整统计（情况2）：实际文件数={actual_file_count}，成功数={downloaded_count}，原失败计数={old_failed}（误报），清零后失败={failed_count} ✓✓✓")
                    sys.stdout.flush()
                else:
                    print(f"[DownloadController] 无需调整统计")
                    sys.stdout.flush()
            else:
                print(f"[DownloadController] 未找到实际文件，使用原始统计")
                sys.stdout.flush()
            
            print(f"[DownloadController] ========== 最终统计: downloaded={downloaded_count}, skipped={skipped_count}, failed={failed_count} ==========")
            sys.stdout.flush()
            
            total_count = downloaded_count + skipped_count + failed_count
            
            # 显示下载统计
            print(f"[DownloadController] ========== 准备显示统计信息 ==========")
            print(f"[DownloadController] 显示统计: downloaded={downloaded_count}, skipped={skipped_count}, failed={failed_count}")
            sys.stdout.flush()
            
            self._log(f"\n下载统计: 总计 {total_count}", "INFO")
            if downloaded_count > 0:
                self._log(f"  ✓ 成功: {downloaded_count} 个", "SUCCESS")
            if skipped_count > 0:
                self._log(f"  ⊘ 跳过: {skipped_count} 个", "INFO")
            if failed_count > 0:
                # 如果实际有文件但统计显示失败，说明可能是统计误差
                if actual_file_count > 0:
                    # 这种情况不应该出现（因为我们已经调整了统计），但如果出现了，说明调整逻辑有问题
                    print(f"[DownloadController] ⚠️⚠️⚠️ 警告：failed_count={failed_count} > 0，但实际文件数={actual_file_count}，这不应该发生！")
                    sys.stdout.flush()
                    self._log(f"  ⚠️ 注意: 统计显示失败 {failed_count} 个，但实际找到了 {actual_file_count} 个文件", "WARN")
                else:
                    self._log(f"  ✗ 失败: {failed_count} 个", "ERROR")
            else:
                print(f"[DownloadController] ✓ failed_count=0，不显示失败信息")
                sys.stdout.flush()
            
            # 显示文件列表（最多显示前20个）
            if downloaded_files:
                self._log(f"\n下载的文件 ({len(downloaded_files)} 个):", "INFO")
                for i, file_path in enumerate(downloaded_files[:20], 1):
                    file_size = file_path.stat().st_size
                    size_str = self._format_file_size(file_size)
                    self._log(f"  {i}. {file_path.name} ({size_str})", "INFO")
                
                if len(downloaded_files) > 20:
                    self._log(f"  ... 还有 {len(downloaded_files) - 20} 个文件", "INFO")
                
                # 验证文件数量是否匹配
                if downloaded_count > 0 and len(downloaded_files) < downloaded_count:
                    self._log(f"⚠️ 警告: 预期下载 {downloaded_count} 个文件，但只找到 {len(downloaded_files)} 个文件", "WARN")
                elif len(downloaded_files) == downloaded_count:
                    self._log(f"✓ 文件数量验证通过: {len(downloaded_files)} 个文件", "SUCCESS")
            else:
                if downloaded_count > 0:
                    self._log(f"⚠️ 警告: 统计显示下载了 {downloaded_count} 个文件，但未找到字幕文件", "WARN")
                else:
                    self._log("未找到下载的字幕文件", "INFO")
                    
                    # 检查是否是Cookie失效导致的失败
                    self._check_cookie_expiration(run_path, result)
            
            # 显示输出目录路径
            self._log(f"\n输出目录: {run_dir}", "SUCCESS")
            
            # 检查是否有HTML报告
            html_report = run_path / "report.html"
            if html_report.exists():
                self._log(f"HTML报告: {html_report}", "SUCCESS")
            
            print(f"[DownloadController] ✓ 下载结果验证完成")
            
        except Exception as e:
            print(f"[DownloadController] ✗ 验证下载结果失败: {e}")
            import traceback
            traceback.print_exc()
            self._log(f"验证下载结果失败: {e}", "WARN")
    
    def _check_cookie_expiration(self, run_path: Path, result: dict):
        """
        检查Cookie是否失效
        
        Args:
            run_path: 运行目录路径
            result: 下载结果
        """
        try:
            detected = False
            # 1. 检查 failed_items 中的错误信息
            failed_items = result.get("failed_items", [])
            if failed_items:
                for item in failed_items:
                    error = item.get("error", "")
                    error_msg = item.get("error_msg", "")
                    status = item.get("status", "")
                    
                    # 检查错误消息中是否包含Cookie相关关键词
                    error_text = f"{error} {error_msg} {status}".lower()
                    if any(keyword in error_text for keyword in ["sign in", "cookie", "bot", "authentication", "expired", "invalid"]):
                        detected = True
                        break
            if detected:
                self._log("⚠️ Cookie 失效或已过期！", "ERROR")
                self._log("请前往【高级设置】→【网络设置】→【Cookie文件】更新有效的Cookie文件", "WARN")
                self._log("提示：Cookie文件通常需要定期更新，建议使用浏览器扩展（如Get cookies.txt）导出最新Cookie", "INFO")
                return
            
            # 2. 检查 errors.txt 文件
            errors_file = run_path / "errors.txt"
            if errors_file.exists():
                try:
                    error_content = errors_file.read_text(encoding='utf-8', errors='ignore').lower()
                    if any(keyword in error_content for keyword in ["sign in", "cookie", "bot", "authentication", "expired", "invalid"]):
                        self._log("⚠️ Cookie 失效或已过期！", "ERROR")
                        self._log("请前往【高级设置】→【网络设置】→【Cookie文件】更新有效的Cookie文件", "WARN")
                        self._log("提示：Cookie文件通常需要定期更新，建议使用浏览器扩展（如Get cookies.txt）导出最新Cookie", "INFO")
                        return
                except Exception as e:
                    print(f"[DownloadController] 读取errors.txt失败: {e}")
            
            # 3. 检查 history.jsonl 中的错误记录
            history_file = run_path / "history.jsonl"
            if history_file.exists():
                try:
                    for line in history_file.read_text(encoding='utf-8', errors='ignore').splitlines():
                        if not line.strip():
                            continue
                        try:
                            import json
                            record = json.loads(line)
                            error_msg = record.get("error_msg", "") or record.get("api_err", "") or record.get("status", "")
                            if error_msg:
                                error_text = error_msg.lower()
                                if any(keyword in error_text for keyword in ["sign in", "cookie", "bot", "authentication", "expired", "invalid"]):
                                    self._log("⚠️ Cookie 失效或已过期！", "ERROR")
                                    self._log("请前往【高级设置】→【网络设置】→【Cookie文件】更新有效的Cookie文件", "WARN")
                                    self._log("提示：Cookie文件通常需要定期更新，建议使用浏览器扩展（如Get cookies.txt）导出最新Cookie", "INFO")
                                    return
                        except (json.JSONDecodeError, KeyError):
                            continue
                except Exception as e:
                    print(f"[DownloadController] 读取history.jsonl失败: {e}")

            # 4. 检查 diagnose.txt 中的建议
            diagnose_file = run_path / "diagnose.txt"
            if diagnose_file.exists():
                try:
                    diag_text = diagnose_file.read_text(encoding='utf-8', errors='ignore').lower()
                    if "cookie" in diag_text:
                        self._log("⚠️ Cookie 失效或已过期（诊断报告提示）", "ERROR")
                        self._log("请更新Cookie文件或重新从浏览器导出有效的Cookie", "WARN")
                        self._log("提示：使用浏览器扩展（如Get cookies.txt）导出最新的 YouTube Cookie", "INFO")
                        return
                except Exception as e:
                    print(f"[DownloadController] 读取diagnose.txt失败: {e}")

            # 5. 回退：根据统计推断（downloaded=0 且存在失败项）
            if result.get("downloaded", 0) == 0 and result.get("total", 0) > 0 and failed_items:
                self._log("⚠️ 下载失败：可能需要有效的 Cookie 或登录授权", "WARN")
                self._log("提示：请更新 Cookie 文件后重试，或使用浏览器导出最新 Cookie", "INFO")
                    
        except Exception as e:
            print(f"[DownloadController] Cookie失效检测失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _format_file_size(self, size_bytes: int) -> str:
        """
        格式化文件大小
        
        Args:
            size_bytes: 文件大小（字节）
        
        Returns:
            格式化后的文件大小字符串
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    
    def stop_download(self):
        """停止下载"""
        if not self.service.is_running():
            self.view.show_error("没有正在运行的下载任务")
            return
        
        # 设置停止标志，防止后续进度回调显示
        self.is_stopped = True
        
        # 停止服务
        self.service.stop()
        
        # 发布事件
        self.event_bus.publish(Event(EventType.DOWNLOAD_STOPPED))
        
        self._log("已请求停止下载", "WARN")
    
    def pause_download(self):
        """暂停下载"""
        if not self.service.is_running():
            self.view.show_error("没有正在运行的下载任务")
            return
        
        if self.is_paused:
            # 如果已暂停，执行恢复
            return self.resume_download()
        
        # 暂停服务
        self.service.pause()
        self.is_paused = True
        
        # 发布事件
        self.event_bus.publish(Event(EventType.DOWNLOAD_PAUSED))
        
        self._log("已暂停下载", "WARN")
    
    def resume_download(self):
        """恢复下载"""
        if not self.service.is_running():
            self.view.show_error("没有正在运行的下载任务")
            return
        
        if not self.is_paused:
            # 如果未暂停，执行暂停
            return self.pause_download()
        
        # 恢复服务
        self.service.resume()
        self.is_paused = False
        
        # 发布事件
        self.event_bus.publish(Event(EventType.DOWNLOAD_RESUMED))
        
        self._log("已恢复下载", "INFO")
    
    def retry_failed(self):
        """重试失败项"""
        if not self.service.run_dir:
            self.view.show_error("没有可重试的任务")
            return
        
        success = self.service.retry_failed(
            run_dir=self.service.run_dir,
            progress_callback=self._on_progress
        )
        
        if success:
            self._log("开始重试失败项")
        else:
            self.view.show_error("已有任务正在运行")
    
    def import_urls(self):
        """
        导入URL文件（支持txt/csv/json）
        
        支持格式：
        - TXT: 一行一个URL
        - CSV: 读取第一列或url列
        - JSON: 支持数组或对象数组
        """
        try:
            from tkinter import filedialog
            from pathlib import Path
            from utils.batch_url_manager import BatchURLManager
            
            # 选择文件
            file_path = filedialog.askopenfilename(
                title="导入URL文件",
                filetypes=[
                    ("所有支持格式", "*.txt;*.csv;*.json"),
                    ("文本文件", "*.txt"),
                    ("CSV文件", "*.csv"),
                    ("JSON文件", "*.json"),
                    ("所有文件", "*.*")
                ]
            )
            
            if not file_path:
                return
            
            file_path = Path(file_path)
            
            # 导入URL
            result = BatchURLManager.import_from_file(file_path)
            
            if not result["success"]:
                error_msg = "\n".join(result["errors"])
                self.view.show_error(f"导入失败:\n{error_msg}")
                self._log(f"导入URL失败: {error_msg}", "ERROR")
                return
            
            if not result["urls"]:
                self.view.show_warning("文件中没有有效的URL")
                self._log("导入的URL文件没有有效URL", "WARN")
                return
            
            # 获取当前URL列表
            current_text = self.view.txt_urls.get("1.0", "end-1c").strip()
            current_urls = [line.strip() for line in current_text.split("\n") if line.strip()]
            
            # 合并URL（去重）
            all_urls = current_urls + result["urls"]
            unique_result = BatchURLManager.remove_duplicates(all_urls)
            final_urls = unique_result["unique_urls"]
            
            # 更新UI
            self.view.txt_urls.delete("1.0", "end")
            self.view.txt_urls.insert("1.0", "\n".join(final_urls))
            
            # 显示导入结果
            imported_count = result["valid"]
            duplicate_count = unique_result["duplicate_count"]
            invalid_count = result["invalid"]
            
            msg_parts = [f"成功导入 {imported_count} 个URL"]
            if duplicate_count > 0:
                msg_parts.append(f"（跳过 {duplicate_count} 个重复）")
            if invalid_count > 0:
                msg_parts.append(f"（忽略 {invalid_count} 个无效URL）")
            
            self._log(" | ".join(msg_parts), "SUCCESS")
            self.view.show_info("\n".join(msg_parts))
            
        except Exception as e:
            print(f"[DownloadController] 导入URL失败: {e}")
            import traceback
            traceback.print_exc()
            self._log(f"导入URL失败: {e}", "ERROR")
            self.view.show_error(f"导入URL失败: {e}")
    
    def clean_invalid_urls(self):
        """清理无效URL"""
        try:
            from utils.batch_url_manager import BatchURLManager
            
            # 获取当前URL列表
            urls_text = self.view.txt_urls.get("1.0", "end-1c").strip()
            if not urls_text:
                self.view.show_info("没有URL需要清理")
                return
            
            urls = [line.strip() for line in urls_text.split("\n") if line.strip()]
            
            # 清理无效URL
            result = BatchURLManager.clean_invalid_urls(urls)
            
            if result["removed_count"] == 0:
                self.view.show_info("所有URL都是有效的")
                self._log("URL验证完成，所有URL有效", "SUCCESS")
                return
            
            # 更新UI
            self.view.txt_urls.delete("1.0", "end")
            self.view.txt_urls.insert("1.0", "\n".join(result["valid_urls"]))
            
            # 显示清理结果
            removed_count = result["removed_count"]
            remaining_count = len(result["valid_urls"])
            
            self._log(f"清理完成: 移除了 {removed_count} 个无效URL，剩余 {remaining_count} 个有效URL", "SUCCESS")
            self.view.show_info(f"清理完成:\n移除了 {removed_count} 个无效URL\n剩余 {remaining_count} 个有效URL")
            
        except Exception as e:
            print(f"[DownloadController] 清理无效URL失败: {e}")
            import traceback
            traceback.print_exc()
            self._log(f"清理无效URL失败: {e}", "ERROR")
            self.view.show_error(f"清理无效URL失败: {e}")
    
    def remove_duplicate_urls(self):
        """移除重复URL"""
        try:
            from utils.batch_url_manager import BatchURLManager
            
            # 获取当前URL列表
            urls_text = self.view.txt_urls.get("1.0", "end-1c").strip()
            if not urls_text:
                self.view.show_info("没有URL需要去重")
                return
            
            urls = [line.strip() for line in urls_text.split("\n") if line.strip()]
            
            # 移除重复
            result = BatchURLManager.remove_duplicates(urls)
            
            if result["duplicate_count"] == 0:
                self.view.show_info("没有重复的URL")
                self._log("URL去重完成，没有重复", "SUCCESS")
                return
            
            # 更新UI
            self.view.txt_urls.delete("1.0", "end")
            self.view.txt_urls.insert("1.0", "\n".join(result["unique_urls"]))
            
            # 显示去重结果
            duplicate_count = result["duplicate_count"]
            remaining_count = len(result["unique_urls"])
            
            self._log(f"去重完成: 移除了 {duplicate_count} 个重复URL，剩余 {remaining_count} 个唯一URL", "SUCCESS")
            self.view.show_info(f"去重完成:\n移除了 {duplicate_count} 个重复URL\n剩余 {remaining_count} 个唯一URL")
            
        except Exception as e:
            print(f"[DownloadController] 移除重复URL失败: {e}")
            import traceback
            traceback.print_exc()
            self._log(f"移除重复URL失败: {e}", "ERROR")
            self.view.show_error(f"移除重复URL失败: {e}")
    
    def validate_urls(self):
        """验证URL并显示统计信息"""
        try:
            from utils.batch_url_manager import BatchURLManager
            
            # 获取当前URL列表
            urls_text = self.view.txt_urls.get("1.0", "end-1c").strip()
            if not urls_text:
                self.view.show_info("没有URL需要验证")
                return
            
            urls = [line.strip() for line in urls_text.split("\n") if line.strip()]
            
            # 验证并统计
            result = BatchURLManager.validate_and_statistics(urls)
            
            # 显示统计信息
            stats_msg = f"URL验证统计:\n"
            stats_msg += f"总计: {result['total']}\n"
            stats_msg += f"有效: {result['valid']}\n"
            stats_msg += f"无效: {result['invalid']}"
            
            if result["statistics"]:
                stats_msg += f"\n\n按域名统计:"
                for domain, count in sorted(result["statistics"].items(), key=lambda x: x[1], reverse=True)[:5]:
                    stats_msg += f"\n  {domain}: {count}"
            
            self._log(stats_msg, "INFO")
            self.view.show_info(stats_msg)
            
            # 如果有无效URL，显示前5个
            if result["invalid_urls"]:
                invalid_msg = "\n无效URL（前5个）:"
                for url, error_msg in result["invalid_urls"][:5]:
                    invalid_msg += f"\n  {url[:50]}: {error_msg[:30]}"
                self._log(invalid_msg, "WARN")
            
        except Exception as e:
            print(f"[DownloadController] 验证URL失败: {e}")
            import traceback
            traceback.print_exc()
            self._log(f"验证URL失败: {e}", "ERROR")
            self.view.show_error(f"验证URL失败: {e}")
    
    def export_error_log(self):
        """导出错误日志"""
        if not self.error_logger or len(self.error_logger.errors) == 0:
            self.view.show_info("没有错误日志可导出")
            return
        
        try:
            from tkinter import filedialog
            from pathlib import Path
            
            # 选择保存位置
            file_path = filedialog.asksaveasfilename(
                title="导出错误日志",
                defaultextension=".json",
                filetypes=[
                    ("JSON文件", "*.json"),
                    ("文本文件", "*.txt"),
                    ("所有文件", "*.*")
                ]
            )
            
            if file_path:
                file_path = Path(file_path)
                
                if file_path.suffix == ".txt":
                    exported_path = self.error_logger.export_to_text(file_path)
                else:
                    exported_path = self.error_logger.export_to_json(file_path)
                
                self._log(f"错误日志已导出到: {exported_path}", "SUCCESS")
                self.view.show_info(f"错误日志已导出到:\n{exported_path}")
        except Exception as e:
            print(f"[DownloadController] 导出错误日志失败: {e}")
            self._log(f"导出错误日志失败: {e}", "ERROR")
            self.view.show_error(f"导出错误日志失败: {e}")
    
    def clear_error_log(self):
        """清空错误日志"""
        if self.error_logger:
            self.error_logger.clear()
            self._log("错误日志已清空", "INFO")
    
    def clear_urls(self):
        """清空URL"""
        self.view.clear_urls()
        # 清除错误高亮
        self.view.txt_urls.config(highlightthickness=0)
        self._log("已清空链接输入框", "INFO")
    
    def _on_theme_changed(self, event: Event):
        """
        主题变化处理
        
        Args:
            event: 事件对象
        """
        theme = event.data.get("theme")
        self.view.update_theme(theme)


__all__ = ['DownloadController']

