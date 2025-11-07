# -*- coding: utf-8 -*-
"""
配置服务 - 统一管理应用配置的保存和加载
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional
import json
import os
from config_store import load_config as _load_config, save_config as _save_config, DEFAULTS


class ConfigService:
    """
    配置服务
    
    职责：
    1. 统一管理所有模块的配置
    2. 提供配置保存/加载接口
    3. 维护配置结构的一致性
    """
    
    def __init__(self):
        """初始化配置服务"""
        self.config_path = Path.cwd() / "config" / "config.json"
        self._config: Dict[str, Any] = {}
        self._load()
    
    def _load(self):
        """加载配置文件"""
        try:
            self._config = _load_config()
            # 验证加载的AI配置
            ai_section = self._config.get("ai", {})
            api_key = ai_section.get("api_key", "")
            print(f"[ConfigService._load] 加载配置后验证 - ai.api_key: {'***' if api_key else '(空)'}, 长度: {len(api_key)}")
        except Exception as e:
            print(f"[ConfigService] 加载配置失败，使用默认配置: {e}")
            self._config = DEFAULTS.copy()
    
    def get(self, section: str = None, key: str = None, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            section: 配置段（如 "download", "ai", "network"）
            key: 配置键（如 "output_root", "provider"）
            default: 默认值
        
        Returns:
            配置值
        """
        if section is None:
            return self._config
        
        if key is None:
            return self._config.get(section, default if default is not None else {})
        
        section_config = self._config.get(section, {})
        if isinstance(section_config, dict):
            return section_config.get(key, default)
        
        return default
    
    def set(self, section: str, key: str = None, value: Any = None):
        """
        设置配置值
        
        Args:
            section: 配置段
            key: 配置键（如果为None，则value应该是整个section的字典）
            value: 配置值
        """
        if section not in self._config:
            self._config[section] = {}
        
        if key is None:
            # 设置整个section
            if isinstance(value, dict):
                print(f"[ConfigService.set] 设置整个section '{section}', api_key: {'***' if value.get('api_key') else '(空)'}")
                self._config[section] = value.copy()  # 使用copy避免引用问题
                print(f"[ConfigService.set] 设置后，self._config['{section}']['api_key']: {'***' if self._config[section].get('api_key') else '(空)'}")
            else:
                raise ValueError(f"当key为None时，value必须是字典类型")
        else:
            # 设置单个键值
            if not isinstance(self._config[section], dict):
                self._config[section] = {}
            self._config[section][key] = value
    
    def update(self, section: str, updates: Dict[str, Any]):
        """
        更新配置段（合并更新）
        
        Args:
            section: 配置段
            updates: 要更新的键值对
        """
        if section not in self._config:
            self._config[section] = {}
        
        if isinstance(self._config[section], dict):
            # 打印调试信息
            if section == "network" and "cookiefile" in updates:
                print(f"[ConfigService.update] 更新network.cookiefile:")
                print(f"  - 原始值: {updates.get('cookiefile', '')}")
                print(f"  - 长度: {len(updates.get('cookiefile', ''))}")
            
            # 合并更新
            self._config[section].update(updates)
            
            # 验证更新结果
            if section == "network" and "cookiefile" in updates:
                saved_value = self._config[section].get("cookiefile", "")
                print(f"[ConfigService.update] 更新后验证:")
                print(f"  - 保存的值: {saved_value}")
                print(f"  - 长度: {len(saved_value)}")
        else:
            self._config[section] = updates
    
    def save(self):
        """保存配置到文件"""
        try:
            # 验证保存前的配置
            ai_section = self._config.get("ai", {})
            api_key_before_save = ai_section.get("api_key", "")
            print(f"[ConfigService.save] 保存前验证 - ai.api_key: {'***' if api_key_before_save else '(空)'}")
            
            # 验证network配置中的cookiefile
            network_section = self._config.get("network", {})
            cookiefile_before_save = network_section.get("cookiefile", "")
            print(f"[ConfigService.save] 保存前验证 - network.cookiefile: {cookiefile_before_save}")
            print(f"[ConfigService.save] 保存前验证 - network.cookiefile长度: {len(cookiefile_before_save)}")
            
            _save_config(self._config)
            print(f"[ConfigService] 配置已保存: {self.config_path}")
            
            # 验证保存后的配置文件
            import json
            saved_content = json.loads(self.config_path.read_text(encoding="utf-8"))
            saved_api_key = saved_content.get("ai", {}).get("api_key", "")
            print(f"[ConfigService.save] 保存后验证配置文件 - ai.api_key: {'***' if saved_api_key else '(空)'}")
            
            # 验证保存后的network配置中的cookiefile
            saved_network = saved_content.get("network", {})
            saved_cookiefile = saved_network.get("cookiefile", "")
            print(f"[ConfigService.save] 保存后验证配置文件 - network.cookiefile: {saved_cookiefile}")
            print(f"[ConfigService.save] 保存后验证配置文件 - network.cookiefile长度: {len(saved_cookiefile)}")
            
            return True
        except Exception as e:
            print(f"[ConfigService] 保存配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_all(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self._config.copy()
    
    def load_download_config(self) -> Dict[str, Any]:
        """
        加载下载模块配置
        
        Returns:
            下载配置字典
        """
        return {
            "output_root": self.get("download", "output_root", "out"),
            "download_langs": self.get("download", "download_langs", ["zh", "en"]),
            "download_fmt": self.get("download", "download_fmt", "srt"),
            "max_workers": self.get("download", "max_workers", 3),
            # 高级选项默认值（与UI保持一致）
            "merge_bilingual": self.get("download", "merge_bilingual", True),
            "incremental_detect": self.get("download", "incremental_detect", True),
            "incremental_download": self.get("download", "incremental_download", True),
            "force_refresh": self.get("download", "force_refresh", False),
            "early_stop_on_seen": self.get("download", "early_stop_on_seen", True),
        }
    
    def save_download_config(self, config: Dict[str, Any]):
        """
        保存下载模块配置
        
        Args:
            config: 下载配置字典
        """
        self.update("download", {
            "output_root": config.get("output_root", "out"),
            "download_langs": config.get("download_langs", ["zh", "en"]),
            "download_fmt": config.get("download_fmt", "srt"),
            "max_workers": config.get("max_workers", 3),
            # 高级选项（保存UI设置的值）
            "merge_bilingual": config.get("merge_bilingual", True),
            "incremental_detect": config.get("incremental_detect", True),
            "incremental_download": config.get("incremental_download", True),
            "force_refresh": config.get("force_refresh", False),
            "early_stop_on_seen": config.get("early_stop_on_seen", True),
        })
    
    def load_ai_config(self) -> Dict[str, Any]:
        """
        加载AI模块配置
        
        Returns:
            AI配置字典
        """
        ai_section = self.get("ai") or {}  # 修复：使用 or {} 而不是传入 {} 作为默认值
        api_key = ai_section.get("api_key", "") if isinstance(ai_section, dict) else ""
        print(f"[ConfigService.load_ai_config] 加载AI配置 - api_key: {'***' if api_key else '(空)'}, 长度: {len(api_key)}")
        print(f"[ConfigService.load_ai_config] ai_section类型: {type(ai_section)}, 键: {list(ai_section.keys()) if isinstance(ai_section, dict) else 'N/A'}")
        
        return {
            "enabled": ai_section.get("enabled", False) if isinstance(ai_section, dict) else False,
            "provider": ai_section.get("provider", "GPT") if isinstance(ai_section, dict) else "GPT",
            "model": ai_section.get("model", "gpt-5") if isinstance(ai_section, dict) else "gpt-5",
            "api_key": api_key,
            "base_url": ai_section.get("base_url", "") if isinstance(ai_section, dict) else "",
            "translate_enabled": ai_section.get("translate_enabled", False) if isinstance(ai_section, dict) else False,
            "translate_langs": ai_section.get("translate_langs", ["zh", "en"]) if isinstance(ai_section, dict) else ["zh", "en"],
            "bilingual_enabled": ai_section.get("bilingual_enabled", False) if isinstance(ai_section, dict) else False,
        }
    
    def save_ai_config(self, config: Dict[str, Any]):
        """
        保存AI模块配置
        
        Args:
            config: AI配置字典
        """
        api_key = config.get("api_key", "")
        api_key_str = str(api_key) if api_key else ""
        
        print(f"[ConfigService.save_ai_config] 接收到的配置:")
        print(f"  - provider: {config.get('provider')}")
        print(f"  - model: {config.get('model')}")
        print(f"  - api_key类型: {type(api_key)}, 长度: {len(api_key_str)}, 值: {'***' if api_key_str else '(空)'}")
        print(f"  - api_key原始值前10字符: {repr(api_key_str[:10]) if api_key_str else '(空)'}")
        
        ai_config_dict = {
            "enabled": config.get("enabled", False),
            "provider": config.get("provider", "GPT"),
            "model": config.get("model", "gpt-5"),
            "api_key": api_key_str,  # 确保是字符串
            "base_url": config.get("base_url", ""),
            "translate_enabled": config.get("translate_enabled", False),
            "translate_langs": config.get("translate_langs", ["zh", "en"]),
            "bilingual_enabled": config.get("bilingual_enabled", False),
        }
        
        print(f"[ConfigService.save_ai_config] 准备设置的配置 - api_key: {'***' if api_key_str else '(空)'}")
        
        self.set("ai", None, ai_config_dict)
        
        # 验证设置是否成功
        saved_api_key = self.get("ai", "api_key", "")
        print(f"[ConfigService.save_ai_config] 设置后验证 - api_key: {'***' if saved_api_key else '(空)'}")
    
    def load_network_config(self) -> Dict[str, Any]:
        """
        加载网络配置
        
        Returns:
            网络配置字典
        """
        network_section = self.get("network") or {}
        if not isinstance(network_section, dict):
            network_section = {}
        
        cookiefile = network_section.get("cookiefile", "")
        print(f"[ConfigService.load_network_config] 加载网络配置:")
        print(f"  - cookiefile原始值: {cookiefile}")
        print(f"  - cookiefile长度: {len(cookiefile)}")
        print(f"  - network_section keys: {list(network_section.keys())}")
        
        return {
            "proxy_text": network_section.get("proxy_text", ""),
            "cookiefile": cookiefile,
            "user_agent": network_section.get("user_agent", ""),
            "timeout": network_section.get("timeout", 30),
            "retry_times": network_section.get("retry_times", 2),
            "verify_ssl": network_section.get("verify_ssl", True),
            "follow_redirects": network_section.get("follow_redirects", True),
            "debug": network_section.get("debug", False),
            "save_history": network_section.get("save_history", True),
        }
    
    def save_network_config(self, config: Dict[str, Any]):
        """
        保存网络配置
        
        Args:
            config: 网络配置字典
        """
        self.update("network", {
            "proxy_text": config.get("proxy_text", ""),
            "cookiefile": config.get("cookiefile", ""),
            "user_agent": config.get("user_agent", ""),
            "timeout": config.get("timeout", 30),
            "retry_times": config.get("retry_times", 2),
            "verify_ssl": config.get("verify_ssl", True),
            "follow_redirects": config.get("follow_redirects", True),
            "debug": config.get("debug", False),
            "save_history": config.get("save_history", True),
        })


# 单例模式
_config_service: Optional[ConfigService] = None

def get_config_service() -> ConfigService:
    """获取配置服务单例"""
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service

