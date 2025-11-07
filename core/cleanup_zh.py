# -*- coding: utf-8 -*-
"""
A2: 中文清洗与术语统一管线
在 A1 质量优化基础上，增加术语规范化能力
"""
from __future__ import annotations
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Tuple

# 复用 A1 的基础清洗能力
try:
    from .quality_postprocess import (
        remove_noise,
        normalize_punctuation,
        is_chinese_text,
        NOISE_PATTERNS
    )
except ImportError:
    # 兼容直接导入
    from quality_postprocess import (
        remove_noise,
        normalize_punctuation,
        is_chinese_text,
        NOISE_PATTERNS
    )


def load_terminology(terminology_file: str = "terminology.json") -> Dict[str, Dict[str, str]]:
    """
    加载术语映射表
    
    Args:
        terminology_file: 术语文件路径
    
    Returns:
        术语映射字典
    """
    try:
        # 尝试从多个位置加载
        possible_paths = [
            Path(terminology_file),
            Path(__file__).parent.parent / terminology_file,
            Path.cwd() / terminology_file
        ]
        
        for path in possible_paths:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 过滤掉注释字段
                    return {k: v for k, v in data.items() if not k.startswith('_')}
        
        logging.warning(f"[CLEANUP] 术语文件未找到: {terminology_file}，使用空映射")
        return {}
    
    except Exception as e:
        logging.warning(f"[CLEANUP] 加载术语文件失败: {e}")
        return {}


def apply_terminology(text: str, terminology: Dict[str, Dict[str, str]]) -> Tuple[str, int]:
    """
    应用术语统一规则
    
    Args:
        text: 原始文本
        terminology: 术语映射字典
    
    Returns:
        (处理后的文本, 替换次数)
    """
    if not text or not terminology:
        return text, 0
    
    result = text
    replace_count = 0
    
    # 遍历所有术语分类
    for category, terms in terminology.items():
        for source, target in terms.items():
            # 如果源词和目标词相同，跳过
            if source == target:
                continue
            
            # 执行替换（区分大小写）
            if source in result:
                count = result.count(source)
                result = result.replace(source, target)
                replace_count += count
    
    return result, replace_count


def clean_zh_line(line: str, terminology: Dict[str, Dict[str, str]] = None) -> Tuple[str, Dict]:
    """
    清洗单行中文字幕（A2 增强版）
    
    处理流程：
    1. A1 基础清洗（去噪、标点）
    2. A2 术语统一
    
    Args:
        line: 原始行
        terminology: 术语映射表
    
    Returns:
        (清洗后的行, 统计信息)
    """
    stats = {
        "noise_removed": False,
        "punctuation_fixed": False,
        "terminology_replaced": 0
    }
    
    if not line or not line.strip():
        return line, stats
    
    # 只处理中文文本
    if not is_chinese_text(line):
        return line, stats
    
    result = line
    
    # 1. A1 基础清洗
    original = result
    result = remove_noise(result)
    if result != original:
        stats["noise_removed"] = True
    
    original = result
    result = normalize_punctuation(result)
    if result != original:
        stats["punctuation_fixed"] = True
    
    # 2. A2 术语统一
    if terminology:
        original = result
        result, replace_count = apply_terminology(result, terminology)
        stats["terminology_replaced"] = replace_count
    
    return result, stats


def merge_short_zh_lines(lines: List[str], min_length: int = 15, max_length: int = 40) -> List[str]:
    """
    合并过短的中文句子（A2 优化阈值）
    
    相比 A1，A2 提高了最小长度阈值（8→15），确保句子更完整
    
    Args:
        lines: 原始行列表
        min_length: 最小行长度
        max_length: 最大合并长度
    
    Returns:
        合并后的行列表
    """
    if not lines:
        return lines
    
    result = []
    buffer = ""
    
    for line in lines:
        line = line.strip()
        
        if not line:
            if buffer:
                result.append(buffer)
                buffer = ""
            continue
        
        # 如果缓冲区为空，直接加入
        if not buffer:
            buffer = line
            continue
        
        # 检查缓冲区是否已经是完整句子
        if buffer[-1] in '。！？':
            result.append(buffer)
            buffer = line
            continue
        
        # 尝试合并
        merged = buffer + line
        
        # 如果合并后太长，分别输出
        if len(merged) > max_length:
            result.append(buffer)
            buffer = line
        else:
            # 合并成功
            buffer = merged
    
    # 处理最后的缓冲区
    if buffer:
        result.append(buffer)
    
    return result


def clean_zh_lines(
    lines: List[str],
    terminology: Dict[str, Dict[str, str]] = None,
    merge_enabled: bool = True
) -> Tuple[List[str], Dict]:
    """
    批量清洗中文字幕行（A2 主函数）
    
    Args:
        lines: 原始字幕行列表
        terminology: 术语映射表
        merge_enabled: 是否启用句子合并
    
    Returns:
        (清洗后的行列表, 统计信息)
    """
    stats = {
        "original_lines": len(lines),
        "noise_removed": 0,
        "punctuation_fixed": 0,
        "terminology_replaced": 0,
        "lines_merged": 0,
        "final_lines": 0,
        "chinese_lines": 0
    }
    
    # 第一阶段：逐行清洗
    cleaned = []
    for line in lines:
        if not line.strip():
            continue
        
        # 检测是否中文
        if is_chinese_text(line):
            stats["chinese_lines"] += 1
            
            # 清洗
            cleaned_line, line_stats = clean_zh_line(line, terminology)
            
            # 累计统计
            if line_stats["noise_removed"]:
                stats["noise_removed"] += 1
            if line_stats["punctuation_fixed"]:
                stats["punctuation_fixed"] += 1
            stats["terminology_replaced"] += line_stats["terminology_replaced"]
            
            if cleaned_line:
                cleaned.append(cleaned_line)
        else:
            # 非中文行：检查是否为噪音
            cleaned_non_chinese = remove_noise(line)
            if cleaned_non_chinese and cleaned_non_chinese.strip():
                cleaned.append(line)
            else:
                stats["noise_removed"] += 1
    
    # 第二阶段：合并短句
    if merge_enabled:
        original_count = len(cleaned)
        merged = merge_short_zh_lines(cleaned, min_length=15, max_length=40)
        stats["lines_merged"] = original_count - len(merged)
        final_lines = merged
    else:
        final_lines = cleaned
    
    stats["final_lines"] = len(final_lines)
    
    logging.info(
        f"[CLEANUP-A2] 清洗完成: {stats['original_lines']}行 → {stats['final_lines']}行 "
        f"(去噪={stats['noise_removed']}, 标点={stats['punctuation_fixed']}, "
        f"术语={stats['terminology_replaced']}, 合并={stats['lines_merged']})"
    )
    
    return final_lines, stats


def clean_subtitle_file(
    input_file: str,
    output_file: str = None,
    terminology_file: str = "terminology.json",
    merge_enabled: bool = True
) -> Dict:
    """
    清洗字幕文件（支持 TXT/SRT/VTT）
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径（None=覆盖原文件）
        terminology_file: 术语文件路径
        merge_enabled: 是否启用句子合并
    
    Returns:
        统计信息
    """
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"文件不存在: {input_file}")
    
    # 加载术语表
    terminology = load_terminology(terminology_file)
    
    # 读取文件
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 提取纯文本行（跳过 SRT/VTT 时间轴）
    text_lines = []
    for line in lines:
        line = line.strip()
        # 跳过空行、序号、时间轴
        if not line or line.isdigit() or '-->' in line:
            continue
        text_lines.append(line)
    
    # 清洗
    cleaned_lines, stats = clean_zh_lines(text_lines, terminology, merge_enabled)
    
    # 写回文件
    output_path = Path(output_file) if output_file else input_path
    with open(output_path, 'w', encoding='utf-8') as f:
        for line in cleaned_lines:
            f.write(line + '\n')
    
    stats["input_file"] = str(input_path)
    stats["output_file"] = str(output_path)
    
    return stats


# 导出的公共接口
__all__ = [
    'load_terminology',
    'clean_zh_lines',
    'clean_zh_line',
    'clean_subtitle_file',
    'apply_terminology'
]

