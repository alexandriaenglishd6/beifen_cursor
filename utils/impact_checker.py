# -*- coding: utf-8 -*-
"""
代码修改前影响范围检查工具
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
import re
import ast


class ImpactChecker:
    """
    影响范围检查器
    
    用于在修改代码前检查影响范围
    """
    
    def __init__(self, project_root: str = None):
        """
        初始化
        
        Args:
            project_root: 项目根目录（默认当前目录）
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.impact_map: Dict[str, List[str]] = {}
    
    def check_file(self, file_path: str) -> Dict[str, Any]:
        """
        检查文件修改的影响范围
        
        Args:
            file_path: 文件路径
        
        Returns:
            影响范围分析结果
        """
        file = Path(file_path)
        if not file.is_absolute():
            file = self.project_root / file
        
        if not file.exists():
            return {"error": f"文件不存在: {file}"}
        
        try:
            content = file.read_text(encoding='utf-8')
        except Exception as e:
            return {"error": f"读取文件失败: {e}"}
        
        result = {
            "file": str(file),
            "imports": [],
            "exports": [],
            "dependencies": [],
            "potential_issues": [],
            "affected_files": [],
            "risk_level": "low"
        }
        
        # 分析导入
        imports = self._extract_imports(content)
        result["imports"] = imports
        
        # 分析导出的类/函数
        exports = self._extract_exports(content)
        result["exports"] = exports
        
        # 查找依赖此文件的其他文件
        result["affected_files"] = self._find_dependent_files(file)
        
        # 检查潜在问题
        issues = self._check_potential_issues(content, file)
        result["potential_issues"] = issues
        
        # 评估风险等级
        result["risk_level"] = self._assess_risk(result)
        
        return result
    
    def _extract_imports(self, content: str) -> List[str]:
        """提取导入语句"""
        imports = []
        import_pattern = r'^from\s+(\S+)\s+import|^import\s+(\S+)'
        
        for line in content.split('\n'):
            match = re.match(import_pattern, line.strip())
            if match:
                module = match.group(1) or match.group(2)
                imports.append(module)
        
        return imports
    
    def _extract_exports(self, content: str) -> List[str]:
        """提取导出的类/函数"""
        exports = []
        
        # 提取类
        class_pattern = r'^class\s+(\w+)'
        for line in content.split('\n'):
            match = re.match(class_pattern, line.strip())
            if match:
                exports.append(f"class:{match.group(1)}")
        
        # 提取顶级函数
        func_pattern = r'^def\s+(\w+)'
        for line in content.split('\n'):
            match = re.match(func_pattern, line.strip())
            if match and not line.strip().startswith('    '):  # 顶级函数
                exports.append(f"function:{match.group(1)}")
        
        return exports
    
    def _find_dependent_files(self, target_file: Path) -> List[str]:
        """查找依赖此文件的其他文件"""
        dependent_files = []
        
        # 获取目标文件的模块名
        rel_path = target_file.relative_to(self.project_root)
        module_parts = rel_path.with_suffix('').parts
        
        # 搜索所有Python文件
        for py_file in self.project_root.rglob("*.py"):
            if py_file == target_file:
                continue
            
            try:
                content = py_file.read_text(encoding='utf-8')
                
                # 检查是否导入此模块
                module_name = '.'.join(module_parts)
                if module_name in content or str(rel_path).replace('\\', '/') in content:
                    dependent_files.append(str(py_file.relative_to(self.project_root)))
            except:
                pass
        
        return dependent_files
    
    def _check_potential_issues(self, content: str, file_path: Path) -> List[str]:
        """检查潜在问题"""
        issues = []
        
        # 检查使用 root.after()
        if 'root.after(' in content:
            count = content.count('root.after(')
            if count > 5:
                issues.append(f"大量使用 root.after() ({count}次)，可能存在时序问题")
            else:
                issues.append("使用了 root.after()，可能存在时序问题")
        
        # 检查配置保存/加载
        if 'load_config' in content and 'save_config' in content:
            issues.append("同时包含配置加载和保存，需要检查是否会导致冲突")
        
        # 检查大量使用 hasattr
        hasattr_count = content.count('hasattr')
        if hasattr_count > 5:
            issues.append(f"大量使用 hasattr ({hasattr_count}次)，可能存在懒加载时序问题")
        
        # 检查异常处理
        if content.count('except:') > content.count('except Exception'):
            issues.append("使用了裸 except，可能掩盖错误")
        
        # 检查延迟初始化
        if 'root.after(' in content and 'load_config' in content:
            issues.append("延迟初始化配置加载，需要确保时序正确")
        
        return issues
    
    def _assess_risk(self, result: Dict[str, Any]) -> str:
        """评估风险等级"""
        risk_score = 0
        
        # 受影响文件数量
        if len(result["affected_files"]) > 5:
            risk_score += 2
        elif len(result["affected_files"]) > 0:
            risk_score += 1
        
        # 潜在问题数量
        risk_score += len(result["potential_issues"])
        
        # 导出数量（影响范围）
        if len(result["exports"]) > 10:
            risk_score += 1
        
        if risk_score >= 5:
            return "high"
        elif risk_score >= 3:
            return "medium"
        else:
            return "low"
    
    def generate_report(self, file_path: str) -> str:
        """
        生成影响范围报告
        
        Args:
            file_path: 文件路径
        
        Returns:
            报告文本
        """
        result = self.check_file(file_path)
        
        if "error" in result:
            return f"错误: {result['error']}"
        
        report = []
        report.append("=" * 60)
        report.append(f"影响范围分析报告: {result['file']}")
        report.append("=" * 60)
        report.append("")
        
        # 风险等级
        risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        report.append(f"风险等级: {risk_emoji.get(result['risk_level'], '⚪')} {result['risk_level'].upper()}")
        report.append("")
        
        # 导出项
        if result["exports"]:
            report.append(f"导出的类/函数 ({len(result['exports'])}):")
            for export in result["exports"][:10]:  # 只显示前10个
                report.append(f"  - {export}")
            if len(result["exports"]) > 10:
                report.append(f"  ... 还有 {len(result['exports']) - 10} 个")
            report.append("")
        
        # 受影响文件
        if result["affected_files"]:
            report.append(f"可能受影响的文件 ({len(result['affected_files'])}):")
            for dep_file in result["affected_files"][:10]:  # 只显示前10个
                report.append(f"  - {dep_file}")
            if len(result["affected_files"]) > 10:
                report.append(f"  ... 还有 {len(result['affected_files']) - 10} 个")
            report.append("")
        
        # 潜在问题
        if result["potential_issues"]:
            report.append("⚠️ 潜在问题:")
            for issue in result["potential_issues"]:
                report.append(f"  - {issue}")
            report.append("")
        
        # 建议
        report.append("💡 建议:")
        if result["risk_level"] == "high":
            report.append("  - 修改前仔细检查所有受影响文件")
            report.append("  - 修改后进行完整测试")
            report.append("  - 考虑分步骤修改")
        elif result["risk_level"] == "medium":
            report.append("  - 修改前检查主要受影响文件")
            report.append("  - 修改后进行相关功能测试")
        else:
            report.append("  - 修改后运行基本测试")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)


def check_before_modify(file_path: str, project_root: str = None) -> None:
    """
    修改代码前检查影响范围（便捷函数）
    
    Args:
        file_path: 要修改的文件路径
        project_root: 项目根目录
    """
    checker = ImpactChecker(project_root)
    report = checker.generate_report(file_path)
    print(report)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        check_before_modify(sys.argv[1])
    else:
        print("用法: python impact_checker.py <文件路径>")

