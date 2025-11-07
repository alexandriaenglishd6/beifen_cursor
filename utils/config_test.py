# -*- coding: utf-8 -*-
"""
配置保存/加载测试工具
"""
from pathlib import Path
from typing import Dict, Any, List
import json
import shutil
import sys
import io

# Windows编码修复
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        pass

from config_store import load_config, save_config, health_check


class ConfigTestSuite:
    """
    配置测试套件
    
    职责：
    1. 测试配置保存/加载
    2. 验证配置完整性
    3. 检测配置丢失
    """
    
    def __init__(self, project_root: Path):
        """
        初始化
        
        Args:
            project_root: 项目根目录
        """
        self.project_root = project_root
        self.config_path = project_root / "config" / "config.json"
        self.backup_path = project_root / "config" / "config.test_backup.json"
    
    def backup_config(self):
        """备份当前配置"""
        if self.config_path.exists():
            shutil.copy2(self.config_path, self.backup_path)
            print(f"[ConfigTest] 配置已备份到: {self.backup_path}")
        else:
            print("[ConfigTest] 配置文件不存在，无需备份")
    
    def restore_config(self):
        """恢复配置"""
        if self.backup_path.exists():
            shutil.copy2(self.backup_path, self.config_path)
            print(f"[ConfigTest] 配置已从备份恢复")
        else:
            print("[ConfigTest] 备份文件不存在，无法恢复")
    
    def test_save_load(self) -> Dict[str, Any]:
        """
        测试配置保存/加载
        
        Returns:
            测试结果
        """
        print("[ConfigTest] 开始测试配置保存/加载...")
        
        # 备份当前配置
        self.backup_config()
        
        try:
            # 1. 加载当前配置
            original_config = load_config()
            print(f"[ConfigTest] 加载原始配置成功")
            
            # 2. 修改配置
            test_config = original_config.copy()
            test_config["test"] = {"timestamp": "test_value"}
            
            # 3. 保存配置
            save_config(test_config)
            print(f"[ConfigTest] 保存测试配置成功")
            
            # 4. 重新加载配置
            loaded_config = load_config()
            print(f"[ConfigTest] 重新加载配置成功")
            
            # 5. 验证配置
            if "test" not in loaded_config:
                return {
                    "success": False,
                    "error": "测试配置项丢失"
                }
            
            if loaded_config["test"]["timestamp"] != "test_value":
                return {
                    "success": False,
                    "error": "测试配置项值不匹配"
                }
            
            # 6. 恢复原始配置
            save_config(original_config)
            print(f"[ConfigTest] 恢复原始配置成功")
            
            return {
                "success": True,
                "message": "配置保存/加载测试通过"
            }
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            # 清理测试配置项
            try:
                config = load_config()
                if "test" in config:
                    del config["test"]
                    save_config(config)
            except:
                pass
    
    def test_config_sections(self) -> Dict[str, Any]:
        """
        测试各个配置段的保存/加载
        
        Returns:
            测试结果
        """
        print("[ConfigTest] 开始测试配置段保存/加载...")
        
        sections = ["network", "run", "ai", "ui"]
        results = {}
        
        for section in sections:
            try:
                # 加载配置
                config = load_config()
                
                # 检查配置段是否存在
                if section not in config:
                    results[section] = {
                        "success": False,
                        "error": f"配置段 '{section}' 不存在"
                    }
                    continue
                
                # 保存配置
                save_config(config)
                
                # 重新加载
                loaded_config = load_config()
                
                # 验证
                if section not in loaded_config:
                    results[section] = {
                        "success": False,
                        "error": f"配置段 '{section}' 保存后丢失"
                    }
                    continue
                
                # 比较配置
                original_section = config[section]
                loaded_section = loaded_config[section]
                
                if original_section != loaded_section:
                    results[section] = {
                        "success": False,
                        "error": f"配置段 '{section}' 值不匹配"
                    }
                    continue
                
                results[section] = {
                    "success": True,
                    "message": f"配置段 '{section}' 测试通过"
                }
                print(f"[ConfigTest] {section} 配置段测试通过")
            
            except Exception as e:
                results[section] = {
                    "success": False,
                    "error": str(e)
                }
                print(f"[ConfigTest] ✗ {section} 配置段测试失败: {e}")
        
        return {
            "success": all(r.get("success", False) for r in results.values()),
            "results": results
        }
    
    def test_health_check(self) -> Dict[str, Any]:
        """
        测试健康检查
        
        Returns:
            测试结果
        """
        print("[ConfigTest] 开始测试健康检查...")
        
        issues = health_check()
        
        return {
            "success": len(issues) == 0,
            "issues": issues,
            "count": len(issues)
        }
    
    def run_all_tests(self) -> Dict[str, Any]:
        """
        运行所有测试
        
        Returns:
            测试结果
        """
        print("=" * 60)
        print("配置测试套件")
        print("=" * 60)
        print("")
        
        results = {
            "save_load": self.test_save_load(),
            "sections": self.test_config_sections(),
            "health": self.test_health_check()
        }
        
        print("")
        print("=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        
        all_passed = all(
            r.get("success", False) if isinstance(r, dict) else False
            for r in results.values()
        )
        
        if all_passed:
            print("所有测试通过")
        else:
            print("部分测试失败")
            for test_name, result in results.items():
                if isinstance(result, dict) and not result.get("success", False):
                    print(f"  - {test_name}: {result.get('error', '未知错误')}")
        
        print("=" * 60)
        
        return {
            "success": all_passed,
            "results": results
        }


__all__ = ['ConfigTestSuite']
