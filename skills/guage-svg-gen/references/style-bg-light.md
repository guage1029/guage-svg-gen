# BG-Light Visual Specification（纸感白底暖灰网格）

## 适用定位
浅色 SVG 技术配图、文档插图、架构/原理图与清爽概念对比卡。采用**温和纸张感纯平底板（`#F7F5F0`）+ 像素对齐的暖灰细线网格 + 纯白（`#FFFFFF`）不透明卡片**，无背景光晕与模糊阴影，靠明确暖灰描边与强调色区分层次，兼具长时间阅读舒适度与清晰的主卡立体剥离感。

## Palette（`bg_light` Token）
- **Background**: `#F7F5F0`（偏纸张感的米白/书页白，纯平无光晕，衬托 `#FFFFFF` 纯白主卡更清晰）
- **Outer Frame（画幅收边，仅 `wechat_article`）**: `#CCC7BD`（`border`），使用 `x="0" y="0" width="1200" height="<H>" fill="none" stroke-width="2"`（默认 `16:9` 时 `H=675`）由视口外裁保留稳定 1px 整数对齐细边；`wechat_cover` 封面不加外框
- **Grid Line**: `#D6D2C9`（暖灰细线），`25×25px` 抗缩放细线（`M 24 0 L 24 25 M 0 24 L 25 24`），`stroke-width="1.5"`，`stroke-opacity="0.55"`（防止缩略图下 `1px` 细线劈裂发虚）
- **Card / Surface**:
  - 节点主卡与遮罩底托（不透明防穿线）：`#FFFFFF`（`surface` / `surface_accent`）
  - 次级卡片 / 子模块：`#EFECE4`（`surface_alt` / `surface_secondary`）
  - 焦点卡片底面：`#FFFFFF` 配合 `#2563EB`（`border_primary`）强调边框
  - 常规边框：`#CCC7BD`（`border`）或 `#A8A29E`（`border_mid`）
- **Dashed Zones（虚线区）**: `stroke="#78716C"`（`border_zone`），**`fill="none"`**（保持虚线框内外网格线颜色完全一致），主域 `stroke-dasharray="8,4"`，子域 `4,4`
- **Edges & Accents**: 主连线 `#2563EB`（`2–2.5px` 实线），异步/事件流 `#7C3AED`（`stroke-dasharray="5,5"`）
- **Text**: `#09090B`（主字）、`#52525B`（次字）、`#3F3F46`（弱化说明），均满足 `≥ 4.5:1` 对比度

## Radius Hierarchy（四级圆角规范）
- `zones` 大虚线边界框：`rx="12"`
- 主节点卡片：`rx="10"`
- 次级/内嵌/底层卡片：`rx="8"`
- 标签胶囊（Pill / Badge）：半高全圆角（`rx = h / 2`，如高 `26px` 用 `rx="13"`、高 `34px` 用 `rx="17"`）

## Typography & Scales（`wechat_article` 宽 1200 默认 `16:9` `1200×675` / `wechat_cover` `1800×766`）
- **Font Stacks**: 中文 `PingFang SC, Noto Sans SC, Microsoft YaHei, system-ui, sans-serif`；英文展示 `Inter, PingFang SC, Noto Sans SC, system-ui, sans-serif`；代码 `JetBrains Mono, monospace`（字体名不加引号）
- **多节点架构/流程图（`wechat_article`）**：H1 主标题 `28–36px`（`font-weight="800"`），H2 副标题 `16–18px`（`500`），主卡标题 `18–20px`（`700`），次卡标题/胶囊/虚线域标签 `16px`（`600`），正文/图例 `16px`（`400`，**硬下限 16px**；`wechat_cover` 下限 `18px`）
- **高冲击双核对比图卡（Dual-Hero，`wechat_article`）**：推荐使用紧凑 `2.4:1`（`1200×500`）或默认 `16:9`（`1200×675`），L1 主视觉词 `108–116px`（`800`）、L2 分类标签 `22px`（`600`）、L3 胶囊说明 `18px`（`500`，高 `34px`、`rx="17"`）
- **混排与字距**：中文 `letter-spacing` 为 `0`；仅纯 Latin 短标签可用 `2–3px`。左对齐混排可用 `<tspan>` 切换英文/等宽字体且与中文等大；居中/右对齐禁止多 `<tspan>`（拆成独立 `<text>`）。

## Background & Grid SVG Pattern（`16:9` 默认 `1200×675` 示例）
```xml
<pattern id="svga-<slug>-grid" width="25" height="25" patternUnits="userSpaceOnUse">
  <path d="M 24 0 L 24 25 M 0 24 L 25 24"
        fill="none" stroke="#D6D2C9" stroke-width="1.5" stroke-opacity="0.55"
        data-svga-role="decoration" data-svga-color-role="grid"/>
</pattern>
<rect x="0" y="0" width="1200" height="675" fill="#F7F5F0" data-svga-color-role="background"/>
<rect x="0" y="0" width="1200" height="675" fill="url(#svga-<slug>-grid)" data-svga-role="decoration"/>
<!-- wechat_article 正文配图加 1px 整数裁切外框；wechat_cover 省略此行 -->
<rect x="0" y="0" width="1200" height="675" fill="none" stroke="#CCC7BD" stroke-width="2" data-svga-role="decoration" data-svga-color-role="border"/>
```

## Negative Constraints
- 不添加任何背景光晕、渐变底色或 CSS 模糊阴影（`cairosvg` 下易退化）
- 节点首层须使用不透明 `#FFFFFF`（或实色 `surface`）以遮挡背后穿过的连线
- 不使用浅灰文字（如 `#94A3B8`）放在白底上，确保对比度 `≥ 4.5:1`
