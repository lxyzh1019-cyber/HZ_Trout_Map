# Repository rules

The working rules for this repository come from `hz-claude-config`: `.claude/hz-loader.py` fetches them at session start and the session-start hook injects them. They are not copied into this repository — do not add copies, and do not edit `.claude/settings.json`, `.claude/hz-loader.py` or `.claude/agents/opus-worker.md` here; changes to them go through `hz-claude-config`.

If the "Global Working Rules" are not in your context at session start, stop before any work and tell me: "Central rules not loaded in this session."

Repository-specific files: `FEATURES.md` and `WORKING_RECORD.md`.
