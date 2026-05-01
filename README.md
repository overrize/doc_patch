# Repair Manual Scraper

多平台手机维修手册爬虫 — 从 iFixit / Samsung / Apple / Xiaomi 自动拉取维修指南，按品牌/产品分类存储。

## 安装

```powershell
# 1. 克隆
git clone git@github.com:overrize/doc_patch.git
cd doc_patch

# 2. Python 虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 3. 依赖（requests + pyyaml + playwright）
pip install -r requirements.txt

# 4. [Windows 必须] 设置 UTF-8 编码
set PYTHONIOENCODING=utf-8
# 永久生效: setx PYTHONIOENCODING utf-8
```

`playwright install chromium` **不需要** — 会自动用系统 Edge。

## 使用

### 命令行（直接跑）

```bash
python -m src.main start              # 全部品牌，默认 1GB
python -m src.main start apple 200MB  # 只爬 Apple，200MB
python -m src.main start samsung,xiaomi 500MB
python -m src.main start 500MB        # 全部品牌，500MB
```

### OpenCode 里用

```bash
opencode
/scrape-manuals apple 200MB
```

### 交互模式

```bash
python -m src.main
scraper> start apple 200MB    # 一步启动
scraper> status               # 进度 + 已完成产品 + size 告警
scraper> brands               # 可用品牌
scraper> stop / resume        # 暂停 / 续传
```

## 爬取结果

```
manuals/
├── Apple/
│   ├── iPhone_15_Pro/
│   │   ├── guides/           HTML 维修指南
│   │   ├── images/           步骤图片
│   │   └── manuals/          PDF 维修手册
│   └── iPhone_14/
├── Samsung/
│   └── Galaxy_S24/
└── Xiaomi/
    └── Xiaomi_14_Pro/
```

**已下载过的产品会自动跳过**，再跑 `start` 不会重复拉。

## 可用品牌

| 参数 | 产品 |
|------|------|
| `apple` | iPhone 12–17, MacBook M3/M4, iPad Pro, Apple Watch |
| `samsung` | Galaxy S22–S25, Z Fold/Flip 4–6, A 系列 |
| `xiaomi` | Xiaomi 12–15, Redmi Note, POCO |
| `all` / 不填 | 以上全部 |

## 配置

### 加品牌/产品

编辑 `config/products.yaml`：

```yaml
Huawei:
  - name: "Pura 70 Pro"
    keywords: ["pura 70 pro", "hbp-al00"]
```

然后 `start huawei` 即可。

### 改默认 size

`config/settings.yaml`：

```yaml
total_size_limit: 1073741824  # 字节
```

也可以在命令里随时覆盖：`start apple 200MB`。

### 启用 LLM 辅助匹配

`config/settings.yaml`：

```yaml
llm:
  enabled: true
  provider: "deepseek"
  model: "deepseek-chat"
```

关键字匹配失败时用 LLM 识别产品名称。

## 日志

| 文件 | 内容 |
|------|------|
| `manuals/scraper.log` | 全部日志（文件名:行号） |
| `manuals/errors.log` | 仅 WARNING+ |

## 项目结构

```
src/
├── main.py             入口
├── engine/             核心引擎（队列/去重/限速/会话/size追踪）
├── platforms/          平台适配器
│   ├── ifixit.py       iFixit API（主数据源）
│   ├── samsung.py      Samsung（iFixit 为搜索源）
│   ├── apple.py        Apple（已知 Manual ID + 搜索）
│   ├── xiaomi.py       Xiaomi（支持文章 + diygeardo）
│   └── headless.py     Playwright 封装（自动用系统 Edge）
├── storage/           文件组织
├── llm/               LLM 分类器
└── cli/              交互终端
config/
├── settings.yaml      通用设置
├── products.yaml      目标产品
└── platforms.yaml     平台开关
```

## 常见问题

**Windows 中文乱码？**
```powershell
set PYTHONIOENCODING=utf-8
```

**爬取中断了？**
状态保存到 `config/state.json`，直接重新 `start` 续传。

**Samsung 爬不到？**
Samsung 站点是 JS 渲染，自动用 iFixit 搜索替代。无需额外配置。

**加新平台？**
1. `config/platforms.yaml` 加配置
2. `src/platforms/` 创建新 adapter
3. `src/engine/scraper.py` 的 `_get_adapter()` 注册
