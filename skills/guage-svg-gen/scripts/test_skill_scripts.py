#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pillow>=10.0.0",
#   "cairosvg>=2.7.1",
# ]
# ///
"""Automated regression test suite for guage-svg-gen scripts and skill layout."""
import copy
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
ASSETS_DIR = SKILL_ROOT / "assets"
REFERENCES_DIR = SKILL_ROOT / "references"
EVALS_DIR = SKILL_ROOT / "evals"


def run_script(script_name, args):
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


BASE_PLAN = {
    "canvas": {"viewBox": "0 0 1200 500", "safe_area": {"x": 80, "y": 50, "width": 1040, "height": 400}},
    "metadata": {"theme": "bg_dark", "platform": "wechat_article", "language": "zh"},
    "slots": [
        {"slot_id": "background", "rect": {"x": 0, "y": 0, "w": 1200, "h": 500}, "content_type": "dark_flat_25px_gray_grid"},
        {"slot_id": "title_area", "rect": {"x": 80, "y": 50, "w": 1040, "h": 74}, "content_type": "diagram_header"},
        {"slot_id": "info_area", "rect": {"x": 90, "y": 140, "w": 1020, "h": 300}, "content_type": "main_diagram_nodes_and_edges"},
    ],
    "creative_zone": {"allowed_area": "x: 90-1110, y: 140-440", "visual_language": "charcoal cards", "focal_point": "stages"},
    "palette": {"background": "#050506", "primary": "#3B82F6", "text": "#FAFAFA"},
    "color_system": {
        "theme": "bg_dark",
        "diagram_type": "architecture",
        "role_map": {
            "background": "background",
            "grid": "surface_grid",
            "node": "surface",
            "node_primary": "surface_accent",
            "node_secondary": "surface_alt",
            "text_primary": "text_primary",
            "text_secondary": "text_secondary",
            "text_muted": "text_muted",
            "text_blue_soft": "text_blue_soft",
            "edge_flow": "edge",
            "edge_data": "edge_secondary",
        },
    },
    "layout_constraints": {
        "orthogonal_edges": True,
        "uniform_node_groups": [{"id": "primary-stages", "nodes": ["stage-1", "stage-2"], "y": 160, "height": 180, "tolerance": 1}],
    },
    "nodes": [
        {"id": "stage-1", "rect": {"x": 140, "y": 160, "w": 380, "h": 180}, "padding": 14, "ports": {"right": {"x": 520, "y": 250}}},
        {"id": "stage-2", "rect": {"x": 680, "y": 160, "w": 380, "h": 180}, "padding": 14, "ports": {"left": {"x": 680, "y": 250}}},
    ],
    "text_boxes": [
        {"id": "main-title", "rect": {"x": 360, "y": 50, "w": 480, "h": 46}},
        {"id": "sub-title", "rect": {"x": 300, "y": 98, "w": 600, "h": 24}},
        {"id": "s1-title", "node": "stage-1", "rect": {"x": 164, "y": 190, "w": 330, "h": 28}},
        {"id": "s2-title", "node": "stage-2", "rect": {"x": 704, "y": 190, "w": 330, "h": 28}},
    ],
    "edges": [
        {
            "id": "edge-1-2",
            "from": "stage-1.right",
            "to": "stage-2.left",
            "directed": True,
            "route": "straight",
            "waypoints": [{"x": 520, "y": 250}, {"x": 680, "y": 250}],
            "min_clearance": 10,
        }
    ],
}

BASE_SVG = """<svg xmlns="http://www.w3.org/2000/svg"
     width="1200" height="500" viewBox="0 0 1200 500"
     preserveAspectRatio="xMidYMid meet" role="img"
     aria-labelledby="svga-test-title svga-test-desc">
  <title id="svga-test-title">测试架构图</title>
  <desc id="svga-test-desc">用于自动化回归测试的标准两阶段架构图。</desc>
  <defs>
    <marker id="svga-test-arrow" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse" orient="auto">
      <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#60A5FA" data-svga-role="decoration" data-svga-color-role="edge_flow"/>
    </marker>
  </defs>
  <rect x="0" y="0" width="1200" height="500" fill="#050506" data-svga-color-role="background"/>
  <text x="600" y="84" text-anchor="middle" font-size="34" font-weight="800"
        font-family="PingFang SC, Noto Sans SC, Microsoft YaHei, system-ui, sans-serif"
        fill="#FAFAFA" data-svga-color-role="text_primary" data-svga-text="main-title">渐进式加载测试</text>
  <text x="600" y="114" text-anchor="middle" font-size="17" font-weight="500"
        font-family="PingFang SC, Noto Sans SC, Microsoft YaHei, system-ui, sans-serif"
        fill="#A1A1AA" data-svga-color-role="text_secondary" data-svga-text="sub-title">副标题说明文本</text>
  <g id="svga-test-stage-1" data-svga-node="stage-1">
    <rect x="140" y="160" width="380" height="180" rx="10" fill="#111114" stroke="#27272A" data-svga-color-role="node"/>
    <g transform="translate(164, 168)" data-svga-role="icon">
      <rect x="0" y="0" width="16" height="16" rx="3" fill="none" stroke="#60A5FA" data-svga-role="icon" data-svga-color-role="edge_flow"/>
    </g>
    <text x="164" y="212" font-size="22" font-weight="700"
          font-family="PingFang SC, Noto Sans SC, Microsoft YaHei, system-ui, sans-serif"
          fill="#FAFAFA" data-svga-color-role="text_primary" data-svga-text="s1-title"><tspan>读取 </tspan><tspan font-family="JetBrains Mono, monospace" data-svga-text-kind="path">SKILL.md</tspan></text>
  </g>
  <g id="svga-test-stage-2" data-svga-node="stage-2">
    <rect x="680" y="160" width="380" height="180" rx="10" fill="#18181B" stroke="#3B82F6" data-svga-color-role="node_secondary"/>
    <text x="704" y="212" font-size="22" font-weight="700"
          font-family="PingFang SC, Noto Sans SC, Microsoft YaHei, system-ui, sans-serif"
          fill="#FAFAFA" data-svga-color-role="text_primary" data-svga-text="s2-title">按需加载资源</text>
  </g>
  <path d="M 520 250 L 680 250" fill="none" stroke="#60A5FA" stroke-width="2.5"
        marker-end="url(#svga-test-arrow)" data-svga-edge="edge-1-2" data-svga-role="edge" data-svga-color-role="edge_flow"/>
</svg>
"""


class TestGuageSvgGenSkill(unittest.TestCase):
    def test_directory_and_script_conventions(self):
        self.assertTrue((SKILL_ROOT / "SKILL.md").exists())
        for expected_asset in (
            "color-tokens.json",
            "fonts-whitelist.json",
            "language-policy.json",
            "layout-plan.schema.json",
            "layout-plan-template.json",
            "layout-plan-light-template.json",
            "svg-starter-template.svg",
            "svg-starter-light-template.svg",
        ):
            self.assertTrue((ASSETS_DIR / expected_asset).is_file(), expected_asset)
        for expected_ref in (
            "error-codes.md",
            "style-bg-dark.md",
            "style-bg-light.md",
        ):
            self.assertTrue((REFERENCES_DIR / expected_ref).is_file(), expected_ref)
        for deprecated_ref in (
            "style-tech-dark.md",
            "style-minimal-clean.md",
            "style-glass-premium.md",
            "style-neubrutalism.md",
            "style-bento-info.md",
            "style-clay-soft.md",
        ):
            self.assertFalse((REFERENCES_DIR / deprecated_ref).exists(), deprecated_ref)
        # Ensure references/ is strictly flat (1-level deep)
        subdirs = [p for p in REFERENCES_DIR.iterdir() if p.is_dir()]
        self.assertEqual(subdirs, [])
        self.assertTrue((EVALS_DIR / "trigger-queries.json").is_file())

        for script in SCRIPTS_DIR.glob("*.py"):
            content = script.read_text(encoding="utf-8")
            self.assertIn("# /// script", content, f"{script.name} missing PEP 723 header")
            res = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{script.name} --help failed")

    def test_validate_language_tspan_and_suggestions(self):
        with tempfile.TemporaryDirectory() as td:
            td_p = pathlib.Path(td)
            plan_p = td_p / "plan.json"
            svg_p = td_p / "test.svg"
            plan_p.write_text(json.dumps(BASE_PLAN), encoding="utf-8")

            # 1. Valid tspan-level annotation passes
            svg_p.write_text(BASE_SVG, encoding="utf-8")
            r1 = run_script("validate_language.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            rep1 = json.loads(r1.stdout)
            self.assertEqual(rep1["status"], "PASS")

            # 2. Untranslated term 'Goal' alongside tagged <tspan> fails and suggests '目标'
            bad_svg = BASE_SVG.replace("<tspan>读取 </tspan>", "<tspan>读取 Goal </tspan>")
            svg_p.write_text(bad_svg, encoding="utf-8")
            r2 = run_script("validate_language.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            rep2 = json.loads(r2.stdout)
            self.assertEqual(rep2["status"], "FAIL")
            self.assertIn("目标", rep2["errors"][0]["message"])

    def test_validate_color_diagnostics(self):
        with tempfile.TemporaryDirectory() as td:
            td_p = pathlib.Path(td)
            plan_p = td_p / "plan.json"
            svg_p = td_p / "test.svg"
            plan_p.write_text(json.dumps(BASE_PLAN), encoding="utf-8")
            svg_p.write_text(BASE_SVG.replace('data-svga-color-role="node"', 'data-svga-color-role="unmapped_role"'), encoding="utf-8")
            r = run_script("validate_color.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            rep = json.loads(r.stdout)
            self.assertEqual(rep["status"], "FAIL")
            self.assertEqual(rep["errors"][0]["code"], "E_COLOR_ROLE_UNMAPPED")
            self.assertIn("Declared roles:", rep["errors"][0]["message"])

    def test_validate_geometry_whitespace_anchor_icon_and_safe_area(self):
        with tempfile.TemporaryDirectory() as td:
            td_p = pathlib.Path(td)
            plan_p = td_p / "plan.json"
            svg_p = td_p / "test.svg"
            plan_p.write_text(json.dumps(BASE_PLAN), encoding="utf-8")

            # 1. Multiline formatted <tspan> passes without false overflow
            formatted = BASE_SVG.replace(
                '<tspan>读取 </tspan><tspan font-family="JetBrains Mono, monospace" data-svga-text-kind="path">SKILL.md</tspan>',
                '\n            <tspan>读取 </tspan>\n            <tspan font-family="JetBrains Mono, monospace" data-svga-text-kind="path">SKILL.md</tspan>\n          ',
            )
            svg_p.write_text(formatted, encoding="utf-8")
            r1 = run_script("validate_geometry.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            self.assertEqual(json.loads(r1.stdout)["status"], "PASS")

            # 2. Centered multi-tspan fails with E_TEXT_TSPAN_ANCHOR_UNSAFE
            centered_bad = BASE_SVG.replace(
                '>渐进式加载测试</text>',
                '><tspan>Skill</tspan><tspan> 渐进式加载测试</tspan></text>',
            )
            svg_p.write_text(centered_bad, encoding="utf-8")
            r2 = run_script("validate_geometry.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            codes2 = [e["code"] for e in json.loads(r2.stdout)["errors"]]
            self.assertIn("E_TEXT_TSPAN_ANCHOR_UNSAFE", codes2)

            # 3. Icon colliding with s1-title fails with E_TEXT_RESERVED_OVERLAP
            icon_bad = BASE_SVG.replace("translate(164, 168)", "translate(170, 198)")
            svg_p.write_text(icon_bad, encoding="utf-8")
            r3 = run_script("validate_geometry.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            codes3 = [e["code"] for e in json.loads(r3.stdout)["errors"]]
            self.assertIn("E_TEXT_RESERVED_OVERLAP", codes3)

            # 4. Safe area violation reports coordinates
            bad_plan = copy.deepcopy(BASE_PLAN)
            bad_plan["nodes"][0]["rect"]["x"] = 20
            plan_p.write_text(json.dumps(bad_plan), encoding="utf-8")
            svg_p.write_text(BASE_SVG, encoding="utf-8")
            r4 = run_script("validate_geometry.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            rep4 = json.loads(r4.stdout)
            self.assertEqual(rep4["errors"][0]["code"], "E_GEOMETRY_OUT_OF_BOUNDS")
            self.assertIn("safe_area=", rep4["errors"][0]["msg"])

    def test_validate_svg_contrast_and_text_id(self):
        with tempfile.TemporaryDirectory() as td:
            svg_p = pathlib.Path(td) / "low.svg"
            svg_p.write_text(
                BASE_SVG.replace("<tspan>读取 </tspan>", '<tspan fill="#27272A">低对比 </tspan>'),
                encoding="utf-8",
            )
            r = run_script("validate_svg.py", ["--svg", str(svg_p), "--strict", "--json"])
            rep = json.loads(r.stdout)
            self.assertEqual(rep["status"], "ERROR")
            self.assertEqual(rep["errors"][0]["code"], "E_CONTRAST_LOW")
            self.assertEqual(rep["errors"][0]["text_id"], "s1-title")

    def test_pipeline_json_staging_and_preview_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            td_p = pathlib.Path(td)
            draft_p = td_p / "draft.svg"
            out_p = td_p / "final.svg"
            plan_p = td_p / "plan.json"
            draft_p.write_text(BASE_SVG, encoding="utf-8")
            plan_p.write_text(json.dumps(BASE_PLAN), encoding="utf-8")

            r_pipe = run_script("run_pipeline.py", [
                "--svg", str(draft_p),
                "--plan", str(plan_p),
                "--output-svg", str(out_p),
                "--cleanup-draft",
                "--strict",
                "--json",
            ])
            self.assertEqual(r_pipe.returncode, 0, r_pipe.stdout + r_pipe.stderr)
            rep_pipe = json.loads(r_pipe.stdout)
            self.assertEqual(rep_pipe["status"], "SUCCESS")
            self.assertTrue(out_p.exists())
            self.assertFalse(draft_p.exists())

            r_prev = run_script("render_preview.py", [
                "--svg", str(out_p),
                "--platform", "wechat_article",
                "--strict",
                "--json",
            ])
            self.assertEqual(r_prev.returncode, 0, r_prev.stdout + r_prev.stderr)
            rep_prev = json.loads(r_prev.stdout)
            self.assertEqual(rep_prev["status"], "PASS")
            self.assertTrue(rep_prev["is_isolated_temp"])
            pdir = pathlib.Path(rep_prev["preview_dir"])
            self.assertTrue(pdir.exists())

            r_clean = run_script("render_preview.py", ["--cleanup-dir", str(pdir), "--json"])
            self.assertEqual(r_clean.returncode, 0)
            self.assertFalse(pdir.exists())

    def test_starter_template_passes_full_pipeline(self):
        for svg_name, plan_name in (
            ("svg-starter-template.svg", "layout-plan-template.json"),
            ("svg-starter-light-template.svg", "layout-plan-light-template.json"),
        ):
            starter_svg = ASSETS_DIR / svg_name
            starter_plan = ASSETS_DIR / plan_name
            with tempfile.TemporaryDirectory() as td:
                out_p = pathlib.Path(td) / f"{starter_svg.stem}-out.svg"
                r_pipe = run_script("run_pipeline.py", [
                    "--svg", str(starter_svg),
                    "--plan", str(starter_plan),
                    "--output-svg", str(out_p),
                    "--strict",
                    "--json",
                ])
                self.assertEqual(r_pipe.returncode, 0, r_pipe.stdout + r_pipe.stderr)
                self.assertEqual(json.loads(r_pipe.stdout)["status"], "SUCCESS")

                r_prev = run_script("render_preview.py", [
                    "--svg", str(out_p),
                    "--platform", "wechat_article",
                    "--strict",
                    "--json",
                ])
                self.assertEqual(r_prev.returncode, 0, r_prev.stdout + r_prev.stderr)
                rep_prev = json.loads(r_prev.stdout)
                self.assertEqual(rep_prev["status"], "PASS")
                run_script("render_preview.py", ["--cleanup-dir", rep_prev["preview_dir"], "--json"])

    def test_zones_containment_overlap_and_legend_placement(self):
        with tempfile.TemporaryDirectory() as td:
            td_p = pathlib.Path(td)
            plan_p = td_p / "zone-plan.json"
            svg_p = td_p / "zone.svg"

            zone_plan = copy.deepcopy(BASE_PLAN)
            zone_plan["zones"] = [
                {
                    "id": "cluster-a",
                    "rect": {"x": 110, "y": 135, "w": 980, "h": 230},
                    "nodes": ["stage-1", "stage-2"],
                    "label": "zone-label",
                    "padding": 10,
                }
            ]
            zone_plan["text_boxes"].append({
                "id": "zone-label",
                "zone": "cluster-a",
                "role": "zone_label",
                "rect": {"x": 124, "y": 138, "w": 120, "h": 22},
            })
            zone_plan["text_boxes"].append({
                "id": "legend-item",
                "role": "legend",
                "rect": {"x": 120, "y": 400, "w": 160, "h": 22},
            })
            zone_svg = BASE_SVG.replace(
                '<g id="svga-test-stage-1"',
                '<g data-svga-zone="cluster-a"><rect x="110" y="135" width="980" height="230" rx="12" fill="#18181B" fill-opacity="0.22" stroke="#3F3F46" stroke-dasharray="8,4"/>'
                '<text x="124" y="154" font-size="16" font-family="PingFang SC, Noto Sans SC, Microsoft YaHei, system-ui, sans-serif" fill="#93C5FD" data-svga-text="zone-label">集群边界</text></g>'
                '<text x="120" y="418" font-size="16" font-family="PingFang SC, Noto Sans SC, Microsoft YaHei, system-ui, sans-serif" fill="#D4D4D8" data-svga-text="legend-item">图例：主链路</text>'
                '<g id="svga-test-stage-1"',
            )
            plan_p.write_text(json.dumps(zone_plan), encoding="utf-8")
            svg_p.write_text(zone_svg, encoding="utf-8")

            # 1. Valid zone + external legend passes full pipeline
            r_ok = run_script("run_pipeline.py", [
                "--svg", str(svg_p), "--plan", str(plan_p), "--in-place", "--strict", "--json"
            ])
            self.assertEqual(r_ok.returncode, 0, r_ok.stdout + r_ok.stderr)

            # 2. Legend placed inside zone fails with E_LEGEND_INSIDE_ZONE
            bad_legend_plan = copy.deepcopy(zone_plan)
            bad_legend_plan["text_boxes"][-1]["rect"]["y"] = 340
            plan_p.write_text(json.dumps(bad_legend_plan), encoding="utf-8")
            r_leg = run_script("validate_geometry.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            codes_leg = [e["code"] for e in json.loads(r_leg.stdout)["errors"]]
            self.assertIn("E_LEGEND_INSIDE_ZONE", codes_leg)

            # 3. Node not listed in zone.nodes overlapping zone fails with E_ZONE_OVERLAP
            unowned_plan = copy.deepcopy(zone_plan)
            unowned_plan["zones"][0]["nodes"] = ["stage-1"]
            plan_p.write_text(json.dumps(unowned_plan), encoding="utf-8")
            r_unowned = run_script("validate_geometry.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            codes_unowned = [e["code"] for e in json.loads(r_unowned.stdout)["errors"]]
            self.assertIn("E_ZONE_OVERLAP", codes_unowned)

            # 4. Node escaping zone fails with E_ZONE_CONTAINMENT
            esc_plan = copy.deepcopy(zone_plan)
            esc_plan["zones"][0]["rect"]["w"] = 600
            plan_p.write_text(json.dumps(esc_plan), encoding="utf-8")
            r_esc = run_script("validate_geometry.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            codes_esc = [e["code"] for e in json.loads(r_esc.stdout)["errors"]]
            self.assertIn("E_ZONE_CONTAINMENT", codes_esc)

    def test_semantic_architecture_color_roles(self):
        with tempfile.TemporaryDirectory() as td:
            td_p = pathlib.Path(td)
            plan_p = td_p / "sem-plan.json"
            svg_p = td_p / "sem.svg"
            sem_plan = copy.deepcopy(BASE_PLAN)
            sem_plan["color_system"]["role_map"].update({
                "gateway": "surface_gateway",
                "gateway_border": "border_gateway",
                "service": "surface_service",
                "service_border": "border_service",
            })
            sem_svg = BASE_SVG.replace(
                'fill="#111114" stroke="#27272A" data-svga-color-role="node"',
                'fill="#26141C" stroke="#FB7185" data-svga-color-role="gateway"',
            ).replace(
                'fill="#18181B" stroke="#3B82F6" data-svga-color-role="node_secondary"',
                'fill="#0F221C" stroke="#34D399" data-svga-color-role="service"',
            )
            plan_p.write_text(json.dumps(sem_plan), encoding="utf-8")
            svg_p.write_text(sem_svg, encoding="utf-8")

            r_col = run_script("validate_color.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            self.assertEqual(r_col.returncode, 0, r_col.stdout)
            r_svg = run_script("validate_svg.py", ["--svg", str(svg_p), "--plan", str(plan_p), "--strict", "--json"])
            self.assertEqual(r_svg.returncode, 0, r_svg.stdout)

    def test_wechat_article_aspect_ratio_presets_and_bounds(self):
        with tempfile.TemporaryDirectory() as td:
            td_p = pathlib.Path(td)
            for h, ratio in ((500, "2.4:1"), (675, "16:9"), (900, "4:3"), (1200, "1:1")):
                svg_p = td_p / f"preset-{h}.svg"
                plan_p = td_p / f"preset-{h}.layout.json"
                plan = copy.deepcopy(BASE_PLAN)
                plan["canvas"]["viewBox"] = f"0 0 1200 {h}"
                plan["canvas"]["aspect_ratio"] = ratio
                plan["canvas"]["safe_area"]["height"] = h - 100
                plan["slots"][0]["rect"]["h"] = h
                svg = (
                    BASE_SVG.replace('width="1200" height="500" viewBox="0 0 1200 500"', f'width="1200" height="{h}" viewBox="0 0 1200 {h}"')
                    .replace('<rect x="0" y="0" width="1200" height="500"', f'<rect x="0" y="0" width="1200" height="{h}"')
                )
                plan_p.write_text(json.dumps(plan), encoding="utf-8")
                svg_p.write_text(svg, encoding="utf-8")

                r_pipe = run_script("run_pipeline.py", [
                    "--svg", str(svg_p), "--plan", str(plan_p), "--in-place", "--strict", "--json",
                ])
                self.assertEqual(r_pipe.returncode, 0, r_pipe.stdout + r_pipe.stderr)
                r_prev = run_script("render_preview.py", [
                    "--svg", str(svg_p), "--platform", "wechat_article", "--strict", "--json",
                ])
                self.assertEqual(r_prev.returncode, 0, r_prev.stdout + r_prev.stderr)
                rep_prev = json.loads(r_prev.stdout)
                self.assertTrue(rep_prev["dimensions_match"])
                self.assertEqual(rep_prev["expected_size"]["h"], h)
                run_script("render_preview.py", ["--cleanup-dir", rep_prev["preview_dir"], "--json"])

            # Out-of-range height (> 1200) must fail dimensions_match and warn W_PLATFORM_UNKNOWN
            bad_svg_p = td_p / "too-tall.svg"
            bad_svg_p.write_text(
                BASE_SVG.replace('width="1200" height="500" viewBox="0 0 1200 500"', 'width="1200" height="1400" viewBox="0 0 1200 1400"')
                .replace('<rect x="0" y="0" width="1200" height="500"', '<rect x="0" y="0" width="1200" height="1400"'),
                encoding="utf-8",
            )
            r_bad_v = run_script("validate_svg.py", ["--svg", str(bad_svg_p), "--strict", "--json"])
            w_codes = [w["code"] for w in json.loads(r_bad_v.stdout)["warnings"]]
            self.assertIn("W_PLATFORM_UNKNOWN", w_codes)
            r_bad_p = run_script("render_preview.py", ["--svg", str(bad_svg_p), "--platform", "wechat_article", "--strict", "--json"])
            self.assertNotEqual(r_bad_p.returncode, 0)
            rep_bad = json.loads(r_bad_p.stdout)
            self.assertFalse(rep_bad["dimensions_match"])
            self.assertIn("dimensions_mismatch", rep_bad["blocking_issues"])
            run_script("render_preview.py", ["--cleanup-dir", rep_bad["preview_dir"], "--json"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
