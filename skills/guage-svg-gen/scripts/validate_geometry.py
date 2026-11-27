#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pillow>=10.0.0",
# ]
# ///
"""Validate semantic SVG layout contracts: nodes, text boxes, ports, icons, and edges."""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import ImageFont

EPILOG = """Examples:
  python3 scripts/validate_geometry.py --svg out.svg --plan out.layout.json --strict --json

Exit codes:
  0  PASS
  1  ERROR (one or more geometry/layout contract violations detected)
"""


NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
TOKEN_RE = re.compile(rf"[A-Za-z]|{NUMBER}")
SVG_NS = "http://www.w3.org/2000/svg"
TOLERANCE = 8.0
ARROW_MAX_SIZE = 10.0
EDGE_MIN_GAP = 10.0
NODE_SIDE_RAIL_MAX_WIDTH = 12.0
NODE_SIDE_RAIL_MIN_HEIGHT_RATIO = 0.85
NODE_EDGE_TOLERANCE = 4.0


def fail(report, code, message):
    report["errors"].append({"code": code, "msg": message})


def warn(report, code, message):
    report["warnings"].append({"code": code, "msg": message})


def _fmt_rect(r):
    return f"({r[0]:.1f}, {r[1]:.1f}, {r[2]:.1f}, {r[3]:.1f})"


def rect(data):
    return (
        float(data["x"]),
        float(data["y"]),
        float(data.get("w", data.get("width"))),
        float(data.get("h", data.get("height"))),
    )


def point(data):
    return float(data["x"]), float(data["y"])


def inset(r, padding):
    x, y, w, h = r
    return x + padding, y + padding, w - 2 * padding, h - 2 * padding


def contains(outer, inner, tolerance=0.0):
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (
        ix >= ox - tolerance
        and iy >= oy - tolerance
        and ix + iw <= ox + ow + tolerance
        and iy + ih <= oy + oh + tolerance
    )


def overlaps(a, b, gap=0.0):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw + gap <= bx
        or bx + bw + gap <= ax
        or ay + ah + gap <= by
        or by + bh + gap <= ay
    )


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def is_cjk(text):
    return any("\u2e80" <= ch <= "\u9fff" for ch in text)


def font_path(family, text):
    families = [f.strip().strip('"\'') for f in (family or "sans-serif").split(",") if f.strip()]
    if is_cjk(text):
        families = ["Heiti SC", "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC", "Microsoft YaHei"] + families
    for name in families:
        try:
            path = subprocess.check_output(
                ["fc-match", "-f", "%{file}", name], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            continue
        if path and os.path.exists(path):
            return path
    return None


def measure_text(text, size, family):
    path = font_path(family, text)
    if path:
        try:
            font = ImageFont.truetype(path, max(1, round(size)))
            if hasattr(font, "getlength"):
                return float(font.getlength(text))
            box = font.getbbox(text)
            return float(box[2] - box[0])
        except OSError:
            pass
    factor = 1.0 if is_cjk(text) else 0.62
    return len(text) * size * factor


def _local_tag(elem):
    return elem.tag.split("}")[-1].lower()


def _build_ancestor_map(root):
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


def _resolve_attr(elem, attr, ancestors, default=None):
    val = elem.attrib.get(attr)
    if val:
        return val
    for anc in reversed(ancestors):
        val = anc.attrib.get(attr)
        if val:
            return val
    return default


def _cumulative_translate(elem, ancestors):
    dx, dy = 0.0, 0.0
    for node in list(ancestors) + [elem]:
        tf = node.attrib.get("transform", "")
        for m in re.finditer(r"translate\(\s*([-+]?(?:\d*\.\d+|\d+))(?:[\s,]+([-+]?(?:\d*\.\d+|\d+)))?\s*\)", tf):
            dx += float(m.group(1))
            dy += float(m.group(2)) if m.group(2) is not None else 0.0
    return dx, dy


def _parse_float(value, default):
    if value is None:
        return default
    match = re.match(r"\s*" + NUMBER, str(value))
    return float(match.group()) if match else default


def _collect_runs(elem, size, family, runs):
    if elem.text:
        runs.append((elem.text, size, family, False))
    for child in elem:
        if _local_tag(child) == "tspan":
            child_size = _parse_float(child.attrib.get("font-size"), size)
            child_family = child.attrib.get("font-family") or family
            new_line = ("x" in child.attrib) or ("y" in child.attrib)
            if child.text:
                runs.append((child.text, child_size, child_family, new_line))
                new_line = False
            for nested in child:
                if _local_tag(nested) == "tspan":
                    _collect_runs(nested, child_size, child_family, runs)
                else:
                    nested_text = "".join(nested.itertext())
                    if nested_text:
                        runs.append((nested_text, child_size, child_family, False))
                if nested.tail:
                    runs.append((nested.tail, child_size, child_family, False))
        else:
            child_text = "".join(child.itertext())
            if child_text:
                runs.append((child_text, size, family, False))
        if child.tail:
            runs.append((child.tail, size, family, False))


def _normalize_runs(raw_runs):
    """Collapse XML formatting whitespace across <text>/<tspan> boundaries."""
    collapsed = []
    for text, size, family, new_line in raw_runs:
        norm = re.sub(r"\s+", " ", text)
        if not norm:
            continue
        if new_line:
            if collapsed and collapsed[-1][0].endswith(" "):
                prev_t, prev_s, prev_f, prev_nl = collapsed[-1]
                collapsed[-1] = (prev_t.rstrip(" "), prev_s, prev_f, prev_nl)
            norm = norm.lstrip(" ")
        elif collapsed and collapsed[-1][0].endswith(" ") and norm.startswith(" "):
            norm = norm.lstrip(" ")
        if norm:
            collapsed.append((norm, size, family, new_line))
    if collapsed:
        t0, s0, f0, nl0 = collapsed[0]
        collapsed[0] = (t0.lstrip(" "), s0, f0, nl0)
        t_last, s_last, f_last, nl_last = collapsed[-1]
        collapsed[-1] = (t_last.rstrip(" "), s_last, f_last, nl_last)
    return [(t, s, f, nl) for t, s, f, nl in collapsed if t]


def has_unsafe_centered_tspans(elem, ancestors=None):
    anchor = _resolve_attr(elem, "text-anchor", ancestors or [], "start")
    if anchor not in {"middle", "end"}:
        return False, anchor
    tspans = [c for c in elem if _local_tag(c) == "tspan"]
    if not tspans:
        return False, anchor
    non_empty_parts = 0
    if (elem.text or "").strip():
        non_empty_parts += 1
    for tspan in tspans:
        if "".join(tspan.itertext()).strip():
            non_empty_parts += 1
        if (tspan.tail or "").strip():
            non_empty_parts += 1
    return non_empty_parts >= 2, anchor


def text_bbox(elem, ancestor_map=None):
    ancestors = ancestor_map.get(id(elem), []) if ancestor_map else []
    base_size = _parse_float(_resolve_attr(elem, "font-size", ancestors), 16.0)
    base_family = _resolve_attr(elem, "font-family", ancestors, "")
    raw_runs = []
    _collect_runs(elem, base_size, base_family, raw_runs)
    runs = _normalize_runs(raw_runs)
    text = "".join(t for t, _, _, _ in runs)
    if not runs:
        width = 0.0
        max_size = base_size
        line_count = 1
    else:
        line_widths = [0.0]
        max_size = max(s for _, s, _, _ in runs)
        for run_text, run_size, run_family, new_line in runs:
            if new_line and line_widths[-1] > 0:
                line_widths.append(0.0)
            line_widths[-1] += measure_text(run_text, run_size, run_family)
        width = max(line_widths)
        line_count = len(line_widths)
    x = _parse_float(elem.attrib.get("x"), 0.0)
    y = _parse_float(elem.attrib.get("y"), 0.0)
    anchor = _resolve_attr(elem, "text-anchor", ancestors, "start")
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    return x, y - max_size * 0.84, width, max_size * 1.18 * line_count, text, max_size


def parse_path_segments(d):
    tokens = TOKEN_RE.findall(d or "")
    i = 0
    cmd = None
    current = (0.0, 0.0)
    start = None
    segments = []

    def next_number():
        nonlocal i
        if i >= len(tokens) or re.match(r"[A-Za-z]", tokens[i]):
            raise ValueError("missing path number")
        value = float(tokens[i])
        i += 1
        return value

    while i < len(tokens):
        if re.match(r"[A-Za-z]", tokens[i]):
            cmd = tokens[i]
            i += 1
            if cmd.upper() == "Z":
                if start is not None:
                    segments.append(("L", current, start))
                    current = start
                continue
        if not cmd:
            raise ValueError("path starts without command")
        upper = cmd.upper()
        relative = cmd.islower()
        try:
            if upper == "M":
                x, y = next_number(), next_number()
                end = (x + current[0], y + current[1]) if relative else (x, y)
                current = end
                if start is None:
                    start = end
                cmd = "l" if relative else "L"
            elif upper == "L":
                x, y = next_number(), next_number()
                end = (x + current[0], y + current[1]) if relative else (x, y)
                segments.append(("L", current, end))
                current = end
            elif upper == "H":
                x = next_number()
                end = (x + current[0], current[1]) if relative else (x, current[1])
                segments.append(("L", current, end))
                current = end
            elif upper == "V":
                y = next_number()
                end = (current[0], y + current[1]) if relative else (current[0], y)
                segments.append(("L", current, end))
                current = end
            elif upper == "C":
                values = [next_number() for _ in range(6)]
                if relative:
                    values = [values[j] + current[j % 2] for j in range(6)]
                c1, c2, end = tuple(values[0:2]), tuple(values[2:4]), tuple(values[4:6])
                segments.append(("C", current, c1, c2, end))
                current = end
            else:
                # Unsupported commands still get a conservative endpoint check.
                values = [next_number(), next_number()]
                end = (values[0] + current[0], values[1] + current[1]) if relative else tuple(values)
                segments.append(("L", current, end))
                current = end
        except ValueError:
            break
    return segments


def sample_segment(segment, count=12):
    if segment[0] == "L":
        return [segment[1], segment[2]]
    _, p0, p1, p2, p3 = segment
    points = []
    for index in range(count + 1):
        t = index / count
        u = 1 - t
        points.append((
            u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
        ))
    return points


def path_vertices(segments):
    if not segments:
        return []
    return [segments[0][1]] + [segment[-1] for segment in segments]


def min_point_distance(left, right):
    if not left or not right:
        return float("inf")
    return min(distance(a, b) for a in left for b in right)


def inside(point_value, r, padding=0.0):
    x, y, w, h = r
    return x + padding < point_value[0] < x + w - padding and y + padding < point_value[1] < y + h - padding


def segment_hits_rect(segment, box):
    if segment[0] != "L":
        return any(inside(p, box) for p in sample_segment(segment, 48))
    a, b = segment[1], segment[-1]
    x, y, w, h = box
    if abs(a[0] - b[0]) < 0.01:
        return x < a[0] < x + w and max(min(a[1], b[1]), y) < min(max(a[1], b[1]), y + h)
    if abs(a[1] - b[1]) < 0.01:
        return y < a[1] < y + h and max(min(a[0], b[0]), x) < min(max(a[0], b[0]), x + w)
    # Clipping against the rectangle handles diagonal segments without sparse point sampling.
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x), (dx, x + w - a[0]), (-dy, a[1] - y), (dy, y + h - a[1])):
        if p == 0:
            if q <= 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
    return t0 < t1


def numeric_attr(elem, name):
    value = elem.attrib.get(name)
    if value is None:
        return None
    match = re.match(r"\s*" + NUMBER, value)
    return float(match.group()) if match else None


def shape_bounds(elem):
    tag = elem.tag.split("}")[-1].lower()
    if tag == "rect":
        x = numeric_attr(elem, "x")
        y = numeric_attr(elem, "y")
        width = numeric_attr(elem, "width")
        height = numeric_attr(elem, "height")
        if None in {x, y, width, height}:
            return None
        return x, y, width, height
    if tag == "circle":
        cx = numeric_attr(elem, "cx")
        cy = numeric_attr(elem, "cy")
        r = numeric_attr(elem, "r")
        if None in {cx, cy, r}:
            return None
        return cx - r, cy - r, 2 * r, 2 * r
    if tag == "ellipse":
        cx = numeric_attr(elem, "cx")
        cy = numeric_attr(elem, "cy")
        rx = numeric_attr(elem, "rx")
        ry = numeric_attr(elem, "ry")
        if None in {cx, cy, rx, ry}:
            return None
        return cx - rx, cy - ry, 2 * rx, 2 * ry
    if tag == "line":
        x1 = numeric_attr(elem, "x1")
        y1 = numeric_attr(elem, "y1")
        x2 = numeric_attr(elem, "x2")
        y2 = numeric_attr(elem, "y2")
        if None in {x1, y1, x2, y2}:
            return None
        return min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)
    if tag == "path":
        segments = parse_path_segments(elem.attrib.get("d", ""))
        points = [point for segment in segments for point in (segment[1], segment[-1])]
        if not points:
            return None
        xs = [item[0] for item in points]
        ys = [item[1] for item in points]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    return None


def collect_icon_boxes(root, ancestor_map):
    """Extract global bounding boxes for elements tagged data-svga-role='icon'."""
    icon_boxes = []
    for elem in root.iter():
        ancestors = ancestor_map.get(id(elem), [])
        in_icon = elem.attrib.get("data-svga-role") == "icon" or any(
            anc.attrib.get("data-svga-role") == "icon" for anc in ancestors
        )
        if not in_icon:
            continue
        bounds = shape_bounds(elem)
        if bounds is None:
            continue
        dx, dy = _cumulative_translate(elem, ancestors)
        bx, by, bw, bh = bounds
        if bw > 0 or bh > 0:
            icon_boxes.append((bx + dx, by + dy, bw, bh))
    return icon_boxes


def validate_node_chrome(root, node_rects, report):
    """Reject decorative full-height side rails inside semantic node groups."""
    svg_nodes = {
        elem.attrib.get("data-svga-node"): elem
        for elem in root.iter()
        if elem.attrib.get("data-svga-node")
    }
    for node_id, (node_x, node_y, node_w, node_h) in node_rects.items():
        node_group = svg_nodes.get(node_id)
        if node_group is None:
            continue
        for elem in node_group.iter():
            bounds = shape_bounds(elem)
            if bounds is None:
                continue
            x, y, width, height = bounds
            full_height = (
                height >= node_h * NODE_SIDE_RAIL_MIN_HEIGHT_RATIO
                and abs(y - node_y) <= NODE_EDGE_TOLERANCE
                and abs((y + height) - (node_y + node_h)) <= NODE_EDGE_TOLERANCE
            )
            at_side = (
                abs(x - node_x) <= NODE_EDGE_TOLERANCE
                or abs((x + width) - (node_x + node_w)) <= NODE_EDGE_TOLERANCE
            )
            if width <= NODE_SIDE_RAIL_MAX_WIDTH and full_height and at_side:
                fail(
                    report,
                    "E_NODE_SIDE_RAIL",
                    f"node {node_id} contains a full-height side rail; use the outer border only",
                )
                break


def validate(svg_path, plan_path, strict=False):
    report = {"status": "PASS", "errors": [], "warnings": [], "info": []}
    try:
        plan = json.loads(Path(plan_path).read_text())
        root = ET.parse(svg_path).getroot()
    except Exception as exc:
        fail(report, "E_GEOMETRY_INPUT", str(exc))
        report["status"] = "ERROR"
        return report

    nodes = {item["id"]: item for item in plan.get("nodes", [])}
    text_boxes = {item["id"]: item for item in plan.get("text_boxes", [])}
    edges_raw = plan.get("edges", [])
    if edges_raw is None:
        edges_raw = []
    edges = {item["id"]: item for item in (edges_raw if isinstance(edges_raw, list) else [])}
    if not nodes or not text_boxes or not isinstance(edges_raw, list):
        fail(report, "E_GEOMETRY_CONTRACT_MISSING", "plan must declare non-empty nodes and text_boxes (edges may be [] or omitted for non-edge charts)")
        report["status"] = "ERROR"
        return report

    zones = {item["id"]: item for item in plan.get("zones", [])}
    zone_rects = {key: rect(value["rect"]) for key, value in zones.items()}
    node_rects = {key: rect(value["rect"]) for key, value in nodes.items()}
    vb_raw = root.attrib.get("viewBox", "")
    vb_parts = [float(p) for p in re.split(r"[,\s]+", vb_raw.strip()) if p] if vb_raw.strip() else []
    vb_w = vb_parts[2] if len(vb_parts) == 4 and vb_parts[2] > 0 else 1200.0
    canvas_scale = min(1.0, max(0.4, vb_w / 1200.0))
    default_edge_gap = max(6.0, min(EDGE_MIN_GAP, round(EDGE_MIN_GAP * canvas_scale, 1)))
    safe_area_data = plan.get("canvas", {}).get("safe_area")
    safe_area = rect(safe_area_data) if safe_area_data else None
    if safe_area is not None:
        for zone_id, zone_rect in zone_rects.items():
            if not contains(safe_area, zone_rect, 1.0):
                fail(report, "E_GEOMETRY_OUT_OF_BOUNDS", f"zone {zone_id} escapes safe_area: zone={_fmt_rect(zone_rect)} vs safe_area={_fmt_rect(safe_area)}")
        for node_id, node_rect in node_rects.items():
            if not contains(safe_area, node_rect, 1.0):
                fail(report, "E_GEOMETRY_OUT_OF_BOUNDS", f"node {node_id} escapes safe_area: node={_fmt_rect(node_rect)} vs safe_area={_fmt_rect(safe_area)}")
        for text_id, spec in text_boxes.items():
            t_rect = rect(spec["rect"])
            if not contains(safe_area, t_rect, 1.0):
                fail(report, "E_GEOMETRY_OUT_OF_BOUNDS", f"text_box {text_id} escapes safe_area: box={_fmt_rect(t_rect)} vs safe_area={_fmt_rect(safe_area)}")

    if zone_rects:
        svg_zones = {elem.attrib.get("data-svga-zone") for elem in root.iter() if elem.attrib.get("data-svga-zone")}
        zone_ancestors = {}
        for z_id, z_spec in zones.items():
            if z_id not in svg_zones:
                fail(report, "E_ZONE_MISSING", f"missing SVG zone: {z_id}")
            anc_set = set()
            cur = z_spec.get("parent_zone")
            while cur:
                if cur in anc_set or cur == z_id:
                    fail(report, "E_ZONE_CONTAINMENT", f"cyclic parent_zone detected at {z_id}")
                    break
                if cur not in zone_rects:
                    fail(report, "E_ZONE_PARENT_MISSING", f"zone {z_id} references missing parent_zone: {cur}")
                    break
                anc_set.add(cur)
                cur = zones[cur].get("parent_zone")
            zone_ancestors[z_id] = anc_set
            p_id = z_spec.get("parent_zone")
            if p_id and p_id in zone_rects:
                parent_inner = inset(zone_rects[p_id], float(zones[p_id].get("padding", 0)))
                if not contains(parent_inner, zone_rects[z_id], 1.0):
                    fail(report, "E_ZONE_CONTAINMENT", f"child zone {z_id} escapes parent_zone {p_id}: child={_fmt_rect(zone_rects[z_id])} vs parent={_fmt_rect(parent_inner)}")
        for z1, zr1 in zone_rects.items():
            for z2, zr2 in zone_rects.items():
                if z1 >= z2:
                    continue
                if z1 in zone_ancestors.get(z2, set()) or z2 in zone_ancestors.get(z1, set()):
                    continue
                if overlaps(zr1, zr2):
                    fail(report, "E_ZONE_OVERLAP", f"sibling zones overlap: {z1} / {z2}")

        owned_node_zones = {}
        for z_id, z_spec in zones.items():
            z_inner = inset(zone_rects[z_id], float(z_spec.get("padding", 0)))
            for n_id in z_spec.get("nodes", []):
                if n_id not in node_rects:
                    fail(report, "E_LAYOUT_CONSTRAINT_NODE_MISSING", f"zone {z_id} references missing node: {n_id}")
                    continue
                owned_node_zones.setdefault(n_id, set()).add(z_id)
                if not contains(z_inner, node_rects[n_id], 1.0):
                    fail(report, "E_ZONE_CONTAINMENT", f"node {n_id} escapes zone {z_id}: node={_fmt_rect(node_rects[n_id])} vs zone_inner={_fmt_rect(z_inner)}")
            label_id = z_spec.get("label")
            if label_id:
                if label_id not in text_boxes:
                    fail(report, "E_TEXT_MISSING", f"zone {z_id} label text_box missing: {label_id}")
                elif not contains(zone_rects[z_id], rect(text_boxes[label_id]["rect"]), 1.0):
                    fail(report, "E_ZONE_CONTAINMENT", f"zone {z_id} label {label_id} escapes zone boundary")

        for n_id, n_rect in node_rects.items():
            allowed_z = owned_node_zones.get(n_id, set())
            expanded_allowed = set(allowed_z)
            for az in allowed_z:
                expanded_allowed.update(zone_ancestors.get(az, set()))
            for z_id, z_rect in zone_rects.items():
                if z_id not in expanded_allowed and overlaps(n_rect, z_rect):
                    fail(report, "E_ZONE_OVERLAP", f"node {n_id} overlaps unowned zone {z_id} (add to zone.nodes or move outside)")

        legend_boxes = []
        for slot in plan.get("slots", []):
            if slot.get("slot_id") == "legend_area":
                legend_boxes.append(("slot:legend_area", rect(slot["rect"])))
        for n_id, n_rect in node_rects.items():
            if "legend" in n_id.split("-"):
                legend_boxes.append((f"node:{n_id}", n_rect))
        for t_id, t_spec in text_boxes.items():
            if t_spec.get("role") == "legend" or "legend" in t_id.split("-"):
                legend_boxes.append((f"text:{t_id}", rect(t_spec["rect"])))
        for l_name, l_rect in legend_boxes:
            for z_id, z_rect in zone_rects.items():
                if overlaps(l_rect, z_rect):
                    fail(report, "E_LEGEND_INSIDE_ZONE", f"legend {l_name} overlaps zone {z_id}; place legend outside all boundary zones")
    layout_constraints = plan.get("layout_constraints", {})
    for group in layout_constraints.get("uniform_node_groups", []):
        group_id = group.get("id", "unnamed")
        tolerance = float(group.get("tolerance", 0.5))
        group_nodes = group.get("nodes", [])
        missing = [node_id for node_id in group_nodes if node_id not in node_rects]
        if missing:
            fail(report, "E_LAYOUT_CONSTRAINT_NODE_MISSING", f"uniform group {group_id} references missing nodes: {', '.join(missing)}")
            continue
        target_y = group.get("y")
        target_height = group.get("height")
        if target_y is None:
            target_y = node_rects[group_nodes[0]][1]
        if target_height is None:
            target_height = node_rects[group_nodes[0]][3]
        for node_id in group_nodes:
            _, actual_y, _, actual_height = node_rects[node_id]
            if abs(actual_y - float(target_y)) > tolerance:
                fail(report, "E_NODE_ALIGNMENT_INCONSISTENT", f"node {node_id} violates uniform y in group {group_id}")
            if abs(actual_height - float(target_height)) > tolerance:
                fail(report, "E_NODE_HEIGHT_INCONSISTENT", f"node {node_id} violates uniform height in group {group_id}")
    for left_id, left in node_rects.items():
        for right_id, right in node_rects.items():
            if left_id >= right_id:
                continue
            if overlaps(left, right):
                fail(report, "E_NODE_OVERLAP", f"nodes overlap: {left_id} / {right_id}")

    plan_ports = {}
    for node_id, node in nodes.items():
        for port_name, port in node.get("ports", {}).items():
            plan_ports[f"{node_id}.{port_name}"] = point(port)

    markers = {
        elem.attrib.get("id"): elem
        for elem in root.iter()
        if elem.tag.split("}")[-1] == "marker" and elem.attrib.get("id")
    }

    svg_nodes = {elem.attrib.get("data-svga-node") for elem in root.iter() if elem.attrib.get("data-svga-node")}
    for node_id in nodes:
        if node_id not in svg_nodes:
            fail(report, "E_NODE_MISSING", f"missing SVG node: {node_id}")

    validate_node_chrome(root, node_rects, report)

    ancestor_map = _build_ancestor_map(root)
    icon_boxes = collect_icon_boxes(root, ancestor_map)
    svg_texts = {elem.attrib.get("data-svga-text"): elem for elem in root.iter() if elem.attrib.get("data-svga-text")}
    for text_id, spec in text_boxes.items():
        elem = svg_texts.get(text_id)
        if elem is None:
            fail(report, "E_TEXT_MISSING", f"missing SVG text: {text_id}")
            continue
        unsafe_tspan, anchor_val = has_unsafe_centered_tspans(elem, ancestor_map.get(id(elem), []))
        if unsafe_tspan:
            fail(
                report,
                "E_TEXT_TSPAN_ANCHOR_UNSAFE",
                f"text {text_id} uses text-anchor={anchor_val!r} with multiple tspans, which overlaps in cairosvg; split into separate <text> elements or use text-anchor='start'",
            )
        actual = text_bbox(elem, ancestor_map)
        actual_rect = actual[:4]
        allowed = rect(spec["rect"])
        if actual[2] > allowed[2] + 1:
            fail(report, "E_TEXT_OVERFLOW", f"text width exceeds box: {text_id} ({actual[2]:.1f} > {allowed[2]:.1f})")
        if not contains(allowed, actual_rect, 2):
            fail(report, "E_TEXT_OUT_OF_BOX", f"text escapes box: {text_id} (actual={_fmt_rect(actual_rect)} vs box={_fmt_rect(allowed)})")
        node_id = spec.get("node")
        if node_id:
            inner = inset(node_rects[node_id], float(nodes[node_id].get("padding", 0)))
            if not contains(inner, allowed, 0.5):
                fail(report, "E_TEXT_PADDING", f"text box violates node padding: {text_id} (box={_fmt_rect(allowed)} vs node_inner={_fmt_rect(inner)})")
            for reserved in nodes[node_id].get("reserved", []):
                if overlaps(allowed, rect(reserved)):
                    fail(report, "E_TEXT_RESERVED_OVERLAP", f"text overlaps reserved zone: {text_id}")
        zone_id = spec.get("zone")
        if zone_id:
            if zone_id not in zone_rects:
                fail(report, "E_ZONE_MISSING", f"text_box {text_id} references missing zone: {zone_id}")
            elif not contains(zone_rects[zone_id], allowed, 1.0):
                fail(report, "E_ZONE_CONTAINMENT", f"text_box {text_id} escapes zone {zone_id}")
        for reserved in spec.get("reserved_overlap", []):
            if overlaps(allowed, rect(reserved)):
                fail(report, "E_TEXT_RESERVED_OVERLAP", f"text overlaps reserved zone: {text_id}")
        for icon_box in icon_boxes:
            if overlaps(actual_rect, icon_box):
                fail(report, "E_TEXT_RESERVED_OVERLAP", f"text overlaps icon geometry: {text_id}")
                break

    extra_texts = set(svg_texts) - set(text_boxes)
    for text_id in sorted(extra_texts):
        warn(report, "W_TEXT_UNPLANNED", f"SVG text has no plan box: {text_id}")

    svg_edges = {elem.attrib.get("data-svga-edge"): elem for elem in root.iter() if elem.attrib.get("data-svga-edge")}
    draw_order = list(root.iter())
    draw_index = {id(elem): index for index, elem in enumerate(draw_order)}
    edge_records = []
    for edge_id, edge in edges.items():
        elem = svg_edges.get(edge_id)
        if elem is None:
            fail(report, "E_EDGE_MISSING", f"missing SVG edge: {edge_id}")
            continue
        if elem.attrib.get("stroke", "").startswith("url("):
            fail(report, "E_EDGE_GRADIENT_STROKE", f"edge {edge_id} uses a gradient stroke; use a solid token color")
        if edge.get("directed", True) and not elem.attrib.get("marker-end"):
            fail(report, "E_ARROW_MISSING", f"directed edge has no arrow: {edge_id}")
        marker_match = re.search(r"url\(#([^)]+)\)", elem.attrib.get("marker-end", ""))
        if edge.get("directed", True) and marker_match:
            marker = markers.get(marker_match.group(1))
            if marker is None:
                fail(report, "E_ARROW_MARKER_MISSING", f"arrow marker is undefined: {edge_id}")
            else:
                if marker.attrib.get("markerUnits", "strokeWidth") != "userSpaceOnUse":
                    fail(report, "E_ARROW_MARKER_UNITS", f"arrow marker must use userSpaceOnUse: {edge_id}")
                try:
                    marker_width = float(marker.attrib.get("markerWidth", 0))
                    marker_height = float(marker.attrib.get("markerHeight", 0))
                    ref_x = float(marker.attrib.get("refX", 0))
                    if max(marker_width, marker_height) > ARROW_MAX_SIZE:
                        fail(report, "E_ARROW_OVERSIZE", f"arrow marker is too large: {edge_id}")
                    if ref_x < marker_width - 1:
                        fail(report, "E_ARROW_REF_MISMATCH", f"arrow tip is not aligned to marker end: {edge_id}")
                except ValueError:
                    fail(report, "E_ARROW_MARKER_INVALID", f"arrow marker geometry is invalid: {edge_id}")
        if edge.get("route") not in {"orthogonal", "straight", "bezier"}:
            fail(report, "E_EDGE_ROUTE_UNDECLARED", f"edge route must be declared: {edge_id}")
        source = plan_ports.get(edge["from"])
        target = plan_ports.get(edge["to"])
        if source is None or target is None:
            fail(report, "E_PORT_MISSING", f"edge references missing port: {edge_id}")
            continue
        try:
            segments = parse_path_segments(elem.attrib.get("d", ""))
            if not segments:
                raise ValueError("empty path")
            start = segments[0][1]
            end = segments[-1][-1]
        except (TypeError, ValueError, IndexError) as exc:
            fail(report, "E_EDGE_PATH_INVALID", f"invalid edge path {edge_id}: {exc}")
            continue
        for later in draw_order[draw_index[id(elem)] + 1:]:
            if later.tag.split("}")[-1] != "rect" or later.attrib.get("fill", "none") == "none":
                continue
            if float(later.attrib.get("opacity", "1")) == 0 or float(later.attrib.get("fill-opacity", "1")) == 0:
                continue
            bounds = shape_bounds(later)
            if bounds and not any(contains(node_box, bounds, 1) for node_box in node_rects.values()):
                if any(segment_hits_rect(segment, bounds) for segment in segments):
                    fail(report, "E_EDGE_OCCLUDED", f"edge {edge_id} is covered by a later filled rectangle")
                    break
        if layout_constraints.get("orthogonal_edges") and edge.get("route") in {"straight", "orthogonal"}:
            for segment in segments:
                if segment[0] != "L":
                    fail(report, "E_EDGE_NON_ORTHOGONAL", f"edge {edge_id} uses a curve while orthogonal_edges is enabled")
                    break
                segment_start, segment_end = segment[1], segment[-1]
                if abs(segment_start[0] - segment_end[0]) > 0.01 and abs(segment_start[1] - segment_end[1]) > 0.01:
                    fail(report, "E_EDGE_NON_ORTHOGONAL", f"edge {edge_id} contains a diagonal segment")
                    break
        if distance(start, source) > TOLERANCE:
            fail(report, "E_EDGE_START_MISMATCH", f"edge start misses port: {edge_id} (actual=({start[0]:.1f}, {start[1]:.1f}) vs port=({source[0]:.1f}, {source[1]:.1f}))")
        if distance(end, target) > TOLERANCE:
            fail(report, "E_EDGE_END_MISMATCH", f"edge end misses port: {edge_id} (actual=({end[0]:.1f}, {end[1]:.1f}) vs port=({target[0]:.1f}, {target[1]:.1f}))")
        waypoints = edge.get("waypoints", [])
        if len(waypoints) < 2:
            fail(report, "E_EDGE_WAYPOINTS_MISSING", f"edge needs at least two waypoints: {edge_id}")
        elif edge.get("route") in {"orthogonal", "straight"}:
            expected_vertices = [point(item) for item in waypoints]
            actual_vertices = path_vertices(segments)
            if len(expected_vertices) != len(actual_vertices) or any(
                distance(expected, actual) > TOLERANCE
                for expected, actual in zip(expected_vertices, actual_vertices)
            ):
                fail(report, "E_EDGE_ROUTE_MISMATCH", f"SVG path does not match planned route: {edge_id}")
        source_node = edge["from"].split(".", 1)[0]
        target_node = edge["to"].split(".", 1)[0]
        sampled = [point for segment in segments for point in sample_segment(segment)]
        if safe_area is not None and any(
            not contains(safe_area, (pt[0], pt[1], 0.0, 0.0), 2.0) for pt in sampled
        ):
            fail(report, "E_GEOMETRY_OUT_OF_BOUNDS", f"edge {edge_id} escapes safe_area")
        edge_records.append({
            "id": edge_id,
            "points": sampled,
            "min_clearance": float(edge.get("min_clearance", default_edge_gap)),
            "from": edge["from"],
            "to": edge["to"],
        })
        for node_id, node_rect in node_rects.items():
            if node_id in {source_node, target_node}:
                continue
            if any(inside(item, node_rect, 2) for item in sampled):
                fail(report, "E_EDGE_CROSSES_NODE", f"edge crosses unrelated node: {edge_id} -> {node_id}")
        for text_id, spec in text_boxes.items():
            text_rect = rect(spec["rect"])
            if any(inside(item, text_rect, 0) for item in sampled[2:-2]):
                fail(report, "E_EDGE_CROSSES_TEXT", f"edge crosses text box: {edge_id} -> {text_id}")

    for index, left in enumerate(edge_records):
        left_inner = left["points"][2:-2]
        for right in edge_records[index + 1:]:
            if left["from"] == right["from"] or left["to"] == right["to"]:
                continue
            gap = max(left["min_clearance"], right["min_clearance"])
            if min_point_distance(left_inner, right["points"][2:-2]) < gap:
                fail(report, "E_EDGE_TOO_CLOSE", f"edges violate minimum clearance: {left['id']} / {right['id']}")

    defs_paths = {
        id(item)
        for defs in root.iter()
        if defs.tag.split("}")[-1] == "defs"
        for item in defs.iter()
        if item.tag.split("}")[-1] == "path"
    }
    for elem in root.iter():
        if elem.tag.split("}")[-1] != "path" or elem.attrib.get("data-svga-edge"):
            continue
        if id(elem) in defs_paths:
            continue
        ancestors = ancestor_map.get(id(elem), [])
        role = elem.attrib.get("data-svga-role") or next(
            (anc.attrib.get("data-svga-role") for anc in reversed(ancestors) if anc.attrib.get("data-svga-role")),
            None,
        )
        if role not in {"icon", "decoration"}:
            fail(report, "E_PATH_UNTAGGED", "non-edge path lacks data-svga-role ('decoration' for chart arcs/needles/dividers, 'icon' for standalone icons)")

    report["status"] = "ERROR" if report["errors"] else "PASS"
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Guage SVG Gen semantic geometry validator (nodes, text boxes, ports, icons, and edges).",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--svg", required=True, help="Path to SVG file")
    parser.add_argument("--plan", required=True, help="Path to layout plan JSON")
    parser.add_argument("--strict", action="store_true", help="Enable strict checking")
    parser.add_argument("--json", action="store_true", help="Emit JSON report to stdout")
    args = parser.parse_args()
    report = validate(args.svg, args.plan, args.strict)
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"Status: {report['status']}")
        for item in report["errors"] + report["warnings"]:
            print(f"{item['code']}: {item['msg']}")
    sys.exit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
