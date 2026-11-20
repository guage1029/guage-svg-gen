#!/usr/bin/env bash
# Smoke & unit regression tests for guage-svg-gen

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/../skills/guage-svg-gen" && pwd)"
CASES_DIR="$SCRIPT_DIR/cases"

PASS_COUNT=0
FAIL_COUNT=0

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
    "case_transparent_bg.svg"
)
for case_file in "${REQUIRED_CASES[@]}"; do
    if [ ! -f "$CASES_DIR/$case_file" ]; then
        echo -e "${RED}[ERROR] Missing: $case_file${NC}"; exit 1
    fi
done

echo "=== Running functional validation (validate_svg.py) ==="

run_test() {
    local name=$1
    local file=$2
    local extra=$3
    local expected_status=$4
    echo -n "[Test] $name: "
    local report_status
    report_status=$(python3 -B "$BASE_DIR/scripts/validate_svg.py" --svg "$CASES_DIR/$file" --json $extra 2>/dev/null \
        | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
    if [ "$report_status" == "$expected_status" ]; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL (Expected $expected_status, got $report_status)${NC}"
        ((FAIL_COUNT++))
    fi
}

expect_error_code() {
    local name=$1
    local file=$2
    local extra=$3
    local expected_code=$4
    echo -n "[Test] $name: "
    local report
    report=$(python3 -B "$BASE_DIR/scripts/validate_svg.py" --svg "$CASES_DIR/$file" --json $extra 2>/dev/null)
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

run_test "Missing ViewBox"           "case_viewbox_missing.svg"    ""         "ERROR"
run_test "External Style URL"        "case_style_external_url.svg" ""         "ERROR"
run_test "Local ID Use"              "case_use_local_id.svg"       "--id-prefix=" "PASS"
run_test "Low Contrast Strict"       "case_contrast_low.svg"       "--strict"  "ERROR"

echo -n "[Test] Standard Interface Parsing: "
python3 -B "$BASE_DIR/scripts/validate_svg.py" --svg "$CASES_DIR/case_use_local_id.svg" --json --id-prefix= \
    | python3 -c "import sys, json; json.load(sys.stdin)" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}PASS (Pure standard parse)${NC}"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL (Standard parse failed)${NC}"
    ((FAIL_COUNT++))
fi

run_test "Valid Prefixed Font (PASS)" "case_valid_prefixed_font.svg" "--strict" "PASS"

expect_error_code "ID Prefix Missing"        "case_id_prefix_missing.svg"    ""         "E_ID_PREFIX_MISSING"
expect_error_code "Font Family Missing"      "case_font_family_missing.svg"  ""         "E_FONT_FAMILY_MISSING"
expect_error_code "Font Fallback Missing"    "case_font_fallback_missing.svg" ""        "E_FONT_FALLBACK_MISSING"
expect_error_code "Font Size Too Small"      "case_font_size_too_small.svg"  ""         "E_FONT_SIZE_TOO_SMALL"
expect_error_code "Gradient Text Strict"     "case_gradient_text_strict.svg" "--strict" "E_CONTRAST_GRADIENT_TEXT"

echo -n "[Test] Gradient Text Non-Strict (PASS or WARN only): "
report=$(python3 -B "$BASE_DIR/scripts/validate_svg.py" --svg "$CASES_DIR/case_gradient_text_strict.svg" --json 2>/dev/null)
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
pipeline_out=$(python3 -B "$BASE_DIR/scripts/run_pipeline.py" \
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
echo "=== Running render preview smoke test (render_preview.py) ==="

expect_render_status() {
    local name=$1
    local file=$2
    local platform=$3
    local expected_status=$4
    echo -n "[Test] $name: "
    local RTMPD
    RTMPD=$(mktemp -d)
    local report
    report=$(python3 -B "$BASE_DIR/scripts/render_preview.py" \
        --svg "$CASES_DIR/$file" \
        --platform "$platform" \
        --out-dir "$RTMPD" \
        --json 2>/dev/null)
    local status
    status=$(echo "$report" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null)

    local disk_ok=1
    if [ "$expected_status" == "PASS" ] || [ "$expected_status" == "WARN" ]; then
        if [ ! -f "$RTMPD/visual_report.json" ]; then
            disk_ok=0
        else
            python3 -c "import json; json.load(open('$RTMPD/visual_report.json'))" 2>/dev/null || disk_ok=0
        fi
        [ -f "$RTMPD/preview.png" ] || disk_ok=0
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

expect_render_transparent() {
    local name=$1
    local file=$2
    local platform=$3
    echo -n "[Test] $name: "
    local RTMPD
    RTMPD=$(mktemp -d)
    local report
    report=$(python3 -B "$BASE_DIR/scripts/render_preview.py" \
        --svg "$CASES_DIR/$file" \
        --platform "$platform" \
        --out-dir "$RTMPD" \
        --json 2>/dev/null)
    local status
    status=$(echo "$report" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
    local flag
    flag=$(echo "$report" | python3 -c "import sys,json; print(json.load(sys.stdin).get('has_transparent_bg'))" 2>/dev/null)

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

expect_render_status      "Render Valid (PASS)"           "case_valid_prefixed_font.svg" "wechat_article" "PASS"
expect_render_status      "Render Missing ViewBox (FAIL)" "case_viewbox_missing.svg"     "wechat_article" "FAIL"
expect_render_status      "Render Dim Mismatch (FAIL)"    "case_valid_prefixed_font.svg" "wechat_cover"   "FAIL"
expect_render_transparent "Render Transparent BG (WARN)"  "case_transparent_bg.svg"      "wechat_article"

echo ""
echo "=== Running skill unit regression suite (test_skill_scripts.py) ==="
echo -n "[Test] Skill Full Regression (test_skill_scripts.py): "
if python3 -B "$BASE_DIR/scripts/test_skill_scripts.py" >/tmp/guage_svg_unit.log 2>&1; then
    echo -e "${GREEN}PASS${NC}"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}"
    cat /tmp/guage_svg_unit.log
    ((FAIL_COUNT++))
fi
rm -f /tmp/guage_svg_unit.log

echo ""
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "=== Smoke Tests Completed: $PASS_COUNT/$TOTAL PASS ==="
if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
fi
