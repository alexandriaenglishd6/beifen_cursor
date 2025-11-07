# -*- coding: utf-8 -*-
"""
字幕优化服务 - 统一调用 clean_subs 和 quality_postprocess
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class SubtitleOptimizeService:
    """
    字幕优化服务
    
    职责：
    1. 统一调用 clean_subs 和 quality_postprocess
    2. 根据配置决定是否启用优化
    3. 处理不同格式的字幕文件（SRT, VTT, TXT）
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化
        
        Args:
            config: 配置字典，包含 postprocess 和 quality 配置
        """
        self.config = config or {}
        self.postprocess_config = self.config.get("postprocess", {})
        self.quality_config = self.config.get("quality", {})
    
    def optimize_subtitle_file(
        self,
        subtitle_path: Path,
        lang: Optional[str] = None
    ) -> Dict:
        """
        优化单个字幕文件
        
        Args:
            subtitle_path: 字幕文件路径
            lang: 字幕语言（用于质量优化）
        
        Returns:
            优化结果字典，包含：
            - success: 是否成功
            - optimized: 是否进行了优化
            - stats: 统计信息
            - error: 错误信息（如果有）
        """
        if not subtitle_path.exists():
            return {
                "success": False,
                "optimized": False,
                "error": f"文件不存在: {subtitle_path}"
            }
        
        try:
            # 读取原始文件
            original_content = subtitle_path.read_text(encoding='utf-8', errors='ignore')
            if not original_content.strip():
                return {
                    "success": False,
                    "optimized": False,
                    "error": "文件为空"
                }
            
            # 检查是否启用优化
            postprocess_enabled = self.postprocess_config.get("enabled", True)
            quality_enabled = self.quality_config.get("enabled", True)
            
            if not postprocess_enabled and not quality_enabled:
                return {
                    "success": True,
                    "optimized": False,
                    "stats": {"enabled": False}
                }
            
            # 根据文件扩展名选择处理方式
            ext = subtitle_path.suffix.lower()
            optimized_content = original_content
            stats = {}
            
            # 1. 后处理优化（clean_subs）
            if postprocess_enabled:
                try:
                    from clean_subs import clean_srt_subs, clean_vtt_subs, clean_text_subs
                    
                    # 构建后处理选项
                    postprocess_opts = {
                        "merge_short_lines": self.postprocess_config.get("merge_short_lines", True),
                        "dedupe_near_duplicates": self.postprocess_config.get("dedupe_near_duplicates", True),
                        "strip_nonspeech": self.postprocess_config.get("strip_nonspeech", False),
                        "normalize_whitespace": self.postprocess_config.get("normalize_whitespace", True),
                        "short_line_len": self.postprocess_config.get("short_line_len", 12),
                        "fix_overlapping_timestamps": self.postprocess_config.get("fix_overlapping_timestamps", True)
                    }
                    
                    if ext == ".srt":
                        optimized_content = clean_srt_subs(original_content, opts=postprocess_opts)
                        stats["postprocess"] = "srt"
                    elif ext == ".vtt":
                        optimized_content = clean_vtt_subs(original_content, opts=postprocess_opts)
                        stats["postprocess"] = "vtt"
                    elif ext == ".txt":
                        optimized_content = clean_text_subs(original_content, opts=postprocess_opts)
                        stats["postprocess"] = "txt"
                    else:
                        logger.warning(f"不支持的文件格式: {ext}")
                        stats["postprocess"] = "skipped"
                    
                except ImportError as e:
                    logger.warning(f"无法导入 clean_subs: {e}")
                    stats["postprocess"] = "error"
                except Exception as e:
                    logger.error(f"后处理优化失败: {e}")
                    stats["postprocess"] = "error"
                    # 继续使用原始内容
            
            # 2. 质量优化（quality_postprocess，仅对中文字幕）
            if quality_enabled and lang and lang.lower().startswith("zh"):
                try:
                    from core.quality_postprocess import process_subtitle_quality
                    
                    # 提取文本行（用于质量优化）
                    if ext in [".srt", ".vtt"]:
                        # 从 SRT/VTT 提取文本行
                        lines = []
                        for line in optimized_content.splitlines():
                            line = line.strip()
                            # 跳过时间码和序号
                            if not line or line.isdigit() or "-->" in line or line.upper().startswith("WEBVTT"):
                                continue
                            lines.append(line)
                    else:
                        # TXT 格式直接按行分割
                        lines = [line.strip() for line in optimized_content.splitlines() if line.strip()]
                    
                    if lines:
                        # 执行质量优化
                        optimized_lines, quality_stats = process_subtitle_quality(
                            lines,
                            enabled=True,
                            lang_filter="zh"
                        )
                        
                        # 如果是 SRT/VTT，需要重新组装
                        if ext in [".srt", ".vtt"]:
                            # 简单处理：将优化后的文本行替换回原文件
                            # 注意：这里简化处理，实际应该保持时间码结构
                            # 为了不影响时间码，我们只对文本部分进行优化
                            # 这里暂时跳过，因为需要更复杂的解析
                            stats["quality"] = "skipped_format"
                        else:
                            # TXT 格式直接使用优化后的行
                            optimized_content = "\n".join(optimized_lines) + "\n"
                            stats["quality"] = quality_stats
                    
                except ImportError as e:
                    logger.warning(f"无法导入 quality_postprocess: {e}")
                    stats["quality"] = "error"
                except Exception as e:
                    logger.error(f"质量优化失败: {e}")
                    stats["quality"] = "error"
            
            # 3. 保存优化后的内容（如果有变化）
            if optimized_content != original_content:
                # 备份原文件（可选）
                # backup_path = subtitle_path.with_suffix(subtitle_path.suffix + ".bak")
                # subtitle_path.rename(backup_path)
                
                # 写入优化后的内容
                subtitle_path.write_text(optimized_content, encoding='utf-8')
                
                return {
                    "success": True,
                    "optimized": True,
                    "stats": stats,
                    "original_size": len(original_content),
                    "optimized_size": len(optimized_content)
                }
            else:
                return {
                    "success": True,
                    "optimized": False,
                    "stats": stats
                }
        
        except Exception as e:
            logger.error(f"优化字幕文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "optimized": False,
                "error": str(e)
            }
    
    def optimize_subtitle_files(
        self,
        subtitle_paths: List[Path],
        lang_hint: Optional[str] = None
    ) -> Dict:
        """
        批量优化字幕文件
        
        Args:
            subtitle_paths: 字幕文件路径列表
            lang_hint: 语言提示（从文件名提取）
        
        Returns:
            批量优化结果字典
        """
        results = {
            "total": len(subtitle_paths),
            "success": 0,
            "failed": 0,
            "optimized": 0,
            "details": []
        }
        
        for path in subtitle_paths:
            # 从文件名提取语言（格式：video_id.lang.ext）
            lang = lang_hint
            if not lang and path.stem:
                parts = path.stem.split(".")
                if len(parts) >= 2:
                    lang = parts[-1]  # 假设最后一部分是语言代码
            
            result = self.optimize_subtitle_file(path, lang=lang)
            results["details"].append({
                "path": str(path),
                "lang": lang,
                **result
            })
            
            if result["success"]:
                results["success"] += 1
                if result.get("optimized", False):
                    results["optimized"] += 1
            else:
                results["failed"] += 1
        
        return results

