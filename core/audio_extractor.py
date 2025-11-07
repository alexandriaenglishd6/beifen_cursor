# -*- coding: utf-8 -*-
"""
A 计划 Day 1: 音频提取模块
从 YouTube 提取 16k mono WAV 用于 WhisperX
"""
from __future__ import annotations
import os
import logging
import subprocess
import tempfile
from pathlib import Path


def extract_audio(
    video_url: str,
    *,
    out_dir: str,
    fmt: str = "wav",
    sr: int = 16000
) -> str:
    """
    从 YouTube URL 提取音频（16k mono）
    
    Args:
        video_url: 视频 URL
        out_dir: 输出目录
        fmt: 格式（wav/mp3）
        sr: 采样率（Hz），WhisperX 推荐 16000
    
    Returns:
        音频文件路径；失败返回空字符串
    """
    try:
        # 确保输出目录存在
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        
        # 提取视频 ID
        video_id = _extract_video_id(video_url)
        output_file = Path(out_dir) / f"{video_id}.{fmt}"
        
        # 检查 yt-dlp 是否可用
        if not _check_ytdlp():
            logging.error("[AUDIO] yt-dlp 未安装或不可用")
            return ""
        
        logging.info(f"[AUDIO] 开始提取音频: {video_url}")
        
        # 获取 ffmpeg 路径（如果有 imageio-ffmpeg）
        ffmpeg_location = _get_ffmpeg_location()
        
        # 先下载最佳音频流（不转换）
        temp_file = output_file.with_suffix(".temp")
        
        cmd = [
            "yt-dlp",
            "-f", "bestaudio",  # 最佳音频流
            "-o", str(temp_file),
            "--no-playlist",
            "--max-downloads", "1",
            video_url
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 分钟超时
        )
        
        # 退出码 101 表示达到 --max-downloads，这是正常的
        if result.returncode != 0 and result.returncode != 101:
            logging.error(f"[AUDIO] 下载失败 (code {result.returncode}): {result.stderr[:200]}")
            return ""
        
        # 查找下载的文件（可能有各种扩展名或无扩展名）
        downloaded_file = None
        
        # 先检查是否已存在（无扩展名）
        if temp_file.exists():
            downloaded_file = temp_file
        else:
            # 检查常见扩展名
            for ext in [".webm", ".m4a", ".opus", ".mp3", ".wav"]:
                candidate = temp_file.with_suffix(ext)
                if candidate.exists():
                    downloaded_file = candidate
                    break
        
        if not downloaded_file:
            # 尝试模糊搜索
            pattern = str(temp_file.parent / f"{temp_file.stem}*")
            import glob
            candidates = glob.glob(pattern)
            if candidates:
                downloaded_file = Path(candidates[0])
            else:
                logging.error("[AUDIO] 音频文件未下载")
                return ""
        
        # 如果已经是 WAV 且采样率正确，直接返回
        if downloaded_file.suffix.lower() == f".{fmt}" and sr == 16000:
            actual_file = output_file.with_suffix(f".{fmt}")
            downloaded_file.rename(actual_file)
        else:
            # 使用 ffmpeg 转换
            actual_file = output_file.with_suffix(f".{fmt}")
            if not _convert_audio(str(downloaded_file), str(actual_file), sr, ffmpeg_location):
                logging.error("[AUDIO] 音频转换失败")
                try:
                    downloaded_file.unlink()  # 清理临时文件
                except:
                    pass
                return ""
            
            # 清理临时文件
            try:
                downloaded_file.unlink()
            except:
                pass
        
        # 检查最终文件
        if not actual_file.exists():
            logging.error("[AUDIO] 最终音频文件不存在")
            return ""
        
        # 验证文件大小
        file_size = actual_file.stat().st_size
        if file_size == 0:
            logging.error("[AUDIO] 音频文件为空")
            return ""
        
        # 获取时长（可选，不阻塞）
        duration = _get_audio_duration(str(actual_file))
        
        logging.info(f"[AUDIO] 提取成功: {actual_file} ({file_size} bytes, {duration:.1f}s)")
        
        return str(actual_file)
    
    except subprocess.TimeoutExpired:
        logging.error("[AUDIO] 提取超时（>5分钟）")
        return ""
    
    except Exception as e:
        logging.error(f"[AUDIO] 提取异常: {e}")
        return ""


def _check_ytdlp() -> bool:
    """检查 yt-dlp 是否可用"""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def _extract_video_id(url: str) -> str:
    """从 URL 提取视频 ID"""
    import re
    from datetime import datetime
    
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


def _get_ffmpeg_location() -> str:
    """尝试获取 ffmpeg 位置（优先使用 imageio-ffmpeg）"""
    try:
        import imageio_ffmpeg
        import os
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        # 返回目录路径
        return os.path.dirname(ffmpeg_exe)
    except:
        return ""


def _convert_audio(input_file: str, output_file: str, sr: int, ffmpeg_location: str) -> bool:
    """使用 ffmpeg 转换音频格式"""
    try:
        # 确定 ffmpeg 可执行文件
        ffmpeg_cmd = "ffmpeg"
        if ffmpeg_location:
            ffmpeg_cmd = str(Path(ffmpeg_location) / "ffmpeg.exe")
        
        cmd = [
            ffmpeg_cmd,
            "-i", input_file,
            "-ar", str(sr),  # 采样率
            "-ac", "1",  # 单声道
            "-y",  # 覆盖输出文件
            output_file
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        return result.returncode == 0
    
    except:
        return False


def _get_audio_duration(audio_file: str) -> float:
    """获取音频时长（使用 ffprobe，可选）"""
    try:
        # 尝试获取 ffprobe
        ffprobe_cmd = "ffprobe"
        ffmpeg_loc = _get_ffmpeg_location()
        if ffmpeg_loc:
            ffprobe_cmd = str(Path(ffmpeg_loc) / "ffprobe.exe")
        
        cmd = [
            ffprobe_cmd,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_file
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return float(result.stdout.strip())
    except:
        pass
    
    return 0.0


__all__ = ['extract_audio']
