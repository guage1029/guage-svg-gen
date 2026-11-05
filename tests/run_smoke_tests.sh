#!/bin/bash

# Guage SVG Gen Smoke Tests v4 (Batch 3: ID/Font/Size/Gradient checks)

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/../skills/guage-svg-gen" && pwd)"
CASES_DIR="$SCRIPT_DIR/cases"

PASS_COUNT=0
FAIL_COUNT=0

# 1. 前置检查
declare -a REQUIRED_CASES=(
    "case_viewbox_missing.svg"
    "case_style_external_url.svg"
    "case_use_local_id.svg"
    "case_contrast_low.svg"
    "case_id_prefix_missing.svg"
    "case_font_family_missing.svg"
    "case_font_fallback_missing.svg"
    "case_font_size_too_small.svg"
    "case_gradient_text_strict.svg"
    "case_valid_prefixed_font.svg"
)
for case in "${REQUIRED_CASES[@]}"; do
    if [ ! -f "$CASES_DIR/$case" ]; then
        echo -e "${RED}[ERROR] Missing: $case${NC}"; exit 1
    fi
done

echo "=== Running functional validation (Standard Interface) ==="

# Helper: 断言 status
run_test() {
    local name=$1
    local file=$2
    local extra=$3
    local expected_status=$4
    echo -n "[Test] $name: "
    local report_status
    report_status=$(python3 "$BASE_DIR/scripts/svg_validator.py" --svg "$CASES_DIR/$file" --json $extra 2>/dev/null \
        | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
    if [ "$report_status" == "$expected_status" ]; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL (Expected $expected_status, got $report_status)${NC}"
        ((FAIL_COUNT++))
    fi
}

# Helper: 断言 status 且 JSON 输出包含指定错误码
expect_error_code() {
    local name=$1
    local file=$2
    local extra=$3
    local expected_code=$4
    echo -n "[Test] $name: "
    local report
    report=$(python3 "$BASE_DIR/scripts/svg_validator.py" --svg "$CASES_DIR/$file" --json $extra 2>/dev/null)
    local status
    status=$(echo "$report" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
    local has_code
    has_code=$(echo "$report" | python3 -c "
import sys, json
data = json.load(sys.stdin)
codes = [e['code'] for e in data.get('errors', [])] + [w['code'] for w in data.get('warnings', [])]
print('YES' if '$expected_code' in codes else 'NO')
" 2>/dev/null)
    if [ "$status" == "ERROR" ] && [ "$has_code" == "YES" ]; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL (status=$status, code_found=$has_code)${NC}"
        ((FAIL_COUNT++))
    fi
}

# ── 原有 6 个测试（保留） ─────────────────────────────────────────────────────
run_test "Missing ViewBox"           "case_viewbox_missing.svg"    ""         "ERROR"
run_test "External Style URL"        "case_style_external_url.svg" ""         "ERROR"
run_test "Local ID Use"              "case_use_local_id.svg"       "--id-prefix=" "PASS"
run_test "Low Contrast Strict"       "case_contrast_low.svg"       "--strict"  "ERROR"

echo -n "[Test] Standard Interface Parsing: "
python3 "$BASE_DIR/scripts/svg_validator.py" --svg "$CASES_DIR/case_use_local_id.svg" --json --id-prefix= \
    | python3 -c "import sys, json; json.load(sys.stdin)" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}PASS (Pure standard parse)${NC}"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL (Standard parse failed)${NC}"
    ((FAIL_COUNT++))
fi

run_test "Valid Prefixed Font (PASS)" "case_valid_prefixed_font.svg" "--strict" "PASS"

# ── 新增 6 个 Batch 3 测试 ────────────────────────────────────────────────────
expect_error_code "ID Prefix Missing"        "case_id_prefix_missing.svg"    ""         "E_ID_PREFIX_MISSING"
expect_error_code "Font Family Missing"      "case_font_family_missing.svg"  ""         "E_FONT_FAMILY_MISSING"
expect_error_code "Font Fallback Missing"    "case_font_fallback_missing.svg" ""        "E_FONT_FALLBACK_MISSING"
expect_error_code "Font Size Too Small"      "case_font_size_too_small.svg"  ""         "E_FONT_SIZE_TOO_SMALL"
expect_error_code "Gradient Text Strict"     "case_gradient_text_strict.svg" "--strict" "E_CONTRAST_GRADIENT_TEXT"

echo -n "[Test] Gradient Text Non-Strict (PASS or WARN only): "
report=$(python3 "$BASE_DIR/scripts/svg_validator.py" --svg "$CASES_DIR/case_gradient_text_strict.svg" --json 2>/dev/null)
status=$(echo "$report" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
if [ "$status" == "PASS" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL (Expected PASS in non-strict, got $status)${NC}"
    ((FAIL_COUNT++))
fi

echo ""
echo "=== Running pipeline end-to-end test ==="

echo -n "[Test] Pipeline E2E (run_pipeline.py): "
TMPDIR_PIPELINE=$(mktemp -d)
pipeline_out=$(python3 "$BASE_DIR/scripts/run_pipeline.py" \
    --svg "$CASES_DIR/case_valid_prefixed_font.svg" \
    --slug smoke-e2e \
    --output-dir "$TMPDIR_PIPELINE" 2>/dev/null)
pipeline_exit=$?
rm -rf "$TMPDIR_PIPELINE"

if [ $pipeline_exit -eq 0 ] && echo "$pipeline_out" | grep -q "svg_abs_path:"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL (exit=$pipeline_exit, output=$(echo "$pipeline_out" | tail -2))${NC}"
    ((FAIL_COUNT++))
fi

echo ""
echo "=== Running render preview smoke test ==="

# Helper: 渲染预览断言 status + 验证落盘文件（eval 协议合规性）
expect_render_status() {
    local name=$1
    local file=$2
    local platform=$3
    local expected_status=$4
    echo -n "[Test] $name: "
    local RTMPD
    RTMPD=$(mktemp -d)
    local report
    report=$(python3 "$BASE_DIR/scripts/render_svg_preview.py" \
        --svg "$CASES_DIR/$file" \
        --platform "$platform" \
        --out-dir "$RTMPD" \
        --json 2>/dev/null)
    local status
    status=$(echo "$report" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null)

    # 正例才验证落盘文件（FAIL 时 preview/thumb 可能不存在属正常）
    local disk_ok=1
    if [ "$expected_status" == "PASS" ] || [ "$expected_status" == "WARN" ]; then
        # visual_report.json 必须存在且可解析
        if [ ! -f "$RTMPD/visual_report.json" ]; then
            disk_ok=0
        else
            python3 -c "import json; json.load(open('$RTMPD/visual_report.json'))" 2>/dev/null || disk_ok=0
        fi
        # preview.png 必须存在
        [ -f "$RTMPD/preview.png" ] || disk_ok=0
        # thumbnail_crop.png 必须存在
        [ -f "$RTMPD/thumbnail_crop.png" ] || disk_ok=0
    fi

    rm -rf "$RTMPD"
    if [ "$status" == "$expected_status" ] && [ "$disk_ok" == "1" ]; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS_COUNT++))
    elif [ "$status" != "$expected_status" ]; then
        echo -e "${RED}FAIL (Expected $expected_status, got $status)${NC}"
        ((FAIL_COUNT++))
    else
        echo -e "${RED}FAIL (status=$status OK, but disk files missing or visual_report.json invalid)${NC}"
        ((FAIL_COUNT++))
    fi
}

# Helper: 渲染预览断言 status 不得为 PASS 且 has_transparent_bg=true + 落盘文件验证
expect_render_transparent() {
    local name=$1
    local file=$2
    local platform=$3
    echo -n "[Test] $name: "
    local RTMPD
    RTMPD=$(mktemp -d)
    local report
    report=$(python3 "$BASE_DIR/scripts/render_svg_preview.py" \
        --svg "$CASES_DIR/$file" \
        --platform "$platform" \
        --out-dir "$RTMPD" \
        --json 2>/dev/null)
    local status
    status=$(echo "$report" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
    local flag
    flag=$(echo "$report" | python3 -c "import sys,json; print(json.load(sys.stdin).get('has_transparent_bg'))" 2>/dev/null)

    # 落盘验证：visual_report.json 可解析，preview.png 存在（WARN 仍应产出文件）
    local disk_ok=1
    if [ ! -f "$RTMPD/visual_report.json" ]; then
        disk_ok=0
    else
        python3 -c "import json; json.load(open('$RTMPD/visual_report.json'))" 2>/dev/null || disk_ok=0
    fi
    [ -f "$RTMPD/preview.png" ] || disk_ok=0

    rm -rf "$RTMPD"
    if [ "$status" != "PASS" ] && [ "$flag" == "True" ] && [ "$disk_ok" == "1" ]; then
        echo -e "${GREEN}PASS (status=$status, has_transparent_bg=True)${NC}"
        ((PASS_COUNT++))
    elif [ "$status" == "PASS" ] || [ "$flag" != "True" ]; then
        echo -e "${RED}FAIL (status=$status, has_transparent_bg=$flag)${NC}"
        ((FAIL_COUNT++))
    else
        echo -e "${RED}FAIL (status/flag OK, but disk files missing or visual_report.json invalid)${NC}"
        ((FAIL_COUNT++))
    fi
}

# 正例：有效 SVG 应 PASS
expect_render_status   "Render Valid (PASS)"             "case_valid_prefixed_font.svg" "wechat_article" "PASS"
# 反例 1：缺 viewBox 应 FAIL
expect_render_status   "Render Missing ViewBox (FAIL)"   "case_viewbox_missing.svg"     "wechat_article" "FAIL"
# 反例 2：尺寸不匹配应 FAIL（1200×500 SVG 按 wechat_cover 平台渲染）
expect_render_status   "Render Dim Mismatch (FAIL)"      "case_valid_prefixed_font.svg" "wechat_cover"   "FAIL"
# 反例 3：透明背景应至少 WARN 且 has_transparent_bg=true
expect_render_transparent "Render Transparent BG (WARN)" "case_transparent_bg.svg"     "wechat_article"

echo ""
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "=== Smoke Tests Completed: $PASS_COUNT/$TOTAL PASS ==="
if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
fi
