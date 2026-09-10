# GPT-5.6 Luna host-envelope test — 2026-09-10

本轮采用新的 `host-envelope-single-pass-v1` 策略：模型只生成已验证的基础 verdict，主机端补齐审计字段；每个样本一次证据账本判断，保留历史截止日期约束，并停止救援式重试。

## 状态

测试的 16 个 direct/double-loop 臂均已完成，模型调用均返回成功，使用 GPT-5.6 Luna、low reasoning、local Codex-login 路由。独立汇总在审计阶段拒绝了结果：double-loop 的 `result.json` 记录了 1 个模型调用，但缺少与该调用对应的 harness response audit 条目（`report_io` 数量为 0）。

因此本轮结果**无效，不计入准确率比较**，也不能据此声称 harness 超过 Luna。这个问题是结果审计/封装层的结构不一致，不是模型判断分数；按规则不重复运行同一策略。

下一步应先修复 host-envelope 的 response-audit 写入，使每个调用都有一条可验证的审计记录，再设计新的策略并重新预注册测试。
