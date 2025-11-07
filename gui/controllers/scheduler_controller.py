# -*- coding: utf-8 -*-
"""
调度器控制器 - 管理调度任务
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from gui.controllers.base_controller import BaseController
from events.event_bus import EventType, Event
from services.scheduler_service import SchedulerService
from gui_models import SchedulerJobDisplay, SchedulerJobForm

if TYPE_CHECKING:
    from gui.views.scheduler_panel import SchedulerPanel


class SchedulerController(BaseController):
    """
    调度器控制器
    
    职责：
    1. 管理调度任务（增删改查）
    2. 启动/停止调度器
    3. 执行任务
    """
    
    def __init__(self, view: SchedulerPanel, config: dict):
        """
        初始化
        
        Args:
            view: 调度器面板视图
            config: 全局配置
        """
        self.view = view
        self.config = config
        self.service = SchedulerService(config)
        self.main_controller = None  # 将在主控制器中设置
        super().__init__()
        
        # 状态跟踪
        self._last_tick_time = None  # 上次tick时间戳
        self._status_update_job = None  # 状态更新定时器
        
        # 设置执行器（必须在初始化后设置）
        if self.service.is_available() and self.service.scheduler_engine:
            self.service.scheduler_engine.set_executor(self._scheduler_executor)
        
        # 绑定视图按钮事件
        self._bind_view_events()
        
        # 初始化后立即刷新任务列表并启动状态更新
        if self.service.is_available():
            self.refresh_jobs()
            self._start_status_updates()
    
    def _bind_view_events(self):
        """绑定视图事件"""
        # 任务管理按钮
        if hasattr(self.view, 'btn_add'):
            self.view.btn_add.config(command=self.add_job)
        
        if hasattr(self.view, 'btn_edit'):
            self.view.btn_edit.config(command=self.edit_job)
        
        if hasattr(self.view, 'btn_delete'):
            self.view.btn_delete.config(command=self.delete_job)
        
        if hasattr(self.view, 'btn_toggle'):
            self.view.btn_toggle.config(command=self.toggle_job)
        
        if hasattr(self.view, 'btn_run_once'):
            self.view.btn_run_once.config(command=self.run_job_once)
        
        # 调度器控制按钮
        if hasattr(self.view, 'btn_start'):
            self.view.btn_start.config(command=self.start_scheduler)
        
        if hasattr(self.view, 'btn_stop'):
            self.view.btn_stop.config(command=self.stop_scheduler)
        
        if hasattr(self.view, 'btn_refresh'):
            self.view.btn_refresh.config(command=self.refresh_jobs)
    
    def _setup_event_listeners(self):
        """设置事件监听"""
        # 监听任务事件，自动刷新
        self.event_bus.subscribe(EventType.JOB_ADDED, lambda e: self.refresh_jobs())
        self.event_bus.subscribe(EventType.JOB_UPDATED, lambda e: self.refresh_jobs())
        self.event_bus.subscribe(EventType.JOB_DELETED, lambda e: self.refresh_jobs())
        self.event_bus.subscribe(EventType.JOB_TOGGLED, lambda e: self.refresh_jobs())
        
        # 监听主题变化
        self.event_bus.subscribe(EventType.THEME_CHANGED, self._on_theme_changed)
    
    def add_job(self):
        """添加任务"""
        if not self.service.is_available():
            self.view.show_error("调度系统未初始化")
            return
        
        # 显示添加对话框
        form_data = self.view.show_add_dialog()
        
        if form_data:
            try:
                # 创建任务
                job_id = self.service.create_job(form_data)
                
                # 发布事件
                self.event_bus.publish(Event(
                    EventType.JOB_ADDED,
                    {"job_id": job_id, "name": form_data.get("name")}
                ))
                
                self._log(f"任务已添加: {form_data.get('name')}")
                
            except Exception as e:
                self.view.show_error(f"添加任务失败: {e}")
                self._log(f"添加任务失败: {e}", "ERROR")
    
    def edit_job(self):
        """编辑任务"""
        if not self.service.is_available():
            self.view.show_error("调度系统未初始化")
            return
        
        # 获取选中的任务
        selected_job = self.view.get_selected_job()
        if not selected_job:
            self.view.show_info("请先选择一个任务")
            return
        
        job_id = int(selected_job.id)
        
        # 获取任务详情
        try:
            job = self.service.scheduler_storage.get_job(job_id)
            if not job:
                self.view.show_error(f"任务 ID={job_id} 不存在")
                return
        except Exception as e:
            self.view.show_error(f"获取任务信息失败: {e}")
            return
        
        # 显示编辑对话框
        form_data = self.view.show_edit_dialog(job)
        
        if form_data:
            try:
                # 更新任务
                self.service.update_job(job_id, form_data)
                
                # 发布事件
                self.event_bus.publish(Event(
                    EventType.JOB_UPDATED,
                    {"job_id": job_id, "name": form_data.get("name")}
                ))
                
                self._log(f"任务已更新: {form_data.get('name')}")
                
            except Exception as e:
                self.view.show_error(f"更新任务失败: {e}")
                self._log(f"更新任务失败: {e}", "ERROR")
    
    def delete_job(self):
        """删除任务"""
        if not self.service.is_available():
            self.view.show_error("调度系统未初始化")
            return
        
        # 获取选中的任务
        selected_job = self.view.get_selected_job()
        if not selected_job:
            self.view.show_info("请先选择一个任务")
            return
        
        job_id = int(selected_job.id)
        job_name = selected_job.name
        
        # 确认删除
        if not self.view.confirm_delete(job_name):
            return
        
        try:
            # 删除任务
            self.service.delete_job(job_id)
            
            # 发布事件
            self.event_bus.publish(Event(
                EventType.JOB_DELETED,
                {"job_id": job_id, "name": job_name}
            ))
            
            self._log(f"任务已删除: {job_name}")
            
        except Exception as e:
            self.view.show_error(f"删除任务失败: {e}")
            self._log(f"删除任务失败: {e}", "ERROR")
    
    def toggle_job(self):
        """切换任务状态（启用/暂停）"""
        if not self.service.is_available():
            self.view.show_error("调度系统未初始化")
            return
        
        # 获取选中的任务
        selected_job = self.view.get_selected_job()
        if not selected_job:
            self.view.show_info("请先选择一个任务")
            return
        
        job_id = int(selected_job.id)
        new_enabled = not selected_job.enabled
        
        try:
            # 切换状态
            self.service.toggle_job(job_id, new_enabled)
            
            # 发布事件
            self.event_bus.publish(Event(
                EventType.JOB_TOGGLED,
                {"job_id": job_id, "enabled": new_enabled}
            ))
            
            status = "启用" if new_enabled else "暂停"
            self._log(f"任务已{status}: {selected_job.name}")
            
        except Exception as e:
            self.view.show_error(f"切换状态失败: {e}")
            self._log(f"切换状态失败: {e}", "ERROR")
    
    def run_job_once(self):
        """立即运行一次任务"""
        if not self.service.is_available():
            self.view.show_error("调度系统未初始化")
            return
        
        # 获取选中的任务
        selected_job = self.view.get_selected_job()
        if not selected_job:
            self.view.show_info("请先选择一个任务")
            return
        
        job_id = int(selected_job.id)
        job_name = selected_job.name
        
        try:
            # 更新UI状态：显示任务执行中
            if hasattr(self.view, 'update_task_status'):
                self.view.update_task_status(task_name=job_name, is_running=True)
            
            # 运行任务
            self.service.run_job_once(job_id)
            self._log(f"任务已触发运行: {job_name}")
            self.view.show_info(f"任务 '{job_name}' 已触发运行")
            
            # 监听下载完成事件，更新任务状态
            def on_download_completed(event):
                # 清除任务执行状态（这会触发状态恢复）
                if hasattr(self.view, 'update_task_status'):
                    self.view.update_task_status(is_running=False)
                # 强制更新调度器状态显示（确保状态栏正确显示）
                if hasattr(self.view, 'update_status'):
                    is_running = self.service.is_running()
                    # 直接调用update_status，传入正确的状态
                    self.view.update_status(is_running)
                # 取消订阅（只监听一次）
                self.event_bus.unsubscribe(EventType.DOWNLOAD_COMPLETED, on_download_completed)
                self.event_bus.unsubscribe(EventType.DOWNLOAD_FAILED, on_download_failed)
            
            def on_download_failed(event):
                # 清除任务执行状态（这会触发状态恢复）
                if hasattr(self.view, 'update_task_status'):
                    self.view.update_task_status(is_running=False)
                # 强制更新调度器状态显示（确保状态栏正确显示）
                if hasattr(self.view, 'update_status'):
                    is_running = self.service.is_running()
                    # 直接调用update_status，传入正确的状态
                    self.view.update_status(is_running)
                # 取消订阅
                self.event_bus.unsubscribe(EventType.DOWNLOAD_COMPLETED, on_download_completed)
                self.event_bus.unsubscribe(EventType.DOWNLOAD_FAILED, on_download_failed)
            
            # 订阅下载完成/失败事件（临时监听）
            self.event_bus.subscribe(EventType.DOWNLOAD_COMPLETED, on_download_completed)
            self.event_bus.subscribe(EventType.DOWNLOAD_FAILED, on_download_failed)
            
        except Exception as e:
            # 如果启动失败，清除任务状态
            if hasattr(self.view, 'update_task_status'):
                self.view.update_task_status(is_running=False)
            self.view.show_error(f"运行任务失败: {e}")
            self._log(f"运行任务失败: {e}", "ERROR")
    
    def list_jobs(self):
        """
        获取任务列表（用于导出）
        
        Returns:
            任务列表（字典格式）
        """
        if not self.service.is_available():
            return []
        
        try:
            return self.service.list_jobs()
        except Exception as e:
            self._log(f"获取任务列表失败: {e}", "ERROR")
            return []
    
    def refresh_jobs(self):
        """刷新任务列表"""
        if not self.service.is_available():
            return
        
        try:
            # 确保内容已加载（如果是懒加载模式）
            if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
                # 触发懒加载（如果尚未加载）
                self.view.accordion.get_content_frame()
            
            # 检查tree控件是否存在
            if not hasattr(self.view, 'tree'):
                # 如果还不存在，延迟重试
                root = self.view.winfo_toplevel()
                root.after(200, self.refresh_jobs)
                return
            
            # 获取任务列表
            jobs_dict_list = self.service.list_jobs()
            
            # 转换为dataclass模型
            jobs = [SchedulerJobDisplay.from_dict(job_dict) for job_dict in jobs_dict_list]
            
            # 更新视图
            self.view.update_job_list(jobs)
            
        except Exception as e:
            self._log(f"刷新任务列表失败: {e}", "ERROR")
    
    def start_scheduler(self):
        """启动调度器"""
        if not self.service.is_available():
            self.view.show_error("调度系统未初始化")
            return
        
        if self.service.is_running():
            self.view.show_info("调度器已经在运行中")
            return
        
        try:
            success = self.service.start_scheduler()
            if success:
                import time
                self._last_tick_time = time.time()  # 记录启动时间
                # 发布事件
                self.event_bus.publish(Event(EventType.SCHEDULER_STARTED))
                self._log("调度器已启动（自动模式，每60秒tick一次）")
                self.view.show_info("调度器已启动")
                # 立即更新状态显示（确保按钮状态正确）
                if hasattr(self.view, 'update_status'):
                    self.view.update_status(True)
                self._start_status_updates()  # 开始状态更新
            else:
                self.view.show_error("启动调度器失败")
                
        except Exception as e:
            self.view.show_error(f"启动调度器失败: {e}")
            self._log(f"启动调度器失败: {e}", "ERROR")
    
    def stop_scheduler(self):
        """停止调度器"""
        if not self.service.is_available():
            self.view.show_error("调度系统未初始化")
            return
        
        if not self.service.is_running():
            self.view.show_info("调度器未在运行")
            return
        
        try:
            success = self.service.stop_scheduler()
            if success:
                self._last_tick_time = None  # 清除时间记录
                # 发布事件
                self.event_bus.publish(Event(EventType.SCHEDULER_STOPPED))
                self._log("调度器已停止")
                self.view.show_info("调度器已停止")
                # 立即更新状态显示（确保按钮状态正确）
                if hasattr(self.view, 'update_status'):
                    self.view.update_status(False)
                self._stop_status_updates()  # 停止状态更新
            else:
                self.view.show_error("停止调度器失败")
                
        except Exception as e:
            self.view.show_error(f"停止调度器失败: {e}")
            self._log(f"停止调度器失败: {e}", "ERROR")
    
    def _start_status_updates(self):
        """开始状态更新"""
        if self._status_update_job:
            return  # 已经在运行
        
        self._update_status()
    
    def _stop_status_updates(self):
        """停止状态更新"""
        if self._status_update_job:
            root = self.view.winfo_toplevel()
            root.after_cancel(self._status_update_job)
            self._status_update_job = None
        
        # 更新UI为停止状态
        if hasattr(self.view, 'update_status'):
            self.view.update_status(False)
    
    def _update_status(self):
        """更新状态显示（每秒调用）"""
        if not hasattr(self.view, 'update_status'):
            return
        
        is_running = self.service.is_running()
        next_tick_seconds = None
        
        if is_running:
            # 计算下次tick的倒计时
            import time
            tick_interval = self.service.get_tick_interval()
            
            if self._last_tick_time:
                elapsed = time.time() - self._last_tick_time
                remaining = max(0, tick_interval - int(elapsed))
                next_tick_seconds = remaining
                
                # 如果已经过了tick时间，重置计时器
                if remaining == 0:
                    self._last_tick_time = time.time()
                    next_tick_seconds = tick_interval
            else:
                # 首次启动，使用完整间隔
                self._last_tick_time = time.time()
                next_tick_seconds = tick_interval
        
        # 检查是否有任务在执行（通过任务状态标签）
        has_task_running = False
        if hasattr(self.view, 'lbl_task_status'):
            task_text = self.view.lbl_task_status.cget('text')
            has_task_running = bool(task_text and task_text.strip())
        
        # 更新UI
        # 如果有任务在执行，不更新调度器状态（保持"任务执行中"）
        # 如果没有任务在执行，正常更新调度器状态
        if not has_task_running:
            self.view.update_status(is_running, next_tick_seconds)
        # 注意：即使有任务在执行，也要确保按钮状态正确
        # 因为停止按钮应该始终可以点击（如果调度器在运行）
        elif is_running:
            # 有任务在执行，但调度器也在运行，确保停止按钮可用
            if hasattr(self.view, 'btn_stop'):
                self.view.btn_stop.config(state='normal')
            if hasattr(self.view, 'btn_start'):
                self.view.btn_start.config(state='disabled')
        
        # 安排下次更新（1秒后）
        root = self.view.winfo_toplevel()
        self._status_update_job = root.after(1000, self._update_status)
    
    def _scheduler_executor(self, *args, **kwargs):
        """
        调度器执行器
        
        支持两种调用方式：
        1. 自动调度：executor(source_url=..., output_root=..., preferred_langs=..., do_download=...)
        2. 手动运行：executor(job, run) - 位置参数
        
        Args:
            *args: 位置参数（可能是 job, run）
            **kwargs: 关键字参数（source_url, output_root, preferred_langs, do_download）
        
        Returns:
            执行结果字典（包含run_dir等）
        """
        try:
            # 判断调用方式：如果第一个参数是Job对象，则是手动运行方式
            if len(args) >= 1 and hasattr(args[0], 'source_url'):
                # 手动运行方式：executor(job, run)
                job = args[0]
                run = args[1] if len(args) > 1 else None
                source_url = job.source_url
                output_root = job.output_root
                preferred_langs = job.preferred_langs
                do_download = job.do_download
            else:
                # 自动调度方式：使用关键字参数
                source_url = kwargs.get('source_url')
                output_root = kwargs.get('output_root', self.config.get("output_root", "out"))
                preferred_langs = kwargs.get('preferred_langs', self.config.get("download_langs", ["zh", "en"]))
                do_download = kwargs.get('do_download', True)
            
            if not source_url:
                raise ValueError("source_url is required")
            
            # 获取主控制器（通过事件总线）
            main_ctrl = self._get_main_controller()
            if not main_ctrl:
                raise RuntimeError("无法获取主控制器")
            
            # 准备配置
            download_config = {
                "output_root": output_root,
                "download_langs": preferred_langs,
                "download_fmt": self.config.get("download_fmt", "srt"),
                "max_workers": self.config.get("max_workers", 5),
                "incremental_detect": self.config.get("incremental_detect", True),
                "incremental_download": self.config.get("incremental_download", True),
                "force_refresh": self.config.get("force_refresh", False),
                "merge_bilingual": self.config.get("merge_bilingual", True),
            }
            
            # 获取网络配置（从设置控制器获取，确保使用最新的UI配置）
            settings_ctrl = main_ctrl.controllers.get('settings')
            if settings_ctrl:
                try:
                    # 使用 get_advanced_config 方法获取网络配置（从UI获取最新值）
                    network_config = settings_ctrl.get_advanced_config()
                    # 确保Cookie文件路径正确
                    if network_config.get('cookiefile'):
                        from pathlib import Path
                        cookie_path = Path(network_config['cookiefile'])
                        # 如果是相对路径，转换为绝对路径
                        if not cookie_path.is_absolute():
                            cookie_path = Path.cwd() / cookie_path
                            network_config['cookiefile'] = str(cookie_path)
                        # 验证文件是否存在
                        if not cookie_path.exists():
                            self._log(f"⚠️ Cookie文件不存在: {network_config['cookiefile']}", "WARNING")
                    
                    download_config.update(network_config)
                    self._log(f"✓ 已获取网络配置: cookiefile={network_config.get('cookiefile', '(未设置)')[:50]}...", "DEBUG")
                except Exception as e:
                    self._log(f"获取网络配置失败: {e}，使用默认配置", "WARNING")
                    import traceback
                    traceback.print_exc()
                    # 使用默认配置
                    download_config.update({
                        "proxy_text": "",
                        "cookiefile": "",
                        "user_agent": "",
                        "timeout": 30,
                        "retry_times": 3,
                    })
            else:
                self._log("⚠️ 无法获取设置控制器，使用默认网络配置", "WARNING")
            
            # 执行下载（使用DownloadService）
            from services.download_service import DownloadService
            download_service = DownloadService()
            
            # 创建进度回调
            def progress_callback(progress_data: dict):
                # 发布进度事件
                self.event_bus.publish(Event(
                    EventType.DOWNLOAD_PROGRESS,
                    progress_data
                ))
            
            # 创建完成回调
            completion_result = {"success": False, "run_dir": None, "error": None}
            
            def completion_callback(result: dict):
                completion_result["run_dir"] = result.get("run_dir")
                
                # 调试：打印结果信息（强制输出到控制台和日志）
                result_info = f"total={result.get('total', 0)}, downloaded={result.get('downloaded', 0)}, errors={result.get('errors', 0)}, failed={result.get('failed', 0)}"
                print(f"[调度器] 下载完成回调: {result_info}")
                self._log(f"[调度器] 下载完成回调: {result_info}", "INFO")
                
                # 检查是否有错误（多种方式）
                # 1. 直接error字段
                # 2. errors字段 > 0
                # 3. failed字段 > 0
                # 4. downloaded = 0 且 total > 0（表示全部失败）
                has_error = False
                error_msg = None
                
                if "error" in result:
                    has_error = True
                    error_msg = result["error"]
                elif result.get("errors", 0) > 0 or result.get("failed", 0) > 0:
                    has_error = True
                    # 尝试从history.jsonl读取错误信息
                    run_dir = result.get("run_dir", "")
                    if run_dir:
                        try:
                            from pathlib import Path
                            import json
                            history_file = Path(run_dir) / "history.jsonl"
                            if history_file.exists():
                                # 读取history.jsonl，查找错误记录
                                self._log(f"[调度器] 尝试从 {history_file} 读取错误信息", "DEBUG")
                                with history_file.open('r', encoding='utf-8', errors='ignore') as f:
                                    for line in f:
                                        if not line.strip():
                                            continue
                                        try:
                                            rec = json.loads(line)
                                            status = rec.get("status", "")
                                            # 查找错误状态
                                            if status.startswith("error"):
                                                # 优先使用 error_msg 字段（包含详细错误信息）
                                                error_msg_field = rec.get("error_msg", "")
                                                if error_msg_field:
                                                    error_msg = error_msg_field
                                                    self._log(f"[调度器] 从history.jsonl读取到错误信息: {error_msg[:100]}", "DEBUG")
                                                    break
                                                # 如果没有 error_msg，尝试 api_err（旧格式）
                                                api_err = rec.get("api_err", "")
                                                if api_err:
                                                    error_msg = api_err
                                                    self._log(f"[调度器] 从history.jsonl读取到错误信息(api_err): {error_msg[:100]}", "DEBUG")
                                                    break
                                                # 如果都没有，使用 status
                                                if status != "error" and ":" in status:
                                                    error_msg = status.split(":", 1)[1] if ":" in status else status
                                                    self._log(f"[调度器] 从status读取到错误信息: {error_msg[:100]}", "DEBUG")
                                                    break
                                        except (json.JSONDecodeError, Exception) as e:
                                            self._log(f"[调度器] 解析history.jsonl行失败: {e}", "DEBUG")
                                            continue
                            else:
                                self._log(f"[调度器] history.jsonl不存在: {history_file}", "DEBUG")
                        except Exception as e:
                            # 如果读取失败，记录但不影响流程
                            self._log(f"读取错误信息失败: {e}", "DEBUG")
                    
                    # 如果还是没有错误信息，使用默认消息
                    if not error_msg:
                        errors_count = result.get("errors", 0) or result.get("failed", 0)
                        error_msg = f"下载失败，错误数: {errors_count}"
                        print(f"[调度器] 使用默认错误消息: {error_msg}")
                elif result.get("failed", 0) > 0:
                    has_error = True
                    error_msg = f"下载失败，失败数: {result.get('failed', 0)}"
                elif result.get("total", 0) > 0 and result.get("downloaded", 0) == 0:
                    has_error = True
                    # 即使errors和failed为0，如果downloaded=0，也说明下载失败了
                    # 尝试从history.jsonl读取详细错误信息
                    run_dir = result.get("run_dir", "")
                    if run_dir:
                        try:
                            from pathlib import Path
                            import json
                            history_file = Path(run_dir) / "history.jsonl"
                            if history_file.exists():
                                # 读取history.jsonl，查找错误记录
                                print(f"[调度器] 尝试从 {history_file} 读取错误信息（downloaded=0情况）")
                                with history_file.open('r', encoding='utf-8', errors='ignore') as f:
                                    for line in f:
                                        if not line.strip():
                                            continue
                                        try:
                                            rec = json.loads(line)
                                            status = rec.get("status", "")
                                            # 查找错误状态
                                            if status.startswith("error"):
                                                # 优先使用 error_msg 字段
                                                error_msg_field = rec.get("error_msg", "")
                                                if error_msg_field:
                                                    error_msg = error_msg_field
                                                    print(f"[调度器] 从history.jsonl读取到错误信息: {error_msg[:200]}")
                                                    break
                                                # 如果没有 error_msg，尝试 api_err
                                                api_err = rec.get("api_err", "")
                                                if api_err:
                                                    error_msg = api_err
                                                    print(f"[调度器] 从history.jsonl读取到错误信息(api_err): {error_msg[:200]}")
                                                    break
                                        except (json.JSONDecodeError, Exception) as e:
                                            continue
                            
                            # 如果history.jsonl中没有错误信息，检查errors.txt
                            # 如果errors.txt存在且有内容，说明有错误发生
                            errors_file = Path(run_dir) / "errors.txt"
                            if not error_msg and errors_file.exists():
                                errors_content = errors_file.read_text(encoding='utf-8', errors='ignore').strip()
                                if errors_content:
                                    # errors.txt存在且有内容，说明有错误
                                    # 由于无法直接读取控制台输出，我们基于常见错误模式推断
                                    # 如果downloaded=0且errors.txt有内容，很可能是Cookie失效
                                    error_msg = "下载失败：检测到错误（可能是Cookie失效或网络问题）"
                                    print(f"[调度器] 从errors.txt推断错误: {error_msg}")
                        except Exception as e:
                            print(f"[调度器] 读取错误信息失败: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    # 如果还是没有错误信息，使用默认消息
                    if not error_msg:
                        error_msg = "下载失败，所有任务均未成功下载"
                        print(f"[调度器] 使用默认错误消息: {error_msg}")
                
                completion_result["error"] = error_msg if has_error else None
                completion_result["success"] = not has_error and result.get("downloaded", 0) > 0
                
                # 检查是否有错误
                if has_error and error_msg:
                    print(f"[调度器] 检测到错误: {error_msg[:200]}")
                    # 检测Cookie失效
                    # 1. 检查错误消息中是否包含Cookie相关关键词
                    # 2. 如果downloaded=0且errors.txt有内容，也推断为Cookie失效
                    is_cookie_error = False
                    if "sign in" in error_msg.lower() or "cookie" in error_msg.lower() or "bot" in error_msg.lower():
                        is_cookie_error = True
                    elif result.get("total", 0) > 0 and result.get("downloaded", 0) == 0:
                        # 如果downloaded=0，检查errors.txt是否存在且有内容
                        run_dir = result.get("run_dir", "")
                        if run_dir:
                            try:
                                from pathlib import Path
                                errors_file = Path(run_dir) / "errors.txt"
                                if errors_file.exists():
                                    errors_content = errors_file.read_text(encoding='utf-8', errors='ignore').strip()
                                    if errors_content:
                                        # errors.txt有内容，且downloaded=0，很可能是Cookie失效
                                        is_cookie_error = True
                                        print(f"[调度器] 基于errors.txt和downloaded=0推断为Cookie失效")
                            except Exception:
                                pass
                    
                    if is_cookie_error:
                        # Cookie失效特殊提示（强制输出）
                        cookie_warning = "⚠️ Cookie 失效或已过期！"
                        cookie_instruction = "请前往【高级设置】→【网络设置】→【Cookie文件】更新有效的Cookie文件"
                        cookie_tip = "提示：Cookie文件通常需要定期更新，建议使用浏览器扩展（如Get cookies.txt）导出最新Cookie"
                        print(f"[调度器] {cookie_warning}")
                        print(f"[调度器] {cookie_instruction}")
                        print(f"[调度器] {cookie_tip}")
                        self._log(cookie_warning, "ERROR")
                        self._log(cookie_instruction, "WARN")
                        self._log(cookie_tip, "INFO")
                    
                    # 发布下载失败事件
                    try:
                        from utils.error_handler import ErrorHandler
                        error_code = "error_other"
                        if "timeout" in error_msg.lower():
                            error_code = "error_timeout"
                        elif "429" in error_msg or "rate limit" in error_msg.lower():
                            error_code = "error_429"
                        elif "503" in error_msg:
                            error_code = "error_503"
                        elif "sign in" in error_msg.lower() or "cookie" in error_msg.lower() or "bot" in error_msg.lower():
                            error_code = "YTDLP_SIGNIN"
                        
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
                    except ImportError:
                        # 如果错误处理工具不可用，使用简单方式
                        self.event_bus.publish(Event(
                            EventType.DOWNLOAD_FAILED,
                            {"reason": error_msg}
                        ))
                    except Exception as e:
                        # 如果错误处理工具出错，使用简单方式
                        self._log(f"错误处理工具出错: {e}", "WARNING")
                        self.event_bus.publish(Event(
                            EventType.DOWNLOAD_FAILED,
                            {"reason": error_msg}
                        ))
                else:
                    # 下载成功，发布完成事件
                    self.event_bus.publish(Event(
                        EventType.DOWNLOAD_COMPLETED,
                        result
                    ))
            
            # 启动下载
            success = download_service.start_download(
                urls=[source_url],
                config=download_config,
                progress_callback=progress_callback,
                completion_callback=completion_callback,
                dry_run=not do_download
            )
            
            if not success:
                raise RuntimeError("启动下载失败")
            
            # 等待完成（简单实现，实际应该异步）
            import time
            timeout = 300  # 5分钟超时
            start_time = time.time()
            print(f"[调度器] 开始等待下载完成，超时={timeout}秒")
            print(f"[调度器] 初始状态: run_dir={completion_result.get('run_dir')}, error={completion_result.get('error')}, success={completion_result.get('success')}")
            wait_count = 0
            while time.time() - start_time < timeout:
                wait_count += 1
                # 每10次循环（5秒）打印一次状态
                if wait_count % 10 == 0:
                    elapsed = time.time() - start_time
                    print(f"[调度器] 等待中... 已等待{elapsed:.1f}秒, run_dir={completion_result.get('run_dir')}, error={completion_result.get('error')}, success={completion_result.get('success')}")
                
                # 检查是否完成（有run_dir或error表示完成）
                if completion_result["run_dir"] is not None or completion_result["error"] is not None:
                    elapsed = time.time() - start_time
                    print(f"[调度器] 下载完成，耗时={elapsed:.1f}秒, run_dir={completion_result.get('run_dir')}, error={completion_result.get('error')}, success={completion_result.get('success')}")
                    break
                time.sleep(0.5)
            else:
                # 超时
                elapsed = time.time() - start_time
                print(f"[调度器] 等待超时，耗时={elapsed:.1f}秒, run_dir={completion_result.get('run_dir')}, error={completion_result.get('error')}, success={completion_result.get('success')}")
            
            # 检查是否超时
            if time.time() - start_time >= timeout:
                error_msg = "下载超时（5分钟）"
                self._log(f"执行调度任务超时: {error_msg}", "ERROR")
                # 发布失败事件
                self.event_bus.publish(Event(
                    EventType.DOWNLOAD_FAILED,
                    {"reason": error_msg}
                ))
                return {
                    "run_dir": "",
                    "success": False
                }
            
            # 返回结果
            return {
                "run_dir": completion_result.get("run_dir", ""),
                "success": completion_result.get("success", False) and completion_result.get("error") is None
            }
            
        except Exception as e:
            self._log(f"执行调度任务失败: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            raise
    
    def _get_main_controller(self):
        """获取主控制器"""
        # 优先使用直接引用
        if self.main_controller:
            return self.main_controller
        
        # 尝试从视图的父窗口获取
        widget = self.view
        while widget:
            if hasattr(widget, 'main_controller'):
                return widget.main_controller
            widget = widget.master if hasattr(widget, 'master') else None
        
        # 尝试从事件总线获取（如果事件总线有引用）
        if hasattr(self.event_bus, '_main_controller'):
            return self.event_bus._main_controller
        
        return None
    
    def _on_theme_changed(self, event: Event):
        """主题变化处理"""
        theme = event.data.get("theme")
        self.view.update_theme(theme)


__all__ = ['SchedulerController']

