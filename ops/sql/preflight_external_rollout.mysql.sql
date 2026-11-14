-- Read-only MySQL 8 preflight. Any affected_count greater than zero requires review.
WITH source_counts AS (
  SELECT
    c.id AS customer_id,
    COUNT(l.id) AS source_lead_count
  FROM `customers` c
  LEFT JOIN `leads` l
    ON l.converted_customer_id = c.id
   AND l.is_delete = 0
  WHERE c.is_delete = 0
  GROUP BY c.id
),
active_opportunity_counts AS (
  SELECT
    c.id AS customer_id,
    COUNT(d.id) AS active_opportunity_count
  FROM `customers` c
  LEFT JOIN `deals` d
    ON d.customer_id = c.id
   AND d.is_delete = 0
   AND d.stage NOT IN ('won', 'lost')
  WHERE c.is_delete = 0
  GROUP BY c.id
),
phone_mismatches AS (
  SELECT DISTINCT
    c.id AS customer_id,
    l.id AS source_lead_id
  FROM `customers` c
  JOIN `leads` l
    ON l.converted_customer_id = c.id
   AND l.is_delete = 0
  WHERE c.is_delete = 0
    AND COALESCE(TRIM(c.phone), '') <> COALESCE(TRIM(l.phone), '')
)
SELECT
  'customer_without_source_lead' AS `check_code`,
  COUNT(*) AS `affected_count`,
  COALESCE(GROUP_CONCAT(`customer_id`), '') AS `object_ids`
FROM source_counts
WHERE source_lead_count = 0
UNION ALL
SELECT
  'customer_without_active_opportunity',
  COUNT(*),
  COALESCE(GROUP_CONCAT(`customer_id`), '')
FROM active_opportunity_counts
WHERE active_opportunity_count = 0
UNION ALL
SELECT
  'source_phone_mismatch',
  COUNT(*),
  COALESCE(GROUP_CONCAT(DISTINCT `customer_id`), '')
FROM phone_mismatches
UNION ALL
SELECT
  'multiple_source_leads',
  COUNT(*),
  COALESCE(GROUP_CONCAT(`customer_id`), '')
FROM source_counts
WHERE source_lead_count > 1
ORDER BY `check_code`;
