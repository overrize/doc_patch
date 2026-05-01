# Repair Manual Scraper

多平台手机维修手册爬虫 — 从 iFixit、Samsung、Apple、Xiaomi 自动爬取维修指南和说明书，按品牌/产品分类存储。

## 前置条件

| 工具 | 版本 | 安装 |
|------|------|------|
| **Git** | 2.x+ | [git-scm.com](https://git-scm.com/download/win) |
| **Python** | 3.9+ | [python.org](https://www.python.org/downloads/) |
| **pip** | 随 Python | 安装时勾选 "Add Python to PATH" |
| **OpenCode** | 1.14+ | `npm install -g opencode-ai` |

## 快速开始

### 1. 克隆 & 安装环境

```powershell
# Windows PowerShell
git clone git@github.com:overrize/doc_patch.git
cd doc_patch

# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# [Windows 重要] 设置 UTF-8 编码，避免中文乱码
set PYTHONIOENCODING=utf-8
# 或永久设置: setx PYTHONIOENCODING utf-8
```

### 2. 在 OpenCode 中使用（推荐）

```bash
# 在项目根目录启动 opencode
opencode

# 输入命令，agent 自动执行爬取
/scrape-manuals apple 200MB
/scrape-manuals samsung,xiaomi 500MB
/scrape-manuals all
```

`/scrape-manuals` 告诉 AI agent 调用 Python 脚本，不需要手动输入交互命令。

### 3. 直接使用 Python（备选）

```bash
# 交互模式
python -m src.main

# 进入后
scraper> start apple 200MB
scraper> status
scraper> stop
scraper> quit
```

## 可用品牌

| 命令参数 | 覆盖产品 |
|----------|----------|
| `apple` | iPhone 12–17, MacBook M3/M4, iPad Pro, Apple Watch |
| `samsung` | Galaxy S22–S25, Z Fold/Flip 4–6, A 系列 |
| `xiaomi` | Xiaomi 12–15, Redmi Note, POCO |
| `all` | 以上全部 |

## 爬取结果

```
manuals/
├── Apple/
│   ├── iPhone_15_Pro/
│   │   ├── guides/      # HTML 维修指南文字
│   │   ├── images/      # 维修步骤图片
│   │   └── manuals/     # PDF 维修手册
│   └── iPhone_14/
│       └── ...
├── Samsung/
│   └── Galaxy_S24_Ultra/
│       └── ...
└── Xiaomi/
    └── Xiaomi_14_Pro/
        └── ...
```

## 配置

### 添加品牌/产品

编辑 `config/products.yaml`：

```yaml
# 添加新品牌只需加一个顶层 key
Huawei:
  - name: "Pura 70 Pro"
    keywords: ["pura 70 pro", "hbp-al00"]
  - name: "Pura 70 Ultra"
    keywords: ["pura 70 ultra", "hbp-al10"]
```

### 修改大小限制

`config/settings.yaml` 第 5 行：

```yaml
total_size_limit: 1073741824  # 1GB = 1073741824 字节
```

也可以在 `start` 命令中覆盖：`start apple 200MB`

### LLM 辅助产品匹配

在 `config/settings.yaml` 中启用，当关键词匹配失败时使用 LLM 识别产品：

```yaml
llm:
  enabled: true
  provider: "deepseek"
  model: "deepseek-chat"
```

## 项目结构

```
doc_patch/
├── .opencode/                # OpenCode 命令定义
│   └── commands/
│       └── scrape-manuals.md # /scrape-manuals 命令
├── src/                      # 爬虫源码
│   ├── main.py               # 入口
│   ├── engine/               # 核心引擎 (队列/去重/限速/会话)
│   ├── platforms/            # 4 个平台适配器
│   ├── storage/              # 文件组织
│   ├── llm/                  # LLM 分类器
│   └── cli/                  # 交互终端
├── config/                   # 配置
│   ├── settings.yaml         # 通用设置 (size, 限速, LLM)
│   ├── products.yaml         # 目标产品列表
│   └── platforms.yaml        # 平台配置
├── manuals/                  # 爬取结果 (gitignore)
├── requirements.txt
└── README.md
```

## 常见问题

**Q: Windows 上中文乱码 / GBK 编码错误？**
```powershell
set PYTHONIOENCODING=utf-8
# 永久: setx PYTHONIOENCODING utf-8
```
重启终端生效。代码已内置 UTF-8 编码处理，确保环境变量即可。

**Q: 爬取中途断了怎么办？**
状态自动保存到 `config/state.json`，重新 `start` 即可续传。

**Q: 为什么有些产品没爬到？**
检查 `config/platforms.yaml` 确认平台已启用。部分平台可能因网络/反爬返回空结果。

**Q: 想加新平台（如华为）？**
1. 在 `config/platforms.yaml` 添加平台配置
2. 在 `src/platforms/` 创建新的 adapter 类
3. 在 `src/engine/scraper.py` 的 `_get_adapter()` 注册
