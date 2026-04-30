# Repair Manual Scraper

多平台手机维修手册爬虫 - 自动从 iFixit、Samsung、Apple、Xiaomi 等平台爬取维修指南和说明书。

## 功能

- **多平台支持**: iFixit API、Samsung Self-Repair、Apple Self Service Repair、Xiaomi Support
- **智能产品匹配**: 关键字匹配 + LLM 辅助分类
- **按产品组织**: `品牌/产品名/guides|images|manuals` 清晰结构
- **1GB 大小限制**: 自动追踪并暂停
- **断点续传**: 中断后可恢复
- **交互式终端**: 实时查看进度、管理任务

## 目录结构

```
doc_patch/
├── src/                    # 爬虫源代码
│   ├── main.py             # 入口
│   ├── engine/             # 核心引擎
│   │   ├── scraper.py      # 主编排器
│   │   ├── queue.py        # URL 队列
│   │   ├── dedup.py        # 去重
│   │   ├── limiter.py      # 限速 + 大小追踪
│   │   └── session.py      # 断点保存
│   ├── platforms/          # 平台适配器
│   │   ├── base.py         # 基类
│   │   ├── ifixit.py       # iFixit
│   │   ├── samsung.py      # Samsung
│   │   ├── apple.py        # Apple
│   │   └── xiaomi.py       # Xiaomi
│   ├── storage/            # 文件存储
│   │   ├── organizer.py    # 按产品组织
│   │   └── filesystem.py   # 文件 I/O
│   ├── llm/                # LLM 辅助
│   │   └── classifier.py   # 产品分类
│   └── cli/                # 终端界面
│       └── interactive.py  # 交互式 CLI
├── config/                 # 配置文件
│   ├── settings.yaml       # 通用设置
│   ├── products.yaml       # 目标产品列表
│   └── platforms.yaml      # 平台配置
├── manuals/                # 爬取结果 (不提交)
│   ├── Apple/
│   │   └── iPhone_15_Pro/
│   │       ├── guides/     # 文字维修指南
│   │       ├── images/     # 维修图片
│   │       └── manuals/    # PDF 手册
│   ├── Samsung/
│   └── Xiaomi/
└── requirements.txt
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 交互式模式
python -m src.main

# 进入后:
scraper> setup      # 初始化
scraper> platforms  # 查看平台
scraper> products   # 查看目标产品
scraper> start      # 开始爬取
scraper> status     # 查看进度
scraper> stop       # 暂停 (保存状态)
scraper> resume     # 继续
scraper> index      # 查看收集的内容
scraper> quit       # 退出
```

## 配置

### 修改目标产品
编辑 `config/products.yaml`，按 Apple/Samsung/Xiaomi 分类添加产品名称和搜索关键词。

### 修改大小限制
`config/settings.yaml` 中的 `total_size_limit` (字节)，默认 1GB。

### LLM 辅助分类
在 `config/settings.yaml` 中启用 `llm.enabled: true`，配置 `llm.provider` 和 `llm.model`。

当前默认使用 DeepSeek API (与 OpenCode 共用配置)。
