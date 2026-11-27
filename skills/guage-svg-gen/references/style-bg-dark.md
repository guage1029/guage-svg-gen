# BG-Dark Visual Specification（极暗黑底 · 默认）

## 适用定位
默认 SVG 技术与概念配图风格（架构图、流程图、原理图、时序图、层级图、双核对比图卡）。采用**接近纯黑的纯平底板（`#050506`）+ 自适应背景纹理（默认 `25×25px` 微圆点阵 / 可选 `40px` 淡线网 / 纯色无网格）+ 中性深炭灰卡片**，无背景光晕，配 **Okabe-Ito 低饱和莫兰迪三强调色（靛蓝 + 鼠尾草绿 + 暖赭琥珀）** 与中性灰常规连线。

## Palette（`bg_dark` Token）
- **Background**: `#050506`（接近纯黑，纯平无光晕；禁止 `#000000`）
- **Outer Frame（画幅收边，适用于 `wechat_article` 与带框 `custom` 画布）**: `#3F3F46`（`border`），使用 `x="0" y="0" width="<W>" height="<H>" fill="none" stroke-width="2"`（默认 `16:9` 时 `W=1200, H=675`，自定义画布取实际 `W×H`）由视口外裁保留稳定 1px 整数对齐细边；`wechat_cover` 封面不加外框
- **Adaptive Background Texture（按图型择一写入 `metadata.background_style`）**:
  - **C. `dot`（默认主力，架构/流程/状态/ER/部署/层级）**：`25×25px` 格心微圆点阵（`<circle cx="12.5" cy="12.5" r="1.15"/>`，`#3F3F46` `surface_grid_dot`，`fill-opacity="0.65"`）+ 区外标题/域标/边标签/图例加 `#050506` 同底小垫片
  - **B. `line`（`timeline` 及节点 `≤ 6` 轻量矩阵蓝图）**：`40×40px` 极淡疏朗线网（`M 39.5 0 L 39.5 40 M 0 39.5 L 40 39.5`，`#27272A` `surface_grid`，`stroke-width="1"`，`stroke-opacity="0.42"`）+ 同底小垫片
  - **D. `solid`（`sequence`/`swimlane`/`data_visualization`/`comparison`/Dual-Hero/高密度图/`wechat_cover`）**：纯色 `#050506` 零纹理底板，省略 `<pattern>` 与标签垫片；当 `dot`/`line` 节点 `≥ 8` 或边标签 `≥ 5` 时自动退一阶（`line → dot` / `dot → solid`），用户显式要求优先
- **Card / Surface & Border Hierarchy（中性深炭灰）**:
  - 节点主卡（不透明防穿线）：`#111114`（`surface`），中性默认边框 **`#52525B`**（`border_mid`）
  - 次级卡片 / 子模块：`#18181B`（`surface_alt`），清晰中性边框 **`#3F3F46`**（`border`，不与 `#27272A` 网格混色）
  - 焦点卡片底面：`#1A1B24`（`surface_accent`）配合靛蓝框 **`#6979B0`**（`border_primary`）
- **Dashed Zones（虚线区）**: `stroke="#71717A"`（`border_zone`），**`fill="none"`**（保持虚线框内外网格线颜色一致），主域 `stroke-dasharray="8,4"`，子域 `4,4`
- **Edges & Okabe-Ito Morandi Accents（中性灰为主 + 同源色继承）**:
  - **常规结构连线（默认）**：`#71717A`（`edge_neutral`）
  - **靛蓝（核心主链）**：框 `#6979B0` · 线与正文高亮 `#8FA1D9` · 胶囊底 `#1C2238` · 胶囊亮字 `#C7D2FE`
  - **鼠尾草绿（服务/放行/成功）**：框 `#5EB88A` · 线与字 `#7DD3A8` · 胶囊底 `#0F221C`
  - **暖赭琥珀（旁路/异步队列/warning）**：框 `#D9A25F` · 线与字 `#E8B878` · 胶囊底 `#261E12`（异步分支用 `stroke-dasharray="5,5"`）
  - **枯玫瑰红（仅阻断/高危/danger 语义态）**：框 `#CC6E78` · 线与字 `#E38B94` · 胶囊底 `#2A171A`（配虚线与边标签）
  - *连线原则*：中性框出线走 `edge_neutral`；带强调色框的直接下游出线默认继承该框同源强调色（单跳不无限传染），同源正反分流按边语义覆盖并用实/虚线与标签做第二区分（WCAG 1.4.1）。
- **Text**: `#FAFAFA`（`text_primary` 主字：H1/主卡标题/次卡标题）、`#D4D4D8`（`text_secondary` 副标题/域标签/卡片正文统一亮度）、`#A1A1AA`（`text_muted` 底部图例/弱注释）

## Radius Hierarchy（默认四级圆角规范 · 用户指定圆角优先）
- 若用户或题面配置显式指定圆角（如 `radius: 8`），直接按用户配置的 `rx` 执行；未指定时默认：
- `zones` 大虚线边界框：`rx="12"`
- 主节点卡片：`rx="10"`
- 次级/内嵌/底层卡片：`rx="8"`
- **标签胶囊（Pill / Badge，按需可选）**：半高全圆角（`rx = h / 2`，默认高 `28px` 用 `rx="14"`，高 `34px` 用 `rx="17"`）。**注意**：仅当题面或源数据显式给出状态判定规则/阈值时才绘制状态判定胶囊（如 `达标/关注/正常`）与阈值图例口径；若仅给出原始数值与量程（如 `92/88/64` 与 `0–100`）而无阈值定义，**必须省略状态判定胶囊、五档主观刻度与阈值图例**，严禁自拟 `90%/80%` 等阈值。

## Typography & Scales（`wechat_article` 宽 1200 默认 `16:9` `1200×675` / `wechat_cover` `1800×766`）
- **Font Stacks**: 中文 `PingFang SC, Hiragino Sans GB, Noto Sans SC, Microsoft YaHei, sans-serif`；英文展示 `Inter, PingFang SC, Hiragino Sans GB, Noto Sans SC, sans-serif`；代码 `JetBrains Mono, SF Mono, Menlo, Consolas, monospace`（去 `system-ui`，字体名不加引号）
- **多节点架构/流程图五级阶梯（`wechat_article`）**：结构区分只依赖 `400` / `700`（加粗与常规）：H1 主标题 `32px`（`800`）、H2 副标题 `18px`（`400`）、主卡标题 `20px`（`700`）、次卡标题 `18px`（`700`）、虚线域标题 `17px`（`700`）、主链路标签 `17px`（`600`）、卡片正文 / 异步标签 / 底部图例 `16px`（`400`）、`28px` 高胶囊文字 `16px`（`600`）——**硬下限 16px**；`wechat_cover` 下限 `18px`。
- **高冲击双核对比图卡（Dual-Hero，`wechat_article`）**：推荐使用紧凑 `2.4:1`（`1200×500`）或默认 `16:9`（`1200×675`）分两组核心数值/概念强对比（左列 `x: 100–580`，中隔线 `x=600`，右列 `x: 670–1100`）；L1 主视觉词 `108–116px`（`800`）、L2 分类标签 `22px`（`600`）、L3 胶囊说明 `18px`（`500`，高 `34px`、`rx="17"`）
- **自定义画布（`custom`，如 `640×360` / `800×450`）**：字号、留边、间距与节点 `padding` 按 `scale = min(W/1200, H/675)` 等比缩放，Caption 下限为 `max(10, min(16, round(16 × scale)))`（例如 `640×360` 下限 `10px`，标题可用 `18–20px`、卡标题 `13–14px`、正文 `10–12px`）。
- **混排与字距**：中文 `letter-spacing` 为 `0`；仅纯 Latin 短标签可用 `2–3px`。左对齐混排可用 `<tspan>` 切换英文/等宽字体且与中文等大；居中/右对齐禁止多 `<tspan>`（拆成独立 `<text>`）。

## Background Texture & Cutout Halo SVG Snippets（`16:9` 默认 `1200×675` 示例）

1. **C. `dot`（默认微圆点阵 + 同底标签遮罩）**：
```xml
<pattern id="svga-<slug>-grid" width="25" height="25" patternUnits="userSpaceOnUse">
  <circle cx="12.5" cy="12.5" r="1.15"
          fill="#3F3F46" fill-opacity="0.65"
          data-svga-role="decoration" data-svga-color-role="grid"/>
</pattern>
<rect x="0" y="0" width="1200" height="675" fill="#050506" data-svga-color-role="background"/>
<rect x="0" y="0" width="1200" height="675" fill="url(#svga-<slug>-grid)" data-svga-role="decoration"/>
<!-- wechat_article 正文配图加 1px 整数裁切外框；wechat_cover 省略此行 -->
<rect x="0" y="0" width="1200" height="675" fill="none" stroke="#3F3F46" stroke-width="2" data-svga-role="decoration" data-svga-color-role="border"/>
<!-- 在 Zones 与 Edges 之前为区外标题/域标/边标签/图例加同底垫片，免点阵切割也免 E_EDGE_OCCLUDED -->
<g id="svga-<slug>-label-halos" data-svga-role="decoration">
  <rect x="..." y="..." width="..." height="..." rx="4" fill="#050506" data-svga-color-role="background"/>
</g>
```

2. **B. `line`（`timeline` / 轻量矩阵 40px 淡线网，同需 `label-halos`）**：
```xml
<pattern id="svga-<slug>-grid" width="40" height="40" patternUnits="userSpaceOnUse">
  <path d="M 39.5 0 L 39.5 40 M 0 39.5 L 40 39.5"
        fill="none" stroke="#27272A" stroke-width="1" stroke-opacity="0.42"
        data-svga-role="decoration" data-svga-color-role="grid"/>
</pattern>
```

3. **D. `solid`（纯色无网格，省略 `<pattern>` 与 `label-halos`）**：
```xml
<rect x="0" y="0" width="1200" height="675" fill="#050506" data-svga-color-role="background"/>
<rect x="0" y="0" width="1200" height="675" fill="none" stroke="#3F3F46" stroke-width="2" data-svga-role="decoration" data-svga-color-role="border"/>
```

## Negative Constraints
- 禁用 `#000000` 纯黑、背景光晕（`<radialGradient>`/`<feGaussianBlur>`）及节点侧边全高竖条
- 禁用未在 `assets/color-tokens.json` (`bg_dark`) 中声明的裸色值
- 禁用低对比文本（`< 4.5:1`）或渐变文字（`url(#...)`）
