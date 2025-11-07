# -*- coding: utf-8 -*-
"""
开发工作流工具 - 修改代码前检查影响范围，修改后测试配置
"""
from __future__ import annotations
import sys
from pathlib import Path

# 添加utils目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.impact_checker import ImpactChecker, check_before_modify
from utils.config_test import ConfigTestRunner, run_config_tests


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  检查影响范围: python dev_workflow.py check <文件路径>")
        print("  运行配置测试: python dev_workflow.py test")
        print("  完整流程: python dev_workflow.py full <文件路径>")
        return
    
    command = sys.argv[1]
    
    if command == "check":
        if len(sys.argv) < 3:
            print("错误: 需要指定文件路径")
            print("用法: python dev_workflow.py check <文件路径>")
            return
        
        file_path = sys.argv[2]
        print("=" * 60)
        print("🔍 影响范围检查")
        print("=" * 60)
        print()
        check_before_modify(file_path)
    
    elif command == "test":
        print("=" * 60)
        print("🧪 配置保存/加载测试")
        print("=" * 60)
        print()
        exit_code = run_config_tests()
        sys.exit(exit_code)
    
    elif command == "full":
        if len(sys.argv) < 3:
            print("错误: 需要指定文件路径")
            print("用法: python dev_workflow.py full <文件路径>")
            return
        
        file_path = sys.argv[2]
        
        # 步骤1: 检查影响范围
        print("=" * 60)
        print("步骤 1: 影响范围检查")
        print("=" * 60)
        print()
        check_before_modify(file_path)
        print()
        
        # 步骤2: 运行配置测试
        print("=" * 60)
        print("步骤 2: 配置保存/加载测试")
        print("=" * 60)
        print()
        exit_code = run_config_tests()
        
        if exit_code == 0:
            print()
            print("=" * 60)
            print("✅ 所有检查通过，可以继续修改代码")
            print("=" * 60)
        else:
            print()
            print("=" * 60)
            print("❌ 测试失败，请修复问题后再继续")
            print("=" * 60)
        
        sys.exit(exit_code)
    
    else:
        print(f"错误: 未知命令 '{command}'")
        print("用法:")
        print("  检查影响范围: python dev_workflow.py check <文件路径>")
        print("  运行配置测试: python dev_workflow.py test")
        print("  完整流程: python dev_workflow.py full <文件路径>")


if __name__ == "__main__":
    main()

