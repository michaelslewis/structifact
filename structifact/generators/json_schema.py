import json
from decimal import Decimal

from .base import Generator, Artifact
from ..ir import DatasetSpec


# JSON Schema's current core specification (2020-12) — the latest
# stable draft as of this writing, and the one every mainstream
# validator (ajv, jsonschema, etc.) already tracks. Structifact has no
# reason to pin an older draft: nothing generated here reaches into
# draft-specific corners (no $ref, no conditional/if-then-else
# vocabulary), so there's no compatibility trade-off being made either
# way — this is simply "declare the spec you're actually targeting."
JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"

# Straight mapping from Structifact's own normalized type vocabulary
# (structifact/types.py's TYPE_MAP values) to JSON Schema's primitive
# types, per the build plan (scratch/BUILD_PLAN.md, Step 2 — "Step,"
# not "Phase": see docs/DECISION_HISTORY.md's "Two Different Numbering
# Systems Both Called 'Phase'" entry). Both
# `decimal` and `float` map to `number` — JSON Schema (like JSON
# itself) has no separate fixed-point numeric type the way SQL does,
# so `SQL_TYPE_MAP`'s decimal/float distinction has nothing to land on
# here.
#
# "unknown" is deliberately absent from this map rather than mapped to
# some default (e.g. sql.py's TEXT fallback) — see `_field_schema`
# below for why.
JSON_SCHEMA_TYPE_MAP = {
    "string": "string",
    "integer": "integer",
    "decimal": "number",
    "float": "number",
    "boolean": "boolean",
    "date": "string",
    "timestamp": "string",
}

# JSON Schema's Format vocabulary defines "date" and "date-time"
# tokens for exactly Structifact's `date`/`timestamp` types (the
# vocabulary is annotation-only by default — it documents intent but
# isn't enforced unless a validator opts into format assertion, so
# adding it never makes previously-valid data fail validation). Left
# unmapped, both types would otherwise be indistinguishable from a
# plain `string` field, silently discarding information Structifact
# already has. This is the one place this generator emits something
# beyond the build plan's literal field list (type/nullable/
# accepted_values/min_value/max_value/pattern) — justified because it
# uses JSON Schema's own designated slot for this exact information,
# rather than inventing a new one.
JSON_SCHEMA_FORMAT_MAP = {
    "date": "date",
    "timestamp": "date-time",
}


def _json_number(value: Decimal):
    """
    Decimal isn't directly JSON-serializable (json.dumps raises
    TypeError on one), so min_value/max_value need converting to a
    native int or float first. Emitting a whole-valued bound (e.g.
    Decimal("100")) as `100` rather than `100.0` matters for an
    `integer`-typed field, where a JSON Schema validator would reject
    `"minimum": 100.0` paired with `"type": "integer"` on some
    implementations' strict interpretations — checking
    `value == value.to_integral_value()` (Decimal-to-Decimal, so exact,
    no float round-trip involved) picks int whenever the value has no
    fractional part, regardless of which field type it's attached to.
    """
    if value == value.to_integral_value():
        return int(value)

    return float(value)


def _field_schema(f) -> dict:
    schema = {}

    json_type = JSON_SCHEMA_TYPE_MAP.get(f.type)
    if json_type is not None:
        schema["type"] = json_type

    json_format = JSON_SCHEMA_FORMAT_MAP.get(f.type)
    if json_format is not None:
        schema["format"] = json_format

    if f.description:
        schema["description"] = f.description

    if f.accepted_values:
        schema["enum"] = list(f.accepted_values)

    if f.min_value is not None:
        schema["minimum"] = _json_number(f.min_value)

    if f.max_value is not None:
        schema["maximum"] = _json_number(f.max_value)

    if f.pattern:
        schema["pattern"] = f.pattern

    return schema


class JSONSchemaGenerator(Generator):
    """
    Generates a JSON Schema document from a dataset's metadata
    (Step 2 — structifact.com build plan). The clearest single
    signal that Structifact isn't warehouse-specific: every other
    default/optional generator today emits something SQL- or
    dbt-shaped, and JSON Schema is neither.

    A straight mapping from FieldSpec, per the build plan: `type` →
    JSON Schema type (see JSON_SCHEMA_TYPE_MAP), `nullable: false` →
    listed in the dataset-level `required` array, `accepted_values` →
    `enum`, `min_value`/`max_value` → `minimum`/`maximum`, `pattern` →
    `pattern`. (`date`/`timestamp` additionally get a `format`
    annotation — see JSON_SCHEMA_FORMAT_MAP's docstring for why that
    one extra mapping is included.)

    `nullable` maps only to `required`, never to a `["string", "null"]`
    type union — the same scope SQLGenerator gives it (NOT NULL, never
    a union type). JSON Schema's `required` keyword is actually about
    key *presence*, not value nullability, so this reuses the same
    not-quite-exact fit `SQLGenerator`'s NOT NULL already relies on
    (nullable is stored as one bool describing one real-world
    intention: "this field must always be given a real value") rather
    than introducing a second, more literal-but-heavier mechanism this
    generator's siblings don't have either.
    `required` is a straight list of every field with `nullable:
    False`, in field-declaration order (not stable-sorted or grouped)
    — no field has ever been observed to want the key present but
    the value nullable in this codebase's metadata model, so there is
    only one bool to consult, not two.

    Deliberately NOT mapped in this first version: `length`/
    `precision`/`scale` (a natural next step — `maxLength` for a
    bounded string mirrors sql.py's own VARCHAR(length) — but outside
    the build plan's literal field list for Step 2, whose stated
    purpose is proving the format-registry story cheaply, not
    reaching feature parity with SQLGenerator in one pass) and every
    ConstraintSpec type (primary_key/unique/foreign_key/check have no
    single-document JSON Schema equivalent the way a `CREATE TABLE`
    constraint does — `$ref`-based cross-document schema composition
    could someday express foreign_key, but that's real design work,
    not a mechanical mapping like everything else here).

    A field whose normalized `type` is "unknown" gets no `type` key at
    all, rather than falling back to some default the way sql.py falls
    back to TEXT — an absent `type` keyword in JSON Schema means "any
    type accepted," which is the accurate statement here (Structifact
    itself doesn't know what this field is), whereas defaulting to
    `string` would assert something Structifact was never told.
    """

    name = "json_schema"

    def generate(self, dataset: DatasetSpec) -> Artifact:
        properties = {}
        required = []

        for f in dataset.fields:
            properties[f.name] = _field_schema(f)

            if not f.nullable:
                required.append(f.name)

        schema = {
            "$schema": JSON_SCHEMA_DRAFT,
            "title": dataset.name,
        }

        if dataset.description:
            schema["description"] = dataset.description

        schema["type"] = "object"
        schema["properties"] = properties

        if required:
            schema["required"] = required

        return Artifact(
            filename=f"{dataset.name}.schema.json",
            content=json.dumps(schema, indent=2) + "\n",
        )
