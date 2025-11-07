# -*- coding: utf-8 -*-
"""
B1: ASR 无字幕补全桥接
统一适配多种 ASR 提供商（Mock / Whisper / WhisperX / OpenAI）

Day 4: WhisperX 性能升级
- 设备自动选择（CUDA/CPU）
- 模型单例复用
- VAD分段
- 批量推理
- 缓存机制
"""
from __future__ import annotations
import os
import logging
import tempfile
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# 全局模型缓存（单例复用）
_WHISPERX_MODEL_CACHE = {}
_WHISPERX_ALIGN_MODEL_CACHE = {}

# GPU自适应配置（全局缓存）
_GPU_CONFIG_CACHE = None


def _select_device(asr_config: Dict) -> Tuple[str, str]:
    """
    自动选择设备和数据类型（GPU自适应版本）
    
    Args:
        asr_config: ASR配置字典
    
    Returns:
        (device, compute_type)
    """
    global _GPU_CONFIG_CACHE
    
    try:
        from core.gpu_utils import get_gpu_info, select_device_and_dtype, init_torch_runtime, log_gpu_config
        
        # 获取GPU信息
        gpu_info = get_gpu_info()
        
        # 自动选择设备和精度
        config = select_device_and_dtype(asr_config, gpu_info)
        
        # 初始化运行时
        init_torch_runtime(config["device"], config["dtype"])
        
        # 记录配置
        log_gpu_config(config, gpu_info)
        
        # 缓存配置
        _GPU_CONFIG_CACHE = {
            **config,
            "gpu_info": gpu_info
        }
        
        return config["device"], config["compute_type"]
    
    except ImportError as e:
        logging.warning(f"[ASR] GPU工具导入失败，使用简化逻辑: {e}")
        # 回退到简单逻辑
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            device = "cuda" if cuda_available and asr_config.get("device", "auto") != "cpu" else "cpu"
            compute_type = "float16" if device == "cuda" else "float32"
            logging.info(f"[ASR] 设备选择(简化): device={device}, compute_type={compute_type}")
            return device, compute_type
        except:
            return "cpu", "float32"


def _load_whisperx(
    model_size: str,
    device: str,
    compute_type: str,
    language: str = None,
    download_root: str = None
):
    """
    加载WhisperX模型（支持单例复用）
    
    Args:
        model_size: "tiny" | "base" | "small" | "medium" | "large-v2"
        device: "cuda" | "cpu"
        compute_type: "int8" | "float16" | "float32"
        language: 语言代码（可选）
        download_root: 模型下载目录（可选）
    
    Returns:
        whisperx model
    """
    global _WHISPERX_MODEL_CACHE
    
    # 生成缓存key
    cache_key = f"{model_size}_{device}_{compute_type}_{language or 'auto'}"
    
    # 检查缓存
    if cache_key in _WHISPERX_MODEL_CACHE:
        logging.info(f"[ASR] 复用已加载的模型: {cache_key}")
        return _WHISPERX_MODEL_CACHE[cache_key]
    
    # 加载新模型
    try:
        import whisperx
        
        logging.info(f"[ASR] 加载WhisperX模型: size={model_size}, device={device}, compute_type={compute_type}")
        
        model = whisperx.load_model(
            model_size,
            device=device,
            compute_type=compute_type,
            language=language,
            download_root=download_root
        )
        
        # 缓存模型
        _WHISPERX_MODEL_CACHE[cache_key] = model
        logging.info(f"[ASR] 模型加载成功并缓存: {cache_key}")
        
        return model
    
    except Exception as e:
        logging.error(f"[ASR] 模型加载失败: {e}")
        raise


def _load_whisperx_align_model(
    language_code: str,
    device: str
):
    """
    加载WhisperX对齐模型（支持单例复用）
    
    Args:
        language_code: 语言代码（如"zh", "en"）
        device: "cuda" | "cpu"
    
    Returns:
        (align_model, metadata)
    """
    global _WHISPERX_ALIGN_MODEL_CACHE
    
    cache_key = f"{language_code}_{device}"
    
    # 检查缓存
    if cache_key in _WHISPERX_ALIGN_MODEL_CACHE:
        logging.info(f"[ASR] 复用已加载的对齐模型: {cache_key}")
        return _WHISPERX_ALIGN_MODEL_CACHE[cache_key]
    
    # 加载新模型
    try:
        import whisperx
        
        logging.info(f"[ASR] 加载WhisperX对齐模型: lang={language_code}, device={device}")
        
        model, metadata = whisperx.load_align_model(
            language_code=language_code,
            device=device
        )
        
        # 缓存模型
        _WHISPERX_ALIGN_MODEL_CACHE[cache_key] = (model, metadata)
        logging.info(f"[ASR] 对齐模型加载成功并缓存: {cache_key}")
        
        return model, metadata
    
    except Exception as e:
        logging.warning(f"[ASR] 对齐模型加载失败: {e}")
        return None, None


def _vad_segment_audio(
    audio_file: str,
    vad_config: Dict,
    segment_config: Dict,
    device: str = "cpu"
) -> List[Dict]:
    """
    使用VAD对音频进行智能分段
    
    Args:
        audio_file: 音频文件路径
        vad_config: VAD配置 {"enabled": bool, "min_silence": float, "min_segment": float}
        segment_config: 分段配置 {"max_dur_sec": int, "overlap_sec": float}
        device: 设备
    
    Returns:
        List[Dict]: 分段信息列表
        [
            {"id": 0, "start": 0.0, "end": 600.0, "duration": 600.0},
            {"id": 1, "start": 599.0, "end": 1200.0, "duration": 601.0},
            ...
        ]
    """
    try:
        import whisperx
        import torch
        import torchaudio
        
        # 加载音频
        waveform, sample_rate = torchaudio.load(audio_file)
        
        # 转换为单声道
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)
        
        # 获取总时长
        total_duration = waveform.shape[1] / sample_rate
        
        logging.info(f"[ASR-VAD] 音频总时长: {total_duration:.2f}秒")
        
        # 简化版本：不使用VAD，直接使用整段音频
        # (WhisperX的VAD API在不同版本中不一致，为了兼容性暂时禁用)
        speech_timestamps = [{"start": 0, "end": int(total_duration * sample_rate)}]
        logging.info(f"[ASR-VAD] 使用整段音频（VAD已禁用以确保兼容性）")
        
        # 根据max_dur_sec进一步切分
        max_dur_sec = segment_config.get("max_dur_sec", 600)
        overlap_sec = segment_config.get("overlap_sec", 1.0)
        
        segments = []
        segment_id = 0
        
        for speech in speech_timestamps:
            start_sample = speech["start"]
            end_sample = speech["end"]
            
            start_sec = start_sample / sample_rate
            end_sec = end_sample / sample_rate
            duration = end_sec - start_sec
            
            # 如果段落小于max_dur_sec，直接使用
            if duration <= max_dur_sec:
                segments.append({
                    "id": segment_id,
                    "start": start_sec,
                    "end": end_sec,
                    "duration": duration
                })
                segment_id += 1
            else:
                # 需要进一步切分
                current_start = start_sec
                
                while current_start < end_sec:
                    current_end = min(current_start + max_dur_sec, end_sec)
                    
                    segments.append({
                        "id": segment_id,
                        "start": current_start,
                        "end": current_end,
                        "duration": current_end - current_start
                    })
                    
                    segment_id += 1
                    
                    # 下一段开始位置（考虑重叠）
                    current_start = current_end - overlap_sec
                    
                    # 如果剩余时间太短，合并到前一段
                    if end_sec - current_start < segment_config.get("min_segment", 2.0):
                        break
        
        logging.info(f"[ASR-VAD] 最终分段数: {len(segments)}, 平均时长: {sum(s['duration'] for s in segments)/len(segments):.2f}秒")
        
        return segments
    
    except Exception as e:
        logging.error(f"[ASR-VAD] 分段失败: {e}")
        # 返回整段
        return [{"id": 0, "start": 0.0, "end": 0.0, "duration": 0.0}]


def run_asr(
    video_url: str,
    provider: str = "mock",
    lang_hint: str = "auto",
    out_dir: str = None,
    timeout: int = 120,
    **kwargs
) -> Dict:
    """
    运行 ASR 生成字幕（统一接口）
    
    Args:
        video_url: 视频URL或本地路径
        provider: ASR提供商 ("mock" | "whisperx" | "faster-whisper" | "openai")
        lang_hint: 语言提示（"auto" 自动检测）
        out_dir: 输出目录
        timeout: 超时时间（秒）
        **kwargs: 其他参数
    
    Returns:
        {
            "success": bool,
            "file": str,           # 输出文件路径
            "lang": str,           # 检测到的语言
            "lines": int,          # 行数
            "duration": float,     # 时长（秒）
            "provider": str,
            "error": str           # 错误信息（如果失败）
        }
    """
    logging.info(f"[ASR-B1] 启动 ASR: provider={provider}, lang={lang_hint}, url={video_url}")
    
    # 确保输出目录
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
    
    # 根据 provider 分发
    if provider == "mock":
        return _run_mock_asr(video_url, lang_hint, out_dir)
    
    elif provider in ("whisperx", "faster-whisper"):
        return _run_local_whisper(video_url, provider, lang_hint, out_dir, timeout)
    
    elif provider == "openai":
        return _run_openai_whisper(video_url, lang_hint, out_dir, timeout)
    
    else:
        return {
            "success": False,
            "error": f"未知的 ASR provider: {provider}",
            "provider": provider
        }


def _run_mock_asr(video_url: str, lang_hint: str, out_dir: str) -> Dict:
    """
    Mock ASR（测试用，产生占位文本）
    
    Args:
        video_url: 视频URL
        lang_hint: 语言提示
        out_dir: 输出目录
    
    Returns:
        ASR结果字典
    """
    logging.info(f"[ASR-MOCK] 使用 Mock ASR 生成占位字幕")
    
    # 生成占位内容
    mock_content = [
        "这是自动生成的字幕。",
        "视频没有可用的字幕。",
        "ASR 功能使用 Mock 模式。",
        "请安装真实的 ASR 引擎以获得实际字幕。"
    ]
    
    # 提取视频ID（简化处理）
    video_id = _extract_video_id(video_url)
    
    # 输出文件
    output_dir = Path(out_dir) if out_dir else Path(tempfile.gettempdir())
    output_file = output_dir / f"{video_id}.mock.txt"
    
    # 写入
    with open(output_file, 'w', encoding='utf-8') as f:
        for line in mock_content:
            f.write(line + '\n')
    
    return {
        "success": True,
        "file": str(output_file),
        "lang": lang_hint if lang_hint != "auto" else "zh",
        "lines": len(mock_content),
        "duration": 0.1,
        "provider": "mock"
    }


def _run_local_whisper(
    video_url: str,
    provider: str,
    lang_hint: str,
    out_dir: str,
    timeout: int
) -> Dict:
    """
    本地 Whisper ASR（WhisperX / Faster-Whisper）
    
    Args:
        video_url: 视频URL
        provider: "whisperx" 或 "faster-whisper"
        lang_hint: 语言提示
        out_dir: 输出目录
        timeout: 超时时间
    
    Returns:
        ASR结果字典
    """
    if provider == "whisperx":
        return _run_whisperx_impl(video_url, lang_hint, out_dir, timeout)
    else:
        # Faster-Whisper 保持占位
        return {
            "success": False,
            "error": f"{provider} 实现需要用户自定义集成",
            "provider": provider
        }


def _run_whisperx_impl(
    video_url: str,
    lang_hint: str,
    out_dir: str,
    timeout: int
) -> Dict:
    """
    WhisperX 性能优化实现（Day 4 升级版）
    
    集成功能：
    - 设备自动选择
    - 模型单例复用
    - VAD智能分段
    - 批量推理with OOM降级
    - 断点续跑
    - MD5缓存
    - 对齐与去重
    
    Args:
        video_url: 视频URL
        lang_hint: 语言提示
        out_dir: 输出目录
        timeout: 超时时间
    
    Returns:
        ASR结果字典
    """
    try:
        logging.info("[ASR-WHISPERX-PERF] 开始 WhisperX 性能优化处理")
        
        # 1. 提取音频
        from core.audio_extractor import extract_audio
        
        audio_dir = Path(out_dir).parent / "asr_raw"
        audio_file = extract_audio(
            video_url,
            out_dir=str(audio_dir),
            fmt="wav",
            sr=16000
        )
        
        if not audio_file:
            return {
                "success": False,
                "error": "音频提取失败",
                "provider": "whisperx-perf"
            }
        
        logging.info(f"[ASR-WHISPERX-PERF] 音频文件: {audio_file}")
        
        # 2. 加载配置
        from core.config import load_config
        cfg = load_config("config.json")
        asr_config = cfg.get("asr", {
            "enabled": True,
            "provider": "whisperx",
            "device": "auto",
            "model_size": "medium",
            "batch_size": 16,
            "vad": {"enabled": True, "min_silence": 0.4, "min_segment": 2.0},
            "segment": {"max_dur_sec": 600, "overlap_sec": 1.0},
            "cache": {"enabled": True, "dir": "cache/asr", "reuse_md5": True},
            "alignment": {"enabled": True},
            "timeout_sec": 1800,
            "fallback_to": ""
        })
        
        # 3. 调用性能优化版本
        from core.asr_whisperx_perf import run_whisperx_perf
        
        video_id = _extract_video_id(video_url)
        
        result = run_whisperx_perf(
            audio_file=audio_file,
            config=asr_config,
            out_dir=out_dir,
            video_id=video_id,
            lang_hint=lang_hint
        )
        
        logging.info(f"[ASR-WHISPERX-PERF] 完成: success={result.get('success')}, lines={result.get('lines', 0)}")
        
        return result
    
    except ImportError as e:
        return {
            "success": False,
            "error": f"依赖未安装: whisperx - {e}. 请运行: pip install whisperx",
            "provider": "whisperx"
        }
    
    except Exception as e:
        logging.error(f"[ASR-WHISPERX] 执行失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "provider": "whisperx"
        }


def _format_timestamp(seconds: float) -> str:
    """格式化时间戳为 SRT 格式（HH:MM:SS,mmm）"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _run_openai_whisper(
    video_url: str,
    lang_hint: str,
    out_dir: str,
    timeout: int
) -> Dict:
    """
    OpenAI Whisper API（云端）
    
    Args:
        video_url: 视频URL
        lang_hint: 语言提示
        out_dir: 输出目录
        timeout: 超时时间
    
    Returns:
        ASR结果字典
    """
    try:
        import openai
        
        # 读取 API Key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {
                "success": False,
                "error": "未设置 OPENAI_API_KEY 环境变量",
                "provider": "openai"
            }
        
        logging.info("[ASR-OPENAI] 调用 OpenAI Whisper API...")
        
        # 这里是占位实现，真实场景需要：
        # 1. 下载/提取音频
        # 2. 调用 OpenAI API
        # 3. 格式化输出
        
        # 示例代码:
        # with open(audio_path, "rb") as audio_file:
        #     transcript = openai.Audio.transcribe(
        #         model="whisper-1",
        #         file=audio_file,
        #         language=lang_hint if lang_hint != "auto" else None
        #     )
        # ...
        
        return {
            "success": False,
            "error": "OpenAI Whisper API 实现需要用户自定义集成（音频提取、API调用等）",
            "provider": "openai"
        }
    
    except ImportError:
        return {
            "success": False,
            "error": "openai 库未安装: pip install openai",
            "provider": "openai"
        }
    
    except Exception as e:
        logging.error(f"[ASR-OPENAI] 执行失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "provider": "openai"
        }


def _extract_video_id(url: str) -> str:
    """
    从URL提取视频ID（简化版）
    
    Args:
        url: 视频URL
    
    Returns:
        视频ID
    """
    import re
    
    # YouTube URL 模式
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be/([0-9A-Za-z_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # 兜底：使用时间戳
    return f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def check_asr_availability(provider: str) -> Dict[str, any]:
    """
    检查 ASR 提供商可用性
    
    Args:
        provider: ASR提供商名称
    
    Returns:
        {
            "available": bool,
            "version": str,
            "requirements": List[str],
            "notes": str
        }
    """
    result = {
        "provider": provider,
        "available": False,
        "version": None,
        "requirements": [],
        "notes": ""
    }
    
    if provider == "mock":
        result["available"] = True
        result["version"] = "1.0"
        result["notes"] = "测试用占位实现，始终可用"
    
    elif provider == "whisperx":
        try:
            import whisperx
            result["available"] = True
            result["version"] = getattr(whisperx, '__version__', 'unknown')
        except ImportError:
            result["requirements"] = ["pip install whisperx"]
            result["notes"] = "需要安装 whisperx 及其依赖"
    
    elif provider == "faster-whisper":
        try:
            from faster_whisper import WhisperModel
            result["available"] = True
            result["version"] = "installed"
        except ImportError:
            result["requirements"] = ["pip install faster-whisper"]
            result["notes"] = "需要安装 faster-whisper"
    
    elif provider == "openai":
        try:
            import openai
            result["available"] = bool(os.getenv("OPENAI_API_KEY"))
            result["version"] = getattr(openai, '__version__', 'unknown')
            if not result["available"]:
                result["notes"] = "已安装 openai 库，但未设置 OPENAI_API_KEY"
            result["requirements"] = ["pip install openai", "设置 OPENAI_API_KEY 环境变量"]
        except ImportError:
            result["requirements"] = ["pip install openai"]
            result["notes"] = "需要安装 openai 库并设置 API Key"
    
    return result


def run_whisperx(
    audio_file: str,
    *,
    lang_hint: str | None = "auto",
    device: str | None = None
) -> dict:
    """
    WhisperX 直接调用接口（A 计划 Day 1）
    
    Args:
        audio_file: 音频文件路径
        lang_hint: 语言提示（"auto" 自动检测）
        device: 设备（None=自动检测）
    
    Returns:
        {"file": str, "lang": str, "lines": int}
    """
    try:
        import whisperx
        import torch
        
        # 检测设备
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        compute_type = "float16" if device == "cuda" else "int8"
        
        logging.info(f"[ASR-WHISPERX] starting whisperx device={device}")
        
        # 加载模型
        model = whisperx.load_model(
            "base",
            device=device,
            compute_type=compute_type
        )
        
        # 转录
        result = model.transcribe(
            audio_file,
            language=None if lang_hint == "auto" else lang_hint,
            batch_size=16 if device == "cuda" else 4
        )
        
        # 对齐
        try:
            model_a, metadata = whisperx.load_align_model(
                language_code=result["language"],
                device=device
            )
            result = whisperx.align(
                result["segments"],
                model_a,
                metadata,
                audio_file,
                device
            )
        except Exception as e:
            logging.warning(f"[ASR-WHISPERX] 对齐失败: {e}")
        
        # 输出 SRT
        from pathlib import Path
        audio_path = Path(audio_file)
        srt_file = audio_path.with_suffix('.srt')
        
        with open(srt_file, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(result["segments"], 1):
                start = _format_timestamp(seg["start"])
                end = _format_timestamp(seg["end"])
                text = seg["text"].strip()
                
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{text}\n\n")
        
        lines = len(result["segments"])
        detected_lang = result.get("language", lang_hint)
        
        logging.info(f"[ASR] audio={audio_file} srt={srt_file} lines={lines}")
        
        return {
            "file": str(srt_file),
            "lang": detected_lang,
            "lines": lines
        }
    
    except ImportError:
        logging.error("[ASR] error=whisperx not installed")
        return {"file": ""}
    
    except Exception as e:
        logging.error(f"[ASR] error={str(e)[:100]}")
        return {"file": ""}


# 导出的公共接口
__all__ = [
    'run_asr',
    'run_whisperx',
    'check_asr_availability'
]

