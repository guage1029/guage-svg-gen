#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pillow>=10.0.0",
#   "cairosvg>=2.7.1",
# ]
# ///
"""
render_preview.py — QA 预览渲染器

将 SVG 渲染为 preview.png + thumbnail_crop.png，并输出 visual_report.json。
Primary backend : Playwright / Chromium（omit_background=True，保留真实透明度）
Fallback backend: cairosvg（需 libcairo 本地库）
图像分析      : Pillow + numpy（可选；缺失时使用纯 Pillow 全通道分析）

状态语义
  FAIL : 渲染失败 / viewbox_ok=false / dimensions_match=false / is_blank=true / 必要文件缺失
  WARN : 透明背景 / 核心区像素占比过低 / 裁切失败 / 分析不完整 / cairosvg 渲染退化隐患
  PASS : 无 blocking issue，关键输出完整
退出码
  1 : status=FAIL，或 status=WARN 且 --strict 开启
  0 : status=PASS 或 status=WARN（非 strict）
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

PLATFORM_SPECS = {
    "wechat_cover": {
        "w": 1800,
        "min_h": 766,
        "max_h": 766,
        "default_h": 766,
    },
    "wechat_article": {
        "w": 1200,
        "min_h": 500,
        "max_h": 1200,
        "default_h": 675,
    },
}


def log_err(msg):
    print(msg, file=sys.stderr)


# ── ViewBox 解析 ──────────────────────────────────────────────────────────────

def parse_viewbox(svg_path):
    """返回 (w, h) 或 (None, None)。"""
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
        vb = root.attrib.get("viewBox", "")
        parts = re.split(r"[,\s]+", vb.strip())
        if len(parts) == 4:
            return float(parts[2]), float(parts[3])
    except Exception:
        pass
    return None, None


# ── 渲染后端 ──────────────────────────────────────────────────────────────────

def _render_playwright(svg_path, width, height, scale, out_path):
    from playwright.sync_api import sync_playwright
    w = max(1, int(width * scale))
    h = max(1, int(height * scale))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        page.goto(f"file://{os.path.abspath(svg_path)}")
        page.wait_for_load_state("networkidle")
        # omit_background=True：保留真实透明区域，不合成白色底
        page.screenshot(path=str(out_path), full_page=False, omit_background=True)
        browser.close()
    return "chromium"


def _render_cairosvg(svg_path, width, height, scale, out_path):
    import cairosvg
    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(out_path),
        output_width=int(width * scale),
        output_height=int(height * scale),
    )
    return "cairosvg"


def render_preview(svg_path, width, height, scale, out_path):
    """尝试 Playwright，失败则 cairosvg。返回 backend 名称。"""
    errors = []
    for fn, name in [(_render_playwright, "playwright"), (_render_cairosvg, "cairosvg")]:
        try:
            return fn(svg_path, width, height, scale, out_path)
        except ImportError:
            errors.append(f"{name}: not installed")
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise RuntimeError(
        "No rendering backend available. "
        "Install playwright (then `playwright install chromium`) or cairosvg. "
        f"Details: {'; '.join(errors)}"
    )


# ── 裁切缩略图 ─────────────────────────────────────────────────────────────────

def crop_thumbnail(src_path, dst_path, crop_x, crop_y, crop_w, crop_h, scale):
    from PIL import Image
    img = Image.open(src_path)
    x1 = int(crop_x * scale)
    y1 = int(crop_y * scale)
    x2 = min(int((crop_x + crop_w) * scale), img.width)
    y2 = min(int((crop_y + crop_h) * scale), img.height)
    cropped = img.crop((x1, y1, x2, y2))
    cropped.save(dst_path)


# ── 图像分析 ──────────────────────────────────────────────────────────────────

def analyze_image(img_path, crop_x, crop_y, crop_w, crop_h, scale):
    """
    返回 {is_blank, has_transparent_bg, core_region_pixel_ratio}。
    依赖 Pillow（必须）和 numpy（可选）。
    """
    result: dict = {
        "is_blank": None,
        "has_transparent_bg": None,
        "core_region_pixel_ratio": None,
    }
    try:
        from PIL import Image
        img = Image.open(img_path).convert("RGBA")
        w, h = img.size

        try:
            import numpy as np
            arr = np.array(img)

            # is_blank：无任何不透明像素才视为空白；单色文字不触发（交给 core_region_pixel_ratio 处理）
            opaque_mask = arr[:, :, 3] > 10
            opaque_pixels = arr[opaque_mask, :3]
            if opaque_pixels.size == 0:
                result["is_blank"] = True  # 完全透明，无任何可见内容
            else:
                # 有不透明内容就不算 blank，避免单色文字被误判
                result["is_blank"] = False

            # has_transparent_bg：四角 alpha < 200
            # 使用 omit_background=True 后，无内容区域为真正透明
            corners_alpha = [
                int(arr[0, 0, 3]),
                int(arr[0, -1, 3]),
                int(arr[-1, 0, 3]),
                int(arr[-1, -1, 3]),
            ]
            result["has_transparent_bg"] = any(a < 200 for a in corners_alpha)
            result["corner_alpha_values"] = corners_alpha

            # core_region_pixel_ratio：焦点区内与左上角背景色有明显差异的像素占比
            x1 = min(int(crop_x * scale), w)
            y1 = min(int(crop_y * scale), h)
            x2 = min(int((crop_x + crop_w) * scale), w)
            y2 = min(int((crop_y + crop_h) * scale), h)
            core = arr[y1:y2, x1:x2, :3]
            if core.size > 0:
                # 背景估计：使用四角均值而非单点，更鲁棒
                bg = np.array([
                    arr[0, 0, :3], arr[0, -1, :3],
                    arr[-1, 0, :3], arr[-1, -1, :3],
                ]).mean(axis=0)
                diff = np.abs(core.astype(float) - bg).max(axis=2)
                result["core_region_pixel_ratio"] = round(float((diff > 20).mean()), 3)
            else:
                result["core_region_pixel_ratio"] = 0.0

        except ImportError:
            # numpy 不可用时用纯 Pillow 做等价全通道像素检测
            raw_fn = getattr(img, "get_flattened_data", img.getdata)
            pixels = list(raw_fn())
            opaque = [p[:3] for p in pixels if p[3] > 10]
            if not opaque:
                result["is_blank"] = True
            else:
                ch_spread = max(
                    max(p[c] for p in opaque) - min(p[c] for p in opaque)
                    for c in range(3)
                )
                result["is_blank"] = ch_spread < 5

            corners_rgba = [
                img.getpixel((0, 0)),
                img.getpixel((w - 1, 0)),
                img.getpixel((0, h - 1)),
                img.getpixel((w - 1, h - 1)),
            ]
            corners_alpha = [c[3] for c in corners_rgba]
            result["has_transparent_bg"] = any(a < 200 for a in corners_alpha)
            result["corner_alpha_values"] = [int(a) for a in corners_alpha]

            x1 = min(int(crop_x * scale), w)
            y1 = min(int(crop_y * scale), h)
            x2 = min(int((crop_x + crop_w) * scale), w)
            y2 = min(int((crop_y + crop_h) * scale), h)
            if x2 > x1 and y2 > y1:
                bg_rgb = [sum(c[ch] for c in corners_rgba) / 4.0 for ch in range(3)]
                core_img = img.crop((x1, y1, x2, y2))
                core_pixels = list(getattr(core_img, "get_flattened_data", core_img.getdata)())
                hits = sum(
                    1
                    for p in core_pixels
                    if max(abs(p[ch] - bg_rgb[ch]) for ch in range(3)) > 20
                )
                result["core_region_pixel_ratio"] = round(hits / len(core_pixels), 3) if core_pixels else 0.0
            else:
                result["core_region_pixel_ratio"] = 0.0

    except Exception as e:
        result["analysis_error"] = str(e)
    return result


# ── 主流程 ─────────────────────────────────────────────────────────────────────

def detect_cairosvg_hazards(svg_path):
    """检测在 cairosvg 回退后端下已知会退化或错位的 SVG 结构。"""
    hazards = []
    try:
        root = ET.parse(svg_path).getroot()
    except Exception:
        return hazards
    has_blur = any(el.tag.split("}")[-1].lower() == "fegaussianblur" for el in root.iter())
    uses_filter = any("filter" in el.attrib for el in root.iter())
    if has_blur and uses_filter:
        hazards.append((
            "cairosvg_blur_unsupported",
            "cairosvg 无法正确渲染 feGaussianBlur 滤镜，环境光晕可能退化为硬边图形；建议改用 radialGradient 或安装 playwright",
        ))
    for el in root.iter():
        if el.tag.split("}")[-1].lower() != "text":
            continue
        if el.attrib.get("text-anchor") not in {"middle", "end"}:
            continue
        tspans = [c for c in el if c.tag.split("}")[-1].lower() == "tspan"]
        if not tspans:
            continue
        parts = 1 if (el.text or "").strip() else 0
        for ts in tspans:
            if "".join(ts.itertext()).strip():
                parts += 1
            if (ts.tail or "").strip():
                parts += 1
        if parts >= 2:
            hazards.append((
                "cairosvg_centered_tspan_overlap",
                "cairosvg 下 text-anchor='middle'/'end' 与多个 <tspan> 混用可能导致文字重叠",
            ))
            break
    return hazards


def get_default_preview_root():
    return Path(tempfile.gettempdir()) / "guage-svg-gen-preview"


def cleanup_preview_dir(target_dir):
    """Safely remove a generated QA preview directory."""
    p = Path(target_dir).resolve()
    if not p.exists() or not p.is_dir():
        return False, f"Preview directory does not exist: {p}"
    temp_root = get_default_preview_root().resolve()
    has_report = (p / "visual_report.json").exists()
    is_under_temp_root = p != temp_root and temp_root in p.parents
    if not (has_report or is_under_temp_root):
        return False, f"Refusing to remove non-preview directory: {p}"
    shutil.rmtree(p)
    return True, f"Removed preview directory: {p}"


EPILOG = """Examples:
  python3 scripts/render_preview.py --svg out.svg --platform wechat_article --strict --json
  python3 scripts/render_preview.py --cleanup-dir /tmp/guage-svg-gen-preview/out_abc123 --json

Exit codes:
  0  PASS (or WARN without --strict)
  1  FAIL (or WARN with --strict)
"""


def main():
    parser = argparse.ArgumentParser(
        description="Guage SVG Gen QA Preview Renderer (isolated temp preview & pixel verification).",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--svg", help="SVG 文件路径（绝对或相对）")
    parser.add_argument(
        "--platform",
        choices=list(PLATFORM_SPECS.keys()),
        help="目标平台（决定预期尺寸和缩略图裁切区）",
    )
    parser.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        help="输出目录（省略时默认隔离到系统临时目录 guage-svg-gen-preview）",
    )
    parser.add_argument(
        "--cleanup-dir",
        dest="cleanup_dir",
        default=None,
        help="清理指定的 QA 预览目录（要求目录含 visual_report.json 或位于默认临时根目录下）",
    )
    parser.add_argument("--scale", type=float, default=1.0,
                        help="渲染缩放比（默认 1，不影响 SVG 内容）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出报告到 stdout")
    parser.add_argument("--strict", action="store_true",
                        help="strict 模式：WARN 也视为失败，退出码 1")
    args = parser.parse_args()

    if args.cleanup_dir:
        ok, msg = cleanup_preview_dir(args.cleanup_dir)
        payload = {"status": "PASS" if ok else "FAIL", "message": msg, "cleaned_dir": str(Path(args.cleanup_dir).resolve())}
        print(json.dumps(payload, ensure_ascii=False) if args.json else msg)
        sys.exit(0 if ok else 1)

    if not args.svg or not args.platform:
        parser.error("--svg and --platform are required unless --cleanup-dir is used")

    svg_path = Path(args.svg).resolve()
    if not svg_path.exists():
        log_err(f"[ERROR] SVG not found: {svg_path}")
        sys.exit(1)

    if args.out_dir:
        out_dir = Path(args.out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        is_isolated_temp = False
    else:
        preview_root = get_default_preview_root()
        preview_root.mkdir(parents=True, exist_ok=True)
        out_dir = Path(tempfile.mkdtemp(prefix=f"{svg_path.stem}_", dir=str(preview_root))).resolve()
        is_isolated_temp = True

    spec = PLATFORM_SPECS[args.platform]
    expected_w = spec["w"]
    min_h, max_h, default_h = spec["min_h"], spec["max_h"], spec["default_h"]

    preview_path = out_dir / "preview.png"
    thumb_path = out_dir / "thumbnail_crop.png"
    report_path = out_dir / "visual_report.json"

    # ── 1. 解析 viewBox ──────────────────────────────────────────────────────
    vb_w, vb_h = parse_viewbox(str(svg_path))
    viewbox_ok = vb_w is not None
    dimensions_match = (
        viewbox_ok
        and abs(vb_w - expected_w) <= 2
        and (min_h - 2) <= vb_h <= (max_h + 2)
    )
    expected_h = int(round(vb_h)) if dimensions_match else default_h
    crop_x, crop_y, crop_w, crop_h = expected_w // 4, 0, expected_w // 2, expected_h

    range_note = f" (allowed h={min_h}..{max_h})" if min_h != max_h else ""
    log_err(f"[*] SVG      : {svg_path}")
    log_err(f"[*] Platform : {args.platform}  expected={expected_w}×{expected_h}{range_note}")
    log_err(f"[*] viewBox  : {vb_w}×{vb_h}  match={dimensions_match}")

    # ── 2. 渲染完整预览 ──────────────────────────────────────────────────────
    backend = None
    render_error = None
    try:
        backend = render_preview(
            str(svg_path), expected_w, expected_h, args.scale, preview_path
        )
        log_err(f"[*] preview.png via {backend}: {preview_path}")
    except Exception as e:
        render_error = str(e)
        log_err(f"[ERROR] Render failed: {render_error}")

    # ── 3. 裁切缩略图 ────────────────────────────────────────────────────────
    crop_error = None
    if render_error is None:
        try:
            crop_thumbnail(preview_path, thumb_path, crop_x, crop_y, crop_w, crop_h, args.scale)
            log_err(f"[*] thumbnail_crop.png: {thumb_path}")
        except Exception as e:
            crop_error = str(e)
            log_err(f"[WARN] Crop failed: {crop_error}")

    # ── 4. 图像分析 ──────────────────────────────────────────────────────────
    analysis: dict = {}
    if render_error is None and preview_path.exists():
        analysis = analyze_image(
            str(preview_path), crop_x, crop_y, crop_w, crop_h, args.scale
        )

    # ── 5. 决定状态 ──────────────────────────────────────────────────────────
    # blocking issues → FAIL
    blocking: list[str] = []
    if render_error is not None:
        blocking.append("render_failed")
    if not viewbox_ok:
        blocking.append("viewbox_missing")
    if not dimensions_match:
        blocking.append("dimensions_mismatch")
    if analysis.get("is_blank") is True:
        blocking.append("blank_output")
    if render_error is None and not preview_path.exists():
        blocking.append("preview_missing")

    # non-blocking issues → WARN
    warn_flags: list[str] = []
    if analysis.get("has_transparent_bg") is True:
        warn_flags.append("transparent_background")
    cr = analysis.get("core_region_pixel_ratio")
    if cr is not None and cr < 0.01:
        warn_flags.append("low_core_region_ratio")
    if crop_error:
        warn_flags.append("crop_failed")
    if "analysis_error" in analysis:
        warn_flags.append("analysis_incomplete")
    cairo_hazards = detect_cairosvg_hazards(str(svg_path)) if backend == "cairosvg" else []
    for flag, _ in cairo_hazards:
        warn_flags.append(flag)

    if blocking:
        status = "FAIL"
    elif warn_flags:
        status = "WARN"
    else:
        status = "PASS"

    # ── 6. 生成警告摘要 ──────────────────────────────────────────────────────
    warnings: list[str] = []
    if not viewbox_ok:
        warnings.append(f"viewBox 解析失败，无法验证尺寸")
    elif not dimensions_match:
        exp_desc = f"{expected_w}×{expected_h}" if min_h == max_h else f"{expected_w}×[{min_h}..{max_h}]"
        warnings.append(f"viewBox {vb_w}×{vb_h} ≠ expected {exp_desc}")
    if analysis.get("is_blank"):
        warnings.append("preview 几乎全为纯色，可能是空白输出")
    if analysis.get("has_transparent_bg"):
        warnings.append("背景疑似透明（四角含 alpha < 200），应补全背景 rect")
    if cr is not None and cr < 0.01:
        warnings.append(f"核心区域像素占比 {cr:.1%}，可能核心区几乎空白")
    if crop_error:
        warnings.append(f"缩略图裁切失败: {crop_error}")
    if render_error:
        warnings.append(f"渲染失败: {render_error}")
    for _, msg in cairo_hazards:
        warnings.append(msg)

    # ── 7. 写报告 ────────────────────────────────────────────────────────────
    report = {
        "status": status,
        "blocking_issues": blocking,
        "warn_flags": warn_flags,
        "backend": backend,
        "platform": args.platform,
        "scale": args.scale,
        "svg_path": str(svg_path),
        "preview_dir": str(out_dir),
        "is_isolated_temp": is_isolated_temp,
        "preview_path": str(preview_path) if preview_path.exists() else None,
        "thumbnail_crop_path": str(thumb_path) if thumb_path.exists() else None,
        "viewbox_ok": viewbox_ok,
        "viewbox_size": {"w": vb_w, "h": vb_h},
        "expected_size": (
            {"w": expected_w, "h": expected_h}
            if min_h == max_h
            else {"w": expected_w, "h": expected_h, "h_range": [min_h, max_h]}
        ),
        "dimensions_match": dimensions_match,
        **analysis,
        "warnings": warnings,
    }
    if render_error:
        report["render_error"] = render_error
    if crop_error:
        report["crop_error"] = crop_error

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log_err(f"[*] visual_report.json: {report_path}  status={status}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"Status  : {status}")
        print(f"Backend : {backend}")
        print(f"Preview : {preview_path}")
        print(f"Thumb   : {thumb_path}")
        print(f"Report  : {report_path}")
        for w in warnings:
            print(f"  [{'FAIL' if blocking else 'WARN'}] {w}")

    # 退出码：FAIL=1；WARN+strict=1；其余=0
    if status == "FAIL":
        sys.exit(1)
    if status == "WARN" and args.strict:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
