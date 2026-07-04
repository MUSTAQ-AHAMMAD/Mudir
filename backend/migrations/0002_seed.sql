-- =============================================================================
-- Mudir — seed data for local development / demos.
-- Creates three team leads and one in-flight store-opening project.
-- =============================================================================

insert into team_leads (team_name, whatsapp_number, escalation_number) values
  ('property',  'whatsapp:+966500000001', 'whatsapp:+966500000099'),
  ('marketing', 'whatsapp:+966500000002', 'whatsapp:+966500000099'),
  ('it',        'whatsapp:+966500000003', 'whatsapp:+966500000099')
on conflict do nothing;

insert into projects (code, name, status, current_team, location, opening_date, metadata)
values (
  'P-001',
  'Riyadh Mall Store #342',
  'property_pending',
  'property',
  'Riyadh',
  current_date + interval '15 days',
  '{"workflow": ["property", "marketing", "it"]}'::jsonb
)
on conflict (code) do nothing;
