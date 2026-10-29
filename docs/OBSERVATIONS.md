# Repeated observation baseline (M2 incremental slice)

Focu records content fingerprints per caller-defined `scope_id` and canonical HTTP(S) URL in the same SQLite database as intents and evidence packs.

```python
from focu.observations import ObservationStore
store = ObservationStore("data/focu.sqlite3")
result = store.observe("my-watch", "https://example.com/update", "Agent-fetched page text")
# status: new | changed | unchanged
```

- **new**: the source has not been observed in this scope.
- **changed**: a different, previously unseen fingerprint was stored after an earlier observation.
- **unchanged**: the latest content matches or this exact fingerprint was recorded before. Repeated ingestion is idempotent.
- `requires_semantic_review` means the host agent *may need* to evaluate importance; it is **not** permission to notify.
- Whitespace is normalized; exact text changes can still be insignificant. URL query strings are preserved to avoid conflating distinct resources.
- The host agent owns fetching, scope authorization, semantic assessment, scheduling, and delivery. Focu does not silently create subscriptions or notifications.

This is a persistence and deduplication primitive, **not** a Watch implementation, a semantic change detector, or a notification engine.
