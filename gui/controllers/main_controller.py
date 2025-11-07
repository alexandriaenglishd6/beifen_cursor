# -*- coding: utf-8 -*-
"""
主控制器 - 协调所有子控制器
"""
from gui.controllers.base_controller import BaseController
from gui.controllers.download_controller import DownloadController
from gui.controllers.scheduler_controller import SchedulerController
from gui.controllers.subscription_controller import SubscriptionController
from gui.controllers.ai_controller import AIController
from gui.controllers.settings_controller import SettingsController
from gui.controllers.optimize_controller import OptimizeController
from gui.controllers.translate_controller import TranslateController
from gui.controllers.export_controller import ExportController
from gui.utils.log_manager import LogManager
from events.event_bus import EventType, Event
from theme_manager import apply_theme
from config_store import load_config
from services.config_service import get_config_service
from datetime import datetime
from pathlib import Path
from typing import List
import json
from tkinter import simpledialog, messagebox, filedialog


class MainController(BaseController):
    """
    主控制器
    
    职责：
    1. 协调所有子控制器
    2. 处理全局事件（主题切换、配置保存等）
    3. 管理应用生命周期
    """
    
    def __init__(self, view, config: dict):
        """
        初始化主控制器
        
        Args:
            view: 主窗口视图
            config: 全局配置
        """
        self.view = view
        self.config = config
        self.controllers = {}
        self.cfg_service = get_config_service()
        
        super().__init__()
        
        # 创建日志管理器
        max_logs = config.get("logging", {}).get("max_entries", 10000)
        self.log_manager = LogManager(max_entries=max_logs)
        self._log_search_pos = 0  # 当前搜索位置
        
        # 创建子控制器
        self._create_controllers()
        
    def _create_controllers(self):
        """
        创建所有子控制器（使用统一的初始化顺序）
        
        初始化顺序：
        1. 确保UI完全创建（触发所有懒加载）
        2. SettingsController（先创建，供DownloadController使用）
        3. DownloadController（依赖SettingsController）
        4. AIController
        5. SchedulerController
        6. SubscriptionController
        7. ExportController（不需要视图）
        8. 加载配置到所有控制器
        9. 设置自动保存
        10. 绑定UI事件
        """
        print("[MainController] 开始创建子控制器...")
        
        # 1. 设置控制器（先创建，供下载控制器使用）
        print("[MainController] 创建设置控制器...")
        self.controllers['settings'] = SettingsController(
            self.view.settings_panel,
            self.config
        )
        
        # 2. 下载控制器（需要settings_ctrl来获取网络配置）
        print("[MainController] 创建下载控制器...")
        self.controllers['download'] = DownloadController(
            self.view.download_panel,
            self.config,
            settings_ctrl=self.controllers['settings']  # 传递设置控制器的引用
        )
        
        # 3. AI控制器
        print("[MainController] 创建AI控制器...")
        self.controllers['ai'] = AIController(
            self.view.ai_panel,
            self.config
        )
        
        # 4. 字幕优化控制器
        print("[MainController] 创建字幕优化控制器...")
        try:
            self.controllers['optimize'] = OptimizeController(
                self.view.optimize_panel,
                self.config
            )
            print("[MainController] ✓ 字幕优化控制器创建成功")
        except Exception as e:
            print(f"[MainController] ⚠️ 字幕优化控制器创建失败: {e}")
            import traceback
            traceback.print_exc()
            # 即使失败也继续，不影响其他功能
        
        # 5. 字幕翻译控制器
        print("[MainController] 创建字幕翻译控制器...")
        try:
            self.controllers['translate'] = TranslateController(
                self.view.translate_panel,
                self.config
            )
            print("[MainController] ✓ 字幕翻译控制器创建成功")
        except Exception as e:
            print(f"[MainController] ⚠️ 字幕翻译控制器创建失败: {e}")
            import traceback
            traceback.print_exc()
            # 即使失败也继续，不影响其他功能
        
        # 6. 调度器控制器
        print("[MainController] 创建调度器控制器...")
        scheduler_ctrl = SchedulerController(
            self.view.scheduler_panel,
            self.config
        )
        scheduler_ctrl.main_controller = self  # 设置主控制器引用
        self.controllers['scheduler'] = scheduler_ctrl
        
        # 5. 订阅控制器
        print("[MainController] 创建订阅控制器...")
        self.controllers['subscription'] = SubscriptionController(
            self.view.subscription_panel,
            self.config
        )
        
        # 8. 导出控制器（不需要视图）
        print("[MainController] 创建导出控制器...")
        self.controllers['export'] = ExportController(self.config)
        
        print("[MainController] ✓ 所有子控制器已创建")
        
        # 确保UI完全创建后再加载配置和绑定事件
        self._ensure_ui_ready_then_init()
    
    def _ensure_ui_ready_then_init(self):
        """
        确保UI完全创建后再初始化（包括懒加载组件）
        
        使用统一的初始化管理器来确保初始化顺序
        """
        try:
            from utils.init_manager import InitializationManager
            init_manager = InitializationManager(self.view.root)
            
            # 步骤1: 确保UI完全创建（触发所有懒加载）
            def ensure_ui_ready():
                """确保UI完全创建"""
                return self._ensure_ui_components_ready()
            
            init_manager.add_step("确保UI就绪", ensure_ui_ready, retry_on_fail=True, max_retries=5)
            
            # 步骤2: 加载配置（依赖UI就绪）
            def load_all_configs():
                """加载所有配置"""
                try:
                    self.controllers['settings'].load_config()
                    self.controllers['download'].load_config()
                    self.controllers['ai'].load_config()
                    # 加载优化配置（如果存在）
                    if 'optimize' in self.controllers:
                        try:
                            self.controllers['optimize'].load_config()
                        except Exception as e:
                            print(f"[MainController] ⚠️ 加载优化配置失败: {e}")
                            # 继续执行，不影响其他配置加载
                    # 加载翻译配置（如果存在）
                    if 'translate' in self.controllers:
                        try:
                            self.controllers['translate'].load_config()
                        except Exception as e:
                            print(f"[MainController] ⚠️ 加载翻译配置失败: {e}")
                            # 继续执行，不影响其他配置加载
                    print("[MainController] ✓ 所有配置已加载")
                    return True
                except Exception as e:
                    print(f"[MainController] ✗ 加载配置失败: {e}")
                    import traceback
                    traceback.print_exc()
                    return False
            
            init_manager.add_step("加载配置", load_all_configs, dependencies=["确保UI就绪"])
            
            # 步骤3: 绑定事件（依赖配置加载）
            def bind_events():
                """绑定所有事件"""
                try:
                    print("[MainController] 开始绑定视图事件...")
                    self._bind_view_events()
                    print("[MainController] ✓ 所有事件已绑定")
                    
                    # 验证按钮绑定
                    if hasattr(self.view, 'btn_detect'):
                        cmd = self.view.btn_detect.cget('command')
                        if cmd:
                            print(f"[MainController] ✓ 检测按钮已绑定: {cmd}")
                        else:
                            print("[MainController] ✗ 检测按钮未绑定（command为空）")
                    
                    if hasattr(self.view, 'btn_download'):
                        cmd = self.view.btn_download.cget('command')
                        if cmd:
                            print(f"[MainController] ✓ 下载按钮已绑定: {cmd}")
                        else:
                            print("[MainController] ✗ 下载按钮未绑定（command为空）")
                    
                    return True
                except Exception as e:
                    print(f"[MainController] ✗ 绑定事件失败: {e}")
                    import traceback
                    traceback.print_exc()
                    return False
            
            init_manager.add_step("绑定事件", bind_events, dependencies=["加载配置"])
            
            # 步骤4: 延迟验证按钮绑定（确保绑定成功）
            def verify_bindings():
                """验证按钮绑定"""
                try:
                    print("[MainController] ========== 验证按钮绑定 ==========")
                    if hasattr(self.view, 'btn_detect'):
                        cmd = self.view.btn_detect.cget('command')
                        state = self.view.btn_detect.cget('state')
                        print(f"[MainController] 检测按钮: command={cmd is not None}, state={state}")
                        if not cmd:
                            print("[MainController] ⚠️ 检测按钮未绑定，尝试重新绑定")
                            self._bind_view_events()
                    else:
                        print("[MainController] ✗ 检测按钮不存在")
                    
                    if hasattr(self.view, 'btn_download'):
                        cmd = self.view.btn_download.cget('command')
                        state = self.view.btn_download.cget('state')
                        print(f"[MainController] 下载按钮: command={cmd is not None}, state={state}")
                        if not cmd:
                            print("[MainController] ⚠️ 下载按钮未绑定，尝试重新绑定")
                            self._bind_view_events()
                    else:
                        print("[MainController] ✗ 下载按钮不存在")
                    
                    print("[MainController] =====================================")
                    return True
                except Exception as e:
                    print(f"[MainController] ✗ 验证绑定失败: {e}")
                    return False
            
            init_manager.add_step("验证按钮绑定", verify_bindings, dependencies=["绑定事件"])
            
            # 执行初始化
            print("[MainController] 开始统一初始化...")
            init_manager.execute_all()
            
            # 检查状态
            status = init_manager.get_status()
            if status["failed"] > 0:
                print(f"[MainController] ⚠️ 初始化完成，但有 {status['failed']} 个步骤失败")
                for error in status["errors"]:
                    print(f"  - {error}")
            else:
                print("[MainController] ✓ 统一初始化完成")
                
            # 延迟再次验证和绑定（确保按钮绑定成功）
            def delayed_verify_and_bind():
                """延迟验证和绑定（确保UI完全创建后）"""
                print("[MainController] ========== 延迟验证按钮绑定 ==========")
                try:
                    if hasattr(self.view, 'btn_detect'):
                        cmd = self.view.btn_detect.cget('command')
                        state = self.view.btn_detect.cget('state')
                        visible = self.view.btn_detect.winfo_viewable()
                        print(f"[MainController] 检测按钮: command={cmd is not None}, state={state}, visible={visible}")
                        
                        if not cmd:
                            print("[MainController] ⚠️ 检测按钮未绑定，强制绑定测试函数...")
                            # 绑定一个简单的测试函数
                            def test_detect():
                                print("[MainController] ===== 检测按钮被点击（延迟绑定测试）======")
                                import sys
                                sys.stdout.flush()
                                # 然后调用真正的功能
                                if 'download' in self.controllers:
                                    try:
                                        self.controllers['download'].start_download(dry_run=True)
                                    except Exception as e:
                                        print(f"[MainController] ✗ 执行检测失败: {e}")
                            
                            self.view.btn_detect.config(command=test_detect)
                            print(f"[MainController] ✓ 已强制绑定检测按钮")
                        
                        # 验证最终状态
                        final_cmd = self.view.btn_detect.cget('command')
                        final_state = self.view.btn_detect.cget('state')
                        print(f"[MainController] 检测按钮最终: command={final_cmd is not None}, state={final_state}")
                    
                    if hasattr(self.view, 'btn_download'):
                        cmd = self.view.btn_download.cget('command')
                        state = self.view.btn_download.cget('state')
                        visible = self.view.btn_download.winfo_viewable()
                        print(f"[MainController] 下载按钮: command={cmd is not None}, state={state}, visible={visible}")
                        
                        if not cmd:
                            print("[MainController] ⚠️ 下载按钮未绑定，强制绑定测试函数...")
                            # 绑定一个简单的测试函数
                            def test_download():
                                print("[MainController] ===== 下载按钮被点击（延迟绑定测试）======")
                                import sys
                                sys.stdout.flush()
                                # 然后调用真正的功能
                                if 'download' in self.controllers:
                                    try:
                                        self.controllers['download'].start_download(dry_run=False)
                                    except Exception as e:
                                        print(f"[MainController] ✗ 执行下载失败: {e}")
                            
                            self.view.btn_download.config(command=test_download)
                            print(f"[MainController] ✓ 已强制绑定下载按钮")
                        
                        # 验证最终状态
                        final_cmd = self.view.btn_download.cget('command')
                        final_state = self.view.btn_download.cget('state')
                        print(f"[MainController] 下载按钮最终: command={final_cmd is not None}, state={final_state}")
                except Exception as e:
                    print(f"[MainController] ✗ 延迟验证失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 延迟500ms后再次验证和绑定
            self.view.root.after(500, delayed_verify_and_bind)
                
        except ImportError:
            # 如果初始化管理器不可用，使用传统方式
            print("[MainController] ⚠️ 初始化管理器不可用，使用传统初始化方式")
            self._ensure_ui_ready_then_init_legacy()
    
    def _ensure_ui_components_ready(self) -> bool:
        """
        确保所有UI组件已创建（包括懒加载组件）
        
        Returns:
            是否就绪
        """
        # 检查关键UI组件
        critical_components = [
            ('btn_detect', '检测按钮'),
            ('btn_download', '下载按钮'),
            ('btn_stop', '停止按钮'),
            ('download_panel', '下载面板'),
            ('settings_panel', '设置面板'),
            ('ai_panel', 'AI面板'),
            ('optimize_panel', '字幕优化面板'),
            ('translate_panel', '字幕翻译面板'),
        ]
        
        missing_components = []
        for attr, name in critical_components:
            if not hasattr(self.view, attr):
                missing_components.append(name)
        
        # 检查懒加载组件
        lazy_load_issues = []
        panels = [
            ("settings", getattr(self.view, "settings_panel", None)),
            ("download", getattr(self.view, "download_panel", None)),
            ("ai", getattr(self.view, "ai_panel", None)),
            ("optimize", getattr(self.view, "optimize_panel", None)),
            ("translate", getattr(self.view, "translate_panel", None)),
            ("scheduler", getattr(self.view, "scheduler_panel", None)),
            ("subscription", getattr(self.view, "subscription_panel", None)),
        ]
        
        for panel_name, panel in panels:
            if panel and hasattr(panel, "accordion"):
                accordion = panel.accordion
                if hasattr(accordion, "_lazy_load") and accordion._lazy_load:
                    try:
                        # 触发懒加载
                        accordion.get_content_frame()
                    except Exception as e:
                        lazy_load_issues.append(f"{panel_name}面板: {e}")
        
        if missing_components or lazy_load_issues:
            if missing_components:
                print(f"[MainController] ⚠️ 缺少关键组件: {', '.join(missing_components)}")
            if lazy_load_issues:
                print(f"[MainController] ⚠️ 懒加载问题: {', '.join(lazy_load_issues)}")
            return False
        
        print("[MainController] ✓ 所有UI组件已就绪")
        return True
    
    def _ensure_ui_ready_then_init_legacy(self):
        """
        传统初始化方式（兼容性，当初始化管理器不可用时使用）
        """
        def check_and_init(retry_count=0, max_retries=5):
            """检查UI就绪状态并初始化"""
            if not self._ensure_ui_components_ready():
                if retry_count < max_retries:
                    print(f"[MainController] UI未就绪，{200}ms后重试 ({retry_count + 1}/{max_retries})")
                    self.view.root.after(200, lambda: check_and_init(retry_count + 1, max_retries))
                    return
                else:
                    print("[MainController] ⚠️ UI未就绪，但已达到最大重试次数，继续初始化")
            
            # UI就绪后，加载配置和绑定事件
            try:
                self.controllers['settings'].load_config()
                self.controllers['download'].load_config()
                self.controllers['ai'].load_config()
                print("[MainController] ✓ 所有配置已加载")
            except Exception as e:
                print(f"[MainController] ✗ 加载配置失败: {e}")
            
            # 绑定事件
            try:
                print("[MainController] 开始绑定视图事件...")
                self._bind_view_events()
                print("[MainController] ✓ 所有事件已绑定")
            except Exception as e:
                print(f"[MainController] ✗ 绑定事件失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 延迟验证按钮绑定
            def delayed_verify():
                print("[MainController] ========== 传统方式延迟验证按钮绑定 ==========")
                try:
                    if hasattr(self.view, 'btn_detect'):
                        cmd = self.view.btn_detect.cget('command')
                        state = self.view.btn_detect.cget('state')
                        print(f"[MainController] 检测按钮: command={cmd is not None}, state={state}")
                        if not cmd:
                            print("[MainController] ⚠️ 检测按钮未绑定，重新绑定...")
                            self._bind_view_events()
                    
                    if hasattr(self.view, 'btn_download'):
                        cmd = self.view.btn_download.cget('command')
                        state = self.view.btn_download.cget('state')
                        print(f"[MainController] 下载按钮: command={cmd is not None}, state={state}")
                        if not cmd:
                            print("[MainController] ⚠️ 下载按钮未绑定，重新绑定...")
                            self._bind_view_events()
                except Exception as e:
                    print(f"[MainController] ✗ 延迟验证失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 延迟500ms后验证
            self.view.root.after(500, delayed_verify)
        
        # 延迟检查，确保UI完全创建
        self.view.root.after(100, lambda: check_and_init())
    
    def _setup_event_listeners(self):
        """设置事件监听"""
        # 监听日志事件
        self.event_bus.subscribe(EventType.LOG_MESSAGE, self._on_log_message)
        self.event_bus.subscribe(EventType.LOG_CLEAR, self._on_log_clear)
        
        # 监听下载事件
        self.event_bus.subscribe(EventType.DOWNLOAD_STARTED, self._on_download_started)
        self.event_bus.subscribe(EventType.DOWNLOAD_PROGRESS, self._on_download_progress)
        self.event_bus.subscribe(EventType.DOWNLOAD_COMPLETED, self._on_download_completed)
        self.event_bus.subscribe(EventType.DOWNLOAD_FAILED, self._on_download_failed)
        self.event_bus.subscribe(EventType.DOWNLOAD_STOPPED, self._on_download_stopped)
        self.event_bus.subscribe(EventType.DOWNLOAD_PAUSED, self._on_download_paused)
        self.event_bus.subscribe(EventType.DOWNLOAD_RESUMED, self._on_download_resumed)
        
        # 监听主题变化
        self.event_bus.subscribe(EventType.THEME_CHANGED, self._on_theme_changed)
        
        # 监听配置事件
        self.event_bus.subscribe(EventType.CONFIG_SAVED, self._on_config_saved)
    
    def _bind_view_events(self):
        """绑定视图事件"""
        print("[MainController] 开始绑定视图事件...")
        print(f"[MainController] 视图对象: {self.view}")
        print(f"[MainController] 视图类型: {type(self.view)}")
        print(f"[MainController] 控制器字典: {list(self.controllers.keys())}")
        
        # 主题切换
        if hasattr(self.view, 'theme_combo'):
            self.view.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_combo_change)
        
        # 下载按钮（确保控制器已创建）
        if hasattr(self.view, 'btn_detect'):
            print(f"[MainController] ✓ 检测按钮存在: {self.view.btn_detect}")
            if 'download' in self.controllers:
                print(f"[MainController] ✓ 下载控制器存在: {self.controllers['download']}")
                try:
                    # 使用包装函数，避免lambda闭包问题
                    def on_detect_click():
                        print("=" * 80)
                        print("[MainController] ===== 检测按钮被点击 ======")
                        print("=" * 80)
                        import sys
                        sys.stdout.flush()
                        try:
                            print(f"[MainController] 调用下载控制器: {self.controllers['download']}")
                            print(f"[MainController] start_download方法存在: {hasattr(self.controllers['download'], 'start_download')}")
                            self.controllers['download'].start_download(dry_run=True)
                            print("[MainController] ✓ start_download调用完成")
                        except Exception as e:
                            print(f"[MainController] ✗ 执行检测失败: {e}")
                            import traceback
                            traceback.print_exc()
                            sys.stdout.flush()
                    
                    print(f"[MainController] 准备绑定检测按钮，command函数: {on_detect_click}")
                    print(f"[MainController] on_detect_click函数ID: {id(on_detect_click)}")
                    
                    # 确保按钮未被禁用
                    current_state = self.view.btn_detect.cget('state')
                    print(f"[MainController] 检测按钮当前状态: {current_state}")
                    if current_state == 'disabled':
                        print("[MainController] ⚠️ 检测按钮被禁用，启用它")
                        self.view.btn_detect.config(state='normal')
                    
                    # 先检查当前command是什么
                    old_cmd = self.view.btn_detect.cget('command')
                    print(f"[MainController] 检测按钮当前command: {old_cmd}")
                    print(f"[MainController] 检测按钮当前command类型: {type(old_cmd)}")
                    
                    # 检查按钮是否可见
                    try:
                        is_visible = self.view.btn_detect.winfo_viewable()
                        print(f"[MainController] 检测按钮是否可见: {is_visible}")
                    except:
                        print("[MainController] ⚠️ 无法检查按钮可见性")
                    
                    # 强制绑定，即使已经有command
                    print(f"[MainController] 准备覆盖按钮command（从测试绑定改为实际功能）")
                    # 先移除可能存在的bind事件（避免事件冲突）
                    try:
                        self.view.btn_detect.unbind('<Button-1>')
                        print(f"[MainController] ✓ 已移除检测按钮的Button-1绑定")
                    except:
                        pass
                    
                    # 然后设置command - 直接绑定函数，避免lambda闭包问题
                    self.view.btn_detect.config(command=on_detect_click)
                    print(f"[MainController] ✓ 已绑定检测按钮（直接绑定函数）")
                    print(f"[MainController] 绑定后的command: {self.view.btn_detect.cget('command')}")
                    
                    # 验证绑定
                    cmd = self.view.btn_detect.cget('command')
                    print(f"[MainController] 验证：检测按钮command = {cmd}")
                    print(f"[MainController] 验证：检测按钮command类型 = {type(cmd)}")
                    
                    # 验证command是否真的是我们的函数
                    cmd_str = str(cmd)
                    if 'on_detect_click' in cmd_str or 'lambda' in cmd_str:
                        print(f"[MainController] ✓ 确认：检测按钮command已正确绑定到控制器函数")
                    else:
                        print(f"[MainController] ⚠️ 警告：检测按钮command可能未正确绑定")
                        print(f"[MainController] command字符串: {cmd_str[:200]}")
                    
                    # 再次验证状态
                    final_state = self.view.btn_detect.cget('state')
                    print(f"[MainController] 检测按钮最终状态: {final_state}")
                    
                    # 强制刷新按钮
                    self.view.btn_detect.update()
                    print(f"[MainController] ✓ 检测按钮已刷新")
                    
                    # 再次验证command是否还在
                    final_cmd = self.view.btn_detect.cget('command')
                    if final_cmd != cmd:
                        print(f"[MainController] ⚠️ 警告：检测按钮command被改变！原={cmd}, 现={final_cmd}")
                        # 重新绑定
                        self.view.btn_detect.config(command=on_detect_click)
                        print(f"[MainController] ✓ 已重新绑定检测按钮")
                    
                    # 尝试程序化调用，验证绑定是否有效
                    try:
                        print("[MainController] 尝试程序化调用按钮（仅测试，不执行实际功能）...")
                        # 不实际调用，只检查command是否存在
                        if cmd:
                            print("[MainController] ✓ 按钮command存在，应该可以响应点击")
                        else:
                            print("[MainController] ✗ 按钮command为空！")
                    except Exception as e:
                        print(f"[MainController] ⚠️ 程序化调用测试失败: {e}")
                except Exception as e:
                    print(f"[MainController] ✗ 绑定检测按钮失败: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("[MainController] ✗ 检测按钮存在，但下载控制器未创建")
        else:
            print("[MainController] ✗ 检测按钮不存在")
        
        if hasattr(self.view, 'btn_download'):
            print(f"[MainController] ✓ 下载按钮存在: {self.view.btn_download}")
            if 'download' in self.controllers:
                try:
                    # 使用包装函数，避免lambda闭包问题
                    def on_download_click():
                        print("=" * 80)
                        print("[MainController] ===== 下载按钮被点击 ======")
                        print("=" * 80)
                        import sys
                        sys.stdout.flush()
                        try:
                            print(f"[MainController] 调用下载控制器: {self.controllers['download']}")
                            print(f"[MainController] start_download方法存在: {hasattr(self.controllers['download'], 'start_download')}")
                            self.controllers['download'].start_download(dry_run=False)
                            print("[MainController] ✓ start_download调用完成")
                        except Exception as e:
                            print(f"[MainController] ✗ 执行下载失败: {e}")
                            import traceback
                            traceback.print_exc()
                            sys.stdout.flush()
                    
                    print(f"[MainController] 准备绑定下载按钮，command函数: {on_download_click}")
                    print(f"[MainController] on_download_click函数ID: {id(on_download_click)}")
                    
                    # 确保按钮未被禁用
                    current_state = self.view.btn_download.cget('state')
                    print(f"[MainController] 下载按钮当前状态: {current_state}")
                    if current_state == 'disabled':
                        print("[MainController] ⚠️ 下载按钮被禁用，启用它")
                        self.view.btn_download.config(state='normal')
                    
                    # 先检查当前command是什么
                    old_cmd = self.view.btn_download.cget('command')
                    print(f"[MainController] 下载按钮当前command: {old_cmd}")
                    print(f"[MainController] 下载按钮当前command类型: {type(old_cmd)}")
                    
                    # 检查按钮是否可见
                    try:
                        is_visible = self.view.btn_download.winfo_viewable()
                        print(f"[MainController] 下载按钮是否可见: {is_visible}")
                    except:
                        print("[MainController] ⚠️ 无法检查按钮可见性")
                    
                    # 强制绑定，即使已经有command
                    print(f"[MainController] 准备覆盖按钮command（从测试绑定改为实际功能）")
                    # 先移除可能存在的bind事件（避免事件冲突）
                    try:
                        self.view.btn_download.unbind('<Button-1>')
                        print(f"[MainController] ✓ 已移除下载按钮的Button-1绑定")
                    except:
                        pass
                    
                    # 然后设置command - 直接绑定函数，避免lambda闭包问题
                    self.view.btn_download.config(command=on_download_click)
                    print(f"[MainController] ✓ 已绑定下载按钮（直接绑定函数）")
                    print(f"[MainController] 绑定后的command: {self.view.btn_download.cget('command')}")
                    
                    # 验证绑定
                    cmd = self.view.btn_download.cget('command')
                    print(f"[MainController] 验证：下载按钮command = {cmd}")
                    print(f"[MainController] 验证：下载按钮command类型 = {type(cmd)}")
                    
                    # 验证command是否真的是我们的函数
                    cmd_str = str(cmd)
                    if 'on_download_click' in cmd_str or 'lambda' in cmd_str:
                        print(f"[MainController] ✓ 确认：下载按钮command已正确绑定到控制器函数")
                    else:
                        print(f"[MainController] ⚠️ 警告：下载按钮command可能未正确绑定")
                        print(f"[MainController] command字符串: {cmd_str[:200]}")
                    
                    # 再次验证状态
                    final_state = self.view.btn_download.cget('state')
                    print(f"[MainController] 下载按钮最终状态: {final_state}")
                    
                    # 强制刷新按钮
                    self.view.btn_download.update()
                    print(f"[MainController] ✓ 下载按钮已刷新")
                    
                    # 再次验证command是否还在
                    final_cmd = self.view.btn_download.cget('command')
                    if final_cmd != cmd:
                        print(f"[MainController] ⚠️ 警告：下载按钮command被改变！原={cmd}, 现={final_cmd}")
                        # 重新绑定
                        self.view.btn_download.config(command=on_download_click)
                        print(f"[MainController] ✓ 已重新绑定下载按钮")
                    
                    # 尝试程序化调用，验证绑定是否有效
                    try:
                        print("[MainController] 尝试程序化调用按钮（仅测试，不执行实际功能）...")
                        # 不实际调用，只检查command是否存在
                        if cmd:
                            print("[MainController] ✓ 按钮command存在，应该可以响应点击")
                        else:
                            print("[MainController] ✗ 按钮command为空！")
                    except Exception as e:
                        print(f"[MainController] ⚠️ 程序化调用测试失败: {e}")
                except Exception as e:
                    print(f"[MainController] ✗ 绑定下载按钮失败: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("[MainController] ✗ 下载按钮存在，但下载控制器未创建")
        else:
            print("[MainController] ✗ 下载按钮不存在")
        
        if hasattr(self.view, 'btn_stop'):
            print(f"[MainController] ✓ 停止按钮存在: {self.view.btn_stop}")
            if 'download' in self.controllers:
                try:
                    self.view.btn_stop.config(command=self.controllers['download'].stop_download)
                    print("[MainController] ✓ 已绑定停止按钮")
                except Exception as e:
                    print(f"[MainController] ✗ 绑定停止按钮失败: {e}")
            else:
                print("[MainController] ✗ 停止按钮存在，但下载控制器未创建")
        else:
            print("[MainController] ✗ 停止按钮不存在")
        
        # 暂停/恢复按钮
        if hasattr(self.view, 'btn_pause_resume'):
            self.view.btn_pause_resume.config(command=self._toggle_pause_resume)
            print("[MainController] ✓ 已绑定暂停/恢复按钮")
        else:
            print("[MainController] ✗ 暂停/恢复按钮不存在")
        
        # 日志按钮
        if hasattr(self.view, 'btn_clear_log'):
            self.view.btn_clear_log.config(command=self._clear_log)
        
        if hasattr(self.view, 'btn_search_log_toolbar'):
            print(f"[DEBUG] 绑定搜索按钮: {self.view.btn_search_log_toolbar}")
            self.view.btn_search_log_toolbar.config(command=self._on_search_log_click)
            print(f"[DEBUG] ✓ 搜索按钮已绑定")
        else:
            print(f"[DEBUG] ✗ btn_search_log_toolbar 不存在")
        
        if hasattr(self.view, 'btn_export_log'):
            self.view.btn_export_log.config(command=self._export_log)
        
        if hasattr(self.view, 'btn_find_next'):
            self.view.btn_find_next.config(command=self._find_next_log)
        
        # 日志过滤
        if hasattr(self.view, 'combo_log_level'):
            self.view.combo_log_level.bind("<<ComboboxSelected>>", self._on_log_level_changed)
        
        if hasattr(self.view, 'entry_log_search'):
            print(f"[DEBUG] 绑定搜索输入框事件")
            self.view.entry_log_search.bind("<Return>", lambda e: self._on_search_log_click())
            self.view.entry_log_search.bind("<KeyRelease>", self._on_search_text_changed)
            print(f"[DEBUG] ✓ 搜索输入框事件已绑定")
        
        # 历史记录按钮
        if hasattr(self.view, 'btn_view_history'):
            self.view.btn_view_history.config(command=self._view_history)
        
        # 预设功能
        if hasattr(self.view, 'preset_menu'):
            self.view.preset_menu.bind("<<ComboboxSelected>>", self._on_preset_selected)
        
        if hasattr(self.view, 'refs') and 'btn_save_preset' in self.view.refs:
            self.view.refs['btn_save_preset'].config(command=self.save_preset)
        
        # 暂停/恢复按钮初始状态
        if hasattr(self.view, 'btn_pause_resume'):
            self._update_pause_resume_button(state="normal")
        
        # 初始化预设菜单
        self.view.root.after(200, self._refresh_preset_menu)
    
    def _test_button_binding(self):
        """测试按钮绑定是否成功"""
        print("[MainController] ========== 测试按钮绑定 ==========")
        if hasattr(self.view, 'btn_detect'):
            cmd = self.view.btn_detect.cget('command')
            print(f"[MainController] 检测按钮command: {cmd}")
            if cmd:
                print("[MainController] ✓ 检测按钮已绑定")
            else:
                print("[MainController] ✗ 检测按钮未绑定（command为空）")
        else:
            print("[MainController] ✗ 检测按钮不存在")
        
        if hasattr(self.view, 'btn_download'):
            cmd = self.view.btn_download.cget('command')
            print(f"[MainController] 下载按钮command: {cmd}")
            if cmd:
                print("[MainController] ✓ 下载按钮已绑定")
            else:
                print("[MainController] ✗ 下载按钮未绑定（command为空）")
        else:
            print("[MainController] ✗ 下载按钮不存在")
        
        # 测试直接调用
        if 'download' in self.controllers:
            print("[MainController] 测试直接调用下载控制器...")
            try:
                # 不实际执行，只测试方法是否存在
                if hasattr(self.controllers['download'], 'start_download'):
                    print("[MainController] ✓ 下载控制器的start_download方法存在")
                else:
                    print("[MainController] ✗ 下载控制器的start_download方法不存在")
            except Exception as e:
                print(f"[MainController] ✗ 测试失败: {e}")
        print("[MainController] =====================================")
    
    def _on_theme_combo_change(self, event=None):
        """主题下拉框变化"""
        new_theme = self.view.theme_combo.get()
        self.switch_theme(new_theme)
    
    def switch_theme(self, theme_name: str):
        """
        切换主题
        
        Args:
            theme_name: 主题名称 (light/dark/blue)
        """
        # 更新配置（统一经由 ConfigService）
        try:
            self.cfg_service.update("ui", {"theme": theme_name})
            self.cfg_service.save()
        except Exception as e:
            print(f"[MainController] ⚠️ 保存主题配置失败: {e}")
        
        # 应用主题到ttk.Style
        from tkinter import ttk
        style = ttk.Style()
        apply_theme(style, theme_name)
        
        # 更新视图主题
        if hasattr(self.view, 'update_theme'):
            self.view.update_theme(theme_name)
        
        # 更新所有子控制器视图的主题
        for ctrl in self.controllers.values():
            if hasattr(ctrl, 'view') and hasattr(ctrl.view, 'update_theme'):
                ctrl.view.update_theme(theme_name)
        
        # 发布主题变化事件
        self.event_bus.publish(Event(
            EventType.THEME_CHANGED,
            {"theme": theme_name}
        ))
    
    def _on_log_message(self, event: Event):
        """处理日志消息事件"""
        message = event.data.get("message", "")
        level = event.data.get("level", "INFO")
        print(f"[MainController] _on_log_message 被调用: level={level}, message={message[:50]}")
        try:
            # 添加到日志管理器
            self.log_manager.add_log(message, level)
            
            # 添加到视图（视图会检查级别过滤）
            self.view.append_log(message, level)
            print(f"[MainController] ✓ 日志已添加到视图")
        except Exception as e:
            print(f"[MainController] ✗ 添加日志失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_log_clear(self, event: Event):
        """处理清空日志事件"""
        self._clear_log()
    
    def _clear_log(self):
        """清空日志"""
        self.log_manager.clear()
        self.view.clear_log()
        self._log_search_pos = 0
        self.event_bus.publish(Event(EventType.LOG_CLEAR))
    
    def _on_log_level_changed(self, event=None):
        """日志级别过滤改变"""
        # 重新显示所有日志（应用新的过滤）
        self._refresh_log_display()
    
    def _refresh_log_display(self):
        """刷新日志显示（应用当前过滤条件）"""
        # 获取当前过滤条件
        level = self.view.combo_log_level.get() if hasattr(self.view, 'combo_log_level') else "ALL"
        keyword = self.view.entry_log_search.get().strip() if hasattr(self.view, 'entry_log_search') else ""
        use_regex = self.view.var_use_regex.get() if hasattr(self.view, 'var_use_regex') else False
        
        # 确保Text组件处于normal状态
        current_state = self.view.txt_log.cget('state')
        was_disabled = (current_state == 'disabled')
        if was_disabled:
            self.view.txt_log.config(state='normal')
        
        # 清空显示
        self.view.txt_log.delete("1.0", "end")
        
        # 获取过滤后的日志
        filtered_logs = self.log_manager.filter_logs(
            level=level if level != "ALL" else None,
            keyword=keyword if keyword else None,
            use_regex=use_regex
        )
        
        # 重新显示，并在插入时同时应用搜索高亮
        for log in filtered_logs:
            log_line = f"[{log.timestamp}] [{log.level}] {log.message}\n"
            start_pos = self.view.txt_log.index("end")
            self.view.txt_log.insert("end", log_line, log.level)
            end_pos = self.view.txt_log.index("end-1c")
            
            # 如果有关键词，检查这一行是否匹配并添加高亮
            if keyword:
                line_content = log.message
                if use_regex:
                    try:
                        import re
                        pattern = re.compile(keyword, re.IGNORECASE)
                        if pattern.search(line_content):
                            # 找到匹配，高亮整行中的关键词
                            self._highlight_keyword_in_line(start_pos, end_pos, keyword, use_regex)
                    except re.error:
                        if keyword.lower() in line_content.lower():
                            self._highlight_keyword_in_line(start_pos, end_pos, keyword, False)
                else:
                    if keyword.lower() in line_content.lower():
                        self._highlight_keyword_in_line(start_pos, end_pos, keyword, False)
        
        # 恢复Text组件状态
        if was_disabled:
            self.view.txt_log.config(state='disabled')
        
        # 滚动到底部
        if hasattr(self.view, 'var_auto_scroll') and self.view.var_auto_scroll.get():
            self.view.txt_log.see("end")
    
    def _highlight_keyword_in_line(self, line_start: str, line_end: str, keyword: str, use_regex: bool):
        """在指定行中高亮关键词"""
        try:
            # 使用Text组件的search方法在行内搜索
            start_pos = line_start
            while True:
                pos = self.view.txt_log.search(keyword, start_pos, line_end, nocase=True)
                if not pos:
                    break
                
                end_pos = f"{pos}+{len(keyword)}c"
                # 添加search_match tag（会覆盖level tag的颜色）
                self.view.txt_log.tag_add("search_match", pos, end_pos)
                # 确保search_match tag在最上层
                self.view.txt_log.tag_raise("search_match")
                start_pos = end_pos
        except Exception as e:
            print(f"[DEBUG] 行内高亮失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_search_log_click(self):
        """搜索日志按钮点击"""
        print("[DEBUG] ========== _on_search_log_click 被调用 ==========")
        
        if not hasattr(self.view, 'entry_log_search'):
            print("[DEBUG] ✗ entry_log_search 不存在")
            return
        
        keyword = self.view.entry_log_search.get().strip()
        print(f"[DEBUG] 获取到的关键词: '{keyword}'")
        
        if not keyword:
            messagebox.showinfo("提示", "请输入搜索关键词")
            return
        
        use_regex = self.view.var_use_regex.get() if hasattr(self.view, 'var_use_regex') else False
        
        print(f"[DEBUG] 搜索关键词: '{keyword}', 使用正则: {use_regex}")
        import sys
        sys.stdout.flush()
        
        # 查找匹配项（用于导航）
        matches = self.log_manager.search(keyword, use_regex, 0)
        
        # 直接高亮当前显示的日志（不刷新）
        print("[DEBUG] 开始高亮当前显示的日志...")
        highlight_count = self.view.highlight_search_matches(keyword, use_regex)
        print(f"[DEBUG] 高亮完成，实际高亮 {highlight_count} 处")
        sys.stdout.flush()
        
        if highlight_count > 0:
            self._log_search_pos = matches[0][0] if matches else 0
            # 显示实际高亮的字符匹配数，而不是日志条目数
            self.view.append_log(f"找到 {highlight_count} 处匹配", "SUCCESS")
            
            # 尝试滚动到第一个匹配位置
            try:
                # 找到第一个匹配的日志在显示中的位置
                if matches:
                    content = self.view.txt_log.get("1.0", "end")
                    search_text = f"[{matches[0][1].timestamp}] [{matches[0][1].level}] {matches[0][1].message}"
                    pos = content.find(search_text)
                    if pos != -1:
                        line_start = content.rfind('\n', 0, pos) + 1
                        line_num = content[:line_start].count('\n') + 1
                        self.view.txt_log.see(f"{line_num}.0")
            except Exception as e:
                print(f"[DEBUG] 滚动失败: {e}")
                import traceback
                traceback.print_exc()
                pass
        else:
            print(f"[DEBUG] 未找到匹配项")
            sys.stdout.flush()
            # 清除高亮
            self.view.txt_log.tag_remove("search_match", "1.0", "end")
            self.view.append_log(f"未找到匹配项", "WARN")
    
    def _on_search_text_changed(self, event=None):
        """搜索文本改变"""
        keyword = self.view.entry_log_search.get().strip() if hasattr(self.view, 'entry_log_search') else ""
        if not keyword:
            # 清除高亮并刷新显示（显示所有日志）
            self.view.txt_log.tag_delete("search_match")
            # 重新显示所有日志（应用级别过滤）
            self._refresh_log_display()
            return
        
        use_regex = self.view.var_use_regex.get() if hasattr(self.view, 'var_use_regex') else False
        # 实时高亮（不刷新整个显示，只高亮当前显示的日志）
        self.view.highlight_search_matches(keyword, use_regex)
    
    def _find_next_log(self):
        """查找下一个匹配项"""
        if not hasattr(self.view, 'entry_log_search'):
            return
        
        keyword = self.view.entry_log_search.get().strip()
        if not keyword:
            return
        
        use_regex = self.view.var_use_regex.get() if hasattr(self.view, 'var_use_regex') else False
        
        # 从当前位置开始搜索
        matches = self.log_manager.search(keyword, use_regex, self._log_search_pos + 1)
        
        if matches:
            self._log_search_pos = matches[0][0]
            # 刷新显示并滚动到匹配位置
            self._refresh_log_display()
            try:
                content = self.view.txt_log.get("1.0", "end")
                search_text = f"[{matches[0][1].timestamp}] [{matches[0][1].level}] {matches[0][1].message}"
                pos = content.find(search_text)
                if pos != -1:
                    line_start = content.rfind('\n', 0, pos) + 1
                    line_num = content[:line_start].count('\n') + 1
                    self.view.txt_log.see(f"{line_num}.0")
            except:
                pass
        else:
            # 没找到，从头开始
            matches = self.log_manager.search(keyword, use_regex, 0)
            if matches:
                self._log_search_pos = matches[0][0]
                self._refresh_log_display()
                messagebox.showinfo("提示", "已到达末尾，从头开始搜索")
            else:
                messagebox.showinfo("提示", "未找到匹配项")
    
    def _export_log(self):
        """导出日志"""
        # 选择导出格式
        format_choice = messagebox.askyesno("导出日志", "选择导出格式：\n是 = JSON格式\n否 = TXT格式")
        is_json = format_choice
        
        # 选择文件路径
        if is_json:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                title="导出日志为JSON"
            )
        else:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                title="导出日志为TXT"
            )
        
        if not file_path:
            return
        
        try:
            # 获取当前过滤条件
            level = self.view.combo_log_level.get() if hasattr(self.view, 'combo_log_level') else "ALL"
            keyword = self.view.entry_log_search.get().strip() if hasattr(self.view, 'entry_log_search') else ""
            use_regex = self.view.var_use_regex.get() if hasattr(self.view, 'var_use_regex') else False
            
            # 导出
            if is_json:
                count = self.log_manager.export_json(
                    file_path,
                    level=level if level != "ALL" else None,
                    keyword=keyword if keyword else None,
                    use_regex=use_regex
                )
            else:
                count = self.log_manager.export_txt(
                    file_path,
                    level=level if level != "ALL" else None,
                    keyword=keyword if keyword else None,
                    use_regex=use_regex
                )
            
            messagebox.showinfo("成功", f"已导出 {count} 条日志到:\n{file_path}")
            self.view.append_log(f"日志已导出: {count} 条 -> {file_path}", "SUCCESS")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")
            self.view.append_log(f"导出日志失败: {e}", "ERROR")
            import traceback
            traceback.print_exc()
    
    def _view_history(self):
        """查看历史记录"""
        try:
            # 传递根窗口给ExportController
            self.controllers['export'].view_history(root_window=self.view.root)
        except Exception as e:
            self._log(f"打开历史记录失败: {e}", "ERROR")
            import traceback
            traceback.print_exc()
    
    def _on_theme_changed(self, event: Event):
        """主题变化事件处理"""
        theme = event.data.get("theme", "")
        if theme and hasattr(self.view, 'theme_combo'):
            self.view.theme_combo.set(theme)
    
    def _on_config_saved(self, event: Event):
        """配置保存事件处理"""
        self.view.append_log("配置已保存", "SUCCESS")
    
    def _on_download_started(self, event: Event):
        """下载开始事件处理"""
        print(f"[MainController] _on_download_started 被调用")
        data = event.data
        dry_run = data.get("dry_run", False)
        count = data.get("count", 0)
        urls = data.get("urls", [])
        mode = "检测" if dry_run else "下载"
        
        print(f"[MainController] 下载开始: mode={mode}, count={count}, urls={len(urls)}")
        
        # 更新按钮状态（显示加载动画）
        if dry_run:
            self.view.set_button_loading('detect', True)
            self.view.set_button_loading('download', False)
        else:
            self.view.set_button_loading('detect', False)
            self.view.set_button_loading('download', True)
        
        # 启用停止按钮
        if hasattr(self.view, 'btn_stop'):
            self.view.btn_stop.config(state='normal')
            print("[MainController] ✓ 已启用停止按钮")
        
        # 重置进度条
        self.view.update_progress({
            "percent": 0,
            "phase": "",
            "task": f"准备{mode} {count} 个任务",
            "title": "",
            "speed": None,
            "eta": None
        })
        
        log_msg = f"开始{mode}任务，共 {count} 个视频"
        print(f"[MainController] 准备添加日志: {log_msg}")
        self.view.append_log(log_msg, "INFO")
        print(f"[MainController] 日志已添加")
        
        # 更新暂停/恢复按钮状态
        self._update_pause_resume_button(state="running")
    
    def _on_download_progress(self, event: Event):
        """下载进度事件处理"""
        progress = event.data
        phase = progress.get("phase", "")
        current = progress.get("current", 0)
        total = progress.get("total", 0)
        message = progress.get("message", "")
        url = progress.get("url", "")  # 当前处理的URL
        
        # 计算进度百分比
        if total > 0:
            percent = int((current / total) * 100)
            percent = max(0, min(100, percent))
        else:
            percent = 0
        
        # 构建任务信息
        task_info = ""
        if url:
            # 显示当前处理的URL（截断）
            if len(url) > 40:
                task_info = url[:37] + "..."
            else:
                task_info = url
        elif total > 0:
            task_info = f"任务 {current}/{total}"
        
        # 更新进度条和百分比显示
        progress_dict = {
            "percent": percent,
            "phase": phase,
            "task": task_info,
            "title": "",
            "speed": None,
            "eta": None
        }
        self.view.update_progress(progress_dict)
        
        # 格式化进度消息
        if message:
            # 如果消息包含 "✓ 完成" 并且有失败计数，暂时不显示
            # 因为 _verify_download_results 会显示调整后的统计
            if "✓ 完成" in message and "失败" in message:
                # 检查是否有失败计数
                import re
                match = re.search(r'(\d+)\s*失败', message)
                if match and int(match.group(1)) > 0:
                    # 暂时不显示这个消息，让 _verify_download_results 显示调整后的统计
                    print(f"[MainController] 跳过显示原始完成消息（包含失败计数）: {message}")
                    return
            
            log_msg = message
        elif total > 0:
            log_msg = f"[{phase}] {current}/{total} ({percent}%)"
        else:
            log_msg = f"[{phase}] {current}"
        
        self.view.append_log(log_msg, "INFO")
    
    def _on_download_completed(self, event: Event):
        """下载完成事件处理"""
        data = event.data
        
        # 重置按钮状态（取消加载动画）
        self.view.set_button_loading('detect', False)
        self.view.set_button_loading('download', False)
        
        # 禁用停止按钮
        if hasattr(self.view, 'btn_stop'):
            self.view.btn_stop.config(state='disabled')
            print("[MainController] ✓ 已禁用停止按钮")
        
        # 更新进度条到100%
        self.view.update_progress({"percent": 100, "phase": "", "task": "", "title": "", "speed": None, "eta": None})
        
        # 检查是否为检测模式
        is_detection = data.get("is_detection", False)
        
        if is_detection:
            # 检测模式：显示检测结果（已在DownloadController中格式化）
            has_subs_count = data.get("has_subs_count", 0)
            no_subs_count = data.get("no_subs_count", 0)
            total = data.get("total", 0)
            
            # 检测结果已在DownloadController中显示，这里只记录日志
            self.view.append_log(f"检测任务完成: 总计 {total}，有字幕 {has_subs_count}，无字幕 {no_subs_count}", "SUCCESS")
        else:
            # 下载模式：显示下载结果
            # 注意：详细的统计信息会在 DownloadController._verify_download_results 中显示（已调整）
            # 这里只显示简单的完成消息，避免显示未调整的原始统计
            run_dir = data.get("run_dir", "")
            
            # 不在这里显示详细的统计信息，因为 _verify_download_results 会显示调整后的统计
            # self.view.append_log(f"下载完成: 总计 {total}，成功 {downloaded}，失败 {errors}", "SUCCESS")
            if run_dir:
                self.view.append_log(f"输出目录: {run_dir}", "INFO")
            # 重置暂停/恢复按钮状态
            self._update_pause_resume_button(state="normal")
        
        # 延迟重置进度条（3秒后）
        self.view.root.after(3000, lambda: self.view.update_progress({"percent": 0, "phase": "", "task": "", "title": "", "speed": None, "eta": None}))
    
    def _on_download_failed(self, event: Event):
        """下载失败事件处理（包括Cookie失效检测）"""
        reason = event.data.get("reason", "未知错误")
        
        # 重置按钮状态
        self.view.set_button_loading('detect', False)
        self.view.set_button_loading('download', False)
        
        # 禁用停止按钮
        if hasattr(self.view, 'btn_stop'):
            self.view.btn_stop.config(state='disabled')
            print("[MainController] ✓ 已禁用停止按钮")
        
        self.view.append_log(f"下载失败: {reason}", "ERROR")
        # 重置暂停/恢复按钮状态
        self._update_pause_resume_button(state="normal")
    
    def _on_download_stopped(self, event: Event):
        """下载停止事件处理"""
        # 重置按钮状态
        self.view.set_button_loading('detect', False)
        self.view.set_button_loading('download', False)
        
        # 禁用停止按钮
        if hasattr(self.view, 'btn_stop'):
            self.view.btn_stop.config(state='disabled')
            print("[MainController] ✓ 已禁用停止按钮")
        
        self.view.append_log("下载已停止", "WARN")
        # 重置暂停/恢复按钮状态
        self._update_pause_resume_button(state="normal")
    
    def _on_download_paused(self, event: Event):
        """下载暂停事件处理"""
        self.view.append_log("下载已暂停", "WARN")
        # 更新按钮为"恢复"
        self._update_pause_resume_button(state="paused")
    
    def _on_download_resumed(self, event: Event):
        """下载恢复事件处理"""
        self.view.append_log("下载已恢复", "INFO")
        # 更新按钮为"暂停"
        self._update_pause_resume_button(state="running")
    
    def _toggle_pause_resume(self):
        """切换暂停/恢复状态"""
        download_ctrl = self.controllers['download']
        
        print(f"[MainController] 暂停/恢复按钮被点击，当前状态: is_paused={download_ctrl.is_paused}")
        
        # 检查是否有任务在运行
        if not download_ctrl.service.is_running():
            self.view.show_error("没有正在运行的下载任务")
            print("[MainController] ✗ 没有正在运行的下载任务")
            return
        
        # 根据当前状态切换
        if download_ctrl.is_paused:
            print("[MainController] 执行恢复操作")
            download_ctrl.resume_download()
        else:
            print("[MainController] 执行暂停操作")
            download_ctrl.pause_download()
    
    def _update_pause_resume_button(self, state: str = "normal"):
        """
        更新暂停/恢复按钮状态
        
        Args:
            state: 状态 ("normal"=正常/"running"=运行中/"paused"=已暂停)
        """
        if not hasattr(self.view, 'btn_pause_resume'):
            return
        
        print(f"[MainController] 更新暂停/恢复按钮状态: {state}")
        
        if state == "paused":
            # 已暂停，显示"恢复"
            self.view.btn_pause_resume.config(text="▶️ 恢复", state="normal")
            print("[MainController] ✓ 按钮已更新为: ▶️ 恢复")
        elif state == "running":
            # 运行中，显示"暂停"
            self.view.btn_pause_resume.config(text="⏸️ 暂停", state="normal")
            print("[MainController] ✓ 按钮已更新为: ⏸️ 暂停")
        else:
            # 正常状态（无任务），禁用按钮
            self.view.btn_pause_resume.config(text="⏸️ 暂停", state="disabled")
            print("[MainController] ✓ 按钮已更新为: ⏸️ 暂停 (禁用)")
    
    def save_preset(self):
        """保存当前配置为预设"""
        preset_name = simpledialog.askstring(
            "保存预设",
            "输入预设名称:",
            initialvalue=f"预设{len(self._list_presets()) + 1}"
        )
        
        if not preset_name or not preset_name.strip():
            return
        
        preset_name = preset_name.strip()
        
        # 收集当前配置（包括所有主要配置和AI配置）
        config = {
            "ui_theme": self.config.get("ui", {}).get("theme", "dark"),
            "ui_lang": self.config.get("ui", {}).get("lang", "zh"),
            "output_root": self.config.get("run", {}).get("output_root", "out"),
            "max_workers": self.config.get("run", {}).get("max_workers", 5),
            "download_langs": self.config.get("run", {}).get("download_langs", []),
        }
        
        # 添加AI配置（从AI控制器获取）
        if 'ai' in self.controllers:
            ai_config = self.controllers['ai'].view.get_config()
            config["ai_config"] = {
                "ai_enabled": ai_config.get("ai_enabled", False),
                "ai_provider": ai_config.get("ai_provider", "GPT"),
                "ai_model": ai_config.get("ai_model", "gpt-5"),
                "ai_api_key": ai_config.get("ai_api_key", ""),
                "ai_base_url": ai_config.get("ai_base_url", ""),
                "translate_enabled": ai_config.get("translate_enabled", False),
                "translate_langs": ai_config.get("translate_langs", ["zh", "en"]),
                "bilingual_enabled": ai_config.get("bilingual_enabled", False),
            }
        
        # 保存到文件
        preset_dir = Path("config/presets")
        preset_dir.mkdir(parents=True, exist_ok=True)
        preset_file = preset_dir / f"{preset_name}.json"
        
        with open(preset_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        self.view.append_log(f"预设已保存: {preset_name}", "SUCCESS")
        self._refresh_preset_menu()
        messagebox.showinfo("成功", f"预设 '{preset_name}' 已保存")
    
    def load_preset(self, preset_name: str):
        """加载配置预设"""
        if not preset_name:
            return
        
        preset_file = Path("config/presets") / f"{preset_name}.json"
        
        if not preset_file.exists():
            messagebox.showerror("错误", f"预设不存在: {preset_name}")
            return
        
        # 读取配置
        try:
            with open(preset_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            messagebox.showerror("错误", f"读取预设失败: {e}")
            return
        
        # 更新配置
        if "ui_theme" in config:
            try:
                # 先持久化再切换主题
                self.cfg_service.update("ui", {"theme": config["ui_theme"]})
                self.cfg_service.save()
            except Exception as e:
                print(f"[MainController] ⚠️ 保存预设主题失败: {e}")
            self.switch_theme(config["ui_theme"])  # 应用到UI
        
        if "ui_lang" in config:
            try:
                self.cfg_service.update("ui", {"lang": config["ui_lang"]})
            except Exception as e:
                print(f"[MainController] ⚠️ 保存预设语言失败: {e}")
        
        if "output_root" in config:
            try:
                # 存入 run 段，保持与默认结构一致
                run_section = self.cfg_service.get("run") or {}
                run_section["output_root"] = config["output_root"]
                self.cfg_service.set("run", None, run_section)
            except Exception as e:
                print(f"[MainController] ⚠️ 保存预设输出目录失败: {e}")
        
        if "max_workers" in config:
            try:
                run_section = self.cfg_service.get("run") or {}
                run_section["max_workers"] = config["max_workers"]
                self.cfg_service.set("run", None, run_section)
            except Exception as e:
                print(f"[MainController] ⚠️ 保存预设并发数失败: {e}")
        
        if "download_langs" in config:
            try:
                run_section = self.cfg_service.get("run") or {}
                run_section["download_langs"] = config["download_langs"]
                self.cfg_service.set("run", None, run_section)
            except Exception as e:
                print(f"[MainController] ⚠️ 保存预设语言列表失败: {e}")
        
        # 加载AI配置（如果存在）
        if "ai_config" in config and 'ai' in self.controllers:
            ai_config = config["ai_config"]
            self.controllers['ai'].view.load_config(ai_config)
            # 触发供应商切换以更新型号列表
            if hasattr(self.controllers['ai'], '_on_provider_changed'):
                self.controllers['ai']._on_provider_changed()
        
        try:
            self.cfg_service.save()
        except Exception as e:
            print(f"[MainController] ⚠️ 预设保存失败: {e}")
        self.view.append_log(f"预设已加载: {preset_name}", "SUCCESS")
    
    def _on_preset_selected(self, event=None):
        """预设选择事件"""
        preset_name = self.view.preset_menu.get()
        if preset_name:
            self.load_preset(preset_name)
    
    def _list_presets(self) -> List[str]:
        """列出所有预设"""
        preset_dir = Path("config/presets")
        if not preset_dir.exists():
            return []
        
        presets = [f.stem for f in preset_dir.glob("*.json")]
        return sorted(presets)
    
    def _refresh_preset_menu(self):
        """刷新预设菜单"""
        try:
            presets = self._list_presets()
            
            if hasattr(self.view, 'preset_menu'):
                menu = self.view.preset_menu
                if presets:
                    menu['values'] = presets
                    menu.set('')
                else:
                    menu['values'] = []
                    menu.set('')
        except Exception as e:
            print(f"[ERROR] 刷新预设菜单失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        # 清理所有子控制器
        for ctrl in self.controllers.values():
            if hasattr(ctrl, 'cleanup'):
                ctrl.cleanup()
        
        # 保存配置（统一入口）
        try:
            self.cfg_service.save()
        except Exception as e:
            print(f"[MainController] ⚠️ 退出时保存配置失败: {e}")


__all__ = ['MainController']

