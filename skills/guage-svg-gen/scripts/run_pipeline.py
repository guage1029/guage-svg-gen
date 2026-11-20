#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pillow>=10.0.0",
#   "cairosvg>=2.7.1",
# ]
# ///
"""Orchestrate SVG schema, structural, language, color, and geometry validation with atomic staging."""
import subprocess
import json
import os
import argparse
import re
import sys
import hashlib
import shlex
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

# Skill Root deduction
SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
VALIDATE_SVG_SCRIPT = SCRIPTS_DIR / "validate_svg.py"
GEOMETRY_SCRIPT = SCRIPTS_DIR / "validate_geometry.py"
COLOR_SCRIPT = SCRIPTS_DIR / "validate_color.py"
LANGUAGE_SCRIPT = SCRIPTS_DIR / "validate_language.py"
FIX_SVG_SCRIPT = SCRIPTS_DIR / "fix_svg.py"
OPTIMIZE_SVG_SCRIPT = SCRIPTS_DIR / "optimize_svg.py"

EPILOG = """Examples:
  python3 scripts/run_pipeline.py --svg /tmp/draft.svg --plan out.layout.json --output-svg out.svg --cleanup-draft --strict --json
  python3 scripts/run_pipeline.py --svg out.svg --plan out.layout.json --in-place --strict --json

Exit codes:
  0  SUCCESS (all validation gates and optimization passed)
  1  FAILED (max retries reached or pipeline stalled)
  2  FAILED (validator crash or report parse error)
  3  REPAIR_REQUIRED (validation gate failed; see errors in output)
  4  PARTIAL_SUCCESS / POST_PROCESS_FAIL (SVG ready, bitmap conversion failed)
"""

AUTO_FIXABLE = ["E_VIEWBOX_MISSING", "E_VIEWBOX_INVALID", "E_A11Y_MISSING", "E_SECURITY_STYLE_CONTENT"]
ID_RE = re.compile(r"^[a-z0-9-]+$")
PORT_REF_RE = re.compile(r"^[a-z0-9-]+\.[a-z0-9-]+$")
HEX6_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
VIEWBOX_RE = re.compile(r"^-?\d+(\.\d+)? -?\d+(\.\d+)? \d+(\.\d+)? \d+(\.\d+)?$")


def get_file_hash(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return None


def run_cmd(cmd, env=None):
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return res.returncode, res.stdout, res.stderr


def _is_num(val):
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def validate_layout_plan_schema(plan_path):
    """Lightweight stdlib validator aligned with assets/layout-plan.schema.json."""
    try:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Failed to parse layout plan JSON: {exc}"]

    if not isinstance(plan, dict):
        return ["Layout plan root must be a JSON object"]

    errors = []
    allowed_root = {
        "canvas", "metadata", "slots", "creative_zone", "palette",
        "color_system", "layout_constraints", "zones", "nodes", "text_boxes", "edges",
    }
    required_root = allowed_root - {"layout_constraints", "zones"}
    for key in sorted(required_root - set(plan.keys())):
        errors.append(f"Missing required root field: {key}")
    for key in sorted(set(plan.keys()) - allowed_root):
        errors.append(f"Unexpected root field: {key}")

    canvas = plan.get("canvas")
    if isinstance(canvas, dict):
        for k in set(canvas.keys()) - {"viewBox", "aspect_ratio", "safe_area"}:
            errors.append(f"Unexpected canvas field: {k}")
        vb = canvas.get("viewBox")
        if not isinstance(vb, str) or not VIEWBOX_RE.match(vb):
            errors.append("canvas.viewBox is missing or malformed")
        if "aspect_ratio" in canvas and canvas["aspect_ratio"] not in {"16:9", "4:3", "1:1", "2.4:1", "2.35:1", "custom"}:
            errors.append(f"Invalid canvas.aspect_ratio: {canvas.get('aspect_ratio')}")
        sa = canvas.get("safe_area")
        if not isinstance(sa, dict) or not all(k in sa and _is_num(sa[k]) for k in ("x", "y", "width", "height")):
            errors.append("canvas.safe_area must contain numeric x, y, width, height")
    elif "canvas" in plan:
        errors.append("canvas must be an object")

    meta = plan.get("metadata")
    if isinstance(meta, dict):
        for k in set(meta.keys()) - {"theme", "platform", "language"}:
            errors.append(f"Unexpected metadata field: {k}")
        if meta.get("theme") not in {"bg_dark", "bg_light"}:
            errors.append(f"Invalid metadata.theme: {meta.get('theme')}")
        if not isinstance(meta.get("platform"), str):
            errors.append("metadata.platform must be a string")
        if "language" in meta and meta["language"] not in {"zh", "en", "mixed"}:
            errors.append(f"Invalid metadata.language: {meta['language']}")

    palette = plan.get("palette")
    if isinstance(palette, dict):
        for k in set(palette.keys()) - {"background", "primary", "text"}:
            errors.append(f"Unexpected palette field: {k}")
        for k in ("background", "primary", "text"):
            if not isinstance(palette.get(k), str) or not HEX6_RE.match(palette[k]):
                errors.append(f"palette.{k} must be a 6-digit hex color")

    cs = plan.get("color_system")
    if isinstance(cs, dict):
        for k in set(cs.keys()) - {"theme", "diagram_type", "role_map"}:
            errors.append(f"Unexpected color_system field: {k}")
        if cs.get("theme") not in {"bg_dark", "bg_light"}:
            errors.append(f"Invalid color_system.theme: {cs.get('theme')}")
        if not isinstance(cs.get("role_map"), dict):
            errors.append("color_system.role_map must be an object")

    for idx, zone in enumerate(plan.get("zones", []) if isinstance(plan.get("zones"), list) else []):
        if not isinstance(zone, dict):
            errors.append(f"zones[{idx}] must be an object")
            continue
        for k in set(zone.keys()) - {"id", "rect", "parent_zone", "nodes", "label", "padding"}:
            errors.append(f"Unexpected zones[{idx}] field: {k}")
        if not isinstance(zone.get("id"), str) or not ID_RE.match(zone["id"]):
            errors.append(f"Invalid zones[{idx}].id: {zone.get('id')}")
        r = zone.get("rect")
        if not isinstance(r, dict) or not all(k in r and _is_num(r[k]) for k in ("x", "y", "w", "h")) or r["w"] <= 0 or r["h"] <= 0:
            errors.append(f"Invalid zones[{idx}].rect")
        if "parent_zone" in zone and (not isinstance(zone["parent_zone"], str) or not ID_RE.match(zone["parent_zone"])):
            errors.append(f"Invalid zones[{idx}].parent_zone: {zone.get('parent_zone')}")

    for idx, node in enumerate(plan.get("nodes", []) if isinstance(plan.get("nodes"), list) else []):
        if not isinstance(node, dict):
            errors.append(f"nodes[{idx}] must be an object")
            continue
        for k in set(node.keys()) - {"id", "rect", "padding", "reserved", "ports"}:
            errors.append(f"Unexpected nodes[{idx}] field: {k}")
        if not isinstance(node.get("id"), str) or not ID_RE.match(node["id"]):
            errors.append(f"Invalid nodes[{idx}].id: {node.get('id')}")
        r = node.get("rect")
        if not isinstance(r, dict) or not all(k in r and _is_num(r[k]) for k in ("x", "y", "w", "h")) or r["w"] <= 0 or r["h"] <= 0:
            errors.append(f"Invalid nodes[{idx}].rect")
        if not isinstance(node.get("ports"), dict):
            errors.append(f"nodes[{idx}].ports must be an object")

    for idx, tb in enumerate(plan.get("text_boxes", []) if isinstance(plan.get("text_boxes"), list) else []):
        if not isinstance(tb, dict):
            errors.append(f"text_boxes[{idx}] must be an object")
            continue
        for k in set(tb.keys()) - {"id", "node", "zone", "role", "rect", "reserved_overlap"}:
            errors.append(f"Unexpected text_boxes[{idx}] field: {k}")
        if "role" in tb and tb["role"] not in {"default", "legend", "zone_label"}:
            errors.append(f"Invalid text_boxes[{idx}].role: {tb.get('role')}")
        if not isinstance(tb.get("id"), str) or not ID_RE.match(tb["id"]):
            errors.append(f"Invalid text_boxes[{idx}].id: {tb.get('id')}")
        r = tb.get("rect")
        if not isinstance(r, dict) or not all(k in r and _is_num(r[k]) for k in ("x", "y", "w", "h")) or r["w"] <= 0 or r["h"] <= 0:
            errors.append(f"Invalid text_boxes[{idx}].rect")

    for idx, edge in enumerate(plan.get("edges", []) if isinstance(plan.get("edges"), list) else []):
        if not isinstance(edge, dict):
            errors.append(f"edges[{idx}] must be an object")
            continue
        for k in set(edge.keys()) - {"id", "from", "to", "directed", "route", "waypoints", "min_clearance"}:
            errors.append(f"Unexpected edges[{idx}] field: {k}")
        if not isinstance(edge.get("id"), str) or not ID_RE.match(edge["id"]):
            errors.append(f"Invalid edges[{idx}].id: {edge.get('id')}")
        for end_key in ("from", "to"):
            if not isinstance(edge.get(end_key), str) or not PORT_REF_RE.match(edge[end_key]):
                errors.append(f"Invalid edges[{idx}].{end_key}: {edge.get(end_key)}")
        if edge.get("route") not in {"straight", "orthogonal", "bezier"}:
            errors.append(f"Invalid edges[{idx}].route: {edge.get('route')}")
        wps = edge.get("waypoints")
        if not isinstance(wps, list) or len(wps) < 2:
            errors.append(f"edges[{idx}].waypoints must contain at least 2 points")

    return errors


def run_plan_gates(working_svg, plan_path, strict, json_mode=False):
    gates = [
        ("language", LANGUAGE_SCRIPT),
        ("color", COLOR_SCRIPT),
        ("geometry", GEOMETRY_SCRIPT),
    ]
    gate_results = {}
    for name, script_path in gates:
        cmd = [sys.executable, str(script_path), "--svg", working_svg, "--plan", plan_path, "--json"]
        if strict:
            cmd.append("--strict")
        ret, stdout, stderr = run_cmd(cmd)
        parsed = None
        if stdout.strip():
            try:
                parsed = json.loads(stdout.strip())
            except Exception:
                parsed = {"raw": stdout.strip()}
        gate_results[name] = parsed or {"status": "PASS" if ret == 0 else "FAIL"}
        if not json_mode and stdout.strip() and (name != "geometry" or ret != 0):
            print(stdout.strip())
        if ret != 0:
            if stderr.strip():
                print(stderr.strip(), file=sys.stderr)
            return False, name, gate_results
        if not json_mode:
            print(f"{name}_status: PASS")
        else:
            print(f"[*] {name}_status: PASS", file=sys.stderr)
    return True, None, gate_results


def main():
    parser = argparse.ArgumentParser(
        description="Industrial SVG Orchestrator (Atomic Staging, Iteration Merge & Full Re-validation).",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--svg", required=True, help="Input SVG draft or file path")
    parser.add_argument("--plan", help="Path to layout plan JSON")
    parser.add_argument("--slug", default="asset", help="Asset slug for timestamped output naming")
    parser.add_argument("--strict", action="store_true", help="Enable strict mode across all validators")
    parser.add_argument("--json", action="store_true", help="Emit a single structured JSON summary to stdout (diagnostics go to stderr)")
    parser.add_argument("--max-retries", type=int, default=3, help="Max auto-fix retries (default: 3)")
    parser.add_argument("--repair-cmd", help="External command to fix errors")
    parser.add_argument("--export-format", default="svg", choices=["svg", "png", "all"], help="Export format (default: svg)")
    parser.add_argument("--in-place", action="store_true", help="Atomically update --svg in place instead of creating a timestamped copy")
    parser.add_argument("--output-svg", default=None, help="Canonical target SVG path (overwrites across iterations instead of creating timestamped copies)")
    parser.add_argument("--cleanup-draft", action="store_true", help="Remove the input --svg draft file after validation succeeds (only when distinct from target)")
    parser.add_argument("--supersede", action="append", default=[], help="Previous SVG path(s) to remove after the new deliverable succeeds")
    parser.add_argument("--merge-same-slug", action="store_true", help="Remove older YYYYMMDD_HHMMSS_<slug>.svg deliverables in output-dir after success")
    parser.add_argument("--keep-failed", action="store_true", help="Keep failed staging SVG in output-dir for debugging")
    parser.add_argument("--output-dir", default=os.environ.get("SVG_ARCHITECT_WORKSPACE", os.path.join(os.path.expanduser("~"), "Documents", "workspace", "svg-architect")), help="Output directory when neither --in-place nor --output-svg is set")
    args = parser.parse_args()

    if args.in_place and args.output_svg:
        parser.error("--in-place and --output-svg are mutually exclusive")

    source_svg = Path(args.svg).resolve()
    out_dir = Path(args.output_dir).resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_filename = f"{timestamp}_{args.slug}"

    if args.in_place:
        target_svg = source_svg
        target_png = source_svg.with_suffix(".png")
        out_dir = target_svg.parent
    elif args.output_svg:
        target_svg = Path(args.output_svg).resolve()
        target_png = target_svg.with_suffix(".png")
        out_dir = target_svg.parent
    else:
        target_svg = out_dir / f"{target_filename}.svg"
        target_png = out_dir / f"{target_filename}.png"

    out_dir.mkdir(parents=True, exist_ok=True)

    if args.plan:
        schema_errors = validate_layout_plan_schema(args.plan)
        if schema_errors:
            print(json.dumps({
                "status": "FAIL",
                "gate": "plan_schema",
                "errors": [{"code": "E_PLAN_SCHEMA_INVALID", "message": msg} for msg in schema_errors],
            }, ensure_ascii=False, indent=2))
            sys.exit(3)

    with tempfile.TemporaryDirectory() as stage_dir:
        stage_svg_path = Path(stage_dir) / f"{target_filename}.svg"
        stage_png_path = Path(stage_dir) / f"{target_filename}.png"
        shutil.copy(args.svg, stage_svg_path)
        working_svg = str(stage_svg_path.resolve())

        print(f"[*] Pipeline Staging: {working_svg}", file=sys.stderr)
        attempt = 0
        attempt_history = set()
        gate_reports = {}

        def abort_with_code(code, fail_payload=None):
            if args.keep_failed and stage_svg_path.exists():
                failed_path = out_dir / f"{target_filename}.failed.svg"
                shutil.copy(stage_svg_path, failed_path)
                print(f"[*] Failed draft kept at: {failed_path}", file=sys.stderr)
            if args.json and fail_payload is not None:
                print(json.dumps(fail_payload, ensure_ascii=False, indent=2))
            sys.exit(code)

        while attempt <= args.max_retries:
            val_cmd = [sys.executable, str(VALIDATE_SVG_SCRIPT), '--svg', working_svg, '--json']
            if args.plan:
                val_cmd.extend(['--plan', args.plan])
            if args.strict:
                val_cmd.append('--strict')

            _, stdout, stderr = run_cmd(val_cmd)
            try:
                report = json.loads(stdout.strip())
            except Exception:
                if stderr.strip():
                    print(stderr.strip(), file=sys.stderr)
                abort_with_code(2, {"status": "FAILED", "gate": "svg", "reason": "Malformed validator JSON"})

            gate_reports["svg"] = report
            if report['status'] == 'PASS':
                if args.plan:
                    ok, failed_gate, plan_gate_reports = run_plan_gates(working_svg, args.plan, args.strict, json_mode=args.json)
                    gate_reports.update(plan_gate_reports)
                    if not ok:
                        failed_rep = plan_gate_reports.get(failed_gate, {})
                        abort_with_code(3, {
                            "status": "FAIL",
                            "gate": failed_gate,
                            "errors": failed_rep.get("errors", []),
                            "gates": gate_reports,
                        })
                break

            errors = [e['code'] for e in report['errors']]
            file_hash = get_file_hash(working_svg)
            state_id = hashlib.md5(f"{sorted(errors)}_{file_hash}".encode()).hexdigest()
            if state_id in attempt_history:
                if not args.json:
                    print(stdout.strip())
                abort_with_code(1, {"status": "FAIL", "gate": "svg", "errors": report.get("errors", [])})
            attempt_history.add(state_id)

            fixable = [e for e in errors if e in AUTO_FIXABLE]
            non_fixable = [e for e in errors if e not in AUTO_FIXABLE]

            if fixable:
                fix_cmd = [sys.executable, str(FIX_SVG_SCRIPT), '--svg', working_svg, '--errors', ','.join(fixable)]
                if args.plan:
                    fix_cmd.extend(['--plan', args.plan])
                run_cmd(fix_cmd)
                attempt += 1
                continue

            if non_fixable:
                if args.repair_cmd:
                    env = os.environ.copy()
                    env['SVG_ERRORS'] = ','.join(non_fixable)
                    env['SVG_PATH'] = working_svg
                    run_cmd(shlex.split(args.repair_cmd), env=env)
                    attempt += 1
                    continue
                else:
                    if not args.json:
                        print(stdout.strip())
                    abort_with_code(3, {"status": "FAIL", "gate": "svg", "errors": report.get("errors", [])})
            attempt += 1

        # Final Gate: Post-processing in staging
        pp_cmd = [
            sys.executable, str(OPTIMIZE_SVG_SCRIPT), working_svg,
            '--output', working_svg, '--png', str(stage_png_path.resolve()),
            '--format', args.export_format, '--json',
        ]
        _, pp_out, _ = run_cmd(pp_cmd)

        try:
            pp_report = json.loads(pp_out.strip())
        except Exception:
            if not args.json:
                print("status: FAILED")
                print("[💥] Post-processing report malformed or empty.")
            abort_with_code(4, {"status": "FAILED", "gate": "optimize", "reason": "Post-processing report malformed"})

        # Re-validate after svgo if svgo altered the SVG
        if pp_report.get('details', {}).get('svgo') == 'SUCCESS':
            reval_cmd = [sys.executable, str(VALIDATE_SVG_SCRIPT), '--svg', working_svg, '--json']
            if args.plan:
                reval_cmd.extend(['--plan', args.plan])
            if args.strict:
                reval_cmd.append('--strict')
            _, reval_out, _ = run_cmd(reval_cmd)
            try:
                reval_report = json.loads(reval_out.strip())
            except Exception:
                abort_with_code(2, {"status": "FAILED", "gate": "post_svgo_svg"})
            if reval_report.get('status') != 'PASS':
                if not args.json:
                    print(reval_out.strip())
                abort_with_code(3, {"status": "FAIL", "gate": "post_svgo_svg", "errors": reval_report.get("errors", [])})
            if args.plan:
                ok, failed_gate, plan_gate_reports = run_plan_gates(working_svg, args.plan, args.strict, json_mode=args.json)
                if not ok:
                    abort_with_code(3, {"status": "FAIL", "gate": f"post_svgo_{failed_gate}", "gates": plan_gate_reports})

        def finalize_cleanup():
            cleaned = []
            if args.cleanup_draft and source_svg.exists() and source_svg != target_svg.resolve():
                source_svg.unlink()
                cleaned.append(str(source_svg))
            for prev_raw in args.supersede:
                for item in prev_raw.split(","):
                    item = item.strip()
                    if not item:
                        continue
                    prev_p = Path(item).resolve()
                    if prev_p.exists() and prev_p != target_svg.resolve() and prev_p.suffix.lower() == ".svg":
                        prev_p.unlink()
                        cleaned.append(str(prev_p))
            if args.merge_same_slug and not (args.in_place or args.output_svg):
                ts_re = re.compile(rf"^\d{{8}}_\d{{6}}_{re.escape(args.slug)}\.svg$")
                for candidate in out_dir.iterdir():
                    if candidate.is_file() and ts_re.match(candidate.name) and candidate.resolve() != target_svg.resolve():
                        candidate.unlink()
                        cleaned.append(str(candidate.resolve()))
                        png_cand = candidate.with_suffix(".png")
                        if png_cand.exists() and png_cand.resolve() != target_png.resolve():
                            png_cand.unlink()
                            cleaned.append(str(png_cand.resolve()))
            return cleaned

        if pp_report['status'] == 'SUCCESS':
            shutil.copy(stage_svg_path, target_svg)
            if args.export_format in ["png", "all"] and stage_png_path.exists():
                shutil.copy(stage_png_path, target_png)
            cleaned_files = finalize_cleanup()
            svg_abs = str(target_svg.resolve())
            png_abs = str(target_png.resolve()) if args.export_format in ["png", "all"] else None
            if args.json:
                print(json.dumps({
                    "status": "SUCCESS",
                    "svg_abs_path": svg_abs,
                    "png_abs_path": png_abs,
                    "cleaned_process_files": cleaned_files,
                    "post_process": pp_report.get("details", {}),
                }, ensure_ascii=False, indent=2))
            else:
                print(f"svg_abs_path: {svg_abs}")
                if png_abs:
                    print(f"png_abs_path: {png_abs}")
                if cleaned_files:
                    print(f"cleaned_process_files: {json.dumps(cleaned_files, ensure_ascii=False)}")
                print("status: SUCCESS")
            sys.exit(0)
        elif pp_report['status'] == 'PARTIAL_SUCCESS':
            shutil.copy(stage_svg_path, target_svg)
            cleaned_files = finalize_cleanup()
            svg_abs = str(target_svg.resolve())
            if args.json:
                print(json.dumps({
                    "status": "PARTIAL_SUCCESS",
                    "svg_abs_path": svg_abs,
                    "cleaned_process_files": cleaned_files,
                    "reason": "Bitmap conversion failed.",
                }, ensure_ascii=False, indent=2))
            else:
                print(f"svg_abs_path: {svg_abs}")
                if cleaned_files:
                    print(f"cleaned_process_files: {json.dumps(cleaned_files, ensure_ascii=False)}")
                print("status: PARTIAL_SUCCESS")
                print("reason: Bitmap conversion failed.")
            sys.exit(4)
        else:
            if not args.json:
                print("status: FAILED")
                print(f"reason: {pp_report}")
            abort_with_code(4, {"status": "FAILED", "reason": pp_report})


if __name__ == "__main__":
    main()
