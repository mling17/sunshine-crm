-- Read-only MySQL 8 postcheck. Every row must return PASS before enabling traffic.
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
  SELECT DISTINCT c.id AS customer_id
  FROM `customers` c
  JOIN `leads` l
    ON l.converted_customer_id = c.id
   AND l.is_delete = 0
  WHERE c.is_delete = 0
    AND COALESCE(TRIM(c.phone), '') <> COALESCE(TRIM(l.phone), '')
),
checks(check_code, ok, detail) AS (
  SELECT
    'schema_version',
    (
      SELECT COUNT(*) FROM `schema_migrations`
      WHERE version IN ('v2_023', 'v2_024', 'v2_025')
    ) = 3,
    'v2_023/v2_024/v2_025 present'
  UNION ALL
  SELECT
    'users_is_active',
    (
      SELECT COUNT(*) FROM `information_schema`.`columns`
      WHERE table_schema = DATABASE()
        AND table_name = 'users'
        AND column_name = 'is_active'
    ) = 1,
    'users.is_active'
  UNION ALL
  SELECT
    'leads_created_by',
    (
      SELECT COUNT(*) FROM `information_schema`.`columns`
      WHERE table_schema = DATABASE()
        AND table_name = 'leads'
        AND column_name = 'created_by'
    ) = 1,
    'leads.created_by'
  UNION ALL
  SELECT
    'follow_ups_created_by',
    (
      SELECT COUNT(*) FROM `information_schema`.`columns`
      WHERE table_schema = DATABASE()
        AND table_name = 'follow_ups'
        AND column_name = 'created_by'
    ) = 1,
    'follow_ups.created_by'
  UNION ALL
  SELECT
    'api_tokens_contract',
    (
      SELECT COUNT(*) FROM `information_schema`.`columns`
      WHERE table_schema = DATABASE()
        AND table_name = 'api_tokens'
        AND column_name IN (
          'id', 'name', 'token', 'user_id', 'expires_at', 'revoked_at',
          'created_at', 'updated_at', 'create_time', 'update_time', 'is_delete'
        )
    ) = 11,
    'api_tokens required columns'
  UNION ALL
  SELECT
    'api_tokens_audit',
    (
      SELECT COUNT(*) FROM `information_schema`.`columns`
      WHERE table_schema = DATABASE()
        AND table_name = 'api_tokens'
        AND column_name IN ('create_time', 'update_time', 'is_delete')
    ) = 3,
    'api_tokens standard audit columns'
  UNION ALL
  SELECT
    'api_tokens_no_fk',
    (
      SELECT COUNT(*) FROM `information_schema`.`table_constraints`
      WHERE constraint_schema = DATABASE()
        AND table_name = 'api_tokens'
        AND constraint_type = 'FOREIGN KEY'
    ) = 0,
    'api_tokens has no database foreign keys'
  UNION ALL
  SELECT
    'api_idempotency_contract',
    (
      SELECT COUNT(*) FROM `information_schema`.`columns`
      WHERE table_schema = DATABASE()
        AND table_name = 'api_idempotency_records'
        AND column_name IN (
          'id', 'token_id', 'endpoint', 'idempotency_key', 'request_hash',
          'response_status', 'response_body', 'expires_at', 'created_at',
          'updated_at', 'create_time', 'update_time', 'is_delete'
        )
    ) = 13,
    'api_idempotency_records required columns'
  UNION ALL
  SELECT
    'api_idempotency_audit',
    (
      SELECT COUNT(*) FROM `information_schema`.`columns`
      WHERE table_schema = DATABASE()
        AND table_name = 'api_idempotency_records'
        AND column_name IN ('create_time', 'update_time', 'is_delete')
    ) = 3,
    'api_idempotency_records standard audit columns'
  UNION ALL
  SELECT
    'api_idempotency_no_fk',
    (
      SELECT COUNT(*) FROM `information_schema`.`table_constraints`
      WHERE constraint_schema = DATABASE()
        AND table_name = 'api_idempotency_records'
        AND constraint_type = 'FOREIGN KEY'
    ) = 0,
    'api_idempotency_records has no database foreign keys'
  UNION ALL
  SELECT
    'customer_source_api',
    EXISTS (
      SELECT 1 FROM `dict_items`
      WHERE dict_code = 'customer_source'
        AND `key` = 'api'
        AND label = 'API'
        AND enabled = 1
        AND is_delete = 0
    ),
    'customer_source.api enabled'
  UNION ALL
  SELECT
    'active_api_token',
    EXISTS (
      SELECT 1
      FROM `api_tokens` t
      JOIN `users` u ON u.id = t.user_id
      WHERE t.is_delete = 0
        AND t.revoked_at IS NULL
        AND (t.expires_at IS NULL OR t.expires_at = ''
             OR t.expires_at > DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ'))
        AND u.is_delete = 0
        AND u.is_active = 1
    ),
    'at least one active Token bound to an active user'
  UNION ALL
  SELECT
    'customer_without_source_lead',
    NOT EXISTS (SELECT 1 FROM source_counts WHERE source_lead_count = 0),
    'zero customers without source leads'
  UNION ALL
  SELECT
    'customer_without_active_opportunity',
    NOT EXISTS (
      SELECT 1 FROM active_opportunity_counts
      WHERE active_opportunity_count = 0
    ),
    'zero customers without active opportunities'
  UNION ALL
  SELECT
    'source_phone_mismatch',
    NOT EXISTS (SELECT 1 FROM phone_mismatches),
    'zero source-lead/customer phone mismatches'
  UNION ALL
  SELECT
    'multiple_source_leads',
    NOT EXISTS (SELECT 1 FROM source_counts WHERE source_lead_count > 1),
    'zero customers with multiple source leads'
)
SELECT
  check_code,
  CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS status,
  detail
FROM checks
ORDER BY check_code;
