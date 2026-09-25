- The subprocess-heaviest test modules (the ones that shell out to the CLI
  repeatedly and together account for several minutes of suite time) now run
  only in the release check, not a routine local pass. `godmode precheck
  --preflight` still runs every one of them; nothing security-related (gate,
  authorize, guard coverage) moved.
