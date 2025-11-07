# -*- coding: utf-8 -*-
"""
Day 2: 内容分析模块（基础版）
分析中文字幕文本：词频、难度、统计
零外部依赖，纯正则实现
"""
from __future__ import annotations
import re
from typing import Dict, List, Tuple, Any
from collections import Counter
from pathlib import Path


# 内置中文停用词表（最小集）
CHINESE_STOPWORDS = {
    "我们", "你们", "他们", "她们", "它们",
    "这个", "那个", "哪个", "这样", "那样",
    "然后", "就是", "以及", "还有", "而且",
    "但是", "如果", "因为", "所以", "虽然",
    "不过", "只是", "可以", "能够", "应该",
    "一个", "两个", "一些", "很多", "非常",
    "什么", "怎么", "为什么", "哪里", "谁",
    "的", "了", "在", "是", "有", "和", "与",
    "啊", "吗", "呢", "吧", "哦", "嗯",
}

# 英文停用词表（最小集）
ENGLISH_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "on", "at", "for", "with", "by", "from",
    "and", "or", "but", "not", "if", "so", "as", "that", "this",
    "it", "he", "she", "they", "we", "you", "me", "my", "your",
    "can", "will", "would", "should", "could", "may", "might",
    "do", "does", "did", "have", "has", "had",
}


def analyze_subtitle(text: str) -> Dict[str, Any]:
    """
    分析字幕文本，返回统计数据
    
    Args:
        text: 字幕文本（支持中英文混排）
    
    Returns:
        {
            "chars": int,                 # 总字符数
            "sentences": int,             # 句子数
            "avg_sentence_len": float,    # 平均句长
            "top_words": [(word, count)], # 词频Top10
            "keywords": [str],            # 关键词Top10
            "difficulty": int             # 难度0-100
        }
    """
    if not text or not text.strip():
        return {
            "chars": 0,
            "sentences": 0,
            "avg_sentence_len": 0.0,
            "top_words": [],
            "keywords": [],
            "difficulty": 0
        }
    
    # 1. 基础统计
    text = text.strip()
    
    # 总字符数（中文+英文+数字，排除空白）
    chars = len(re.sub(r'\s+', '', text))
    
    # 句子分割（按中英文标点 + 换行）
    sentences = re.split(r'[。！？!?\n]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    sentence_count = len(sentences)
    
    # 平均句长（按字符计，不含空白）
    if sentence_count > 0:
        total_chars_in_sentences = sum(len(re.sub(r'\s+', '', s)) for s in sentences)
        avg_sentence_len = total_chars_in_sentences / sentence_count
    else:
        avg_sentence_len = 0.0
    
    # 2. 分词与词频统计
    words = _extract_words(text)
    
    # 过滤停用词
    words_filtered = [w for w in words if w.lower() not in CHINESE_STOPWORDS and w.lower() not in ENGLISH_STOPWORDS]
    
    # 词频统计（先过滤低频词 < 2）
    word_counts = Counter(words_filtered)
    # 只保留频次 >= 2 的词
    word_counts = {word: count for word, count in word_counts.items() if count >= 2}
    top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # 关键词（与top_words相同，后续可优化）
    keywords = [word for word, _ in top_words]
    
    # 3. 难度评分（0-100）
    difficulty = _calculate_difficulty(
        chars=chars,
        sentences=sentence_count,
        avg_sentence_len=avg_sentence_len,
        unique_words=len(word_counts),
        total_words=len(words_filtered)
    )
    
    return {
        "chars": chars,
        "sentences": sentence_count,
        "avg_sentence_len": round(avg_sentence_len, 2),
        "top_words": top_words,
        "keywords": keywords,
        "difficulty": difficulty
    }


def _extract_words(text: str) -> List[str]:
    """
    提取词汇（中英文混合）
    - 中文：2-4字窗口滑动切分（清洗版）
    - 英文：按单词边界分割
    """
    import unicodedata
    
    words = []
    
    # 0. 标准化文本（NFKC：兼容性分解+组合）
    text = unicodedata.normalize('NFKC', text)
    
    # 1. 提取英文单词（连续字母+数字，长度>=2）
    english_words = re.findall(r'\b[a-zA-Z]{2,}\b', text)
    words.extend(english_words)
    
    # 2. 提取中文（仅保留 CJK 基本区 U+4E00-U+9FFF）
    chinese_text = ''.join(c for c in text if '\u4e00' <= c <= '\u9fff')
    
    # 3. 双字窗口（互信息基础）
    bigrams = []
    for i in range(len(chinese_text) - 1):
        word = chinese_text[i:i+2]
        if len(word) == 2 and not _is_repetitive(word):
            bigrams.append(word)
    
    # 4. 三字窗口（较保守）
    trigrams = []
    for i in range(len(chinese_text) - 2):
        word = chinese_text[i:i+3]
        if len(word) == 3 and not _is_repetitive(word):
            trigrams.append(word)
    
    # 合并并返回
    words.extend(bigrams)
    words.extend(trigrams)
    
    return words


def _is_repetitive(word: str) -> bool:
    """检查是否为重复字符（如"哈哈哈"）"""
    if len(word) < 2:
        return False
    # 如果超过一半字符相同，视为重复
    from collections import Counter
    counts = Counter(word)
    max_count = max(counts.values())
    return max_count > len(word) * 0.6


def _calculate_difficulty(
    chars: int,
    sentences: int,
    avg_sentence_len: float,
    unique_words: int,
    total_words: int
) -> int:
    """
    计算难度评分（0-100）
    
    四因子线性加权：
    - 句长指数（20%）：句子越长越难
    - 词汇多样性（30%）：unique/total 比例
    - 文本长度（25%）：总字符数
    - 词汇密度（25%）：总词数与句数比
    """
    if chars == 0 or sentences == 0:
        return 0
    
    # 1. 句长因子（0-20）：avg_sentence_len 映射到 0-20
    # 假设：句长 < 10 = 简单，20-30 = 中等，> 50 = 困难
    sentence_factor = min(20, (avg_sentence_len / 50.0) * 20)
    
    # 2. 词汇多样性（0-30）：unique/total
    if total_words > 0:
        diversity = unique_words / total_words
    else:
        diversity = 0
    diversity_factor = diversity * 30
    
    # 3. 文本长度因子（0-25）：chars 映射
    # 假设：< 1000 字 = 简单，5000-10000 = 中等，> 20000 = 困难
    length_factor = min(25, (chars / 20000.0) * 25)
    
    # 4. 词汇密度因子（0-25）：总词数/句数
    word_density = total_words / sentences if sentences > 0 else 0
    # 假设：密度 < 5 = 简单，10-15 = 中等，> 20 = 困难
    density_factor = min(25, (word_density / 20.0) * 25)
    
    # 总分
    total_score = sentence_factor + diversity_factor + length_factor + density_factor
    
    return int(min(100, max(0, total_score)))


def get_content_text_for_analysis(run_dir: Path) -> str:
    """
    获取用于分析的中文文本（优先级：翻译 > 双语 > 原始字幕）
    
    Args:
        run_dir: 运行目录
    
    Returns:
        拼接的中文文本（限制前100k字符）
    """
    run_dir = Path(run_dir)
    text_parts = []
    
    # 优先1：翻译产物 translations/
    translations_dir = run_dir / "translations"
    if translations_dir.exists():
        for ext in [".srt", ".txt", ".vtt"]:
            for file in translations_dir.glob(f"*{ext}"):
                try:
                    content = file.read_text(encoding="utf-8")
                    # 如果是SRT，提取纯文本
                    if ext == ".srt":
                        content = _extract_text_from_srt(content)
                    text_parts.append(content)
                except:
                    pass
    
    # 优先2：双语字幕 bilingual/ 中文列
    if not text_parts:
        bilingual_dir = run_dir / "bilingual"
        if bilingual_dir.exists():
            for tsv_file in bilingual_dir.glob("*.tsv"):
                try:
                    content = tsv_file.read_text(encoding="utf-8")
                    # 提取中文列（假设第一列是中文）
                    lines = content.split('\n')
                    for line in lines:
                        if '\t' in line:
                            parts = line.split('\t')
                            if parts:
                                text_parts.append(parts[0])
                except:
                    pass
    
    # 拼接并截断到100k字符
    full_text = '\n'.join(text_parts)
    if len(full_text) > 100000:
        full_text = full_text[:100000]
    
    return full_text


def _extract_text_from_srt(srt_content: str) -> str:
    """从SRT格式提取纯文本"""
    lines = []
    for line in srt_content.split('\n'):
        line = line.strip()
        # 跳过序号和时间戳行
        if not line or line.isdigit() or '-->' in line:
            continue
        lines.append(line)
    return '\n'.join(lines)


__all__ = ['analyze_subtitle', 'get_content_text_for_analysis']

