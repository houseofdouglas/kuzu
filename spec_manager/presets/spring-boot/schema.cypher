// Spring Boot Spec Graph Schema
// Tailored for Spring Boot / Java applications
//
// DESIGN PRINCIPLE: Every relationship has specific semantics.
// Use the most specific relationship type available.
// RelatedTo is reserved for Feature↔Feature and Feature↔Requirement only.

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
    priority    STRING,        // p0 | p1 | p2 | p3
    test_coverage STRING,      // required | recommended | none
    status      STRING,
    PRIMARY KEY (id)
);

// A test suite or test category that verifies functionality
CREATE NODE TABLE IF NOT EXISTS TestSuite(
    id          STRING,
    name        STRING,
    description STRING,
    path        STRING,        // src/test/java/com/example/UserServiceTest.java
    kind        STRING,        // unit | integration | e2e | contract | performance
    framework   STRING,        // junit | testng | cucumber | spring-test | mockito
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

// ─── Structural Relationships ────────────────────────────────────────────────
// These define the architecture: what exposes what, what contains what

// Controller exposes Endpoint
CREATE REL TABLE IF NOT EXISTS Exposes(
    FROM Controller TO Endpoint
);

// Repository manages Entity (CRUD operations)
CREATE REL TABLE IF NOT EXISTS Manages(
    FROM Repository TO Entity
);

// Configuration configures components
CREATE REL TABLE IF NOT EXISTS Configures(
    FROM Configuration TO Service,
    FROM Configuration TO Repository,
    FROM Configuration TO Controller,
    FROM Configuration TO Endpoint
);

// ─── Dependency Relationships ────────────────────────────────────────────────
// These define runtime dependencies: A needs B to function

// Component depends on another component (injection, method calls)
CREATE REL TABLE IF NOT EXISTS DependsOn(
    FROM Controller TO Service,
    FROM Controller TO Repository,
    FROM Controller TO Controller,
    FROM Service TO Service,
    FROM Service TO Repository,
    FROM Repository TO Repository,
    FROM Configuration TO Service,
    FROM Configuration TO Repository,
    FROM Configuration TO Configuration,
    strength    STRING    // required | optional
);

// ─── Data Flow Relationships ─────────────────────────────────────────────────
// These define how data moves through the system

// Endpoint/Controller/Service uses DTO for data transfer
CREATE REL TABLE IF NOT EXISTS UsesDTO(
    FROM Endpoint TO DTO,
    FROM Controller TO DTO,
    FROM Service TO DTO,
    direction   STRING    // request | response | both
);

// Service transforms between Entity and DTO
CREATE REL TABLE IF NOT EXISTS Maps(
    FROM Service TO Entity,
    FROM Service TO DTO
);

// Entity/DTO references another Entity/DTO (composition, embedding)
CREATE REL TABLE IF NOT EXISTS References(
    FROM Entity TO Entity,
    FROM DTO TO DTO,
    FROM DTO TO Entity,
    relation    STRING    // one-to-one | one-to-many | many-to-one | many-to-many | embeds
);

// ─── Feature Relationships ───────────────────────────────────────────────────
// These link business capabilities to technical implementations

// Feature is implemented by technical components
CREATE REL TABLE IF NOT EXISTS Implements(
    FROM Feature TO Controller,
    FROM Feature TO Service,
    FROM Feature TO Repository,
    FROM Feature TO Endpoint,
    FROM Feature TO Configuration
);

// Feature/Component satisfies a Requirement
CREATE REL TABLE IF NOT EXISTS Satisfies(
    FROM Feature TO Requirement,
    FROM Service TO Requirement,
    FROM Controller TO Requirement,
    FROM Repository TO Requirement,
    FROM Configuration TO Requirement,
    FROM Endpoint TO Requirement
);

// Feature depends on another Feature (business-level dependency)
CREATE REL TABLE IF NOT EXISTS FeatureDependsOn(
    FROM Feature TO Feature,
    strength    STRING    // required | optional
);

// ─── Informational Relationships ─────────────────────────────────────────────
// Loose coupling for documentation purposes only

// Informational link (NARROW: Feature-level only)
// Use specific relationships for technical components
CREATE REL TABLE IF NOT EXISTS RelatedTo(
    FROM Feature TO Feature,
    FROM Feature TO Requirement
);

// A and B cannot coexist (mutual exclusion)
CREATE REL TABLE IF NOT EXISTS Conflicts(
    FROM Feature TO Feature,
    FROM Configuration TO Configuration,
    FROM Endpoint TO Endpoint,
    reason      STRING
);

// ─── Test Relationships ─────────────────────────────────────────────────────
// These link test suites to the features and components they verify

// Feature/Component is verified by a TestSuite
CREATE REL TABLE IF NOT EXISTS VerifiedBy(
    FROM Feature TO TestSuite,
    FROM Endpoint TO TestSuite,
    FROM Controller TO TestSuite,
    FROM Service TO TestSuite,
    FROM Repository TO TestSuite,
    FROM Configuration TO TestSuite,
    coverage    STRING    // full | partial | smoke
);

// TestSuite depends on another TestSuite (test utilities, fixtures)
CREATE REL TABLE IF NOT EXISTS TestDependsOn(
    FROM TestSuite TO TestSuite
);

// ─── Security Relationships ──────────────────────────────────────────────────
// CRITICAL: Changes to these relationships require security review

// Component is secured by a SecurityConstraint
CREATE REL TABLE IF NOT EXISTS SecuredBy(
    FROM Endpoint TO SecurityConstraint,
    FROM Controller TO SecurityConstraint,
    FROM Service TO SecurityConstraint,
    FROM Repository TO SecurityConstraint,
    FROM Configuration TO SecurityConstraint,
    enforced_at STRING    // method | class | global
);

// Component requires a specific Role for access
CREATE REL TABLE IF NOT EXISTS RequiresRole(
    FROM Endpoint TO Role,
    FROM Controller TO Role,
    FROM Service TO Role,
    FROM Repository TO Role,
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
