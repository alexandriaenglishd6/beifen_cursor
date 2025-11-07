# -*- coding: utf-8 -*-
"""
订阅控制器 - 管理订阅
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from gui.controllers.base_controller import BaseController
from events.event_bus import EventType, Event
from services.subscription_service import SubscriptionService

if TYPE_CHECKING:
    from gui.views.subscription_panel import SubscriptionPanel


class SubscriptionController(BaseController):
    """
    订阅控制器
    
    职责：
    1. 管理订阅（增删改查）
    2. 订阅启用/禁用
    3. 订阅导入/导出
    """
    
    def __init__(self, view: SubscriptionPanel, config: dict):
        """
        初始化
        
        Args:
            view: 订阅面板视图
            config: 全局配置
        """
        self.view = view
        self.config = config
        self.service = SubscriptionService(config)
        super().__init__()
        
        # 统一初始化顺序：主动触发懒加载后绑定并立即刷新
        if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
            try:
                self.view.accordion.get_content_frame()
            except Exception:
                pass
        self._bind_view_events_immediate()
        self.refresh_subscriptions()
    
    def _bind_view_events(self):
        """绑定视图事件（支持懒加载模式）"""
        # 统一为立即绑定（InitializationManager已保证就绪）
        self._bind_view_events_immediate()
    
    def _bind_view_events_delayed(self):
        """兼容函数：直接转为立即绑定"""
        self._bind_view_events_immediate()
    
    def _bind_view_events_immediate(self):
        """立即绑定视图事件"""
        # 订阅管理按钮
        if hasattr(self.view, 'btn_add'):
            self.view.btn_add.config(command=self.add_subscription)
        
        if hasattr(self.view, 'btn_edit'):
            self.view.btn_edit.config(command=self.edit_subscription)
        
        if hasattr(self.view, 'btn_delete'):
            self.view.btn_delete.config(command=self.delete_subscription)
        
        if hasattr(self.view, 'btn_toggle'):
            self.view.btn_toggle.config(command=self.toggle_subscription)
        
        # 导入/导出按钮
        if hasattr(self.view, 'btn_import'):
            self.view.btn_import.config(command=self.import_subscriptions)
        
        if hasattr(self.view, 'btn_export'):
            self.view.btn_export.config(command=self.export_subscriptions)
        
        if hasattr(self.view, 'btn_refresh'):
            self.view.btn_refresh.config(command=self.refresh_subscriptions)
    
    def _setup_event_listeners(self):
        """设置事件监听"""
        # 监听订阅事件，自动刷新
        self.event_bus.subscribe(EventType.SUBSCRIPTION_ADDED, lambda e: self.refresh_subscriptions())
        self.event_bus.subscribe(EventType.SUBSCRIPTION_UPDATED, lambda e: self.refresh_subscriptions())
        self.event_bus.subscribe(EventType.SUBSCRIPTION_DELETED, lambda e: self.refresh_subscriptions())
        self.event_bus.subscribe(EventType.SUBSCRIPTION_TOGGLED, lambda e: self.refresh_subscriptions())
        
        # 监听主题变化
        self.event_bus.subscribe(EventType.THEME_CHANGED, self._on_theme_changed)
    
    def add_subscription(self):
        """添加订阅"""
        # 显示添加对话框
        sub_data = self.view.show_add_dialog()
        
        if sub_data:
            try:
                # 添加订阅
                sub_id = self.service.add_subscription(sub_data)
                
                # 发布事件
                self.event_bus.publish(Event(
                    EventType.SUBSCRIPTION_ADDED,
                    {"sub_id": sub_id, "name": sub_data.get("name")}
                ))
                
                self._log(f"订阅已添加: {sub_data.get('name')}")
                
            except Exception as e:
                self.view.show_error(f"添加订阅失败: {e}")
                self._log(f"添加订阅失败: {e}", "ERROR")
    
    def edit_subscription(self):
        """编辑订阅"""
        # 获取选中的订阅（使用控制器的服务实例）
        selected_sub = self.view.get_selected_subscription(self.service)
        if not selected_sub:
            self.view.show_info("请先选择一个订阅")
            return
        
        sub_id = selected_sub.get("id")
        
        # 显示编辑对话框
        sub_data = self.view.show_edit_dialog(selected_sub)
        
        if sub_data:
            try:
                # 更新订阅
                self.service.update_subscription(sub_id, sub_data)
                
                # 发布事件
                self.event_bus.publish(Event(
                    EventType.SUBSCRIPTION_UPDATED,
                    {"sub_id": sub_id, "name": sub_data.get("name")}
                ))
                
                self._log(f"订阅已更新: {sub_data.get('name')}")
                
            except Exception as e:
                self.view.show_error(f"更新订阅失败: {e}")
                self._log(f"更新订阅失败: {e}", "ERROR")
    
    def delete_subscription(self):
        """删除订阅"""
        # 获取选中的订阅（使用控制器的服务实例）
        selected_sub = self.view.get_selected_subscription(self.service)
        if not selected_sub:
            self.view.show_info("请先选择一个订阅")
            return
        
        sub_id = selected_sub.get("id")
        sub_name = selected_sub.get("name")
        
        # 确认删除
        if not self.view.confirm_delete(sub_name):
            return
        
        try:
            # 删除订阅
            self.service.delete_subscription(sub_id)
            
            # 发布事件
            self.event_bus.publish(Event(
                EventType.SUBSCRIPTION_DELETED,
                {"sub_id": sub_id, "name": sub_name}
            ))
            
            self._log(f"订阅已删除: {sub_name}")
            
        except Exception as e:
            self.view.show_error(f"删除订阅失败: {e}")
            self._log(f"删除订阅失败: {e}", "ERROR")
    
    def toggle_subscription(self):
        """切换订阅状态"""
        # 获取选中的订阅（使用控制器的服务实例，确保获取最新数据）
        selected_sub = self.view.get_selected_subscription(self.service)
        if not selected_sub:
            self.view.show_info("请先选择一个订阅")
            return
        
        sub_id = selected_sub.get("id")
        current_enabled = selected_sub.get("enabled", True)
        new_enabled = not current_enabled
        
        try:
            # 切换状态
            self.service.toggle_subscription(sub_id, new_enabled)
            
            # 发布事件
            self.event_bus.publish(Event(
                EventType.SUBSCRIPTION_TOGGLED,
                {"sub_id": sub_id, "enabled": new_enabled}
            ))
            
            status = "启用" if new_enabled else "禁用"
            self._log(f"订阅已{status}: {selected_sub.get('name')}")
            
        except Exception as e:
            self.view.show_error(f"切换状态失败: {e}")
            self._log(f"切换状态失败: {e}", "ERROR")
    
    def refresh_subscriptions(self):
        """刷新订阅列表"""
        try:
            # 确保内容已加载（如果是懒加载模式）
            if hasattr(self.view, 'accordion') and self.view.accordion._lazy_load:
                # 触发懒加载（如果尚未加载）
                self.view.accordion.get_content_frame()
            
            # 检查tree控件是否存在
            if not hasattr(self.view, 'tree'):
                # 如果还不存在，延迟重试
                root = self.view.winfo_toplevel()
                root.after(200, self.refresh_subscriptions)
                return
            
            # 获取订阅列表
            subscriptions = self.service.list_subscriptions()
            
            # 更新视图
            self.view.update_subscription_list(subscriptions)
            
        except Exception as e:
            self._log(f"刷新订阅列表失败: {e}", "ERROR")
    
    def import_subscriptions(self):
        """导入订阅"""
        # 选择文件
        file_path = self.view.select_import_file()
        if not file_path:
            return
        
        try:
            # 导入
            count = self.service.import_subscriptions(file_path)
            
            self._log(f"成功导入 {count} 个订阅")
            self.view.show_info(f"成功导入 {count} 个订阅")
            
            # 刷新列表
            self.refresh_subscriptions()
            
        except Exception as e:
            self.view.show_error(f"导入失败: {e}")
            self._log(f"导入订阅失败: {e}", "ERROR")
    
    def list_subscriptions(self):
        """获取订阅列表（用于导出）"""
        return self.service.list_subscriptions()
    
    def export_subscriptions(self):
        """导出订阅（保留原方法以兼容）"""
        # 选择保存路径
        file_path = self.view.select_export_file()
        if not file_path:
            return
        
        try:
            # 导出
            count = self.service.export_subscriptions(file_path)
            
            self._log(f"成功导出 {count} 个订阅")
            self.view.show_info(f"成功导出 {count} 个订阅到\n{file_path}")
            
        except Exception as e:
            self.view.show_error(f"导出失败: {e}")
            self._log(f"导出订阅失败: {e}", "ERROR")
    
    def _on_theme_changed(self, event: Event):
        """主题变化处理"""
        theme = event.data.get("theme")
        self.view.update_theme(theme)


__all__ = ['SubscriptionController']

