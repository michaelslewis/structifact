#!/usr/bin/env python3
"""
Generate a synthetic requirements document that reproduces the `discover --ai`
override-merge challenge, plus a machine-checkable ground truth.

Everything in the output is fictional. Table names and a handful of field
abbreviations below are synthetic (not real SAP codes) specifically because
they matched real SAP delivery-module terminology referenced elsewhere in
this project's own docs closely enough to be worth avoiding; the remaining
field abbreviations are ordinary, public SAP Data Dictionary codes, generic
across countless SAP implementations and not identifying on their own. No
employer content is used or required either way.

The structural challenge being reproduced:
  * fields are defined in a main section under one name prefix  (struct_<table>_<field>)
  * a LATER "Revisions" section supersedes a subset of them under a DIFFERENT
    prefix                                                       (sap_<table>_<field>)
  * correct extraction must correlate across the whole document and merge the
    revision INTO the existing field, not create a second one

This script is committed (fictional content, public field names, no IP
concern); its generated output is not -- run it with -o pointed at the
gitignored scratch/synth/out/ directory, not into the repo.

Usage (from the repo root):
  python3 tests/fixtures/discover_ai_synth/make_requirements_doc.py \\
      --fields 40 --overrides 4 -o scratch/synth/out/small/
  python3 tests/fixtures/discover_ai_synth/make_requirements_doc.py \\
      --fields 500 --overrides 12 --filler 900 -o scratch/synth/out/full/
  python3 tests/fixtures/discover_ai_synth/make_requirements_doc.py \\
      --fields 40 --overrides 4 --xlsx -o scratch/synth/out/small/

  # --hard: strip the self-explaining preamble, drop the overview's
  # forward-reference, retitle the revisions section neutrally, and place
  # it mid-document -- see DECISION_HISTORY.md's override-merge entry for
  # why the fixture without --hard undertested the real task.
  python3 tests/fixtures/discover_ai_synth/make_requirements_doc.py \\
      --fields 500 --overrides 12 --filler 900 --hard -o scratch/synth/out/full_hard/
"""

import argparse
import json
import os
import random

# ---------------------------------------------------------------- field pool
# Table names and a few field abbreviations are synthetic -- see the module
# docstring. Descriptions below are invented either way.
TABLES = {
    "DELIVHDR": ("Delivery Header", [
        ("DOCNUM", "Delivery document number"),
        ("ERNAM", "Name of the user who created the record"),
        ("ERDAT", "Date on which the record was created"),
        ("VSTEL", "Shipping point or receiving point"),
        ("LFART", "Delivery document type"),
        ("KUNNR", "Ship-to party account number"),
        ("STATGROUP", "Update group for statistics update"),
        ("VKORG", "Sales organization"),
        ("LFDAT", "Delivery date"),
        ("WADAT", "Goods movement date"),
        ("ROUTE", "Shipping route"),
        ("BTGEW", "Total weight of the delivery"),
        ("NTGEW", "Net weight of the delivery"),
        ("GEWEI", "Weight unit of measure"),
        ("VOLUM", "Volume of the delivery"),
        ("VOLEH", "Volume unit of measure"),
        ("ANZPK", "Number of packages in the delivery"),
        ("INCO1", "Incoterms part one"),
        ("INCO2", "Incoterms part two"),
        ("TDDAT", "Transportation planning date"),
    ]),
    "DELIVITEM": ("Delivery Item", [
        ("ITEMNUM", "Delivery item number"),
        ("MATNR", "Material number"),
        ("WERKS", "Plant supplying the item"),
        ("LGORT", "Storage location"),
        ("CHARG", "Batch number"),
        ("LFIMG", "Actual quantity delivered in sales units"),
        ("MEINS", "Base unit of measure"),
        ("UMVKZ", "Numerator for unit conversion"),
        ("UPDFLOW", "Subsequent document flow indicator"),
        ("VGBEL", "Reference document number of the preceding document"),
        ("VGPOS", "Reference item number of the preceding document"),
        ("PSTYV", "Delivery item category"),
        ("ITEMTEXT", "Short text describing the sales order item"),
        ("NETWR", "Net value of the delivery item"),
        ("WAERK", "Document currency"),
        ("MATKL", "Material group"),
        ("PRCTR", "Profit center assigned to the item"),
        ("KOSTL", "Cost center assigned to the item"),
        ("BWART", "Movement type for inventory management"),
        ("SOBKZ", "Special stock indicator"),
    ]),
    "HDRSTATUS": ("Header Status", [
        ("MOVESTAT", "Total goods movement status"),
        ("KOSTK", "Overall picking or putaway status"),
        ("LFSTK", "Delivery status at header level"),
        ("GBSTK", "Overall processing status of the document"),
        ("FKSTK", "Billing status at header level"),
        ("TRSTA", "Transportation planning status"),
        ("PKSTK", "Packing status at header level"),
        ("UVALL", "Incompleteness status for the whole document"),
    ]),
    "ITEMSTATUS": ("Item Status", [
        ("LINESTAT", "Delivery status at item level"),
        ("WBSTA", "Goods movement status at item level"),
        ("KOSTA", "Picking or putaway status at item level"),
        ("FKSTA", "Billing status at item level"),
        ("UVALS", "Incompleteness status for the item"),
        ("PKSTA", "Packing status at item level"),
    ]),
}

def infer_type_role(abbr, desc):
    """Type/role must follow the field's own meaning.

    Random assignment would put `decimal / measure` on a date field, adding a
    second, unrelated difficulty to a document meant to isolate exactly one:
    the override merge.
    """
    a, d = abbr.upper(), desc.lower()
    if "DAT" in a or "date" in d:
        return "date", "dimension"
    if any(k in d for k in ("weight", "volume", "value", "amount", "quantity")):
        return "decimal", "measure"
    # word-boundary check: "account number" must not match on "count"
    words = d.replace("-", " ").split()
    if d.startswith("number of") or "count" in words:
        return "integer", "measure"
    if any(k in d for k in ("numerator", "conversion")):
        return "decimal", "measure"
    return "string", "dimension"

FILLER_PARAGRAPHS = [
    "Records are loaded on a nightly schedule and must be available before the "
    "reporting window opens the following business morning.",
    "Any row failing a mandatory-field check is routed to the exception queue "
    "rather than being silently discarded.",
    "Historical values are retained for seven fiscal years in line with the "
    "retention policy agreed with the finance team.",
    "Where a source system supplies a blank value for an optional attribute, the "
    "blank is preserved rather than being substituted with a default.",
    "Downstream consumers should not assume ordering; the extract is not sorted.",
    "Currency amounts are carried in document currency and converted downstream.",
    "Unit-of-measure conversions are handled by the consuming layer, not here.",
    "Duplicate keys are not expected; if encountered, the load should fail loudly.",
]

REVISION_NOTES = [
    "Description clarified following review with the business analyst.",
    "Wording aligned with the definition used in the finance data dictionary.",
    "Updated after the source system upgrade changed the field semantics.",
    "Corrected: the previous description referred to the wrong status level.",
    "Revised to match the terminology used in the downstream Tableau workbook.",
    "Amended following feedback from the quarter-end reconciliation review.",
]


def build(n_fields, n_overrides, n_filler, seed):
    rng = random.Random(seed)

    # Flatten the pool, cycling if the caller asked for more fields than exist.
    pool = []
    for table, (label, fields) in TABLES.items():
        for abbr, desc in fields:
            pool.append({"table": table, "table_label": label,
                         "abbr": abbr, "desc": desc})

    chosen = []
    i = 0
    while len(chosen) < n_fields:
        base = pool[i % len(pool)]
        gen = i // len(pool)
        entry = dict(base)
        if gen:  # disambiguate when cycling past the pool size
            entry["abbr"] = f"{base['abbr']}{gen}"
            entry["desc"] = f"{base['desc']} (variant {gen})"
        entry["name"] = f"struct_{entry['table'].lower()}_{entry['abbr'].lower()}"
        entry["type"], entry["role"] = infer_type_role(entry["abbr"], entry["desc"])
        chosen.append(entry)
        i += 1

    # Overrides are spread across the document, never only at the start.
    n_overrides = min(n_overrides, len(chosen))
    idxs = sorted(rng.sample(range(len(chosen)), n_overrides))
    overrides = []
    for k, idx in enumerate(idxs):
        f = chosen[idx]
        overrides.append({
            "target_name": f["name"],
            # THE CHALLENGE: revision section uses a DIFFERENT prefix
            "revision_name": f"sap_{f['table'].lower()}_{f['abbr'].lower()}",
            "table": f["table"],
            "abbr": f["abbr"],
            "new_desc": f"{f['desc']}, restated for the revised specification",
            "comment": rng.choice(REVISION_NOTES),
        })

    return chosen, overrides


def render_revisions(L, overrides, hard):
    """The revisions table.

    In default mode the section explains itself ("these supersede... they are
    not additional fields"). That sentence IS the hint the task requires, so a
    document containing it measures instruction-following, not the correlation
    problem a real document poses. `hard` removes it and gives the section a
    neutral title, which is how a real business document actually reads.
    """
    if hard:
        L.append("## Appendix B — Updated Entries")
        L.append("")
        L.append("| Source Field | Field Reference | Description | Note |")
        L.append("| --- | --- | --- | --- |")
    else:
        L.append("## 4. Revisions")
        L.append("")
        L.append("The following entries **supersede** the corresponding definitions "
                 "in Section 2. Where a field appears below, the description given "
                 "here replaces the one above, and the note is carried as a comment "
                 "on the field. These are revisions to existing fields — they are "
                 "not additional fields.")
        L.append("")
        L.append("| Source Field | Field Reference | Revised Description | Note |")
        L.append("| --- | --- | --- | --- |")
    for o in overrides:
        L.append(f"| {o['abbr']} | {o['revision_name']} | "
                 f"{o['new_desc']} | {o['comment']} |")
    L.append("")


def render_filler(L, n, rng, prefix, first=1):
    for k in range(n):
        L.append(f"### {prefix}{first + k} Note")
        L.append("")
        L.append(rng.choice(FILLER_PARAGRAPHS))
        L.append("")


def render_markdown(chosen, overrides, n_filler, rng, hard=False):
    L = []
    L.append("# Delivery Reporting Extract — Requirements Specification")
    L.append("")
    L.append("## 1. Overview")
    L.append("")
    if hard:
        # No forward-reference to the revisions section either — pointing at it
        # from the overview is another form of the same hint.
        L.append("This document specifies the fields required for the delivery "
                 "reporting extract, together with the processing notes agreed "
                 "with the reporting team.")
    else:
        L.append("This document specifies the fields required for the delivery "
                 "reporting extract. Section 2 defines each field. Section 4 lists "
                 "revisions agreed after the initial specification was circulated.")
    L.append("")
    L.append("## 2. Field Definitions")
    L.append("")

    by_table = {}
    for f in chosen:
        by_table.setdefault((f["table"], f["table_label"]), []).append(f)

    for (table, label), fields in by_table.items():
        L.append(f"### 2.{list(by_table).index((table, label)) + 1} {table} — {label}")
        L.append("")
        L.append("| Source Field | Output Name | Type | Role | Description |")
        L.append("| --- | --- | --- | --- | --- |")
        for f in fields:
            L.append(f"| {f['abbr']} | {f['name']} | {f['type']} | "
                     f"{f['role']} | {f['desc']} |")
        L.append("")

    L.append("## 3. Processing Notes")
    L.append("")

    if hard:
        # Revisions land MID-document, with filler after, so the model must
        # carry them while continuing to read — matching the real document,
        # where the override section sat roughly halfway through.
        half = n_filler // 2
        render_filler(L, half, rng, prefix="3.")
        render_revisions(L, overrides, hard=True)
        L.append("## Appendix C — Further Processing Notes")
        L.append("")
        render_filler(L, n_filler - half, rng, prefix="C.")
    else:
        render_filler(L, n_filler, rng, prefix="3.")
        render_revisions(L, overrides, hard=False)

    return "\n".join(L)


def ground_truth(chosen, overrides):
    omap = {o["target_name"]: o for o in overrides}
    fields = []
    for f in chosen:
        o = omap.get(f["name"])
        fields.append({
            "name": f["name"],
            "type": f["type"],
            "role": f["role"],
            "description": o["new_desc"] if o else f["desc"],
            # The pre-revision text, kept so the scorer can tell "kept the
            # original" apart from "applied the revision". The revised string
            # contains the original as a prefix, so a substring test alone
            # matches both and silently collapses F-IGNORE into F-PARTIAL.
            "original_description": f["desc"],
            "comment": o["comment"] if o else None,
            "was_overridden": bool(o),
            "must_not_appear": o["revision_name"] if o else None,
        })
    return {
        "field_count": len(fields),
        "override_count": len(overrides),
        "fields": fields,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fields", type=int, default=40)
    p.add_argument("--overrides", type=int, default=4)
    p.add_argument("--filler", type=int, default=8,
                   help="Processing-note sections between definitions and revisions. "
                        "Increases the span the model must correlate across.")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--hard", action="store_true",
                   help="Remove the self-explaining revisions preamble and place the "
                        "revisions table mid-document with content after it. Closer to "
                        "how a real requirements document reads. Without this, the "
                        "document states outright that the entries supersede earlier "
                        "ones — which is the hint the task requires, making it a test "
                        "of instruction-following rather than correlation.")
    p.add_argument("--xlsx", action="store_true", help="Also emit an .xlsx version")
    p.add_argument("-o", "--outdir", default="out")
    a = p.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    rng = random.Random(a.seed)
    chosen, overrides = build(a.fields, a.overrides, a.filler, a.seed)

    md = render_markdown(chosen, overrides, a.filler, rng, hard=a.hard)
    stem = (f"delivery_spec_{a.fields}f_{a.overrides}o_seed{a.seed}"
            + ("_hard" if a.hard else ""))
    md_path = os.path.join(a.outdir, stem + ".md")
    with open(md_path, "w") as fh:
        fh.write(md)

    gt = ground_truth(chosen, overrides)
    gt_path = os.path.join(a.outdir, stem + ".groundtruth.json")
    with open(gt_path, "w") as fh:
        json.dump(gt, fh, indent=2)

    print(f"document      : {md_path}")
    print(f"ground truth  : {gt_path}")
    print(f"fields        : {gt['field_count']}")
    print(f"overrides     : {gt['override_count']}")
    print(f"approx tokens : ~{len(md)//4:,}")

    if a.xlsx:
        try:
            from openpyxl import Workbook
        except ImportError:
            print("!! openpyxl not installed; skipping .xlsx "
                  "(pip install openpyxl)")
            return
        wb = Workbook()
        ws = wb.active
        ws.title = "Field Definitions"
        ws.append(["Source Field", "Output Name", "Type", "Role", "Description"])
        for f in chosen:
            ws.append([f["abbr"], f["name"], f["type"], f["role"], f["desc"]])
        ws2 = wb.create_sheet("Revisions")
        ws2.append(["Source Field", "Field Reference", "Revised Description", "Note"])
        ws2.append(["These entries supersede the Field Definitions sheet.",
                    "", "", ""])
        for o in overrides:
            ws2.append([o["abbr"], o["revision_name"], o["new_desc"], o["comment"]])
        xp = os.path.join(a.outdir, stem + ".xlsx")
        wb.save(xp)
        print(f"xlsx          : {xp}")


if __name__ == "__main__":
    main()
