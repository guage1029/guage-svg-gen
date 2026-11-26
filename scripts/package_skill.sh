#!/usr/bin/env bash
# scripts/package_skill.sh — 生成纯净开箱即用技能分发包（适配 SkillPay 与本地导入）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_SRC="$REPO_ROOT/skills/guage-svg-gen"
OUT_DIR="${1:-$HOME/Desktop}"

VERSION=$(python3 -c '
import re, pathlib
txt = pathlib.Path("'"$SKILL_SRC/SKILL.md"'").read_text(encoding="utf-8")
m = re.search(r"version:\s*\"([^\"]+)\"", txt)
print(m.group(1) if m else "0.0.0")
')

PKG_DIR="$OUT_DIR/guage-svg-gen"
ZIP_PATH="$OUT_DIR/guage-svg-gen-v${VERSION}.zip"

mkdir -p "$OUT_DIR"
rm -rf "$PKG_DIR" "$ZIP_PATH"
mkdir -p "$PKG_DIR"

# 仅复制运行时必需文件；剔除缓存垃圾与开发期评测/单测冗余项
rsync -a \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='evals/' \
  --exclude='scripts/test_skill_scripts.py' \
  "$SKILL_SRC/" "$PKG_DIR/"

# 清理打包目录内残余隐藏垃圾
find "$PKG_DIR" -name ".DS_Store" -delete -o -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# 打包为标准 ZIP（解压直接得到 guage-svg-gen/SKILL.md）
(
  cd "$OUT_DIR"
  zip -rq "$ZIP_PATH" "guage-svg-gen" -x "*/.DS_Store" "*/__pycache__/*" "*.pyc"
)

# 校验 SkillPay 上传限制与纯洁度
python3 - "$PKG_DIR" "$ZIP_PATH" <<'PYEOF'
import pathlib, sys, zipfile

pkg_dir = pathlib.Path(sys.argv[1])
zip_path = pathlib.Path(sys.argv[2])

files = [p for p in pkg_dir.rglob("*") if p.is_file()]
skill_mds = [p for p in files if p.name == "SKILL.md"]
max_file = max((p.stat().st_size, p) for p in files)
total_dir_bytes = sum(p.stat().st_size for p in files)
zip_bytes = zip_path.stat().st_size

assert len(skill_mds) == 1, f"Expected 1 SKILL.md, got {len(skill_mds)}"
assert max_file[0] <= 512 * 1024, f"File > 512KB: {max_file[1]} ({max_file[0]} bytes)"
assert total_dir_bytes <= 3 * 1024 * 1024, f"Folder > 3MB: {total_dir_bytes} bytes"
assert zip_bytes <= 3 * 1024 * 1024, f"Zip > 3MB: {zip_bytes} bytes"
assert (pkg_dir / "README.md").is_file(), "Missing README.md"
assert (pkg_dir / "requirements.txt").is_file(), "Missing requirements.txt"

with zipfile.ZipFile(zip_path) as zf:
    bad = [n for n in zf.namelist() if "__pycache__" in n or n.endswith(".pyc") or n.endswith(".DS_Store") or "/evals/" in n]
    assert not bad, f"Unwanted entries in zip: {bad}"

print(f"FOLDER : {pkg_dir}")
print(f"ZIP    : {zip_path}")
print(f"FILES  : {len(files)} files (SKILL.md count={len(skill_mds)})")
print(f"MAX    : {max_file[0] / 1024:.1f} KB ({max_file[1].relative_to(pkg_dir)}) <= 512 KB")
print(f"TOTAL  : folder={total_dir_bytes / 1024:.1f} KB, zip={zip_bytes / 1024:.1f} KB <= 3072 KB")
PYEOF
