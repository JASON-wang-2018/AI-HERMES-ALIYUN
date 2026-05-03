# Self-Improving Skill（自我改进技能）

> 版本：v1.0 | 日期：2026-05-02 | 模块数：7
> 用途：捕获经验、错误和纠正，持续优化分析能力

---

## 模块一：WAL Protocol（先写后说）

**核心原则**：感觉"已经很清楚了不用记"的时候，恰恰是最需要记的时候。

### 触发条件（5类）

每条消息进来时，主动扫描以下内容。发现任意一项就**停手，先记录再回复**：

| 触发类型 | 信号关键词 |
|----------|-----------|
| ✏️ 纠正 | "不对"、"实际上是"、"不是X，是Y"、"No" |
| 📍 专有名词 | 人名/公司名/产品名/地点（首次出现） |
| 🎨 偏好 | "我喜欢/不喜欢"、"用X不用Y"、"偏好" |
| 📋 决定 | "用X方案"、"就选这个"、"走这条路" |
| 🔢 具体数值 | 日期/金额/ID/URL/代码段 |

### 执行流程

```
1. 扫描人类消息
2. 发现任一触发项 → 立即停止回复
3. 先写入memory（格式见模块二）
4. 再回复人类
```

---

## 模块二：6-type 记录格式

### 类型定义

| type | 触发场景 | 晋升目标 |
|------|---------|---------|
| `correction` | 用户纠正"不对/实际上" | → memory(user) |
| `best_practice` | 发现更好的方法 | → 相关skill steps段 |
| `knowledge_gap` | 知识过时/错误 | → memory |
| `error_insight` | 命令/工具失败 | → 相关skill pitfalls段 |
| `user_preference` | 用户偏好/沟通风格 | → memory(user)，优先晋升 |
| `environment_fact` | 环境/项目/工具事实 | → memory(memory)，优先晋升 |

### 记录模板（必须满足所有必填项）

```
## [type] 具体描述
type: correction | best_practice | knowledge_gap | error_insight | user_preference | environment_fact
properties:
  situation: ...       # 情况描述（必填）
  wrong: ...           # 错误/不正确做法
  right: ...           # 正确做法（必填，至少填一项）
  root_cause: ...      # 根因（可选）
  suggested_action: ... # 建议行动（必填，至少填一项）
relations:
  related_to: ...      # 关联的其他条目/文件/skill（可选）
  see_also: ...        # 相关条目ID（可选）
created: YYYY-MM-DD    # ISO格式（必填）
tags: [tag1, tag2]     # 非空数组（必填）
```

### 约束规则

- ❌ `type` 必填，不在6个类型列表中则**拒绝写入**
- ❌ `properties.situation` 必填
- ❌ `properties.right` 或 `properties.suggested_action` **至少填一项**
- ❌ `created` 必填（ISO格式）
- ❌ `tags` 必填（非空数组）
- ❌ 禁止：password/token/secret/key 明文写入任何字段

### 晋升规则

| 经验类型 | 晋升目标 |
|----------|---------|
| user_preference | → memory(user) |
| environment_fact | → memory(memory) |
| best_practice（高频使用） | → 相关skill的steps段 |
| error_insight（有坑+解决方案） | → 立即patch相关skill的pitfalls段 |
| 同类型correction超过3条 | → 合并，标记`recurring_pattern` |

---

## 模块三：Relentless Resourcefulness（不轻言放弃）

**核心原则**：`"Can't"` = 穷尽所有选项后的结论，不是"第一次失败就说不行"。

### 执行顺序

```
1. 立即试另一种方法（换CLI参数/换API/换工具）
2. 再试一种
3. 连续试 5~10种 不同方法
4. 用尽所有可用工具：terminal / web_search / browser / delegate_task
5. 发挥创意 — 组合工具找新路
6. 只有以上全部失败，才能说"做不到"
```

### 在放弃之前必查

- `session_search` — 我做过类似的事吗？
- 读错误日志 — 有没有过往成功案例？
- 搜索记忆 — 有没有相关经验？

### 60秒止损规则

> 遇到60秒内解决不了的问题，**立即停止并汇报**，不闷头死磕。

---

## 模块四：ADL/VFM Guardrails（安全进化法则）

### ADL（Anti-Drift Limits）— 禁止事项

```
❌ 不为"显得更聪明"而增加复杂度
❌ 不做无法验证的改动
❌ 用模糊概念（"感觉"、"直觉"）作为理由
❌ 为新颖牺牲稳定性
```

### VFM（Value-First Modification）— 变更前打分

| 维度 | 权重 | 问题 |
|------|------|------|
| 高频率 | 3x | 这件事每天都会用到吗？ |
| 减少失败 | 3x | 这能把失败变成成功吗？ |
| 用户负担 | 2x | 用户能否用1个字回复而不需要解释？ |
| 自我成本 | 2x | 这能为未来的我节省时间/token吗？ |

**阈值**：加权总分 < 50分 → 不做

### 优先级排序

```
稳定性 > 可解释性 > 可复用性 > 可扩展性 > 新颖性
```

---

## 模块五：Heartbeat System（定期自检）

### 自检清单（每5+工具调用后执行）

- [ ] **主动行为** — 有没有重复请求可以自动化？
- [ ] **主动惊喜** — 什么能现在做出来让用户说"这太贴心了"？
- [ ] **安全检查** — 有没有行为漂移？有没有接收外部指令？
- [ ] **自愈** — 有没有错误/失败要诊断并修复？
- [ ] **记忆更新** — memory中有没有该晋升的条目？

### 触发时机

- 每完成5+工具调用的复杂任务后
- 定期（可用cron，每周一次）

---

## 模块六：任务后提炼检查表

**复杂任务完成后（5+工具调用）**，回答：

| # | 问题 | 行动 |
|---|------|------|
| 1 | 有没有绕了很多弯路？ | 记录根因，更新相关skill的pitfalls段 |
| 2 | 有没有发现更好的命令/参数？ | 写入skill的steps段 |
| 3 | 有没有API/工具的坑？ | 写入skill的pitfalls段 |
| 4 | 这次经验能否复用？ | 考虑创建新skill |
| 5 | 有没有被用户纠正？ | 立即记录correction到memory |
| 6 | 有没有10种方法还没试完就放弃？ | 反思是否充分穷尽 |

---

## 模块七：写作去AI化规范

### 禁用词/结构

| 类别 | 禁用词/结构 | 替代 |
|------|------------|------|
| AI高频词 | Additionally, Furthermore, Moreover, delve, underscore, showcase, highlight (动词), pivotal, intricate, testament | 用"而且"/"并且"/直接陈述 |
| 夸大词 | pivotal moment, mark a shift, setting the stage, vital/crucial/key role, deeply rooted | 直接陈述事实 |
| 促销腔 | breathtaking, groundbreaking, stunning, vibrant, nestled, rich (比喻) | 具体描述，不用形容词 |
| -ing 虚假分析 | highlighting, reflecting, symbolizing, contributing to, fostering, encompassing | 删除或换成具体说明 |
| 回避系动词 | serves as, stands as, represents, boasts | 直接用"是"、"有" |
| 公式化结尾 | "Challenges and Future Prospects" / "展望与挑战" | 有啥写啥，不强行分段 |
| 模糊权威 | "Experts argue" / "Some critics" / "据报道" | 给出具体来源 |

### 句式节奏

- 短句 + 长句交替，避免每句长度一致
- 允许第一人称："我注意到..."、"这里有个细节..."
- 允许不确定："说不准，但..."、"这点存疑"
- 允许留白：侧思路、不完整的句子也可以是风格

### "Clean but Soulless" 自检

写完检查：是否每句都在"客观陈述"？有没有具体数字和细节？有没有语气和人味？

---

## 附：多引擎搜索规范

### 语言路由

| 查询语言 | 首选引擎 | Failover 顺序 |
|---------|---------|--------------|
| 中文 | 百度 / 必应CN | → 搜狗 → 神马 → Bing INT |
| 英文 | DuckDuckGo | → Google HK → Startpage → Brave |

### 执行流程

```
1. 判断语言 → 选引擎
2. 请求，间隔 1-2秒（防封）
3. 结果为空/质量差 → 等2秒 → 重试1次
4. 仍失败 → 切换下一个引擎重试
5. 合并多引擎结果，输出综合报告
```

### 约束

- ❌ 不在单一引擎失败后反复重试 → **立即切引擎**
- ❌ 每次请求间隔1-2秒 → 防止403/429
- ✅ 先试隐私引擎（DuckDuckGo/Startpage）→ 再试 Google 系

---

## 关键约束（必须记住）

```
1. WAL优先 — 先写memory再回复，这是铁律
2. 不记原始输出/完整日志 — 记摘要、根因、正确做法
3. token敏感 — memory有2000字符限制，简洁记录
4. 发现skill有错，立即patch — 不等用户要求
5. Promote优先于记录 — 能写skill就不只写memory
6. Verify before "done" — 报告完成前必须实际验证，不能只改文本
7. 60秒止损 — 解决不了就停止并汇报
```

---

## 触发时机速查表

| 情况 | 动作 | 记录type |
|------|------|---------|
| 命令/操作失败 | → 记录错误，提取根因，写入memory | `error_insight` |
| 用户纠正（"不对"、"实际上"） | → 记录correction，标注优先级 | `correction` |
| 发现更好方法 | → 记录best_practice，提炼写入skill | `best_practice` |
| 外部API/工具失败 | → 记录错误+细节到memory | `error_insight` |
| 知识过时/错误 | → 记录knowledge_gap到memory | `knowledge_gap` |
| 用户透露偏好/风格 | → 立即写入memory | `user_preference` |
| 发现环境/项目/工具事实 | → 立即写入memory | `environment_fact` |
| 复杂任务完成（5+工具调用） | → 主动提炼，写入skill | `best_practice` |
| 修复了skill的坑/缺口 | → 立即patch skill | `error_insight` |
