#!/usr/bin/env python3
"""Validate semantic SVG layout contracts: nodes, text boxes, ports and edges."""

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


def text_bbox(elem):
    text = "".join(elem.itertext()).strip()
    size = float(elem.attrib.get("font-size", 16))
    width = measure_text(text, size, elem.attrib.get("font-family", ""))
    x = float(elem.attrib.get("x", 0))
    y = float(elem.attrib.get("y", 0))
    anchor = elem.attrib.get("text-anchor", "start")
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    return x, y - size * 0.84, width, size * 1.18, text, size


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
    tag = elem.tag.split("}")[-1]
    if tag == "rect":
        x = numeric_attr(elem, "x")
        y = numeric_attr(elem, "y")
        width = numeric_attr(elem, "width")
        height = numeric_attr(elem, "height")
        if None in {x, y, width, height}:
            return None
        return x, y, width, height
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
    edges = {item["id"]: item for item in plan.get("edges", [])}
    if not nodes or not edges or not text_boxes:
        fail(report, "E_GEOMETRY_CONTRACT_MISSING", "plan must declare nodes, text_boxes and edges")
        report["status"] = "ERROR"
        return report

    node_rects = {key: rect(value["rect"]) for key, value in nodes.items()}
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

    svg_texts = {elem.attrib.get("data-svga-text"): elem for elem in root.iter() if elem.attrib.get("data-svga-text")}
    for text_id, spec in text_boxes.items():
        elem = svg_texts.get(text_id)
        if elem is None:
            fail(report, "E_TEXT_MISSING", f"missing SVG text: {text_id}")
            continue
        actual = text_bbox(elem)
        actual_rect = actual[:4]
        allowed = rect(spec["rect"])
        if actual[2] > allowed[2] + 1:
            fail(report, "E_TEXT_OVERFLOW", f"text width exceeds box: {text_id} ({actual[2]:.1f} > {allowed[2]:.1f})")
        if not contains(allowed, actual_rect, 2):
            fail(report, "E_TEXT_OUT_OF_BOX", f"text escapes box: {text_id}")
        node_id = spec.get("node")
        if node_id:
            inner = inset(node_rects[node_id], float(nodes[node_id].get("padding", 0)))
            if not contains(inner, allowed, 0.5):
                fail(report, "E_TEXT_PADDING", f"text box violates node padding: {text_id}")
            for reserved in nodes[node_id].get("reserved", []):
                if overlaps(allowed, rect(reserved)):
                    fail(report, "E_TEXT_RESERVED_OVERLAP", f"text overlaps reserved zone: {text_id}")
        for reserved in spec.get("reserved_overlap", []):
            if overlaps(allowed, rect(reserved)):
                fail(report, "E_TEXT_RESERVED_OVERLAP", f"text overlaps reserved zone: {text_id}")

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
            fail(report, "E_EDGE_START_MISMATCH", f"edge start misses port: {edge_id}")
        if distance(end, target) > TOLERANCE:
            fail(report, "E_EDGE_END_MISMATCH", f"edge end misses port: {edge_id}")
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
        edge_records.append({
            "id": edge_id,
            "points": sampled,
            "min_clearance": float(edge.get("min_clearance", EDGE_MIN_GAP)),
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
        if elem.attrib.get("data-svga-role") not in {"icon", "decoration"}:
            fail(report, "E_PATH_UNTAGGED", "non-edge path lacks data-svga-role")

    report["status"] = "ERROR" if report["errors"] else "PASS"
    return report


def main():
    parser = argparse.ArgumentParser(description="Guage SVG Gen semantic geometry validator")
    parser.add_argument("--svg", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
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
