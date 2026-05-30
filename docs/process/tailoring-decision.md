# Project Tailoring Decision

Status: approved by Russ in Discord `#moose-inventory-python` on 2026-05-29.

## Project

`moose-inventory-python` is a Python CLI package intended to be interchangeable with the Ruby `moose-inventory` CLI.

Reference implementation:

- Ruby source project: `../moose-inventory`
- Python target project: `../moose-inventory-python`

## Classification

Treat this project as serious distributed software with a **Software CLI Package / Command Package** target profile.

This is close to the workspace `Software Library / Package` profile, but the primary public interface is the command line rather than an importable Python API.

## Required concerns

The project must keep discipline around:

- Ruby CLI compatibility
- command names, flags, defaults, exit behavior, and protected output compatibility
- configuration discovery and YAML configuration compatibility
- Ansible dynamic inventory compatibility
- database backend support for SQLite, MySQL/MariaDB, and PostgreSQL
- database schema compatibility with the Ruby implementation
- snapshot import/export schema compatibility
- dry-run and machine-readable plan output compatibility
- test coverage and Ruby-vs-Python parity evidence
- package build and release integrity
- dependency and supply-chain hygiene
- vulnerability intake and security patch maintenance
- maintainer/release ownership
- user documentation and migration guidance

## Excluded by default

Because this project is a CLI package rather than a hosted service, daemon, or scheduled runtime component, the following are excluded by default:

- service operations runbook
- monitoring and alerting dashboards
- pager-style incident response
- backup/restore operation of customer or production infrastructure
- runtime service-level support process
- AI-agent runtime-operation boundaries for a non-existent runtime service

These exclusions stop applying if the project later adds a hosted service, daemon, scheduler, telemetry backend, license/update service, production credentials, persistent operated storage, or any other component that someone must operate at runtime.

## Approval boundaries

Human approval is still required for:

- public package release or publishing
- accepted security risk
- breaking CLI, schema, config, snapshot, or Ansible compatibility changes
- external communications or public claims
- destructive repository/package-registry actions
- changes to GitHub/PyPI security or publishing settings

## Practical rule

Do not underbuild this as a casual script, and do not overbuild it as a production service.

Build it as a reliable, compatible, releasable Python CLI package whose behavior can be proven against the Ruby implementation.
