The atlas now dispatches extraction through a suffix registry — a third
language is one `register_extractor` call, not a core edit — records
`tested-by` and `documents` edges so `affected` can bound traversal by
relation kind and bucket its answer into callers / tests / docs, and can be
persisted with `save_index` / `load_index`, which reports fresh, stale, and
missing files from content hashes with a derived confidence, never from time.
