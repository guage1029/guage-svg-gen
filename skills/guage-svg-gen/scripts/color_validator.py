#!/usr/bin/env python3
"""Validate SVG colors against the selected diagram-safe theme tokens."""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HEX_RE = re.compile(r"^#[0-9a-f]{6}$", re.I)
ATTRS = ("fill", "stroke", "stop-color", "color")


def fail(code, message):
    return {"code": code, "message": message}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--svg", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--tokens", default=str(Path(__file__).resolve().parent.parent / "references" / "color_tokens.json"))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    errors = []
    token_data = json.loads(Path(args.tokens).read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    color_system = plan.get("color_system", {})
    theme_name = color_system.get("theme", token_data.get("default_theme"))
    theme = token_data.get("themes", {}).get(theme_name)
    if not theme:
        errors.append(fail("E_COLOR_THEME_UNKNOWN", f"Unknown color theme: {theme_name}"))
    else:
        tokens = theme.get("tokens", {})
        allowed = {value.lower() for value in tokens.values() if HEX_RE.match(value)}
        role_map = color_system.get("role_map", {})
        for role, token_name in role_map.items():
            if token_name not in tokens:
                errors.append(fail("E_COLOR_TOKEN_UNKNOWN", f"Role {role!r} references unknown token {token_name!r}"))

        diagram_type = color_system.get("diagram_type")
        if diagram_type and diagram_type not in token_data.get("diagram_types", {}):
            errors.append(fail("E_DIAGRAM_TYPE_UNKNOWN", f"Unknown diagram type: {diagram_type}"))

        try:
            root = ET.parse(args.svg).getroot()
        except ET.ParseError as exc:
            errors.append(fail("E_XML_PARSE", str(exc)))
            root = None

        if root is not None:
            for elem in root.iter():
                for attr in ATTRS:
                    value = elem.attrib.get(attr, "").strip().lower()
                    if HEX_RE.match(value) and value not in allowed:
                        errors.append(fail("E_COLOR_RAW_UNAPPROVED", f'{attr}="{value}" is not a token in theme {theme_name}'))
                role = elem.attrib.get("data-svga-color-role")
                if role and role not in role_map:
                    errors.append(fail("E_COLOR_ROLE_UNMAPPED", f"data-svga-color-role={role!r} has no plan mapping"))

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
