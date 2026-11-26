# guage-svg-gen — 确定性工程级 SVG 绘图 Skill

- **版本**：`v0.17.29`
- **作者**：`donglin`
- **适用平台**：Claude Code · OpenAI Codex CLI · Antigravity · Gemini CLI · SkillPay（Agent Skills 标准）

让 AI Agent 告别盲写 SVG 坐标导致的「文字溢出卡片」「箭头斜穿节点」「中英混排成方块」「高饱和霓虹配色」。通过 **`layout.json` 布局契约 + 四重机械校验门禁 + 真图视觉预览**，稳定产出可源码直改的纯代码矢量技术配图与公众号封面。

---

## 1. 30 秒导入 Agent 使用

将本目录（包含 `SKILL.md` 的 `guage-svg-gen/` 文件夹）放到你的 Agent 技能目录下即可生效：

| Agent / 平台 | 推荐放置路径 | 唤醒方式 |
| --- | --- | --- |
| **Claude Code** | `~/.claude/skills/guage-svg-gen/` | 直接提画图需求，或输入 `/guage-svg-gen` |
| **Codex CLI / Antigravity** | `~/.agents/skills/guage-svg-gen/` | 直接提画图需求，或调用 `guage-svg-gen` |
| **SkillPay / 在线商店** | 直接上传本包 `.zip` 或本文件夹 | 平台自动识别根目录 `SKILL.md` |

---

## 2. 让 Agent 一键帮你检查并配齐环境（开箱即用）

如果你不确定本机环境是否齐全，**导入技能包后可直接对 Agent 发送下面这句话**：

> 「请读取 `guage-svg-gen/README.md` 与 `requirements.txt`，检查我当前机器缺少哪些 Python 包或系统依赖，告诉我具体版本并帮我完成安装和验证。」

---

## 3. 运行环境与版本要求总表

| 组件 | 要求版本 | 作用说明 | 是否必需 | 安装命令参考 |
| --- | --- | --- | --- | --- |
| **Python** | `>= 3.10` | 运行校验与渲染管线脚本 | **必需** | `python3 --version`（macOS: `brew install python@3.12`） |
| **Pillow** | `>= 10.0.0` | `validate_geometry.py` 字体度量与 `render_preview.py` 裁剪分析 | **必需** | `pip install -r requirements.txt` |
| **cairosvg** | `>= 2.7.1` | SVG 转 PNG 预览与高清 PNG 导出后端 | **推荐必需** | `pip install -r requirements.txt` |
| **numpy** | `>= 1.24.0` | `render_preview.py` 高速像素占比与空白边角检测 | 推荐 | `pip install -r requirements.txt` |
| **系统 Cairo 库** | `libcairo >= 1.16` | `cairosvg` 底层 C 库支撑 | 用 `cairosvg` 时必需 | macOS: `brew install cairo`<br>Ubuntu/Debian: `sudo apt-get install -y libcairo2` |
| **fontconfig (`fc-match`)** | 系统自带或最新 | `validate_geometry.py` 匹配真实 CJK/Latin 字体文件 | **必需** | macOS: `brew install fontconfig`<br>Ubuntu/Debian: `sudo apt-get install -y fontconfig` |
| **中文字体** | 任意现代黑体 | 确保中文渲染不出现方块（`Hiragino Sans GB` / `PingFang SC` / `Noto Sans CJK` / `Microsoft YaHei`） | **中文图必需** | macOS / Windows 自带；Linux: `sudo apt-get install -y fonts-noto-cjk` |
| **Playwright + Chromium** | `>= 1.40.0` | 当无需 `cairosvg` 或追求浏览器原汁原味渲染时作为主预览引擎 | 可选 | `pip install playwright>=1.40.0 && playwright install chromium` |
| **svgo** | `>= 3.0.0` | `optimize_svg.py` 压缩 SVG 体积 | 可选 | `npm install -g svgo` |

### 一键依赖自检命令

在 Skill 根目录（`SKILL.md` 所在目录）执行：

```bash
python3 - <<'EOF'
import sys, shutil
print("Python:", sys.version.split()[0], "OK" if sys.version_info >= (3, 10) else "NEED >= 3.10")
for pkg in ("PIL", "cairosvg", "numpy", "playwright"):
    try:
        m = __import__(pkg)
        print(f"  [OK] {pkg}:", getattr(m, "__version__", "installed"))
    except Exception as e:
        print(f"  [--] {pkg}: not installed ({e})")
for bin_name in ("fc-match", "svgo"):
    print(f"  [{'OK' if shutil.which(bin_name) else '--'}] {bin_name}:", shutil.which(bin_name) or "not found")
EOF
```

安装依赖后，验证管线入口可执行：

```bash
python3 scripts/run_pipeline.py --help
python3 scripts/render_preview.py --help
```

### 常见问题快速排查

- **`cairosvg` 报错 `no library called "cairo-2" was found`**：说明未安装系统级 `libcairo`。macOS 执行 `brew install cairo`，Ubuntu/Debian 执行 `sudo apt-get install -y libcairo2`。
- **预览图中文变成方框（豆腐块）**：Linux 无默认中文字体时，执行 `sudo apt-get install -y fonts-noto-cjk fontconfig && fc-cache -fv`。
- **导出位置**：默认导出到 `$SVG_ARCHITECT_WORKSPACE`（未设置时默认为 `~/Documents/workspace/svg-architect`），也可在对话中直接指定输出目录。

---

## 4. 目录结构与支持能力

```text
guage-svg-gen/
├── SKILL.md            # 核心技能规约：风格路由、布局契约、门禁与交付模板
├── README.md           # 本开箱即用环境配置与使用手册
├── requirements.txt    # Python 依赖及最低版本清单
├── assets/             # BG-Dark / BG-Light 调色板、字体白名单、JSON Schema 与起步模板
├── references/         # BG-Dark / BG-Light 视觉细节手册与 E_* 错误码修复索引
└── scripts/            # 4 重校验器、自动修复、预览渲染、优化与统一编排 CLI
```

### 对话触发示例

- 「帮我画一张大模型智能体网关与沙箱运行时架构图，深色点阵风格」
- 「用暖纸白淡线风格画一张 2022–2026 演进时间线」
- 「生成一张 1800×766 微信公众号技术封面图，主标题……副标题……」
- 「原地修改这个 SVG 文件，把背景改为纯黑底并重新跑严格校验」
