A derived SQLite index (`index.db` in the archive) now persists ranked corpus
segments, compiled rules, and archive summaries between sessions: `rebuild`
regenerates it wholesale from the live sources, `fresh` proves the sources have
not moved before any read, and `query` refuses a stale index outright unless
the caller opts in and accepts a `stale: true` label. Alongside it, a read-only
database architecture manager inventories every SQLite file via `mode=ro`,
runs the 11-row Mandatory Schema Review (rollback text is a hard fail, never a
question), and statically flags hazardous migration SQL such as `DELETE`
without `WHERE`.
