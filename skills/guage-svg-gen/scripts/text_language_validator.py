#!/usr/bin/env python3
"""Enforce the skill's Chinese-first visible-text policy."""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+#./:-]*")
def error(code, message, text_id=None):
    item = {"code": code, "message": message}
    if text_id:
        item["text_id"] = text_id
    return item


def visible_text_nodes(root):
    nodes = []
    for elem in root.iter():
        tag = elem.tag.split("}")[-1].lower()
        if tag in {"title", "desc"} or (tag == "text" and elem.attrib.get("data-svga-text")):
            nodes.append((elem, elem.attrib.get("data-svga-text", tag)))
    return nodes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--svg", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--policy", default=str(Path(__file__).resolve().parent.parent / "references" / "language_policy.json"))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    language = plan.get("metadata", {}).get("language", policy.get("default_language", "zh"))
    errors = []

    if language not in {"zh", "en", "mixed"}:
        errors.append(error("E_LANGUAGE_INVALID", f"Unsupported metadata.language: {language}"))

    try:
        root = ET.parse(args.svg).getroot()
    except ET.ParseError as exc:
        errors.append(error("E_XML_PARSE_FAIL", str(exc)))
        root = None

    preserved = {term.lower() for term in policy.get("preserve_terms", [])}
    allowed_kinds = set(policy.get("preserve_kinds", []))
    if root is not None and language == "zh":
        for elem, text_id in visible_text_nodes(root):
            text = "".join(elem.itertext()).strip()
            if not text:
                continue
            kind = elem.attrib.get("data-svga-text-kind")
            if kind and kind not in allowed_kinds:
                errors.append(error("E_LANGUAGE_KIND_INVALID", f"Unsupported text kind: {kind}", text_id))
                continue
            if kind in allowed_kinds:
                continue
            tokens = ASCII_TOKEN_RE.findall(text)
            unknown = [token for token in tokens if token.lower() not in preserved]
            if unknown:
                errors.append(error(
                    "E_LANGUAGE_DEFAULT_NOT_ZH",
                    f"Visible text contains non-allowlisted English in zh mode: {', '.join(unknown)}",
                    text_id,
                ))

    report = {
        "status": "PASS" if not errors else "FAIL",
        "language": language,
        "errors": errors,
        "checked": {"svg": str(Path(args.svg).resolve()), "plan": str(Path(args.plan).resolve())},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else report["status"])
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
