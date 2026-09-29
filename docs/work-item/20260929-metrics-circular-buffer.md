# Metrics Circular Buffer

## Status

done

## Outcome

The controller owns a fixed 30-minute, 1,800-point Metrics circular buffer. The UI reads selected ranges through chunked API requests and continuation cursors. Clear Metrics clears controller storage and the displayed API response cache.

Prometheus and Elasticsearch remain future external targets for longer metrics and log retention. Neither is a dependency or partial implementation in this change.

## Decision Changes

- Replace configurable day-scale controller retention with a fixed 30-minute in-memory buffer.
- Serve historical chart samples through an authenticated range API instead of status snapshots.
- Keep bounded persistence only as a restart warm-start.

## Main Quests

- Bound controller metric storage and persistence to 1,800 samples / 1,800 seconds.
- Load chart ranges from the controller in pages and append continuation samples while Metrics is visible.
- Re-fetch the selected range when Metrics is activated again.

## Acceptance Criteria

- Samples older than the retained 30-minute interval are pruned and excluded from export.
- The authenticated API returns ascending pages of at most 240 rows with exclusive continuation cursors.
- Status snapshots contain no historical series; chart samples originate only from the Metrics API.
- Clear Metrics clears controller history and the displayed API cache.
- Prometheus and Elasticsearch are documented as future longer-retention integrations only.

## Metadata

### id

metrics-circular-buffer

### type

Issue
