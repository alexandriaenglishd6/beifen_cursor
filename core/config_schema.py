# -*- coding: utf-8 -*-
"""
配置Schema校验
确保配置值在合理范围内
"""
import logging
from typing import Dict, Any, List, Tuple


class ConfigValidator:
    """配置验证器"""
    
    # 配置规则
    RULES = {
        "asr.batch_size": {
            "type": int,
            "min": 1,
            "max": 64,
            "default": 16
        },
        "asr.max_dur_sec": {
            "type": int,
            "min": 120,
            "max": 1200,
            "default": 600
        },
        "asr.timeout_sec": {
            "type": int,
            "min": 60,
            "max": 7200,
            "default": 1800
        },
        "asr.device": {
            "type": str,
            "choices": ["auto", "cuda", "cpu"],
            "default": "auto"
        },
        "asr.compute_type": {
            "type": str,
            "choices": ["auto", "float16", "bfloat16", "int8_float16"],
            "default": "float16"
        },
        "asr.model_size": {
            "type": str,
            "choices": ["tiny", "base", "small", "medium", "large-v2"],
            "default": "medium"
        },
        "cache.max_size_gb": {
            "type": float,
            "min": 0.1,
            "max": 100.0,
            "default": 10.0
        },
        "cache.max_entries": {
            "type": int,
            "min": 10,
            "max": 10000,
            "default": 1000
        },
        "cache.ttl_days": {
            "type": int,
            "min": 1,
            "max": 365,
            "default": 30
        },
        "scheduler.max_concurrency": {
            "type": int,
            "min": 1,
            "max": 20,
            "default": 3
        }
    }
    
    @classmethod
    def validate(cls, config: Dict, fix: bool = True) -> Tuple[Dict, List[str]]:
        """
        验证配置
        
        Args:
            config: 配置字典
            fix: 是否自动修复无效值
        
        Returns:
            (修复后的配置, 错误列表)
        """
        errors = []
        fixed_config = config.copy()
        
        for path, rule in cls.RULES.items():
            try:
                # 获取嵌套值
                keys = path.split('.')
                value = fixed_config
                parent = None
                last_key = keys[-1]
                
                for key in keys[:-1]:
                    parent = value
                    value = value.get(key, {})
                    if not isinstance(value, dict):
                        value = {}
                        parent[key] = value
                
                current_value = value.get(last_key)
                
                # 类型检查
                expected_type = rule["type"]
                if current_value is None:
                    if fix:
                        value[last_key] = rule["default"]
                        errors.append(f"{path}: 缺失，使用默认值 {rule['default']}")
                    else:
                        errors.append(f"{path}: 缺失")
                    continue
                
                # 类型转换
                if not isinstance(current_value, expected_type):
                    try:
                        current_value = expected_type(current_value)
                        value[last_key] = current_value
                    except:
                        if fix:
                            value[last_key] = rule["default"]
                            errors.append(f"{path}: 类型错误，使用默认值 {rule['default']}")
                        else:
                            errors.append(f"{path}: 类型错误")
                        continue
                
                # 范围检查
                if "min" in rule and current_value < rule["min"]:
                    if fix:
                        value[last_key] = rule["min"]
                        errors.append(f"{path}: {current_value} < {rule['min']}，已调整")
                    else:
                        errors.append(f"{path}: {current_value} < {rule['min']}")
                
                if "max" in rule and current_value > rule["max"]:
                    if fix:
                        value[last_key] = rule["max"]
                        errors.append(f"{path}: {current_value} > {rule['max']}，已调整")
                    else:
                        errors.append(f"{path}: {current_value} > {rule['max']}")
                
                # 枚举检查
                if "choices" in rule and current_value not in rule["choices"]:
                    if fix:
                        value[last_key] = rule["default"]
                        errors.append(f"{path}: {current_value} 不在选项中，使用默认值 {rule['default']}")
                    else:
                        errors.append(f"{path}: {current_value} 不在选项 {rule['choices']} 中")
            
            except Exception as e:
                errors.append(f"{path}: 验证异常 - {e}")
        
        if errors:
            logging.warning(f"[CONFIG] 发现{len(errors)}个配置问题：")
            for error in errors:
                logging.warning(f"  - {error}")
        else:
            logging.info("[CONFIG] 配置校验通过")
        
        return fixed_config, errors
    
    @classmethod
    def validate_path_writable(cls, path: str) -> bool:
        """
        验证路径可写
        
        Args:
            path: 路径
        
        Returns:
            是否可写
        """
        import os
        from pathlib import Path
        
        try:
            p = Path(path)
            p.mkdir(parents=True, exist_ok=True)
            
            # 尝试创建测试文件
            test_file = p / ".write_test"
            test_file.touch()
            test_file.unlink()
            
            return True
        
        except Exception as e:
            logging.error(f"[CONFIG] 路径 {path} 不可写: {e}")
            return False

