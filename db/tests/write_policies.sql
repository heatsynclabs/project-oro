-- What each role may write. An earlier pass built read isolation and no write
-- policies at all, which left two holes: the API could not insert anything, and
-- the tables carrying authority had no row level security while the application
-- role held INSERT and UPDATE on them.
\pset pager off
\set QUIET on
SET client_min_messages = notice;
INSERT INTO members (id,identity_subject,name,email,tier_id,standing,joined_on) VALUES
 ('ffffffff-0000-0000-0000-000000000001','sub-plain','Plain Pim','pim@example.test','basic','good','2020-01-01'),
 ('ffffffff-0000-0000-0000-000000000002','sub-boss','Boss Bea','bea@example.test','basic','good','2020-01-01');
INSERT INTO member_roles (member_id,role_id) VALUES
 ('ffffffff-0000-0000-0000-000000000002','admin');
INSERT INTO certifications (id,name) VALUES ('laser','Laser cutter'),('mill','Mill');
\set QUIET off

SET ROLE oro_api;

CALL t.note('is_admin answers about other people, not just the caller');
SET LOCAL oro.identity_subject = 'sub-plain';
CALL t.must_query('a plain member can see that somebody else is an admin',
  $$SELECT is_admin('ffffffff-0000-0000-0000-000000000002')::text$$, 'true');
CALL t.must_query('and admin_count sees every admin, not only visible rows',
  $$SELECT admin_count()::text$$, '1');
RESET ROLE; SET ROLE oro_api;

CALL t.note('a plain member cannot grant themselves anything');
SET LOCAL oro.identity_subject = 'sub-plain';

CALL t.must_fail('granting themselves an ordinary role',
  $$INSERT INTO member_roles (member_id,role_id)
    VALUES ('ffffffff-0000-0000-0000-000000000001','accountant')$$,
  'row-level security');
CALL t.must_fail('granting themselves admin',
  $$INSERT INTO member_roles (member_id,role_id)
    VALUES ('ffffffff-0000-0000-0000-000000000001','admin')$$,
  'row-level security');
CALL t.must_change('rewriting the bylaws numbers changes nothing',
  $$UPDATE governance_parameters SET value='0' WHERE key='card_access.tenure_months'$$, 0);
CALL t.must_fail('inventing a membership tier',
  $$INSERT INTO tiers (id,name,monthly_cents,sort_order,card_eligible)
    VALUES ('free-plus','Free Plus',0,9,true)$$,
  'row-level security');
CALL t.must_fail('issuing themselves a card',
  $$INSERT INTO cards (member_id,tag_number,controller_slot)
    VALUES ('ffffffff-0000-0000-0000-000000000001','0000FEED',77)$$,
  'row-level security');
CALL t.must_fail('recording a waiver for themselves',
  $$INSERT INTO waivers (member_id,signed_at,storage)
    VALUES ('ffffffff-0000-0000-0000-000000000001',now(),'made-up')$$,
  'row-level security');
CALL t.must_fail('certifying themselves on the laser',
  $$INSERT INTO member_certifications (member_id,certification_id)
    VALUES ('ffffffff-0000-0000-0000-000000000001','laser')$$,
  'row-level security');
CALL t.must_fail('creating another member',
  $$INSERT INTO members (name,email) VALUES ('Ghost','ghost@example.test')$$,
  'row-level security');
CALL t.must_query('and the bylaws numbers are readable but unchanged',
  $$SELECT value::text FROM governance_parameters WHERE key='card_access.tenure_months'$$, '2');

CALL t.note('an admin can do the work the portal needs');
SET LOCAL oro.identity_subject = 'sub-boss';

CALL t.must_change('create a member, which the kiosk waiver path needs',
  $$INSERT INTO members (name,email) VALUES ('Walk In Win','win@example.test')$$);
CALL t.must_change('issue a card',
  $$INSERT INTO cards (member_id,tag_number,controller_slot)
    VALUES ('ffffffff-0000-0000-0000-000000000001','0000FEED',77)$$);
CALL t.must_change('record a waiver reference',
  $$INSERT INTO waivers (member_id,signed_at,storage,reference)
    VALUES ('ffffffff-0000-0000-0000-000000000001',now(),'google-form','r-1')$$);
CALL t.must_change('grant an ordinary role',
  $$INSERT INTO member_roles (member_id,role_id)
    VALUES ('ffffffff-0000-0000-0000-000000000001','accountant')$$);
CALL t.must_change('open an approval',
  $$INSERT INTO approvals (kind,target_member_id,role_id,proposed_by)
    VALUES ('grant_role','ffffffff-0000-0000-0000-000000000001','admin',
            'ffffffff-0000-0000-0000-000000000002')$$);
CALL t.must_query('and read it back, which a forced table with no policy cannot',
  $$SELECT count(*) FROM approvals$$, '1');
CALL t.must_change('correct a bylaws number',
  $$UPDATE governance_parameters SET value='3' WHERE key='card_access.tenure_months'$$);

CALL t.note('only an instructor for that tool may grant its certification');
CALL t.must_change('an admin may grant any',
  $$INSERT INTO member_certifications (member_id,certification_id)
    VALUES ('ffffffff-0000-0000-0000-000000000002','mill')$$);
RESET ROLE;
INSERT INTO certification_instructors (member_id,certification_id)
  VALUES ('ffffffff-0000-0000-0000-000000000001','laser');
SET ROLE oro_api;
SET LOCAL oro.identity_subject = 'sub-plain';
CALL t.must_change('a laser instructor may grant the laser',
  $$INSERT INTO member_certifications (member_id,certification_id)
    VALUES ('ffffffff-0000-0000-0000-000000000002','laser')$$);
CALL t.must_fail('but not the mill',
  $$INSERT INTO member_certifications (member_id,certification_id)
    VALUES ('ffffffff-0000-0000-0000-000000000001','mill')$$,
  'row-level security');
RESET ROLE;

CALL t.note('the bylaws numbers are actually read by something');
CALL t.must_query('eligibility uses the tenure value, not a constant',
  $$SELECT reason FROM card_eligibility('ffffffff-0000-0000-0000-000000000001')$$,
  'Eligible. A cardholder nominates, and card members vote at Hack Your Hackerspace.');
UPDATE governance_parameters SET value='600' WHERE key='card_access.tenure_months';
CALL t.must_query('raising tenure to 600 months makes the same member ineligible',
  $$SELECT eligible::text FROM card_eligibility('ffffffff-0000-0000-0000-000000000001')$$,
  'false');

CALL t.note('first sign in claims an existing row rather than duplicating it');
CALL t.must_query('a member an admin created has no identity yet',
  $$SELECT count(*) FROM members WHERE email='win@example.test' AND identity_subject IS NULL$$, '1');
CALL t.must_query('signing in claims that row',
  $$SELECT link_or_create_member('sub-win','win@example.test','Walk In Win') =
           (SELECT id FROM members WHERE email='win@example.test')$$, 'true');
CALL t.must_query('and creates no duplicate',
  $$SELECT count(*) FROM members WHERE email='win@example.test'$$, '1');
CALL t.must_query('signing in again is idempotent',
  $$SELECT link_or_create_member('sub-win','win@example.test','Walk In Win') =
           (SELECT id FROM members WHERE email='win@example.test')$$, 'true');

CALL t.note('migrations are an operator action, not something the app can touch');
SET ROLE oro_api;
CALL t.must_fail('the app role cannot read the migration log',
  'SELECT count(*) FROM schema_migrations', 'permission denied');
CALL t.must_fail('nor forge an entry in it',
  $$INSERT INTO schema_migrations (filename,sha256) VALUES ('fake.sql','0')$$,
  'permission denied');
RESET ROLE;
CALL t.must_query('and every migration that ran is recorded',
  $$SELECT (count(*) > 8)::text FROM schema_migrations$$, 'true');
