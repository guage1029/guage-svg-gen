#!/usr/bin/env bash
# scripts/install.sh — svg-architect Skill 安装脚本
# 只安装 skills/svg-architect/ 目录内容，不复制 docs/、workspace/ 等

set -e

SKILL_NAME="svg-architect"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$SCRIPT_DIR/../skills/svg-architect"

echo "========================================="
echo " svg-architect Skill 安装向导"
echo "========================================="
echo ""

# ─── 验证 Skill 源目录 ──────────────────────────────────────────────────────
if [ ! -f "$SKILL_SRC/SKILL.md" ]; then
    echo "错误：在 $SKILL_SRC 下找不到 SKILL.md"
    echo "请确保从项目根目录或 scripts/ 目录内执行此脚本"
    exit 1
fi

# ─── 选择安装模式 ────────────────────────────────────────────────────────────
echo "请选择安装模式："
echo "  1) 个人本地模式（默认 workspace: ${SVG_ARCHITECT_WORKSPACE:-$HOME/Documents/workspace/svg-architect}）"
echo "  2) 开源通用模式（自定义 workspace 路径）"
echo ""
read -r MODE_CHOICE

WORKSPACE_PATH=""
case "$MODE_CHOICE" in
    2)
        if [ -n "$SVG_ARCHITECT_WORKSPACE" ]; then
            WORKSPACE_PATH="$SVG_ARCHITECT_WORKSPACE"
            echo "检测到环境变量 SVG_ARCHITECT_WORKSPACE，使用：$WORKSPACE_PATH"
        else
            echo "请输入你的 workspace 路径（或设置环境变量 SVG_ARCHITECT_WORKSPACE 后重新运行）："
            read -r WORKSPACE_PATH
            WORKSPACE_PATH="${WORKSPACE_PATH/#\~/$HOME}"
            if [ -z "$WORKSPACE_PATH" ]; then
                echo "错误：未提供 workspace 路径"
                echo "提示：可在 shell 配置中添加：export SVG_ARCHITECT_WORKSPACE=/your/workspace"
                exit 1
            fi
        fi
        ;;
    *)
        WORKSPACE_PATH="${SVG_ARCHITECT_WORKSPACE:-$HOME/Documents/workspace/svg-architect}"
        echo "个人本地模式，workspace：$WORKSPACE_PATH"
        ;;
esac

echo ""

# ─── 初始化 workspace 目录 ──────────────────────────────────────────────────
echo "正在初始化 workspace 目录..."
mkdir -p "$WORKSPACE_PATH"

echo "  ✓ $WORKSPACE_PATH  已就绪（SVG 输出目录）"
echo ""

# ─── 安装 Python 依赖 ────────────────────────────────────────────────────────
echo "正在检查 Python 依赖..."
if command -v python3 &>/dev/null; then
    echo "  ✓ Python3 已就绪"
    if [ -f "$SKILL_SRC/requirements.txt" ]; then
        echo "  安装依赖（可选，PNG 导出与 QA 预览渲染需要）..."
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
check_tool "cairosvg" "pip install cairosvg（PNG 导出用）"
check_tool "svgo"     "npm install -g svgo（SVG 压缩用）"
echo ""

# ─── 安装 Skill 到工具目录 ──────────────────────────────────────────────────
echo "请选择要安装到哪个工具的 Skills 目录："
echo "  1) Claude Code  (~/.claude/skills/)"
echo "  2) 手动指定路径"
echo "  3) 跳过（仅初始化 workspace）"
echo ""
read -r TOOL_CHOICE

DEST=""
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
    3)
        echo "  跳过 Skill 安装，仅完成 workspace 初始化。"
        ;;
    *)
        echo "  无效选择，跳过 Skill 安装。"
        ;;
esac

if [ -n "$DEST" ] && [ -d "$DEST" ]; then
    echo "检测到已安装的旧版本，是否覆盖？(y/n)"
    read -r OVERWRITE
    if [ "$OVERWRITE" != "y" ]; then
        echo "已取消覆盖，保留旧版本。"
        DEST=""
    fi
fi

if [ -n "$DEST" ]; then
    rsync -a --delete \
        --exclude='.git/' \
        --exclude='.DS_Store' \
        --exclude='scripts/tests/' \
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
echo "  在 Claude Code 中说："
echo "    '帮我做一张公众号封面图，主题是 [xxx]'"
echo "    '画一张 [xxx] 的架构图'"
echo "    '出一张 [xxx] 流程图配图'"
echo ""
