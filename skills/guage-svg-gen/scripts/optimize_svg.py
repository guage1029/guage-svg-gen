#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "cairosvg>=2.7.1",
# ]
# ///
"""Optimize SVG assets and optionally export PNG bitmaps matching viewBox dimensions."""
import argparse
import os
import subprocess
import shutil
import re
import sys
import xml.etree.ElementTree as ET
import json

EPILOG = """Examples:
  python3 scripts/optimize_svg.py out.svg --output out.svg --format svg --json
  python3 scripts/optimize_svg.py out.svg --png out.png --format png --json

Exit codes:
  0  SUCCESS
  1  FAILED (missing input file or fatal error)
  4  PARTIAL_SUCCESS (SVG ready, PNG conversion failed)
"""

def prefix_svg_ids_xml(svg_path, prefix):
    ET.register_namespace('', "http://www.w3.org/2000/svg")
    ET.register_namespace('xlink', "http://www.w3.org/1999/xlink")
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
        id_map = {}
        for elem in root.iter():
            if 'id' in elem.attrib:
                old_id = elem.attrib['id']
                new_id = f"{prefix}_{old_id}"
                id_map[old_id] = new_id
                elem.attrib['id'] = new_id
        for elem in root.iter():
            for attr, value in elem.attrib.items():
                if 'url(#' in value:
                    for old_id, new_id in id_map.items():
                        value = value.replace(f'url(#{old_id})', f'url(#{new_id})')
                    elem.attrib[attr] = value
                if value.startswith('#'):
                    old_id = value[1:]
                    if old_id in id_map:
                        elem.attrib[attr] = f"#{id_map[old_id]}"
        tree.write(svg_path, encoding='utf-8', xml_declaration=True)
        return True
    except: return False

def optimize_with_svgo(input_path, output_path):
    if shutil.which('svgo'):
        try:
            subprocess.run(['svgo', input_path, '-o', output_path], check=True, capture_output=True)
            return True
        except: return False
    return False

def infer_svg_dimensions(svg_path):
    try:
        root = ET.parse(svg_path).getroot()
        vb = root.attrib.get("viewBox", "")
        parts = re.split(r"[,\s]+", vb.strip())
        if len(parts) == 4:
            return int(round(float(parts[2]))), int(round(float(parts[3])))
    except Exception:
        pass
    return 1200, 675


def convert_to_png(svg_path, png_path, width=None, height=None):
    try:
        import cairosvg
        kwargs = {"url": str(svg_path), "write_to": str(png_path)}
        if width:
            kwargs["output_width"] = int(width)
        if height:
            kwargs["output_height"] = int(height)
        cairosvg.svg2png(**kwargs)
        return True
    except Exception:
        pass
    for tool in ['resvg', 'resvg-js', 'rsvg-convert']:
        if shutil.which(tool):
            try:
                if tool == 'rsvg-convert':
                    cmd = [tool, '-w', str(width or 1200), '-h', str(height or 675), svg_path, '-o', png_path]
                elif tool == 'resvg':
                    cmd = [tool, '-w', str(width or 1200), '-h', str(height or 675), svg_path, png_path]
                else:
                    cmd = [tool, svg_path, png_path]
                subprocess.run(cmd, check=True, capture_output=True)
                return True
            except Exception:
                continue
    try:
        from render_preview import _render_pillow_svg
        _render_pillow_svg(svg_path, width or 1200, height or 675, 1.0, png_path)
        return os.path.exists(png_path)
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Optimize SVG and optionally convert to PNG using viewBox dimensions.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="Input SVG path")
    parser.add_argument("--output", help="Output SVG path (defaults to input in-place)")
    parser.add_argument("--png", help="Output PNG path when --format is png or all")
    parser.add_argument("--prefix", help="Optional ID prefix to prepend to all element IDs")
    parser.add_argument("--width", type=int, default=None, help="Override PNG width (inferred from viewBox if omitted)")
    parser.add_argument("--height", type=int, default=None, help="Override PNG height (inferred from viewBox if omitted)")
    parser.add_argument("--format", default="svg", choices=["svg", "png", "all"], help="Export format (default: svg)")
    parser.add_argument("--json", action="store_true", help="Emit JSON report to stdout")
    args = parser.parse_args()
    
    report = {"status": "SUCCESS", "details": {}}
    if not os.path.exists(args.input):
        report["status"] = "FAILED"
        if args.json: print(json.dumps(report))
        sys.exit(1)
        
    output_svg = args.output if args.output else args.input
    output_png = args.png if args.png else args.input.replace('.svg', '.png')
    if args.output and args.output != args.input: shutil.copy(args.input, args.output)

    inferred_w, inferred_h = infer_svg_dimensions(output_svg)
    png_w = args.width if args.width is not None else inferred_w
    png_h = args.height if args.height is not None else inferred_h

    if args.prefix: report["details"]["prefix"] = "SUCCESS" if prefix_svg_ids_xml(output_svg, args.prefix) else "FAILED"
    report["details"]["svgo"] = "SUCCESS" if optimize_with_svgo(output_svg, output_svg) else "SKIPPED"
    
    # New Logic: Bitmap conversion only if requested
    if args.format in ["png", "all"]:
        if convert_to_png(output_svg, output_png, png_w, png_h):
            report["details"]["png"] = "SUCCESS"
        else:
            report["details"]["png"] = "FAILED"
            report["status"] = "PARTIAL_SUCCESS"
    else:
        report["details"]["png"] = "NOT_REQUESTED"

    if args.json:
        print(json.dumps(report))
    else:
        print(f"Status: {report['status']}")
        print(f"Details: {report['details']}")
        
    sys.exit(0 if report["status"] == "SUCCESS" else (4 if report["status"] == "PARTIAL_SUCCESS" else 1))

if __name__ == "__main__": main()
