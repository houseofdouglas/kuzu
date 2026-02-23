# spec-manager

A Kuzu-backed specification graph management system for Claude Code agentic workflows.

## Installation

```bash
# From this repository
pip install -e /path/to/kuzu

# Or install from git
pip install git+https://github.com/your-org/kuzu.git
```

## Quick Start: Initialize a Java/Spring Boot Project

```bash
# Clone your project
git clone https://github.com/your-org/your-spring-boot-app.git
cd your-spring-boot-app

# Initialize spec with Spring Boot schema
spec-manager init --preset spring-boot --show-mcp

# Add to .gitignore
echo "spec.db" >> .gitignore
echo "spec.db.wal" >> .gitignore
echo "spec.db.lock" >> .gitignore

# Build the database
spec-manager rebuild

# View the schema
spec-manager schema
```

## Available Presets

| Preset | Node Types | Best For |
|--------|------------|----------|
| `generic` | Feature, Component, Interface, Requirement | Any software project |
| `spring-boot` | Controller, Service, Repository, Entity, DTO, Endpoint, Configuration, Feature, Requirement | Spring Boot applications |
| `java` | Feature, Module, Interface, Entity, Requirement | General Java projects |

## CLI Commands

```bash
# Initialize a new spec directory
spec-manager init [--preset NAME] [--spec-dir PATH] [--force] [--show-mcp]

# Rebuild spec.db from spec/ files
spec-manager [--db PATH] [--spec-dir PATH] rebuild

# Check for cycles in DAG relations
spec-manager [--db PATH] [--spec-dir PATH] detect-cycles

# Export spec.db to spec/ JSON files
spec-manager [--db PATH] [--spec-dir PATH] export

# Run a Cypher query
spec-manager [--db PATH] [--spec-dir PATH] query '<cypher>'

# Read a specific node with neighbors
spec-manager [--db PATH] [--spec-dir PATH] node <id>

# List all nodes (optionally by table)
spec-manager [--db PATH] [--spec-dir PATH] list [<table>]

# Print node/edge counts
spec-manager [--db PATH] [--spec-dir PATH] counts

# Show discovered schema info
spec-manager [--spec-dir PATH] schema
```

## MCP Server for Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "spec-manager": {
      "command": "python3",
      "args": [
        "-m", "spec_manager.mcp_server",
        "--db", "./spec.db",
        "--spec-dir", "./spec"
      ]
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `read_spec_node` | Read a node and its neighbors |
| `write_spec_node` | Create a new node |
| `update_spec_node` | Update an existing node |
| `delete_spec_node` | Delete a node and its edges |
| `write_spec_edge` | Create an edge between nodes |
| `query_spec` | Run a Cypher query |
| `detect_cycles_tool` | Check for cycles |
| `get_affected_by_tool` | Find nodes affected by a change |
| `export_to_files_tool` | Export DB to spec/ files |
| `list_spec_nodes` | List all nodes |

## Workflow: Baseline Generation

After initializing, use the Claude agents to bootstrap your spec:

1. **baseline-generator** — Orchestrates the full extraction pipeline
2. **repo-explorer** — Explores bounded sections of the codebase
3. **spec-author** — Formalizes findings into spec nodes
4. **feature-analyst** — Analyzes spec health and coverage
5. **spec-manager** — Commits spec changes
6. **merge-coordinator** — Reconciles branch spec divergence

```
User: Generate a baseline spec for this repository. Start with the top-level architecture.
→ Claude launches baseline-generator agent
→ Agent explores codebase layer by layer
→ Creates Feature, Component, Interface nodes
→ Commits to spec/ (git-tracked)
```

## Detecting Spec Drift

As development continues, spec drift is tracked through:

1. **Git diff on spec/** — Changes to JSON files show what evolved
2. **Cycle detection** — `spec-manager detect-cycles` catches dependency problems
3. **Coverage reports** — Compare codebase against spec coverage

## Directory Structure

```
your-project/
├── .mcp.json           # MCP server config
├── spec.db             # Kuzu database (gitignored)
├── spec/
│   ├── schema.cypher   # Node/edge table definitions
│   ├── nodes/          # JSON files per node type
│   │   ├── controllers.json
│   │   ├── services.json
│   │   └── ...
│   └── edges/          # JSON files per edge type
│       ├── depends-on.json
│       └── ...
└── ...
```

## Custom Schema

Edit `spec/schema.cypher` to customize node and edge types for your domain:

```cypher
// Add a custom node type
CREATE NODE TABLE IF NOT EXISTS MyCustomType(
    id          STRING,
    name        STRING,
    description STRING,
    status      STRING,
    PRIMARY KEY (id)
);

// Add a custom relationship
CREATE REL TABLE IF NOT EXISTS MyCustomRelation(
    FROM MyCustomType TO Feature,
    reason      STRING
);
```

After editing, create corresponding JSON files in `spec/nodes/` and `spec/edges/`, then rebuild:

```bash
touch spec/nodes/my-custom-types.json  # Empty: []
touch spec/edges/my-custom-relations.json
spec-manager rebuild
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SPEC_DB_PATH` | Path to spec.db | `./spec.db` |
| `SPEC_DIR` | Path to spec/ directory | `./spec` |
