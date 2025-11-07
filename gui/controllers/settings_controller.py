# -*- coding: utf-8 -*-
"""
设置控制器 - 连接视图和配置管理
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from tkinter import filedialog
from pathlib import Path
from gui.controllers.base_controller import BaseController
from events.event_bus import EventType, Event

if TYPE_CHECKING:
    from gui.views.settings_panel import SettingsPanel


class SettingsController(BaseController):
    """
    设置控制器
    
    职责：
    1. 处理高级设置
    2. 管理配置持久化
    3. 处理文件选择等操作
    """
    
    def __init__(self, view: SettingsPanel, config: dict):
        """
        初始化
        
        Args:
            view: 设置面板视图
            config: 全局配置
        """
        self.view = view
        self.config = config
        
        super().__init__()
        
        # 统一初始化顺序由 InitializationManager 保证，这里同步初始化
        self._setup_button_bindings()
        self.load_config()
        self._setup_auto_save()
    
    def _setup_button_bindings(self):
        """设置按钮绑定（延迟执行，确保懒加载内容已创建）"""
        # 确保内容已加载（如果是懒加载模式）
        if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
            # 触发懒加载（如果尚未加载）
            self.view.accordion.get_content_frame()
        
        # 绑定按钮事件
        if hasattr(self.view, 'btn_browse_cookie'):
            self.view.btn_browse_cookie.config(command=self.browse_cookie_file)
        # 若未存在，InitializationManager 已确保UI创建，这里不再重试
    
    def _setup_event_listeners(self):
        """设置事件监听"""
        # 监听主题变化
        self.event_bus.subscribe(EventType.THEME_CHANGED, self._on_theme_changed)
        # 监听配置保存事件
        self.event_bus.subscribe(EventType.CONFIG_SAVED, self._on_config_saved)
    
    def browse_cookie_file(self):
        """浏览Cookie文件"""
        file_path = filedialog.askopenfilename(
            title="选择Cookie文件",
            filetypes=[
                ("Cookie files", "*.txt"),
                ("All files", "*.*")
            ]
        )
        
        if file_path:
            # 验证路径是文件而不是目录
            from pathlib import Path
            path_obj = Path(file_path)
            if path_obj.is_dir():
                self._log(f"错误：选择的是目录而不是文件: {file_path}", "ERROR")
                return
            
            if not path_obj.exists():
                self._log(f"错误：文件不存在: {file_path}", "ERROR")
                return
            
            print(f"[SettingsController.browse_cookie_file] 选择的文件路径:")
            print(f"  - 完整路径: {file_path}")
            print(f"  - 路径长度: {len(file_path)}")
            
            # 设置到UI
            self.view.ent_cookie.delete(0, "end")
            self.view.ent_cookie.insert(0, str(file_path))
            
            # 立即验证UI中的值
            ui_value = self.view.ent_cookie.get()
            print(f"[SettingsController.browse_cookie_file] UI中的值:")
            print(f"  - UI值: {ui_value}")
            print(f"  - UI值长度: {len(ui_value)}")
            
            if ui_value != file_path:
                print(f"[SettingsController.browse_cookie_file] ⚠️ UI中的值与选择的值不一致！")
                print(f"  - 选择的值: {file_path}")
                print(f"  - UI值: {ui_value}")
                # 尝试重新设置
                self.view.ent_cookie.delete(0, "end")
                self.view.ent_cookie.insert(0, str(file_path))
                ui_value_retry = self.view.ent_cookie.get()
                print(f"  - 重试后UI值: {ui_value_retry}")
                print(f"  - 重试后UI值长度: {len(ui_value_retry)}")
            
            # 使用简短路径显示，避免日志过长
            from pathlib import Path
            path_obj = Path(file_path)
            display_path = path_obj.name if len(file_path) > 60 else file_path
            self._log(f"已选择Cookie文件: {display_path}")
            # 立即触发保存
            self._on_config_changed()
    
    def get_advanced_config(self) -> dict:
        """
        获取高级配置
        
        Returns:
            配置字典
        """
        return self.view.get_config()
    
    def save_config(self):
        """保存配置"""
        try:
            from services.config_service import get_config_service
            config_service = get_config_service()
            
            # 获取网络配置
            network_config = self.view.get_config()
            
            # 保存网络配置
            config_service.save_network_config(network_config)
            config_service.save()
            
            # 发布事件
            self.event_bus.publish(Event(
                EventType.CONFIG_SAVED,
                {"config": network_config}
            ))
            
            self._log("配置已保存", "SUCCESS")
            
        except Exception as e:
            self._log(f"保存配置失败: {e}", "ERROR")
            self.view.show_error(f"保存配置失败: {e}")
    
    def load_config(self):
        """加载保存的配置到UI"""
        try:
            # 确保内容已加载（如果是懒加载模式）
            if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
                # 触发懒加载（如果尚未加载）
                self.view.accordion.get_content_frame()
            
            from services.config_service import get_config_service
            config_service = get_config_service()
            config = config_service.load_network_config()
            print(f"[SettingsController] 加载网络配置:")
            print(f"  - proxy_text长度: {len(config.get('proxy_text', ''))}")
            cookiefile = config.get('cookiefile', '')
            print(f"  - cookiefile完整路径: {cookiefile}")
            print(f"  - cookiefile长度: {len(cookiefile)}")
            print(f"  - user_agent长度: {len(config.get('user_agent', ''))}")
            print(f"  - timeout: {config.get('timeout')}")
            print(f"  - retry_times: {config.get('retry_times')}")
            self.view.load_config(config)
            print(f"[SettingsController] ✓ 网络配置已加载到UI")
            
            # 验证UI中的值
            ui_cookie = self.view.ent_cookie.get()
            print(f"[SettingsController] 验证UI中的cookiefile:")
            print(f"  - UI中的值: {ui_cookie}")
            print(f"  - UI中的值长度: {len(ui_cookie)}")
            if ui_cookie != cookiefile:
                print(f"[SettingsController] ⚠️ UI中的值与配置不一致！")
                print(f"  - 配置值: {cookiefile}")
                print(f"  - UI值: {ui_cookie}")
        except Exception as e:
            print(f"[SettingsController] ✗ 加载配置失败: {e}")
            import traceback
            traceback.print_exc()
            # 不再进行延迟重试，交由初始化流程保证
    
    def _setup_auto_save(self):
        """设置自动保存机制（延迟保存）"""
        self._auto_save_job = None
        
        # 获取root窗口
        try:
            root = self.view.winfo_toplevel()
        except:
            root = self.view.master
        
        # 检查必要的控件是否存在
        if not hasattr(self.view, 'txt_proxy') or not hasattr(self.view, 'ent_user_agent'):
            print("[SettingsController] 警告: 必要控件缺失")
            return
        
        print("[SettingsController] 开始设置自动保存绑定")
        
        def delayed_save():
            """延迟保存函数"""
            if self._auto_save_job:
                try:
                    root.after_cancel(self._auto_save_job)
                except:
                    pass
            
            # 延迟500ms保存，避免频繁写入
            self._auto_save_job = root.after(500, self._on_config_changed)
        
        # 绑定代理输入框变化事件（Text控件）
        self.view.txt_proxy.bind('<KeyRelease>', lambda e: delayed_save())
        self.view.txt_proxy.bind('<FocusOut>', lambda e: self._on_config_changed())
        print("[SettingsController] ✓ 已绑定 txt_proxy 事件")
        
        # 绑定Cookie输入框变化事件
        self.view.ent_cookie.bind('<KeyRelease>', lambda e: delayed_save())
        self.view.ent_cookie.bind('<FocusOut>', lambda e: self._on_config_changed())
        print("[SettingsController] ✓ 已绑定 ent_cookie 事件")
        
        # 绑定User-Agent输入框变化事件
        self.view.ent_user_agent.bind('<KeyRelease>', lambda e: delayed_save())
        self.view.ent_user_agent.bind('<FocusOut>', lambda e: self._on_config_changed())
        print("[SettingsController] ✓ 已绑定 ent_user_agent 事件")
        
        # 绑定其他选项变化事件
        for widget in [self.view.spin_timeout, self.view.spin_retry]:
            widget.bind('<ButtonRelease-1>', lambda e: delayed_save())
            widget.bind('<KeyRelease>', lambda e: delayed_save())
            widget.bind('<FocusOut>', lambda e: self._on_config_changed())
        
        # 绑定复选框变化事件（注意：变量名与settings_panel中一致）
        checkbox_vars = []
        if hasattr(self.view, 'var_verify_ssl'):
            checkbox_vars.append(self.view.var_verify_ssl)
        if hasattr(self.view, 'var_follow_redirect'):
            checkbox_vars.append(self.view.var_follow_redirect)
        if hasattr(self.view, 'var_debug'):
            checkbox_vars.append(self.view.var_debug)
        if hasattr(self.view, 'var_save_history'):
            checkbox_vars.append(self.view.var_save_history)
        
        for var in checkbox_vars:
            var.trace_add('write', lambda *args: delayed_save())
        
        print("[SettingsController] ✓ 自动保存绑定完成")
    
    def _on_config_changed(self):
        """配置变化时自动保存（延迟保存）"""
        try:
            from services.config_service import get_config_service
            config_service = get_config_service()
            
            # 获取当前网络配置（使用宽松模式，保留输入过程中的不完整格式）
            network_config = self.view.get_config(strict_validation=False)
            
            # 打印调试信息
            proxy_text = network_config.get("proxy_text", "")
            user_agent = network_config.get("user_agent", "")
            timeout = network_config.get("timeout", 30)
            retry_times = network_config.get("retry_times", 2)
            verify_ssl = network_config.get("verify_ssl", True)
            follow_redirects = network_config.get("follow_redirects", True)
            debug = network_config.get("debug", False)
            save_history = network_config.get("save_history", True)
            
            cookiefile = network_config.get('cookiefile', '')
            print(f"[SettingsController] 自动保存网络配置（宽松模式）:")
            print(f"  - proxy_text长度: {len(proxy_text)}, 前50字符: {proxy_text[:50] if proxy_text else '(空)'}")
            print(f"  - cookiefile完整路径: {cookiefile}")
            print(f"  - cookiefile长度: {len(cookiefile)}")
            print(f"  - user_agent长度: {len(user_agent)}, 前50字符: {user_agent[:50] if user_agent else '(空)'}")
            print(f"  - timeout: {timeout}, retry_times: {retry_times}")
            print(f"  - verify_ssl: {verify_ssl}, follow_redirects: {follow_redirects}")
            print(f"  - debug: {debug}, save_history: {save_history}")
            
            # 保存网络配置
            config_service.save_network_config(network_config)
            save_result = config_service.save()
            
            if save_result:
                # 验证保存结果（使用宽松模式读取）
                saved_config = config_service.load_network_config()
                saved_proxy = saved_config.get("proxy_text", "")
                saved_cookie = saved_config.get("cookiefile", "")
                saved_ua = saved_config.get("user_agent", "")
                saved_timeout = saved_config.get("timeout", 30)
                saved_retry = saved_config.get("retry_times", 2)
                saved_verify_ssl = saved_config.get("verify_ssl", True)
                saved_follow_redirects = saved_config.get("follow_redirects", True)
                
                print(f"[SettingsController] ✓ 保存后验证:")
                print(f"  - proxy_text长度: {len(saved_proxy)}, 前50字符: {saved_proxy[:50] if saved_proxy else '(空)'}")
                print(f"  - cookiefile完整路径: {saved_cookie}")
                print(f"  - cookiefile长度: {len(saved_cookie)}")
                print(f"  - user_agent长度: {len(saved_ua)}, 前50字符: {saved_ua[:50] if saved_ua else '(空)'}")
                print(f"  - timeout: {saved_timeout}, retry_times: {saved_retry}")
                print(f"  - verify_ssl: {saved_verify_ssl}, follow_redirects: {saved_follow_redirects}")
                print(f"[SettingsController] ✓ 配置已自动保存成功")
            else:
                print(f"[SettingsController] ✗ 配置保存失败（save()返回False）")
        except Exception as e:
            # 自动保存失败不阻塞，但打印错误信息
            import traceback
            print(f"[SettingsController] ✗ 自动保存失败: {e}")
            traceback.print_exc()
    
    def _on_config_saved(self, event: Event):
        """配置保存事件处理"""
        # 可以在这里更新UI或执行其他操作
        pass
    
    def _on_theme_changed(self, event: Event):
        """
        主题变化处理
        
        Args:
            event: 事件对象
        """
        theme = event.data.get("theme")
        self.view.update_theme(theme)


__all__ = ['SettingsController']

