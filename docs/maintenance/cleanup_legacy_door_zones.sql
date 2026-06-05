-- M2b: legacy door-zone cleanup.
--
-- Older frontend builds created every transit zone with the same placeholder
-- mid-house polygon and direction. Delete these rows after confirming no
-- caregiver intentionally authored them outside the fixed editor.

BEGIN;

SELECT id, name, kind, inside_room_id, outside_room_id, polygon, direction_vec
FROM transit_zones
WHERE polygon = '[[0.4, 0.45], [0.6, 0.45], [0.6, 0.55], [0.4, 0.55]]'::jsonb
  AND direction_vec = '[1.0, 0.0]'::jsonb;

-- DELETE FROM transit_zones
-- WHERE polygon = '[[0.4, 0.45], [0.6, 0.45], [0.6, 0.55], [0.4, 0.55]]'::jsonb
--   AND direction_vec = '[1.0, 0.0]'::jsonb;

ROLLBACK;
