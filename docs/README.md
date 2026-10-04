# Documentation guide

Choose a short reading route, then inspect the contracts behind the decisions.
Capability documents describe their implementation increment; their historical deferrals
are superseded by later contracts. The architecture overview describes current v0.1 scope.

## Start here

- [Portfolio walkthrough](portfolio-walkthrough.md): product problem, search case, judgment and tradeoffs.
- [Architecture overview](architecture/overview.md): current layers, capability map and integrity boundaries.
- [Product specification](product-specs/discovery-prioritization-system-v0.1.md): full source-of-truth contracts, with historical requirements preserved.
- [v0.1.0 release-note draft](releases/v0.1.0.md): public capabilities and verification limits.

## Architecture

- [Visual architecture](architecture/portfolio-architecture.md): lifecycle, authority and dependency diagrams.
- [Authority boundaries](architecture/authority-boundaries.md): AI proposals, deterministic policy and human accountability.
- [Discovery interpretation](architecture/discovery-analysis.md): provider contracts and provenance safeguards.
- [Evidence and validation](architecture/evidence-validation.md): scoped quality, freshness, independence and challenges.
- [Discovery decisioning](architecture/discovery-decisioning.md): learning priority, Delivery Readiness and Discovery Gate.
- [Delivery selection and specifications](architecture/delivery-specification.md): reviewed proposals and immutable drafts.
- [Specification completeness and Delivery Gate](architecture/spec-completeness-delivery-gate.md): clarification, exact review and handoff.
- [Implementation outcomes and feedback](architecture/implementation-outcome-feedback.md): actual scope, targets, causality and closure.

## Architectural decisions

| ADR | Decision |
| --- | --- |
| [0001](decisions/0001-domain-foundation.md) | Pure domain foundation, immutable snapshots and provenance |
| [0002](decisions/0002-discovery-analysis.md) | Review proposals behind a replaceable structured provider |
| [0003](decisions/0003-evidence-validation.md) | Deterministic evidence and advisory challenges |
| [0004](decisions/0004-discovery-decisioning.md) | Separate learning priority, readiness and discovery gating |
| [0005](decisions/0005-reviewed-delivery-specification-proposals.md) | Human selection and reviewed AI specification proposals |
| [0006](decisions/0006-separate-specification-and-delivery-authority.md) | Separate completeness, clarification, review, gate and handoff |
| [0007](decisions/0007-separate-implementation-outcomes-and-causal-learning.md) | Separate implementation, outcomes and causal learning |

ADRs preserve the scope and alternatives considered at their original increment.

## Evaluation

- [Evaluation overview](evals/README.md): offline contracts versus live semantics.
- [Offline golden-evaluation guide](../tests/evals/README.md) and [fixture guide](../tests/fixtures/README.md).
- [Integration tests](../tests/integration/README.md): policy loading and composed workflows.
- [Deferred live verification](evals/deferred-live-verification.md): authorization boundary and future checklist.
- [Historical live attempt](evals/milestone-3-live-verification.md): infrastructure-blocked execution; no semantic pass.

## Development history

- [Milestones 0–7 and preserved repository narratives](history/development-history.md).
- Milestones 0–1: [validation report](architecture/milestone-0-1-validation.md) and [domain review](architecture/milestone-0-1-domain-review.md).
- [Milestone 2 review](architecture/milestone-2-review.md): discovery analysis.
- [Milestone 3 review](architecture/milestone-3-review.md): evidence and validation.
- [Milestone 4 review](architecture/milestone-4-review.md): discovery decisioning.
- [Milestone 5 review](architecture/milestone-5-review.md): selection and draft specifications.
- [Milestone 6 review](architecture/milestone-6-review.md): completeness and delivery entry.
- [Milestone 7 review](architecture/milestone-7-review.md): implementation outcomes and feedback.

Review files remain at their original paths to preserve existing links.

## Repository presentation

[Repository metadata recommendations](repository-metadata.md) record intended description,
topics and homepage settings for application after merge. The [root README](../README.md)
provides setup and the primary offline demo.
