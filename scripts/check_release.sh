#!/usr/bin/env bash
# scripts/check_release.sh — guage-svg-gen 发布自检
# 在每次 release commit 前运行，确保仓库符合公开发布标准

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

ok()   { echo -e "  ${GREEN}PASS${NC}  $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}FAIL${NC}  $1"; FAIL=$((FAIL+1)); }
warn() { echo -e "  ${YELLOW}WARN${NC}  $1"; }

echo "========================================="
echo " guage-svg-gen Release Check"
echo "========================================="
echo ""

# ─── 1. JSON 合法性 ──────────────────────────────────────────────────────────
echo "[1] JSON 合法性"

check_json() {
    local f="$1"
    if [ ! -f "$f" ]; then
        fail "文件不存在: ${f#$REPO_ROOT/}"
        return
    fi
    if python3 -c "import json; json.load(open('$f'))" 2>/dev/null; then
        ok "${f#$REPO_ROOT/}"
    else
        fail "${f#$REPO_ROOT/} — JSONDecodeError"
    fi
}

check_json "$REPO_ROOT/evals/trigger_evals.json"
check_json "$REPO_ROOT/evals/negative_evals.json"
check_json "$REPO_ROOT/evals/style_coverage_evals.json"
check_json "$REPO_ROOT/evals/output_quality_evals.json"
check_json "$REPO_ROOT/integrations/gemini/gemini-extension.json"
echo ""

# ─── 2. 无硬编码本机绝对路径 ────────────────────────────────────────────────
echo "[2] 无硬编码本机绝对路径（/Users/<name>）"

HARDCODED=$(git -C "$REPO_ROOT" grep -rn "/Users/" \
    -- ':!*.gitignore' ':!scripts/check_release.sh' 2>/dev/null || true)

if [ -z "$HARDCODED" ]; then
    ok "无 /Users/ 绝对路径"
else
    echo "$HARDCODED" | while IFS= read -r line; do
        fail "$line"
    done
fi
echo ""

# ─── 3. 已删除文件不被引用 ──────────────────────────────────────────────────
echo "[3] 已删除文件不被引用"

DELETED_REFS=(
    "legacy_evals.json"
    "agent-skills-protocol-reference.md"
    "case_nested_json_report.txt"
    "article_cover_tech.svg"
    "setup_doctor.py"
)

for name in "${DELETED_REFS[@]}"; do
    REFS=$(git -C "$REPO_ROOT" grep -rln "$name" \
        -- ':!scripts/check_release.sh' 2>/dev/null || true)
    if [ -z "$REFS" ]; then
        ok "无引用: $name"
    else
        fail "仍有引用 $name: $REFS"
    fi
done
echo ""

# ─── 4. 关键文件存在 ─────────────────────────────────────────────────────────
echo "[4] 关键文件存在"

REQUIRED=(
    "skills/guage-svg-gen/SKILL.md"
    "skills/guage-svg-gen/references/fonts_whitelist.json"
    "skills/guage-svg-gen/references/quality_checklist.md"
    "skills/guage-svg-gen/scripts/svg_validator.py"
    "skills/guage-svg-gen/scripts/render_svg_preview.py"
    "tests/run_smoke_tests.sh"
    "integrations/gemini/gemini-extension.json"
    "evals/eval_protocol.md"
)

for rel in "${REQUIRED[@]}"; do
    if [ -f "$REPO_ROOT/$rel" ]; then
        ok "$rel"
    else
        fail "$rel — 文件不存在"
    fi
done
echo ""

# ─── 5. Smoke Tests ─────────────────────────────────────────────────────────
echo "[5] Smoke Tests"
SMOKE_RESULT=$(bash "$REPO_ROOT/tests/run_smoke_tests.sh" 2>/dev/null | tail -1)

if echo "$SMOKE_RESULT" | grep -q "17/17 PASS"; then
    ok "17/17 PASS"
else
    fail "Smoke tests 未全部通过: $SMOKE_RESULT"
fi
echo ""

# ─── 汇总 ────────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo "========================================="
echo " Release Check: $PASS/$TOTAL PASS"
echo "========================================="

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}发布前请修复以上 FAIL 项。${NC}"
    exit 1
else
    echo -e "${GREEN}所有检查通过，可以发布。${NC}"
    exit 0
fi
