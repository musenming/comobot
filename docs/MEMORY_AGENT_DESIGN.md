# Comobot Memory & Agent 智能化升级设计方案

## 一、现状分析

### 当前 Memory 系统的问题

1. **搜索能力原始**: 仅靠 `grep` 搜索 HISTORY.md，无语义理解能力
2. **无日志分层**: HISTORY.md 是单一追加文件，无法按日期管理
3. **无向量搜索**: 无 embedding、无语义匹配，"同义词"搜索失效
4. **无主动记忆保存**: 上下文压缩前不会主动保存重要记忆
5. **工具缺失**: Agent 没有专用的 `memory_search` / `memory_get` 工具

### 当前 Agent 系统的问题

1. **上下文构建单一**: 仅加载 MEMORY.md，不加载最近日志
2. **记忆连续性差**: 每次会话无法主动回忆相关上下文
3. **无记忆维护**: 无定期整理、无衰减、无去重

---

## 二、目标架构 (对标 OpenClaw)

```
┌─────────────────────────────────────────┐
│              Agent Loop                  │
│  ┌─────────┐  ┌──────────┐  ┌────────┐ │
│  │ Context  │  │ Memory   │  │ Skills │ │
│  │ Builder  │  │ Store    │  │ Loader │ │
│  └────┬─────┘  └────┬─────┘  └────────┘ │
│       │              │                    │
│  ┌────┴──────────────┴────┐              │
│  │    Memory Search       │              │
│  │  ┌────────┐ ┌────────┐ │              │
│  │  │ Vector │ │  BM25  │ │              │
│  │  │ Index  │ │  FTS5  │ │              │
│  │  └───┬────┘ └───┬────┘ │              │
│  │      └─────┬─────┘      │              │
│  │    Hybrid Merge         │              │
│  │    + Temporal Decay     │              │
│  │    + MMR Re-ranking     │              │
│  └─────────────────────────┘              │
│                                           │
│  ┌─────────────────────────┐              │
│  │  Agent Tools            │              │
│  │  - memory_search        │              │
│  │  - memory_get           │              │
│  │  - (existing tools)     │              │
│  └─────────────────────────┘              │
└───────────────────────────────────────────┘
```

---

## 三、核心改动清单

### 3.1 Daily Log 日志系统

**替换**: `HISTORY.md` → `memory/YYYY-MM-DD.md`

- 每日一个 Markdown 文件，追加写入
- 会话启动时加载今天 + 昨天的日志到上下文
- MEMORY.md 保留为长期记忆（手动/自动维护）
- 合并(consolidation)时写入当天的日志文件而非 HISTORY.md

### 3.2 memory_search 工具

Agent 可调用的语义搜索工具:

```python
memory_search(query: str, max_results: int = 5) -> str
```

- 对 `MEMORY.md` + `memory/*.md` 进行语义搜索
- 返回: snippet 文本、文件路径、行范围、相关度分数
- 支持 Hybrid Search (BM25 + Vector)

### 3.3 memory_get 工具

Agent 可调用的精确读取工具:

```python
memory_get(path: str, start_line: int = 0, num_lines: int = 0) -> str
```

- 读取特定 memory 文件（workspace 相对路径）
- 文件不存在时优雅降级，返回空文本
- 仅允许读取 `MEMORY.md` 和 `memory/` 下的文件

### 3.4 向量索引引擎 (MemorySearchEngine)

**存储**: SQLite + FTS5 + 向量列

```sql
-- chunks 表: 存储文本块
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    content TEXT NOT NULL,
    embedding BLOB,           -- numpy float32 序列化
    updated_at REAL NOT NULL
);

-- FTS5 全文索引
CREATE VIRTUAL TABLE chunks_fts USING fts5(content, content=chunks, content_rowid=id);
```

**Chunking 策略**:
- 目标 ~400 tokens/chunk, 80 tokens overlap
- 按段落/标题分割 Markdown
- 保留文件路径和行号信息

**Embedding 提供者** (按优先级):
1. OpenAI `text-embedding-3-small` (需 API key)
2. 通过 LiteLLM 使用已配置的 provider
3. 可配置自定义 endpoint

### 3.5 Hybrid Search (BM25 + Vector)

```
最终分数 = vectorWeight × vectorScore + textWeight × textScore
textScore = 1 / (1 + max(0, bm25Rank))
```

默认权重: vector 0.7, text 0.3

### 3.6 Temporal Decay (时间衰减)

```
decayedScore = score × e^(-λ × ageInDays)
λ = ln(2) / halfLifeDays
```

- 默认半衰期: 30 天
- 常驻文件(MEMORY.md, 非日期文件)不衰减
- 日期文件从文件名提取日期

### 3.7 MMR Re-ranking (多样性重排)

```
MMR = λ × relevance − (1−λ) × max_similarity_to_selected
```

- 默认 λ=0.7
- 使用 Jaccard 文本相似度
- 消除近重复结果

### 3.8 Pre-compaction Memory Flush

接近 consolidation 阈值时，触发一次静默 agent 调用:
- 提醒 agent 将重要记忆写入日志文件
- 每次 consolidation 周期只触发一次
- 可配置阈值

---

## 四、文件改动清单

### 新建文件

| 文件 | 描述 |
|------|------|
| `comobot/agent/memory_search.py` | 向量搜索引擎 (chunking, embedding, hybrid search, decay, MMR) |
| `comobot/agent/tools/memory_tools.py` | memory_search 和 memory_get 工具 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `comobot/agent/memory.py` | Daily log 替换 HISTORY.md, pre-compaction flush |
| `comobot/agent/context.py` | 加载 daily logs 到上下文, memory_search 自动注入 |
| `comobot/agent/loop.py` | 注册 memory 工具, 触发 memory flush |
| `comobot/config/schema.py` | MemorySearchConfig 配置 |
| `comobot/skills/memory/SKILL.md` | 更新文档 |
| `comobot/templates/AGENTS.md` | daily memory 工作流 |

---

## 五、配置 Schema

```python
class MemorySearchConfig(Base):
    enabled: bool = True
    provider: str = "auto"           # auto, openai, local
    model: str = "text-embedding-3-small"

    class HybridConfig(Base):
        enabled: bool = True
        vector_weight: float = 0.7
        text_weight: float = 0.3
        candidate_multiplier: int = 4

    class TemporalDecayConfig(Base):
        enabled: bool = True
        half_life_days: int = 30

    class MMRConfig(Base):
        enabled: bool = False
        lambda_: float = 0.7

    hybrid: HybridConfig
    temporal_decay: TemporalDecayConfig
    mmr: MMRConfig
    max_results: int = 5
    chunk_target_tokens: int = 400
    chunk_overlap_tokens: int = 80

class MemoryFlushConfig(Base):
    enabled: bool = True
    soft_threshold_ratio: float = 0.8  # 触发时机 = memory_window × ratio
```

---

## 六、实现优先级

### P0 — 基础能力 (本次实现)
1. Daily log 日志系统
2. memory_search 工具 (BM25 全文搜索)
3. memory_get 工具
4. 上下文加载 daily logs
5. 更新 consolidation 流程
6. 更新 templates 和 SKILL.md

### P1 — 向量搜索 (本次实现)
1. Embedding provider 抽象
2. Chunk 索引和向量存储
3. Hybrid search (BM25 + Vector)
4. Temporal decay
5. 配置 schema

### P2 — 高级特性 (可选)
1. MMR re-ranking
2. Pre-compaction memory flush
3. Session transcript 索引
4. Embedding cache
5. 文件变更 watcher

---

## 七、与 OpenClaw 对比

| 能力 | OpenClaw | Comobot (当前) | Comobot (升级后) |
|------|----------|---------------|-----------------|
| 日志分层 | YYYY-MM-DD.md | HISTORY.md 单文件 | ✅ YYYY-MM-DD.md |
| 长期记忆 | MEMORY.md | MEMORY.md | ✅ MEMORY.md |
| 语义搜索 | Vector + BM25 | grep | ✅ Hybrid Search |
| 时间衰减 | ✅ | ❌ | ✅ |
| MMR 去重 | ✅ | ❌ | ✅ |
| 记忆工具 | memory_search/get | grep via exec | ✅ memory_search/get |
| 预压缩保存 | ✅ | ❌ | ✅ |
| 日志上下文 | today+yesterday | 无 | ✅ today+yesterday |
| Session 索引 | ✅ (experimental) | ❌ | P2 |
| QMD sidecar | ✅ (experimental) | ❌ | 不实现 (过于复杂) |
