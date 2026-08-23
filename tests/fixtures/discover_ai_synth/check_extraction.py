#!/usr/bin/env python3
"""
Score a `discover --ai` draft schema against the synthetic document's ground truth
and emit one outcome code per overridden field.

Removes manual inspection from the measurement loop: 13 runs scored identically,
by the same rule, with no judgement call per run.

Usage:
  python3 check_extraction.py draft.yml spec.groundtruth.json
  python3 check_extraction.py draft.yml spec.groundtruth.json --json
"""

import argparse
import json
import sys

try:
    import yaml
except ImportError:
    sys.exit("pyyaml required:  pip install pyyaml")

# OK        later revision correctly merged into the existing field
# F-IGNORE  field present, original description kept, revision dropped
# F-DUP     a SECOND field created under the revision's own name
# F-PARTIAL description updated but comment missing (or vice versa)
# F-DROP    field absent entirely
# F-OTHER   present but matches nothing above


def load_fields(path):
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    if isinstance(doc, dict):
        for key in ("fields", "columns"):
            if isinstance(doc.get(key), list):
                return doc[key], doc
        for v in doc.values():
            if isinstance(v, dict) and isinstance(v.get("fields"), list):
                return v["fields"], doc
    if isinstance(doc, list):
        return doc, doc
    return [], doc


def norm(s):
    return " ".join(str(s or "").lower().split())


def classify(gt_field, by_name):
    name = gt_field["name"]
    dup_name = gt_field["must_not_appear"]
    got = by_name.get(name)
    dup = by_name.get(dup_name) if dup_name else None

    if got is None and dup is not None:
        return "F-DUP", f"only '{dup_name}' present; '{name}' absent"
    if got is None:
        return "F-DROP", f"'{name}' absent from draft"
    if dup is not None:
        return "F-DUP", f"both '{name}' and '{dup_name}' present"

    want_desc = norm(gt_field["description"])
    orig_desc = norm(gt_field.get("original_description"))
    want_comment = norm(gt_field["comment"])
    have_desc = norm(got.get("description"))
    have_comment = norm(got.get("comment"))

    # The revised description contains the original as a prefix, so test for the
    # revision-only remainder rather than plain containment — otherwise a draft
    # that kept the original scores as though it applied the revision.
    revision_tail = want_desc[len(orig_desc):].strip(" ,") if (
        orig_desc and want_desc.startswith(orig_desc)) else want_desc
    desc_applied = bool(revision_tail) and revision_tail in have_desc
    desc_is_original = bool(have_desc) and not desc_applied and (
        have_desc == orig_desc or orig_desc in have_desc)

    comment_ok = bool(want_comment) and bool(have_comment) and (
        want_comment in have_comment or have_comment in want_comment)

    if desc_applied and comment_ok:
        return "OK", ""
    # Distinct third shape seen on the real excerpt: original description kept,
    # and the revision's replacement text misfiled into `comment` instead.
    if desc_is_original and revision_tail and revision_tail in have_comment:
        return "F-MISFILE", "revised description misfiled into comment"
    if desc_applied or comment_ok:
        missing = "comment" if desc_applied else "description"
        return "F-PARTIAL", f"revised {missing} not applied"
    if desc_is_original:
        return "F-IGNORE", "original description retained; revision not applied"
    return "F-OTHER", f"desc={have_desc[:60]!r} comment={have_comment[:60]!r}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("draft")
    p.add_argument("ground_truth")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    fields, raw = load_fields(a.draft)
    with open(a.ground_truth) as fh:
        gt = json.load(fh)

    by_name = {}
    for f in fields:
        if isinstance(f, dict) and f.get("name"):
            by_name[str(f["name"])] = f

    results = []
    for g in gt["fields"]:
        if not g["was_overridden"]:
            continue
        code, note = classify(g, by_name)
        results.append({"field": g["name"], "outcome": code, "detail": note})

    counts = {}
    for r in results:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1

    # A confident-but-false success claim is a distinct defect from the merge
    # failure itself: a reviewer trusting the note has no reason to check.
    notes_text = ""
    if isinstance(raw, dict):
        for k in ("unresolved_notes", "notes", "unresolved"):
            if raw.get(k):
                notes_text = str(raw[k])
                break
    false_success = bool(notes_text) and any(
        kw in notes_text.lower()
        for kw in ("all revisions", "all overrides", "have been applied",
                   "fully applied", "no unresolved")
    ) and counts.get("OK", 0) < len(results)

    run_outcome = "OK" if counts.get("OK", 0) == len(results) else (
        max(((c, n) for c, n in counts.items() if c != "OK"),
            key=lambda x: x[1])[0] if counts else "F-DROP")

    if a.json:
        print(json.dumps({
            "run_outcome": run_outcome,
            "fields_total": len(fields),
            "overrides_checked": len(results),
            "counts": counts,
            "false_success_claim": false_success,
            "per_field": results,
        }, indent=2))
        return

    print(f"fields in draft      : {len(fields)}  (expected {gt['field_count']})")
    print(f"overrides checked    : {len(results)}")
    print(f"outcome counts       : {counts}")
    print(f"false success claim  : {'YES — ' + notes_text[:90] if false_success else 'no'}")
    print(f"RUN OUTCOME          : {run_outcome}")
    print()
    for r in results:
        line = f"  {r['outcome']:<10} {r['field']}"
        if r["detail"]:
            line += f"   — {r['detail']}"
        print(line)


if __name__ == "__main__":
    main()
