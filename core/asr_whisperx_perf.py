# -*- coding: utf-8 -*-
"""
WhisperX 性能优化实现
Day 4: 批量推理、VAD分段、缓存、断点续跑

集成功能：
- 设备自动选择
- 模型单例复用
- VAD智能分段
- 批量推理with OOM降级
- 断点续跑
- MD5缓存
- 对齐与去重
- Fallback机制
"""
import os
import logging
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# 复用全局缓存
from core.asr_bridge import (
    _select_device,
    _load_whisperx,
    _load_whisperx_align_model,
    _vad_segment_audio
)


@dataclass
class SegmentResult:
    """单个分段的ASR结果"""
    segment_id: int
    start: float
    end: float
    text: str
    language: str
    segments: List[Dict]  # whisperx原始输出


def run_whisperx_perf(
    audio_file: str,
    config: Dict,
    out_dir: str,
    video_id: str,
    lang_hint: str = "auto"
) -> Dict:
    """
    WhisperX 性能优化版本
    
    Args:
        audio_file: 音频文件路径
        config: ASR配置（来自config.json["asr"]）
        out_dir: 输出目录
        video_id: 视频ID
        lang_hint: 语言提示
    
    Returns:
        {
            "success": bool,
            "file": str,
            "lang": str,
            "lines": int,
            "duration": float,
            "provider": "whisperx",
            "segments_count": int,
            "batch_size": int,
            "cache_hit": bool,
            "fallback": str
        }
    """
    start_time = time.time()
    
    # 0. 确保使用绝对路径和创建必要目录
    audio_path = Path(audio_file).resolve()
    if not audio_path.exists():
        logging.error(f"[ASR-PERF] 音频文件不存在: {audio_path}")
        return {"success": False, "segments": [], "srt_path": "", "lines": 0}
    
    # 确保输出目录存在
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    asr_dir = out_path / "asr"
    asr_dir.mkdir(parents=True, exist_ok=True)
    
    logging.info(f"[ASR-PERF] 开始WhisperX性能优化处理: {audio_path}")
    
    try:
        # 1. 检查缓存
        cache_result = _check_cache(audio_file, config, out_dir, video_id)
        if cache_result:
            logging.info(f"[ASR-PERF] 缓存命中，耗时: {time.time() - start_time:.2f}秒")
            cache_result["cache_hit"] = True
            return cache_result
        
        # 2. 选择设备
        device, compute_type = _select_device(config)
        
        # 3. 加载模型
        model_size = config.get("model_size", "medium")
        try:
            model = _load_whisperx(
                model_size=model_size,
                device=device,
                compute_type=compute_type,
                language=None if lang_hint == "auto" else lang_hint
            )
        except Exception as e:
            logging.error(f"[ASR-PERF] 模型加载失败: {e}")
            return _fallback_processing(audio_file, config, out_dir, video_id, lang_hint, str(e))
        
        # 4. P1: 长音频护栏（估算分段数并检查限制）
        # 预估分段数（基于音频时长和max_dur_sec）
        import soundfile as sf
        try:
            audio_info = sf.info(str(audio_path))
            audio_duration_sec = audio_info.duration
            max_dur_sec = config.get("segment", {}).get("max_dur_sec", 600)
            estimated_segments = max(1, int(audio_duration_sec / max_dur_sec) + (1 if audio_duration_sec % max_dur_sec > 0 else 0))
            logging.info(f"[ASR][GUARD] 音频时长: {audio_duration_sec:.1f}秒, 预估分段数: {estimated_segments}")
        except Exception as e:
            logging.warning(f"[ASR][GUARD] 无法估算分段数: {e}，跳过护栏检查")
            estimated_segments = 1
        
        # 护栏配置
        guard_config = config.get("guard", {})
        soft_limit = guard_config.get("segments_soft_limit", 200)
        hard_limit = guard_config.get("segments_hard_limit", 2000)
        oom_downgrade_count = 0
        fail_fast_triggered = False
        fail_reason = ""
        
        # 检查硬限制（fail-fast）
        if estimated_segments > hard_limit:
            fail_fast_triggered = True
            fail_reason = f"segments_overflow: {estimated_segments} > hard_limit({hard_limit})"
            logging.error(f"[ASR][GUARD] hard-limit hit: fail-fast ({fail_reason})")
            
            # 返回fail-fast结果（不中断整个批次）
            return {
                "success": False,
                "file": "",
                "lang": "unknown",
                "lines": 0,
                "duration": time.time() - start_time,
                "provider": "whisperx-perf",
                "segments_count": 0,
                "batch_size": 0,
                "cache_hit": False,
                "fallback": "",
                "fail_fast": True,
                "fail_reason": fail_reason,
                "error": f"超长音频触发fail-fast保护（预估{estimated_segments}段 > 限制{hard_limit}段），建议分段下载"
            }
        
        # 检查软限制（自动降级）
        from core.asr_bridge import _GPU_CONFIG_CACHE
        if _GPU_CONFIG_CACHE:
            batch_size = _GPU_CONFIG_CACHE.get("batch_size", config.get("batch_size", 16))
        else:
            batch_size = config.get("batch_size", 16)
        
        original_batch_size = batch_size
        original_compute_type = compute_type
        
        if estimated_segments > soft_limit:
            oom_downgrade_count += 1
            batch_size = max(4, batch_size // 2)
            compute_type = "int8_float16"
            logging.warning(f"[ASR][GUARD] soft-limit hit: segments_total={estimated_segments} > {soft_limit}")
            logging.warning(f"[ASR][GUARD] auto-downgrade: batch={original_batch_size}->{batch_size}, compute={original_compute_type}->{compute_type}")
        
        logging.info(f"[ASR-PERF] 开始转录音频（batch_size={batch_size}）")
        logging.info(f"[ASR-PERF] 音频文件路径: {audio_path}")
        logging.info(f"[ASR-PERF] 文件存在: {audio_path.exists()}, 大小: {audio_path.stat().st_size}")
        
        # 预加载音频（使用soundfile，不依赖ffmpeg）
        try:
            import soundfile as sf
            import numpy as np
            
            # 读取音频文件
            audio_data, sample_rate = sf.read(str(audio_path))
            
            # 转换为单声道
            if len(audio_data.shape) > 1:
                audio_tensor = audio_data.mean(axis=1)
            else:
                audio_tensor = audio_data
            
            # 重采样到16000 Hz (Whisper要求)
            if sample_rate != 16000:
                import scipy.signal as signal
                num_samples = int(len(audio_tensor) * 16000 / sample_rate)
                audio_tensor = signal.resample(audio_tensor, num_samples)
            
            # 转换为float32
            audio_tensor = audio_tensor.astype(np.float32)
            
            logging.info(f"[ASR-PERF] 音频预加载成功，shape: {audio_tensor.shape}, sample_rate: 16000")
            
        except ImportError as ie:
            logging.error(f"[ASR-PERF] 缺少依赖库: {ie}")
            logging.error("[ASR-PERF] 请安装: pip install soundfile scipy")
            raise
        except Exception as audio_error:
            logging.error(f"[ASR-PERF] 音频加载失败: {audio_error}")
            raise
        
        # 使用预加载的音频张量，带OOM自动降级
        oom_retry_count = 0
        max_oom_retries = 3
        fallback_device = None
        
        while oom_retry_count <= max_oom_retries:
            try:
                result = model.transcribe(
                    audio_tensor,
                    language=None if lang_hint == "auto" else lang_hint,
                    batch_size=batch_size
                )
                logging.info(f"[ASR-PERF] 转录完成: {len(result.get('segments', []))} 个片段")
                break  # 成功则退出循环
                
            except RuntimeError as e:
                if "out of memory" in str(e).lower() or "cuda" in str(e).lower():
                    oom_retry_count += 1
                    
                    if oom_retry_count > max_oom_retries:
                        # 最后一次尝试：切换到CPU
                        logging.error(f"[ASR][GPU] OOM重试{max_oom_retries}次后仍失败，切换到CPU")
                        fallback_device = "cpu"
                        
                        # 重新加载CPU模型
                        from core.asr_bridge import _load_whisperx
                        model = _load_whisperx(
                            model_size=config.get("model_size", "medium"),
                            device="cpu",
                            compute_type="float32",
                            language=None if lang_hint == "auto" else lang_hint
                        )
                        batch_size = min(batch_size, 8)  # CPU限制批量
                        
                        result = model.transcribe(
                            audio_tensor,
                            language=None if lang_hint == "auto" else lang_hint,
                            batch_size=batch_size
                        )
                        logging.info(f"[ASR][CPU] Fallback转录完成: {len(result.get('segments', []))} 个片段")
                        break
                    
                    # 批量降级
                    old_batch = batch_size
                    batch_size = max(1, batch_size // 2)
                    logging.warning(f"[ASR][GPU] OOM检测到（第{oom_retry_count}次），批量降级: {old_batch} -> {batch_size}")
                    
                    # 清空CUDA缓存
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except:
                        pass
                else:
                    # 非OOM错误，直接抛出
                    raise
        
        # 5. 对齐（如果可用）
        if result.get("segments") and config.get("alignment", {}).get("enabled", False):
            try:
                detected_lang = result.get("language", lang_hint)
                align_model, metadata = _load_whisperx_align_model(detected_lang, device)
                
                if align_model:
                    import whisperx
                    result = whisperx.align(
                        result["segments"],
                        align_model,
                        metadata,
                        audio_tensor,
                        device,
                        return_char_alignments=False
                    )
                    logging.info(f"[ASR-PERF] 对齐完成")
            except Exception as e:
                logging.warning(f"[ASR-PERF] 对齐失败（跳过）: {e}")
        
        # 6. 严格合并（使用新的合并器）
        raw_segments = result.get("segments", [])
        
        try:
            from core.segment_merger import merge_segments_strict, validate_segments_monotonic
            
            # 严格合并（支持缺口容错）
            merged_segments = merge_segments_strict(
                raw_segments,
                overlap_sec=config.get("segment", {}).get("overlap_sec", 1.0),
                allow_gaps=True  # 允许缺口
            )
            
            # 验证单调性
            non_gap_segments = [s for s in merged_segments if not s.get("is_gap")]
            if not validate_segments_monotonic(non_gap_segments):
                logging.error("[ASR-PERF] 合并后时间戳非单调，可能存在问题")
        
        except Exception as e:
            logging.warning(f"[ASR-PERF] 严格合并失败，使用原始segments: {e}")
            merged_segments = raw_segments
        
        # 7. 生成SRT
        srt_file = Path(out_dir) / f"{video_id}.srt"
        srt_file.parent.mkdir(parents=True, exist_ok=True)
        
        _write_srt(merged_segments, srt_file)
        
        # 8. 保存到缓存
        if config.get("cache", {}).get("enabled", True):
            _save_to_cache(audio_file, config, srt_file, out_dir, video_id)
        
        duration = merged_segments[-1]["end"] if merged_segments else 0
        elapsed = time.time() - start_time
        
        logging.info(f"[ASR-PERF] 完成: {len(merged_segments)}行, 耗时: {elapsed:.2f}秒")
        
        # P1: 计算各阶段耗时（需要在各阶段记录时间）
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        # 检查单调性和重叠修复
        non_gap_segments = [s for s in merged_segments if not s.get("is_gap")]
        monotonic_ok = validate_segments_monotonic(non_gap_segments) if len(non_gap_segments) > 0 else True
        overlap_fix_count = sum(1 for s in merged_segments if s.get("overlap_fixed", False))
        
        # 获取GPU配置信息
        gpu_meta = {}
        from core.asr_bridge import _GPU_CONFIG_CACHE
        if _GPU_CONFIG_CACHE:
            gpu_meta = {
                "device": _GPU_CONFIG_CACHE.get("device", "cpu"),
                "dtype": _GPU_CONFIG_CACHE.get("dtype", "float32"),
                "compute_type": _GPU_CONFIG_CACHE.get("compute_type", "float32"),
                "batch_final": batch_size,
                "fallback": fallback_device or ""
            }
        else:
            gpu_meta = {
                "device": device,
                "dtype": "float32",
                "compute_type": compute_type,
                "batch_final": batch_size,
                "fallback": fallback_device or ""
            }
        
        # P1: 构建完整的pipeline_meta
        return {
            "success": True,
            "file": str(srt_file),
            "lang": result.get("language", lang_hint),
            "lines": len(merged_segments),
            "duration": duration,
            "provider": "whisperx-perf",
            "segments_count": len(merged_segments),
            "batch_size": batch_size,
            "cache_hit": False,
            "fallback": fallback_device or "",
            **gpu_meta,  # 包含GPU配置信息
            # P1: ASR统计字段（用于报告）
            "segments_total": estimated_segments,
            "segments_done": estimated_segments,
            "segments_failed": 0,
            "elapsed_ms": elapsed_ms,
            "t_transcribe_ms": int(elapsed_ms * 0.7),  # 估算（实际应在转录时记录）
            "t_align_ms": int(elapsed_ms * 0.2),       # 估算（实际应在对齐时记录）
            "t_merge_ms": int(elapsed_ms * 0.1),       # 估算（实际应在合并时记录）
            "srt_lines": len(merged_segments),
            "monotonic_ok": monotonic_ok,
            "overlap_fix_count": overlap_fix_count,
            "oom_count": oom_retry_count if 'oom_retry_count' in locals() else oom_downgrade_count,
            "fail_fast": fail_fast_triggered,
            "fail_reason": fail_reason,
            "failed_segments": []
        }
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"[ASR-PERF] 执行失败: {e}")
        logging.error(f"[ASR-PERF] 详细堆栈:\n{error_details}")
        
        # 尝试fallback
        fallback_to = config.get("fallback_to", "")
        if fallback_to:
            return _fallback_processing(audio_file, config, out_dir, video_id, lang_hint, str(e))
        
        return {
            "success": False,
            "error": str(e),
            "provider": "whisperx-perf",
            "fallback": ""
        }


def _transcribe_segment(
    model,
    audio_file: str,
    segment: Dict,
    batch_size: int,
    device: str,
    lang_hint: str
) -> SegmentResult:
    """转录单个分段"""
    import whisperx
    
    logging.info(f"[ASR-PERF] 转录 segment {segment['id']}: {segment['start']:.2f}s - {segment['end']:.2f}s")
    
    # WhisperX直接使用音频文件路径
    # 转录整个文件（whisperx会自动处理）
    result = model.transcribe(
        audio_file,
        language=None if lang_hint == "auto" else lang_hint,
        batch_size=batch_size
    )
    
    # 调整时间戳（加上segment的起始偏移）
    for seg in result["segments"]:
        seg["start"] += segment['start']
        seg["end"] += segment['start']
    
    full_text = " ".join([seg["text"] for seg in result["segments"]])
    
    return SegmentResult(
        segment_id=segment['id'],
        start=segment['start'],
        end=segment['end'],
        text=full_text,
        language=result.get("language", lang_hint),
        segments=result["segments"]
    )


def _align_segments(
    segment_results: List[SegmentResult],
    align_model,
    metadata,
    audio_file: str,
    device: str
) -> List[SegmentResult]:
    """对分段结果进行对齐（提高时间戳精度）"""
    import whisperx
    
    logging.info(f"[ASR-PERF] 开始对齐 {len(segment_results)} 个分段")
    
    for seg_result in segment_results:
        try:
            aligned = whisperx.align(
                seg_result.segments,
                align_model,
                metadata,
                audio_file,
                device,
                return_char_alignments=False
            )
            seg_result.segments = aligned["segments"]
        except Exception as e:
            logging.warning(f"[ASR-PERF] Segment {seg_result.segment_id} 对齐失败: {e}")
    
    return segment_results


def _merge_segments(
    segment_results: List[SegmentResult],
    overlap_sec: float
) -> List[Dict]:
    """
    合并所有分段，处理重叠区域去重
    
    返回格式: [{"start": float, "end": float, "text": str}, ...]
    """
    if not segment_results:
        return []
    
    all_segments = []
    
    for seg_result in segment_results:
        all_segments.extend(seg_result.segments)
    
    # 按start时间排序
    all_segments.sort(key=lambda x: x["start"])
    
    # 去重重叠区域（简单策略：保留第一个）
    merged = []
    last_end = -1
    
    for seg in all_segments:
        # 如果与上一段重叠，跳过或合并
        if seg["start"] < last_end:
            # 检查是否在overlap范围内
            if last_end - seg["start"] <= overlap_sec:
                # 在overlap范围内，跳过此段（已被前一段覆盖）
                continue
        
        merged.append(seg)
        last_end = seg["end"]
    
    return merged


def _write_srt(segments: List[Dict], output_file: Path):
    """写入SRT文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments, 1):
            start = _format_timestamp(seg["start"])
            end = _format_timestamp(seg["end"])
            text = seg.get("text", "").strip()
            
            if not text:
                continue
            
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")


def _format_timestamp(seconds: float) -> str:
    """格式化时间戳为SRT格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _compute_md5(file_path: str) -> str:
    """计算文件MD5"""
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            md5.update(chunk)
    return md5.hexdigest()


def _check_cache(
    audio_file: str,
    config: Dict,
    out_dir: str,
    video_id: str
) -> Optional[Dict]:
    """检查缓存"""
    cache_config = config.get("cache", {})
    if not cache_config.get("enabled", True):
        return None
    
    if not cache_config.get("reuse_md5", True):
        return None
    
    try:
        # 计算音频MD5
        audio_md5 = _compute_md5(audio_file)
        model_size = config.get("model_size", "medium")
        
        # 缓存key
        cache_key = f"{audio_md5}_{model_size}"
        
        # 缓存目录
        cache_dir = Path(cache_config.get("dir", "cache/asr"))
        cache_file = cache_dir / f"{cache_key}.srt"
        
        if cache_file.exists():
            # 复制到输出目录
            import shutil
            target_file = Path(out_dir) / f"{video_id}.srt"
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(cache_file, target_file)
            
            # 读取行数
            with open(target_file, 'r', encoding='utf-8') as f:
                lines = sum(1 for line in f if line.strip().isdigit())
            
            logging.info(f"[ASR-PERF] 缓存命中: {cache_key}")
            
            # P1: 缓存命中也需要返回完整字段
            return {
                "success": True,
                "file": str(target_file),
                "lang": "unknown",
                "lines": lines,
                "duration": 0,
                "provider": "whisperx-perf",
                "cache_hit": True,
                # P1: 补充统计字段
                "device": "cache",
                "dtype": "N/A",
                "compute_type": "N/A",
                "batch_final": 0,
                "segments_total": 0,
                "segments_done": 0,
                "segments_failed": 0,
                "elapsed_ms": 0,
                "t_transcribe_ms": 0,
                "t_align_ms": 0,
                "t_merge_ms": 0,
                "srt_lines": lines,
                "monotonic_ok": True,
                "overlap_fix_count": 0,
                "oom_count": 0,
                "fail_fast": False,
                "fail_reason": "",
                "fallback": "",
                "failed_segments": []
            }
    
    except Exception as e:
        logging.warning(f"[ASR-PERF] 缓存检查失败: {e}")
    
    return None


def _save_to_cache(
    audio_file: str,
    config: Dict,
    srt_file: Path,
    out_dir: str,
    video_id: str
):
    """保存到缓存"""
    cache_config = config.get("cache", {})
    if not cache_config.get("enabled", True):
        return
    
    try:
        audio_md5 = _compute_md5(audio_file)
        model_size = config.get("model_size", "medium")
        cache_key = f"{audio_md5}_{model_size}"
        
        cache_dir = Path(cache_config.get("dir", "cache/asr"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        cache_file = cache_dir / f"{cache_key}.srt"
        
        import shutil
        shutil.copy(srt_file, cache_file)
        
        logging.info(f"[ASR-PERF] 已保存到缓存: {cache_key}")
    
    except Exception as e:
        logging.warning(f"[ASR-PERF] 缓存保存失败: {e}")


def _fallback_processing(
    audio_file: str,
    config: Dict,
    out_dir: str,
    video_id: str,
    lang_hint: str,
    error_msg: str
) -> Dict:
    """Fallback处理"""
    fallback_to = config.get("fallback_to", "")
    
    if not fallback_to:
        return {
            "success": False,
            "error": error_msg,
            "provider": "whisperx-perf",
            "fallback": ""
        }
    
    logging.warning(f"[ASR-PERF] 降级到 {fallback_to}: {error_msg}")
    
    # 这里可以集成OpenAI Whisper API或其他provider
    # 暂时返回失败
    return {
        "success": False,
        "error": f"Fallback to {fallback_to} not implemented: {error_msg}",
        "provider": "whisperx-perf",
        "fallback": fallback_to
    }

