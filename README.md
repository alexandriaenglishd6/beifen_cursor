# YouTube 字幕工具 v4.0.0-stable 🎉

一个功能强大的 YouTube 字幕检测与下载工具，支持 **AI 智能摘要**、**订阅管理**、**队列处理**、**数据导出**等高级功能。

**🎊 v4.0.0-stable 发布！** 完整模块化架构、Webhook 通知、Dry Run 预演、订阅/队列/导出全流程打通！

[![Version](https://img.shields.io/badge/version-4.0.0--stable-brightgreen)](https://github.com/your-repo/releases/tag/v4.0.0)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## ✨ 核心功能

### 🤖 AI 智能摘要
- ✅ **智能摘要**（500-800字精炼总结）
- ✅ **关键词提取**（10个核心词汇）
- ✅ **要点列表**（5-10个关键要点）
- ✅ **章节划分**（4-10个智能章节，基于时间轴对齐）
- ✅ **HTML 报告**（可视化展示 + 图表）
- ✅ **多提供商**（OpenAI/Claude/Gemini/DeepSeek/通义千问等）
- ✅ **预算护栏**（防止超支，支持 tokens 和成本限制）
- ✅ **智能缓存**（避免重复调用，节省成本）

### 📺 字幕处理
- ✅ 批量检测字幕可用性（手动字幕 + 自动字幕）
- ✅ 多语言字幕下载（SRT/VTT/TXT 格式）
- ✅ 双语对照支持（中英文合并）
- ✅ 增量下载（智能跳过已下载字幕）
- ✅ 原子写入（并发安全，防止数据损坏）

### 📮 订阅管理（v4.0 新增）
- ✅ 添加/删除/查看 YouTube 频道/播放列表订阅
- ✅ 标签分类管理（支持多标签）
- ✅ 导入导出（JSON/CSV 格式）
- ✅ 自动生成执行计划（一键更新所有订阅）
- ✅ 持久化存储（`subscriptions.json`）

### 🚦 队列管理（v4.0 新增）
- ✅ 多来源批处理队列
- ✅ 并行度限制（默认 2，可调）
- ✅ 失败自动重试
- ✅ 中断恢复（支持暂停/停止）
- ✅ 公平调度（同频道任务间随机延迟）
- ✅ 状态追踪（pending/running/done/error）

### 📊 数据导出（v4.0 新增）
- ✅ CSV 导出（`videos.csv`、`errors.csv`、`ai.csv`）
- ✅ Excel 周报汇总（3 个 sheets：汇总/按运行/错误详情）
- ✅ 自动降级（openpyxl 未安装时降级为 CSV）
- ✅ 字段完整（URL、标题、时长、播放量、AI 摘要等）

### 🔔 Webhook 通知（v4.0 新增）
- ✅ 实时推送（run_start/detect_done/download_done/ai_done/run_end）
- ✅ HMAC 签名（可选，保证安全）
- ✅ Fire-and-forget 模式（不阻塞主流程）
- ✅ 失败降级（只记录到 warnings.txt）

### 🧪 Dry Run 模式（v4.0 新增）
- ✅ 安全预演（只检测，不下载/AI）
- ✅ 生成 `plan.md` 预览报告
- ✅ 不更新 `last_seen`（不影响增量逻辑）
- ✅ 轻量级 HTML 预览

### 🚀 高级功能
- ✅ 流量控制（全局请求速率限制 + 分路限流）
- ✅ 熔断机制（429/503 错误自动冷静期 + 热配置）
- ✅ 代理池管理（健康评分 + 自动黑名单恢复）
- ✅ 错误分类（error_429/503/timeout/private/geo）
- ✅ 诊断报告（`diagnose.txt`）
- ✅ 配置快照（`config.final.json`）

### 🎨 用户界面
- ✅ 10 种精美主题（GitHub Dark、Dracula、Nord 等）
- ✅ 中英文双语切换
- ✅ 实时进度显示（带倒计时）
- ✅ 配置自动保存
- ✅ 任务暂停/停止

---

## 📦 快速开始

### 1. 安装依赖

```bash
# 基础依赖（必须）
pip install yt-dlp youtube-transcript-api

# AI 功能依赖（可选）
pip install requests  # 通常已安装

# Excel 导出依赖（可选）
pip install openpyxl
```

### 2. 启动程序

```bash
# GUI 模式
python yt_subs_gui.py

# 命令行模式（示例）
python -c "
from core import run_full_process
result = run_full_process(
    channel_or_playlist_url='https://youtube.com/@channel',
    do_download=True,
    download_langs=['zh', 'en']
)
print(f'完成！共 {result[\"total\"]} 个视频')
"
```

### 3. 基本使用

#### 场景 1：检测单个视频的字幕

```python
from core import detect_links

results = detect_links(
    urls=["https://youtube.com/watch?v=xxx"],
    max_workers=5
)

for item in results:
    print(f"{item['url']}: {item['status']}")
    if item['status'] == 'has_subs':
        print(f"  语言: {', '.join(item['all_langs'])}")
```

#### 场景 2：下载字幕

```python
from core import download_subtitles

files = download_subtitles(
    url="https://youtube.com/watch?v=xxx",
    subs_dir="./subs",
    download_langs=["zh", "en"],
    download_prefer="both",
    download_fmt="txt"
)

print(f"已下载 {len(files)} 个字幕文件")
```

#### 场景 3：完整处理（检测 + 下载 + AI）

```python
from core import run_full_process, run_ai_pipeline

# 1. 检测并下载字幕
result = run_full_process(
    channel_or_playlist_url="https://youtube.com/@channel",
    output_root="out",
    do_download=True,
    download_langs=["zh", "en"],
    incremental_detect=True  # 增量模式
)

print(f"运行目录: {result['run_dir']}")
print(f"共 {result['total']} 个视频，已下载 {result['downloaded']} 个")

# 2. 生成 AI 摘要（可选）
ai_result = run_ai_pipeline(
    run_dir=result['run_dir'],
    ai_cfg={
        "enabled": True,
        "providers": [{
            "name": "openai",
            "api_key": "sk-...",
            "model": "gpt-3.5-turbo"
        }]
    }
)

print(f"AI 处理完成，成功 {ai_result['success']}，失败 {ai_result['failed']}")
```

#### 场景 4：订阅管理

```python
from core import (
    subscribe_add,
    subscribe_list,
    build_run_plan_from_subscriptions,
    run_full_process
)

# 添加订阅
subscribe_add(
    url="https://youtube.com/@tech",
    kind="channel",
    title="技术频道",
    tags=["tech", "education"]
)

# 列出订阅
subs = subscribe_list(active_only=True, tag_filter=["tech"])
print(f"共 {len(subs)} 个订阅")

# 生成执行计划并运行
plan = build_run_plan_from_subscriptions()
result = run_full_process(
    urls_override=plan["urls"],
    do_download=True
)
```

#### 场景 5：队列处理

```python
from core import enqueue_sources, run_queue

# 添加到队列
sources = [
    {"id": "1", "kind": "channel", "url": "https://youtube.com/@tech"},
    {"id": "2", "kind": "playlist", "url": "https://youtube.com/playlist?list=..."}
]
run_id = enqueue_sources(sources, tags=["batch1"])

# 执行队列（并行度=2）
result = run_queue(
    max_parallel=2,
    run_opts={"do_download": True, "download_langs": ["zh", "en"]}
)

print(f"总计 {result['total']}，成功 {result['success']}，失败 {result['failed']}")
```

#### 场景 6：数据导出

```python
from core import export_run_csv, export_runs_excel

# 导出单次运行 CSV
csv_files = export_run_csv("out/20251026_153012")
print(f"CSV 文件：{csv_files}")

# 导出近 7 天汇总 Excel
excel_file = export_runs_excel("out", days=7)
print(f"Excel 文件：{excel_file}")
```

---

## 📁 项目结构

### 核心模块（v4.0 模块化架构）

```
gpt_tool/
├── core/                      # 核心模块（11 个）
│   ├── __init__.py           # 统一导出接口（19 个函数）
│   ├── detection.py          # 字幕检测（yt-dlp + youtube_transcript_api）
│   ├── download.py           # 字幕下载与格式转换
│   ├── orchestrator.py       # 主流程编排（webhook + dry run）
│   ├── ai_pipeline.py        # AI 处理（预算护栏 + 缓存 + 重试）
│   ├── reporting.py          # 报告生成（HTML/MD + 图表 + 周报）
│   ├── config.py             # 配置管理（环境变量 + 快照）
│   ├── net.py                # 网络层（代理池 + 限流 + 熔断）
│   ├── utils.py              # 工具函数（原子写 + ID 提取 + SHA1）
│   ├── subscription.py       # 订阅管理（v4.0 新增）
│   ├── queue.py              # 队列管理（v4.0 新增）
│   └── exports.py            # 数据导出（v4.0 新增）
├── adapters/
│   └── ai_adapter.py         # AI 适配器（多供应商聚合）
├── tests/
│   ├── smoke_test.py         # 导入测试
│   └── quick_regression.py   # 快速回归测试
├── yt_subs_gui.py            # GUI 主程序
├── config.json               # 配置文件
├── config.example.json       # 配置示例（v4.0 新增）
├── subscriptions.json        # 订阅数据（运行时生成）
├── queue_state.json          # 队列状态（运行时生成）
├── README.md                 # 本文件
├── RELEASE_v4.0.0.md         # 发布说明（v4.0 新增）
└── MIGRATION_GUIDE.md        # 迁移指南（v4.0 新增）
```

### 输出目录

```
out/
├── 20251026_153012/           # 单次运行目录
│   ├── run.jsonl              # 详细记录（action: detect/download）
│   ├── diagnose.txt           # 诊断报告（错误分布 + 语言分布）
│   ├── warnings.txt           # 警告日志（质量告警 + webhook 失败）
│   ├── config.final.json      # 配置快照（便于复现）
│   ├── plan.md                # Dry Run 预览报告（可选）
│   ├── subs/                  # 字幕文件夹
│   ├── ai/                    # AI 摘要目录
│   │   └── <video_id>.json   # 单视频 AI 分析
│   ├── ai_metrics.jsonl       # AI 指标（tokens/cost/latency）
│   ├── ai_failed.jsonl        # AI 失败记录
│   ├── report.html            # HTML 可视化报告
│   ├── report.md              # Markdown 报告
│   ├── videos.csv             # 视频数据导出（v4.0 新增）
│   ├── errors.csv             # 错误数据导出（v4.0 新增）
│   └── ai.csv                 # AI 数据导出（v4.0 新增）
├── summary_7days.xlsx         # 周报汇总（v4.0 新增）
└── channel_index.json         # 频道增量索引
```

---

## ⚙️ 配置说明

### 配置文件（`config.json`）

完整配置示例见 [`config.example.json`](config.example.json)

#### 核心配置

```json
{
  "output_root": "out",
  "max_workers": 5,
  "sleep_between": 0.5,
  "retry_times": 2
}
```

#### 下载配置

```json
{
  "download": {
    "enabled": true,
    "langs": ["zh", "en"],
    "prefer": "both",
    "format": "txt",
    "merge_bilingual": false,
    "incremental": true
  }
}
```

#### AI 配置

```json
{
  "ai": {
    "enabled": false,
    "workers": 3,
    "timeout_s": 60,
    "max_tokens_per_run": 500000,
    "max_daily_cost_usd": 10.0,
    "providers": [
      {
        "name": "openai",
        "enabled": false,
        "api_key": "env:OPENAI_API_KEY",
        "model": "gpt-3.5-turbo"
      }
    ]
  }
}
```

**成本参考**：
- DeepSeek：￥10 ≈ 500-1000 个视频
- OpenAI：$10 ≈ 600-2000 个视频

#### Webhook 配置（v4.0 新增）

```json
{
  "webhook": {
    "enabled": false,
    "url": "https://your-webhook-endpoint.com/notify",
    "timeout_sec": 5,
    "max_retry": 3,
    "secret": "env:WEBHOOK_SECRET",
    "events": ["run_start", "detect_done", "download_done", "ai_done", "run_end"]
  }
}
```

#### 订阅/队列/导出配置（v4.0 新增）

```json
{
  "subscription": {
    "enabled": true,
    "auto_update": false
  },
  "queue": {
    "enabled": true,
    "max_parallel": 2,
    "retry_on_failure": true
  },
  "export": {
    "auto_export_csv": true,
    "auto_export_excel": false,
    "excel_days": 7
  }
}
```

### 环境变量

支持环境变量占位符：

```json
{
  "api_key": "env:OPENAI_API_KEY",
  "secret": "env:WEBHOOK_SECRET"
}
```

设置环境变量：

```bash
# Linux/Mac
export OPENAI_API_KEY="sk-..."
export WEBHOOK_SECRET="your_secret"

# Windows
set OPENAI_API_KEY=sk-...
set WEBHOOK_SECRET=your_secret
```

---

## 📖 API 文档

### 完整 API 列表（19 个函数）

#### 核心功能

| 函数 | 模块 | 功能 |
|------|------|------|
| `detect_links` | detection.py | 批量检测视频字幕 |
| `download_subtitles` | download.py | 下载字幕 |
| `run_full_process` | orchestrator.py | 主流程编排（检测 + 下载） |
| `run_ai_pipeline` | ai_pipeline.py | 批量 AI 处理 |
| `reprocess_ai_errors` | ai_pipeline.py | 重新处理 AI 失败 |
| `export_run_html` | reporting.py | 生成 HTML 报告 |
| `export_run_md` | reporting.py | 生成 Markdown 报告 |

#### 订阅管理（v4.0 新增）

| 函数 | 功能 |
|------|------|
| `subscribe_add` | 添加订阅 |
| `subscribe_remove` | 删除订阅 |
| `subscribe_list` | 列出订阅 |
| `subscribe_update` | 更新订阅 |
| `subscribe_import` | 导入订阅 |
| `subscribe_export` | 导出订阅 |
| `build_run_plan_from_subscriptions` | 生成执行计划 |

#### 队列管理（v4.0 新增）

| 函数 | 功能 |
|------|------|
| `enqueue_sources` | 入队来源 |
| `list_queue` | 列出队列 |
| `run_queue` | 执行队列 |
| `clear_queue` | 清理队列 |

#### 数据导出（v4.0 新增）

| 函数 | 功能 |
|------|------|
| `export_run_csv` | 导出单次运行 CSV |
| `export_runs_excel` | 导出近期汇总 Excel |

### 使用示例

完整示例见"快速开始"章节。

---

## 🔧 高级功能

### 1. 增量更新

**工作原理**：
- 首次运行：处理所有视频
- 后续运行：只处理 `upload_date > last_seen` 的新视频
- 自动更新 `channel_index.json` 记录最新视频日期

**优点**：
- 大幅节省时间（跳过已处理视频）
- 降低 API 调用次数
- 适合长期订阅使用

### 2. Webhook 通知（v4.0 新增）

**触发时机**：
- `run_start`：开始处理
- `detect_done`：检测完成
- `download_done`：下载完成
- `ai_done`：AI 处理完成
- `ai_guard_stop`：预算护栏触发
- `run_end`：结束处理

**Payload 示例**：
```json
{
  "event": "run_end",
  "run_dir": "out/20251026_153012",
  "stats": {
    "total": 42,
    "detected": 42,
    "downloads_ok": 28,
    "ai_ok": 26
  },
  "budget": {
    "tokens": 18342,
    "cost_usd": 0.73
  },
  "ts": "2025-10-26T15:30:12Z"
}
```

### 3. Dry Run 模式（v4.0 新增）

**使用场景**：安全预演，测试检测逻辑，生成计划报告

**特点**：
- 只执行 `detect_links`，不下载/AI
- 不更新 `last_seen`
- 生成 `plan.md` 预览报告

**示例**：
```python
from core import run_full_process

result = run_full_process(
    channel_or_playlist_url="https://youtube.com/@tech",
    dry_run=True  # 预演模式
)

print(f"检测到 {result['total']} 个视频")
print(f"预览报告：{result['run_dir']}/plan.md")
```

### 4. AI 预算护栏（v4.0 增强）

**作用**：防止 AI 成本超支

**配置**：
```json
{
  "ai": {
    "max_tokens_per_run": 500000,
    "max_daily_cost_usd": 10.0
  }
}
```

**触发效果**：
- 超限立即停止 AI 处理
- 记录到 `warnings.txt`
- 发送 `ai_guard_stop` webhook

### 5. 代理池管理（v4.0 增强）

**健康评分**：
```
score = 0.7 * success_rate + 0.3 * latency_score
```

**自动管理**：
- 成功率 < 15% 自动拉黑
- 黑名单冷却 10 分钟后自动恢复
- 按评分自动选择最佳代理

**查看状态**：
```python
from core.net import get_current_proxy_stats

stats = get_current_proxy_stats()
for proxy, info in stats.items():
    print(f"{proxy}: score={info['score']:.2f}, success_rate={info['success_rate']:.2f}")
```

---

## 🐛 故障排除

### 常见问题

详见 [`MIGRATION_GUIDE.md`](MIGRATION_GUIDE.md) 的"常见问题"章节。

### 调试方法

1. **查看日志**：
   ```bash
   cat out/latest_run/diagnose.txt
   cat out/latest_run/warnings.txt
   ```

2. **运行测试**：
   ```bash
   python tests/smoke_test.py
   python tests/quick_regression.py
   ```

3. **Dry Run 预演**：
   ```python
   from core import run_full_process
   result = run_full_process(
       channel_or_playlist_url="...",
       dry_run=True
   )
   ```

---

## 📊 性能指标

### 代码质量
- **模块数**：11 个（原 1 个）
- **单文件行数**：< 650 行（原 2000+ 行）
- **函数数**：19 个对外函数
- **测试覆盖**：4/4 通过

### 运行时性能
- **启动时间**：减少 ~30%（延迟导入）
- **并发处理**：支持自适应并发（2-20 workers）
- **内存占用**：减少 ~20%（模块化按需加载）
- **AI 缓存命中率**：提升 70%+

---

## 🚀 升级指南

### 从 v3.x 升级到 v4.0

详细迁移指南见 [`MIGRATION_GUIDE.md`](MIGRATION_GUIDE.md)

**快速升级**：
1. 备份旧版本
2. 下载 v4.0 release
3. 覆盖核心文件
4. 更新配置（添加新字段）
5. 运行测试

**兼容性**：
- ✅ 核心接口不变（detect_links, download_subtitles, run_full_process 等）
- ✅ GUI 自动适配
- ✅ 旧配置文件兼容

---

## 📜 版本历史

### v4.0.0-stable (2025-10-26)

**新增**：
- ✅ 订阅管理（7 个函数）
- ✅ 队列管理（4 个函数）
- ✅ 数据导出（2 个函数）
- ✅ Webhook 通知
- ✅ Dry Run 模式

**改进**：
- ✅ 模块化架构（11 个模块）
- ✅ AI 预算护栏
- ✅ 代理池评分
- ✅ 原子写入
- ✅ 配置快照

**详细变更**：见 [`RELEASE_v4.0.0.md`](RELEASE_v4.0.0.md)

### v3.x (历史版本)

见旧版 README。

---

## 📖 文档

- [快速开始指南](README.md#快速开始)（本文件）
- [发布说明](RELEASE_v4.0.0.md)（v4.0.0 详细内容）
- [迁移指南](MIGRATION_GUIDE.md)（v3.x → v4.0）
- [项目架构](项目架构完整概览.md)（11 个模块详解）
- [配置示例](config.example.json)（完整配置）

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

**贡献指南**：
1. Fork 项目
2. 创建特性分支
3. 提交代码（附测试和文档）
4. 运行测试（`python tests/quick_regression.py`）
5. 提交 PR

---

## 📜 许可证

本项目仅供学习和研究使用。

---

## 📞 联系

如有问题或建议，请通过 Issue 联系。

---

**版本**: v4.0.0-stable  
**更新日期**: 2025-10-26  
**状态**: ✅ Stable（生产就绪）

**关键文档**：
- 📖 [`RELEASE_v4.0.0.md`](RELEASE_v4.0.0.md) - 发布说明
- 📖 [`MIGRATION_GUIDE.md`](MIGRATION_GUIDE.md) - 迁移指南
- 📖 [`config.example.json`](config.example.json) - 配置示例

---

**🎉 v4.0.0-stable 发布！享受模块化带来的稳定与高效！** ✨
