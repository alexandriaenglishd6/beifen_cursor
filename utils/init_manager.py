# -*- coding: utf-8 -*-
"""
初始化管理器 - 统一管理应用初始化顺序
"""
import tkinter as tk
from typing import Callable, List, Dict, Optional
from pathlib import Path


class InitializationManager:
    """
    初始化管理器
    
    职责：
    1. 统一管理初始化顺序
    2. 处理依赖关系
    3. 确保UI完全创建后再初始化控制器
    4. 提供重试机制
    """
    
    def __init__(self, root: tk.Tk):
        """
        初始化
        
        Args:
            root: Tkinter根窗口
        """
        self.root = root
        self.steps: List[Dict] = []
        self.status: Dict[str, any] = {
            "completed": [],
            "failed": [],
            "errors": []
        }
        self._current_step_index = 0
    
    def add_step(
        self,
        name: str,
        func: Callable[[], bool],
        dependencies: List[str] = None,
        retry_on_fail: bool = False,
        max_retries: int = 3,
        delay_ms: int = 0
    ):
        """
        添加初始化步骤
        
        Args:
            name: 步骤名称
            func: 执行函数（返回True表示成功）
            dependencies: 依赖的步骤名称列表
            retry_on_fail: 失败时是否重试
            max_retries: 最大重试次数
            delay_ms: 延迟执行时间（毫秒）
        """
        self.steps.append({
            "name": name,
            "func": func,
            "dependencies": dependencies or [],
            "retry_on_fail": retry_on_fail,
            "max_retries": max_retries,
            "retry_count": 0,
            "delay_ms": delay_ms,
            "completed": False
        })
    
    def execute_all(self):
        """执行所有初始化步骤"""
        print(f"[InitManager] 开始执行 {len(self.steps)} 个初始化步骤")
        
        # 按依赖关系排序
        sorted_steps = self._topological_sort()
        
        # 执行步骤
        for step in sorted_steps:
            self._execute_step(step)
    
    def _topological_sort(self) -> List[Dict]:
        """拓扑排序，确保依赖步骤先执行"""
        # 创建步骤映射
        step_map = {step["name"]: step for step in self.steps}
        
        # 拓扑排序
        sorted_steps = []
        visited = set()
        temp_visited = set()
        
        def visit(step_name: str):
            if step_name in temp_visited:
                print(f"[InitManager] ⚠️ 检测到循环依赖: {step_name}")
                return
            if step_name in visited:
                return
            
            temp_visited.add(step_name)
            step = step_map.get(step_name)
            if step:
                # 先访问依赖
                for dep in step["dependencies"]:
                    visit(dep)
                sorted_steps.append(step)
            visited.add(step_name)
            temp_visited.remove(step_name)
        
        for step in self.steps:
            if step["name"] not in visited:
                visit(step["name"])
        
        return sorted_steps
    
    def _execute_step(self, step: Dict):
        """执行单个步骤"""
        name = step["name"]
        
        # 检查依赖是否完成
        for dep_name in step["dependencies"]:
            dep_step = next((s for s in self.steps if s["name"] == dep_name), None)
            if not dep_step or not dep_step["completed"]:
                print(f"[InitManager] ⚠️ 步骤 '{name}' 的依赖 '{dep_name}' 未完成，跳过")
                self.status["failed"].append(name)
                self.status["errors"].append(f"步骤 '{name}' 的依赖 '{dep_name}' 未完成")
                return
        
        # 延迟执行
        if step["delay_ms"] > 0:
            self.root.after(step["delay_ms"], lambda: self._run_step(step))
        else:
            self._run_step(step)
    
    def _run_step(self, step: Dict):
        """运行步骤"""
        name = step["name"]
        print(f"[InitManager] 执行步骤: {name}")
        
        try:
            result = step["func"]()
            if result:
                step["completed"] = True
                self.status["completed"].append(name)
                print(f"[InitManager] ✓ 步骤 '{name}' 完成")
            else:
                # 失败，检查是否需要重试
                if step["retry_on_fail"] and step["retry_count"] < step["max_retries"]:
                    step["retry_count"] += 1
                    print(f"[InitManager] ⚠️ 步骤 '{name}' 失败，重试 {step['retry_count']}/{step['max_retries']}")
                    self.root.after(200, lambda: self._run_step(step))
                else:
                    step["completed"] = False
                    self.status["failed"].append(name)
                    self.status["errors"].append(f"步骤 '{name}' 失败")
                    print(f"[InitManager] ✗ 步骤 '{name}' 失败")
        except Exception as e:
            import traceback
            error_msg = f"步骤 '{name}' 执行异常: {e}"
            print(f"[InitManager] ✗ {error_msg}")
            traceback.print_exc()
            self.status["failed"].append(name)
            self.status["errors"].append(error_msg)
    
    def ensure_ui_ready(self, view) -> bool:
        """
        确保UI完全创建（检查所有懒加载组件）
        
        Args:
            view: 主窗口视图
        
        Returns:
            是否就绪
        """
        # 检查所有面板的懒加载组件
        panels = [
            ("settings", getattr(view, "settings_panel", None)),
            ("download", getattr(view, "download_panel", None)),
            ("ai", getattr(view, "ai_panel", None)),
            ("optimize", getattr(view, "optimize_panel", None)),
            ("translate", getattr(view, "translate_panel", None)),
            ("scheduler", getattr(view, "scheduler_panel", None)),
            ("subscription", getattr(view, "subscription_panel", None)),
        ]
        
        all_ready = True
        for panel_name, panel in panels:
            if panel and hasattr(panel, "accordion"):
                accordion = panel.accordion
                if hasattr(accordion, "_lazy_load") and accordion._lazy_load:
                    # 触发懒加载
                    try:
                        accordion.get_content_frame()
                        print(f"[InitManager] ✓ {panel_name} 面板已加载")
                    except Exception as e:
                        print(f"[InitManager] ⚠️ {panel_name} 面板加载失败: {e}")
                        all_ready = False
        
        return all_ready
    
    def get_status(self) -> Dict:
        """获取初始化状态"""
        return {
            "total": len(self.steps),
            "completed": len(self.status["completed"]),
            "failed": len(self.status["failed"]),
            "errors": self.status["errors"]
        }


__all__ = ['InitializationManager']
