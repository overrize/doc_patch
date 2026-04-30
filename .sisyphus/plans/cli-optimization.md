# CLI 优化方案

## 当前问题

| 痛点 | 现状 |
|------|------|
| 两步启动 | `setup` → `start`，反直觉 |
| 产品配置重 | 42 个产品手工 YAML + model number keywords |
| 无法按品牌筛选 | `start` 无参数，全量跑 |
| size 无反馈 | 1GB 写死，不够时静默停 |
| 扩展不明确 | 加新品牌不知道改哪个文件 |

## 方案 A：一命令流

### 新 CLI

```bash
# 一行启动
python -m src.main start apple 200MB

# 多品牌逗号分隔
python -m src.main start samsung,xiaomi 500MB

# 全部品牌
python -m src.main start all

# 交互模式
scraper> start apple 100MB
scraper> start samsung
scraper> status
scraper> stop
```

### 命令简化为 6 个

| 命令 | 说明 |
|------|------|
| `start apple 200MB` | 自动 setup + 爬取，指定品牌和 size |
| `status` | 进度 + size 使用 + size 不足告警 |
| `stop` | 暂停保存 |
| `resume` | 续传上次 |
| `brands` | 列出可用品牌 |
| `quit` | 退出 |

移除：`setup`（合并进 start）、`platforms`、`products`、`limit`（合并进 start 参数）、`index`（合并进 status）

## 方案 B：品牌即产品（自动联想）

### brands.yaml（新文件）

```yaml
brands:
  apple:
    aliases: [iphone, ipad, mac]
    families:
      - prefix: iPhone
        generations: [12, 13, 14, 15, 16, 17]
        variants: ["", Pro, "Pro Max", Plus, mini]
    platforms: [ifixit, apple_self_repair]

  samsung:
    aliases: [galaxy, samsung galaxy]
    families:
      - prefix: Galaxy S
        generations: [22, 23, 24, 25]
        variants: ["", +, Ultra, FE]
    platforms: [ifixit, samsung_parts]

  xiaomi:
    aliases: [mi, redmi, poco]
    families:
      - prefix: Xiaomi
        generations: [12, 13, 14, 15]
        variants: ["", Pro, Ultra, T]
    platforms: [ifixit, xiaomi_service]
```

**加新品牌只需加一个 block**，系统自动生成产品 × 变体列表 + 搜索关键词。

### 产品自动生成逻辑

```
iPhone 15 Pro → keywords: ["iphone 15 pro", "a2848", "a3101"]
iPhone 15 → keywords: ["iphone 15", "a2846", "a3089"]
...
```

Model numbers 由内置数据库提供，用户不用管。

## 方案 C：per-session size + 不足告警

### start 第二个参数覆盖默认 size

```bash
start apple 200MB    # 本次 200MB
start samsung         # 用 settings.yaml 默认值
```

### size 不足检测

引擎在 `SizeTracker` 中记录被跳过的文件：

```python
class SizeTracker:
    skipped_files: list[str]       # 因限额不够跳过的文件名
    skipped_total_bytes: int       # 跳过的总量
```

### status 输出增强

```
=== Scraper Status ===
Brand:      apple
Downloaded: 156 MB / 200 MB (78%)
Skipped:    3 files (need ~45 MB more)
  - iPhone_15_Pro_battery_replacement.html (12 MB)
  - samsung_galaxy_s24_screen.pdf (28 MB)
  - ...
Queue:      12 URLs pending
Elapsed:    320 seconds

[WARN] Size limit too small. 5 items skipped.
       Try: start apple 500MB
```

## 改动范围

| 文件 | 改动 |
|------|------|
| `src/main.py` | 重构参数流：`start <brand> [size]` |
| `src/cli/interactive.py` | `start` 接受品牌参数，移除 `setup`/`products`/`limit` |
| `src/engine/scraper.py` | `run(brands, size_override)` 支持筛选 + per-session |
| `src/engine/limiter.py` | `SizeTracker` 增加 skipped 记录 |
| `src/config.py` | 新增 `load_brands()` |
| `src/types.py` | 新增 `Brand` / `ProductFamily` 类 |
| `config/brands.yaml` | 新建 |
| `config/settings.yaml` | `total_size_limit` → `default_size_limit` |

## 不变文件

- 4 个平台适配器 — 无变更
- 存储模块 — 无变更
- LLM 分类器 — 无变更
- `queue.py` / `dedup.py` / `session.py` — 无变更

## 实施顺序

**Round 1**（高优先级）: CLI 简化 + per-session size
- `main.py` + `interactive.py` + `scraper.py` + `limiter.py`

**Round 2**（可独立）: 品牌自动联想
- 新增 `brands.yaml` + `config.py` 改动
