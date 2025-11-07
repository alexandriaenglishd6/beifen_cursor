# -*- coding: utf-8 -*-
"""
core.config — 配置加载/默认值/向后兼容
"""
from __future__ import annotations
import os, json
from pathlib import Path
from typing import Any, Dict

def _resolve_env_vars(cfg: Dict[str, Any], warnings_list: list | None = None) -> Dict[str, Any]:
    """
    递归解析配置中的环境变量占位符
    
    支持格式：env:ENV_VAR_NAME
    例如：{"api_key": "env:OPENAI_API_KEY"}
    """
    if isinstance(cfg, dict):
        result = {}
        for k, v in cfg.items():
            if isinstance(v, str) and v.startswith("env:"):
                env_name = v[4:]  # 去掉 "env:" 前缀
                env_value = os.getenv(env_name, "")
                if not env_value:
                    if warnings_list is not None:
                        warnings_list.append(f"missing_env\t{env_name}")
                result[k] = env_value
            elif isinstance(v, (dict, list)):
                result[k] = _resolve_env_vars(v, warnings_list)
            else:
                result[k] = v
        return result
    elif isinstance(cfg, list):
        return [_resolve_env_vars(item, warnings_list) for item in cfg]
    else:
        return cfg

def load_config(path: str = "config.json", resolve_env: bool = True, warnings_list: list | None = None) -> Dict[str, Any]:
    """
    加载配置文件（支持向后兼容）
    
    参数：
    - path: 配置文件路径
    - resolve_env: 是否解析环境变量占位符
    - warnings_list: 可选的告警列表，用于收集缺失的环境变量
    """
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        
        if resolve_env:
            cfg = _resolve_env_vars(cfg, warnings_list)
        
        return cfg
    except Exception:
        return {}

def merge_config_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """合并默认配置值"""
    defaults = {
        "max_workers": 5,
        "sleep_between": 0.5,
        "retry_times": 2,
        "download_langs": ["zh", "en"],
        "download_prefer": "both",
        "download_fmt": "srt",
        "req_rate": 4.0,
        "breaker_threshold": 8,
        "breaker_cooldown_sec": 120.0,
        "ai": {
            "enabled": False,
            "max_chars_per_video": 30000,
            "chunk_chars": 4000,
            "merge_strategy": "map_reduce",
            "cache_enabled": True,
            "metrics_enabled": True,
            "max_tokens_per_run": 0,  # 0=无限制
            "max_daily_cost_usd": 0,  # 0=无限制
            "lang_pref": ["zh", "en"],
            "providers": []
        }
    }
    # 深度合并
    result = defaults.copy()
    for k, v in cfg.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = {**result[k], **v}
        else:
            result[k] = v
    return result

def save_json(path: Path, obj: Any):
    """保存 JSON 文件"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def save_config_snapshot(run_dir: str, config: Dict[str, Any]):
    """
    保存配置快照到运行目录
    
    便于复现和审计
    """
    try:
        snap_file = Path(run_dir) / "config.final.json"
        save_json(snap_file, config)
    except Exception:
        pass

