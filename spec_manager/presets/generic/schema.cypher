// Generic Spec Graph Schema
// Suitable for any software project

// ─── Node Tables ─────────────────────────────────────────────────────────────

// A user-visible or system-level capability
CREATE NODE TABLE IF NOT EXISTS Feature(
    id          STRING,
    name        STRING,
    description STRING,
    status      STRING,   // proposed | active | deprecated | removed
    PRIMARY KEY (id)
);

// An internal architectural unit with a defined boundary
CREATE NODE TABLE IF NOT EXISTS Component(
    id          STRING,
    name        STRING,
    description STRING,
    status      STRING,   // proposed | active | deprecated | removed
    layer       STRING,   // presentation | business | data | infrastructure
    PRIMARY KEY (id)
);

// A constraint or non-functional requirement
CREATE NODE TABLE IF NOT EXISTS Requirement(
    id          STRING,
    name        STRING,
    description STRING,
    priority    STRING,   // p0 | p1 | p2 | p3
    status      STRING,
    PRIMARY KEY (id)
);

// A stable public contract that external consumers depend on
CREATE NODE TABLE IF NOT EXISTS Interface(
    id          STRING,
    name        STRING,
    description STRING,
    status      STRING,
    PRIMARY KEY (id)
);

// ─── Relationship Tables ──────────────────────────────────────────────────────

// A must exist for B to function (DAG-intended — cycles are defects)
CREATE REL TABLE IF NOT EXISTS DependsOn(
    FROM Feature TO Feature,
    FROM Feature TO Component,
    FROM Component TO Component,
    FROM Component TO Feature,
    strength    STRING    // required | optional
);

// A feature is realized by a component (DAG-intended)
CREATE REL TABLE IF NOT EXISTS Implements(
    FROM Feature TO Component,
    FROM Component TO Interface
);

// A is a specialization or extension of B (DAG-intended)
CREATE REL TABLE IF NOT EXISTS DerivedFrom(
    FROM Feature TO Feature,
    FROM Component TO Component
);

// A and B cannot coexist (symmetric — write both directions)
CREATE REL TABLE IF NOT EXISTS Conflicts(
    FROM Feature TO Feature,
    FROM Feature TO Component,
    FROM Component TO Component,
    reason      STRING
);

// Informational link (symmetric)
CREATE REL TABLE IF NOT EXISTS RelatedTo(
    FROM Feature TO Feature,
    FROM Feature TO Component,
    FROM Component TO Component,
    FROM Feature TO Requirement,
    FROM Component TO Requirement
);

// Feature fulfills a stated Requirement
CREATE REL TABLE IF NOT EXISTS Satisfies(
    FROM Feature TO Requirement,
    FROM Component TO Requirement,
    FROM Component TO Component
);
