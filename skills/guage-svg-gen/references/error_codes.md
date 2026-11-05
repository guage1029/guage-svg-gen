# Guage SVG Gen Error & Exit Codes

## 1. Error Codes (`E_*`)

| Code | Meaning | Repair Responsibility |
| :--- | :--- | :--- |
| `E_VIEWBOX_MISSING` | Missing `viewBox` attribute | `svg_fixer.py` (auto) |
| `E_VIEWBOX_INVALID` | Malformed `viewBox` format | `svg_fixer.py` (auto) |
| `E_GEOMETRY_OUT_OF_BOUNDS` | Safe area or slots exceed viewBox | `repair-cmd` / Manual |
| `E_GEOMETRY_CONTRACT_MISSING` | Layout plan lacks nodes, text_boxes or edges | Manual |
| `E_NODE_OVERLAP` | Declared node rectangles overlap | Manual |
| `E_NODE_MISSING` | A planned node has no matching `data-svga-node` group | Manual |
| `E_NODE_SIDE_RAIL` | 节点内部存在贴左/右边缘的全高装饰竖条；默认仅保留外边框 | Manual |
| `E_TEXT_MISSING` | A planned text box has no matching `data-svga-text` element | Manual |
| `E_TEXT_OVERFLOW` | Measured text width exceeds its planned box | Manual |
| `E_TEXT_OUT_OF_BOX` | Measured text escapes its planned box | Manual |
| `E_TEXT_PADDING` | Text box violates its node padding | Manual |
| `E_TEXT_RESERVED_OVERLAP` | Text overlaps a reserved icon or control zone | Manual |
| `E_EDGE_MISSING` | A planned edge has no matching `data-svga-edge` path | Manual |
| `E_EDGE_GRADIENT_STROKE` | 连线使用渐变描边，零宽/零高包围盒可能令线段消失 | Manual |
| `E_EDGE_OCCLUDED` | 后绘制的不透明矩形遮挡连线 | Manual |
| `E_ARROW_MISSING` | Directed edge has no `marker-end` arrow | Manual |
| `E_ARROW_MARKER_MISSING` | Edge references an undefined marker | Manual |
| `E_ARROW_MARKER_UNITS` | Arrow marker must use fixed `userSpaceOnUse` units | Manual |
| `E_ARROW_MARKER_INVALID` | Arrow marker geometry is not numeric | Manual |
| `E_ARROW_OVERSIZE` | Arrow marker exceeds the maximum visual size | Manual |
| `E_ARROW_REF_MISMATCH` | Arrow tip is not aligned with marker end | Manual |
| `E_PORT_MISSING` | Edge references a missing node port | Manual |
| `E_EDGE_PATH_INVALID` | Edge path cannot be parsed | Manual |
| `E_EDGE_START_MISMATCH` | Edge start misses its declared source port | Manual |
| `E_EDGE_END_MISMATCH` | Edge end misses its declared target port | Manual |
| `E_EDGE_ROUTE_UNDECLARED` | Edge has no declared route strategy | Manual |
| `E_EDGE_WAYPOINTS_MISSING` | Edge has fewer than two planned waypoints | Manual |
| `E_EDGE_ROUTE_MISMATCH` | SVG path does not match planned waypoints | Manual |
| `E_EDGE_CROSSES_NODE` | Edge crosses an unrelated node rectangle | Manual |
| `E_EDGE_CROSSES_TEXT` | Edge crosses a planned text box | Manual |
| `E_EDGE_TOO_CLOSE` | Two unrelated edges violate minimum clearance | Manual |
| `E_PATH_UNTAGGED` | Visible path lacks an explicit edge, icon or decoration role | Manual |
| `E_CONTRAST_LOW` | Contrast ratio < 4.5:1 | `repair-cmd` / Manual |
| `E_CONTRAST_UNRESOLVED` | Text color cannot be resolved (strict) | `repair-cmd` / Manual |
| `E_SECURITY_TAG` | Dangerous tag (`script`, `iframe`, etc.) | `repair-cmd` / Manual |
| `E_SECURITY_STYLE_CONTENT` | Unsafe CSS (`@import`, external `url()`) | `svg_fixer.py` (auto) |
| `E_SECURITY_EXTERNAL` | External `href` or `src` detected | `repair-cmd` / Manual |
| `E_A11Y_MISSING` | Missing `<title>` or `<desc>` | `svg_fixer.py` (auto) |
| `E_ID_PREFIX_MISSING` | 有 `id` 属性但未使用允许前缀（默认 `svga-`）；修复：重命名 id 并同步所有 `url(#id)`、`href="#id"`、`xlink:href="#id"` 引用 | Manual |
| `E_FONT_FAMILY_MISSING` | 文本元素缺少 `font-family`，且祖先也未提供可继承字体栈 | Manual |
| `E_FONT_FALLBACK_MISSING` | `font-family` 缺少最终 fallback：`sans-serif` 或 `monospace` | Manual |
| `E_FONT_EXTERNAL` | 检测到 `@font-face` 或外部字体 `url(...)` | Manual |
| `E_FONT_SIZE_TOO_SMALL` | 文本字号低于当前平台 Caption 下限（`wechat_cover` < 18px，`wechat_article` < 16px） | Manual |
| `E_CONTRAST_GRADIENT_TEXT` | strict 模式下关键文字使用 `url(#...)` 渐变/pattern fill，对比度无法计算；需改为 solid fill 或人工确认 | Manual |
| `E_XML_PARSE_FAIL` | SVG is not a valid XML | Manual |
| `E_VALIDATOR_CRASH` | Internal validator logic error | Developer |
| `E_PIPELINE_STALLED` | No progress made after retry | Manual |
| `E_PIPELINE_REPORT_PARSE_FAIL` | Failed to parse JSON report | Developer |
| `E_COLOR_THEME_UNKNOWN` | Color theme is not defined in the token registry | Manual |
| `E_COLOR_TOKEN_UNKNOWN` | A role references a missing color token | Manual |
| `E_COLOR_ROLE_UNMAPPED` | SVG color role is not declared in the layout plan | Manual |
| `E_COLOR_RAW_UNAPPROVED` | SVG contains a raw hex color outside the selected theme | Manual |
| `E_DIAGRAM_TYPE_UNKNOWN` | Diagram type is not covered by the color mapping registry | Manual |
| `E_LANGUAGE_INVALID` | `metadata.language` is unsupported | Manual |
| `E_LANGUAGE_DEFAULT_NOT_ZH` | zh 模式中出现未允许的普通英文文本 | Manual |
| `E_LANGUAGE_KIND_INVALID` | 英文文本的保留类型未定义 | Manual |
| `E_LAYOUT_CONSTRAINT_NODE_MISSING` | 布局约束引用了不存在的节点 | Manual |
| `E_NODE_ALIGNMENT_INCONSISTENT` | 同组节点未保持统一的 y 基线 | Manual |
| `E_NODE_HEIGHT_INCONSISTENT` | 同组节点高度不一致 | Manual |
| `E_EDGE_NON_ORTHOGONAL` | 开启正交连线时发现曲线或斜线段 | Manual |

---

## 2. Pipeline Exit Codes

| Code | Meaning | Action |
| :--- | :--- | :--- |
| **0** | **Success** | Pipeline completed, assets ready. |
| **1** | **Failed (Logic/Stalled)** | Max retries reached or `E_PIPELINE_STALLED`. |
| **2** | **Failed (Infrastructure)** | `E_PIPELINE_REPORT_PARSE_FAIL` or validator crash. |
| **3** | **Repair Required** | Non-auto-fixable error detected (when no `--repair-cmd`). |
| **4** | **Post-processing Warning** | SVG ready but PNG export failed. |
