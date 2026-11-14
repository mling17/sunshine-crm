-- One-time MySQL token initialization template.
-- Replace all {{PLACEHOLDER}} values before execution. Never commit a real token.
-- {{EXPIRES_AT_SQL_LITERAL_OR_NULL}} is either NULL or an ISO timestamp string
-- such as '2027-01-01T00:00:00Z'.
INSERT INTO `api_tokens`
  (`name`, `token`, `user_id`, `expires_at`, `revoked_at`, `created_at`, `updated_at`,
   `create_time`, `update_time`)
SELECT
  '{{TOKEN_NAME}}',
  '{{TOKEN_VALUE}}',
  `id`,
  {{EXPIRES_AT_SQL_LITERAL_OR_NULL}},
  NULL,
  DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ'),
  DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ'),
  DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ'),
  DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')
FROM `users`
WHERE `username` = '{{BOUND_USERNAME}}'
  AND `is_active` = 1
  AND `is_delete` = 0;
