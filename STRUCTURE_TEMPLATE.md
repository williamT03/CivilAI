# CivilAI Folder Structure Template

This project is moving toward a feature-folder style where each folder explains its purpose, keeps builder/tooling code behind a small facade, and exposes one readable run file for programmers to call.

## Pattern

```text
FeatureName/
  README.md                 # What this feature owns and when to use it.
  feature_run.py            # The public facade. Call this first.
  Tools/
    builder_or_tool.py      # Builders, low-level tools, adapters, helpers.
    another_tool.py
```

## Rules

- `*_run.py` files should read like a short command surface.
- `Tools/` files can hold builder details, adapters, and lower-level mechanics.
- Existing behavior should move only after tests pass through a compatibility facade.
- Public imports should stay stable until callers are migrated.
- Delete only generated files, stale docs, or wrappers with no callers.

## Python Example

```text
Features/
  __init__.py              # Final public facade for this folder.
  Auth/
    auth_run.py
    Tools/
      auth.py
  Parser/
    parser_run.py
    Tools/
      parser.py
  Pipeline/
    pipeline_run.py
    Tools/
      pipeline.py
```

In Python, avoid having both `Features.py` and a `Features/` folder because they compete for the same import name. Use `Features/__init__.py` as the final public facade.

## TypeScript Example

```text
Features/
  index.ts                 # Final public facade for this folder.
  Chat/
    README.md
    chat_run.ts
    Tools/
      chatApi.ts
      chatHooks.ts
      chatComponents.ts
```

Framework files can still import through the feature facade while staying where the framework expects them.
