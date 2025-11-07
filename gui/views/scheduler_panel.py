# -*- coding: utf-8 -*-
"""
调度器面板视图 - 纯UI
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import List, Optional
from gui.views.base_view import BaseView
from ui_components import Accordion
from gui_models import SchedulerJobDisplay


class SchedulerPanel(BaseView):
    """
    调度器面板
    
    职责：
    1. 展示调度任务列表
    2. 提供任务管理按钮
    3. 显示/编辑任务对话框
    """
    
    def _build_ui(self):
        """构建UI"""
        # 创建手风琴（懒加载模式，默认折叠）
        self.accordion = Accordion(
            parent=self,
            title="⏰ 调度中心",
            expanded=False,  # 默认折叠，实现懒加载
            lazy_load=True,
            lazy_load_callback=self._build_content
        )
        self.accordion.pack(fill='both', expand=True)
    
    def _build_content(self, content):
        """构建内容（懒加载回调）"""
        # 状态栏（顶部）
        status_frame = tk.Frame(content)
        status_frame.pack(fill='x', pady=(0, 10))
        
        # 状态信息（左侧）
        status_left = tk.Frame(status_frame)
        status_left.pack(side='left', fill='x', expand=True)
        
        # 运行状态
        self.lbl_status_label = ttk.Label(status_left, text="状态:", font=("Segoe UI", 10, "bold"))
        self.lbl_status_label.pack(side='left', padx=(0, 5))
        
        self.lbl_status = ttk.Label(
            status_left, 
            text="🔴 已停止", 
            font=("Segoe UI", 10, "bold"),
            foreground="#ef4444"
        )
        self.lbl_status.pack(side='left', padx=(0, 15))
        
        # 任务执行状态（独立显示）
        self.lbl_task_status = ttk.Label(
            status_left,
            text="",
            font=("Segoe UI", 10),
            foreground="#64748b"
        )
        self.lbl_task_status.pack(side='left', padx=(0, 15))
        
        # 下次执行倒计时
        self.lbl_next_label = ttk.Label(status_left, text="下次执行:", font=("Segoe UI", 10, "bold"))
        self.lbl_next_label.pack(side='left', padx=(0, 5))
        
        self.lbl_next_time = ttk.Label(
            status_left, 
            text="--:--", 
            font=("Segoe UI", 10),
            foreground="#64748b"
        )
        self.lbl_next_time.pack(side='left')
        
        # 控制按钮（右侧）
        status_right = tk.Frame(status_frame)
        status_right.pack(side='right')
        
        self.btn_start = ttk.Button(status_right, text="🚀 启动", width=10)
        self.btn_start.pack(side='left', padx=2)
        
        self.btn_stop = ttk.Button(status_right, text="⏹️ 停止", width=10)
        self.btn_stop.pack(side='left', padx=2)
        self.btn_stop.config(state='disabled')  # 初始状态：停止按钮禁用
        
        # 按钮区
        btn_frame = tk.Frame(content)
        btn_frame.pack(fill='x', pady=(0, 5))
        
        self.btn_add = ttk.Button(btn_frame, text="➕ 添加", width=10)
        self.btn_add.pack(side='left', padx=2)
        
        self.btn_edit = ttk.Button(btn_frame, text="✏️ 编辑", width=10)
        self.btn_edit.pack(side='left', padx=2)
        
        self.btn_delete = ttk.Button(btn_frame, text="🗑️ 删除", width=10)
        self.btn_delete.pack(side='left', padx=2)
        
        self.btn_toggle = ttk.Button(btn_frame, text="⏯️ 启用/暂停", width=12)
        self.btn_toggle.pack(side='left', padx=2)
        
        self.btn_run_once = ttk.Button(btn_frame, text="▶️ 运行一次", width=12)
        self.btn_run_once.pack(side='left', padx=2)
        
        self.btn_refresh = ttk.Button(btn_frame, text="🔄 刷新", width=10)
        self.btn_refresh.pack(side='left', padx=2)
        
        # 任务列表（TreeView）
        self._build_task_table(content)
        
        # 初始化状态更新定时器
        self._status_update_job = None
    
    def _build_task_table(self, parent):
        """构建任务列表表格"""
        # 表格容器
        table_frame = tk.Frame(parent)
        table_frame.pack(fill='both', expand=True, pady=5)
        
        # TreeView
        columns = ("id", "name", "frequency", "next_run", "status", "prev_end")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)
        
        # 列标题
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="任务名称")
        self.tree.heading("frequency", text="频率")
        self.tree.heading("next_run", text="下次运行")
        self.tree.heading("status", text="状态")
        self.tree.heading("prev_end", text="上次结束")
        
        # 列宽
        self.tree.column("id", width=50, anchor="center")
        self.tree.column("name", width=200)
        self.tree.column("frequency", width=80, anchor="center")
        self.tree.column("next_run", width=120, anchor="center")
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("prev_end", width=120, anchor="center")
        
        # 滚动条
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
    
    def update_job_list(self, jobs: List[SchedulerJobDisplay]):
        """
        更新任务列表
        
        Args:
            jobs: 任务列表
        """
        # 清空现有数据
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 添加新数据
        for job in jobs:
            values = (
                job.id,
                job.name,
                job.frequency,
                job.get_next_run_display(),
                job.get_status_display(),
                job.get_prev_end_display()
            )
            self.tree.insert("", "end", values=values)
    
    def get_selected_job(self) -> Optional[SchedulerJobDisplay]:
        """
        获取选中的任务
        
        Returns:
            选中的任务，如果没有选中则返回None
        """
        selection = self.tree.selection()
        if not selection:
            return None
        
        # 获取值
        values = self.tree.item(selection[0])["values"]
        if not values or len(values) < 6:
            return None
        
        # 解析状态
        status_text = values[4] if len(values) > 4 else "✅ -"
        enabled = "✅" in status_text
        prev_status = status_text.replace("✅ ", "").replace("⏸️ ", "").strip() if status_text != "-" else None
        
        # 构建字典
        job_dict = {
            "id": str(values[0]),
            "name": values[1],
            "frequency": values[2],
            "next_run": values[3] if len(values) > 3 and values[3] != "-" else None,
            "prev_status": prev_status,
            "prev_end": values[5] if len(values) > 5 and values[5] != "-" else None,
            "enabled": enabled
        }
        
        return SchedulerJobDisplay.from_dict(job_dict)
    
    def show_add_dialog(self) -> Optional[dict]:
        """
        显示添加任务对话框
        
        Returns:
            表单数据，如果取消则返回None
        """
        from gui.views.dialogs import SchedulerJobDialog
        
        dialog = SchedulerJobDialog(self)
        self.wait_window(dialog)
        return dialog.result
    
    def show_edit_dialog(self, job) -> Optional[dict]:
        """
        显示编辑任务对话框
        
        Args:
            job: 任务对象
        
        Returns:
            表单数据，如果取消则返回None
        """
        from gui.views.dialogs import SchedulerJobDialog
        
        dialog = SchedulerJobDialog(self, job)
        self.wait_window(dialog)
        return dialog.result
    
    def confirm_delete(self, job_name: str) -> bool:
        """
        确认删除
        
        Args:
            job_name: 任务名称
        
        Returns:
            是否确认删除
        """
        return messagebox.askyesno("确认删除", f"确定要删除任务 '{job_name}' 吗？", parent=self)
    
    def show_error(self, message: str):
        """显示错误"""
        messagebox.showerror("错误", message, parent=self)
    
    def show_info(self, message: str):
        """显示信息"""
        messagebox.showinfo("提示", message, parent=self)
    
    def update_status(self, is_running: bool, next_tick_seconds: Optional[int] = None):
        """
        更新调度器状态显示
        
        Args:
            is_running: 调度器ticker是否运行中
            next_tick_seconds: 下次tick的秒数（如果运行中）
        """
        if not hasattr(self, 'lbl_status'):
            return
        
        # 强制更新按钮状态，确保与调度器运行状态一致
        if is_running:
            self.lbl_status.config(text="🟢 运行中", foreground="#10b981")
            self.btn_start.config(state='disabled')
            self.btn_stop.config(state='normal')  # 确保停止按钮可用
            
            # 更新倒计时
            if next_tick_seconds is not None:
                minutes = next_tick_seconds // 60
                seconds = next_tick_seconds % 60
                self.lbl_next_time.config(
                    text=f"{minutes:02d}:{seconds:02d}",
                    foreground="#10b981"
                )
            else:
                self.lbl_next_time.config(text="计算中...", foreground="#64748b")
        else:
            # 调度器未运行
            # 检查是否有任务在执行
            has_task_running = False
            if hasattr(self, 'lbl_task_status'):
                task_text = self.lbl_task_status.cget('text')
                has_task_running = bool(task_text and task_text.strip())
            
            if not has_task_running:
                # 没有任务在执行，显示"已停止"
                self.lbl_status.config(text="🔴 已停止", foreground="#ef4444")
            
            # 无论是否有任务在执行，都要更新按钮状态
            self.btn_start.config(state='normal')
            self.btn_stop.config(state='disabled')  # 确保停止按钮禁用
            
            # 只有在调度器运行时才显示下次执行时间
            if not is_running:
                self.lbl_next_time.config(text="--:--", foreground="#64748b")
    
    def update_task_status(self, task_name: str = None, is_running: bool = False):
        """
        更新任务执行状态显示
        
        Args:
            task_name: 任务名称（如果正在执行）
            is_running: 是否有任务正在执行
        """
        if not hasattr(self, 'lbl_task_status'):
            return
        
        if is_running and task_name:
            self.lbl_task_status.config(
                text=f"📋 执行中: {task_name}",
                foreground="#3b82f6"
            )
            # 当有任务执行时，更新调度器状态显示为"任务执行中"
            if hasattr(self, 'lbl_status'):
                self.lbl_status.config(text="🟡 任务执行中", foreground="#f59e0b")
        else:
            # 任务完成后，清除任务状态显示
            self.lbl_task_status.config(text="", foreground="#64748b")
            # 任务完成后，立即恢复调度器状态显示
            # 这里需要强制更新状态，确保状态栏正确显示
            if hasattr(self, 'lbl_status'):
                # 检查调度器是否在运行（通过按钮状态判断）
                if hasattr(self, 'btn_start') and hasattr(self, 'btn_stop'):
                    # 如果启动按钮禁用且停止按钮启用，说明调度器在运行
                    start_state = self.btn_start.cget('state')
                    stop_state = self.btn_stop.cget('state')
                    scheduler_running = (start_state == 'disabled' and stop_state == 'normal')
                    
                    # 恢复调度器状态显示
                    if scheduler_running:
                        self.lbl_status.config(text="🟢 运行中", foreground="#10b981")
                    else:
                        self.lbl_status.config(text="🔴 已停止", foreground="#ef4444")
    
    def start_status_updates(self):
        """开始状态更新（每秒更新一次）"""
        self._update_status_display()
    
    def stop_status_updates(self):
        """停止状态更新"""
        if self._status_update_job:
            root = self.winfo_toplevel()
            root.after_cancel(self._status_update_job)
            self._status_update_job = None
    
    def _update_status_display(self):
        """更新状态显示（内部方法，由控制器调用）"""
        # 这个方法会被控制器调用，实际状态由控制器提供
        # 这里只是设置定时器
        root = self.winfo_toplevel()
        self._status_update_job = root.after(1000, self._update_status_display)


__all__ = ['SchedulerPanel']

