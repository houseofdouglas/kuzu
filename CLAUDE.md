# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Kuzu

Kuzu is an embedded property graph database written in C++20. It supports the Cypher query language with columnar disk-based storage, vectorized query execution, and ACID transactions. It has language bindings for Python, Java, Node.js, Rust, C, and WebAssembly.

## Build Commands

The Makefile wraps CMake. All builds output to `build/<type>/`.

```bash
make release           # Release build (default)
make debug             # Debug build
make relwithdebinfo    # Release with debug info (used for tests)
make allconfig         # Configure everything (tests, extensions, all APIs)
make all               # Build from allconfig
```

### Testing

```bash
make test-build        # Build C++ tests (RelWithDebInfo)
make test              # Run all C++ tests (10 parallel jobs via ctest)
make pytest            # Run Python API tests
make javatest          # Run Java API tests
make nodejstest        # Run Node.js API tests
make extension-test    # Run extension tests
make shell-test        # Run interactive shell tests
```

**Running a single C++ test by pattern:**
```bash
ctest --test-dir build/RelWithDebInfo/test --output-on-failure -R "<test_pattern>"
```

**Running Python tests directly:**
```bash
PYTHONPATH=tools/python_api/build python3 -m pytest -vv tools/python_api/test
```

### Code Quality

```bash
make tidy              # Run clang-tidy (full config)
make clangd-diagnostics
```

### Key Build Variables

```bash
NUM_THREADS=8 make release        # Control build parallelism
ASAN=1 make debug                 # Address sanitizer
TSAN=1 make debug                 # Thread sanitizer
UBSAN=1 make debug                # Undefined behavior sanitizer
WERROR=1 make release             # Treat warnings as errors
RUNTIME_CHECKS=1 make debug       # Enable runtime coherency checks
```

## Architecture

Query execution flows: **Parser → Binder → Planner → Optimizer → Processor**

### Core Engine (`src/`)

- **`parser/`** — ANTLR4-based Cypher query parser; grammar lives in `src/antlr4/`
- **`binder/`** — Semantic analysis, name resolution, type checking; produces bound AST
- **`planner/`** — Logical plan generation, join order selection
- **`optimizer/`** — Plan rewriting and cost-based optimization
- **`processor/`** — Physical query execution; vectorized operators, aggregates, DDL execution
- **`storage/`** — Buffer manager, compression, WAL, hash/B-tree indices, columnar table storage, statistics
- **`catalog/`** — Schema metadata (tables, nodes, relationships, their properties)
- **`transaction/`** — ACID transaction management
- **`function/`** — Built-in scalar, aggregate, and specialized functions (path, GDS, sequence, etc.)
- **`expression_evaluator/`** — Vectorized expression evaluation layer
- **`graph/`** — Graph data model abstractions
- **`common/`** — Data types, value representation, Arrow format, filesystem abstraction, task scheduler, exceptions
- **`main/`** — Public database/connection/query result API surface
- **`c_api/`** — C language bindings wrapping `main/`
- **`include/`** — Public and internal header files

### Extensions (`extension/`)

Extensions are loadable plugins. Key ones: `algo` (graph algorithms), `fts` (full-text search), `vector` (vector indices), `duckdb`/`postgres`/`sqlite` (external DB connectors), `json`, `httpfs`, `azure`, `delta`, `iceberg`, `neo4j`, `llm`.

### Language Bindings (`tools/`)

- `python_api/` — pybind11 bindings
- `java_api/` — JNI bindings
- `nodejs_api/` — Node.js native bindings
- `rust_api/` — Rust FFI bindings
- `shell/` — Interactive CLI shell
- `wasm/` — Emscripten/WebAssembly build
- `benchmark/` — Benchmarking harness

### Test Infrastructure (`test/`)

Tests use Google Test. End-to-end tests in `test/test_files/` (`.cypher` files) are matched against expected results in `test/answers/`. The `test/runner/` directory contains the test executor. Component tests live alongside their component (`storage/`, `transaction/`, `common/`, etc.).

## Code Style

The repo uses `.clang-format` for formatting and `.clang-tidy` for static analysis. C++20 is required. Platform support: Linux, macOS, Windows.

## Spec Management

This repository uses a graph-based specification system built on Kuzu.

```
agents/          # Claude agent definitions for spec management (6 agents)
spec/            # Source of truth — committed to git
  schema.cypher  # DDL for all node and edge tables
  nodes/         # One JSON array file per node type
  edges/         # One JSON array file per edge type
spec.db          # Derived — .gitignore'd, rebuilt from spec/ on load
specifications/  # Design documentation for the spec system itself
```

**Note:** JSON files in `spec/nodes/` and `spec/edges/` use JSONC format — `//` line comments are allowed. Strip them before parsing with `json.loads()`:

```python
import json, kuzu, pathlib

def strip_comments(text):
    lines = [l for l in text.splitlines() if not l.strip().startswith("//")]
    return "\n".join(lines)

def parse_statements(sql):
    return [s.strip() for s in strip_comments(sql).split(";") if s.strip()]

db = kuzu.Database("spec.db")
conn = kuzu.Connection(db)
for stmt in parse_statements(pathlib.Path("spec/schema.cypher").read_text()):
    conn.execute(stmt)
# Data is loaded by spec-manager via parameterized MERGE queries (see agents/spec-manager.md)
```

**Agent pipeline:**
- `baseline-generator` → `repo-explorer` — bootstrap a spec from an existing codebase
- `spec-author` → `feature-analyst` → `spec-manager` — add/update spec nodes day-to-day
- `merge-coordinator` — reconcile branch spec divergence at PR time

Requires: `pip install kuzu`
