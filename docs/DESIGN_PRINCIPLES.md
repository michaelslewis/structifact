# DESIGN_PRINCIPLES.md

# Structifact Design Principles

**Project:** Structifact
**Subtitle:** Schema-Driven Data Engineering Framework

---

# Purpose

This document describes the engineering principles that guide Structifact development.

These principles exist to ensure that as Structifact evolves, new capabilities strengthen the framework rather than turning it into a collection of disconnected automation features.

Structifact is intended to be metadata-driven, declarative, modular, transparent, reliable, and extensible.

Most of these principles were written early in the project and have since been tested by real work — computed fields, multi-source joins with deduplication, and a full three-part data quality framework. Where a principle has a concrete example demonstrating it, that's noted below; these aren't just aspirational statements anymore.

---

# 1. Metadata Is the Source of Truth

Metadata should define dataset structure and intent whenever possible.

This now extends beyond structure to *rules*: a field's required-ness, its accepted value domain, its numeric range, its format pattern, and even a dataset's relationship to another dataset are all metadata, checked by the framework — not custom validation code a user would otherwise have to write and maintain separately.

---

# 2. Declarative Over Imperative

Users should describe what they want rather than manually implementing every workflow step.

```yaml
dataset:
  name: customers

fields:
  - name: customer_id
    type: integer
    nullable: false
```

This held up under real pressure: when the data quality framework needed to check foreign-key relationships across two datasets, the declarative interface stayed simple (`--ref alias=schema.yml:data.csv`) even though the underlying resolution logic (validating the reference schema, matching its declared name, confirming the target column exists) is real work.

---

# 3. Dataset Concepts Over Implementation Concepts

Structifact should model logical data concepts rather than prematurely coupling itself to a specific storage technology.

`DatasetSpec`, not `TableSpec`. This paid off directly: a dataset can now be assembled from multiple joined sources (including the same physical table referenced multiple times under different roles) without straining a "table"-shaped model, because the IR was never built around the assumption that one dataset equals one physical table.

---

# 4. Internal Representation Is a First-Class Boundary

The Intermediate Representation (IR) is one of Structifact's most important architectural concepts, separating external formats, internal meaning, and generated outputs.

```text
Input Metadata → Adapter → Parser → IR → { Validation, Generators }
```

The IR has grown considerably (see `ARCHITECTURE.md` for the current full shape) but every addition — computed fields, sources/joins, value-level quality rules — was added *to* the IR, not by working around it.

---

# 5. Fields Describe Structure, Constraints Describe Rules

Field definitions and relational/business rules should remain separate.

```text
Primary Key            Foreign Key
customer_id             orders.customer_id references customers.customer_id
```

This prevented `FieldSpec` from becoming an ever-growing collection of unrelated flags even as real value-level rules (range, pattern) were added to it — those are genuinely intrinsic to a field ("what values may this hold"), while relationships (primary key, foreign key) stayed on `ConstraintSpec` exactly as designed.

---

# 6. Explicit Over Magic

Automation should never become mysterious. Users should understand what Structifact generated, why, where information came from, and how to modify behavior.

This principle directly shaped the data quality framework's error handling: when a schema declares a `foreign_key` relationship but the person running `validate-data` doesn't supply the `--ref` needed to check it, Structifact refuses to silently report "no issues found" — it fails loudly with a specific, actionable error, because a silent skip would be exactly the kind of hidden behavior this principle exists to prevent.

Generated artifacts also remain readable:

```sql
CREATE TABLE customers (
    customer_id INTEGER
);
```

---

# 7. Reliability Before Cleverness

Structifact should prioritize predictable behavior over impressive but fragile automation.

A concrete instance: range checking on a numeric field deliberately does *not* attempt to be clever about a value that fails to parse as a number — it's simply not reported as a range violation, on the principle that a genuinely different, not-yet-built rule (type validation) should own that case rather than range-checking silently overreaching into territory it wasn't designed for.

---

# 8. Separation of Responsibilities

Each component has a clearly defined purpose: adapters handle external formats, the IR holds framework-level concepts, validation enforces metadata rules, generators produce artifacts.

A newer, sharper instance of this principle: `structifact/quality.py` — real-data checking — was deliberately built as its own subsystem rather than extended from `validation.py` or squeezed into the `Generator` interface, because it answers a genuinely different question ("does this data conform?" vs. "is this schema well-formed?" or "what artifact does this schema produce?"). See `DECISION_HISTORY.md` for the full reasoning.

---

# 9. Extensibility Through Stable Interfaces

Future capabilities should be added through well-defined extension points.

```text
Adapters: YAML, CSV, Excel, (future: JSON, database sources)
Generators: SQL, dbt YAML, 2 catalog variants, docs, model, (future: lineage)
```

Six generators and three adapters have now been added through the same registry pattern without requiring a plugin architecture — a real, positive test of this principle holding up at meaningfully larger scale than when it was first written.

---

# 10. Avoid Premature Complexity

Structifact should evolve incrementally, only introducing capabilities the underlying architecture can support naturally.

This principle is why `foreign_key` constraints supported only single-column references for a long stretch (composite FK support was explicitly deferred, and remains deferred, until a real example needs it), and why the data quality framework's foreign-key checking assumes the whole referenced dataset fits in memory rather than building streaming/chunked processing nobody has needed yet.

---

# 11. Reproducibility and Determinism

Given the same metadata, the same input data, and the same framework version, Structifact should produce predictable results.

The data quality framework extends this into new territory: given the same schema and the same CSV, `validate-data` reports the exact same issues, in the same grouping, every time — deterministic even though the underlying check now involves things (regex matching, numeric parsing, cross-dataset membership tests) that didn't exist when this principle was first written.

---

# 12. Validation Is a Core Capability

Validation is not an optional enhancement — metadata-driven systems depend on trust in their definitions.

Worth being precise about scope here, since the project itself learned this distinction the hard way: "validation" in Structifact has always meant checking the *metadata's* well-formedness. Checking real *data* against that metadata is a related but distinct capability (`quality.py`), added later, deliberately kept separate rather than folded into `validation.py` — see `DECISION_HISTORY.md`.

---

# 13. Human-Readable Outputs

Generated artifacts should be understandable without requiring Structifact itself.

This extends naturally to the data quality report format — `validate-data`'s output reads as plain English ("customer_id 'CUST-004' appears in data rows 2 and 5"), not a machine-oriented error code, even though the underlying `QualityIssue`/`QualityResult` data is fully structured for a future machine-readable format if one's ever needed.

---

# 14. CLI as the User Boundary

The command-line interface makes the architecture tangible.

```bash
$ structifact validate customers.yml
✓ Loaded metadata
✓ Parsed 2 fields
✓ Valid schema
✓ No constraint violations
```

Now four commands, not two: `validate`, `generate`, `discover`, and `validate-data`. Each was added only once there was a real capability behind it to expose — the CLI followed capability, rather than driving it.

---

# 15. AI Should Assist, Not Replace Engineering Judgment

AI assistance is now real, shipped functionality (`discover --ai`, `discover --requirements --ai`) rather than a future exploration area — but the principle that motivated deferring it originally held up completely once it was actually built:

* AI-generated suggestions are always written to a draft file, clearly labeled, never auto-validated or auto-applied
* the deterministic core works with zero AI involvement (the one exception — `discover --requirements`, which has no non-AI path — is a property of freeform text being unparseable deterministically, not a compromise on this principle)
* AI usage is bring-your-own-key (an `ANTHROPIC_API_KEY` environment variable, never hardcoded) and built behind a provider-agnostic interface, not locked to one vendor
* every request is cost-estimated and requires explicit confirmation first; declining makes zero API calls, verified in tests

The intended pattern held exactly as designed:

```text
Unknown Dataset → AI-Assisted Discovery → Suggested Metadata → Human Review → Structifact IR → Validation + Generation
```

---

# 16. Documentation Is Part of the System

Documentation is an engineering artifact, capturing decisions so a future contributor doesn't have to reverse-engineer them from code.

This principle was tested directly: several of these documents drifted out of sync with the actual codebase for a period (still describing a removed module, still describing shipped capabilities as future work) before being deliberately refreshed. See `DECISION_HISTORY.md` for the specific instance — the fix was treating documentation refresh as its own real task, not something that happens automatically just because the principle is stated.

---

# 17. Portfolio-Quality Engineering Standards

Structifact is both a framework exploration and a demonstration of engineering capability — clean architecture, thoughtful tradeoffs, maintainable Python, meaningful tests, professional documentation, realistic engineering decisions.

The project's 279-test, CI-enforced suite and its consistent real-example-first design discipline (see `DECISION_HISTORY.md`) are the concrete evidence behind this principle, not just a stated aspiration.

---

# 18. Build Foundations Before Features

> Build the foundation that makes future features easy.

Strong foundations: stable metadata models, clear internal representations, modular architecture, reliable validation, predictable generation. Features should be added because they strengthen the framework, not simply because they're possible — which is also why Phase 6 (the data quality framework) was declared complete once it matched its originally planned scope, rather than continuing to accumulate new rule types indefinitely just because more were conceivable.

---

# Summary

Structifact is guided by a simple philosophy:

> Define structure once. Generate reliable systems from it.

Every design decision should reinforce metadata over duplication, clarity over complexity, reliability over cleverness, transparency over magic, explicit contracts over hidden behavior, and engineering discipline over shortcuts.

These principles have now been tested against real, substantial work — not just held as intentions — and have held up well. Where a principle needed refinement in practice (the metadata-validation-vs-data-validation distinction, in particular), that refinement is recorded here and in `DECISION_HISTORY.md` rather than silently absorbed.
