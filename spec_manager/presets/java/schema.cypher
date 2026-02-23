// Java Spec Graph Schema
// Suitable for general Java applications (non-Spring)

// ─── Node Tables ─────────────────────────────────────────────────────────────

// A user-visible or system-level capability
CREATE NODE TABLE IF NOT EXISTS Feature(
    id          STRING,
    name        STRING,
    description STRING,
    status      STRING,   // proposed | active | deprecated | removed
    PRIMARY KEY (id)
);

// A Java package or module serving as an architectural unit
CREATE NODE TABLE IF NOT EXISTS Module(
    id          STRING,
    name        STRING,
    description STRING,
    package     STRING,   // Root Java package
    layer       STRING,   // api | domain | infrastructure | application
    status      STRING,
    PRIMARY KEY (id)
);

// A public class or interface that forms a contract
CREATE NODE TABLE IF NOT EXISTS Interface(
    id          STRING,
    name        STRING,
    description STRING,
    class_name  STRING,   // Fully qualified class name
    kind        STRING,   // interface | abstract-class | public-class
    status      STRING,
    PRIMARY KEY (id)
);

// A domain entity or value object
CREATE NODE TABLE IF NOT EXISTS Entity(
    id          STRING,
    name        STRING,
    description STRING,
    class_name  STRING,
    kind        STRING,   // entity | value-object | aggregate-root
    status      STRING,
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

// ─── Relationship Tables ──────────────────────────────────────────────────────

// Module depends on another Module
CREATE REL TABLE IF NOT EXISTS DependsOn(
    FROM Module TO Module,
    FROM Module TO Interface,
    FROM Feature TO Module,
    strength    STRING    // required | optional
);

// Feature is implemented by Module/Interface
CREATE REL TABLE IF NOT EXISTS Implements(
    FROM Feature TO Module,
    FROM Module TO Interface,
    FROM Interface TO Interface
);

// Module/Interface exposes Entity
CREATE REL TABLE IF NOT EXISTS Exposes(
    FROM Module TO Entity,
    FROM Interface TO Entity
);

// Entity references another Entity
CREATE REL TABLE IF NOT EXISTS References(
    FROM Entity TO Entity,
    relation    STRING    // has-a | uses | aggregates
);

// Feature satisfies Requirement
CREATE REL TABLE IF NOT EXISTS Satisfies(
    FROM Feature TO Requirement,
    FROM Module TO Requirement
);

// Informational link
CREATE REL TABLE IF NOT EXISTS RelatedTo(
    FROM Feature TO Feature,
    FROM Module TO Module,
    FROM Entity TO Entity,
    FROM Feature TO Requirement
);

// A and B cannot coexist
CREATE REL TABLE IF NOT EXISTS Conflicts(
    FROM Feature TO Feature,
    FROM Module TO Module,
    reason      STRING
);
