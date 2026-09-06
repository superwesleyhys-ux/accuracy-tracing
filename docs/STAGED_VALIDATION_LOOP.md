# PR #1：分阶段提示词与验证回环

PR #1 保留 `Decomposer`、`Verifier` 和 `run_provenance` 公共接口，但把原先集中的语义工作拆成七个单一职责模型阶段，并在模型阶段前后加入确定性 Python 校验。这里保证的是可审计的结构约束和失败关闭，不保证新闻真实性、目标分解的语义完备性或准确率必然提高。

## 实际拓扑

```text
冻结 Target
  → Python TargetPlan（最多 8 个 probe，operator=all，带 plan SHA）

每个 eligible 材料返回
  → 保存快照与时间资格检查
  → atoms → lineage → decomposition_critic
                         ↳ 整个分解事务共享最多 1 次定向重做
  → Python decomposition_assembly 原子提交

每个新的 canonical verifier input
  → evidence → evidence_critic
                 ↳ 该 evidence 事务共享最多 1 次重做
  → world → world_critic
              ↳ 该 world 事务共享最多 1 次重做
  → Python judgement_assembly
  → 未决项生成精确 fetch / reanalyse / search
  → 新返回重新进入同一有界流程
```

七个模型阶段分别是：

1. `atoms`：只提取当前材料中与目标相关的原子陈述及其原文限定词。
2. `lineage`：只提取显式引用、传播方向、原始材料角色与需要重开的旧版本。
3. `decomposition_critic`：同时复核 atoms 和 lineage 的完整草稿，并只点名一个阶段修正。
4. `evidence`：只判断冻结 `evidence_scope` 中的材料怎样支持或反驳目标。
5. `evidence_critic`：只复核 evidence 层，不读取 world-only 材料。
6. `world`：独立判断现实事件是否由可见材料与来源链充分建立。
7. `world_critic`：只复核 world 层。

`decomposition_assembly` 和 `judgement_assembly` 是程序步骤，不是额外模型提示词。任何 schema、原文、范围、任务回执或确定性装配校验失败，当前事务都不会部分提交。

## 固定目标计划与逐维账本

`TargetPlan` 只由冻结目标生成，不读取材料、模型输出或 gold。它记录版本、目标文本 SHA、计划 SHA、最多 8 个稳定 probe，以及每个 probe 必查的维度。三个基础维度始终存在：主体、谓词/对象、范围/地点；数量、时间、否定、条件、语气、比较基线、归因/因果等维度在目标出现对应信号时加入。只拆分能够保留独立主语/谓词的并列项；共享时间、否定、语气或 `alleged that A and B` 这类归因范围保持为同一 probe，无法安全识别的复合目标失败关闭。

evidence 和 world 输出都必须做到：每个 probe 恰好一项、每个 required dimension 恰好一项。每个确定性结论必须引用该 probe 的唯一原文 basis，并通过逐 span 的保守词面落地检查。对 supported 的基础维度还要求英文关键 token 和中文字符按目标顺序落地，阻止 `Alice defeated Bob` 被反向证据 `Bob defeated Alice` 误收。Python 按 `dimension → probe → layer` 聚合；在 `operator=all` 下，明确反驳优先于冲突，冲突优先于未决，只有全部支持才是支持。

这个计划是有界启发式防线，不是自然语言语义证明。常见英文并列和中英文限定词有回归测试，但任意复杂嵌套、指代或歧义仍需要独立人工 gold 与真实数据验证。逐维原始模型 JSON 保存在 `*-calls.json`，计划和阶段审计保存在 `*-semantic-stages.json`；公共 `VerificationResult` 仍返回聚合后的 evidence/world 结果。

## 检索回执与缺口生命周期

任务感知 provider 应实现 `search_hits` 并返回 `RetrievalHit(material, task_ids)`。每个 task ID 必须来自当前轮冻结的 issued tasks，且不可重复。staged 模式从第 2 轮起要求每个外部返回有精确任务归因；首轮 seed 和引擎内部 revisit 例外。旧 `search`/裸 `MaterialVersion` 与调用前冻结的 sidecar 仍保留兼容，但不能满足严格 staged 后续轮的归因要求。

provider 对当前轮每个 issued task 都要返回一条六字段反馈：`gap_id`、`action`、`locator`、`status`、`reason`、`version_ids`。`status` 是 `returned`、`unavailable` 或 `budget_exhausted`。`returned` 的版本集合必须与实际归因完全相等；非 returned 状态不得掩盖已返回版本。回执经 `current_return` 进入分解器，经 `current_round_returns` 进入 verifier，并与规范化反馈一起进入审计。

resolution 只能引用历史注册过的 gap。staged verifier 还要求本轮有该 gap 的精确任务回执，并且 resolution basis 使用该回执实际返回的版本。每个 staged 验证 gap 持久保存所属 `probe_id`；一个 probe 的 unavailable 回执不能授权另一个 probe 停止或关闭任务。gap 的 action/locator/维度/目标/probe 身份不可原地改变；同一 ID 的 blocking 严重度在整个注册生命周期内单调不降，关闭后若是不同或更弱的新任务必须换新 ID。跨材料 open/close 事件按已提交 revision 排序，最新事件胜出；程序拥有的 missing-scope task 使用 canonical ID，不能被模型同 locator 的任务替代，并在精确版本返回准入后自动关闭。含 gap/resolution 的 layer 不进入结果缓存，避免旧任务被重放复活。

## 回环、终止与预算

验证缺口的新材料必须先保存、通过资格检查、完成分解并原子更新图，然后才可进入下一次判断。未来版本或无法证明在 `as_of` 可用的版本只走隔离的 `ConservativeDecomposer` 归档路径，不进入 stateful 模型、当前图或 verifier。

只有完整 canonical verifier input 完全相同时才跳过外层验证。指纹包括冻结目标、材料版本指纹、verifier 可见 analyses 与完整 fragments/relations/origins（含正文、限定词、rationale）、active gaps、当前精确回执，以及 staged verifier 使用的规范化 retrieval feedback。结构进展指纹仍排除纯措辞变化，避免因此无限续轮。evidence/world 另有独立、只缓存无生命周期事件的 layer cache，所以 world-only 输入变化不会迫使 evidence 重采样。

未决 probe 不能静默结束：必须生成可执行任务，或明确给出 `scope_unavailable` / `no_source_lead`。前者只适用于缺少冻结 scope；后者通常需要已验证的 `unavailable` 反馈，`budget_exhausted` 不等于材料不存在。验证器在空结果轮生成的新任务会进入下一轮；provider 本轮预算挤掉的 active task 也会在外层预算允许时重试。终止判断比较完整可执行任务签名；当 locator 为空时，question 就是实际 query，同一 gap ID 的 query 更新必须先真正发出，旧 query 的 unavailable 回执不能提前终止它。

引擎有 round/document/decomposition 三个硬上限。模型 transport 另有每 arm 的 call、总输出 token、单调用输出 token 和 wall-time 上限；staged 事务在开始前按最坏修复路径预检额度。模型 input token 只计量、不按 token 截断，但单阶段序列化输入另有 250,000 字符上限。错误、预算耗尽、空结果、已证实 unavailable、无进展、完成都会留下不同停止或审计记录。

## 运行与审计

```bash
python experiments/loop_compare.py run \
  --inputs experiments/inputs-v03.json \
  --output reports/my-staged-run \
  --model MODEL_NAME \
  --semantic-mode staged \
  --max-repairs 1 \
  --max-rounds 5
```

每个 stage 记录 prompt/payload/schema/output SHA、事务 ID、修复指向以及可用时的 API response ID、模型与实际 usage；程序装配步骤也记录覆盖全部真实依赖的输入/输出 SHA。缓存只可重放同 case/variant 下完全相同的 model、reasoning、prompt、payload、schema、response mode 与 output cap，且会在入库和重放前复核请求/输出哈希，每条历史响应最多消费一次。

兼容或消融运行可显式选择 `--semantic-mode monolithic --max-repairs 0`。staged 与 monolithic 的预算不同，因此当前对照不能单独归因“拆提示词提高了准确率”。准确率结论仍需预登记等总预算、冻结输入、独立人工 gold、事件/时间隔离数据和失败样本全量保留。
