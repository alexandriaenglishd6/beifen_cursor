# -*- coding: utf-8 -*-
"""
ASR分段合并器 - 严格模式
支持缺口容错、时间戳单调性校验、重叠处理
"""
import logging
from typing import List, Dict, Optional


def merge_segments_strict(
    segments: List[Dict],
    overlap_sec: float = 1.0,
    allow_gaps: bool = True
) -> List[Dict]:
    """
    严格合并多个segment列表，确保时间戳单调递增
    
    Args:
        segments: segment列表，每个segment包含 start, end, text
        overlap_sec: 重叠区间（秒）
        allow_gaps: 是否允许时间缺口
    
    Returns:
        合并后的segment列表
    """
    if not segments:
        return []
    
    # 按开始时间排序
    sorted_segments = sorted(segments, key=lambda x: x.get("start", 0))
    
    merged = []
    last_end = 0.0
    gap_count = 0
    
    for seg in sorted_segments:
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        
        if not text:
            continue
        
        # 检查时间戳有效性
        if start < 0 or end <= start:
            logging.warning(f"[MERGE] 无效时间戳: start={start}, end={end}, 跳过")
            continue
        
        # 检查时间倒退
        if start < last_end - overlap_sec:
            logging.warning(f"[MERGE] 时间倒退: start={start} < last_end={last_end}, 调整为{last_end}")
            start = last_end
        
        # 检查时间缺口
        gap = start - last_end
        if gap > overlap_sec * 2:  # 缺口超过2倍重叠时间
            if allow_gaps:
                gap_count += 1
                logging.warning(f"[MERGE] 发现缺口 #{gap_count}: {last_end:.2f}s -> {start:.2f}s ({gap:.2f}s)")
                # 插入缺口标记
                merged.append({
                    "start": last_end,
                    "end": start,
                    "text": f"<!-- SEGMENT GAP {gap_count}: {gap:.2f}s -->",
                    "is_gap": True
                })
            else:
                logging.error(f"[MERGE] 严格模式不允许缺口: {last_end:.2f}s -> {start:.2f}s")
                raise ValueError(f"Segment gap detected: {gap:.2f}s")
        
        # 处理重叠
        if start < last_end and start >= last_end - overlap_sec:
            # 轻微重叠，调整为无缝拼接
            start = last_end
        
        # 添加segment
        merged.append({
            "start": start,
            "end": end,
            "text": text
        })
        
        last_end = end
    
    # 最终验证单调性
    for i in range(1, len(merged)):
        if merged[i]["start"] < merged[i-1]["end"]:
            logging.error(f"[MERGE] 单调性检查失败: seg{i} start={merged[i]['start']} < seg{i-1} end={merged[i-1]['end']}")
    
    logging.info(f"[MERGE] 合并完成: {len(segments)} -> {len(merged)} segments, {gap_count} gaps")
    
    return merged


def validate_segments_monotonic(segments: List[Dict]) -> bool:
    """
    验证segments时间戳单调性
    
    Args:
        segments: segment列表
    
    Returns:
        是否单调递增
    """
    for i in range(1, len(segments)):
        if segments[i]["start"] < segments[i-1]["end"]:
            logging.error(
                f"[VALIDATE] 非单调: seg[{i-1}]({segments[i-1]['start']:.2f}-{segments[i-1]['end']:.2f}) "
                f"-> seg[{i}]({segments[i]['start']:.2f}-{segments[i]['end']:.2f})"
            )
            return False
    
    logging.info(f"[VALIDATE] 时间戳单调性验证通过: {len(segments)} segments")
    return True


def format_srt_with_gaps(segments: List[Dict]) -> str:
    """
    生成SRT格式，包含缺口标记
    
    Args:
        segments: segment列表
    
    Returns:
        SRT格式文本
    """
    lines = []
    index = 1
    
    for seg in segments:
        start = seg["start"]
        end = seg["end"]
        text = seg["text"]
        
        # 时间格式：HH:MM:SS,mmm
        start_time = _format_time(start)
        end_time = _format_time(end)
        
        if seg.get("is_gap"):
            # 缺口标记以注释形式
            lines.append(f"<!-- GAP: {start_time} --> {end_time} -->")
        else:
            lines.append(str(index))
            lines.append(f"{start_time} --> {end_time}")
            lines.append(text)
            lines.append("")  # 空行
            index += 1
    
    return "\n".join(lines)


def _format_time(seconds: float) -> str:
    """
    将秒数转换为SRT时间格式 HH:MM:SS,mmm
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

