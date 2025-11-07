# -*- coding: utf-8 -*-
"""
GPU 工具模块
自动检测GPU、显存、计算能力，提供自适应配置
"""
import logging
import torch
from typing import Dict, Tuple, Optional


def get_gpu_info() -> Dict:
    """
    获取GPU信息
    
    Returns:
        {
            "available": bool,
            "name": str,
            "vram_total_mb": int,
            "vram_free_mb": int,
            "compute_capability": tuple,  # (major, minor)
            "cuda_version": str
        }
    """
    info = {
        "available": False,
        "name": "CPU",
        "vram_total_mb": 0,
        "vram_free_mb": 0,
        "compute_capability": (0, 0),
        "cuda_version": "N/A"
    }
    
    if not torch.cuda.is_available():
        return info
    
    try:
        info["available"] = True
        info["name"] = torch.cuda.get_device_name(0)
        info["cuda_version"] = torch.version.cuda or "unknown"
        
        # 获取计算能力
        if hasattr(torch.cuda, 'get_device_capability'):
            info["compute_capability"] = torch.cuda.get_device_capability(0)
        
        # 获取显存信息（优先使用pynvml，更准确）
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            info["vram_total_mb"] = mem_info.total // 1024 // 1024
            info["vram_free_mb"] = mem_info.free // 1024 // 1024
            pynvml.nvmlShutdown()
        except:
            # 回退到torch
            info["vram_total_mb"] = torch.cuda.get_device_properties(0).total_memory // 1024 // 1024
            # 粗略估计可用显存
            torch.cuda.empty_cache()
            info["vram_free_mb"] = info["vram_total_mb"] - (torch.cuda.memory_allocated(0) // 1024 // 1024)
    
    except Exception as e:
        logging.warning(f"[GPU] 获取GPU信息失败: {e}")
    
    return info


def select_device_and_dtype(config: Dict, gpu_info: Optional[Dict] = None) -> Dict:
    """
    自动选择设备和数据类型
    
    Args:
        config: ASR配置
        gpu_info: GPU信息（可选，不提供则自动获取）
    
    Returns:
        {
            "device": "cuda" or "cpu",
            "dtype": "float32" or "float16" or "bfloat16",
            "compute_type": "float32" or "float16" or "bfloat16" or "int8_float16",
            "batch_size": int,
            "reason": str
        }
    """
    if gpu_info is None:
        gpu_info = get_gpu_info()
    
    device_cfg = config.get("device", "auto")
    compute_type_cfg = config.get("compute_type", "float16")
    batch_size_cfg = config.get("batch_size", 16)
    
    result = {
        "device": "cpu",
        "dtype": "float32",
        "compute_type": "float32",
        "batch_size": batch_size_cfg,
        "reason": ""
    }
    
    # 1. 设备选择
    if device_cfg == "cpu":
        result["reason"] = "用户强制CPU"
        result["batch_size"] = min(batch_size_cfg, 8)  # CPU限制批量
        return result
    
    if device_cfg == "cuda" and not gpu_info["available"]:
        logging.warning("[GPU] 用户指定CUDA但GPU不可用，回退到CPU")
        result["reason"] = "GPU不可用，回退CPU"
        result["batch_size"] = min(batch_size_cfg, 8)
        return result
    
    if device_cfg == "auto" and not gpu_info["available"]:
        result["reason"] = "auto模式，GPU不可用"
        result["batch_size"] = min(batch_size_cfg, 8)
        return result
    
    # GPU可用
    result["device"] = "cuda"
    vram_free = gpu_info["vram_free_mb"]
    cc_major, cc_minor = gpu_info["compute_capability"]
    
    # 2. 数据类型选择
    # Ampere (8.x) 或 Ada (8.9+) 优先 bfloat16
    prefer_bf16 = config.get("gpu", {}).get("prefer_bf16", True)
    
    if cc_major >= 8 and prefer_bf16:
        result["dtype"] = "bfloat16"
    elif cc_major >= 7:  # Turing, Ampere
        result["dtype"] = "float16"
    else:
        result["dtype"] = "float32"
    
    # 3. compute_type 选择（WhisperX专用）
    if compute_type_cfg == "auto":
        if vram_free >= 10240:  # >=10GB
            result["compute_type"] = "float16"
        elif vram_free >= 6144:  # 6-10GB
            result["compute_type"] = "float16"
        else:  # <6GB
            result["compute_type"] = "int8_float16"
    else:
        result["compute_type"] = compute_type_cfg
    
    # 4. 批量大小自适应
    if vram_free >= 12288:  # >=12GB
        result["batch_size"] = min(batch_size_cfg, 32)
    elif vram_free >= 8192:  # 8-12GB
        result["batch_size"] = min(batch_size_cfg, 20)
    elif vram_free >= 6144:  # 6-8GB
        result["batch_size"] = min(batch_size_cfg, 12)
    else:  # <6GB
        result["batch_size"] = min(batch_size_cfg, 8)
        if result["compute_type"] != "int8_float16":
            result["compute_type"] = "int8_float16"
    
    result["reason"] = f"GPU:{gpu_info['name']}, VRAM:{vram_free}MB, CC:{cc_major}.{cc_minor}"
    
    return result


def init_torch_runtime(device: str, dtype: str):
    """
    初始化PyTorch运行时优化
    
    Args:
        device: "cuda" or "cpu"
        dtype: "float32" or "float16" or "bfloat16"
    """
    if device == "cuda":
        # 设置matmul精度
        if hasattr(torch, 'set_float32_matmul_precision'):
            torch.set_float32_matmul_precision("medium")
        
        # 启用cudnn benchmark
        if hasattr(torch.backends, 'cudnn'):
            torch.backends.cudnn.benchmark = True
        
        # 清空缓存
        torch.cuda.empty_cache()
        
        logging.info(f"[GPU] PyTorch运行时初始化完成: matmul_precision=medium, cudnn_benchmark=True")


def adaptive_batch_size(current_batch: int, vram_free_mb: int, oom_occurred: bool = False) -> int:
    """
    自适应调整批量大小
    
    Args:
        current_batch: 当前批量
        vram_free_mb: 可用显存(MB)
        oom_occurred: 是否发生OOM
    
    Returns:
        调整后的批量大小
    """
    if oom_occurred:
        # OOM降级：减半
        new_batch = max(1, current_batch // 2)
        logging.warning(f"[GPU] OOM检测到，批量降级: {current_batch} -> {new_batch}")
        return new_batch
    
    # 基于显存的建议批量
    if vram_free_mb >= 12288:
        suggested = 32
    elif vram_free_mb >= 8192:
        suggested = 20
    elif vram_free_mb >= 6144:
        suggested = 12
    else:
        suggested = 8
    
    return min(current_batch, suggested)


def log_gpu_config(config: Dict, gpu_info: Dict):
    """
    记录GPU配置到日志
    
    Args:
        config: 配置字典
        gpu_info: GPU信息
    """
    if config["device"] == "cuda":
        logging.info(
            f"[ASR][GPU] device={config['device']} "
            f"cc={gpu_info['compute_capability'][0]}.{gpu_info['compute_capability'][1]} "
            f"vram_free={gpu_info['vram_free_mb']}MB "
            f"dtype={config['dtype']} "
            f"compute={config['compute_type']} "
            f"batch={config['batch_size']}"
        )
    else:
        logging.info(
            f"[ASR][CPU] device={config['device']} "
            f"dtype={config['dtype']} "
            f"batch={config['batch_size']} "
            f"reason={config.get('reason', 'N/A')}"
        )

