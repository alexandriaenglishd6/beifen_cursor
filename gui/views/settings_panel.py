# -*- coding: utf-8 -*-
"""
高级设置面板视图 - 纯UI，不包含业务逻辑
"""
import tkinter as tk
from tkinter import ttk
from gui.views.base_view import BaseView
from ui_components import Accordion, ModuleTitle


class SettingsPanel(BaseView):
    """
    高级设置面板
    
    职责：
    1. 展示高级设置UI
    2. 提供配置获取接口
    3. 更新UI状态
    """
    
    def _build_ui(self):
        """构建UI"""
        # 创建手风琴（懒加载模式，默认折叠）
        self.accordion = Accordion(
            parent=self,
            title="⚙️ 高级选项",
            expanded=False,  # 默认折叠，实现懒加载
            lazy_load=True,
            lazy_load_callback=self._build_content
        )
        self.accordion.pack(fill='both', expand=True)
    
    def _build_content(self, content):
        """构建内容（懒加载回调）"""
        # === 网络配置 ===
        ModuleTitle(content, "网络配置").pack(fill='x', pady=(0, 5))
        
        # 代理设置
        proxy_hint = tk.Label(content, text="代理服务器（留空则直连，支持 http/https/socks5）",
                             font=("Segoe UI", 14))
        proxy_hint.pack(anchor='w', pady=(0, 4))
        
        proxy_frame = tk.Frame(content)
        proxy_frame.pack(fill='x', pady=(0, 10))
        
        self.txt_proxy = tk.Text(proxy_frame, height=3, font=("Consolas", 14))
        self.txt_proxy.pack(side='left', fill='both', expand=True, padx=(0, 5))
        self.txt_proxy.insert('1.0', '# 支持格式: http://ip:port, https://ip:port, socks5://user:pass@ip:port\n# 示例: http://127.0.0.1:7890')
        
        # Cookie文件
        cookie_hint = tk.Label(content, text="Cookie路径或内容（留空则跳过）\n💡 提示：使用浏览器扩展 'Get cookies.txt LOCALLY' 导出 YouTube Cookie",
                              font=("Segoe UI", 12), justify='left', fg='gray')
        cookie_hint.pack(anchor='w', pady=(0, 4))
        
        cookie_frame = tk.Frame(content)
        cookie_frame.pack(fill='x', pady=(0, 10))
        
        self.ent_cookie = ttk.Entry(cookie_frame)
        # 移除可能的长度限制，确保可以输入完整路径
        # Entry组件默认没有长度限制，但为了安全起见，我们显式设置
        self.ent_cookie.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        self.btn_browse_cookie = ttk.Button(cookie_frame, text="📁", width=3)
        self.btn_browse_cookie.pack(side='left')
        
        # User-Agent
        ua_hint = tk.Label(content, text="自定义浏览器标识（留空则使用默认）",
                          font=("Segoe UI", 14))
        ua_hint.pack(anchor='w', pady=(0, 4))
        
        self.ent_user_agent = ttk.Entry(content)
        self.ent_user_agent.insert(0, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        self.ent_user_agent.pack(fill='x', pady=(0, 10))
        
        # === 网络选项 ===
        ModuleTitle(content, "网络选项").pack(fill='x', pady=(0, 5))
        
        # 超时和重试（横置）
        net_frame = tk.Frame(content)
        net_frame.pack(fill='x', pady=(0, 5))
        
        tk.Label(net_frame, text="超时:", font=("Segoe UI", 14, "bold")).pack(
            side='left', padx=(0, 5))
        
        self.spin_timeout = ttk.Spinbox(net_frame, from_=5, to=300, width=6)
        self.spin_timeout.set(30)
        self.spin_timeout.pack(side='left', padx=(0, 5))
        
        tk.Label(net_frame, text="秒", font=("Segoe UI", 14, "bold")).pack(
            side='left', padx=(0, 15))
        
        tk.Label(net_frame, text="重试:", font=("Segoe UI", 14, "bold")).pack(
            side='left', padx=(0, 5))
        
        self.spin_retry = ttk.Spinbox(net_frame, from_=0, to=10, width=5)
        self.spin_retry.set(3)
        self.spin_retry.pack(side='left', padx=(0, 5))
        
        tk.Label(net_frame, text="次", font=("Segoe UI", 14, "bold")).pack(side='left')
        
        # SSL和重定向选项（横置）
        options_frame = tk.Frame(content)
        options_frame.pack(fill='x', pady=(0, 10))
        
        self.var_verify_ssl = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="验证SSL",
                       variable=self.var_verify_ssl).pack(side='left', padx=(0, 15))
        
        self.var_follow_redirect = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="跟随重定向",
                       variable=self.var_follow_redirect).pack(side='left')
        
        # === 其他选项 ===
        ModuleTitle(content, "其他选项").pack(fill='x', pady=(0, 5))
        
        other_frame = tk.Frame(content)
        other_frame.pack(fill='x', pady=(0, 10))
        
        self.var_debug = tk.BooleanVar(value=False)
        ttk.Checkbutton(other_frame, text="调试模式",
                       variable=self.var_debug).pack(side='left', padx=(0, 15))
        
        self.var_save_history = tk.BooleanVar(value=True)
        ttk.Checkbutton(other_frame, text="保存历史记录",
                       variable=self.var_save_history).pack(side='left')
    
    def get_config(self, strict_validation: bool = True) -> dict:
        """
        获取高级设置配置
        
        Args:
            strict_validation: 是否进行严格验证（True=过滤无效格式，False=保留原始输入）
        
        Returns:
            配置字典
        """
        # 解析代理文本（去除注释行）
        proxy_text = self.txt_proxy.get("1.0", "end-1c")
        proxy_lines_raw = [line.strip() for line in proxy_text.split('\n') 
                          if line.strip() and not line.strip().startswith('#')]
        
        if strict_validation:
            # 严格验证：验证每行代理格式，只保留有效格式
            from validators import validate_proxy
            valid_proxy_lines = []
            invalid_lines = []
            
            for line in proxy_lines_raw:
                is_valid, error_msg = validate_proxy(line)
                if is_valid:
                    valid_proxy_lines.append(line)
                else:
                    invalid_lines.append(line)
            
            # 如果有无效的代理行，打印警告
            if invalid_lines:
                print(f"[SettingsPanel] 警告：以下代理格式无效，已忽略: {invalid_lines}")
            
            proxy_text = '\n'.join(valid_proxy_lines) if valid_proxy_lines else ""
        else:
            # 宽松模式：保留所有非注释行（用于自动保存，避免输入过程中丢失内容）
            proxy_text = '\n'.join(proxy_lines_raw) if proxy_lines_raw else ""
        
        # 获取Cookie文件路径
        cookiefile = self.ent_cookie.get().strip()
        print(f"[SettingsPanel.get_config] 获取Cookie文件路径:")
        print(f"  - UI中的值: {cookiefile}")
        print(f"  - UI中的值长度: {len(cookiefile)}")
        
        return {
            "proxy_text": proxy_text,
            "cookiefile": cookiefile,
            "user_agent": self.ent_user_agent.get().strip(),
            "timeout": int(self.spin_timeout.get()),
            "retry_times": int(self.spin_retry.get()),
            "verify_ssl": self.var_verify_ssl.get(),
            "follow_redirects": self.var_follow_redirect.get(),
            "debug": self.var_debug.get(),
            "save_history": self.var_save_history.get()
        }
    
    def load_config(self, config: dict):
        """
        加载配置到UI
        
        Args:
            config: 配置字典
        """
        if not config:
            return
        
        # 代理
        if "proxy_text" in config:
            proxy_text = config.get("proxy_text", "")
            self.txt_proxy.delete("1.0", "end")
            if proxy_text:
                self.txt_proxy.insert("1.0", proxy_text)
            else:
                self.txt_proxy.insert("1.0", "# 支持格式: http://ip:port, https://ip:port, socks5://user:pass@ip:port\n# 示例: http://127.0.0.1:7890")
        
        # Cookie
        if "cookiefile" in config:
            cookiefile_value = config.get("cookiefile", "")
            print(f"[SettingsPanel.load_config] 设置Cookie文件路径:")
            print(f"  - 配置值: {cookiefile_value}")
            print(f"  - 配置值长度: {len(cookiefile_value)}")
            self.ent_cookie.delete(0, "end")
            self.ent_cookie.insert(0, cookiefile_value)
            # 验证设置后的值
            ui_value = self.ent_cookie.get()
            print(f"  - UI中的值: {ui_value}")
            print(f"  - UI中的值长度: {len(ui_value)}")
            if ui_value != cookiefile_value:
                print(f"[SettingsPanel.load_config] ⚠️ UI中的值与配置不一致！")
                print(f"  - 配置值: {cookiefile_value}")
                print(f"  - UI值: {ui_value}")
        
        # User-Agent
        if "user_agent" in config:
            ua = config.get("user_agent", "")
            self.ent_user_agent.delete(0, "end")
            if ua:
                self.ent_user_agent.insert(0, ua)
            else:
                self.ent_user_agent.insert(0, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        # 超时
        if "timeout" in config:
            timeout = config.get("timeout", 30)
            self.spin_timeout.set(str(timeout))
        
        # 重试次数
        if "retry_times" in config:
            retry = config.get("retry_times", 2)
            self.spin_retry.set(str(retry))
        
        # 选项
        if "verify_ssl" in config:
            self.var_verify_ssl.set(config.get("verify_ssl", True))
        
        if "follow_redirects" in config:
            self.var_follow_redirect.set(config.get("follow_redirects", True))
        
        if "debug" in config:
            self.var_debug.set(config.get("debug", False))
        
        if "save_history" in config:
            self.var_save_history.set(config.get("save_history", True))
    
    def show_error(self, message: str):
        """
        显示错误消息
        
        Args:
            message: 错误消息
        """
        from tkinter import messagebox
        messagebox.showerror("错误", message)


__all__ = ['SettingsPanel']

