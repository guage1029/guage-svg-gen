# Agent Skills 协议核心参考手册

> 来源：https://agentskills.io — 整理日期：2026-06-09
> 用途：迭代本地 skill 时的标准对照文档

---

## 一、协议设计理念

**核心定义**：Agent Skills 是一种轻量级、开放格式，用于向 AI Agent 扩展专业知识和工作流程能力。本质上是一个包含 `SKILL.md` 文件的文件夹。

**三阶段渐进式披露（Progressive Disclosure）**：

| 阶段 | 内容 | 时机 |
|------|------|------|
| Discovery（发现） | 仅加载 name + description (~100 tokens) | Agent 启动时对所有 skill 执行 |
| Activation（激活） | 加载完整 SKILL.md 正文 | 任务匹配 skill 描述时 |
| Execution（执行） | 按需加载 scripts/、references/、assets/ | 实际执行需要时 |

**重要含义**：description 字段承担触发的全部责任。description 决定了 skill 是否被激活，不能写得太窄（遗漏）或太宽（误触）。

---

## 二、标准目录结构

```
skill-name/
├── SKILL.md          # 必需：元数据 + 指令
├── scripts/          # 可选：可执行代码
├── references/       # 可选：详细文档、参考资料
├── assets/           # 可选：模板、静态资源
└── ...               # 其他任意文件
```

---

## 三、SKILL.md 规格

### 3.1 Frontmatter 字段

| 字段 | 必需 | 约束 |
|------|------|------|
| `name` | **是** | 1-64字符，小写字母/数字/连字符，不能以连字符开头/结尾，不能有连续连字符，**必须与父目录名一致** |
| `description` | **是** | 1-1024字符，非空，描述 skill 做什么 + **何时使用** |
| `license` | 否 | 许可证名称或文件引用 |
| `compatibility` | 否 | 1-500字符，环境要求（产品、系统包、网络等），大多数 skill 不需要 |
| `metadata` | 否 | 任意 key-value 映射（author、version 等） |
| `allowed-tools` | 否 | 空格分隔的预批准工具列表（实验性） |

### 3.2 最小示例

```yaml
---
name: skill-name
description: A description of what this skill does and when to use it.
---
```

### 3.3 完整示例

```yaml
---
name: pdf-processing
description: Extract PDF text, fill forms, merge files. Use when handling PDFs.
license: Apache-2.0
metadata:
  author: example-org
  version: "1.0"
---
```

### 3.4 Body 正文

- **无格式限制**，写任何有助于 Agent 完成任务的内容
- **推荐包含**：分步骤指令、输入/输出示例、常见边缘情况
- **体积限制**：建议 < 500 行 / < 5000 tokens；超过时移入 `references/`

---

## 四、description 字段优化策略

### 4.1 好的 description 写法原则

1. **祈使语气**："Use this skill when…" 而非 "This skill does…"
2. **关注用户意图**，而非内部实现细节
3. **主动列出适用场景**，包括用户不会直接提到领域名词的情况
4. **适中长度**：几句话到一短段，不超过 1024 字符

**好的例子：**
```yaml
description: >
  Analyze CSV and tabular data files — compute summary statistics,
  add derived columns, generate charts, and clean messy data. Use this
  skill when the user has a CSV, TSV, or Excel file and wants to
  explore, transform, or visualize the data, even if they don't
  explicitly mention "CSV" or "analysis."
```

**差的例子：**
```yaml
description: Helps with PDFs.   # 太模糊
description: Process CSV files. # 没有说明何时触发
```

### 4.2 触发测试方法

- 准备约 20 条 eval queries（8-10 条应触发，8-10 条不应触发）
- 每条查询运行 3 次，计算触发率（>0.5 为触发）
- 按 60/40 分 train/validation set，避免过拟合
- 迭代优化循环：评估 → 找失败 → 修改 → 重评估，通常 5 轮足够

**应触发查询的设计维度**：
- 措辞多样（正式/口语/有拼写错误）
- 直接/间接提及领域名词
- 单步/多步复杂任务混合

**不应触发查询**：优先选近似查询（有关键词重叠但任务不同），而非毫无关联的查询。

---

## 五、Skill 创作最佳实践

### 5.1 从真实专业知识出发

- **反模式**：让 LLM 空白生成，产生"适当处理错误"这类模糊泛泛的内容
- **正模式**：喂入真实的内部文档、runbook、API 规格、代码审查记录、历史修复 patch

### 5.2 正文内容原则

**只写 Agent 不知道的**：
- 项目特定约定、领域专用流程、非显而易见的边缘情况
- 不需要解释"什么是 PDF"、"HTTP 怎么工作"

**合理范围（Coherent Units）**：
- 太窄：多个 skill 才能完成一个任务，产生开销和冲突
- 太宽：难以精准触发
- 类比函数设计：单一职责，组合良好

**适度细节**：
- 过于全面的 skill 反而有害：Agent 难以提取相关内容，可能走错路
- 简洁的分步骤指引 + 示例，通常优于面面俱到的文档

### 5.3 校准控制粒度

| 情形 | 推荐方式 |
|------|----------|
| 多种方法都可行，允许变化 | 给 Agent 自由，解释**为什么**，不要死规定步骤 |
| 操作脆弱，顺序必须严格 | 明确规定，列出精确命令，注明"不得修改参数" |

**提供默认值而非菜单**：
```markdown
# 差：太多选项
You can use pypdf, pdfplumber, PyMuPDF, or pdf2image...

# 好：给默认 + 逃生口
Use pdfplumber for text extraction:
```python
import pdfplumber
```
For scanned PDFs requiring OCR, use pdf2image with pytesseract instead.
```

**偏向流程描述，而非声明答案**：教 Agent 如何处理一类问题，而非给出特定实例的答案。

### 5.4 高价值写作模式

**Gotchas 部分（最高价值）**：记录环境特有的反直觉事实：
```markdown
## Gotchas
- `users` 表使用软删除，查询必须包含 `WHERE deleted_at IS NULL`
- 用户 ID 在数据库中是 `user_id`，在认证服务中是 `uid`，在计费 API 中是 `accountId`
```

**输出格式模板**：提供具体模板比描述格式更可靠（Agent 对具体结构的模式匹配能力更强）。

**多步骤工作流 Checklist**：
```markdown
Progress:
- [ ] Step 1: Analyze the form (run `scripts/analyze_form.py`)
- [ ] Step 2: Create field mapping (edit `fields.json`)
- [ ] Step 3: Validate mapping (run `scripts/validate_fields.py`)
```

**验证循环（Validation Loop）**：做 → 验证 → 修复 → 重复，直到通过。

**计划-验证-执行（Plan-Validate-Execute）**：批量或不可逆操作先生成计划，验证后再执行。

### 5.5 渐进披露结构

当 SKILL.md 需要超过 500 行时：
- 核心指令保留在 SKILL.md
- 详细参考资料移入 `references/`
- **关键**：在 SKILL.md 中明确告知 Agent 何时加载每个文件

```markdown
# 好：条件式引用
Read `references/api-errors.md` if the API returns a non-200 status code.

# 差：模糊引用
See references/ for details.
```

---

## 六、与 Claude Code Skill 的关系

Claude Code 中调用 skill 的方式（通过 `Skill` 工具）与标准 Agent Skills 协议一致：
- skill 列在系统提示的 available-skills 部分
- description 决定是否通过 `Skill` 工具激活
- SKILL.md 正文在激活时加载到上下文

---

## 七、目录结构补充说明

官网协议明确：skill 根目录下可以包含**任意额外文件和目录**，`scripts/`、`references/`、`assets/` 是约定惯例而非强制。实践中可根据需要添加：

```
skill-name/
├── SKILL.md
├── scripts/
├── references/
├── assets/
└── evals/          ← 允许，用于存放触发/输出质量评估用例
```

**文件引用规则**：SKILL.md 中引用其他文件时，使用相对于 skill 根目录的路径，避免深层链式引用（A 引 B 再引 C）。

---

## 八、scripts/ 最佳实践

官网对脚本的具体建议（适用于所有放在 scripts/ 下的可执行文件）：

| 实践 | 说明 |
|------|------|
| 无交互式输入 | 脚本不得等待 stdin，所有参数通过 CLI flags 传入 |
| `--help` 清晰 | 每个脚本都应有 `argparse` 描述，方便 Agent 和人工查阅 |
| stdout 输出结构化数据 | 用 `--json` flag 切换机器可读输出，Agent 解析结果用 |
| stderr 放诊断信息 | 进度、警告、调试信息写 stderr，不污染 stdout 的结构化输出 |
| 依赖自包含或显式声明 | 在 `requirements.txt` 中列明所有依赖，可选依赖注明用途 |
| 明确退出码 | 0=成功，非0=失败，不同失败类型用不同退出码区分 |

---

## 九、输出质量评估（补充）

官网将评估分为两件事，本文档之前主要覆盖了触发 eval，补充输出质量 eval：

### 触发 eval（已有）
测试 description 是否在正确场景下激活 skill，方法见第四章。

### 输出质量 eval（补充）
测试 skill 激活后输出的内容是否符合预期，方法：

1. **准备测试用例**：每个用例包含 `prompt`（输入）和 `assertions`（断言列表）
2. **设置 baseline**：不使用 skill 时 Agent 的默认输出，用于对比
3. **运行断言**：对每个断言检查输出是否满足（High severity 不通过则整个 case FAIL）
4. **评分**：统计 PASS/FAIL/WARNING 分布，迭代改进 SKILL.md 指令

推荐用例文件格式：`evals/evals.json`，结构参考：
```json
{
  "trigger_evals": { "queries": [...] },
  "output_quality_evals": { "cases": [...], "grading": {...} }
}
```
