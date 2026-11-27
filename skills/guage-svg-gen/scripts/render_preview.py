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
    "custom": {
        "w": None,
        "min_h": 1,
        "max_h": 10000,
        "default_h": 360,
        "note": "Supports any arbitrary user-specified W×H canvas (e.g. 480×300, 600×340, 640×360) inferred from viewBox",
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
        browser = None
        last_err = None
        for channel in (None, "msedge", "chrome"):
            try:
                browser = p.chromium.launch(channel=channel) if channel else p.chromium.launch()
                break
            except Exception as e:
                last_err = e
        if browser is None:
            raise RuntimeError(f"chromium/msedge/chrome launch failed: {last_err}")
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


def _render_cli_rasterizer(svg_path, width, height, scale, out_path):
    import subprocess
    w = max(1, int(width * scale))
    h = max(1, int(height * scale))
    try:
        import resvg_py
        png_bytes = resvg_py.svg_to_bytes(svg_path=str(svg_path), width=w, height=h)
        Path(out_path).write_bytes(png_bytes)
        return "resvg_py"
    except Exception:
        pass
    for tool, build_cmd in (
        ("resvg", lambda exe: [exe, "-w", str(w), "-h", str(h), str(svg_path), str(out_path)]),
        ("resvg-js", lambda exe: [exe, "--fit-to", "width", str(w), str(svg_path), str(out_path)]),
        ("rsvg-convert", lambda exe: [exe, "-w", str(w), "-h", str(h), str(svg_path), "-o", str(out_path)]),
    ):
        exe = shutil.which(tool)
        if exe:
            try:
                subprocess.run(build_cmd(exe), check=True, capture_output=True)
                if Path(out_path).exists():
                    return tool
            except Exception:
                continue
    raise ImportError("resvg / rsvg-convert not found")


def _parse_hex_rgba(color_str, opacity=1.0):
    if not color_str:
        return None
    s = color_str.strip()
    if not s.startswith("#"):
        return None
    if len(s) == 4:
        r, g, b = int(s[1] * 2, 16), int(s[2] * 2, 16), int(s[3] * 2, 16)
    elif len(s) == 7:
        try:
            r, g, b = int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16)
        except ValueError:
            return None
    else:
        return None
    a = max(0, min(255, int(round(255 * max(0.0, min(1.0, float(opacity)))))))
    return (r, g, b, a)


def _sample_path_points(d_str, dx, dy, sx, sy):
    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", d_str or "")
    pts = []
    i = 0
    cmd = None
    cx, cy = 0.0, 0.0
    start = None

    def next_f():
        nonlocal i
        val = float(tokens[i])
        i += 1
        return val

    while i < len(tokens):
        if re.match(r"[A-Za-z]", tokens[i]):
            cmd = tokens[i]
            i += 1
            if cmd in ("Z", "z"):
                if start is not None:
                    pts.append(((start[0] + dx) * sx, (start[1] + dy) * sy))
                    cx, cy = start
                continue
        if not cmd:
            break
        rel = cmd.islower()
        u = cmd.upper()
        try:
            if u in ("M", "L"):
                x, y = next_f(), next_f()
                cx, cy = (cx + x, cy + y) if rel else (x, y)
                if u == "M" and start is None:
                    start = (cx, cy)
                pts.append(((cx + dx) * sx, (cy + dy) * sy))
                if u == "M":
                    cmd = "l" if rel else "L"
            elif u == "H":
                x = next_f()
                cx = cx + x if rel else x
                pts.append(((cx + dx) * sx, (cy + dy) * sy))
            elif u == "V":
                y = next_f()
                cy = cy + y if rel else y
                pts.append(((cx + dx) * sx, (cy + dy) * sy))
            elif u == "C":
                x1, y1, x2, y2, x, y = [next_f() for _ in range(6)]
                if rel:
                    x1, y1, x2, y2, x, y = cx + x1, cy + y1, cx + x2, cy + y2, cx + x, cy + y
                for step in range(1, 9):
                    t = step / 8.0
                    mt = 1.0 - t
                    px = mt**3 * cx + 3 * mt**2 * t * x1 + 3 * mt * t**2 * x2 + t**3 * x
                    py = mt**3 * cy + 3 * mt**2 * t * y1 + 3 * mt * t**2 * y2 + t**3 * y
                    pts.append(((px + dx) * sx, (py + dy) * sy))
                cx, cy = x, y
            elif u == "Q":
                x1, y1, x, y = [next_f() for _ in range(4)]
                if rel:
                    x1, y1, x, y = cx + x1, cy + y1, cx + x, cy + y
                for step in range(1, 9):
                    t = step / 8.0
                    mt = 1.0 - t
                    px = mt**2 * cx + 2 * mt * t * x1 + t**2 * x
                    py = mt**2 * cy + 2 * mt * t * y1 + t**2 * y
                    pts.append(((px + dx) * sx, (py + dy) * sy))
                cx, cy = x, y
            elif u == "A":
                _rx, _ry, _rot, _laf, _sf, x, y = [next_f() for _ in range(7)]
                if rel:
                    x, y = cx + x, cy + y
                mx, my = (cx + x) / 2.0, (cy + y) / 2.0 - max(4.0, abs(_ry) * 0.4)
                for step in range(1, 9):
                    t = step / 8.0
                    mt = 1.0 - t
                    px = mt**2 * cx + 2 * mt * t * mx + t**2 * x
                    py = mt**2 * cy + 2 * mt * t * my + t**2 * y
                    pts.append(((px + dx) * sx, (py + dy) * sy))
                cx, cy = x, y
            else:
                break
        except (IndexError, ValueError):
            break
    return pts


def _render_pillow_svg(svg_path, width, height, scale, out_path):
    """零原生依赖（无需 libcairo / Playwright）的纯 Python + Pillow SVG 预览光栅化兜底后端。"""
    from PIL import Image, ImageDraw
    tree = ET.parse(svg_path)
    root = tree.getroot()
    vb_w, vb_h = parse_viewbox(svg_path)
    out_w = max(1, int(round(width * scale)))
    out_h = max(1, int(round(height * scale)))
    sx = out_w / float(vb_w if (vb_w and vb_w > 0) else width)
    sy = out_h / float(vb_h if (vb_h and vb_h > 0) else height)

    canvas = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")

    def walk(node, dx=0.0, dy=0.0, inh_fill=None):
        tag = node.tag.split("}")[-1].lower()
        if tag in ("defs", "title", "desc", "metadata", "style", "marker", "pattern"):
            return
        tf = node.attrib.get("transform", "")
        for m in re.finditer(r"translate\(\s*([-+]?(?:\d*\.\d+|\d+))(?:[\s,]+([-+]?(?:\d*\.\d+|\d+)))?\s*\)", tf):
            dx += float(m.group(1))
            dy += float(m.group(2)) if m.group(2) is not None else 0.0

        op = float(node.attrib.get("opacity", "1") or 1.0)
        f_op = op * float(node.attrib.get("fill-opacity", "1") or 1.0)
        s_op = op * float(node.attrib.get("stroke-opacity", "1") or 1.0)
        fill_raw = node.attrib.get("fill", inh_fill)
        stroke_raw = node.attrib.get("stroke")
        fill_rgba = _parse_hex_rgba(fill_raw, f_op) if fill_raw not in (None, "none") else None
        stroke_rgba = _parse_hex_rgba(stroke_raw, s_op) if stroke_raw not in (None, "none") else None
        sw = max(1, int(round(float(node.attrib.get("stroke-width", "1") or 1.0) * min(sx, sy))))

        try:
            if tag == "rect":
                x = (float(node.attrib.get("x", "0")) + dx) * sx
                y = (float(node.attrib.get("y", "0")) + dy) * sy
                w = float(node.attrib.get("width", "0")) * sx
                h = float(node.attrib.get("height", "0")) * sy
                rx = float(node.attrib.get("rx", "0") or 0.0) * min(sx, sy)
                if w > 0 and h > 0 and (fill_rgba or stroke_rgba):
                    box = [x, y, x + w, y + h]
                    if rx > 0 and hasattr(draw, "rounded_rectangle"):
                        draw.rounded_rectangle(box, radius=rx, fill=fill_rgba, outline=stroke_rgba, width=sw if stroke_rgba else 0)
                    else:
                        draw.rectangle(box, fill=fill_rgba, outline=stroke_rgba, width=sw if stroke_rgba else 0)
            elif tag == "circle":
                cx = (float(node.attrib.get("cx", "0")) + dx) * sx
                cy = (float(node.attrib.get("cy", "0")) + dy) * sy
                r = float(node.attrib.get("r", "0")) * min(sx, sy)
                if r > 0 and (fill_rgba or stroke_rgba):
                    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill_rgba, outline=stroke_rgba, width=sw if stroke_rgba else 0)
            elif tag == "ellipse":
                cx = (float(node.attrib.get("cx", "0")) + dx) * sx
                cy = (float(node.attrib.get("cy", "0")) + dy) * sy
                rx = float(node.attrib.get("rx", "0")) * sx
                ry = float(node.attrib.get("ry", "0")) * sy
                if rx > 0 and ry > 0 and (fill_rgba or stroke_rgba):
                    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill_rgba, outline=stroke_rgba, width=sw if stroke_rgba else 0)
            elif tag == "line":
                x1 = (float(node.attrib.get("x1", "0")) + dx) * sx
                y1 = (float(node.attrib.get("y1", "0")) + dy) * sy
                x2 = (float(node.attrib.get("x2", "0")) + dx) * sx
                y2 = (float(node.attrib.get("y2", "0")) + dy) * sy
                if stroke_rgba:
                    draw.line([(x1, y1), (x2, y2)], fill=stroke_rgba, width=sw)
            elif tag in ("polyline", "polygon"):
                nums = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+)", node.attrib.get("points", ""))]
                pts = [((nums[k] + dx) * sx, (nums[k + 1] + dy) * sy) for k in range(0, len(nums) - 1, 2)]
                if len(pts) >= 2:
                    if tag == "polygon" and fill_rgba and len(pts) >= 3:
                        draw.polygon(pts, fill=fill_rgba, outline=stroke_rgba)
                    elif stroke_rgba:
                        draw.line(pts, fill=stroke_rgba, width=sw)
            elif tag == "path":
                pts = _sample_path_points(node.attrib.get("d", ""), dx, dy, sx, sy)
                if len(pts) >= 2:
                    if fill_rgba and len(pts) >= 3:
                        draw.polygon(pts, fill=fill_rgba)
                    if stroke_rgba:
                        draw.line(pts, fill=stroke_rgba, width=sw)
            elif tag == "text":
                txt = "".join(node.itertext()).strip()
                t_rgba = fill_rgba or _parse_hex_rgba("#FAFAFA", f_op)
                if txt and t_rgba:
                    tx = (float(node.attrib.get("x", "0")) + dx) * sx
                    ty = (float(node.attrib.get("y", "0")) + dy) * sy
                    fs = max(8.0, float(re.sub(r"[^0-9.]", "", node.attrib.get("font-size", "14")) or 14.0) * min(sx, sy))
                    est_w = len(txt) * fs * 0.75
                    anchor = node.attrib.get("text-anchor", "start")
                    if anchor == "middle":
                        tx -= est_w / 2.0
                    elif anchor == "end":
                        tx -= est_w
                    draw.rectangle([tx, ty - fs * 0.75, tx + max(4.0, est_w), ty - fs * 0.75 + max(3.0, fs * 0.65)], fill=t_rgba)
        except Exception:
            pass

        next_fill = fill_raw if fill_raw is not None else inh_fill
        for child in node:
            walk(child, dx, dy, next_fill)

    walk(root)
    canvas.save(str(out_path), format="PNG")
    return "pillow-svg"


def render_preview(svg_path, width, height, scale, out_path):
    """依次尝试 Playwright → cairosvg → resvg/rsvg-convert → 纯 Pillow 兜底光栅化。返回 backend 名称。"""
    errors = []
    for fn, name in [
        (_render_playwright, "playwright"),
        (_render_cairosvg, "cairosvg"),
        (_render_cli_rasterizer, "resvg/rsvg-convert"),
        (_render_pillow_svg, "pillow-svg"),
    ]:
        try:
            return fn(svg_path, width, height, scale, out_path)
        except ImportError:
            errors.append(f"{name}: not installed")
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise RuntimeError(
        "No rendering backend available. "
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
    """Safely remove a generated QA preview directory (including fallback qa/preview folders without deliverables)."""
    p = Path(target_dir).resolve()
    if not p.exists() or not p.is_dir():
        return False, f"Preview directory does not exist: {p}"
    temp_root = get_default_preview_root().resolve()
    has_report = (p / "visual_report.json").exists()
    has_preview_png = (p / "preview.png").exists() or (p / "thumbnail_crop.png").exists()
    has_deliverables = any(f.suffix.lower() == ".svg" or f.name.endswith(".layout.json") for f in p.iterdir() if f.is_file())
    is_under_temp_root = p != temp_root and temp_root in p.parents
    if not (has_report or is_under_temp_root or (has_preview_png and not has_deliverables)):
        return False, f"Refusing to remove non-preview directory: {p}"
    shutil.rmtree(p)
    return True, f"Removed preview directory: {p}"


EPILOG = """Examples:
  python3 scripts/render_preview.py --svg out.svg --platform wechat_article --strict --json
  python3 scripts/render_preview.py --svg out.svg --platform custom --strict --json
  python3 scripts/render_preview.py --cleanup-dir /tmp/guage-svg-gen-preview/out_abc123 --json

Exit codes:
  0  PASS (or WARN without --strict)
  1  FAIL (or WARN with --strict)
"""


def resolve_auto_platform(vb_w, vb_h):
    """根据 viewBox 自动匹配预览档位，非标准微信画布回退到 custom。"""
    if vb_w is None or vb_h is None or vb_w <= 0 or vb_h <= 0:
        return "custom"
    wc = PLATFORM_SPECS["wechat_cover"]
    if abs(vb_w - wc["w"]) <= 20 and abs(vb_h - wc["default_h"]) <= 20:
        return "wechat_cover"
    wa = PLATFORM_SPECS["wechat_article"]
    if abs(vb_w - wa["w"]) <= 20 and (wa["min_h"] - 20) <= vb_h <= (wa["max_h"] + 20):
        return "wechat_article"
    return "custom"


def main():
    parser = argparse.ArgumentParser(
        description="Guage SVG Gen QA Preview Renderer (isolated temp preview & pixel verification).",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--svg", help="SVG 文件路径（绝对或相对）")
    parser.add_argument(
        "--platform",
        choices=["auto", *PLATFORM_SPECS.keys(), "custom"],
        default="auto",
        help="目标平台（auto 根据 viewBox 识别，custom 支持任意 W×H 画布）",
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

    if not args.svg:
        parser.error("--svg is required unless --cleanup-dir is used")

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

    preview_path = out_dir / "preview.png"
    thumb_path = out_dir / "thumbnail_crop.png"
    report_path = out_dir / "visual_report.json"

    # ── 1. 解析 viewBox ──────────────────────────────────────────────────────
    vb_w, vb_h = parse_viewbox(str(svg_path))
    viewbox_ok = vb_w is not None and vb_w > 0 and vb_h is not None and vb_h > 0
    if args.platform == "auto":
        effective_platform = resolve_auto_platform(vb_w, vb_h)
    elif (
        args.platform == "wechat_article"
        and viewbox_ok
        and abs(vb_w - PLATFORM_SPECS["wechat_article"]["w"]) > 20
        and abs(vb_w - PLATFORM_SPECS["wechat_cover"]["w"]) > 20
    ):
        # 自定义宽度画布（如 640×360、600×340、480×300）即使误传 --platform wechat_article 也自动按 custom 渲染
        effective_platform = "custom"
    else:
        effective_platform = args.platform

    if effective_platform == "custom":
        dimensions_match = viewbox_ok
        expected_w = max(1, int(round(vb_w))) if viewbox_ok else 1200
        expected_h = max(1, int(round(vb_h))) if viewbox_ok else 675
        min_h = max_h = expected_h
        range_note = " (custom viewBox)"
    else:
        spec = PLATFORM_SPECS[effective_platform]
        expected_w = spec["w"]
        min_h, max_h, default_h = spec["min_h"], spec["max_h"], spec["default_h"]
        dimensions_match = (
            viewbox_ok
            and abs(vb_w - expected_w) <= 2
            and (min_h - 2) <= vb_h <= (max_h + 2)
        )
        expected_h = max(1, int(round(vb_h))) if dimensions_match else default_h
        range_note = f" (allowed h={min_h}..{max_h})" if min_h != max_h else ""

    crop_x, crop_y, crop_w, crop_h = expected_w // 4, 0, max(1, expected_w // 2), expected_h

    log_err(f"[*] SVG      : {svg_path}")
    log_err(f"[*] Platform : {effective_platform}  expected={expected_w}×{expected_h}{range_note}")
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
        "platform": effective_platform,
        "requested_platform": args.platform,
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
