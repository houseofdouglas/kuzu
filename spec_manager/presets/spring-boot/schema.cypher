// Spring Boot Spec Graph Schema
// Tailored for Spring Boot / Java applications

// ─── Node Tables ─────────────────────────────────────────────────────────────

// A REST or messaging endpoint exposed by the application
CREATE NODE TABLE IF NOT EXISTS Endpoint(
    id          STRING,
    name        STRING,
    description STRING,
    method      STRING,   // GET | POST | PUT | DELETE | PATCH | MESSAGE
    path        STRING,   // /api/users/{id}
    auth        STRING,   // public | authenticated | role-based
    status      STRING,   // proposed | active | deprecated | removed
    PRIMARY KEY (id)
);

// A Spring @RestController or @Controller
CREATE NODE TABLE IF NOT EXISTS Controller(
    id          STRING,
    name        STRING,
    description STRING,
    base_path   STRING,   // @RequestMapping base path
    package     STRING,   // Java package
    status      STRING,
    PRIMARY KEY (id)
);

// A Spring @Service or business logic component
CREATE NODE TABLE IF NOT EXISTS Service(
    id          STRING,
    name        STRING,
    description STRING,
    package     STRING,
    status      STRING,
    PRIMARY KEY (id)
);

// A Spring @Repository or data access component
CREATE NODE TABLE IF NOT EXISTS Repository(
    id          STRING,
    name        STRING,
    description STRING,
    entity      STRING,   // The entity type this repository manages
    package     STRING,
    status      STRING,
    PRIMARY KEY (id)
);

// A JPA @Entity or domain model
CREATE NODE TABLE IF NOT EXISTS Entity(
    id          STRING,
    name        STRING,
    description STRING,
    table_name  STRING,   // Database table name
    package     STRING,
    status      STRING,
    PRIMARY KEY (id)
);

// A DTO, request/response object, or view model
CREATE NODE TABLE IF NOT EXISTS DTO(
    id          STRING,
    name        STRING,
    description STRING,
    purpose     STRING,   // request | response | internal
    package     STRING,
    status      STRING,
    PRIMARY KEY (id)
);

// A Spring @Configuration or @Component for infrastructure
CREATE NODE TABLE IF NOT EXISTS Configuration(
    id          STRING,
    name        STRING,
    description STRING,
    config_type STRING,   // security | database | messaging | web | cache
    package     STRING,
    status      STRING,
    PRIMARY KEY (id)
);

// A user-visible feature or capability
CREATE NODE TABLE IF NOT EXISTS Feature(
    id          STRING,
    name        STRING,
    description STRING,
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

// ─── Security Node Tables ────────────────────────────────────────────────────

// A security constraint or policy (authentication, authorization, rate limiting)
CREATE NODE TABLE IF NOT EXISTS SecurityConstraint(
    id          STRING,
    name        STRING,
    description STRING,
    constraint_type STRING,   // authentication | authorization | rate-limit | cors | csrf | encryption
    severity    STRING,       // critical | high | medium | low
    enforcement STRING,       // required | recommended | optional
    status      STRING,
    PRIMARY KEY (id)
);

// A role or permission that grants access
CREATE NODE TABLE IF NOT EXISTS Role(
    id          STRING,
    name        STRING,
    description STRING,
    role_type   STRING,   // system | user | service | admin
    status      STRING,
    PRIMARY KEY (id)
);

// ─── Relationship Tables ──────────────────────────────────────────────────────

// Controller exposes Endpoint
CREATE REL TABLE IF NOT EXISTS Exposes(
    FROM Controller TO Endpoint
);

// Controller/Service depends on Service
CREATE REL TABLE IF NOT EXISTS DependsOn(
    FROM Controller TO Service,
    FROM Service TO Service,
    FROM Service TO Repository,
    FROM Configuration TO Service,
    FROM Configuration TO Repository,
    strength    STRING    // required | optional
);

// Repository manages Entity
CREATE REL TABLE IF NOT EXISTS Manages(
    FROM Repository TO Entity
);

// Endpoint accepts/returns DTO
CREATE REL TABLE IF NOT EXISTS UsesDTO(
    FROM Endpoint TO DTO,
    direction   STRING    // request | response | both
);

// Entity has relationship to another Entity
CREATE REL TABLE IF NOT EXISTS References(
    FROM Entity TO Entity,
    relation    STRING    // one-to-one | one-to-many | many-to-one | many-to-many
);

// Service maps between Entity and DTO
CREATE REL TABLE IF NOT EXISTS Maps(
    FROM Service TO Entity,
    FROM Service TO DTO
);

// Feature is implemented by Controller/Service/Endpoint
CREATE REL TABLE IF NOT EXISTS Implements(
    FROM Feature TO Controller,
    FROM Feature TO Service,
    FROM Feature TO Endpoint
);

// Feature satisfies Requirement
CREATE REL TABLE IF NOT EXISTS Satisfies(
    FROM Feature TO Requirement,
    FROM Service TO Requirement,
    FROM Configuration TO Requirement
);

// Configuration configures other components
CREATE REL TABLE IF NOT EXISTS Configures(
    FROM Configuration TO Service,
    FROM Configuration TO Repository,
    FROM Configuration TO Controller
);

// Informational link
CREATE REL TABLE IF NOT EXISTS RelatedTo(
    FROM Feature TO Feature,
    FROM Service TO Service,
    FROM Entity TO Entity,
    FROM Feature TO Requirement
);

// A and B cannot coexist
CREATE REL TABLE IF NOT EXISTS Conflicts(
    FROM Feature TO Feature,
    FROM Configuration TO Configuration,
    reason      STRING
);

// ─── Security Relationship Tables ─────────────────────────────────────────────

// Endpoint/Service/Controller is secured by a SecurityConstraint
// CRITICAL: Changes to this relationship require security review
CREATE REL TABLE IF NOT EXISTS SecuredBy(
    FROM Endpoint TO SecurityConstraint,
    FROM Service TO SecurityConstraint,
    FROM Controller TO SecurityConstraint,
    FROM Configuration TO SecurityConstraint,
    enforced_at STRING    // method | class | global
);

// Endpoint/Service requires a specific Role for access
// CRITICAL: Changes to this relationship require security review
CREATE REL TABLE IF NOT EXISTS RequiresRole(
    FROM Endpoint TO Role,
    FROM Service TO Role,
    FROM Controller TO Role,
    access_type STRING    // read | write | admin | full
);

// Role inherits permissions from another Role
CREATE REL TABLE IF NOT EXISTS InheritsFrom(
    FROM Role TO Role
);

// SecurityConstraint enforces a Requirement
CREATE REL TABLE IF NOT EXISTS Enforces(
    FROM SecurityConstraint TO Requirement
);
