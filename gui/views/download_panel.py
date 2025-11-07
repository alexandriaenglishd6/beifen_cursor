# -*- coding: utf-8 -*-
"""
下载面板视图 - 纯UI，不包含业务逻辑
"""
import tkinter as tk
from tkinter import ttk, messagebox
from gui.views.base_view import BaseView
from ui_components import Accordion


class DownloadPanel(BaseView):
    """
    下载配置面板
    
    职责：
    1. 展示下载配置UI
    2. 提供数据获取接口
    3. 更新UI状态
    """
    
    def _build_ui(self):
        """构建UI"""
        # 创建手风琴（下载面板默认展开，因为最常用）
        self.accordion = Accordion(
            parent=self,
            title="📥 输入源",
            expanded=True,  # 默认展开（最常用功能）
            lazy_load=False  # 立即加载（因为默认展开）
        )
        self.accordion.pack(fill='both', expand=True)
        
        # 立即构建内容（因为默认展开）
        content = self.accordion.get_content_frame()
        self._build_content(content)
    
    def _build_content(self, content):
        """构建内容"""
        # 视频链接输入
        lbl_urls = tk.Label(content, text="视频链接:", font=("Segoe UI", 14, "bold"))
        lbl_urls.pack(anchor='w', pady=(5, 2))
        
        self.txt_urls = tk.Text(content, height=5, font=("Segoe UI", 14))
        self.txt_urls.pack(fill='both', expand=True, pady=5)
        
        # 按钮区
        btn_frame = tk.Frame(content)
        btn_frame.pack(fill='x', pady=5)
        
        self.btn_import = ttk.Button(btn_frame, text="📁 导入文件")
        self.btn_import.pack(side='left', padx=5)
        
        self.btn_clear = ttk.Button(btn_frame, text="🧹 清空")
        self.btn_clear.pack(side='left', padx=5)
        
        # 批量操作按钮区
        batch_frame = tk.Frame(content)
        batch_frame.pack(fill='x', pady=(5, 0))
        
        lbl_batch = tk.Label(batch_frame, text="批量操作:", font=("Segoe UI", 12, "bold"))
        lbl_batch.pack(side='left', padx=(0, 5))
        
        self.btn_clean_invalid = ttk.Button(batch_frame, text="🔍 清理无效")
        self.btn_clean_invalid.pack(side='left', padx=2)
        
        self.btn_remove_duplicates = ttk.Button(batch_frame, text="🔄 去重")
        self.btn_remove_duplicates.pack(side='left', padx=2)
        
        self.btn_validate = ttk.Button(batch_frame, text="✓ 验证")
        self.btn_validate.pack(side='left', padx=2)
        
        # 输出目录
        dir_frame = tk.Frame(content)
        dir_frame.pack(fill='x', pady=5)
        
        lbl_output = tk.Label(dir_frame, text="输出目录:", font=("Segoe UI", 14, "bold"))
        lbl_output.pack(side='left', padx=(0, 5))
        
        self.ent_output = ttk.Entry(dir_frame, font=("Segoe UI", 14))
        self.ent_output.insert(0, "out")
        self.ent_output.pack(side='left', fill='x', expand=True, padx=5)
        
        btn_browse = ttk.Button(dir_frame, text="📁", width=3)
        btn_browse.pack(side='left')
        
        # 下载设置
        settings_frame = tk.Frame(content)
        settings_frame.pack(fill='x', pady=5)
        
        # 语言
        lbl_langs = tk.Label(settings_frame, text="语言:", font=("Segoe UI", 14, "bold"))
        lbl_langs.grid(row=0, column=0, sticky='w', padx=(0, 5))
        
        self.ent_langs = ttk.Entry(settings_frame, font=("Segoe UI", 14), width=20)
        self.ent_langs.insert(0, "zh,en")
        self.ent_langs.grid(row=0, column=1, sticky='w', padx=5)
        
        # 格式
        lbl_fmt = tk.Label(settings_frame, text="格式:", font=("Segoe UI", 14, "bold"))
        lbl_fmt.grid(row=0, column=2, sticky='w', padx=(15, 5))
        
        self.opt_fmt = ttk.Combobox(settings_frame, values=["srt", "vtt", "txt"], 
                                   state="readonly", font=("Segoe UI", 14), width=8)
        self.opt_fmt.set("srt")
        self.opt_fmt.grid(row=0, column=3, sticky='w', padx=5)
        
        # 并发数
        lbl_workers = tk.Label(settings_frame, text="并发:", font=("Segoe UI", 14, "bold"))
        lbl_workers.grid(row=1, column=0, sticky='w', padx=(0, 5), pady=(5, 0))
        
        self.spin_workers = ttk.Spinbox(settings_frame, from_=1, to=10, 
                                       font=("Segoe UI", 14), width=8)
        self.spin_workers.set("3")
        self.spin_workers.grid(row=1, column=1, sticky='w', padx=5, pady=(5, 0))
        
        # 高级选项区域（手风琴，懒加载）
        self.advanced_accordion = Accordion(
            parent=self,
            title="⚙️ 高级选项",
            expanded=False,
            lazy_load=True,
            lazy_load_callback=self._build_advanced_content
        )
        self.advanced_accordion.pack(fill='x', pady=(10, 0))
    
    def _build_advanced_content(self, advanced_content):
        """构建高级选项内容（懒加载回调）"""
        
        # 高级选项框架（两列布局）
        advanced_frame = tk.Frame(advanced_content)
        advanced_frame.pack(fill='x', padx=5, pady=5)
        
        # 左侧列：下载模式选项
        left_frame = tk.Frame(advanced_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0, 10))
        
        lbl_mode = tk.Label(left_frame, text="下载模式:", font=("Segoe UI", 12, "bold"))
        lbl_mode.pack(anchor='w', pady=(0, 5))
        
        # 双语合并
        self.var_merge_bilingual = tk.BooleanVar(value=True)
        chk_merge_bilingual = tk.Checkbutton(
            left_frame, 
            text="合并双语字幕",
            variable=self.var_merge_bilingual,
            font=("Segoe UI", 11)
        )
        chk_merge_bilingual.pack(anchor='w', pady=2)
        
        # 强制刷新
        self.var_force_refresh = tk.BooleanVar(value=False)
        chk_force_refresh = tk.Checkbutton(
            left_frame,
            text="强制刷新（忽略已下载）",
            variable=self.var_force_refresh,
            font=("Segoe UI", 11)
        )
        chk_force_refresh.pack(anchor='w', pady=2)
        
        # 增量检测
        self.var_incremental_detect = tk.BooleanVar(value=True)
        chk_incremental_detect = tk.Checkbutton(
            left_frame,
            text="启用增量检测",
            variable=self.var_incremental_detect,
            font=("Segoe UI", 11)
        )
        chk_incremental_detect.pack(anchor='w', pady=2)
        
        # 右侧列：增量选项
        right_frame = tk.Frame(advanced_frame)
        right_frame.pack(side='left', fill='both', expand=True, padx=(10, 0))
        
        lbl_incremental = tk.Label(right_frame, text="增量选项:", font=("Segoe UI", 12, "bold"))
        lbl_incremental.pack(anchor='w', pady=(0, 5))
        
        # 增量下载
        self.var_incremental_download = tk.BooleanVar(value=True)
        chk_incremental_download = tk.Checkbutton(
            right_frame,
            text="启用增量下载",
            variable=self.var_incremental_download,
            font=("Segoe UI", 11)
        )
        chk_incremental_download.pack(anchor='w', pady=2)
        
        # 提前停止（已见过）
        self.var_early_stop = tk.BooleanVar(value=True)
        chk_early_stop = tk.Checkbutton(
            right_frame,
            text="已见过提前停止",
            variable=self.var_early_stop,
            font=("Segoe UI", 11)
        )
        chk_early_stop.pack(anchor='w', pady=2)
    
    def get_urls(self) -> list[str]:
        """
        获取URL列表
        
        Returns:
            URL列表
        """
        text = self.txt_urls.get("1.0", "end-1c")
        return [line.strip() for line in text.split('\n') if line.strip()]
    
    def get_config(self) -> dict:
        """
        获取配置
        
        Returns:
            配置字典
        """
        return {
            "output_root": self.ent_output.get().strip() or "out",
            "download_langs": [l.strip() for l in self.ent_langs.get().split(",") if l.strip()],
            "download_fmt": self.opt_fmt.get(),
            "max_workers": int(self.spin_workers.get()),
            # 高级选项（如果变量存在则获取，否则使用默认值）
            "merge_bilingual": self.var_merge_bilingual.get() if hasattr(self, 'var_merge_bilingual') else True,
            "force_refresh": self.var_force_refresh.get() if hasattr(self, 'var_force_refresh') else False,
            "incremental_detect": self.var_incremental_detect.get() if hasattr(self, 'var_incremental_detect') else True,
            "incremental_download": self.var_incremental_download.get() if hasattr(self, 'var_incremental_download') else True,
            "early_stop_on_seen": self.var_early_stop.get() if hasattr(self, 'var_early_stop') else True
        }
    
    def load_config(self, config: dict):
        """
        加载配置到UI
        
        Args:
            config: 配置字典
        """
        print(f"[DownloadPanel] 开始加载配置到UI: {config}")
        if config:
            # 输出目录
            if "output_root" in config:
                output_root = config.get("output_root", "out")
                print(f"[DownloadPanel] 设置输出目录: {output_root}")
                self.ent_output.delete(0, "end")
                self.ent_output.insert(0, output_root)
            
            # 语言
            if "download_langs" in config:
                langs = config.get("download_langs", ["zh", "en"])
                langs_str = ",".join(langs) if isinstance(langs, list) else langs
                print(f"[DownloadPanel] 设置语言: {langs} -> {langs_str}")
                self.ent_langs.delete(0, "end")
                self.ent_langs.insert(0, langs_str)
            
            # 格式
            if "download_fmt" in config:
                fmt = config.get("download_fmt", "srt")
                print(f"[DownloadPanel] 设置格式: {fmt}")
                if fmt in ["srt", "vtt", "txt"]:
                    self.opt_fmt.set(fmt)
                else:
                    print(f"[DownloadPanel] 警告: 格式 {fmt} 不在允许的列表中")
            
            # 并发数
            if "max_workers" in config:
                workers = config.get("max_workers", 3)
                print(f"[DownloadPanel] 设置并发数: {workers}")
                self.spin_workers.set(str(workers))
            
            # 高级选项（如果变量存在则设置，否则跳过）
            if "merge_bilingual" in config and hasattr(self, 'var_merge_bilingual'):
                self.var_merge_bilingual.set(config.get("merge_bilingual", True))
            
            if "force_refresh" in config and hasattr(self, 'var_force_refresh'):
                self.var_force_refresh.set(config.get("force_refresh", False))
            
            if "incremental_detect" in config and hasattr(self, 'var_incremental_detect'):
                self.var_incremental_detect.set(config.get("incremental_detect", True))
            
            if "incremental_download" in config and hasattr(self, 'var_incremental_download'):
                self.var_incremental_download.set(config.get("incremental_download", True))
            
            if "early_stop_on_seen" in config and hasattr(self, 'var_early_stop'):
                self.var_early_stop.set(config.get("early_stop_on_seen", True))
            
            print(f"[DownloadPanel] ✓ 配置已加载到UI")
        else:
            print(f"[DownloadPanel] 警告: 配置字典为空")
    
    def clear_urls(self):
        """清空URL"""
        self.txt_urls.delete("1.0", "end")
    
    def show_error(self, message: str):
        """
        显示错误消息
        
        Args:
            message: 错误消息
        """
        messagebox.showerror("错误", message)
    
    def show_info(self, message: str):
        """
        显示信息消息
        
        Args:
            message: 信息消息
        """
        messagebox.showinfo("信息", message)
    
    def show_warning(self, message: str):
        """
        显示警告消息
        
        Args:
            message: 警告消息
        """
        messagebox.showwarning("警告", message)
    
    def update_progress(self, progress: dict):
        """
        更新进度显示
        
        Args:
            progress: 进度信息
        """
        # 视图层不处理进度显示，由专门的进度控制器处理
        pass
    
    def update_theme(self, theme_name: str):
        """
        更新主题
        
        Args:
            theme_name: 主题名称
        """
        # TODO: 根据主题更新颜色
        pass


__all__ = ['DownloadPanel']

