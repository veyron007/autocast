"""Pipeline stages. Each module exposes `run(spine, cfg, *, dry_run) -> spine`.

A stage is a pure spine->spine function: it reads fields written by prior stages,
writes ONLY its own section, and stamps its own status. Stages never call each
other — only the orchestrator knows the order.
"""
