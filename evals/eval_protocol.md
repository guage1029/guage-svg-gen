# Guage SVG Gen Eval Protocol

## 目标

衡量 guage-svg-gen skill 的真实交付质量，回答三个问题：

1. **触发准确性**：该触发时触发，不该触发时不触发
2. **风格覆盖**：6 种风格是否都能正确输出，各自弱点在哪里
3. **输出质量**：生成结果是否通过机械规范检查、符合平台要求、具备视觉完成度

---

## 文件结构

```
evals/
├── eval_protocol.md              # 本文件
├── trigger_evals.json            # 正例触发用例（24 条，should_trigger 全部为 true）；expected_style=null 表示不考核风格选择，只考核触发与平台推断
├── negative_evals.json           # 负例（16 条，should_trigger 全部为 false）；评测脚本应分别加载两文件，勿混用
├── style_coverage_evals.json     # 风格覆盖（6 风格 × 2 平台 = 12 条）
├── output_quality_evals.json     # 输出质量断言（12 case，三类断言）
└── runs/
    └── <YYYYMMDD>/
        └── <case_id>/
            └── with_skill/
                ├── output.svg
                ├── validator_report.json
                ├── judge_scores.json
                └── notes.md
```

---

## 运行方式

### Step 1：触发评测

针对 `trigger_evals.json` + `negative_evals.json` 中的每条 query：

```bash
# 用 Claude Code 运行，观察 skill 是否被触发
# 记录实际行为：triggered / not_triggered
```

每条记录结果：

```json
{
  "id": "trigger-cover-01",
  "expected": true,
  "actual": true,
  "pass": true
}
```

合格标准：
- `should_trigger=true` 的命中率 ≥ **87.5%**（24 条中至少 21 条触发）
- `should_trigger=false` 的误触率 ≤ **12.5%**（16 条中至多 2 条误触）

---

### Step 2：风格覆盖评测

针对 `style_coverage_evals.json` 中的 12 条，每条跑 `with_skill`：

1. 生成 SVG，保存到 `runs/<date>/<case_id>/with_skill/output.svg`
2. 运行 validator：
   ```bash
   python3 skills/guage-svg-gen/scripts/svg_validator.py \
     --svg runs/<date>/<case_id>/with_skill/output.svg \
     --strict --json \
     > runs/<date>/<case_id>/with_skill/validator_report.json
   ```
3. 对照 `style_characteristics` 列表，人工或 LLM judge 打分

---

### Step 3：输出质量评测

针对 `output_quality_evals.json` 中的 12 个 case，每条必须产出以下 5 个文件：

```
runs/<date>/<case_id>/with_skill/
├── output.svg
├── validator_report.json     # svg_validator.py --strict --json
├── preview.png               # render_svg_preview.py 全画布预览
├── thumbnail_crop.png        # render_svg_preview.py 焦点裁切
└── visual_report.json        # render_svg_preview.py 渲染质量报告
```

#### 3.0 预览渲染（前置步骤，先于人工评分）

```bash
python3 skills/guage-svg-gen/scripts/render_svg_preview.py \
  --svg runs/<date>/<case_id>/with_skill/output.svg \
  --platform <wechat_cover|wechat_article> \
  --out-dir runs/<date>/<case_id>/with_skill/ \
  --json
```

> **注意**：脚本已将 `visual_report.json` 写入 `--out-dir` 指定目录，**不要**用 `> visual_report.json` 重定向 stdout，否则脚本写完后 shell 会再次截断同一文件，产生 `Extra data` JSONDecodeError。如需捕获 stdout 供管道处理，可重定向到另一个文件（如 `render_stdout.json`），或直接读磁盘的 `visual_report.json`。

`visual_report.json` 中的字段必须满足：

| 字段 | 通过条件 |
|------|---------|
| `status` | `PASS` 或 `WARN`（`FAIL` 视为该 case 不通过） |
| `dimensions_match` | `true` |
| `viewbox_ok` | `true` |
| `is_blank` | `false` 或 `null`（`true` 视为空白输出，不通过） |
| `has_transparent_bg` | 允许 `true`（WARN），但需在 `notes.md` 中说明 |

`visual_report.json` 必须同时记录 `backend` 字段（`chromium` 或 `cairosvg`）。

#### 3.1 机械断言（script）

运行 validator 并检查是否包含对应错误码：

```bash
python3 skills/guage-svg-gen/scripts/svg_validator.py \
  --svg output.svg --strict --json \
  | python3 -c "
import sys, json
report = json.load(sys.stdin)
error_codes = [e['code'] for e in report['errors']]
print('ERROR_CODES:', error_codes)
print('STATUS:', report['status'])
"
```

通过条件：`report['status'] == 'PASS'`（严格模式）

#### 3.2 平台断言（rule）

用正则或 XML 解析验证：

```python
import xml.etree.ElementTree as ET
tree = ET.parse('output.svg')
root = tree.getroot()
vb = root.attrib.get('viewBox', '')
# wechat_cover: assert vb == '0 0 1800 766'
# wechat_article: assert vb == '0 0 1200 500'
```

#### 3.3 视觉断言（human_or_llm）

评分维度（1–5 分，3 分及以上为通过）：

| 维度 | 说明 |
|------|------|
| 风格一致性 | 生成风格是否与 expected_style 吻合 |
| 信息层级 | 主标题/副标题/正文是否有清晰视觉权重差异 |
| 构图清晰度 | 元素排布是否合理，无相互遮挡或过度拥挤 |
| 公众号缩略图可读性 | 关键信息是否在缩略图区域（封面中央约 400×766）内可见 |
| 视觉完成度 | 整体是否有设计感，不像"未完成的草稿" |
| 规范合规性 | 机械断言和平台断言通过数量 |

评分记录格式：

```json
{
  "case_id": "quality-tech-dark-cover-01",
  "scores": {
    "style_consistency": 4,
    "info_hierarchy": 5,
    "composition": 4,
    "thumbnail_readability": 3,
    "visual_completeness": 4,
    "spec_compliance": 5
  },
  "overall": "PASS",
  "notes": "渐变文字在 fill=url(#...) 处未被 strict 模式拦截，需人工确认对比度"
}
```

---

## 对比评测（可选）

后续可加 `without_skill` 对照组（直接让 Claude 生成，不触发 skill），对比：

- 规范合规性差距（validator ERROR 率）
- 风格一致性差距
- 平台尺寸准确率

目录约定：

```
runs/<date>/<case_id>/
├── with_skill/
└── without_skill/   # 可选对照
```

---

## 验收门禁

| 指标 | 门槛 |
|------|------|
| trigger 命中率 | ≥ 87.5% |
| negative 误触率 | ≤ 12.5% |
| style coverage validator PASS 率 | ≥ 83%（12 条中 ≥ 10 条） |
| output quality 高严重度断言 PASS 率 | ≥ 90% |
| 视觉维度平均分 | ≥ 3.5 / 5 |

---

## 注意事项

- `human_or_llm` 类断言可以用 Claude 作为 judge，prompt 参考：`"以下是一张公众号 SVG 图，请判断它是否满足：{check}。只回答 PASS/FAIL/PARTIAL，并在一行内说明理由。"`
- 机械断言失败时优先修复 validator 规则或 SVG 生成逻辑，不要调低门槛
- 每次 eval run 结束后更新 `runs/<date>/summary.json`，记录总体通过率和失败 case 列表
