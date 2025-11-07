# -*- coding: utf-8 -*-
"""
旗舰模式 Phase 1: 通知系统
支持 Webhook 和 Email（占位）
"""
from __future__ import annotations
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime


class Notifier:
    """
    通知器（旗舰版）
    
    支持：
    - Webhook 推送
    - Email 通知（占位）
    - 自定义通知渠道
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", False)
        
        logging.info(f"[NOTIFIER] 初始化完成 (enabled={self.enabled})")
    
    def send_task_notification(
        self,
        task_name: str,
        status: str,
        details: Dict[str, Any] = None
    ):
        """
        发送任务通知
        
        Args:
            task_name: 任务名称
            status: 状态 (started/completed/failed)
            details: 详细信息
        """
        if not self.enabled:
            return
        
        message = self._build_message(task_name, status, details or {})
        
        # Webhook 通知
        if self.config.get("webhook"):
            self._send_webhook(message)
        
        # Email 通知（占位）
        if self.config.get("email"):
            self._send_email(message)
    
    def _build_message(
        self,
        task_name: str,
        status: str,
        details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建通知消息"""
        status_emoji = {
            "started": "🚀",
            "completed": "✅",
            "failed": "❌",
            "warning": "⚠️"
        }
        
        emoji = status_emoji.get(status, "ℹ️")
        
        message = {
            "timestamp": datetime.now().isoformat(),
            "task": task_name,
            "status": status,
            "emoji": emoji,
            "title": f"{emoji} 任务{self._status_text(status)}: {task_name}",
            "details": details
        }
        
        return message
    
    def _status_text(self, status: str) -> str:
        """状态文本"""
        mapping = {
            "started": "开始",
            "completed": "完成",
            "failed": "失败",
            "warning": "警告"
        }
        return mapping.get(status, status)
    
    def _send_webhook(self, message: Dict[str, Any]):
        """发送 Webhook 通知"""
        try:
            import requests
            
            webhook_url = self.config.get("webhook", {}).get("url")
            if not webhook_url:
                return
            
            timeout = self.config.get("webhook", {}).get("timeout", 10)
            
            # 发送 POST 请求
            response = requests.post(
                webhook_url,
                json=message,
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                logging.info(f"[NOTIFIER] Webhook 发送成功: {message['title']}")
            else:
                logging.warning(f"[NOTIFIER] Webhook 响应异常: {response.status_code}")
        
        except ImportError:
            logging.warning("[NOTIFIER] requests 库未安装，无法发送 Webhook")
        
        except Exception as e:
            logging.error(f"[NOTIFIER] Webhook 发送失败: {e}")
    
    def _send_email(self, message: Dict[str, Any]):
        """发送 Email 通知（占位实现）"""
        logging.info(f"[NOTIFIER] Email 通知（占位）: {message['title']}")
        
        # TODO: 实现真实的 Email 发送
        # 可以使用 smtplib 或第三方服务（SendGrid, Mailgun等）
        pass


# 全局通知器实例
_global_notifier: Optional[Notifier] = None


def get_notifier(config: Dict[str, Any] = None) -> Notifier:
    """获取全局通知器实例"""
    global _global_notifier
    if _global_notifier is None or config:
        _global_notifier = Notifier(config)
    return _global_notifier


__all__ = ['Notifier', 'get_notifier']

