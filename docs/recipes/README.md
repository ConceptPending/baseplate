# Recipes

Guided transformations of Baseplate. Each recipe is a self-contained "if
you need this pattern, here's how it fits onto what Baseplate already
ships."

These are deliberately **not features in the base app**. Adding every
recipe to the default codebase would make it less compact and harder
for an LLM to hold in context — exactly what Baseplate is trying to
avoid. Apply the recipes you need; leave the rest.

## Format

Every recipe follows the same shape:

1. **What it is + when to use it** — one paragraph.
2. **What you'll add** — the file list, so the scope is visible upfront.
3. **Step-by-step** — concrete code snippets, not abstractions. Names the
   convention being used (service layer, router-level deps, CSRF middleware
   contract, etc.).
4. **Tests** — the assertions that prove the recipe is wired correctly.
5. **What to skip** — adjacent things that look like they belong but
   would expand scope unnecessarily.

## How to use a recipe with a coding agent

Point the agent at the recipe file directly:

> Apply `docs/recipes/audit-log.md` to this codebase. Use the existing
> `ItemService` as the model for any service-layer changes.

The agent reads the recipe, follows the steps, and produces a working
implementation. Because Baseplate's conventions are documented in
`CLAUDE.md` and the recipe assumes them, the result lands consistent
with the rest of the codebase.

## Available recipes

### [Audit log](audit-log.md)
Record who did what when. For apps with compliance, case management, or
internal review queues where a tamper-resistant action history matters.

### [Public submission + admin queue](public-submission-and-admin-queue.md)
Unauthenticated public form → admin review queue with status workflow.
The canonical "intake + review" pattern: applications, complaints,
support requests, candidate submissions, content moderation.

## Suggested future recipes (not yet written)

These came up in scoping but haven't landed yet. Open a PR if you
write one:

- **Document upload model** — file storage + metadata + admin viewer
- **Scheduled importer** — APScheduler job that fetches external data
  and stores it with a `last_synced_at` column
- **Status workflow with allowed transitions** — explicit state machine
  on a model
- **Read-only public page backed by admin CRUD** — `(public)/`-route-group
  pattern, beyond what the example `Item` already shows
- **Workspaces / multi-tenant migration** — already covered in
  [`../growth-paths/multi-tenant.md`](../growth-paths/multi-tenant.md);
  could be re-packaged as a recipe
