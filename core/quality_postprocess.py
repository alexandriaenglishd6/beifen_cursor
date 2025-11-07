# -*- coding: utf-8 -*-
"""
Sprint 1-A1: 中文字幕质量后处理
让中文字幕读起来像人写的，不像机器碎片拼的
"""
from __future__ import annotations
import re
import logging
from typing import List, Tuple

# 噪音模式（需要清除的内容）
NOISE_PATTERNS = [
    r'\[Music\]',
    r'\[音乐\]',
    r'\[Applause\]',
    r'\[掌声\]',
    r'\[Laughter\]',
    r'\[笑声\]',
    r'\(笑\)',
    r'\(笑声\)',
    r'\[♪\]',
    r'♪',
    r'～',
    r'\(music\)',
    r'\(applause\)',
    r'\(laughter\)',
    # 口语填充词
    r'^呃[，。、]?',
    r'^嗯[，。、]?',
    r'^啊[，。、]?',
    r'^哦[，。、]?',
    r'^诶[，。、]?',
    r'[，。、]呃$',
    r'[，。、]嗯$',
    r'[，。、]啊$',
]

# 半角标点 → 全角标点映射
PUNCTUATION_MAP = {
    ',': '，',
    '.': '。',
    '!': '！',
    '?': '？',
    ':': '：',
    ';': '；',
    '(': '（',
    ')': '）',
    '[': '「',
    ']': '」',
    '{': '『',
    '}': '』',
    '"': '"',  # 简化处理
    "'": '\u2019',  # 使用 Unicode 编码避免引号冲突
}


def is_chinese_text(text: str, threshold: float = 0.3) -> bool:
    """
    判断文本是否为中文
    
    Args:
        text: 文本内容
        threshold: 中文字符占比阈值（默认30%）
    
    Returns:
        True if 中文占比 >= threshold
    """
    if not text or not text.strip():
        return False
    
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    total_chars = len([c for c in text if c.strip()])
    
    if total_chars == 0:
        return False
    
    return (chinese_chars / total_chars) >= threshold


def remove_noise(text: str) -> str:
    """
    去除噪音（音乐、笑声、口语填充词等）
    
    Args:
        text: 原始文本
    
    Returns:
        清洗后的文本
    """
    result = text
    
    # 应用所有噪音模式
    for pattern in NOISE_PATTERNS:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    # 清理多余空格
    result = re.sub(r'\s+', ' ', result)
    result = result.strip()
    
    return result


def normalize_punctuation(text: str) -> str:
    """
    标点符号中文化（半角 → 全角）
    
    Args:
        text: 原始文本
    
    Returns:
        标点规范化后的文本
    """
    result = text
    
    # 替换半角标点为全角
    for half, full in PUNCTUATION_MAP.items():
        result = result.replace(half, full)
    
    # 修复连续标点
    result = re.sub(r'[，。！？]{2,}', lambda m: m.group(0)[0], result)
    
    # 确保句尾有标点（如果没有）
    if result and result[-1] not in '。！？，、；：':
        # 检查是否是完整句子（长度 >= 5，不是纯数字/英文）
        if len(result) >= 5 and not result.isascii():
            result += '。'
    
    return result


def merge_short_lines(lines: List[str], min_length: int = 8, max_length: int = 40) -> List[str]:
    """
    合并过短的中文句子，让表达更完整
    
    策略：
    - 短于 min_length 的行尝试与下一行合并
    - 合并后不超过 max_length
    - 保持语义完整性（句号/问号/感叹号结尾不合并）
    
    Args:
        lines: 原始行列表
        min_length: 最小行长度（中文字符）
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


def optimize_chinese_subtitle(text: str) -> str:
    """
    中文字幕综合优化（单行）
    
    处理流程：
    1. 去噪
    2. 标点规范化
    
    Args:
        text: 原始字幕文本
    
    Returns:
        优化后的文本
    """
    if not text or not text.strip():
        return text
    
    # 只处理中文文本
    if not is_chinese_text(text):
        return text
    
    # 1. 去噪
    result = remove_noise(text)
    
    if not result:
        return ""
    
    # 2. 标点规范化
    result = normalize_punctuation(result)
    
    return result


def optimize_chinese_subtitles_batch(lines: List[str]) -> Tuple[List[str], dict]:
    """
    批量优化中文字幕（多行处理，含合并）
    
    Args:
        lines: 原始字幕行列表
    
    Returns:
        (优化后的行列表, 统计信息)
    """
    stats = {
        "original_lines": len(lines),
        "noise_removed": 0,
        "punctuation_fixed": 0,
        "lines_merged": 0,
        "final_lines": 0,
        "chinese_lines": 0
    }
    
    # 第一阶段：逐行优化
    optimized = []
    for line in lines:
        if not line.strip():
            continue
        
        # 检测是否中文
        if is_chinese_text(line):
            stats["chinese_lines"] += 1
            
            # 优化
            original = line
            cleaned = optimize_chinese_subtitle(line)
            
            # 统计
            if cleaned != original:
                if any(pattern in original for pattern in ['[Music]', '呃', '嗯', '啊']):
                    stats["noise_removed"] += 1
                if any(p in original for p in PUNCTUATION_MAP.keys()):
                    stats["punctuation_fixed"] += 1
            
            if cleaned:
                optimized.append(cleaned)
        else:
            # 非中文行：检查是否为噪音标记
            cleaned_non_chinese = remove_noise(line)
            if cleaned_non_chinese and cleaned_non_chinese.strip():
                # 保留非噪音的非中文内容
                optimized.append(line)
            else:
                # 跳过纯噪音行（如 [Music]）
                stats["noise_removed"] += 1
    
    # 第二阶段：合并短句（仅中文）
    final_lines = []
    i = 0
    while i < len(optimized):
        line = optimized[i]
        
        # 只合并中文短句
        if is_chinese_text(line) and len(line) < 12 and i + 1 < len(optimized):
            next_line = optimized[i + 1]
            
            # 检查是否可以合并
            if is_chinese_text(next_line) and line[-1] not in '。！？':
                merged = line + next_line
                if len(merged) <= 40:
                    final_lines.append(merged)
                    stats["lines_merged"] += 1
                    i += 2
                    continue
        
        final_lines.append(line)
        i += 1
    
    stats["final_lines"] = len(final_lines)
    
    return final_lines, stats


def process_subtitle_quality(
    subtitle_lines: List[str],
    enabled: bool = True,
    lang_filter: str = "zh"
) -> Tuple[List[str], dict]:
    """
    字幕质量后处理主函数
    
    Args:
        subtitle_lines: 原始字幕行列表
        enabled: 是否启用质量优化
        lang_filter: 语言过滤（"zh"=仅中文, "all"=所有）
    
    Returns:
        (处理后的行列表, 统计信息)
    """
    if not enabled:
        return subtitle_lines, {"enabled": False}
    
    logging.info(f"[QUALITY] 启动字幕质量优化（语言={lang_filter}）")
    
    # 批量优化
    optimized_lines, stats = optimize_chinese_subtitles_batch(subtitle_lines)
    
    stats["enabled"] = True
    stats["lang_filter"] = lang_filter
    
    logging.info(
        f"[QUALITY] 优化完成: {stats['original_lines']}行 → {stats['final_lines']}行 "
        f"(去噪={stats['noise_removed']}, 标点={stats['punctuation_fixed']}, 合并={stats['lines_merged']})"
    )
    
    return optimized_lines, stats

