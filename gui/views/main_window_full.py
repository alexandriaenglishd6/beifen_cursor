# -*- coding: utf-8 -*-
"""
主窗口完整版 - 集成所有功能（使用手风琴布局）
"""
import tkinter as tk
from tkinter import ttk
from gui.views.download_panel import DownloadPanel
from gui.views.scheduler_panel import SchedulerPanel
from gui.views.subscription_panel import SubscriptionPanel
from gui.views.ai_panel import AIPanel
from gui.views.settings_panel import SettingsPanel
from gui.views.optimize_panel import OptimizePanel
from gui.views.translate_panel import TranslatePanel
from ui_components import Accordion, AccordionGroup
from theme_manager import TOKENS
from config_store import load_config
try:
    from tooltip import create_tooltip
except ImportError:
    # 如果tooltip模块不存在，创建一个简单的占位函数
    def create_tooltip(widget, text, delay=500):
        pass


class MainWindowFull(tk.Frame):
    """
    主窗口完整版（新架构）
    
    集成功能：
    1. 下载功能
    2. 调度器功能
    3. 订阅功能
    4. AI处理
    5. 高级设置
    """
    
    def __init__(self, master: tk.Tk, config: dict):
        super().__init__(master)
        self.root = master
        self.config = config
        
        # 主题系统
        self.current_theme = config["ui"].get("theme", "dark")
        self.theme_tokens = TOKENS[self.current_theme]
        
        # 手风琴组
        self.accordion_group = AccordionGroup()
        
        # 响应式状态
        self._is_dual_column = True
        self._breakpoint = 1200
        
        # 使用Grid布局，便于精确控制高度占比
        self.grid_rowconfigure(0, weight=0)  # 工具栏：固定高度
        self.grid_rowconfigure(1, weight=1)  # 内容区：可扩展
        self.grid_rowconfigure(2, weight=0)  # 日志区：固定25%高度
        self.grid_columnconfigure(0, weight=1)
        
        # 创建顶部导航栏
        self._build_toolbar()
        
        # 创建主内容区（可滚动，手风琴布局）
        self._build_content_area()
        
        # 创建底部日志区
        self._build_log_area()
        
        self.pack(fill='both', expand=True)
        
        # 响应式布局
        self.root.bind('<Configure>', self._on_resize, add='+')
        self.root.after(10, self._adjust_layout)
        self.root.after(200, self._adjust_layout)
    
    def _build_toolbar(self):
        """构建工具栏"""
        nav = tk.Frame(self)
        nav.grid(row=0, column=0, sticky='ew', padx=10, pady=8)
        
        ttk.Label(nav, text="🎬 YouTube字幕工具", 
                 font=("Segoe UI", 14, "bold")).pack(side='left')
        
        right = tk.Frame(nav)
        right.pack(side='right')
        
        # 预设功能
        ttk.Label(right, text="预设:", font=("Segoe UI", 14, "bold")).pack(side='right', padx=(15,5))
        
        self.preset_menu = ttk.Combobox(right, width=15, state="readonly")
        self.preset_menu.pack(side='right', padx=(0,5))
        
        btn_save_preset = ttk.Button(right, text="💾", width=3)
        btn_save_preset.pack(side='right', padx=(0,5))
        
        # 主题选择
        ttk.Label(right, text="主题:", font=("Segoe UI", 12)).pack(side='right', padx=(15,5))
        
        self.theme_combo = ttk.Combobox(right, values=["light", "dark", "blue"], 
                                       state="readonly", width=8)
        self.theme_combo.set(self.current_theme)
        self.theme_combo.pack(side='right', padx=5)
        
        # 初始化refs字典
        self.refs = {
            'preset_menu': self.preset_menu,
            'btn_save_preset': btn_save_preset,
            'sel_theme': self.theme_combo
        }
        
        # 下载控制按钮
        # 注意：不在这里绑定command，让控制器来绑定，避免绑定冲突
        self.btn_detect = ttk.Button(right, text="🔍 检测", width=10)
        self.btn_detect.pack(side='right', padx=5)
        print(f"[MainWindow] ✓ 创建检测按钮: {self.btn_detect}")
        print(f"[MainWindow] 检测按钮初始state: {self.btn_detect.cget('state')}")
        print(f"[MainWindow] 检测按钮初始command: {self.btn_detect.cget('command')}")
        
        self.btn_download = ttk.Button(right, text="▶️ 下载", width=10)
        self.btn_download.pack(side='right', padx=5)
        print(f"[MainWindow] ✓ 创建下载按钮: {self.btn_download}")
        print(f"[MainWindow] 下载按钮初始state: {self.btn_download.cget('state')}")
        print(f"[MainWindow] 下载按钮初始command: {self.btn_download.cget('command')}")
        
        # 确保按钮在最上层，不被遮挡
        try:
            self.btn_detect.lift()
            self.btn_download.lift()
            right.lift()  # 确保按钮所在的Frame也在最上层
            nav.lift()  # 确保工具栏也在最上层
            print(f"[MainWindow] ✓ 已提升按钮层级，确保不被遮挡")
        except Exception as e:
            print(f"[MainWindow] ⚠️ 提升按钮层级失败: {e}")
        
        self.btn_stop = ttk.Button(right, text="■ 停止", width=10, state='disabled')
        self.btn_stop.pack(side='right', padx=5)
        print(f"[MainWindow] ✓ 创建停止按钮: {self.btn_stop}")
        
        # 暂停/恢复按钮（合并为一个按钮，根据状态切换）
        self.btn_pause_resume = ttk.Button(right, text="⏸️ 暂停", width=10, state="disabled")
        self.btn_pause_resume.pack(side='right', padx=5)
        print(f"[MainWindow] ✓ 创建暂停/恢复按钮: {self.btn_pause_resume}")
        
        # 历史记录按钮
        self.btn_view_history = ttk.Button(right, text="📜 历史", width=10)
        self.btn_view_history.pack(side='right', padx=5)
    
    def _build_content_area(self):
        """构建内容区（手风琴布局 - 响应式双列/单列）"""
        # Canvas + Scrollbar（可滚动）
        content_frame = tk.Frame(self)
        content_frame.grid(row=1, column=0, sticky='nsew')
        
        self.content_canvas = tk.Canvas(content_frame, highlightthickness=0,
                                       bg=self.theme_tokens["panel"])
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", 
                                  command=self.content_canvas.yview)
        
        self.content_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side='right', fill='y')
        self.content_canvas.pack(side='left', fill='both', expand=True)
        
        # 内容容器（使用Grid布局支持双列等宽）
        self.content_container = tk.Frame(self.content_canvas, bg=self.theme_tokens["panel"])
        self.content_canvas.create_window((0, 0), window=self.content_container, 
                                         anchor='nw')
        
        # 容器Grid配置：两列等宽（uniform参数）
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1, uniform='cols')
        self.content_container.grid_columnconfigure(1, weight=1, uniform='cols')
        
        # 左列容器（使用Grid布局，初始双列模式）
        self.col_left = tk.Frame(self.content_container, bg=self.theme_tokens["panel"])
        self.col_left.grid(row=0, column=0, sticky='nsew', padx=(10, 5), pady=10)
        
        # 右列容器
        self.col_right = tk.Frame(self.content_container, bg=self.theme_tokens["panel"])
        self.col_right.grid(row=0, column=1, sticky='nsew', padx=(5, 10), pady=10)
        
        # 保存容器引用（用于响应式切换）
        self.container = self.content_container
        
        # 构建手风琴（使用Accordion组件）
        self._build_accordions()
        
        # 更新滚动区域
        self.content_container.bind('<Configure>', 
                                   lambda e: self.content_canvas.configure(
                                       scrollregion=self.content_canvas.bbox("all")
                                   ))
        
        # 绑定鼠标滚轮事件（支持内容区滚动）
        def _on_mousewheel(event):
            """鼠标滚轮滚动处理"""
            # 检查事件来源控件是否在内容区域内
            widget = event.widget
            
            # 向上遍历控件树，检查是否在Canvas或内容容器内
            is_in_content = False
            try:
                current = widget
                while current:
                    if current == self.content_canvas or current == self.content_container:
                        is_in_content = True
                        break
                    try:
                        current = current.master
                    except:
                        break
                
                # 如果不在内容区域内，不处理
                if not is_in_content:
                    return
                
                # Windows/Linux: event.delta
                if hasattr(event, 'delta') and event.delta:
                    self.content_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                # Mac/Linux: event.num
                elif hasattr(event, 'num'):
                    if event.num == 4:
                        self.content_canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        self.content_canvas.yview_scroll(1, "units")
            except Exception:
                # 静默处理错误
                pass
        
        # 绑定鼠标滚轮事件（使用bind_all确保在子控件上也能滚动，包括折叠模块）
        # 注意：绑定到Canvas和所有子控件，确保在折叠模块内也能滚动
        def _bind_mousewheel_to_canvas(event):
            """当鼠标进入Canvas区域时绑定滚轮事件"""
            self.content_canvas.bind_all("<MouseWheel>", _on_mousewheel)
            self.content_canvas.bind_all("<Button-4>", _on_mousewheel)  # Mac/Linux向上
            self.content_canvas.bind_all("<Button-5>", _on_mousewheel)  # Mac/Linux向下
        
        def _unbind_mousewheel_from_canvas(event):
            """当鼠标离开Canvas区域时解绑滚轮事件"""
            self.content_canvas.unbind_all("<MouseWheel>")
            self.content_canvas.unbind_all("<Button-4>")
            self.content_canvas.unbind_all("<Button-5>")
        
        # 绑定到Canvas的进入/离开事件
        self.content_canvas.bind("<Enter>", _bind_mousewheel_to_canvas)
        self.content_canvas.bind("<Leave>", _unbind_mousewheel_from_canvas)
        
        # 同时绑定到内容容器，确保在折叠模块内也能滚动
        self.content_container.bind("<Enter>", _bind_mousewheel_to_canvas)
        self.content_container.bind("<Leave>", _unbind_mousewheel_from_canvas)
        # 只在Canvas上绑定，不在root上bind_all，避免拦截按钮事件
        
        # 存储防抖ID
        self._resize_job = None
        self._scroll_after_id = None
    
    def _build_accordions(self):
        """构建手风琴布局（面板内部已包含手风琴，直接放置）"""
        # 左列：输入源、AI处理、字幕优化、高级选项
        self.download_panel = DownloadPanel(self.col_left)
        self.download_panel.pack(fill='x', pady=(0, 10))
        
        self.ai_panel = AIPanel(self.col_left)
        self.ai_panel.pack(fill='x', pady=(0, 10))
        
        self.optimize_panel = OptimizePanel(self.col_left)
        self.optimize_panel.pack(fill='x', pady=(0, 10))
        
        self.translate_panel = TranslatePanel(self.col_left)
        self.translate_panel.pack(fill='x', pady=(0, 10))
        
        self.settings_panel = SettingsPanel(self.col_left)
        self.settings_panel.pack(fill='x', pady=(0, 10))
        
        # 右列：调度中心、订阅管理
        self.scheduler_panel = SchedulerPanel(self.col_right)
        self.scheduler_panel.pack(fill='x', pady=(0, 10))
        
        self.subscription_panel = SubscriptionPanel(self.col_right)
        self.subscription_panel.pack(fill='x', pady=(0, 10))
        
        # 将所有手风琴添加到组中（用于统一管理）
        for panel in [self.download_panel, self.ai_panel, self.optimize_panel, 
                      self.translate_panel, self.settings_panel,
                      self.scheduler_panel, self.subscription_panel]:
            if hasattr(panel, 'accordion'):
                panel.accordion.set_on_toggle(lambda expanded: self._on_accordion_toggle())
                self.accordion_group.add(panel.accordion)
    
    def _on_accordion_toggle(self):
        """手风琴折叠/展开时更新滚动区域"""
        self.root.after(300, self._update_scroll_region)  # 延迟更新，等待动画完成
    
    def _build_log_area(self):
        """构建日志区（固定25%高度）"""
        log_frame = tk.Frame(self)
        log_frame.grid(row=2, column=0, sticky='nsew', padx=10, pady=5)
        self.log_frame = log_frame  # 保存引用，用于动态调整高度
        
        # 进度显示区域（在日志标题之前，紧凑布局）
        progress_container = tk.Frame(log_frame)
        progress_container.pack(fill='x', pady=(0, 8), padx=5)
        
        # 第一行：任务信息和进度条
        progress_row1 = tk.Frame(progress_container)
        progress_row1.pack(fill='x', pady=(0, 3))
        
        # 左侧：任务信息（紧凑）
        self.lbl_progress_task = ttk.Label(progress_row1, text="等待中...", 
                                           font=("Segoe UI", 10), foreground="#94A3B8")
        self.lbl_progress_task.pack(side='left', padx=(0, 8))
        
        # 中间：阶段信息（紧凑）
        self.lbl_progress_phase = ttk.Label(progress_row1, text="", 
                                            font=("Segoe UI", 10), foreground="#94A3B8")
        self.lbl_progress_phase.pack(side='left', padx=(0, 8))
        
        # 进度条（自适应，填充中间空间）
        self.progress_bar = ttk.Progressbar(progress_row1, mode='determinate', 
                                           maximum=100, value=0)
        self.progress_bar.pack(side='left', padx=(0, 5), fill='x', expand=True)
        
        # 右侧：百分比标签（固定宽度）
        self.lbl_progress = ttk.Label(progress_row1, text="0%", 
                                      font=("Segoe UI", 10, "bold"), width=4)
        self.lbl_progress.pack(side='right')
        
        # 第二行：详细信息（视频标题、速度、剩余时间）
        progress_row2 = tk.Frame(progress_container)
        progress_row2.pack(fill='x')
        
        # 视频标题（左侧）
        self.lbl_progress_title = ttk.Label(progress_row2, text="", 
                                            font=("Segoe UI", 9), foreground="#94A3B8")
        self.lbl_progress_title.pack(side='left', padx=(0, 10))
        
        # 速度（中间）
        self.lbl_progress_speed = ttk.Label(progress_row2, text="", 
                                           font=("Segoe UI", 9), foreground="#94A3B8")
        self.lbl_progress_speed.pack(side='left', padx=(0, 10))
        
        # 剩余时间（右侧）
        self.lbl_progress_eta = ttk.Label(progress_row2, text="", 
                                         font=("Segoe UI", 9), foreground="#94A3B8")
        self.lbl_progress_eta.pack(side='right')
        
        # 日志标题和控制按钮
        log_header = tk.Frame(log_frame)
        log_header.pack(fill='x', pady=(0, 5))
        
        ttk.Label(log_header, text="📋 执行日志:", 
                 font=("Segoe UI", 14, "bold")).pack(side='left')
        
        # 右侧按钮组（只保留导出和清空，搜索功能移到工具栏）
        btn_group = tk.Frame(log_header)
        btn_group.pack(side='right')
        
        self.btn_export_log = ttk.Button(btn_group, text="📤 导出", width=8)
        self.btn_export_log.pack(side='right', padx=2)
        
        self.btn_clear_log = ttk.Button(btn_group, text="🧹 清空", width=8)
        self.btn_clear_log.pack(side='right', padx=2)
        
        # 日志过滤工具栏
        log_toolbar = tk.Frame(log_frame)
        log_toolbar.pack(fill='x', pady=(0, 5))
        
        # 左侧：级别过滤
        left_group = tk.Frame(log_toolbar)
        left_group.pack(side='left')
        
        ttk.Label(left_group, text="级别:", font=("Segoe UI", 10)).pack(side='left', padx=(0, 5))
        self.combo_log_level = ttk.Combobox(left_group, values=["ALL", "INFO", "WARN", "ERROR", "SUCCESS"], 
                                           width=10, state="readonly")
        self.combo_log_level.set("ALL")
        self.combo_log_level.pack(side='left', padx=(0, 15))
        
        # 中间：搜索组（搜索框、正则选项、搜索按钮、下一个按钮紧密排列）
        search_group = tk.Frame(log_toolbar)
        search_group.pack(side='left', padx=(0, 15))
        
        ttk.Label(search_group, text="搜索:", font=("Segoe UI", 10)).pack(side='left', padx=(0, 5))
        self.entry_log_search = ttk.Entry(search_group, width=25)
        self.entry_log_search.pack(side='left', padx=(0, 5))
        
        # 正则表达式选项
        self.var_use_regex = tk.BooleanVar(value=False)
        self.chk_regex = ttk.Checkbutton(search_group, text="正则", variable=self.var_use_regex)
        self.chk_regex.pack(side='left', padx=(0, 5))
        
        # 搜索按钮（紧挨着搜索框）
        self.btn_search_log_toolbar = ttk.Button(search_group, text="搜索", width=6)
        self.btn_search_log_toolbar.pack(side='left', padx=(0, 3))
        
        # 下一个按钮（紧挨着搜索按钮）
        self.btn_find_next = ttk.Button(search_group, text="下一个", width=8)
        self.btn_find_next.pack(side='left', padx=2)
        
        # 右侧：自动滚动选项
        right_group = tk.Frame(log_toolbar)
        right_group.pack(side='right')
        
        self.var_auto_scroll = tk.BooleanVar(value=True)
        self.chk_auto_scroll = ttk.Checkbutton(right_group, text="自动滚动", variable=self.var_auto_scroll)
        self.chk_auto_scroll.pack(side='left', padx=(10, 0))
        
        # 日志文本框
        log_container = tk.Frame(log_frame)
        log_container.pack(fill='both', expand=True)
        
        self.txt_log = tk.Text(log_container, height=12, font=("Consolas", 10),
                              bg="#1E1E1E", fg="#CCCCCC", insertbackground="#CCCCCC")
        self.txt_log.pack(side='left', fill='both', expand=True)
        
        # 滚动条
        log_scrollbar = ttk.Scrollbar(log_container, command=self.txt_log.yview)
        log_scrollbar.pack(side='right', fill='y')
        self.txt_log.config(yscrollcommand=log_scrollbar.set)
        
        # 配置日志颜色标签
        self.txt_log.tag_config("INFO", foreground="#FFFFFF")
        self.txt_log.tag_config("WARN", foreground="#FFB84D")
        self.txt_log.tag_config("ERROR", foreground="#FF6B6B")
        self.txt_log.tag_config("SUCCESS", foreground="#4ECDC4")
        # 搜索匹配高亮：使用非常亮的黄色背景和黑色文字，确保在黑色背景上可见
        # 注意：必须在添加tag之前配置，并且使用正确的参数格式
        self.txt_log.tag_config("search_match", background="#FFEB3B", foreground="#000000")
        # 设置tag优先级：search_match应该在最上层
        self.txt_log.tag_raise("search_match")
        
        # 测试：验证tag配置（使用tag_cget获取实际值）
        try:
            bg = self.txt_log.tag_cget("search_match", "background")
            fg = self.txt_log.tag_cget("search_match", "foreground")
            print(f"[DEBUG] Text组件tag配置测试:")
            print(f"[DEBUG]   search_match background: {bg}")
            print(f"[DEBUG]   search_match foreground: {fg}")
            # 如果配置失败，重新配置
            if not bg or bg == '':
                print(f"[DEBUG] ⚠️ tag配置为空，重新配置...")
                self.txt_log.tag_config("search_match", background="#FFEB3B", foreground="#000000")
                bg = self.txt_log.tag_cget("search_match", "background")
                print(f"[DEBUG]   重新配置后 background: {bg}")
        except Exception as e:
            print(f"[DEBUG] ✗ tag配置验证失败: {e}")
            import traceback
            traceback.print_exc()
        
        import sys
        sys.stdout.flush()
        
        # 添加工具提示
        create_tooltip(self.btn_find_next, 
            "查找下一个匹配项\n"
            "功能说明：\n"
            "• 在搜索框中输入关键词后，点击此按钮查找下一个匹配的日志\n"
            "• 支持普通搜索和正则表达式搜索\n"
            "• 匹配项会高亮显示（黄色背景）\n"
            "• 到达末尾时会自动从头开始搜索")
        
        create_tooltip(self.btn_search_log_toolbar,
            "搜索日志\n"
            "在搜索框中输入关键词后点击此按钮进行搜索\n"
            "或直接按Enter键")
        
        create_tooltip(self.chk_regex,
            "启用正则表达式搜索\n"
            "勾选后可以使用正则表达式模式进行搜索\n"
            "例如：^ERROR.* 可以匹配以ERROR开头的日志")
        
        create_tooltip(self.combo_log_level,
            "日志级别过滤\n"
            "选择要显示的日志级别：\n"
            "• ALL: 显示所有日志\n"
            "• INFO: 仅显示信息日志\n"
            "• WARN: 仅显示警告日志\n"
            "• ERROR: 仅显示错误日志\n"
            "• SUCCESS: 仅显示成功日志")
        
        create_tooltip(self.chk_auto_scroll,
            "自动滚动到底部\n"
            "勾选后，新日志会自动滚动到底部显示\n"
            "取消勾选后，可以手动查看历史日志")
    
    def append_log(self, message: str, level: str = "INFO"):
        """添加日志"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}\n"
        
        # 检查级别过滤
        current_level = self.combo_log_level.get() if hasattr(self, 'combo_log_level') else "ALL"
        if current_level != "ALL" and current_level != level:
            return  # 不显示
        
        # 注意：搜索过滤不在append_log中处理，而是在_refresh_log_display中处理
        # 这样可以保持新日志的实时显示，同时支持搜索过滤
        
        self.txt_log.insert("end", log_line, level)
        
        # 如果有搜索关键词，高亮匹配项（仅高亮，不过滤）
        keyword = self.entry_log_search.get().strip() if hasattr(self, 'entry_log_search') else ""
        if keyword:
            use_regex = self.var_use_regex.get() if hasattr(self, 'var_use_regex') else False
            # 高亮这一行中的匹配项
            # 获取刚插入的行的位置
            line_start = self.txt_log.index("end-1c linestart")
            line_end = self.txt_log.index("end-1c lineend")
            
            if use_regex:
                try:
                    import re
                    pattern = re.compile(keyword, re.IGNORECASE)
                    line_content = self.txt_log.get(line_start, line_end)
                    for match in pattern.finditer(line_content):
                        col_start = match.start()
                        col_end = match.end()
                        start_index = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + col_start}"
                        end_index = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + col_end}"
                        try:
                            self.txt_log.tag_add("search_match", start_index, end_index)
                        except:
                            pass
                except re.error:
                    # 正则表达式错误，使用普通搜索
                    self._highlight_line_matches(line_start, line_end, keyword)
            else:
                # 普通搜索：使用Text组件的search方法
                self._highlight_line_matches(line_start, line_end, keyword)
        
        # 自动滚动
        if hasattr(self, 'var_auto_scroll') and self.var_auto_scroll.get():
            self.txt_log.see("end")
    
    def _highlight_line_matches(self, line_start: str, line_end: str, keyword: str):
        """
        高亮指定行中的匹配项
        
        Args:
            line_start: 行开始位置（Text索引格式）
            line_end: 行结束位置（Text索引格式）
            keyword: 搜索关键词
        """
        start_pos = line_start
        while True:
            pos = self.txt_log.search(keyword, start_pos, line_end, nocase=True)
            if not pos:
                break
            
            end_pos = f"{pos}+{len(keyword)}c"
            try:
                self.txt_log.tag_add("search_match", pos, end_pos)
            except:
                pass
            
            start_pos = end_pos
    
    def clear_log(self):
        """清空日志"""
        self.txt_log.delete("1.0", "end")
        # 清除搜索高亮
        self.txt_log.tag_delete("search_match")
    
    def highlight_search_matches(self, keyword: str, use_regex: bool = False) -> int:
        """
        高亮搜索匹配项
        
        Args:
            keyword: 搜索关键词
            use_regex: 是否使用正则表达式
        
        Returns:
            实际高亮的字符匹配数量
        """
        # 确保Text组件处于normal状态
        current_state = self.txt_log.cget('state')
        if current_state == 'disabled':
            self.txt_log.config(state='normal')
        
        # 清除之前的高亮
        self.txt_log.tag_remove("search_match", "1.0", "end")
        
        if not keyword:
            if current_state == 'disabled':
                self.txt_log.config(state='disabled')
            return
        
        print(f"[DEBUG] highlight_search_matches: keyword='{keyword}', use_regex={use_regex}")
        
        # 重新配置tag（确保配置正确）- 每次高亮前都重新配置
        try:
            # 先删除旧的tag配置（如果有）
            try:
                self.txt_log.tag_delete("search_match")
            except:
                pass
            
            # 重新创建并配置tag
            self.txt_log.tag_config("search_match", background="#FFEB3B", foreground="#000000")
            self.txt_log.tag_raise("search_match")
            bg = self.txt_log.tag_cget("search_match", "background")
            print(f"[DEBUG] tag重新配置后 background: {bg}")
        except Exception as e:
            print(f"[DEBUG] ✗ tag重新配置失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 使用Text组件的search方法进行搜索（更准确）
        start_pos = "1.0"
        match_count = 0
        
        if use_regex:
            # 正则表达式搜索：先获取所有内容，然后用正则匹配，再转换为Text索引
            try:
                import re
                content = self.txt_log.get("1.0", "end")
                pattern = re.compile(keyword, re.IGNORECASE)
                
                # 将字符位置转换为行号和列号
                lines = content.split('\n')
                char_pos = 0
                for line_num, line in enumerate(lines, start=1):
                    line_with_newline = line + '\n'
                    for match in pattern.finditer(line):
                        # 计算匹配位置
                        match_start_char = char_pos + match.start()
                        match_end_char = char_pos + match.end()
                        
                        # 转换为Text索引格式
                        # 找到匹配所在的行
                        line_start_char = char_pos
                        col_start = match.start()
                        col_end = match.end()
                        
                        start_index = f"{line_num}.{col_start}"
                        end_index = f"{line_num}.{col_end}"
                        
                        try:
                            self.txt_log.tag_add("search_match", start_index, end_index)
                            match_count += 1
                            print(f"[DEBUG] 正则高亮第 {match_count} 处: {start_index} -> {end_index}")
                        except Exception as e:
                            # 忽略位置错误
                            print(f"[DEBUG] 正则高亮失败: {e}, start={start_index}, end={end_index}")
                            pass
                    
                    char_pos += len(line_with_newline)
            except re.error:
                # 正则表达式错误，回退到普通搜索
                print(f"[DEBUG] 正则表达式错误，回退到普通搜索")
                self._highlight_normal_search(keyword)
                match_count = len(self.txt_log.tag_ranges("search_match")) // 2
                if current_state == 'disabled':
                    self.txt_log.config(state='disabled')
                return match_count
        else:
            # 普通搜索：使用Text组件的search方法
            self._highlight_normal_search(keyword)
            match_count = len(self.txt_log.tag_ranges("search_match")) // 2
        
        # 恢复Text组件状态
        if current_state == 'disabled':
            self.txt_log.config(state='disabled')
        
        # 计算实际匹配数量
        match_count = len(self.txt_log.tag_ranges("search_match")) // 2
        print(f"[DEBUG] highlight_search_matches 完成: {match_count} 处匹配")
        return match_count
    
    def _highlight_normal_search(self, keyword: str):
        """
        使用Text组件的search方法进行普通搜索和高亮
        
        Args:
            keyword: 搜索关键词
        """
        # 确保Text组件处于normal状态（可以编辑）
        current_state = self.txt_log.cget('state')
        was_disabled = (current_state == 'disabled')
        if was_disabled:
            self.txt_log.config(state='normal')
        
        start_pos = "1.0"
        match_count = 0
        
        print(f"[DEBUG] 开始搜索高亮: keyword='{keyword}'")
        
        while True:
            # 使用Text组件的search方法（支持nocase参数）
            pos = self.txt_log.search(keyword, start_pos, "end", nocase=True)
            if not pos:
                break
            
            # 计算结束位置
            end_pos = f"{pos}+{len(keyword)}c"
            
            # 添加高亮标签
            try:
                self.txt_log.tag_add("search_match", pos, end_pos)
                # 确保search_match tag在最上层（覆盖其他tag）
                self.txt_log.tag_raise("search_match")
                match_count += 1
                print(f"[DEBUG] 高亮第 {match_count} 处: {pos} -> {end_pos}")
            except Exception as e:
                # 打印错误信息
                print(f"[DEBUG] 高亮失败: {e}, pos={pos}, end_pos={end_pos}")
                import traceback
                traceback.print_exc()
            
            # 移动到下一个位置继续搜索
            start_pos = end_pos
        
        # 恢复Text组件状态
        if was_disabled:
            self.txt_log.config(state='disabled')
        
        # 验证tag是否添加成功
        ranges = self.txt_log.tag_ranges("search_match")
        print(f"[DEBUG] tag_ranges('search_match'): {len(ranges)//2} 个范围")
        
        # 强制更新显示
        self.txt_log.update_idletasks()
        
        if match_count > 0:
            print(f"[DEBUG] ✓ 成功高亮 {match_count} 处匹配")
        else:
            print(f"[DEBUG] ✗ 未找到匹配项: {keyword}")
    
    def update_progress(self, progress: dict):
        """
        更新进度条和详细信息
        
        Args:
            progress: 进度信息字典，包含：
                - percent: 进度百分比 (0-100)
                - phase: 当前阶段（可选）
                - task: 当前任务信息（可选）
                - title: 当前视频标题（可选）
                - speed: 处理速度 items/s（可选）
                - eta: 预计剩余时间 秒（可选）
        """
        # 兼容旧格式（如果传入的是简单参数）
        if isinstance(progress, (int, float)):
            percent = int(progress)
            phase = ""
            task = ""
            title = ""
            speed = None
            eta = None
        elif isinstance(progress, dict):
            percent = progress.get("percent", progress.get("percentage", 0))
            phase = progress.get("phase", "")
            task = progress.get("task", progress.get("message", ""))
            title = progress.get("title", progress.get("current_item", ""))
            speed = progress.get("speed")
            eta = progress.get("eta")
        else:
            return
        
        # 更新进度条
        if hasattr(self, 'progress_bar'):
            self.progress_bar['value'] = max(0, min(100, percent))
        
        # 更新百分比
        if hasattr(self, 'lbl_progress'):
            self.lbl_progress.config(text=f"{int(percent)}%")
        
        # 更新阶段信息
        if hasattr(self, 'lbl_progress_phase'):
            if phase:
                phase_map = {
                    'detect': '检测中',
                    'download': '下载中',
                    'retry': '重试中',
                    'complete': '完成',
                    'error': '错误',
                    'paused': '已暂停',
                    'stopped': '已停止'
                }
                phase_text = phase_map.get(phase.lower(), phase)
                self.lbl_progress_phase.config(text=f"阶段: {phase_text}")
            else:
                self.lbl_progress_phase.config(text="")
        
        # 更新任务信息
        if hasattr(self, 'lbl_progress_task'):
            if task:
                # 如果任务信息太长，截断
                if len(task) > 50:
                    task = task[:47] + "..."
                self.lbl_progress_task.config(text=task)
            else:
                self.lbl_progress_task.config(text="等待中...")
        
        # 更新视频标题
        if hasattr(self, 'lbl_progress_title'):
            if title:
                # 如果标题太长，截断
                if len(title) > 60:
                    title = title[:57] + "..."
                self.lbl_progress_title.config(text=f"📹 {title}")
            else:
                self.lbl_progress_title.config(text="")
        
        # 更新速度
        if hasattr(self, 'lbl_progress_speed'):
            if speed is not None:
                if speed >= 1:
                    self.lbl_progress_speed.config(text=f"⚡ {speed:.1f} 项/秒")
                elif speed > 0:
                    self.lbl_progress_speed.config(text=f"⚡ {1/speed:.1f} 秒/项")
                else:
                    self.lbl_progress_speed.config(text="")
            else:
                self.lbl_progress_speed.config(text="")
        
        # 更新剩余时间
        if hasattr(self, 'lbl_progress_eta'):
            if eta is not None and eta > 0:
                # 格式化剩余时间
                if eta < 60:
                    eta_text = f"⏱️ {int(eta)}秒"
                elif eta < 3600:
                    eta_text = f"⏱️ {int(eta/60)}分{int(eta%60)}秒"
                else:
                    hours = int(eta / 3600)
                    minutes = int((eta % 3600) / 60)
                    eta_text = f"⏱️ {hours}时{minutes}分"
                self.lbl_progress_eta.config(text=eta_text)
            else:
                self.lbl_progress_eta.config(text="")
    
    def set_button_loading(self, button_name: str, loading: bool, text: str = None):
        """
        设置按钮加载状态
        
        Args:
            button_name: 按钮名称 ('detect', 'download', 'stop')
            loading: 是否加载中
            text: 自定义文本（可选）
        """
        button_map = {
            'detect': self.btn_detect,
            'download': self.btn_download,
            'stop': self.btn_stop
        }
        
        if button_name not in button_map:
            return
        
        button = button_map[button_name]
        
        # 保存当前的command，避免被覆盖
        current_command = button.cget('command')
        
        if loading:
            button.config(state='disabled')
            if text:
                button.config(text=text)
            elif button_name == 'detect':
                button.config(text="🔍 检测中...")
            elif button_name == 'download':
                button.config(text="▶️ 下载中...")
        else:
            button.config(state='normal')
            if button_name == 'detect':
                button.config(text="🔍 检测")
            elif button_name == 'download':
                button.config(text="▶️ 下载")
            elif button_name == 'stop':
                button.config(text="■ 停止")
        
        # 恢复command（如果被覆盖了）
        if current_command and button.cget('command') != current_command:
            print(f"[MainWindow] ⚠️ 恢复按钮command: {button_name}")
            button.config(command=current_command)
    
    def reset_progress(self):
        """重置进度显示"""
        self.update_progress({"percent": 0, "phase": "", "task": "", "title": "", "speed": None, "eta": None})
        self.set_button_loading('detect', False)
        self.set_button_loading('download', False)
    
    def update_theme(self, theme_name: str):
        """更新主题"""
        self.current_theme = theme_name
        self.theme_tokens = TOKENS[theme_name]
        
        # 更新所有面板的主题
        for panel in [self.download_panel, self.ai_panel, self.settings_panel,
                      self.scheduler_panel, self.subscription_panel]:
            if hasattr(panel, 'update_theme'):
                panel.update_theme(theme_name)
    
    def _on_resize(self, event=None):
        """窗口大小变化事件（防抖优化）"""
        if event and event.widget != self.root:
            return
        
        # 防抖：取消之前的任务
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        
        self._resize_job = self.root.after(30, self._adjust_layout)
    
    def _adjust_layout(self):
        """响应式布局调整（参考旧架构实现）"""
        try:
            self.root.update_idletasks()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            
            # 忽略无效尺寸
            if w < 100 or h < 100:
                return
            
            # 1. 日志区固定25%高度（参考旧架构30%，用户要求25%）
            log_h = max(150, int(h * 0.25))  # 25%或最小150px
            self.grid_rowconfigure(2, minsize=log_h)
            
            # 2. 单双列智能切换
            is_dual = w >= self._breakpoint
            
            if is_dual != self._is_dual_column:
                self._is_dual_column = is_dual
                self._switch_layout_mode(is_dual, w)
            
            # 3. 更新Canvas宽度
            if self.content_canvas.find_all():
                canvas_width = w - 30  # 减去滚动条(15px)和边距(15px)
                self.content_canvas.itemconfig(self.content_canvas.find_all()[0], width=canvas_width)
                self.content_container.update_idletasks()
            
            # 4. 更新滚动区域
            self._update_scroll_region()
            
        except Exception as e:
            print(f"[ERROR] 布局调整失败: {e}")
    
    def _switch_layout_mode(self, is_dual: bool, width: int):
        """切换布局模式（Grid+Pack混合：确保等宽）"""
        # 清理：同时尝试移除Grid和Pack（避免布局冲突）
        try:
            self.col_left.grid_forget()
            self.col_right.grid_forget()
        except:
            pass
        
        try:
            self.col_left.pack_forget()
            self.col_right.pack_forget()
        except:
            pass
        
        if is_dual:
            # 🔑 双列模式：使用Grid + uniform参数强制等宽
            self.container.grid_columnconfigure(0, weight=1, uniform='cols')
            self.container.grid_columnconfigure(1, weight=1, uniform='cols')
            
            self.col_left.grid(row=0, column=0, sticky='nsew', padx=(10, 5), pady=10)
            self.col_right.grid(row=0, column=1, sticky='nsew', padx=(5, 10), pady=10)
            print(f"[UI] ✓ 切换到双列模式 (宽度={width}px, Grid等宽)")
        else:
            # 单列模式：使用Pack布局，上下堆叠
            # 清除Grid配置
            self.container.grid_columnconfigure(0, weight=0)
            self.container.grid_columnconfigure(1, weight=0)
            
            # 使用Pack布局
            self.col_left.pack(side='top', fill='x', expand=False, padx=10, pady=(10, 5))
            self.col_right.pack(side='top', fill='x', expand=False, padx=10, pady=(5, 10))
            print(f"[UI] ✓ 切换到单列模式 (宽度={width}px, Pack堆叠)")
        
        # 立即更新布局
        self.container.update_idletasks()
        self._update_scroll_region()
    
    def _update_scroll_region(self):
        """更新滚动区域"""
        if self.content_canvas:
            self.content_canvas.update_idletasks()
            self.content_canvas.configure(
                scrollregion=self.content_canvas.bbox("all")
            )


__all__ = ['MainWindowFull']

