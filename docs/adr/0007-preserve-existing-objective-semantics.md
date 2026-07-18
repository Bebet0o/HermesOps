# ADR 0007: Preserve Existing Objective Semantics

Status: **Accepted**

## Context

The first API draft modeled every objective under exactly one project and used
four textual priority labels. The existing HermesOps objective queue supports
multiple projects, numeric priority from `-1000` to `1000`, delayed start,
parallel-task limits, and planning-attempt limits.

Replacing those semantics in the Web API would make the future Console less
capable than the current CLI and would create an avoidable data migration.

## Decision

API v1 preserves the existing objective semantics:

- the canonical create endpoint accepts `project_ids` with at least one entry;
- a nested project endpoint remains available as a one-project convenience;
- priority is the existing signed integer and lower values run first;
- scheduling and planning limits remain explicit API fields;
- Console labels such as high or low are presentation mappings only.

The API object is still a domain projection. It may add a title and description
through a future migration while retaining the original objective text.

## Consequences

- multi-project objectives remain possible;
- CLI and Console behavior can share one application service;
- priority ordering remains deterministic;
- the Controller requires an explicit storage-to-domain mapping;
- the Console must not assume an objective belongs to only one project.
