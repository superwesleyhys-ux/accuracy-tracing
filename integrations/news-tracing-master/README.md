# News Tracing Agent

基于 LLM 的新闻溯源 Agent，输入一条新闻或话题，**直接回答**用户关心的问题，并附带透明的多维度可信度指标。同时生成事件时间线、因果分析、多源事实核查等详情供展开查阅。

## 架构

```
Phase 1: 解构 + 搜索规划
    ↓
Phase 2: 双轨并行
    Track A: 多角度信源采集 → 合并去重 → 交叉验证
    Track B: 递归因果挖掘（最多 3 层）
    ↓
Phase 3: 时间线构建 + 综合研判
    锚定验证 → 事件时间线 → 多方视角 → 可信度指标 → 直答生成 → 详细研判
```

## 快速开始

```bash
cd news
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入你的 API Key
```

`.env` 配置项：

```
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5.4-mini
OPENAI_SEARCH_MODEL=gpt-4o-search-preview
```

支持任何兼容 OpenAI API 的代理服务，修改 `OPENAI_BASE_URL` 即可。`OPENAI_SEARCH_MODEL` 用于带联网搜索的调用。

## 使用

```bash
# 直接传入话题
python main.py "美伊冲突"

# 指定因果挖掘深度
python main.py "美伊冲突" --depth 2

# 交互模式（不传参数）
python main.py
```

## 报告输出

报告按以下顺序输出：

| 模块 | 说明 |
|------|------|
| **直答** | 一段话回答用户问题：核查输入声明、纠偏、事件真相、因果主线、争议标注、可信度锚点 |
| 可信度指标 | 透明原始数据：N 个信源 / N 类媒体 / 一致数 / 争议数 / 因果锚定率 |
| 事件时间线 | 按时间排序的关键事件，标注显著性和多方视角 |
| 因果事件树 | 递归挖掘的因果链，每个节点标注 [有据] 或 [推测] |
| 事实核查 | 多源一致的事实 vs 存在分歧的事实 |
| 信源一览 | 所有采集到的信源及其类型 |
| 关键发现 / 信息缺口 / 立场标注 | 综合研判结果 |

## 项目结构

```
news/
├── main.py                 # CLI 入口 + 报告渲染
├── agent/
│   ├── core.py             # 双轨并行编排 + 时间线构建
│   ├── llm_client.py       # OpenAI API 封装（支持搜索模型）
│   ├── models.py           # 数据模型（CredibilityBreakdown, TimelineEvent, ...）
│   └── prompts.py          # 各阶段 prompt 模板
├── requirements.txt
├── .env.example
└── .gitignore
```
