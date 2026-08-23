"""
Tests for JSONSchemaGenerator (structifact.com build plan, Step 2 —
"Step," not "Phase": see docs/DECISION_HISTORY.md's "Two Different
Numbering Systems Both Called 'Phase'" entry).

Covers: the straight FieldSpec -> JSON Schema mapping the build plan
specifies (type, nullable -> required, accepted_values -> enum,
min_value/max_value -> minimum/maximum, pattern -> pattern); the one
addition beyond that literal list (date/timestamp -> format); the
deliberate omission of a `type` keyword for an "unknown" field rather
than a fabricated default; Decimal -> JSON number conversion picking
int for a whole-valued bound and float otherwise; and the generator's
wiring into the registry as optional, not default.

Assertions parse the generated content as JSON and compare structure
(dicts/lists), not substrings -- unlike mermaid_erd's tests, there's
no risk here of a syntactically-valid-but-semantically-wrong render
slipping past a plain "does it parse" check, since JSON's grammar
carries no ambiguity string assertions could uniquely catch that
structural equality wouldn't (json.dumps is deterministic for a given
dict), so structural comparison is strictly more precise, not a
weaker substitute.
"""

import json
from decimal import Decimal

import pytest

from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.generators.json_schema import JSONSchemaGenerator
from structifact.generators.registry import (
    GENERATORS, OPTIONAL_GENERATORS, ALL_GENERATORS,
)

try:
    import jsonschema as _jsonschema_lib
except ImportError:
    _jsonschema_lib = None


def _gen():
    return JSONSchemaGenerator()


def _schema(table: DatasetSpec) -> dict:
    artifact = _gen().generate(table)
    return json.loads(artifact.content)


def test_filename_matches_dataset_name():
    table = DatasetSpec(name="customers", fields=[FieldSpec(name="id", type="integer")])
    artifact = _gen().generate(table)
    assert artifact.filename == "customers.schema.json"


def test_content_is_valid_json():
    table = DatasetSpec(name="customers", fields=[FieldSpec(name="id", type="integer")])
    content = _gen().generate(table).content
    # Should not raise.
    json.loads(content)


def test_top_level_shape():
    table = DatasetSpec(name="customers", fields=[FieldSpec(name="id", type="integer")])
    schema = _schema(table)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["title"] == "customers"
    assert schema["type"] == "object"
    assert "properties" in schema


def test_dataset_description_included_when_set():
    table = DatasetSpec(
        name="customers",
        description="Customer master data",
        fields=[FieldSpec(name="id", type="integer")],
    )
    schema = _schema(table)
    assert schema["description"] == "Customer master data"


def test_dataset_description_omitted_when_unset():
    table = DatasetSpec(name="customers", fields=[FieldSpec(name="id", type="integer")])
    schema = _schema(table)
    assert "description" not in schema


def test_type_mapping_for_each_normalized_type():
    table = DatasetSpec(
        name="widgets",
        fields=[
            FieldSpec(name="a", type="string"),
            FieldSpec(name="b", type="integer"),
            FieldSpec(name="c", type="decimal"),
            FieldSpec(name="d", type="float"),
            FieldSpec(name="e", type="boolean"),
        ],
    )
    props = _schema(table)["properties"]

    assert props["a"]["type"] == "string"
    assert props["b"]["type"] == "integer"
    assert props["c"]["type"] == "number"
    assert props["d"]["type"] == "number"
    assert props["e"]["type"] == "boolean"


def test_date_type_maps_to_string_with_date_format():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_date", type="date")],
    )
    prop = _schema(table)["properties"]["order_date"]

    assert prop["type"] == "string"
    assert prop["format"] == "date"


def test_timestamp_type_maps_to_string_with_date_time_format():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="created_at", type="timestamp")],
    )
    prop = _schema(table)["properties"]["created_at"]

    assert prop["type"] == "string"
    assert prop["format"] == "date-time"


def test_unknown_type_omits_type_keyword_rather_than_defaulting():
    # Unlike sql.py's TEXT fallback, an "unknown" field asserts
    # nothing -- Structifact itself doesn't know what this field is,
    # so no `type` keyword is emitted at all (absent `type` means
    # "any type accepted" in JSON Schema).
    table = DatasetSpec(
        name="widgets",
        fields=[FieldSpec(name="mystery", type="unknown")],
    )
    prop = _schema(table)["properties"]["mystery"]

    assert "type" not in prop


def test_field_description_included_when_set():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="id", type="integer", description="Unique customer identifier")],
    )
    prop = _schema(table)["properties"]["id"]
    assert prop["description"] == "Unique customer identifier"


def test_field_description_omitted_when_unset():
    table = DatasetSpec(name="customers", fields=[FieldSpec(name="id", type="integer")])
    prop = _schema(table)["properties"]["id"]
    assert "description" not in prop


def test_non_nullable_field_is_listed_in_required():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="id", type="integer", nullable=False)],
    )
    schema = _schema(table)
    assert schema["required"] == ["id"]


def test_nullable_field_is_not_listed_in_required():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="notes", type="string", nullable=True)],
    )
    schema = _schema(table)
    assert "required" not in schema or "notes" not in schema.get("required", [])


def test_required_omitted_entirely_when_no_field_is_non_nullable():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="notes", type="string", nullable=True)],
    )
    schema = _schema(table)
    assert "required" not in schema


def test_required_preserves_field_declaration_order():
    table = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(name="z_id", type="integer", nullable=False),
            FieldSpec(name="a_id", type="integer", nullable=False),
        ],
    )
    schema = _schema(table)
    assert schema["required"] == ["z_id", "a_id"]


def test_nullable_does_not_produce_a_null_type_union():
    # nullable maps only to `required` -- never to a
    # ["string", "null"] type union. See JSONSchemaGenerator's
    # docstring for why this mirrors SQLGenerator's own NOT-NULL-only
    # scope for the same attribute.
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="notes", type="string", nullable=True)],
    )
    prop = _schema(table)["properties"]["notes"]
    assert prop["type"] == "string"


def test_accepted_values_maps_to_enum():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="status", type="string", accepted_values=["OPEN", "CLOSED"])],
    )
    prop = _schema(table)["properties"]["status"]
    assert prop["enum"] == ["OPEN", "CLOSED"]


def test_enum_omitted_when_accepted_values_unset():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="status", type="string")],
    )
    prop = _schema(table)["properties"]["status"]
    assert "enum" not in prop


def test_pattern_maps_directly():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="zip_code", type="string", pattern=r"^\d{5}$")],
    )
    prop = _schema(table)["properties"]["zip_code"]
    assert prop["pattern"] == r"^\d{5}$"


def test_pattern_omitted_when_unset():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="zip_code", type="string")],
    )
    prop = _schema(table)["properties"]["zip_code"]
    assert "pattern" not in prop


def test_min_max_value_map_to_minimum_maximum():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(
                name="quantity", type="integer",
                min_value=Decimal("1"), max_value=Decimal("100"),
            ),
        ],
    )
    prop = _schema(table)["properties"]["quantity"]
    assert prop["minimum"] == 1
    assert prop["maximum"] == 100


def test_whole_valued_decimal_bound_serializes_as_json_int_not_float():
    # A whole-valued Decimal (e.g. from an integer-typed field's
    # bound) must come through as a JSON integer, not `1.0` --
    # some JSON Schema validators reject a float minimum/maximum
    # paired with "type": "integer".
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="quantity", type="integer", min_value=Decimal("1"))],
    )
    content = _gen().generate(table).content

    assert '"minimum": 1' in content
    assert '"minimum": 1.0' not in content


def test_fractional_decimal_bound_serializes_as_json_float():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="amount", type="decimal", max_value=Decimal("99.95"))],
    )
    prop = _schema(table)["properties"]["amount"]
    assert prop["maximum"] == 99.95


def test_min_max_omitted_when_unset():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="quantity", type="integer")],
    )
    prop = _schema(table)["properties"]["quantity"]
    assert "minimum" not in prop
    assert "maximum" not in prop


def test_properties_preserve_field_declaration_order():
    table = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(name="z_field", type="string"),
            FieldSpec(name="a_field", type="string"),
        ],
    )
    content = _gen().generate(table).content
    assert content.index('"z_field"') < content.index('"a_field"')


def test_json_schema_generator_is_optional_not_default():
    default_names = {g.name for g in GENERATORS}
    optional_names = {g.name for g in OPTIONAL_GENERATORS}
    all_names = {g.name for g in ALL_GENERATORS}

    assert "json_schema" not in default_names
    assert "json_schema" in optional_names
    assert "json_schema" in all_names


def test_constraints_do_not_affect_required_only_nullable_does():
    # ConstraintSpec is deliberately out of scope for this generator
    # (see JSONSchemaGenerator's docstring) -- a primary_key constraint
    # on a nullable field must NOT pull that field into `required`.
    # Only FieldSpec.nullable governs required.
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="id", type="integer", nullable=True)],
        constraints=[ConstraintSpec(type="primary_key", columns=["id"])],
    )
    schema = _schema(table)
    assert "required" not in schema


@pytest.mark.skipif(
    _jsonschema_lib is None,
    reason="meta-schema validation check requires the 'jsonschema' package",
)
def test_generated_schema_is_actually_valid_per_the_meta_schema():
    # String/structure assertions above only confirm the document
    # looks the way this generator's own code intends. This confirms
    # it independently, the same way test_mermaid_erd_generator.py's
    # mmdc round-trip confirms Mermaid output against the real
    # renderer rather than Structifact's own idea of correct syntax:
    # validate the generated document against the real JSON Schema
    # 2020-12 meta-schema (jsonschema.Draft202012Validator), covering
    # every mapped field kind -- typed fields, an enum, min/max
    # bounds, a pattern, a date/timestamp format, an "unknown"-typed
    # field with no `type` keyword, and `required` -- together in one
    # document.
    table = DatasetSpec(
        name="orders",
        description="Order line items",
        fields=[
            FieldSpec(name="order_id", type="integer", nullable=False),
            FieldSpec(
                name="status", type="string",
                accepted_values=["OPEN", "CLOSED"],
            ),
            FieldSpec(
                name="amount", type="decimal",
                min_value=Decimal("0"), max_value=Decimal("99999.99"),
            ),
            FieldSpec(name="zip_code", type="string", pattern=r"^\d{5}$"),
            FieldSpec(name="ordered_at", type="timestamp"),
            FieldSpec(name="ship_date", type="date"),
            FieldSpec(name="notes", type="string", nullable=True),
            FieldSpec(name="legacy_flag", type="unknown"),
        ],
    )

    schema = _schema(table)

    _jsonschema_lib.Draft202012Validator.check_schema(schema)
