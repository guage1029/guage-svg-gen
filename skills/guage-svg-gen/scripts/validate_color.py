#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Validate SVG colors against the selected diagram-safe theme tokens."""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HEX_RE = re.compile(r"^#[0-9a-f]{6}$", re.I)
ATTRS = ("fill", "stroke", "stop-color", "color")
THEME_ALIASES = {"dark": "bg_dark", "light": "bg_light"}
EPILOG = """Examples:
  python3 scripts/validate_color.py --svg out.svg --plan out.layout.json --strict --json

Exit codes:
  0  PASS (all hex colors and data-svga-color-role attributes match theme tokens)
  1  FAIL (unmapped role, unknown token, raw hex outside theme, or XML error)
"""


def fail(code, message):
    return {"code": code, "message": message}


def main():
    parser = argparse.ArgumentParser(
        description="Validate SVG hex colors and color roles against assets/color-tokens.json.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--svg", required=True, help="Path to SVG file")
    parser.add_argument("--plan", required=True, help="Path to layout plan JSON")
    parser.add_argument(
        "--tokens",
        default=str(Path(__file__).resolve().parent.parent / "assets" / "color-tokens.json"),
        help="Path to color-tokens.json (default: assets/color-tokens.json)",
    )
    parser.add_argument("--strict", action="store_true", help="Enable strict checking")
    parser.add_argument("--json", action="store_true", help="Emit JSON report to stdout")
    args = parser.parse_args()

    errors = []
    token_data = json.loads(Path(args.tokens).read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    color_system = plan.get("color_system", {})
    raw_theme = color_system.get("theme", token_data.get("default_theme"))
    theme_name = THEME_ALIASES.get(raw_theme, raw_theme)
    theme = token_data.get("themes", {}).get(theme_name)
    if not theme:
        avail_themes = ", ".join(sorted(list(token_data.get("themes", {}).keys()) + list(THEME_ALIASES.keys())))
        errors.append(fail("E_COLOR_THEME_UNKNOWN", f"Unknown color theme: {raw_theme!r}. Available themes: {avail_themes}"))
    else:
        tokens = dict(theme.get("tokens", {}))
        custom_tokens = color_system.get("custom_tokens", {})
        if isinstance(custom_tokens, dict):
            for k, v in custom_tokens.items():
                if isinstance(v, str) and HEX_RE.match(v):
                    tokens[k] = v
        palette = plan.get("palette", {})
        allowed = {value.lower() for value in tokens.values() if isinstance(value, str) and HEX_RE.match(value)}
        if isinstance(palette, dict):
            for pv in palette.values():
                if isinstance(pv, str) and HEX_RE.match(pv):
                    allowed.add(pv.lower())
        role_map = color_system.get("role_map", {})
        for role, token_name in role_map.items():
            if token_name not in tokens:
                errors.append(fail(
                    "E_COLOR_TOKEN_UNKNOWN",
                    f"Role {role!r} references unknown token {token_name!r} in theme {theme_name!r}. Available tokens: {', '.join(sorted(tokens.keys()))}",
                ))

        diagram_type = color_system.get("diagram_type")
        if diagram_type and diagram_type not in token_data.get("diagram_types", {}):
            avail_types = ", ".join(sorted(token_data.get("diagram_types", {}).keys()))
            errors.append(fail("E_DIAGRAM_TYPE_UNKNOWN", f"Unknown diagram type: {diagram_type!r}. Available types: {avail_types}"))

        try:
            root = ET.parse(args.svg).getroot()
        except ET.ParseError as exc:
            errors.append(fail("E_XML_PARSE", str(exc)))
            root = None

        if root is not None:
            declared_roles = ", ".join(sorted(role_map.keys())) or "(none)"
            for elem in root.iter():
                for attr in ATTRS:
                    value = elem.attrib.get(attr, "").strip().lower()
                    if HEX_RE.match(value) and value not in allowed:
                        errors.append(fail(
                            "E_COLOR_RAW_UNAPPROVED",
                            f'{attr}="{value}" is not an approved token hex in theme {theme_name!r} (see assets/color-tokens.json)',
                        ))
                role = elem.attrib.get("data-svga-color-role")
                if role and role not in role_map:
                    errors.append(fail(
                        "E_COLOR_ROLE_UNMAPPED",
                        f"data-svga-color-role={role!r} has no mapping in color_system.role_map. Declared roles: {declared_roles}",
                    ))

    report = {
        "status": "PASS" if not errors else "FAIL",
        "theme": theme_name,
        "errors": errors,
        "checked": {"svg": str(Path(args.svg).resolve()), "plan": str(Path(args.plan).resolve())},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else report["status"])
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
