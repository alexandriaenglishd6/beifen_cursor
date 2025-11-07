# -*- coding: utf-8 -*-
"""
影响范围检查工具 - 修改代码前检查影响范围
"""
from pathlib import Path
from typing import List, Dict, Set
import ast
import re


class ImpactAnalyzer:
    """
    影响范围分析器
    
    职责：
    1. 分析代码修改的影响范围
    2. 检查依赖关系
    3. 识别可能受影响的模块
    """
    
    def __init__(self, project_root: Path):
        """
        初始化
        
        Args:
            project_root: 项目根目录
        """
        self.project_root = project_root
        self.import_graph: Dict[str, Set[str]] = {}
        self.config_usage: Dict[str, List[str]] = {}
    
    def analyze_file(self, file_path: Path) -> Dict:
        """
        分析单个文件的影响范围
        
        Args:
            file_path: 文件路径
        
        Returns:
            影响范围分析结果
        """
        if not file_path.exists():
            return {"error": f"文件不存在: {file_path}"}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            # 分析导入
            imports = self._extract_imports(tree)
            
            # 分析配置使用
            config_usage = self._extract_config_usage(content)
            
            # 分析函数调用
            function_calls = self._extract_function_calls(tree)
            
            # 分析类定义
            classes = self._extract_classes(tree)
            
            return {
                "file": str(file_path.relative_to(self.project_root)),
                "imports": imports,
                "config_usage": config_usage,
                "function_calls": function_calls,
                "classes": classes,
                "dependencies": self._find_dependencies(file_path, imports)
            }
        except Exception as e:
            return {"error": f"分析失败: {e}"}
    
    def _extract_imports(self, tree: ast.AST) -> List[str]:
        """提取导入语句"""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")
        return imports
    
    def _extract_config_usage(self, content: str) -> List[str]:
        """提取配置使用"""
        patterns = [
            r'config\["([^"]+)"\]',
            r'config\.get\("([^"]+)"\)',
            r'save_config\(',
            r'load_config\(',
            r'config_service\.save',
            r'config_service\.load',
        ]
        
        usage = []
        for pattern in patterns:
            matches = re.findall(pattern, content)
            usage.extend(matches)
        
        return list(set(usage))
    
    def _extract_function_calls(self, tree: ast.AST) -> List[str]:
        """提取函数调用"""
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
        return list(set(calls))
    
    def _extract_classes(self, tree: ast.AST) -> List[str]:
        """提取类定义"""
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
        return classes
    
    def _find_dependencies(self, file_path: Path, imports: List[str]) -> List[str]:
        """查找依赖文件"""
        dependencies = []
        
        for imp in imports:
            # 简化处理：查找可能的依赖文件
            if imp.startswith("gui."):
                parts = imp.split(".")
                if len(parts) >= 2:
                    module_path = self.project_root / parts[1] / f"{parts[-1]}.py"
                    if module_path.exists():
                        dependencies.append(str(module_path.relative_to(self.project_root)))
        
        return dependencies
    
    def check_config_impact(self, config_key: str) -> Dict:
        """
        检查配置键的影响范围
        
        Args:
            config_key: 配置键（如 "network.cookiefile"）
        
        Returns:
            影响范围
        """
        affected_files = []
        
        # 搜索所有Python文件
        for py_file in self.project_root.rglob("*.py"):
            if "test" in str(py_file) or "__pycache__" in str(py_file):
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 检查是否使用该配置键
                if config_key in content or f'["{config_key}"]' in content:
                    affected_files.append(str(py_file.relative_to(self.project_root)))
            except:
                pass
        
        return {
            "config_key": config_key,
            "affected_files": affected_files,
            "count": len(affected_files)
        }
    
    def generate_impact_report(self, modified_files: List[str]) -> str:
        """
        生成影响范围报告
        
        Args:
            modified_files: 修改的文件列表
        
        Returns:
            报告文本
        """
        report = ["=" * 60]
        report.append("影响范围分析报告")
        report.append("=" * 60)
        report.append("")
        
        report.append(f"修改的文件 ({len(modified_files)}):")
        for file in modified_files:
            report.append(f"  - {file}")
        report.append("")
        
        # 分析每个文件
        all_dependencies = set()
        all_config_usage = set()
        
        for file_path_str in modified_files:
            file_path = self.project_root / file_path_str
            analysis = self.analyze_file(file_path)
            
            if "error" in analysis:
                report.append(f"⚠️ {file_path_str}: {analysis['error']}")
                continue
            
            report.append(f"文件: {file_path_str}")
            report.append(f"  导入: {len(analysis['imports'])} 个")
            report.append(f"  配置使用: {', '.join(analysis['config_usage']) if analysis['config_usage'] else '无'}")
            report.append(f"  依赖文件: {len(analysis['dependencies'])} 个")
            
            all_dependencies.update(analysis['dependencies'])
            all_config_usage.update(analysis['config_usage'])
            report.append("")
        
        if all_dependencies:
            report.append("可能受影响的依赖文件:")
            for dep in sorted(all_dependencies):
                report.append(f"  - {dep}")
            report.append("")
        
        if all_config_usage:
            report.append("涉及的配置项:")
            for config in sorted(all_config_usage):
                report.append(f"  - {config}")
            report.append("")
        
        report.append("=" * 60)
        
        return "\n".join(report)


__all__ = ['ImpactAnalyzer']
