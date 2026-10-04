# Portfolio architecture

Three views of the implemented v0.1 system. For operational contracts, use the
[architecture overview](overview.md); for the product story, use the
[portfolio walkthrough](../portfolio-walkthrough.md).

## A. Full product lifecycle

```mermaid
flowchart TB
    subgraph Discovery
        S[Original signal] --> H[Hypothesis and explicit unknowns]
        H --> E[Scoped supporting and contradicting evidence]
        E --> V[Targeted validation]
        V --> DG[Discovery Gate]
    end
    subgraph Delivery
        SEL[Human delivery selection] --> SPEC[Versioned DeliverySpec]
        SPEC --> R[Completeness, clarification and human review]
        R --> G[Delivery Gate]
        G --> A[Human handoff authorization]
        A --> I[Supplied implementation record and deviations]
    end
    subgraph Learning
        P[Measurement plan and observations] --> T[Deterministic target evaluation]
        T --> C[Human causal interpretation]
        C --> F[Append outcome evidence]
        F --> OR[Human outcome review]
        OR --> END[Human-reviewed closure]
    end
    DG --> SEL
    I --> P
    F -. New learning for discovery .-> E
```

This is a representative flow, not the exhaustive transition graph or strict ordering of
all review records. Evidence feedback informs the final review, and unresolved questions
can feed a distinct follow-up hypothesis. Gate pass permits a bounded next step; it neither
selects work nor executes implementation. Closed means a reviewed episode.

## B. Authority boundary

```mermaid
flowchart TB
    INPUT[Supplied signals, sources and strategy] --> AI[AI: interpret, challenge, draft]
    INPUT --> CORE[Deterministic core: evidence, readiness, gates and targets]
    AI --> P[Retained advisory proposals]
    P --> HUMAN[Humans: select, accept or reject, review and interpret causality]
    CORE --> BASIS[Explicit conditions and limitations]
    BASIS --> HUMAN
    HUMAN --> OP[Explicit application operations]
    OP --> CORE
    CORE --> RECORD[Versioned records and matching audits]
```

Humans supply semantic judgments and intent; code enforces valid operations under current
policy and supplied versions. Human accountability does not mean unrestricted bypass.
AI proposals cannot mutate authoritative records directly. See
[authority boundaries](authority-boundaries.md) for implemented override limits.

## C. Simplified system architecture

Arrows indicate dependency/use, rather than deployment services.

```mermaid
flowchart TB
    ENTRY[Offline examples / callers] --> APP[Application: use cases and provider protocols]
    PRES[Presentation: reserved boundary, no API or UI] -. Future entry point .-> APP
    APP --> DOMAIN[Domain: pure records, policies and invariants]
    INFRA[Infrastructure: TOML loaders and OpenAI adapters] --> APP
    INFRA --> DOMAIN
    INFRA --> AI[AI: versioned prompt instructions]
    INFRA --> EXT[Optional OpenAI service]
    CONFIG[Config: versioned TOML policies] --> INFRA
    TESTS[Tests: unit, integration and offline evals] -. Verify .-> DOMAIN
    TESTS -. Verify .-> APP
    TESTS -. Mock provider transport .-> INFRA
```

The domain imports no other architectural layer. Application services use provider
protocols; concrete adapters live in infrastructure and are supplied by callers. Prompt
modules contain interpretation instructions, while authoritative policy stays in code
and validated configuration. The presentation package is a placeholder. This architecture
is one Python modular monolith with no production storage or hosted service.
