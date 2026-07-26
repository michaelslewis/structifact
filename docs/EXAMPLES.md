# EXAMPLES.md

# Structifact Examples

## Purpose

This document demonstrates how Structifact is intended to be used.

The examples focus on the current metadata-driven workflow:

1. Define dataset structure using YAML metadata.
2. Validate metadata definitions.
3. Load source data through adapters.
4. Generate repeatable engineering artifacts.
5. Produce outputs that can be inspected, tested, and extended.

Structifact is designed around the principle:

> Define structure once. Generate reliable systems from it.

---

# Example 1 — Defining a Dataset Schema

A Structifact dataset begins with metadata.

Instead of writing custom ingestion and validation logic for every dataset, users describe the expected structure declaratively.

Example:

`examples/customers.yml`

```yaml
dataset:
  name: customers
  description: Customer master data

columns:
  - name: customer_id
    type: integer
    nullable: false

  - name: first_name
    type: string
    nullable: false

  - name: last_name
    type: string
    nullable: false

  - name: email
    type: string
    nullable: false
```

This metadata describes the intended structure of the dataset without requiring implementation-specific code.

---

# Example 2 — Providing Source Data

A source file can then be paired with the metadata definition.

Example:

`examples/customers.csv`

```csv
customer_id,first_name,last_name,email
1,Michael,Lewis,michael@example.com
2,Jane,Smith,jane@example.com
```

The metadata acts as the contract describing what the data should contain.

---

# Example 3 — Validation Workflow

A core goal of Structifact is making data quality explicit.

The framework can inspect metadata definitions and validate that datasets conform to expectations.

Example workflow:

```text
customers.yml
      |
      |
      v
Metadata Parser
      |
      |
      v
Validation Engine
      |
      |
      v
Validation Results
```

Potential validations include:

* Required columns exist.
* Data types are correct.
* Required values are not null.
* Constraints are satisfied.

The validation framework is designed to provide early feedback before unreliable data moves further through the pipeline.

---

# Example 4 — Adapter-Based Data Loading

Structifact uses an adapter architecture to support different input formats.

Current repository adapters include:

```
structifact/
└── adapters/
    ├── csv.py
    ├── excel.py
    └── yaml.py
```

The goal is to allow datasets to be processed consistently regardless of source format.

Conceptually:

```text
CSV File
   |
   |
CSV Adapter
   |
   |
Normalized Internal Representation
   |
   |
Generators / Validation
```

Future adapters may support additional sources.

---

# Example 5 — Internal Representation

Structifact separates external formats from internal processing.

Rather than every component understanding every possible input format, source data is converted into a common internal representation.

Conceptually:

```text
YAML Metadata
      |
      |
CSV / Excel / Other Sources
      |
      |
      v
Intermediate Representation
      |
      |
      +----------------+
      |                |
      v                v
Validation       Generators
```

This separation improves:

* maintainability
* extensibility
* testability
* consistency

---

# Example 6 — Generating SQL Artifacts

Structifact includes generators designed to create repeatable outputs from metadata.

Current repository generators include:

```
structifact/
└── generators/
    ├── sql.py
    ├── dbt_yaml.py
    └── registry.py
```

Example output:

```
output/
├── customers.sql
├── transactions.sql
├── customers.yml
└── transactions.yml
```

The purpose is to reduce repetitive manual creation of engineering artifacts.

---

# Example 7 — Example CLI Workflow

The long-term goal is a simple developer experience.

A future workflow may look like:

```bash
structifact validate

structifact build

structifact generate

structifact docs
```

The user defines metadata and Structifact handles repeatable generation tasks.

---

# Example 8 — Extending to Analytics Engineering

Structifact is designed with analytics engineering patterns in mind.

A future workflow could look like:

```text
Raw Source Data

        |
        v

Metadata Definition

        |
        v

Validation

        |
        v

Transformation Generation

        |
        v

Analytics Model

        |
        v

Business Reporting
```

Potential generated artifacts:

* SQL transformations
* dbt models
* documentation
* validation reports
* lineage information

---

# Example 9 — Future AI-Assisted Workflow

One long-term exploration area is AI-assisted metadata discovery.

A future user experience could allow a user to provide an unknown dataset:

```text
customer_export.csv
```

Structifact could analyze:

* column names
* sample values
* data patterns
* relationships
* possible data types

The system could then suggest:

```yaml
dataset:
  name: customer_export

columns:
  - name: customer_id
    suggested_type: integer

  - name: email
    suggested_type: string

  - name: created_date
    suggested_type: timestamp
```

The user could review, modify, and approve the generated metadata before it becomes part of the pipeline.

AI would assist with discovery and acceleration, while the final metadata definition would remain explicit and reviewable.

---

# Example 10 — Future Data Platform Integration

Structifact is intentionally designed to remain independent from any single execution platform.

A future architecture could support:

```text
              Structifact Metadata

                      |
                      |

        +-------------+-------------+

        |             |             |

      Local        Cloud        Warehouse

      DuckDB       Storage      Snowflake

        |             |             |

        +-------------+-------------+

                      |

             Analytics Workflows
```

The metadata layer remains the source of truth while execution environments evolve.

---

# Example 11 — Example Project Structure

A future Structifact project may look like:

```
project/

├── schemas/
│   ├── customers.yml
│   └── transactions.yml

├── data/
│   ├── customers.csv
│   └── transactions.csv

├── transformations/

├── tests/

├── generated/

├── docs/

└── config.yml
```

The exact structure may evolve as the framework matures.

---

# Current Implementation Examples

The current repository demonstrates:

* YAML metadata definitions
* CSV and YAML adapters
* Metadata parsing
* Internal representation objects
* Validation framework
* SQL generation
* dbt-style YAML generation
* Automated tests

The project is intentionally evolving from foundational framework components toward a broader metadata-driven engineering platform.

---

# Example Philosophy

Structifact examples should continue demonstrating:

* realistic engineering workflows
* clear metadata definitions
* inspectable generated outputs
* strong validation practices
* maintainable architecture

The objective is not simply automation.

The objective is creating systems that are easier to understand, trust, and evolve.
