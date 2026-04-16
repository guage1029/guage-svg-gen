#!/bin/bash

# SVG Architect Smoke Tests v3 (Fully Standardized)

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

BASE_DIR="/Users/zhaodonglin/Documents/gemini/skills/svg-architect-extension/skills/svg-architect"
CASES_DIR="$BASE_DIR/scripts/tests/cases"

# 1. 前置检查
declare -a REQUIRED_CASES=("case_viewbox_missing.svg" "case_style_external_url.svg" "case_use_local_id.svg" "case_contrast_low.svg")
for case in "${REQUIRED_CASES[@]}"; do
    if [ ! -f "$CASES_DIR/$case" ]; then
        echo -e "${RED}[ERROR] Missing: $case${NC}"; exit 1
    fi
done

echo "=== Running functional validation (Standard Interface) ==="

# 2. 核心校验逻辑：禁止截取，直接 json.loads
run_test() {
    local name=$1
    local file=$2
    local extra=$3
    echo -n "[Test] $name: "
    
    # 直接调用并利用 python 解析 stdout
    local report_status=$(python3 "$BASE_DIR/scripts/svg_validator.py" --svg "$CASES_DIR/$file" --json $extra | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
    
    if [ "$report_status" == "$4" ]; then
        echo -e "${GREEN}PASS${NC}"
    else
        echo -e "${RED}FAIL (Expected $4, got $report_status)${NC}"
    fi
}

run_test "Missing ViewBox" "case_viewbox_missing.svg" "" "ERROR"
run_test "External Style URL" "case_style_external_url.svg" "" "ERROR"
run_test "Local ID Use" "case_use_local_id.svg" "" "PASS"
run_test "Low Contrast Strict" "case_contrast_low.svg" "--strict" "ERROR"

# 3. Test 5: 标准接口健壮性 (无截取解析)
echo -n "[Test] Standard Interface Parsing: "
# 模拟一个合法的标准调用
python3 "$BASE_DIR/scripts/svg_validator.py" --svg "$CASES_DIR/case_use_local_id.svg" --json | python3 -c "import sys, json; json.load(sys.stdin)" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}PASS (Pure standard parse)${NC}"
else
    echo -e "${RED}FAIL (Standard parse failed)${NC}"
fi

echo "=== Smoke Tests Completed ==="
