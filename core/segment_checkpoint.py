# -*- coding: utf-8 -*-
"""
ASR分段断点续跑管理
支持.done标记、分段超时、失败隔离
"""
import os
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional


class SegmentCheckpoint:
    """分段检查点管理器"""
    
    def __init__(self, tmp_dir: str):
        """
        初始化检查点管理器
        
        Args:
            tmp_dir: 临时目录路径（asr_tmp/）
        """
        self.tmp_dir = Path(tmp_dir)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
    
    def is_segment_done(self, segment_id: int) -> bool:
        """
        检查分段是否已完成
        
        Args:
            segment_id: 分段ID
        
        Returns:
            是否已完成
        """
        done_file = self.tmp_dir / f"seg_{segment_id}.json.done"
        return done_file.exists()
    
    def load_segment_result(self, segment_id: int) -> Optional[Dict]:
        """
        加载分段结果
        
        Args:
            segment_id: 分段ID
        
        Returns:
            分段结果字典，如果不存在返回None
        """
        if not self.is_segment_done(segment_id):
            return None
        
        result_file = self.tmp_dir / f"seg_{segment_id}.json"
        
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                result = json.load(f)
            
            logging.info(f"[CHECKPOINT] 加载断点: seg_{segment_id} ({len(result.get('segments', []))} segments)")
            return result
        
        except Exception as e:
            logging.warning(f"[CHECKPOINT] 加载seg_{segment_id}失败: {e}")
            return None
    
    def save_segment_result(self, segment_id: int, result: Dict):
        """
        保存分段结果并标记完成
        
        Args:
            segment_id: 分段ID
            result: 分段结果
        """
        result_file = self.tmp_dir / f"seg_{segment_id}.json"
        done_file = self.tmp_dir / f"seg_{segment_id}.json.done"
        
        try:
            # 先保存结果
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            # 再创建.done标记
            done_file.touch()
            
            logging.info(f"[CHECKPOINT] 保存断点: seg_{segment_id} ({len(result.get('segments', []))} segments)")
        
        except Exception as e:
            logging.error(f"[CHECKPOINT] 保存seg_{segment_id}失败: {e}")
            raise
    
    def mark_segment_failed(self, segment_id: int, error: str):
        """
        标记分段失败
        
        Args:
            segment_id: 分段ID
            error: 错误信息
        """
        failed_file = self.tmp_dir / f"seg_{segment_id}_failed.json"
        
        try:
            failure_info = {
                "segment_id": segment_id,
                "error": error,
                "timestamp": time.time()
            }
            
            with open(failed_file, 'w', encoding='utf-8') as f:
                json.dump(failure_info, f, ensure_ascii=False, indent=2)
            
            logging.warning(f"[CHECKPOINT] 标记失败: seg_{segment_id} - {error}")
        
        except Exception as e:
            logging.error(f"[CHECKPOINT] 标记失败时出错: {e}")
    
    def get_failed_segments(self) -> List[Dict]:
        """
        获取所有失败的分段信息
        
        Returns:
            失败分段列表
        """
        failed = []
        
        for failed_file in self.tmp_dir.glob("seg_*_failed.json"):
            try:
                with open(failed_file, 'r', encoding='utf-8') as f:
                    failed.append(json.load(f))
            except Exception as e:
                logging.warning(f"[CHECKPOINT] 读取失败记录出错: {e}")
        
        return failed
    
    def get_progress(self) -> Dict:
        """
        获取整体进度
        
        Returns:
            {
                "total": int,
                "done": int,
                "failed": int,
                "pending": int
            }
        """
        # 统计.done文件
        done_files = list(self.tmp_dir.glob("seg_*.json.done"))
        done_count = len(done_files)
        
        # 统计失败文件
        failed_files = list(self.tmp_dir.glob("seg_*_failed.json"))
        failed_count = len(failed_files)
        
        # 统计所有segment文件（排除failed）
        all_seg_files = list(self.tmp_dir.glob("seg_*.json"))
        # 过滤掉failed文件
        all_seg_files = [f for f in all_seg_files if not f.name.endswith("_failed.json")]
        total_count = len(all_seg_files)
        
        pending_count = max(0, total_count - done_count)
        
        return {
            "total": total_count,
            "done": done_count,
            "failed": failed_count,
            "pending": pending_count
        }
    
    def cleanup(self):
        """清理所有检查点文件"""
        try:
            for file in self.tmp_dir.glob("seg_*"):
                file.unlink()
            logging.info("[CHECKPOINT] 检查点清理完成")
        except Exception as e:
            logging.warning(f"[CHECKPOINT] 清理失败: {e}")


def process_segment_with_timeout(
    segment_func,
    segment_id: int,
    timeout_sec: int,
    checkpoint: SegmentCheckpoint,
    *args,
    **kwargs
) -> Optional[Dict]:
    """
    带超时的分段处理
    
    Args:
        segment_func: 分段处理函数
        segment_id: 分段ID
        timeout_sec: 超时时间（秒）
        checkpoint: 检查点管理器
        *args, **kwargs: 传给segment_func的参数
    
    Returns:
        处理结果，超时或失败返回None
    """
    import signal
    
    # 检查是否已完成
    if checkpoint.is_segment_done(segment_id):
        return checkpoint.load_segment_result(segment_id)
    
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Segment {segment_id} 处理超时（>{timeout_sec}秒）")
    
    try:
        # 设置超时（仅Linux/Unix）
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_sec)
        
        # 执行处理
        result = segment_func(segment_id, *args, **kwargs)
        
        # 取消超时
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        
        # 保存结果
        if result:
            checkpoint.save_segment_result(segment_id, result)
        
        return result
    
    except TimeoutError as e:
        logging.error(f"[SEGMENT] {e}")
        checkpoint.mark_segment_failed(segment_id, str(e))
        return None
    
    except Exception as e:
        logging.error(f"[SEGMENT] seg_{segment_id} 处理失败: {e}")
        checkpoint.mark_segment_failed(segment_id, str(e))
        return None
    
    finally:
        # 确保取消超时
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)

