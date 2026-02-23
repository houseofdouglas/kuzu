// Next.js Spec Graph Schema
// Tailored for Next.js applications (App Router or Pages Router)

// ─── Node Tables ─────────────────────────────────────────────────────────────

// A route/page in the application
CREATE NODE TABLE IF NOT EXISTS Page(
    id          STRING,
    name        STRING,
    description STRING,
    route       STRING,   // /dashboard, /users/[id], etc.
    router      STRING,   // app | pages
    rendering   STRING,   // server | client | static | dynamic
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

// ─── Relationship Tables ──────────────────────────────────────────────────────

// Page/Layout renders Component
CREATE REL TABLE IF NOT EXISTS Renders(
    FROM Page TO Component,
    FROM Layout TO Component,
    FROM Component TO Component
);

// Component/Page uses Hook
CREATE REL TABLE IF NOT EXISTS UsesHook(
    FROM Page TO Hook,
    FROM Component TO Hook,
    FROM Hook TO Hook
);

// Component/Page uses Context
CREATE REL TABLE IF NOT EXISTS UsesContext(
    FROM Page TO Context,
    FROM Component TO Context,
    FROM Layout TO Context
);

// Component/Page calls ApiRoute or Service
CREATE REL TABLE IF NOT EXISTS Calls(
    FROM Page TO ApiRoute,
    FROM Component TO ApiRoute,
    FROM Page TO Service,
    FROM Component TO Service,
    FROM ApiRoute TO Service,
    FROM Service TO Service
);

// General dependency
CREATE REL TABLE IF NOT EXISTS DependsOn(
    FROM Page TO Page,
    FROM Component TO Component,
    FROM Service TO Service,
    FROM Feature TO Feature,
    strength    STRING    // required | optional
);

// Feature is implemented by Page/Component/ApiRoute
CREATE REL TABLE IF NOT EXISTS Implements(
    FROM Feature TO Page,
    FROM Feature TO Component,
    FROM Feature TO ApiRoute,
    FROM Feature TO Service
);

// Feature/Service satisfies Requirement
CREATE REL TABLE IF NOT EXISTS Satisfies(
    FROM Feature TO Requirement,
    FROM Service TO Requirement,
    FROM ApiRoute TO Requirement
);

// Page belongs to Layout
CREATE REL TABLE IF NOT EXISTS BelongsTo(
    FROM Page TO Layout
);

// Context wraps other components/pages
CREATE REL TABLE IF NOT EXISTS Wraps(
    FROM Context TO Page,
    FROM Context TO Layout,
    FROM Context TO Component
);

// Informational link
CREATE REL TABLE IF NOT EXISTS RelatedTo(
    FROM Feature TO Feature,
    FROM Component TO Component,
    FROM Page TO Page,
    FROM Feature TO Requirement
);

// A and B cannot coexist
CREATE REL TABLE IF NOT EXISTS Conflicts(
    FROM Feature TO Feature,
    FROM Component TO Component,
    reason      STRING
);
