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
    if python3 -c "import json; json.load(open('$f', encoding='utf-8'))" 2>/dev/null; then
        ok "${f#$REPO_ROOT/}"
    else
        fail "${f#$REPO_ROOT/} — JSONDecodeError"
    fi
}

check_json "$REPO_ROOT/skills/guage-svg-gen/assets/color-tokens.json"
check_json "$REPO_ROOT/skills/guage-svg-gen/assets/fonts-whitelist.json"
check_json "$REPO_ROOT/skills/guage-svg-gen/assets/language-policy.json"
check_json "$REPO_ROOT/skills/guage-svg-gen/assets/layout-plan.schema.json"
check_json "$REPO_ROOT/skills/guage-svg-gen/assets/layout-plan-template.json"
check_json "$REPO_ROOT/skills/guage-svg-gen/assets/layout-plan-light-template.json"
check_json "$REPO_ROOT/skills/guage-svg-gen/evals/evals.json"
check_json "$REPO_ROOT/skills/guage-svg-gen/evals/trigger-queries.json"
check_json "$REPO_ROOT/integrations/gemini/gemini-extension.json"
echo ""

# ─── 2. 无硬编码本机绝对路径与旧仓库 URL ─────────────────────────────────────
echo "[2] 无硬编码本机绝对路径与旧仓库 URL"

HARDCODED=$(grep -rn "/Users/" "$REPO_ROOT" \
    --exclude-dir=.git --exclude-dir=__pycache__ \
    --exclude="check_release.sh" --exclude=".gitignore" 2>/dev/null || true)

if [ -z "$HARDCODED" ]; then
    ok "无 /Users/ 绝对路径"
else
    while IFS= read -r line; do
        fail "$line"
    done <<< "$HARDCODED"
fi

OLD_REPO=$(grep -rn "github.com/guage1029/svg-architect" "$REPO_ROOT" \
    --exclude-dir=.git --exclude-dir=__pycache__ \
    --exclude="check_release.sh" 2>/dev/null || true)

if [ -z "$OLD_REPO" ]; then
    ok "无遗留旧仓库 URL (guage1029/svg-architect)"
else
    while IFS= read -r line; do
        fail "$line"
    done <<< "$OLD_REPO"
fi
echo ""

# ─── 3. 已弃用旧文件不被引用 ──────────────────────────────────────────────────
echo "[3] 已弃用旧文件不被引用"

DEPRECATED_REFS=(
    "svg_validator.py"
    "render_svg_preview.py"
    "style-tech-dark.md"
    "style-minimal-clean.md"
    "style-glass-premium.md"
    "style-neubrutalism.md"
    "style-bento-info.md"
    "style-clay-soft.md"
    "trigger_evals.json"
)

for name in "${DEPRECATED_REFS[@]}"; do
    REFS=$(grep -rln "$name" "$REPO_ROOT" \
        --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=showcase \
        --exclude="check_release.sh" --exclude="test_skill_scripts.py" 2>/dev/null || true)
    if [ -z "$REFS" ]; then
        ok "无引用: $name"
    else
        fail "仍有引用 $name: $REFS"
    fi
done
echo ""

# ─── 4. 关键文件与版本一致性 ─────────────────────────────────────────────────
echo "[4] 关键文件与版本一致性"

REQUIRED=(
    "README.md"
    "scripts/install.sh"
    "skills/guage-svg-gen/SKILL.md"
    "skills/guage-svg-gen/requirements.txt"
    "skills/guage-svg-gen/assets/svg-starter-template.svg"
    "skills/guage-svg-gen/assets/svg-starter-light-template.svg"
    "skills/guage-svg-gen/references/style-bg-dark.md"
    "skills/guage-svg-gen/references/style-bg-light.md"
    "skills/guage-svg-gen/references/error-codes.md"
    "skills/guage-svg-gen/scripts/validate_svg.py"
    "skills/guage-svg-gen/scripts/validate_color.py"
    "skills/guage-svg-gen/scripts/validate_geometry.py"
    "skills/guage-svg-gen/scripts/validate_language.py"
    "skills/guage-svg-gen/scripts/fix_svg.py"
    "skills/guage-svg-gen/scripts/optimize_svg.py"
    "skills/guage-svg-gen/scripts/render_preview.py"
    "skills/guage-svg-gen/scripts/run_pipeline.py"
    "skills/guage-svg-gen/scripts/test_skill_scripts.py"
    "tests/run_smoke_tests.sh"
    "integrations/gemini/gemini-extension.json"
)

for rel in "${REQUIRED[@]}"; do
    if [ -f "$REPO_ROOT/$rel" ]; then
        ok "$rel"
    else
        fail "$rel — 文件不存在"
    fi
done

SKILL_VER=$(python3 -c '
import re, pathlib
txt = pathlib.Path("'"$REPO_ROOT/skills/guage-svg-gen/SKILL.md"'").read_text(encoding="utf-8")
m = re.search(r"version:\s*\"([^\"]+)\"", txt)
print(m.group(1) if m else "")
')
EXT_VER=$(python3 -c '
import json, pathlib
print(json.loads(pathlib.Path("'"$REPO_ROOT/integrations/gemini/gemini-extension.json"'").read_text(encoding="utf-8")).get("version", ""))
')
if [ -n "$SKILL_VER" ] && [ "$SKILL_VER" = "$EXT_VER" ] && grep -q "v$SKILL_VER" "$REPO_ROOT/README.md"; then
    ok "版本一致: $SKILL_VER (SKILL.md / gemini-extension.json / README.md)"
else
    fail "版本不一致: SKILL=$SKILL_VER, gemini-ext=$EXT_VER"
fi
echo ""

# ─── 5. Smoke & Regression Tests ─────────────────────────────────────────────
echo "[5] Smoke & Regression Tests"
SMOKE_OUT=$(bash "$REPO_ROOT/tests/run_smoke_tests.sh" 2>/dev/null) && SMOKE_RC=0 || SMOKE_RC=$?
SMOKE_TAIL=$(echo "$SMOKE_OUT" | tail -1)

if [ "$SMOKE_RC" -eq 0 ] && echo "$SMOKE_TAIL" | grep -q "18/18 PASS"; then
    ok "18/18 PASS (含 17 项冒烟 + 10 项单元测试全绿)"
else
    fail "Smoke tests 未全部通过 (rc=$SMOKE_RC): $SMOKE_TAIL"
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
