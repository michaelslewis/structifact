# Structifact

> Define once. Generate everywhere.

Structifact is a metadata compiler that transforms structured metadata definitions into reusable data artifacts.

Instead of defining the same data structure repeatedly across databases, transformation tools, and documentation systems, Structifact lets you define your metadata once and generate the artifacts you need.

## Why Structifact?

Modern data systems often duplicate information about tables and fields:

* Database schemas
* Analytics models
* Transformation definitions
* Documentation
* Data catalogs

These definitions can drift apart over time.

Structifact provides a single metadata representation that can be validated, normalized, and compiled into different outputs.

## Architecture

Structifact follows a compiler-style architecture:

```
YAML / CSV / Excel
        |
        v
     Adapters
        |
        v
 Intermediate Representation
        |
        v
 Validation + Type Normalization
        |
        v
    Generators
        |
        +--> SQL
        |
        +--> dbt YAML
```

The core intermediate representation (`TableSpec` and `FieldSpec`) allows new input formats and output generators to be added independently.

## Quick Start

Clone the repository and install:

```bash
git clone https://github.com/michaelslewis/structifact.git
cd structifact

python -m venv .venv
source .venv/bin/activate

pip install -e .
```

Generate artifacts:

```bash
structifact generate examples/customers.yml
```

Example output:

```
--- STRUCTURED VIEW ---

Table: customers

Fields:
- customer_id (string)
- created_at (timestamp)

--- GENERATED ARTIFACTS ---
- output/customers.sql
- output/customers.yml
```

## Example Metadata

Input:

```yaml
table: customers

fields:
  - name: customer_id
    type: VARCHAR(255)

  - name: created_at
    type: TIMESTAMP
```

Structifact normalizes types internally:

```
VARCHAR(255)
    -> string(length=255)

TIMESTAMP
    -> timestamp
```

## Supported Inputs

Currently supported:

* YAML
* CSV
* Excel (optional dependency)

Excel support can be installed with:

```bash
pip install -e ".[excel]"
```

## Generated Outputs

Currently supported:

* SQL table definitions
* dbt YAML model definitions

## Type System

Structifact normalizes common database types into a consistent internal representation.

Examples:

```
VARCHAR(255)       -> string(length=255)
NUMBER(13,2)       -> decimal(precision=13, scale=2)
DATETIME2          -> timestamp
```

Unsupported types are detected during validation before generation.

## Development

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

## Project Status

Structifact is currently under active development. The core compiler pipeline, adapters, validation, type normalization, and initial generators are implemented.

## Roadmap

Future improvements include:

* Additional output generators
* Additional input adapters
* Expanded database type mappings
* Richer schema validation
* More metadata attributes
* Documentation and visualization features

## License

Released under the MIT License.
