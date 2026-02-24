// Next.js Spec Graph Schema
// Tailored for Next.js applications (App Router or Pages Router)
//
// DESIGN PRINCIPLE: Every relationship has specific semantics.
// Use the most specific relationship type available.
// RelatedTo is reserved for Feature↔Feature and Feature↔Requirement only.

// ─── Node Tables ─────────────────────────────────────────────────────────────

// A route/page in the application
CREATE NODE TABLE IF NOT EXISTS Page(
    id          STRING,
    name        STRING,
    description STRING,
    route       STRING,   // /dashboard, /users/[id], etc.
    router      STRING,   // app | pages
    rendering   STRING,   // server | client | static | dynamic
    auth        STRING,   // public | authenticated | role-based
    status      STRING,   // proposed | active | deprecated | removed
    PRIMARY KEY (id)
);

// A React component
CREATE NODE TABLE IF NOT EXISTS Component(
    id          STRING,
    name        STRING,
    description STRING,
    path        STRING,   // components/ui/Button.tsx
    kind        STRING,   // ui | layout | feature | shared
    rendering   STRING,   // server | client
    status      STRING,
    PRIMARY KEY (id)
);

// An API route handler
CREATE NODE TABLE IF NOT EXISTS ApiRoute(
    id          STRING,
    name        STRING,
    description STRING,
    route       STRING,   // /api/users, /api/auth/[...nextauth]
    methods     STRING,   // GET | POST | PUT | DELETE | PATCH (comma-separated)
    auth        STRING,   // public | authenticated | role-based
    status      STRING,
    PRIMARY KEY (id)
);

// A layout component (App Router)
CREATE NODE TABLE IF NOT EXISTS Layout(
    id          STRING,
    name        STRING,
    description STRING,
    route       STRING,   // Route segment this layout applies to
    status      STRING,
    PRIMARY KEY (id)
);

// A custom React hook
CREATE NODE TABLE IF NOT EXISTS Hook(
    id          STRING,
    name        STRING,
    description STRING,
    path        STRING,   // hooks/useAuth.ts
    status      STRING,
    PRIMARY KEY (id)
);

// A React context provider
CREATE NODE TABLE IF NOT EXISTS Context(
    id          STRING,
    name        STRING,
    description STRING,
    path        STRING,   // contexts/AuthContext.tsx
    status      STRING,
    PRIMARY KEY (id)
);

// A service or utility module (business logic, data fetching)
CREATE NODE TABLE IF NOT EXISTS Service(
    id          STRING,
    name        STRING,
    description STRING,
    path        STRING,   // services/userService.ts, lib/api.ts
    kind        STRING,   // api | data | util | config
    status      STRING,
    PRIMARY KEY (id)
);

// Next.js middleware for request processing
CREATE NODE TABLE IF NOT EXISTS Middleware(
    id          STRING,
    name        STRING,
    description STRING,
    matcher     STRING,   // Route matcher pattern
    purpose     STRING,   // auth | redirect | rewrite | headers
    status      STRING,
    PRIMARY KEY (id)
);

// A TypeScript type or interface
CREATE NODE TABLE IF NOT EXISTS TypeDef(
    id          STRING,
    name        STRING,
    description STRING,
    path        STRING,   // types/user.ts
    kind        STRING,   // interface | type | enum
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
    path        STRING,        // __tests__/auth.test.ts, e2e/checkout.spec.ts
    kind        STRING,        // unit | integration | e2e | component | snapshot
    framework   STRING,        // jest | vitest | playwright | cypress | testing-library
    status      STRING,
    PRIMARY KEY (id)
);

// ─── Security Node Tables ────────────────────────────────────────────────────

// A security constraint or policy
CREATE NODE TABLE IF NOT EXISTS SecurityConstraint(
    id          STRING,
    name        STRING,
    description STRING,
    constraint_type STRING,   // authentication | authorization | rate-limit | cors | csrf
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
// These define the architecture: what renders what, what contains what

// Page/Layout/Component renders Component
CREATE REL TABLE IF NOT EXISTS Renders(
    FROM Page TO Component,
    FROM Layout TO Component,
    FROM Component TO Component
);

// Page belongs to Layout (route nesting)
CREATE REL TABLE IF NOT EXISTS BelongsTo(
    FROM Page TO Layout,
    FROM Layout TO Layout
);

// Context wraps pages/layouts/components (provider tree)
CREATE REL TABLE IF NOT EXISTS Wraps(
    FROM Context TO Page,
    FROM Context TO Layout,
    FROM Context TO Component
);

// Middleware protects routes
CREATE REL TABLE IF NOT EXISTS Protects(
    FROM Middleware TO Page,
    FROM Middleware TO ApiRoute,
    FROM Middleware TO Layout
);

// ─── Dependency Relationships ────────────────────────────────────────────────
// These define runtime dependencies: A needs B to function

// Component/Page uses Hook
CREATE REL TABLE IF NOT EXISTS UsesHook(
    FROM Page TO Hook,
    FROM Component TO Hook,
    FROM Layout TO Hook,
    FROM Hook TO Hook,
    FROM ApiRoute TO Hook
);

// Component/Page uses Context
CREATE REL TABLE IF NOT EXISTS UsesContext(
    FROM Page TO Context,
    FROM Component TO Context,
    FROM Layout TO Context
);

// Component/Page/ApiRoute calls Service or ApiRoute
CREATE REL TABLE IF NOT EXISTS Calls(
    FROM Page TO ApiRoute,
    FROM Page TO Service,
    FROM Component TO ApiRoute,
    FROM Component TO Service,
    FROM Layout TO Service,
    FROM ApiRoute TO Service,
    FROM ApiRoute TO ApiRoute,
    FROM Service TO Service,
    FROM Service TO ApiRoute,
    FROM Hook TO Service,
    FROM Hook TO ApiRoute
);

// General component dependency
CREATE REL TABLE IF NOT EXISTS DependsOn(
    FROM Component TO Component,
    FROM Service TO Service,
    FROM Hook TO Hook,
    FROM Page TO Page,
    strength    STRING    // required | optional
);

// ─── Data Flow Relationships ─────────────────────────────────────────────────
// These define how data types flow through the system

// Component/Service/ApiRoute uses TypeDef
CREATE REL TABLE IF NOT EXISTS UsesType(
    FROM Component TO TypeDef,
    FROM Service TO TypeDef,
    FROM ApiRoute TO TypeDef,
    FROM Hook TO TypeDef,
    FROM Page TO TypeDef,
    usage       STRING    // props | state | request | response | internal
);

// TypeDef references another TypeDef (composition, extension)
CREATE REL TABLE IF NOT EXISTS References(
    FROM TypeDef TO TypeDef,
    relation    STRING    // extends | contains | uses
);

// ─── Feature Relationships ───────────────────────────────────────────────────
// These link business capabilities to technical implementations

// Feature is implemented by technical components
CREATE REL TABLE IF NOT EXISTS Implements(
    FROM Feature TO Page,
    FROM Feature TO Component,
    FROM Feature TO ApiRoute,
    FROM Feature TO Service,
    FROM Feature TO Hook,
    FROM Feature TO Middleware
);

// Feature/Component satisfies a Requirement
CREATE REL TABLE IF NOT EXISTS Satisfies(
    FROM Feature TO Requirement,
    FROM Page TO Requirement,
    FROM ApiRoute TO Requirement,
    FROM Service TO Requirement,
    FROM Component TO Requirement,
    FROM Middleware TO Requirement
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
    FROM Component TO Component,
    FROM Page TO Page,
    reason      STRING
);

// ─── Test Relationships ─────────────────────────────────────────────────────
// These link test suites to the features and components they verify

// Feature/Component is verified by a TestSuite
CREATE REL TABLE IF NOT EXISTS VerifiedBy(
    FROM Feature TO TestSuite,
    FROM Page TO TestSuite,
    FROM Component TO TestSuite,
    FROM ApiRoute TO TestSuite,
    FROM Service TO TestSuite,
    FROM Hook TO TestSuite,
    FROM Middleware TO TestSuite,
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
    FROM Page TO SecurityConstraint,
    FROM ApiRoute TO SecurityConstraint,
    FROM Service TO SecurityConstraint,
    FROM Middleware TO SecurityConstraint,
    FROM Component TO SecurityConstraint,
    enforced_at STRING    // route | middleware | component
);

// Component requires a specific Role for access
CREATE REL TABLE IF NOT EXISTS RequiresRole(
    FROM Page TO Role,
    FROM ApiRoute TO Role,
    FROM Service TO Role,
    FROM Component TO Role,
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
