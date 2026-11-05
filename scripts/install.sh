#!/usr/bin/env bash
# scripts/install.sh — guage-svg-gen Skill 安装脚本
# 只安装 skills/guage-svg-gen/ 目录内容，不复制 docs/、evals/、tests/ 等

set -e

SKILL_NAME="guage-svg-gen"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$SCRIPT_DIR/../skills/guage-svg-gen"

# ─── 参数解析 ────────────────────────────────────────────────────────────────
OPT_DEST=""
OPT_WORKSPACE=""
OPT_YES=0
OPT_SKIP_DEPS=0

print_usage() {
    cat <<EOF
用法: bash scripts/install.sh [选项]

选项:
  --dest <路径>        安装目标 Skills 目录（如 ~/.claude/skills）
  --workspace <路径>   SVG 产出物输出目录（默认：\${SVG_ARCHITECT_WORKSPACE:-\$HOME/Documents/workspace/svg-architect}）
  --yes                覆盖已有安装，不询问确认
  --skip-deps          跳过 Python 依赖安装
  -h, --help           显示此帮助

非交互示例:
  bash scripts/install.sh --dest ~/.claude/skills --workspace ~/svg-output --yes --skip-deps
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dest)       OPT_DEST="$2";      shift 2 ;;
        --workspace)  OPT_WORKSPACE="$2"; shift 2 ;;
        --yes)        OPT_YES=1;          shift   ;;
        --skip-deps)  OPT_SKIP_DEPS=1;    shift   ;;
        -h|--help)    print_usage; exit 0 ;;
        *) echo "未知参数: $1"; print_usage; exit 1 ;;
    esac
done

INTERACTIVE=0
[[ -z "$OPT_DEST" && -z "$OPT_WORKSPACE" && "$OPT_YES" -eq 0 && "$OPT_SKIP_DEPS" -eq 0 ]] && INTERACTIVE=1

echo "========================================="
echo " guage-svg-gen Skill 安装向导"
echo "========================================="
echo ""

# ─── 验证 Skill 源目录 ──────────────────────────────────────────────────────
if [ ! -f "$SKILL_SRC/SKILL.md" ]; then
    echo "错误：在 $SKILL_SRC 下找不到 SKILL.md"
    echo "请确保从项目根目录或 scripts/ 目录内执行此脚本"
    exit 1
fi

# ─── 确定 workspace 路径 ────────────────────────────────────────────────────
DEFAULT_WORKSPACE="${SVG_ARCHITECT_WORKSPACE:-$HOME/Documents/workspace/svg-architect}"

if [ -n "$OPT_WORKSPACE" ]; then
    WORKSPACE_PATH="${OPT_WORKSPACE/#\~/$HOME}"
elif [ "$INTERACTIVE" -eq 1 ]; then
    echo "请选择安装模式："
    echo "  1) 默认 workspace（$DEFAULT_WORKSPACE）"
    echo "  2) 自定义 workspace 路径"
    echo ""
    read -r MODE_CHOICE
    case "$MODE_CHOICE" in
        2)
            if [ -n "$SVG_ARCHITECT_WORKSPACE" ]; then
                WORKSPACE_PATH="$SVG_ARCHITECT_WORKSPACE"
                echo "检测到环境变量 SVG_ARCHITECT_WORKSPACE，使用：$WORKSPACE_PATH"
            else
                echo "请输入 workspace 路径（或设置环境变量 SVG_ARCHITECT_WORKSPACE）："
                read -r WORKSPACE_PATH
                WORKSPACE_PATH="${WORKSPACE_PATH/#\~/$HOME}"
                if [ -z "$WORKSPACE_PATH" ]; then
                    echo "错误：未提供 workspace 路径"
                    exit 1
                fi
            fi
            ;;
        *) WORKSPACE_PATH="$DEFAULT_WORKSPACE" ;;
    esac
else
    WORKSPACE_PATH="$DEFAULT_WORKSPACE"
fi

echo "workspace：$WORKSPACE_PATH"
mkdir -p "$WORKSPACE_PATH"
echo "  ✓ workspace 已就绪"
echo ""

# ─── 安装 Python 依赖 ────────────────────────────────────────────────────────
if [ "$OPT_SKIP_DEPS" -eq 1 ]; then
    echo "  跳过 Python 依赖安装（--skip-deps）"
elif command -v python3 &>/dev/null; then
    echo "正在检查 Python 依赖..."
    echo "  ✓ Python3 已就绪"
    if [ -f "$SKILL_SRC/requirements.txt" ]; then
        echo "  安装依赖（PNG 导出与 QA 预览渲染需要）..."
        python3 -m pip install -q -r "$SKILL_SRC/requirements.txt" && \
            echo "  ✓ Python 依赖安装完成" || \
            echo "  ⚠ 依赖安装失败（不影响 SVG 生成，仅影响 PNG 导出与 QA 预览渲染）"
    fi
else
    echo "  ⚠ 未检测到 Python3，scripts/ 中的验证脚本将无法运行"
fi
echo ""

# ─── 环境检查 ───────────────────────────────────────────────────────────────
echo "环境检查："
check_tool() {
    if command -v "$1" &>/dev/null; then
        echo "  ✓ $1"
    else
        echo "  ✗ $1（未安装，$2）"
    fi
}
check_tool "cairosvg" "pip install cairosvg（PNG 导出备用引擎）"
check_tool "svgo"     "npm install -g svgo（SVG 压缩优化）"
echo ""

# ─── 确定安装目标 ────────────────────────────────────────────────────────────
DEST=""

if [ -n "$OPT_DEST" ]; then
    OPT_DEST="${OPT_DEST/#\~/$HOME}"
    mkdir -p "$OPT_DEST"
    DEST="$OPT_DEST/$SKILL_NAME"
elif [ "$INTERACTIVE" -eq 1 ]; then
    echo "请选择要安装到哪个工具的 Skills 目录："
    echo "  1) Claude Code  (~/.claude/skills/)"
    echo "  2) 手动指定路径"
    echo "  3) 跳过（仅初始化 workspace）"
    echo ""
    read -r TOOL_CHOICE
    case "$TOOL_CHOICE" in
        1)
            SKILLS_DIR="$HOME/.claude/skills"
            mkdir -p "$SKILLS_DIR"
            DEST="$SKILLS_DIR/$SKILL_NAME"
            ;;
        2)
            echo "请输入目标 Skills 目录路径："
            read -r CUSTOM_SKILLS_DIR
            CUSTOM_SKILLS_DIR="${CUSTOM_SKILLS_DIR/#\~/$HOME}"
            if [ ! -d "$CUSTOM_SKILLS_DIR" ]; then
                echo "错误：目录不存在：$CUSTOM_SKILLS_DIR"
                exit 1
            fi
            DEST="$CUSTOM_SKILLS_DIR/$SKILL_NAME"
            ;;
        *) echo "  跳过 Skill 安装，仅完成 workspace 初始化。" ;;
    esac
fi

# ─── 覆盖确认 ────────────────────────────────────────────────────────────────
if [ -n "$DEST" ] && [ -d "$DEST" ]; then
    if [ "$OPT_YES" -eq 0 ] && [ "$INTERACTIVE" -eq 1 ]; then
        echo "检测到已安装的旧版本，是否覆盖？(y/n)"
        read -r OVERWRITE
        if [ "$OVERWRITE" != "y" ]; then
            echo "已取消覆盖，保留旧版本。"
            DEST=""
        fi
    fi
fi

# ─── 执行安装 ────────────────────────────────────────────────────────────────
if [ -n "$DEST" ]; then
    rsync -a --delete \
        --exclude='.git/' \
        --exclude='.DS_Store' \
        "$SKILL_SRC/" "$DEST/"
    echo "  ✓ Skill 已安装到：$DEST"
fi

# ─── 完成提示 ────────────────────────────────────────────────────────────────
echo ""
echo "========================================="
echo " 安装完成！"
echo "========================================="
echo ""
echo "下一步："
echo ""
echo "  SVG 产出物将保存至："
echo "  $WORKSPACE_PATH"
echo ""
echo "  在支持 Agent Skills 的工具中说："
echo "    '帮我做一张公众号封面图，主题是 [xxx]'"
echo "    '画一张 [xxx] 的架构图'"
echo "    '出一张 [xxx] 流程图配图'"
echo ""
