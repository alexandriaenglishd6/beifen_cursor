# -*- coding: utf-8 -*-
"""
订阅面板视图 - 纯UI
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from typing import List, Dict, Optional
from gui.views.base_view import BaseView
from ui_components import Accordion


class SubscriptionPanel(BaseView):
    """
    订阅面板
    
    职责：
    1. 展示订阅列表
    2. 提供订阅管理按钮
    3. 显示/编辑订阅对话框
    """
    
    def _build_ui(self):
        """构建UI"""
        # 创建手风琴（懒加载模式，默认折叠）
        self.accordion = Accordion(
            parent=self,
            title="📅 订阅管理",
            expanded=False,  # 默认折叠，实现懒加载
            lazy_load=True,
            lazy_load_callback=self._build_content
        )
        self.accordion.pack(fill='both', expand=True)
    
    def _build_content(self, content):
        """构建内容（懒加载回调）"""
        # 统计信息区
        stats_frame = tk.Frame(content)
        stats_frame.pack(fill='x', pady=(0, 10))
        
        self.lbl_stats = ttk.Label(
            stats_frame, 
            text="总计: 0 | 启用: 0 | 禁用: 0",
            font=("Segoe UI", 10, "bold"),
            foreground="#64748b"
        )
        self.lbl_stats.pack(side='left')
        
        # 按钮区（第一行：主要操作）
        btn_frame = tk.Frame(content)
        btn_frame.pack(fill='x', pady=(0, 5))
        
        self.btn_add = ttk.Button(btn_frame, text="➕ 添加", width=10)
        self.btn_add.pack(side='left', padx=2)
        
        self.btn_edit = ttk.Button(btn_frame, text="✏️ 编辑", width=10)
        self.btn_edit.pack(side='left', padx=2)
        
        self.btn_delete = ttk.Button(btn_frame, text="🗑️ 删除", width=10)
        self.btn_delete.pack(side='left', padx=2)
        
        self.btn_toggle = ttk.Button(btn_frame, text="⏯️ 启用/禁用", width=12)
        self.btn_toggle.pack(side='left', padx=2)
        
        # 导入/导出按钮（第二行）
        io_frame = tk.Frame(content)
        io_frame.pack(fill='x', pady=(5, 5))
        
        self.btn_import = ttk.Button(io_frame, text="📥 导入", width=10)
        self.btn_import.pack(side='left', padx=2)
        
        self.btn_export = ttk.Button(io_frame, text="📤 导出", width=10)
        self.btn_export.pack(side='left', padx=2)
        
        self.btn_refresh = ttk.Button(io_frame, text="🔄 刷新", width=10)
        self.btn_refresh.pack(side='left', padx=2)
        
        # 订阅列表（TreeView）
        self._build_subscription_table(content)
    
    def _build_subscription_table(self, parent):
        """构建订阅列表表格"""
        # 表格容器
        table_frame = tk.Frame(parent)
        table_frame.pack(fill='both', expand=True, pady=5)
        
        # TreeView
        columns = ("id", "name", "url", "interval", "status", "last_check")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)
        
        # 列标题
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="名称")
        self.tree.heading("url", text="URL")
        self.tree.heading("interval", text="检查间隔")
        self.tree.heading("status", text="状态")
        self.tree.heading("last_check", text="最后检查")
        
        # 列宽
        self.tree.column("id", width=60, anchor="center")
        self.tree.column("name", width=150)
        self.tree.column("url", width=250)
        self.tree.column("interval", width=80, anchor="center")
        self.tree.column("status", width=80, anchor="center")
        self.tree.column("last_check", width=120, anchor="center")
        
        # 滚动条
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
    
    def update_subscription_list(self, subscriptions: List[Dict]):
        """
        更新订阅列表
        
        Args:
            subscriptions: 订阅列表
        """
        # 清空现有数据
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 统计信息
        total = len(subscriptions)
        enabled_count = sum(1 for sub in subscriptions if sub.get("enabled", True))
        disabled_count = total - enabled_count
        
        # 更新统计信息标签
        if hasattr(self, 'lbl_stats'):
            self.lbl_stats.config(
                text=f"总计: {total} | 启用: {enabled_count} | 禁用: {disabled_count}"
            )
        
        # 添加新数据
        for sub in subscriptions:
            enabled = sub.get("enabled", True)
            status = "✅ 启用" if enabled else "⏸️ 禁用"
            last_check = sub.get("last_check") or "-"
            
            # 格式化URL显示（如果太长则截断）
            url = sub.get("url", "")
            if len(url) > 40:
                url = url[:40] + "..."
            
            values = (
                sub.get("id", ""),
                sub.get("name", ""),
                url,
                sub.get("check_interval", "daily"),
                status,
                last_check
            )
            self.tree.insert("", "end", values=values)
    
    def get_selected_subscription(self, service=None) -> Optional[Dict]:
        """
        获取选中的订阅
        
        Args:
            service: 订阅服务实例（可选，如果提供则使用，否则创建新实例）
        
        Returns:
            选中的订阅，如果没有选中则返回None
        """
        selection = self.tree.selection()
        if not selection:
            return None
        
        # 获取值
        values = self.tree.item(selection[0])["values"]
        if not values or len(values) < 5:
            return None
        
        # 获取完整订阅数据（从服务层）
        sub_id = values[0]
        
        # 如果提供了服务实例，使用它；否则创建新实例
        if service:
            return service.get_subscription(sub_id)
        
        # 备用方案：从配置服务读取
        try:
            from services.config_service import get_config_service
            config_service = get_config_service()
            config = config_service.get_all()
            from services.subscription_service import SubscriptionService
            service = SubscriptionService(config)
            return service.get_subscription(sub_id)
        except Exception as e:
            print(f"[SubscriptionPanel] 获取订阅失败: {e}")
            return None
    
    def show_add_dialog(self) -> Optional[Dict]:
        """
        显示添加订阅对话框
        
        Returns:
            订阅数据，如果取消则返回None
        """
        from gui.views.dialogs import SubscriptionDialog
        
        dialog = SubscriptionDialog(self)
        self.wait_window(dialog)
        return dialog.result
    
    def show_edit_dialog(self, subscription: Dict) -> Optional[Dict]:
        """
        显示编辑订阅对话框
        
        Args:
            subscription: 订阅对象
        
        Returns:
            订阅数据，如果取消则返回None
        """
        from gui.views.dialogs import SubscriptionDialog
        
        dialog = SubscriptionDialog(self, subscription)
        self.wait_window(dialog)
        return dialog.result
    
    def confirm_delete(self, sub_name: str) -> bool:
        """
        确认删除
        
        Args:
            sub_name: 订阅名称
        
        Returns:
            是否确认删除
        """
        return messagebox.askyesno("确认删除", f"确定要删除订阅 '{sub_name}' 吗？", parent=self)
    
    def select_import_file(self) -> Optional[str]:
        """
        选择导入文件
        
        Returns:
            文件路径，如果取消则返回None
        """
        return filedialog.askopenfilename(
            title="选择订阅文件",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            parent=self
        )
    
    def select_export_file(self) -> Optional[str]:
        """
        选择导出文件（自动生成默认文件名）
        
        Returns:
            文件路径，如果取消则返回None
        """
        from datetime import datetime
        from pathlib import Path
        
        # 自动生成文件名（带时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"subscriptions_{timestamp}.json"
        
        # 默认保存到out目录
        default_dir = Path("out")
        default_dir.mkdir(parents=True, exist_ok=True)
        default_path = default_dir / default_filename
        
        file_path = filedialog.asksaveasfilename(
            title="保存订阅文件",
            defaultextension=".json",
            initialfile=default_filename,
            initialdir=str(default_dir),
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            parent=self
        )
        
        # 如果用户选择了路径，确保目录存在
        if file_path:
            export_path = Path(file_path)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            return str(export_path)
        
        return None
    
    def show_error(self, message: str):
        """显示错误"""
        messagebox.showerror("错误", message, parent=self)
    
    def show_info(self, message: str):
        """显示信息"""
        messagebox.showinfo("提示", message, parent=self)


__all__ = ['SubscriptionPanel']

