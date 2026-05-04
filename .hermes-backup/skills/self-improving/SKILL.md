---
name: self-improving
description: "自我改进技能。捕获经验、错误和纠正，持续优化分析能力。每次被纠正、犯错、或发现更好的方法后，主动记录并提炼为持久化知识。"
---

# Self-Improving Skill

## 核心理念

每次交互都是改进机会。知识要流动到该去的地方，不是在记忆里吃灰。

---

## 1. 触发式记录

事件发生时**当场记录**，不靠事后回忆（过了 context 细节全丢）。

| 情况 | 记录到 | type |
|---|---|---|
| 被纠正（"不对"/"实际上是"） | memory | `correction` |
| 发现更好方法 | 相关 skill 或 memory | `best_practice` |
| 命令/工具失败 | memory | `error_insight` |
| 踩坑+解决方案 | **立即 patch 相关 skill** | `error_insight` |
| 用户偏好/风格 | memory(user) | `user_preference` |
| 环境/项目事实 | memory(memory) | `environment_fact` |

---

## 2. 知识晋升规则

信息要流到**该去的地方**：

| 经验类型 | 晋升目标 |
|---|---|
| 用户偏好/沟通风格 | memory(user) |
| 环境/项目事实 | memory(memory) |
| 工具/脚本改进 | 更新对应 skill |
| 踩坑+解决方案 | **立即 patch** 相关 skill 的 pitfalls 段 |
| 高频 best_practice | 写入相关 skill 的 steps 段 |

---

## 3. 任务后自检（复杂任务必做）

每个复杂任务（5+ 工具调用）完成后自问：

1. 有没有绕弯路？→ 记录根因，更新相关 skill pitfalls
2. 有没有发现更好方法？→ 写入 skill steps
3. 有没有 API/工具的坑？→ 写入 skill pitfalls
4. 有没有被用户纠正？→ 立即记录 correction 到 memory
5. 有没有试尽所有方法才放弃？→ 反思是否穷尽了选项

---

## Relentless Resourcefulness（补充）

遇到困难时，连续试 **5～10 种方法**再放弃，不在第 1～2 次失败后就说不行。

「Can't」= 穷尽所有选项后的结论，不是快速放弃的借口。

---

## 变更评估（VFM）

改动前自问：

- 这件事高频吗？（每天用 → 高权重）
- 这能减少失败吗？
- 用户能否用 1 个字回复而不需要解释？
- 这能为未来的我节省时间/token吗？

权重总和低的不做。稳定性 > 可扩展性 > 新颖性。
