# BG-Dark Visual Specification（黑底灰网格 · 默认）

## 适用定位
默认 SVG 技术与概念配图风格（架构图、流程图、原理图、时序图、层级图、双核对比图卡）。采用**接近纯黑的纯平底板 + 像素对齐的中性灰细线网格 + 中性深炭灰卡片**，无背景光晕，突出结构秩序与高对比可读性。

## Palette（`bg_dark` Token）
- **Background**: `#050506`（接近纯黑，纯平无光晕；禁止 `#000000`）
- **Outer Frame（画幅收边，仅 `wechat_article`）**: `#3F3F46`（`border_mid`），使用 `x="0" y="0" width="1200" height="<H>" fill="none" stroke-width="2"`（默认 `16:9` 时 `H=675`）由视口外裁保留稳定 1px 整数对齐细边；`wechat_cover` 封面不加外框
- **Grid Line**: `#27272A`（中性深灰），`25×25px` 像素对齐细线（`M 24.5 0 L 24.5 25 M 0 24.5 L 25 24.5`），`stroke-width="1"`，`stroke-opacity="0.75"`
- **Card / Surface（中性深炭灰）**:
  - 节点底托（不透明防穿线）：`#111114`（`surface`）
  - 次级卡片 / 子模块：`#18181B`（`surface_alt`）
  - 焦点卡片底面：`#1F1F26`（`surface_accent`），配合强调边框 `#3B82F6`（`border_primary`）
  - 常规边框：`#27272A`（`border`）或 `#3F3F46`（`border_mid`）
- **Dashed Zones（虚线区）**: `stroke="#52525B"`（`border_zone`）或 `#3B82F6`（主强调域），**`fill="none"`**（保持虚线框内外网格线颜色一致），主域 `stroke-dasharray="8,4"`，子域 `4,4`
- **Edges & Accents**: 主连线 `#60A5FA`（`2–2.5px` 实线），异步/事件流 `#A78BFA`（`stroke-dasharray="5,5"`）
- **Text**: `#FAFAFA`（主字）、`#A1A1AA`（次字）、`#D4D4D8`（弱化说明）

## Radius Hierarchy（四级圆角规范）
- `zones` 大虚线边界框：`rx="12"`
- 主节点卡片：`rx="10"`
- 次级/内嵌/底层卡片：`rx="8"`
- 标签胶囊（Pill / Badge）：半高全圆角（`rx = h / 2`，如高 `26px` 用 `rx="13"`、高 `34px` 用 `rx="17"`）

## Typography & Scales（`wechat_article` 宽 1200 默认 `16:9` `1200×675` / `wechat_cover` `1800×766`）
- **Font Stacks**: 中文 `PingFang SC, Noto Sans SC, Microsoft YaHei, system-ui, sans-serif`；英文展示 `Inter, PingFang SC, Noto Sans SC, system-ui, sans-serif`；代码 `JetBrains Mono, monospace`（字体名不加引号）
- **多节点架构/流程图（`wechat_article`）**：H1 主标题 `28–36px`（`font-weight="800"`），H2 副标题 `16–18px`（`500`），主卡标题 `18–20px`（`700`），次卡标题/胶囊/虚线域标签 `16px`（`600`），正文/图例 `16px`（`400`，**硬下限 16px**；`wechat_cover` 下限 `18px`）
- **高冲击双核对比图卡（Dual-Hero，`wechat_article`）**：推荐使用紧凑 `2.4:1`（`1200×500`）或默认 `16:9`（`1200×675`）分两组核心数值/概念强对比（左列 `x: 100–580`，中隔线 `x=600`，右列 `x: 670–1100`）；L1 主视觉词 `108–116px`（`800`）、L2 分类标签 `22px`（`600`）、L3 胶囊说明 `18px`（`500`，高 `34px`、`rx="17"`）
- **混排与字距**：中文 `letter-spacing` 为 `0`；仅纯 Latin 短标签可用 `2–3px`。左对齐混排可用 `<tspan>` 切换英文/等宽字体且与中文等大；居中/右对齐禁止多 `<tspan>`（拆成独立 `<text>`）。

## Background & Grid SVG Pattern（`16:9` 默认 `1200×675` 示例）
```xml
<pattern id="svga-<slug>-grid" width="25" height="25" patternUnits="userSpaceOnUse">
  <path d="M 24.5 0 L 24.5 25 M 0 24.5 L 25 24.5"
        fill="none" stroke="#27272A" stroke-width="1" stroke-opacity="0.75"
        data-svga-role="decoration" data-svga-color-role="grid"/>
</pattern>
<rect x="0" y="0" width="1200" height="675" fill="#050506" data-svga-color-role="background"/>
<rect x="0" y="0" width="1200" height="675" fill="url(#svga-<slug>-grid)" data-svga-role="decoration"/>
<!-- wechat_article 正文配图加 1px 整数裁切外框；wechat_cover 省略此行 -->
<rect x="0" y="0" width="1200" height="675" fill="none" stroke="#3F3F46" stroke-width="2" data-svga-role="decoration" data-svga-color-role="border_mid"/>
```

## Negative Constraints
- 禁用 `#000000` 纯黑、背景光晕（`<radialGradient>`/`<feGaussianBlur>`）及节点侧边全高竖条
- 禁用未在 `assets/color-tokens.json` (`bg_dark`) 中声明的裸色值
- 禁用低对比文本（`< 4.5:1`）或渐变文字（`url(#...)`）
