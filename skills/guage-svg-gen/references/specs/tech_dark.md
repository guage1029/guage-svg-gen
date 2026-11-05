# Tech-Dark Visual Specification

## Style Intent

Use `tech_dark` for immersive technical visuals, AI/code/workflow diagrams, dark concept posters, and high-impact comparison images.

The high-impact dual-hero rules below are specifically for WeChat article visuals and card-style illustrations (`wechat_article`, 1200×500): 图卡配图、正文配图、章节配图、对比卡片、概念卡片. They should feel precise, premium, and legible on mobile thumbnails.

For article/card visuals that compare two numbers, concepts, states, models, or choices, prefer the high-impact dual-hero layout below.

## Palette (沉浸暗黑)
- **Background**: `#0A0A0B` (Deep Space)
- **Primary**: `#3B82F6` (Electric Blue)
- **Secondary**: `#8B5CF6` (Cyber Purple)
- **Text (Primary)**: `#F8FAFC`
- **Text (Secondary)**: `#94A3B8`
- **Card Fill**: `rgba(15, 23, 42, 0.68)`
- **Border**: `rgba(148, 163, 184, 0.28)`
- **Glow**: derive from Primary or Secondary at low opacity; never hardcode a new accent outside the palette unless the user provides brand colors.

## Typography (现代排版)
- **Font Stack (中文内容)**: `PingFang SC, Noto Sans SC, Microsoft YaHei, system-ui, sans-serif`
- **Font Stack (英文/数字标题)**: `Inter, PingFang SC, Noto Sans SC, system-ui, sans-serif`
- **Code / Monospace**: `JetBrains Mono, monospace`
- **Title Weight**: 800 (Extra Bold)
- **Letter Spacing**: 2px 仅适用于纯 Latin/ASCII 标题；中文标题 `letter-spacing` 设为 0 或省略，避免汉字间距异常

### 字号（参考 platform_profiles.md 基准）

tech_dark 偏大字号，H1 取基准上限或略超：

| 层级 | wechat_cover | wechat_article |
|------|-------------|----------------|
| H1 主标题 | 96–120px | 72–88px |
| H2 副标题 | 44–56px | 36–44px |
| Body 节点文字 | 26–32px | 22–26px |
| Caption | ≥18px | ≥16px |

### High-Impact Article Typography

Use this scale for `wechat_article` card-style visuals (1200×500) when the content is a two-sided comparison, numeric contrast, before/after, model-vs-model, idea-vs-reality, or any user request for "图卡", "配图", "冲击", "大字", "双核", "高对比", or "手机端一眼看懂".

| Level | Use | Size | Weight | Notes |
|-------|-----|------|--------|-------|
| L1 Hero | Primary number, short keyword, or core concept | 108–116px | 800 | Use Primary/Secondary highlight. Keep Chinese letter spacing at 0; Latin/numbers may use `letter-spacing="-2"` only when it improves fit. |
| L2 Category | Dimension label above the hero | 22px | 600 | Use `letter-spacing="3"` only for Latin/ASCII labels. For Chinese labels, keep spacing 0 and use weight/opacity for hierarchy. |
| L3 Pill | Secondary descriptor, scene, or qualifier | 18px | 500 | Must sit inside a pill container. |

Hard floor: no text under 16px on `wechat_article`.

### 中英文混排规则

- 同一行中英文混排时，用 `<tspan>` 切换字体：中文片段用中文栈，英文/数字片段用英文栈
- 英文单词视觉偏小时，在同一 `<text>` 内对英文 `<tspan>` 设置 `font-size` 放大 5–10%
- 禁止对含中文的 `<text>` 整体设置 `letter-spacing > 0`；如需强调间距，仅对 Latin `<tspan>` 设置

## High-Impact Dual-Hero Layout

Apply this layout only to article/card illustration scenarios where it fits the content. Do not force it onto complex architecture diagrams, flowcharts, sequence diagrams, or content with more than two primary ideas.

### Geometry for `wechat_article` (1200×500)

- Safe area: x=80, y=50, w=1040, h=400.
- Left hero column: x=100–580.
- Right hero column: x=670–1100.
- Center divider: x=600, y1=110, y2=390.
- Core content band: y=110–390, vertically centered with generous top/bottom breathing room.
- Keep both hero groups optically balanced, not necessarily mathematically identical.

### Composition Rules

1. **No header noise**: do not place a top title, slogan, or explanatory paragraph. The hero concepts are the title.
2. **Dual hero columns**: use two large focal groups split by a thin glowing vertical divider.
3. **Massive hero scale**: primary numbers or hero words must use 108–116px when they fit. If Chinese copy is too long, shorten the copy before shrinking below 96px.
4. **Pill descriptors**: all secondary descriptors must be wrapped in centered pill containers.
5. **Mobile-first legibility**: the image must still communicate after shrinking to about 400px wide.
6. **Theme flexibility**: use the tech_dark palette tokens above. Do not introduce static unrelated colors.

### Pill Component Pattern

Use pills instead of loose multi-line small text. Size width to the text, keep height 34px and `rx=17`.

```svg
<g transform="translate(0, 0)">
  <rect x="0" y="0" width="180" height="34" rx="17"
        fill="rgba(15, 23, 42, 0.68)"
        stroke="rgba(148, 163, 184, 0.28)" stroke-width="1"/>
  <text x="90" y="22" font-size="18" font-weight="500"
        text-anchor="middle"
        font-family="PingFang SC, Noto Sans SC, Microsoft YaHei, system-ui, sans-serif"
        fill="#F8FAFC">辅助说明</text>
</g>
```

### Negative Layout Constraints

- No top title bars.
- No dense paragraph copy.
- No more than two competing hero focal points.
- No tiny legends, footnotes, or axis labels below 16px.
- No decorative frames that make the image look like a PPT slide.

## Effects (质感光影)
- **Glow**: Use `feGaussianBlur` with `stdDeviation="15"` for core nodes.
- **Grid**: 40x40px, `#1E293B`, opacity 0.3.
- **Lines**: Smooth Bezier curves with `#3B82F6` stroke and 2px width.
- **High-impact divider**: For dual-hero layouts only, use a 1–2px vertical divider with subtle Primary/Secondary glow. Keep it outside node groups; architecture and flow diagrams must not place full-height accent rails on node edges.

## Negative Constraints
- No pure black `#000000`.
- No high-saturation primary red/green.
- No low-contrast gradient text for essential hero words.
