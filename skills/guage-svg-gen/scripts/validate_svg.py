#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Validate structural, security, contrast, font, and accessibility rules on an SVG asset."""
import xml.etree.ElementTree as ET
import json
import os
import argparse
import sys
import re

EPILOG = """Examples:
  python3 scripts/validate_svg.py --svg out.svg --plan out.layout.json --strict --json

Exit codes:
  0  PASS
  1  ERROR (one or more structural/security/contrast/font checks failed)
"""

ERR_CODES = {
    "E_VIEWBOX_MISSING": "缺失 viewBox 属性",
    "E_VIEWBOX_INVALID": "viewBox 格式错误",
    "E_GEOMETRY_OUT_OF_BOUNDS": "坐标超出 viewBox 范围",
    "E_CONTRAST_LOW": "对比度不足 (要求 4.5:1)",
    "E_CONTRAST_UNRESOLVED": "关键文本颜色无法解析，对比度未知",
    "E_CONTRAST_GRADIENT_TEXT": "strict 模式下文字 fill 为渐变/pattern，对比度无法验证",
    "E_SECURITY_TAG": "检测到危险标签 (script/foreignobject/iframe/use)",
    "E_SECURITY_STYLE_CONTENT": "检测到危险的样式内容 (@import/外部url/data/js)",
    "E_SECURITY_EXTERNAL": "检测到非法外链或脚本协议",
    "E_A11Y_MISSING": "缺少 title 或 desc 标签",
    "E_ID_PREFIX_MISSING": "id 属性未使用规定前缀",
    "E_FONT_FAMILY_MISSING": "文本元素缺少 font-family（含祖先继承）",
    "E_FONT_FALLBACK_MISSING": "font-family 缺少 sans-serif 或 monospace fallback",
    "E_FONT_FAMILY_QUOTED": "font-family 含单引号或双引号（cairosvg 跨平台解析易失效，须去引号）",
    "E_FONT_SYSTEM_UI": "font-family 含 system-ui/-apple-system（禁止使用，请使用明确系统字体栈）",
    "E_FONT_EXTERNAL": "检测到 @font-face 或外部字体 url",
    "E_FONT_SIZE_TOO_SMALL": "文字字号低于平台 Caption 下限",
    "E_XML_PARSE_FAIL": "XML 解析失败",
    "E_VALIDATOR_CRASH": "校验器运行时异常",
}

SVG_NS = "http://www.w3.org/2000/svg"

def log_stderr(msg):
    print(msg, file=sys.stderr)

def parse_length(length_str, viewBox_size=1000):
    if not length_str:
        return 0
    length_str = str(length_str).strip().lower()
    if length_str.endswith('%'):
        try:
            return (float(length_str[:-1]) / 100.0) * viewBox_size
        except:
            return 0
    if length_str.endswith('px'):
        try:
            return float(length_str[:-2])
        except:
            return 0
    try:
        return float(re.sub(r'[a-z%]+', '', length_str))
    except:
        return 0

_CSS_NAMED_COLORS = {
    'black': '000000', 'white': 'ffffff', 'red': 'ff0000', 'green': '008000',
    'blue': '0000ff', 'yellow': 'ffff00', 'cyan': '00ffff', 'magenta': 'ff00ff',
    'orange': 'ffa500', 'purple': '800080', 'pink': 'ffc0cb', 'gray': '808080',
    'grey': '808080', 'silver': 'c0c0c0', 'navy': '000080', 'teal': '008080',
    'maroon': '800000', 'olive': '808000', 'lime': '00ff00', 'aqua': '00ffff',
    'fuchsia': 'ff00ff', 'coral': 'ff7f50', 'salmon': 'fa8072', 'gold': 'ffd700',
    'indigo': '4b0082', 'violet': 'ee82ee', 'brown': 'a52a2a', 'crimson': 'dc143c',
    'darkblue': '00008b', 'darkgray': 'a9a9a9', 'darkgreen': '006400',
    'lightblue': 'add8e6', 'lightgray': 'd3d3d3', 'lightyellow': 'ffffe0',
    'whitesmoke': 'f5f5f5', 'ghostwhite': 'f8f8ff',
}

def parse_color_with_alpha(color_str):
    """Parse hex, CSS named color, rgb(), or rgba() into (rrggbb, alpha)."""
    if not color_str or color_str.strip().lower() in ('none', 'transparent'):
        return None, 0.0
    s = color_str.strip().lower()
    if s in _CSS_NAMED_COLORS:
        return _CSS_NAMED_COLORS[s], 1.0
    if s.startswith('#'):
        c = s.lstrip('#')
        if len(c) == 3:
            c = ''.join([ch * 2 for ch in c])
            return c, 1.0
        if len(c) == 6:
            return c, 1.0
        if len(c) == 8:
            return c[:6], int(c[6:8], 16) / 255.0
        return None, 1.0
    if s.startswith('rgb'):
        nums = re.findall(r'[-+]?(?:\d*\.\d+|\d+)', s)
        if len(nums) >= 3:
            r = max(0, min(255, int(round(float(nums[0])))))
            g = max(0, min(255, int(round(float(nums[1])))))
            b = max(0, min(255, int(round(float(nums[2])))))
            alpha = 1.0
            if len(nums) >= 4:
                alpha = max(0.0, min(1.0, float(nums[3])))
            return '{:02x}{:02x}{:02x}'.format(r, g, b), alpha
        return None, 1.0
    return None, 1.0


def parse_color(color_str):
    hex_val, _ = parse_color_with_alpha(color_str)
    return hex_val


def _blend_hex(fg_hex, alpha, bg_hex):
    if not fg_hex:
        return bg_hex
    if alpha >= 0.999 or not bg_hex:
        return fg_hex
    if alpha <= 0.0:
        return bg_hex
    out = []
    for i in (0, 2, 4):
        fg_c = int(fg_hex[i:i+2], 16)
        bg_c = int(bg_hex[i:i+2], 16)
        val = max(0, min(255, int(round(fg_c * alpha + bg_c * (1.0 - alpha)))))
        out.append(f'{val:02x}')
    return ''.join(out)


def _cumulative_translate(elem, ancestors):
    dx, dy = 0.0, 0.0
    for node in list(ancestors) + [elem]:
        tf = node.attrib.get('transform', '')
        for m in re.finditer(r'translate\(\s*([-+]?(?:\d*\.\d+|\d+))(?:[\s,]+([-+]?(?:\d*\.\d+|\d+)))?\s*\)', tf):
            dx += float(m.group(1))
            dy += float(m.group(2)) if m.group(2) is not None else 0.0
    return dx, dy


def _effective_opacity(elem, ancestors, kind='fill-opacity'):
    op = 1.0
    for node in list(ancestors) + [elem]:
        for attr in ('opacity', kind) if node is elem else ('opacity',):
            val = node.attrib.get(attr) or _get_style_prop(node.attrib.get('style', ''), attr)
            if val is not None:
                try:
                    op *= max(0.0, min(1.0, float(val)))
                except ValueError:
                    pass
    return op


def _collect_gradients(root):
    grads = {}
    for elem in root.iter():
        tag = elem.tag.split('}')[-1].lower()
        if tag in ('lineargradient', 'radialgradient') and elem.attrib.get('id'):
            stops = []
            for child in elem:
                if child.tag.split('}')[-1].lower() == 'stop':
                    sc = child.attrib.get('stop-color') or _get_style_prop(child.attrib.get('style', ''), 'stop-color')
                    so_raw = child.attrib.get('stop-opacity') or _get_style_prop(child.attrib.get('style', ''), 'stop-opacity')
                    sc_hex, sc_alpha = parse_color_with_alpha(sc)
                    if sc_hex:
                        if so_raw is not None:
                            try:
                                sc_alpha *= max(0.0, min(1.0, float(so_raw)))
                            except ValueError:
                                pass
                        stops.append((sc_hex, sc_alpha))
            if stops:
                grads[elem.attrib['id']] = stops
    return grads

def get_luminance(hex_color):
    if not hex_color:
        return 0.5
    try:
        r, g, b = [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
        r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
        g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
        b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    except:
        return 0.5

def check_contrast_ratio(c1_hex, c2_hex):
    if not c1_hex or not c2_hex:
        return None
    l1, l2 = get_luminance(c1_hex), get_luminance(c2_hex)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

def parse_rect(rect_str):
    if not rect_str:
        return None
    parts = re.split(r'[,\s]+', rect_str.strip())
    if len(parts) != 4:
        return None
    try:
        return [float(p) for p in parts]
    except:
        return None

def _get_style_prop(style_str, prop):
    """从 style="..." 字符串中提取属性值。"""
    if not style_str:
        return None
    for part in style_str.split(';'):
        part = part.strip()
        if ':' in part:
            k, _, v = part.partition(':')
            if k.strip().lower() == prop:
                return v.strip()
    return None

def _resolve_attr(elem, attr, ancestors):
    """从元素自身 attr/style 或祖先链查找继承值，返回字符串或 None。"""
    # 自身属性
    val = elem.attrib.get(attr)
    if not val:
        val = _get_style_prop(elem.attrib.get('style', ''), attr)
    if val:
        return val
    # 祖先继承（从近到远）
    for anc in reversed(ancestors):
        val = anc.attrib.get(attr)
        if not val:
            val = _get_style_prop(anc.attrib.get('style', ''), attr)
        if val:
            return val
    return None

_GENERIC_FONT_FAMILIES = frozenset({'sans-serif', 'serif', 'monospace', 'cursive', 'fantasy'})
_BANNED_SYSTEM_FONTS = frozenset({'system-ui', '-apple-system', 'blinkmacsystemfont'})
_FONT_WHITELIST_CACHE = None


def _load_whitelisted_fonts():
    """从 assets/fonts-whitelist.json 加载允许字体家族列表（小写集合）。"""
    global _FONT_WHITELIST_CACHE
    if _FONT_WHITELIST_CACHE is not None:
        return _FONT_WHITELIST_CACHE
    wl_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets",
        "fonts-whitelist.json",
    )
    fonts = set()
    try:
        with open(wl_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            for entry in data:
                fam = (entry.get("family") or "").strip().lower()
                if fam:
                    fonts.add(fam)
    except Exception:
        fonts = set()
    _FONT_WHITELIST_CACHE = fonts
    return fonts


def _has_generic_fallback(font_family_str):
    """检查 font-family 末尾是否包含 sans-serif 或 monospace。"""
    families = [f.strip().strip('"\'').lower() for f in font_family_str.split(',')]
    if not families:
        return False
    last = families[-1]
    return last in _GENERIC_FONT_FAMILIES


def _inspect_font_family(font_family_str, whitelisted_fonts):
    """返回 (quoted, banned_system, unlisted) 列表，校验去引号、禁 system-ui 与字体白名单。"""
    quoted = []
    banned_system = []
    unlisted = []
    for raw in font_family_str.split(','):
        part = raw.strip()
        if not part:
            continue
        if "'" in part or '"' in part:
            quoted.append(part)
        cleaned = part.strip('"\'').strip().lower()
        if not cleaned:
            continue
        if cleaned in _BANNED_SYSTEM_FONTS:
            banned_system.append(cleaned)
        elif cleaned in _GENERIC_FONT_FAMILIES:
            continue
        elif whitelisted_fonts and cleaned not in whitelisted_fonts:
            unlisted.append(part.strip('"\''))
    return quoted, banned_system, unlisted

def _is_gradient_fill(fill_str):
    """检查 fill 是否指向渐变/pattern（url(#...)）。"""
    if not fill_str:
        return False
    return bool(re.match(r'url\s*\(', fill_str.strip().lower()))

def _build_ancestor_map(root):
    """构建每个元素的祖先列表 {id(elem): [anc, ...]}（从根到父）。"""
    parent_map = {}
    for parent in root.iter():
        for child in parent:
            parent_map[id(child)] = parent
    ancestors = {}
    for elem in root.iter():
        chain = []
        cur = elem
        while id(cur) in parent_map:
            cur = parent_map[id(cur)]
            chain.insert(0, cur)
        ancestors[id(elem)] = chain
    return ancestors

WECHAT_COVER_W = 1800
WECHAT_COVER_H = 766
WECHAT_ARTICLE_W = 1200
WECHAT_ARTICLE_MIN_H = 500
WECHAT_ARTICLE_MAX_H = 1200
WECHAT_ARTICLE_DEFAULT_H = 675
CUSTOM_FONT_MIN_FLOOR = 8
CUSTOM_FONT_MAX_FLOOR = 16


def calc_custom_min_font_size(w, h):
    """按 1200×675 基准等比计算自定义画布字号下限（范围 8–16px）。"""
    if not w or not h or w <= 0 or h <= 0:
        return None
    scale = min(float(w) / WECHAT_ARTICLE_W, float(h) / WECHAT_ARTICLE_DEFAULT_H)
    return max(CUSTOM_FONT_MIN_FLOOR, min(CUSTOM_FONT_MAX_FLOOR, round(16.0 * scale)))


def detect_platform(vb_parts):
    """根据 viewBox 自动识别平台，返回 (platform_name, min_font_size)。"""
    if not vb_parts:
        return None, None
    _, _, w, h = vb_parts
    if abs(w - WECHAT_COVER_W) <= 20 and abs(h - WECHAT_COVER_H) <= 20:
        return 'wechat_cover', 18
    if abs(w - WECHAT_ARTICLE_W) <= 20:
        if (WECHAT_ARTICLE_MIN_H - 20) <= h <= (WECHAT_ARTICLE_MAX_H + 20):
            return 'wechat_article', 16
        return None, None
    if w > 0 and h > 0:
        return 'custom', calc_custom_min_font_size(w, h)
    return None, None


def validate_svg(svg_file, layout_plan_file=None, strict=False, id_prefix='svga-', platform='auto'):
    report = {"status": "PASS", "errors": [], "warnings": [], "info": []}
    try:
        tree = ET.parse(svg_file)
        root = tree.getroot()
        vb_raw = root.attrib.get('viewBox', '')
        vb_parts = parse_rect(vb_raw)

        v_w = WECHAT_ARTICLE_W
        v_h = WECHAT_ARTICLE_DEFAULT_H
        if vb_parts:
            v_w = vb_parts[2]
            v_h = vb_parts[3]

        plan = None
        plan_platform = None
        if layout_plan_file and os.path.exists(layout_plan_file):
            with open(layout_plan_file, 'r') as f:
                plan = json.load(f)
            plan_platform = (plan.get('metadata') or {}).get('platform')

        # 确定平台与字号下限
        if platform == 'auto':
            if plan_platform and plan_platform not in ('wechat_cover', 'wechat_article'):
                if vb_parts and v_w > 0 and v_h > 0:
                    detected_platform = 'custom'
                    min_font_size = calc_custom_min_font_size(v_w, v_h)
                else:
                    detected_platform, min_font_size = None, None
            else:
                detected_platform, min_font_size = detect_platform(vb_parts)
        else:
            detected_platform = platform
            if platform == 'wechat_cover':
                min_font_size = 18
            elif platform == 'wechat_article':
                if vb_parts and v_w > 0 and v_h > 0 and abs(v_w - WECHAT_ARTICLE_W) > 20 and abs(v_w - WECHAT_COVER_W) > 20:
                    detected_platform = 'custom'
                    min_font_size = calc_custom_min_font_size(v_w, v_h)
                else:
                    min_font_size = 16
            elif platform == 'custom':
                min_font_size = calc_custom_min_font_size(v_w, v_h) if (vb_parts and v_w > 0 and v_h > 0) else None
            else:
                min_font_size = None

        if detected_platform is None and platform == 'auto':
            report["warnings"].append({"code": "W_PLATFORM_UNKNOWN", "msg": "无法识别平台，跳过字号下限检查"})

        # ── 1. Geometry ──────────────────────────────────────────────────────
        if not vb_raw:
            report["errors"].append({"code": "E_VIEWBOX_MISSING", "msg": ERR_CODES["E_VIEWBOX_MISSING"]})
        elif not vb_parts:
            report["errors"].append({"code": "E_VIEWBOX_INVALID", "msg": ERR_CODES["E_VIEWBOX_INVALID"]})
        else:
            v_x, v_y, v_w, v_h = vb_parts
            if plan is not None:
                sa = plan['canvas']['safe_area']
                if (sa['x'] < v_x or sa['y'] < v_y
                        or (sa['x'] + sa['width']) > (v_x + v_w)
                        or (sa['y'] + sa['height']) > (v_y + v_h)):
                    report["errors"].append({"code": "E_GEOMETRY_OUT_OF_BOUNDS",
                                             "msg": f"Safe Area {sa} exceeds viewBox"})
                for slot in plan.get('slots', []):
                    r = slot['rect']
                    if (r['x'] < v_x or r['y'] < v_y
                            or (r['x'] + r['w']) > (v_x + v_w)
                            or (r['y'] + r['h']) > (v_y + v_h)):
                        report["errors"].append({"code": "E_GEOMETRY_OUT_OF_BOUNDS",
                                                 "msg": f"Slot {slot['slot_id']} exceeds viewBox"})

        # ── 2. Security ───────────────────────────────────────────────────────
        for elem in root.iter():
            tag = elem.tag.split('}')[-1].lower()
            if tag in ('script', 'foreignobject', 'iframe'):
                report["errors"].append({"code": "E_SECURITY_TAG",
                                         "msg": f"Dangerous tag <{tag}> detected."})

            if tag == 'use':
                href = elem.attrib.get('href',
                       elem.attrib.get('{http://www.w3.org/1999/xlink}href', ''))
                if href and not href.startswith('#'):
                    report["errors"].append({"code": "E_SECURITY_EXTERNAL",
                                             "msg": f"External use href detected: {href}"})

            style_text = elem.text if tag == 'style' else elem.attrib.get('style', '')
            if style_text:
                # 外部字体 @font-face
                if re.search(r'@font-face', style_text, re.I):
                    report["errors"].append({"code": "E_FONT_EXTERNAL",
                                             "msg": ERR_CODES["E_FONT_EXTERNAL"]})
                if re.search(r'url\(\s*[\'"]?(?!#)', style_text, re.I) or \
                        any(p in style_text.lower() for p in ['@import', 'data:', 'javascript:']):
                    report["errors"].append({"code": "E_SECURITY_STYLE_CONTENT",
                                             "msg": ERR_CODES["E_SECURITY_STYLE_CONTENT"]})

            for attr, value in elem.attrib.items():
                if (any(p in value.lower() for p in ['http:', 'https:', 'data:', 'javascript:'])
                        and not value.strip().startswith('#')):
                    report["errors"].append({"code": "E_SECURITY_EXTERNAL",
                                             "msg": f"Unsafe value in {attr}: {value}"})

        # ── 3. ID 前缀检查 ────────────────────────────────────────────────────
        if id_prefix:
            all_ids = set()
            for elem in root.iter():
                eid = elem.attrib.get('id')
                if eid is None:
                    continue
                # SVG 根节点允许无前缀
                if elem is root:
                    continue
                all_ids.add(eid)
                if not eid.startswith(id_prefix):
                    report["errors"].append({
                        "code": "E_ID_PREFIX_MISSING",
                        "msg": f"id=\"{eid}\" 未使用前缀 \"{id_prefix}\"",
                    })

            # 引用一致性警告（不存在的 id）
            for elem in root.iter():
                for attr in ('href', '{http://www.w3.org/1999/xlink}href'):
                    ref = elem.attrib.get(attr, '')
                    if ref.startswith('#'):
                        target = ref[1:]
                        if target not in all_ids and target != root.attrib.get('id', ''):
                            report["warnings"].append({
                                "code": "W_ID_REF_MISSING",
                                "msg": f"{attr}=\"{ref}\" 引用的 id 不存在",
                            })
                for attr in ('fill', 'stroke', 'marker-end', 'marker-start', 'marker-mid', 'filter', 'clip-path', 'mask'):
                    val = elem.attrib.get(attr, '')
                    for m in re.finditer(r'url\(#([^)]+)\)', val):
                        target = m.group(1)
                        if target not in all_ids and target != root.attrib.get('id', ''):
                            report["warnings"].append({
                                "code": "W_ID_REF_MISSING",
                                "msg": f"{attr}=\"{val}\" 引用的 id 不存在",
                            })

        # ── 4. Contrast ───────────────────────────────────────────────────────
        ancestor_map = _build_ancestor_map(root)
        gradients = _collect_gradients(root)
        draw_order = {id(el): idx for idx, el in enumerate(root.iter())}

        bg_color_hex = "0a0a0b"
        max_area = 0
        rect_layers = []
        for rect in root.iter(f'{{{SVG_NS}}}rect'):
            r_anc = ancestor_map.get(id(rect), [])
            dx, dy = _cumulative_translate(rect, r_anc)
            rx = parse_length(rect.attrib.get('x', '0'), v_w) + dx
            ry = parse_length(rect.attrib.get('y', '0'), v_h) + dy
            w = parse_length(rect.attrib.get('width', '0'), v_w)
            h = parse_length(rect.attrib.get('height', '0'), v_h)
            raw_fill = _resolve_attr(rect, 'fill', r_anc) or '#000000'
            r_op = _effective_opacity(rect, r_anc, 'fill-opacity')
            if r_op <= 0 or raw_fill.strip().lower() in ('none', 'transparent'):
                continue
            grad_match = re.match(r'url\(#([^)]+)\)', raw_fill.strip())
            if grad_match:
                gid = grad_match.group(1)
                if gid in gradients:
                    rect_layers.append((draw_order[id(rect)], (rx, ry, w, h), ('grad', gradients[gid], r_op)))
                continue
            c_hex, c_alpha = parse_color_with_alpha(raw_fill)
            if c_hex:
                total_alpha = c_alpha * r_op
                rect_layers.append((draw_order[id(rect)], (rx, ry, w, h), ('solid', c_hex, total_alpha)))
                if w * h > max_area and total_alpha >= 0.8:
                    max_area = w * h
                    bg_color_hex = c_hex

        def _bg_candidates_for_point(px, py, before_idx):
            candidates = [bg_color_hex]
            for layer_idx, (rx, ry, rw, rh), paint in rect_layers:
                if layer_idx >= before_idx:
                    continue
                if rx <= px <= rx + rw and ry <= py <= ry + rh:
                    kind = paint[0]
                    if kind == 'solid':
                        _, c_hex, alpha = paint
                        candidates = [_blend_hex(c_hex, alpha, bg) for bg in candidates]
                    else:
                        _, stops, r_op = paint
                        new_cands = []
                        for s_hex, s_alpha in stops:
                            for bg in candidates:
                                new_cands.append(_blend_hex(s_hex, s_alpha * r_op, bg))
                        candidates = new_cands or candidates
            # Deduplicate while preserving order
            return list(dict.fromkeys(candidates))

        def _text_label(elem, elem_ancestors):
            tid = elem.attrib.get('data-svga-text')
            if not tid:
                for anc in reversed(elem_ancestors):
                    tid = anc.attrib.get('data-svga-text')
                    if tid:
                        break
            if tid:
                return tid
            snippet = "".join(elem.itertext()).strip()[:20]
            return snippet or elem.tag.split('}')[-1]

        def _check_paint_contrast(elem, elem_ancestors, bg_candidates):
            fill_val = _resolve_attr(elem, 'fill', elem_ancestors) or 'white'
            t_id = _text_label(elem, elem_ancestors)

            if _is_gradient_fill(fill_val):
                if strict:
                    report["errors"].append({
                        "code": "E_CONTRAST_GRADIENT_TEXT",
                        "msg": f"{ERR_CODES['E_CONTRAST_GRADIENT_TEXT']} (text={t_id!r})",
                        "text_id": t_id,
                    })
                else:
                    report["warnings"].append({
                        "code": "W_CONTRAST_GRADIENT_TEXT",
                        "msg": f"文字 fill 为渐变，对比度无法自动验证 (text={t_id!r})",
                        "text_id": t_id,
                    })
                return

            txt_hex, txt_alpha = parse_color_with_alpha(fill_val)
            txt_op = txt_alpha * _effective_opacity(elem, elem_ancestors, 'fill-opacity')
            if not txt_hex:
                if strict:
                    report["errors"].append({"code": "E_CONTRAST_UNRESOLVED",
                                             "msg": f"Text color unresolved for {t_id!r} (fill={fill_val!r}).",
                                             "text_id": t_id})
                else:
                    report["warnings"].append({"code": "W_COLOR_UNRESOLVED",
                                               "msg": f"Text color unresolved for {t_id!r} (fill={fill_val!r}).",
                                               "text_id": t_id})
                return

            ratios = []
            for bg in bg_candidates:
                effective_txt = _blend_hex(txt_hex, txt_op, bg)
                r = check_contrast_ratio(bg, effective_txt)
                if r is not None:
                    ratios.append((r, bg))
            if not ratios:
                if strict:
                    report["errors"].append({"code": "E_CONTRAST_UNRESOLVED",
                                             "msg": f"Text color unresolved for {t_id!r}.",
                                             "text_id": t_id})
                else:
                    report["warnings"].append({"code": "W_COLOR_UNRESOLVED",
                                               "msg": f"Text color unresolved for {t_id!r}.",
                                               "text_id": t_id})
            else:
                min_ratio, worst_bg = min(ratios, key=lambda item: item[0])
                if min_ratio < 4.5:
                    level = "errors" if strict else "warnings"
                    report[level].append({"code": "E_CONTRAST_LOW",
                                          "msg": f"Contrast ratio {min_ratio:.2f}:1 < 4.5:1 for text {t_id!r} on #{worst_bg}.",
                                          "text_id": t_id})

        for text in root.iter(f'{{{SVG_NS}}}text'):
            ancestors = ancestor_map.get(id(text), [])
            dx, dy = _cumulative_translate(text, ancestors)
            tx = parse_length(text.attrib.get('x', '0'), v_w) + dx
            ty = parse_length(text.attrib.get('y', '0'), v_h) + dy
            fs_str = _resolve_attr(text, 'font-size', ancestors)
            fs = parse_length(fs_str) if fs_str else 16.0
            anchor = _resolve_attr(text, 'text-anchor', ancestors) or 'start'
            cx = tx if anchor == 'middle' else (tx - 10.0 if anchor == 'end' else tx + 10.0)
            cy = ty - fs * 0.35
            bg_candidates = _bg_candidates_for_point(cx, cy, draw_order[id(text)])

            non_empty_tspans = [
                ts for ts in text.iter(f'{{{SVG_NS}}}tspan')
                if ts is not text and "".join(ts.itertext()).strip()
            ]
            has_direct_text = bool((text.text or "").strip()) or any(
                bool((c.tail or "").strip()) for c in text
            )
            overridden_tspans = [
                ts for ts in non_empty_tspans
                if any(
                    ts.attrib.get(a) or _get_style_prop(ts.attrib.get('style', ''), a)
                    for a in ('fill', 'fill-opacity', 'opacity')
                )
            ]
            all_covered_by_tspan_fill = (
                not has_direct_text
                and bool(non_empty_tspans)
                and all(
                    ts.attrib.get('fill') or _get_style_prop(ts.attrib.get('style', ''), 'fill')
                    for ts in non_empty_tspans
                )
            )
            if not all_covered_by_tspan_fill:
                _check_paint_contrast(text, ancestors, bg_candidates)
            for ts in overridden_tspans:
                _check_paint_contrast(ts, ancestor_map.get(id(ts), []), bg_candidates)

        # ── 5. A11y ───────────────────────────────────────────────────────────
        has_title = any(c.tag.split('}')[-1].lower() == 'title' for c in root)
        has_desc = any(c.tag.split('}')[-1].lower() == 'desc' for c in root)
        if not (has_title and has_desc):
            report["errors"].append({"code": "E_A11Y_MISSING", "msg": ERR_CODES["E_A11Y_MISSING"]})

        # ── 6. 字体检查 ───────────────────────────────────────────────────────
        text_tags = (f'{{{SVG_NS}}}text', f'{{{SVG_NS}}}tspan')
        whitelisted_fonts = _load_whitelisted_fonts()
        seen_font_issues = set()
        for elem in root.iter():
            if elem.tag not in text_tags:
                continue
            ancestors = ancestor_map.get(id(elem), [])
            t_id = _text_label(elem, ancestors)
            ff = _resolve_attr(elem, 'font-family', ancestors)
            if not ff:
                report["errors"].append({
                    "code": "E_FONT_FAMILY_MISSING",
                    "msg": f"{ERR_CODES['E_FONT_FAMILY_MISSING']} (text={t_id!r})",
                    "text_id": t_id,
                })
                continue
            if not _has_generic_fallback(ff):
                report["errors"].append({
                    "code": "E_FONT_FALLBACK_MISSING",
                    "msg": f"font-family=\"{ff}\" 缺少 sans-serif/monospace fallback (text={t_id!r})",
                    "text_id": t_id,
                })
            has_own_ff = bool(
                elem.attrib.get('font-family')
                or _get_style_prop(elem.attrib.get('style', ''), 'font-family')
            )
            if elem.tag == f'{{{SVG_NS}}}text' or has_own_ff:
                quoted, banned_sys, unlisted = _inspect_font_family(ff, whitelisted_fonts)
                level = "errors" if strict else "warnings"
                if quoted and ("E_FONT_FAMILY_QUOTED", t_id) not in seen_font_issues:
                    seen_font_issues.add(("E_FONT_FAMILY_QUOTED", t_id))
                    report[level].append({
                        "code": "E_FONT_FAMILY_QUOTED",
                        "msg": f"font-family 含引号 {', '.join(quoted)}，cairosvg 易失败 (text={t_id!r})",
                        "text_id": t_id,
                    })
                if banned_sys and ("E_FONT_SYSTEM_UI", t_id) not in seen_font_issues:
                    seen_font_issues.add(("E_FONT_SYSTEM_UI", t_id))
                    report[level].append({
                        "code": "E_FONT_SYSTEM_UI",
                        "msg": f"font-family 含禁用的 {', '.join(banned_sys)}，请改用明确字体栈 (text={t_id!r})",
                        "text_id": t_id,
                    })
                if unlisted and ("W_FONT_UNLISTED", t_id) not in seen_font_issues:
                    seen_font_issues.add(("W_FONT_UNLISTED", t_id))
                    report["warnings"].append({
                        "code": "W_FONT_UNLISTED",
                        "msg": f"字体不在 fonts-whitelist.json 中: {', '.join(unlisted)} (text={t_id!r})",
                        "text_id": t_id,
                    })

        # ── 7. 字号检查 ───────────────────────────────────────────────────────
        if min_font_size is not None:
            for elem in root.iter():
                if elem.tag not in text_tags:
                    continue
                ancestors = ancestor_map.get(id(elem), [])
                t_id = _text_label(elem, ancestors)
                fs_str = _resolve_attr(elem, 'font-size', ancestors)
                if fs_str is None:
                    if strict:
                        report["errors"].append({
                            "code": "E_FONT_SIZE_TOO_SMALL",
                            "msg": f"font-size 无法解析（strict 模式视为违规, text={t_id!r}）",
                            "text_id": t_id,
                        })
                    else:
                        report["warnings"].append({
                            "code": "W_FONT_SIZE_UNRESOLVED",
                            "msg": f"font-size 无法解析 (text={t_id!r})",
                            "text_id": t_id,
                        })
                    continue
                fs = parse_length(fs_str)
                if fs < min_font_size:
                    report["errors"].append({
                        "code": "E_FONT_SIZE_TOO_SMALL",
                        "msg": f"font-size={fs}px 低于平台下限 {min_font_size}px (text={t_id!r})",
                        "text_id": t_id,
                    })

    except ET.ParseError as e:
        report["errors"].append({"code": "E_XML_PARSE_FAIL", "msg": str(e)})
    except Exception as e:
        report["errors"].append({"code": "E_VALIDATOR_CRASH", "msg": str(e)})

    report["status"] = "ERROR" if report["errors"] else "PASS"
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Guage SVG Gen structural, security, contrast, font, and a11y validator.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--svg", required=True, help="SVG 文件路径")
    parser.add_argument("--plan", help="layout_plan.json 路径")
    parser.add_argument("--strict", action="store_true", help="strict 模式（对比度/渐变文字等升为 error）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出报告")
    parser.add_argument("--id-prefix", default="svga-", dest="id_prefix",
                        help="ID 前缀规则（默认 svga-，设为空字符串可跳过检查）")
    parser.add_argument("--platform", default="auto",
                        choices=["auto", "wechat_cover", "wechat_article", "custom"],
                        help="目标平台（auto 时从 viewBox 或 layout.json 自动识别；custom 支持任意 W×H 画布）")
    args = parser.parse_args()

    log_stderr(f"[*] Validating {args.svg}...")
    report = validate_svg(args.svg, args.plan, args.strict, args.id_prefix, args.platform)

    if args.json:
        print(json.dumps(report))
    else:
        print(f"Status: {report['status']}")
        for e in report["errors"]:
            print(f"  [ERR] {e['code']}: {e['msg']}")
        for w in report["warnings"]:
            print(f"  [WRN] {w['code']}: {w['msg']}")

    sys.exit(1 if report["status"] == "ERROR" else 0)


if __name__ == "__main__":
    main()
