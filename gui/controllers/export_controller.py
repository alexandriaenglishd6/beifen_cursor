# -*- coding: utf-8 -*-
"""
导出控制器 - 处理导出操作
"""
from pathlib import Path
from typing import List, Dict
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
from datetime import datetime
from gui.controllers.base_controller import BaseController
from events.event_bus import EventType, Event
from services.export_service import ExportService
from history_manager import HistoryManager


class ExportController(BaseController):
    """
    导出控制器
    
    职责：
    1. 处理导出操作
    2. 调用服务层执行导出
    3. 发布事件通知其他模块
    """
    
    def __init__(self, config: dict):
        """
        初始化
        
        Args:
            config: 全局配置
        """
        self.config = config
        self.service = ExportService()
        super().__init__()
    
    def _setup_event_listeners(self):
        """设置事件监听"""
        # 导出功能主要通过其他控制器的按钮调用，不需要监听事件
        pass
    
    def export_scheduler_jobs(self, jobs: List[Dict], format: str = "excel"):
        """
        导出调度任务
        
        Args:
            jobs: 任务列表
            format: 导出格式
        """
        try:
            # 选择保存位置
            filename = f"scheduler_jobs.{format if format != 'excel' else 'xlsx'}"
            file_path = filedialog.asksaveasfilename(
                defaultextension=f".{format if format != 'excel' else 'xlsx'}",
                filetypes=[
                    ("Excel files", "*.xlsx"),
                    ("CSV files", "*.csv"),
                    ("JSON files", "*.json"),
                    ("Markdown files", "*.md"),
                    ("All files", "*.*")
                ],
                initialfile=filename
            )
            
            if not file_path:
                return
            
            # 执行导出
            output_path = self.service.export_scheduler_jobs(
                jobs=jobs,
                format=format,
                output_path=Path(file_path)
            )
            
            # 发布事件
            self.event_bus.publish(Event(
                EventType.EXPORT_COMPLETED,
                {"type": "scheduler_jobs", "path": str(output_path)}
            ))
            
            self._log(f"调度任务已导出: {output_path}", "SUCCESS")
            messagebox.showinfo("导出成功", f"调度任务已导出到:\n{output_path}")
            
        except Exception as e:
            self._log(f"导出失败: {e}", "ERROR")
            messagebox.showerror("导出失败", f"导出调度任务时出错:\n{e}")
            self.event_bus.publish(Event(
                EventType.EXPORT_FAILED,
                {"type": "scheduler_jobs", "reason": str(e)}
            ))
    
    def export_subscriptions(self, subscriptions: List[Dict], format: str = "excel"):
        """
        导出订阅列表
        
        Args:
            subscriptions: 订阅列表
            format: 导出格式
        """
        try:
            filename = f"subscriptions.{format if format != 'excel' else 'xlsx'}"
            file_path = filedialog.asksaveasfilename(
                defaultextension=f".{format if format != 'excel' else 'xlsx'}",
                filetypes=[
                    ("Excel files", "*.xlsx"),
                    ("CSV files", "*.csv"),
                    ("JSON files", "*.json"),
                    ("Markdown files", "*.md"),
                    ("All files", "*.*")
                ],
                initialfile=filename
            )
            
            if not file_path:
                return
            
            output_path = self.service.export_subscriptions(
                subscriptions=subscriptions,
                format=format,
                output_path=Path(file_path)
            )
            
            self.event_bus.publish(Event(
                EventType.EXPORT_COMPLETED,
                {"type": "subscriptions", "path": str(output_path)}
            ))
            
            self._log(f"订阅列表已导出: {output_path}", "SUCCESS")
            messagebox.showinfo("导出成功", f"订阅列表已导出到:\n{output_path}")
            
        except Exception as e:
            self._log(f"导出失败: {e}", "ERROR")
            messagebox.showerror("导出失败", f"导出订阅列表时出错:\n{e}")
            self.event_bus.publish(Event(
                EventType.EXPORT_FAILED,
                {"type": "subscriptions", "reason": str(e)}
            ))
    
    def export_logs(self, log_content: str, format: str = "txt"):
        """
        导出日志内容
        
        Args:
            log_content: 日志文本内容
            format: 导出格式
        """
        try:
            filename = f"logs.{format}"
            file_path = filedialog.asksaveasfilename(
                defaultextension=f".{format}",
                filetypes=[
                    ("Text files", "*.txt"),
                    ("Markdown files", "*.md"),
                    ("All files", "*.*")
                ],
                initialfile=filename
            )
            
            if not file_path:
                return
            
            output_path = self.service.export_logs(
                log_content=log_content,
                format=format,
                output_path=Path(file_path)
            )
            
            self.event_bus.publish(Event(
                EventType.EXPORT_COMPLETED,
                {"type": "logs", "path": str(output_path)}
            ))
            
            self._log(f"日志已导出: {output_path}", "SUCCESS")
            messagebox.showinfo("导出成功", f"日志已导出到:\n{output_path}")
            
        except Exception as e:
            self._log(f"导出失败: {e}", "ERROR")
            messagebox.showerror("导出失败", f"导出日志时出错:\n{e}")
            self.event_bus.publish(Event(
                EventType.EXPORT_FAILED,
                {"type": "logs", "reason": str(e)}
            ))
    
    def view_history(self, root_window=None):
        """
        查看下载历史记录
        
        打开一个对话框显示下载历史，支持搜索和过滤
        
        Args:
            root_window: 根窗口（Tk实例），如果为None则尝试自动获取
        """
        try:
            # 获取输出目录
            out_root = self.config.get("run", {}).get("output_root", "out")
            history_mgr = HistoryManager(out_root=out_root)
            
            # 获取根窗口
            if root_window is None:
                # 尝试从事件总线获取（如果设置了）
                try:
                    root_window = tk._default_root
                    if root_window is None:
                        # 如果仍然为None，创建一个临时窗口
                        import tkinter as tk_temp
                        root_window = tk_temp._default_root
                except:
                    pass
            
            if root_window is None:
                self._log("无法获取根窗口，无法打开历史记录对话框", "ERROR")
                messagebox.showerror("错误", "无法打开历史记录对话框：找不到根窗口")
                return
            
            # 创建对话框
            dialog = tk.Toplevel(root_window)
            dialog.title("📜 下载历史记录")
            dialog.geometry("1200x700")
            dialog.transient(root_window)
            
            # 顶部工具栏
            toolbar = ttk.Frame(dialog)
            toolbar.pack(fill='x', padx=10, pady=10)
            
            # 搜索框
            ttk.Label(toolbar, text="搜索:").pack(side='left', padx=(0,5))
            search_var = tk.StringVar()
            search_entry = ttk.Entry(toolbar, textvariable=search_var, width=30)
            search_entry.pack(side='left', padx=(0,10))
            
            # 状态过滤
            ttk.Label(toolbar, text="状态:").pack(side='left', padx=(0,5))
            status_var = tk.StringVar(value="全部")
            status_combo = ttk.Combobox(toolbar, textvariable=status_var, width=12, 
                                       values=["全部", "成功", "失败", "无字幕", "跳过"], state="readonly")
            status_combo.pack(side='left', padx=(0,10))
            
            # 刷新按钮
            def refresh_history():
                keyword = search_var.get().strip()
                status = status_var.get()
                
                # 状态映射
                status_map = {
                    "全部": None,
                    "成功": "ok",
                    "失败": "error",
                    "无字幕": "no_subs",
                    "跳过": "skipped"
                }
                
                # 获取历史记录
                if keyword:
                    records = history_mgr.search_history(keyword, limit=500)
                else:
                    records = history_mgr.get_all_history(limit=500, status_filter=status_map[status])
                
                # 更新表格
                for item in table.get_children():
                    table.delete(item)
                
                for record in records:
                    status_text = {
                        "ok": "✅ 成功",
                        "error": "❌ 失败",
                        "no_subs": "⚠️ 无字幕",
                        "skipped": "⏭️ 跳过"
                    }.get(record.get('status', ''), record.get('status', ''))
                    
                    ts = record.get('ts', '')
                    if ts:
                        try:
                            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            ts_display = dt.strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            ts_display = ts[:19] if len(ts) > 19 else ts
                    else:
                        ts_display = "-"
                    
                    title = record.get('title', '')
                    title_display = title[:50] + "..." if len(title) > 50 else title
                    
                    channel = record.get('channel', '')
                    channel_display = channel[:30] + "..." if len(channel) > 30 else channel
                    
                    langs = ", ".join(record.get('langs', []))
                    
                    table.insert("", "end", values=(
                        ts_display,
                        title_display,
                        channel_display,
                        status_text,
                        langs,
                        record.get('run_dir', '')
                    ))
            
            ttk.Button(toolbar, text="🔄 刷新", command=refresh_history).pack(side='left', padx=(0,5))
            ttk.Button(toolbar, text="📊 统计", command=lambda: self._show_history_stats(history_mgr)).pack(side='left')
            
            # 表格
            table_frame = ttk.Frame(dialog)
            table_frame.pack(fill='both', expand=True, padx=10, pady=(0,10))
            
            columns = ("时间", "标题", "频道", "状态", "语言", "运行目录")
            table = ttk.Treeview(table_frame, columns=columns, show="headings", height=20)
            
            for col in columns:
                table.heading(col, text=col)
                table.column(col, width=150 if col == "时间" else 200 if col == "标题" else 120)
            
            # 滚动条
            scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
            table.configure(yscrollcommand=scrollbar.set)
            
            table.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # 绑定搜索
            search_entry.bind('<Return>', lambda e: refresh_history())
            status_combo.bind('<<ComboboxSelected>>', lambda e: refresh_history())
            
            # 初始加载
            refresh_history()
            
            self._log("历史记录查看窗口已打开", "INFO")
            
        except Exception as e:
            self._log(f"查看历史记录失败: {e}", "ERROR")
            messagebox.showerror("错误", f"查看历史记录时出错:\n{e}")
            import traceback
            traceback.print_exc()
    
    def _show_history_stats(self, history_mgr: HistoryManager):
        """显示历史统计信息"""
        try:
            stats = history_mgr.get_statistics()
            
            stats_text = f"""下载历史统计

总计: {stats['total']}
成功: {stats['ok']}
失败: {stats['error']}
无字幕: {stats['no_subs']}
跳过: {stats['skipped']}

频道数: {stats['channels']}
语言: {', '.join(list(stats['languages'].keys())[:10])}
"""
            
            messagebox.showinfo("历史统计", stats_text)
        except Exception as e:
            self._log(f"获取统计信息失败: {e}", "ERROR")
            messagebox.showerror("错误", f"获取统计信息时出错:\n{e}")


__all__ = ['ExportController']

