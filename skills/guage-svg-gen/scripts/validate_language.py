#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Enforce the skill's Chinese-first visible-text policy."""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+#./:-]*")
EPILOG = """Examples:
  python3 scripts/validate_language.py --svg out.svg --plan out.layout.json --strict --json

Exit codes:
  0  PASS (all visible text complies with metadata.language policy)
  1  FAIL (unapproved English tokens, invalid data-svga-text-kind, or XML error)
"""
def error(code, message, text_id=None):
    item = {"code": code, "message": message}
    if text_id:
        item["text_id"] = text_id
    return item


def local_tag(elem):
    return elem.tag.split("}")[-1].lower()


def visible_text_nodes(root):
    nodes = []
    for elem in root.iter():
        tag = local_tag(elem)
        if tag in {"title", "desc", "text"}:
            nodes.append((elem, elem.attrib.get("data-svga-text", tag)))
    return nodes


def has_tspan_kind(elem):
    return any(
        child is not elem and local_tag(child) == "tspan" and "data-svga-text-kind" in child.attrib
        for child in elem.iter()
    )


def iter_annotated_segments(elem, active_kind=None, honor_root_kind=True):
    """Yield (text, kind) pairs respecting per-tspan data-svga-text-kind."""
    elem_kind = elem.attrib.get("data-svga-text-kind") if honor_root_kind else None
    current_kind = elem_kind if elem_kind is not None else active_kind
    if elem.text:
        yield elem.text, current_kind
    for child in elem:
        if local_tag(child) == "tspan":
            yield from iter_annotated_segments(child, active_kind=current_kind, honor_root_kind=True)
        else:
            child_text = "".join(child.itertext())
            if child_text:
                yield child_text, current_kind
        if child.tail:
            yield child.tail, current_kind


def check_fragment(text, kind, text_id, preserved, allowed_kinds, translate_map, errors):
    cleaned = text.strip()
    if not cleaned:
        return
    if kind:
        if kind not in allowed_kinds:
            errors.append(error(
                "E_LANGUAGE_KIND_INVALID",
                f"Unsupported text kind: {kind!r}. Allowed kinds: {', '.join(sorted(allowed_kinds))}",
                text_id,
            ))
        return
    tokens = ASCII_TOKEN_RE.findall(cleaned)
    unknown = [token for token in tokens if token.lower() not in preserved]
    if unknown:
        annotated = []
        for tok in unknown:
            suggestion = translate_map.get(tok.lower())
            annotated.append(f"{tok} (suggest: '{suggestion}')" if suggestion else tok)
        errors.append(error(
            "E_LANGUAGE_DEFAULT_NOT_ZH",
            f"Visible text contains non-allowlisted English in zh mode: {', '.join(annotated)}. "
            f"Translate generic English or wrap technical terms in <tspan data-svga-text-kind='...'>.",
            text_id,
        ))


def main():
    parser = argparse.ArgumentParser(
        description="Validate SVG visible text against Chinese-first language policy.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--svg", required=True, help="Path to SVG file")
    parser.add_argument("--plan", required=True, help="Path to layout plan JSON")
    parser.add_argument(
        "--policy",
        default=str(Path(__file__).resolve().parent.parent / "assets" / "language-policy.json"),
        help="Path to language-policy.json (default: assets/language-policy.json)",
    )
    parser.add_argument("--strict", action="store_true", help="Enable strict checking")
    parser.add_argument("--json", action="store_true", help="Emit JSON report to stdout")
    args = parser.parse_args()

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    language = plan.get("metadata", {}).get("language", policy.get("default_language", "zh"))
    errors = []

    if language not in {"zh", "en", "mixed"}:
        errors.append(error("E_LANGUAGE_INVALID", f"Unsupported metadata.language: {language} (expected: zh, en, mixed)"))

    try:
        root = ET.parse(args.svg).getroot()
    except ET.ParseError as exc:
        errors.append(error("E_XML_PARSE_FAIL", str(exc)))
        root = None

    preserved = {term.lower() for term in policy.get("preserve_terms", [])}
    allowed_kinds = set(policy.get("preserve_kinds", []))
    translate_map = {k.lower(): v for k, v in policy.get("translate_terms", {}).items()}
    proper_noun_examples = {k.lower(): v for k, v in policy.get("proper_noun_examples", {}).items()}
    require_zh_for_proper = bool(policy.get("proper_noun_requires_zh_annotation", True))
    cjk_re = re.compile(r"[\u4e00-\u9fff]")
    if root is not None and language == "zh":
        for elem, text_id in visible_text_nodes(root):
            tag = local_tag(elem)
            elem_kind = elem.attrib.get("data-svga-text-kind")
            if elem_kind and elem_kind not in allowed_kinds:
                errors.append(error(
                    "E_LANGUAGE_KIND_INVALID",
                    f"Unsupported text kind: {elem_kind!r}. Allowed kinds: {', '.join(sorted(allowed_kinds))}",
                    text_id,
                ))
                continue
            if has_tspan_kind(elem):
                for segment_text, segment_kind in iter_annotated_segments(elem, active_kind=None, honor_root_kind=False):
                    check_fragment(segment_text, segment_kind, text_id, preserved, allowed_kinds, translate_map, errors)
            else:
                check_fragment("".join(elem.itertext()), elem_kind, text_id, preserved, allowed_kinds, translate_map, errors)

            # In zh mode, visible <text> elements using proper_noun / professional_term must include a Chinese annotation
            if require_zh_for_proper and tag == "text":
                full_text = "".join(elem.itertext()).strip()
                used_kinds = {
                    node.attrib.get("data-svga-text-kind")
                    for node in elem.iter()
                    if node.attrib.get("data-svga-text-kind")
                }
                if used_kinds & {"proper_noun", "professional_term"} and full_text and not cjk_re.search(full_text):
                    example_hint = proper_noun_examples.get(full_text.lower(), f"{full_text} 服务/组件")
                    errors.append(error(
                        "E_LANGUAGE_DEFAULT_NOT_ZH",
                        f"Proper noun or technical term {full_text!r} in <text> lacks a Chinese annotation in zh mode. "
                        f"Pair it with its Chinese role in the same <text> (e.g. '<tspan data-svga-text-kind=\"proper_noun\">{full_text}</tspan><tspan>（或中文注：{example_hint}）</tspan>').",
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
