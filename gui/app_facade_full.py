# -*- coding: utf-8 -*-
"""
应用门面完整版 - 集成所有功能
"""
import tkinter as tk
from gui.views.main_window_full import MainWindowFull
from gui.controllers.download_controller import DownloadController
from gui.controllers.scheduler_controller import SchedulerController
from gui.controllers.subscription_controller import SubscriptionController
from gui.controllers.ai_controller import AIController
from gui.controllers.export_controller import ExportController
from gui.controllers.settings_controller import SettingsController
from events.event_bus import event_bus, EventType, Event
from config_store import load_config, save_config
from theme_manager import apply_theme, TOKENS


class AppFacadeFull:
    """
    应用门面完整版
    
    职责：
    1. 创建主窗口和所有面板
    2. 初始化所有控制器
    3. 绑定全局事件
    4. 协调模块间交互
    """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.event_bus = event_bus
        self.config = load_config()
        
        # 创建主窗口（包含所有面板）
        self.main_window = MainWindowFull(root, self.config)
        
        # 初始化控制器
        self._init_controllers()
        
        # 绑定UI事件
        self._bind_ui_events()
        
        # 绑定全局事件
        self._bind_global_events()
        
        # 初始化日志
        self._init_log()
    
    def _init_controllers(self):
        """初始化控制器"""
        # 设置控制器（先创建，供下载控制器使用）
        self.settings_ctrl = SettingsController(
            self.main_window.settings_panel,
            self.config
        )
        
        # 下载控制器（需要settings_ctrl来获取网络配置）
        self.download_ctrl = DownloadController(
            self.main_window.download_panel,
            self.config,
            settings_ctrl=self.settings_ctrl  # 传递设置控制器的引用
        )
        
        # AI控制器
        self.ai_ctrl = AIController(
            self.main_window.ai_panel,
            self.config
        )
        
        # 调度器控制器
        self.scheduler_ctrl = SchedulerController(
            self.main_window.scheduler_panel,
            self.config
        )
        
        # 订阅控制器
        self.subscription_ctrl = SubscriptionController(
            self.main_window.subscription_panel,
            self.config
        )
        
        # 导出控制器（不需要视图）
        self.export_ctrl = ExportController(self.config)
        
        # 加载保存的配置到各个视图
        self._load_saved_configs()
        
        # 设置自动保存（加载配置后）
        self._setup_auto_save()
    
    def _load_saved_configs(self):
        """加载保存的配置到各个视图"""
        try:
            # 加载下载配置
            self.download_ctrl.load_config()
            
            # 加载AI配置
            self.ai_ctrl.load_config()
            
            # 加载网络配置
            self.settings_ctrl.load_config()
            
            print("[AppFacade] 已加载保存的配置")
        except Exception as e:
            print(f"[AppFacade] 加载配置失败: {e}")
    
    def _setup_auto_save(self):
        """设置自动保存"""
        # 为AI控制器设置自动保存
        if hasattr(self.ai_ctrl, '_setup_auto_save'):
            self.ai_ctrl._setup_auto_save()
    
    def _bind_ui_events(self):
        """绑定UI事件"""
        # 工具栏按钮
        self.main_window.btn_detect.config(
            command=lambda: self.download_ctrl.start_download(dry_run=True)
        )
        
        self.main_window.btn_download.config(
            command=lambda: self.download_ctrl.start_download(dry_run=False)
        )
        
        self.main_window.btn_stop.config(
            command=self.download_ctrl.stop_download
        )
        
        # 主题切换
        self.main_window.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_change)
        
        # 日志按钮
        self.main_window.btn_clear_log.config(command=self._clear_log)
        
        # 下载面板按钮
        self.main_window.download_panel.btn_clear.config(
            command=self.download_ctrl.clear_urls
        )
        
        # AI面板按钮
        # (按钮已在AIController中绑定)
        
        # 调度器面板按钮
        self.main_window.scheduler_panel.btn_add.config(
            command=self.scheduler_ctrl.add_job
        )
        self.main_window.scheduler_panel.btn_edit.config(
            command=self.scheduler_ctrl.edit_job
        )
        self.main_window.scheduler_panel.btn_delete.config(
            command=self.scheduler_ctrl.delete_job
        )
        
        # 导出功能（集成到调度器和订阅面板）
        # 调度器导出功能：需要先添加导出按钮到scheduler_panel，或者使用菜单
        # 订阅导出功能：使用控制器原有的export_subscriptions方法（已经包含文件选择）
        self.main_window.scheduler_panel.btn_toggle.config(
            command=self.scheduler_ctrl.toggle_job
        )
        self.main_window.scheduler_panel.btn_run_once.config(
            command=self.scheduler_ctrl.run_job_once
        )
        self.main_window.scheduler_panel.btn_start.config(
            command=self.scheduler_ctrl.start_scheduler
        )
        self.main_window.scheduler_panel.btn_stop.config(
            command=self.scheduler_ctrl.stop_scheduler
        )
        self.main_window.scheduler_panel.btn_refresh.config(
            command=self.scheduler_ctrl.refresh_jobs
        )
        
        # 订阅面板按钮
        self.main_window.subscription_panel.btn_add.config(
            command=self.subscription_ctrl.add_subscription
        )
        self.main_window.subscription_panel.btn_edit.config(
            command=self.subscription_ctrl.edit_subscription
        )
        self.main_window.subscription_panel.btn_delete.config(
            command=self.subscription_ctrl.delete_subscription
        )
        self.main_window.subscription_panel.btn_toggle.config(
            command=self.subscription_ctrl.toggle_subscription
        )
        self.main_window.subscription_panel.btn_import.config(
            command=self.subscription_ctrl.import_subscriptions
        )
        # 订阅导出：使用控制器原有的export_subscriptions方法（已经包含文件选择）
        # 注意：这里保持原实现，因为export_subscriptions内部已经处理了文件选择
        self.main_window.subscription_panel.btn_refresh.config(
            command=self.subscription_ctrl.refresh_subscriptions
        )
    
    def _bind_global_events(self):
        """绑定全局事件"""
        # 日志事件
        self.event_bus.subscribe(EventType.LOG_MESSAGE, self._on_log_message)
        
        # 下载事件
        self.event_bus.subscribe(EventType.DOWNLOAD_STARTED, self._on_download_started)
        self.event_bus.subscribe(EventType.DOWNLOAD_PROGRESS, self._on_download_progress)
        self.event_bus.subscribe(EventType.DOWNLOAD_COMPLETED, self._on_download_completed)
        self.event_bus.subscribe(EventType.DOWNLOAD_FAILED, self._on_download_failed)
        self.event_bus.subscribe(EventType.DOWNLOAD_STOPPED, self._on_download_stopped)
        
        # 调度器事件
        self.event_bus.subscribe(EventType.SCHEDULER_STARTED, self._on_scheduler_started)
        self.event_bus.subscribe(EventType.SCHEDULER_STOPPED, self._on_scheduler_stopped)
        self.event_bus.subscribe(EventType.JOB_ADDED, self._on_job_added)
        self.event_bus.subscribe(EventType.JOB_UPDATED, self._on_job_updated)
        self.event_bus.subscribe(EventType.JOB_DELETED, self._on_job_deleted)
        self.event_bus.subscribe(EventType.JOB_TOGGLED, self._on_job_toggled)
        
        # 订阅事件
        self.event_bus.subscribe(EventType.SUBSCRIPTION_ADDED, self._on_subscription_added)
        self.event_bus.subscribe(EventType.SUBSCRIPTION_UPDATED, self._on_subscription_updated)
        self.event_bus.subscribe(EventType.SUBSCRIPTION_DELETED, self._on_subscription_deleted)
        self.event_bus.subscribe(EventType.SUBSCRIPTION_TOGGLED, self._on_subscription_toggled)
        
        # AI处理事件
        self.event_bus.subscribe(EventType.AI_PROCESSING_STARTED, self._on_ai_started)
        self.event_bus.subscribe(EventType.AI_PROCESSING_PROGRESS, self._on_ai_progress)
        self.event_bus.subscribe(EventType.AI_PROCESSING_COMPLETED, self._on_ai_completed)
        self.event_bus.subscribe(EventType.AI_PROCESSING_FAILED, self._on_ai_failed)
        
        # 导出事件
        self.event_bus.subscribe(EventType.EXPORT_COMPLETED, self._on_export_completed)
        self.event_bus.subscribe(EventType.EXPORT_FAILED, self._on_export_failed)
    
    def _init_log(self):
        """初始化日志"""
        self.main_window.append_log("=" * 60, "INFO")
        self.main_window.append_log("🚀 新架构完整版启动成功", "SUCCESS")
        self.main_window.append_log("=" * 60, "INFO")
        self.main_window.append_log("", "INFO")
        self.main_window.append_log("✅ 事件总线已初始化", "INFO")
        self.main_window.append_log("✅ 下载控制器已初始化", "INFO")
        self.main_window.append_log("✅ AI控制器已初始化", "INFO")
        self.main_window.append_log("✅ 调度器控制器已初始化", "INFO")
        self.main_window.append_log("✅ 设置控制器已初始化", "INFO")
        self.main_window.append_log("✅ 订阅控制器已初始化", "INFO")
        self.main_window.append_log("✅ 导出控制器已初始化", "INFO")
        self.main_window.append_log("", "INFO")
        self.main_window.append_log("📦 当前模块:", "INFO")
        self.main_window.append_log("  - 下载功能 (检测/下载/停止)", "INFO")
        self.main_window.append_log("  - AI处理 (AI摘要/翻译/双语)", "INFO")
        self.main_window.append_log("  - 调度器 (任务管理/启动/停止)", "INFO")
        self.main_window.append_log("  - 高级设置 (网络/代理/认证)", "INFO")
        self.main_window.append_log("  - 订阅管理 (增删改查/导入导出)", "INFO")
        self.main_window.append_log("  - 导出功能 (调度器/订阅/日志导出)", "INFO")
        self.main_window.append_log("", "INFO")
        self.main_window.append_log("=" * 60, "INFO")
    
    # ========== 事件处理 ==========
    
    def _on_log_message(self, event: Event):
        """处理日志消息"""
        message = event.data.get("message", "")
        level = event.data.get("level", "INFO")
        self.main_window.append_log(message, level)
    
    def _on_download_started(self, event: Event):
        """下载开始"""
        count = event.data.get("count", 0)
        dry_run = event.data.get("dry_run", False)
        mode = "检测" if dry_run else "下载"
        self.main_window.append_log(f"🚀 开始{mode}，共 {count} 个任务", "INFO")
    
    def _on_download_progress(self, event: Event):
        """下载进度"""
        phase = event.data.get("phase", "")
        current = event.data.get("current", 0)
        total = event.data.get("total", 0)
        message = event.data.get("message", "")
        
        # current == -1 表示阶段提示消息，不显示百分比
        if current == -1:
            self.main_window.append_log(f"[{phase}] {message}", "INFO")
        elif total > 0:
            percent = max(0, min(100, int((current / total) * 100)))  # 确保在0-100之间
            self.main_window.append_log(f"[{phase}] {percent}% - {message}", "INFO")
        else:
            # total为0的情况，只显示消息
            self.main_window.append_log(f"[{phase}] {message}", "INFO")
    
    def _on_download_completed(self, event: Event):
        """下载完成"""
        self.main_window.append_log("✅ 下载任务完成", "SUCCESS")
    
    def _on_download_failed(self, event: Event):
        """下载失败"""
        reason = event.data.get("reason", "未知错误")
        self.main_window.append_log(f"❌ 下载失败: {reason}", "ERROR")
    
    def _on_download_stopped(self, event: Event):
        """下载停止"""
        self.main_window.append_log("⏹️ 下载已停止", "WARN")
    
    def _on_scheduler_started(self, event: Event):
        """调度器启动"""
        self.main_window.append_log("🚀 调度器已启动", "SUCCESS")
    
    def _on_scheduler_stopped(self, event: Event):
        """调度器停止"""
        self.main_window.append_log("⏹️ 调度器已停止", "WARN")
    
    def _on_job_added(self, event: Event):
        """任务添加"""
        name = event.data.get("name", "")
        self.main_window.append_log(f"✅ 任务已添加: {name}", "SUCCESS")
    
    def _on_job_updated(self, event: Event):
        """任务更新"""
        name = event.data.get("name", "")
        self.main_window.append_log(f"✅ 任务已更新: {name}", "SUCCESS")
    
    def _on_job_deleted(self, event: Event):
        """任务删除"""
        name = event.data.get("name", "")
        self.main_window.append_log(f"🗑️ 任务已删除: {name}", "WARN")
    
    def _on_job_toggled(self, event: Event):
        """任务切换"""
        enabled = event.data.get("enabled", True)
        status = "启用" if enabled else "暂停"
        self.main_window.append_log(f"⏯️ 任务已{status}", "INFO")
    
    def _on_subscription_added(self, event: Event):
        """订阅添加"""
        name = event.data.get("name", "")
        self.main_window.append_log(f"✅ 订阅已添加: {name}", "SUCCESS")
    
    def _on_subscription_updated(self, event: Event):
        """订阅更新"""
        name = event.data.get("name", "")
        self.main_window.append_log(f"✅ 订阅已更新: {name}", "SUCCESS")
    
    def _on_subscription_deleted(self, event: Event):
        """订阅删除"""
        name = event.data.get("name", "")
        self.main_window.append_log(f"🗑️ 订阅已删除: {name}", "WARN")
    
    def _on_subscription_toggled(self, event: Event):
        """订阅切换"""
        enabled = event.data.get("enabled", True)
        status = "启用" if enabled else "禁用"
        self.main_window.append_log(f"⏯️ 订阅已{status}", "INFO")
    
    def _on_ai_started(self, event: Event):
        """AI处理开始"""
        run_dir = event.data.get("run_dir", "")
        self.main_window.append_log(f"🤖 AI处理已开始: {run_dir}", "INFO")
    
    def _on_ai_progress(self, event: Event):
        """AI处理进度"""
        message = event.data.get("message", "")
        self.main_window.append_log(f"🤖 {message}", "INFO")
    
    def _on_ai_completed(self, event: Event):
        """AI处理完成"""
        total = event.data.get("total", 0)
        done = event.data.get("done", 0)
        html_path = event.data.get("html_path")
        
        self.main_window.append_log(
            f"✅ AI处理完成: {done}/{total} 个视频", "SUCCESS"
        )
        
        if html_path:
            self.main_window.append_log(f"📄 HTML报告: {html_path}", "SUCCESS")
    
    def _on_ai_failed(self, event: Event):
        """AI处理失败"""
        reason = event.data.get("reason", "未知错误")
        self.main_window.append_log(f"❌ AI处理失败: {reason}", "ERROR")
    
    def _on_export_completed(self, event: Event):
        """导出完成"""
        export_type = event.data.get("type", "")
        path = event.data.get("path", "")
        self.main_window.append_log(
            f"✅ 导出完成 ({export_type}): {path}", "SUCCESS"
        )
    
    def _on_export_failed(self, event: Event):
        """导出失败"""
        export_type = event.data.get("type", "")
        reason = event.data.get("reason", "未知错误")
        self.main_window.append_log(
            f"❌ 导出失败 ({export_type}): {reason}", "ERROR"
        )
    
    # ========== UI操作 ==========
    
    def _on_theme_change(self, event):
        """主题切换"""
        theme = self.main_window.theme_combo.get()
        
        # 应用主题
        apply_theme(self.main_window.style if hasattr(self.main_window, 'style') else self.root, theme)
        
        # 发布主题变化事件
        self.event_bus.publish(Event(
            EventType.THEME_CHANGED,
            {"theme": theme}
        ))
        
        # 保存配置
        self.config["ui"]["theme"] = theme
        save_config(self.config)
        
        self.main_window.append_log(f"🎨 主题已切换: {theme}", "INFO")
    
    def _clear_log(self):
        """清空日志"""
        self.main_window.clear_log()
        self.main_window.append_log("📋 日志已清空", "INFO")
    
    def cleanup(self):
        """清理资源"""
        self.download_ctrl.cleanup()
        self.scheduler_ctrl.cleanup()
        self.subscription_ctrl.cleanup()


__all__ = ['AppFacadeFull']

