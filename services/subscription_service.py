# -*- coding: utf-8 -*-
"""
订阅服务 - 纯业务逻辑
"""
from typing import List, Dict, Optional
from copy import deepcopy


class SubscriptionService:
    """
    订阅服务
    
    职责：
    1. 管理订阅列表（增删改查）
    2. 订阅启用/禁用
    3. 订阅导入/导出
    """
    
    def __init__(self, config: Dict):
        """
        初始化
        
        Args:
            config: 全局配置
        """
        self.config = config
        self.subscriptions = config.get("subscriptions", [])
    
    def list_subscriptions(self) -> List[Dict]:
        """
        列出所有订阅
        
        Returns:
            订阅列表
        """
        return deepcopy(self.subscriptions)
    
    def get_subscription(self, sub_id: str) -> Optional[Dict]:
        """
        获取单个订阅
        
        Args:
            sub_id: 订阅ID
        
        Returns:
            订阅对象，如果不存在则返回None
        """
        for sub in self.subscriptions:
            if sub.get("id") == sub_id:
                return deepcopy(sub)
        return None
    
    def add_subscription(self, sub_data: Dict) -> str:
        """
        添加订阅
        
        Args:
            sub_data: 订阅数据
        
        Returns:
            订阅ID
        """
        import uuid
        
        # 生成ID
        sub_id = sub_data.get("id") or str(uuid.uuid4())[:8]
        
        # 构建订阅对象
        subscription = {
            "id": sub_id,
            "name": sub_data.get("name", "未命名订阅"),
            "url": sub_data.get("url", ""),
            "enabled": sub_data.get("enabled", True),
            "check_interval": sub_data.get("check_interval", "daily"),
            "download_langs": sub_data.get("download_langs", ["zh", "en"]),
            "last_check": None,
            "created_at": self._now_str()
        }
        
        self.subscriptions.append(subscription)
        self._save_to_config()
        
        return sub_id
    
    def update_subscription(self, sub_id: str, sub_data: Dict):
        """
        更新订阅
        
        Args:
            sub_id: 订阅ID
            sub_data: 订阅数据
        """
        for i, sub in enumerate(self.subscriptions):
            if sub.get("id") == sub_id:
                # 更新字段
                self.subscriptions[i].update({
                    "name": sub_data.get("name", sub["name"]),
                    "url": sub_data.get("url", sub["url"]),
                    "enabled": sub_data.get("enabled", sub["enabled"]),
                    "check_interval": sub_data.get("check_interval", sub["check_interval"]),
                    "download_langs": sub_data.get("download_langs", sub["download_langs"]),
                })
                self._save_to_config()
                return
        
        raise ValueError(f"订阅 {sub_id} 不存在")
    
    def delete_subscription(self, sub_id: str):
        """
        删除订阅
        
        Args:
            sub_id: 订阅ID
        """
        self.subscriptions = [sub for sub in self.subscriptions if sub.get("id") != sub_id]
        self._save_to_config()
    
    def toggle_subscription(self, sub_id: str, enabled: bool):
        """
        切换订阅状态
        
        Args:
            sub_id: 订阅ID
            enabled: 是否启用
        """
        for sub in self.subscriptions:
            if sub.get("id") == sub_id:
                sub["enabled"] = enabled
                self._save_to_config()
                return
        
        raise ValueError(f"订阅 {sub_id} 不存在")
    
    def import_subscriptions(self, file_path: str) -> int:
        """
        导入订阅
        
        Args:
            file_path: JSON文件路径
        
        Returns:
            导入数量
        """
        import json
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                imported = json.load(f)
            
            if not isinstance(imported, list):
                raise ValueError("导入文件格式错误")
            
            count = 0
            for sub in imported:
                try:
                    self.add_subscription(sub)
                    count += 1
                except Exception as e:
                    print(f"[SubscriptionService] 导入订阅失败: {e}")
            
            return count
            
        except Exception as e:
            raise Exception(f"导入失败: {e}")
    
    def export_subscriptions(self, file_path: str) -> int:
        """
        导出订阅
        
        Args:
            file_path: JSON文件路径
        
        Returns:
            导出数量
        """
        import json
        from pathlib import Path
        
        try:
            # 确保目录存在
            export_path = Path(file_path)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 准备导出数据（确保包含所有必要字段，格式统一）
            export_data = []
            for sub in self.subscriptions:
                # 构建完整的订阅数据（确保所有字段都存在）
                export_item = {
                    "id": sub.get("id", ""),
                    "name": sub.get("name", ""),
                    "url": sub.get("url", ""),
                    "enabled": sub.get("enabled", True),
                    "check_interval": sub.get("check_interval", "daily"),
                    "download_langs": sub.get("download_langs", ["zh", "en"]),
                    "last_check": sub.get("last_check"),
                    "created_at": sub.get("created_at", "")
                }
                # 添加其他可能存在的字段（如果有）
                for key in ["tags", "notes", "kind"]:
                    if key in sub:
                        export_item[key] = sub[key]
                
                export_data.append(export_item)
            
            # 写入文件（格式化JSON，确保中文字符正确显示）
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            return len(export_data)
            
        except Exception as e:
            raise Exception(f"导出失败: {e}")
    
    def _save_to_config(self):
        """保存到配置"""
        self.config["subscriptions"] = self.subscriptions
        
        # 保存配置文件
        from config_store import save_config
        save_config(self.config)
    
    def _now_str(self) -> str:
        """获取当前时间字符串"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


__all__ = ['SubscriptionService']

