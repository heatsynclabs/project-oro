-- A view is not covered by the policies on the tables underneath it unless it
-- says so. Both views here once ran as their owner and handed rows to a caller
-- with no identity, while the base tables refused that caller correctly.
\pset pager off
\set QUIET on
SET client_min_messages = notice;
INSERT INTO members (id,identity_subject,name,email,listed_in_directory,phone,phone_visible) VALUES
 ('bbbb1111-0000-0000-0000-000000000001','sub-lou','Listed Lou','lou@example.test',true,'480 555 0001',false),
 ('bbbb1111-0000-0000-0000-000000000002','sub-hana','Hidden Hana','hana@example.test',false,'480 555 0002',true),
 ('bbbb1111-0000-0000-0000-000000000003','sub-hosty','Hosty Hal','hal@example.test',true,NULL,false),
 ('bbbb1111-0000-0000-0000-000000000004','sub-nosy','Nosy Ned','ned@example.test',true,NULL,false);
INSERT INTO member_roles (member_id,role_id) VALUES ('bbbb1111-0000-0000-0000-000000000003','host');
INSERT INTO waivers (member_id,signed_at,storage,reference) VALUES
 ('bbbb1111-0000-0000-0000-000000000001',now(),'google-form','ref-lou');
\set QUIET off

SET ROLE oro_api;

CALL t.note('a caller with no identity gets nothing, views included');
CALL t.must_fail('the directory', 'SELECT count(*) FROM member_directory',
  'No identity set');
CALL t.must_fail('waiver status',
  $$SELECT * FROM waiver_status('bbbb1111-0000-0000-0000-000000000001')$$,
  'No identity set');

CALL t.note('the directory honours the policy and the column rules');
SET LOCAL oro.identity_subject = 'sub-lou';
CALL t.must_query('a member sees listed members only',
  'SELECT count(*) FROM member_directory', '3');
CALL t.must_query('and cannot reach one who opted out',
  $$SELECT count(*) FROM member_directory WHERE name='Hidden Hana'$$, '0');
CALL t.must_query('a phone hidden by its owner stays hidden',
  $$SELECT phone FROM member_directory WHERE name='Listed Lou'$$, NULL);

CALL t.note('waiver status is gated by role, not open to everyone');
SET LOCAL oro.identity_subject = 'sub-nosy';
CALL t.must_fail('an ordinary member cannot check somebody else',
  $$SELECT * FROM waiver_status('bbbb1111-0000-0000-0000-000000000001')$$,
  'hosting or instructing role');
CALL t.must_query('but may check themselves',
  $$SELECT count(*) FROM waiver_status('bbbb1111-0000-0000-0000-000000000004')$$, '0');

SET LOCAL oro.identity_subject = 'sub-hosty';
CALL t.must_query('a host may check another member',
  $$SELECT has_valid_waiver::text FROM waiver_status('bbbb1111-0000-0000-0000-000000000001')$$,
  'true');
CALL t.must_query('and gets the fact and the date, nothing else',
  $$SELECT string_agg(a.attname,',' ORDER BY a.attname)
     FROM pg_proc p, unnest(p.proargnames) WITH ORDINALITY AS a(attname, ord)
     WHERE p.proname='waiver_status' AND a.attname NOT LIKE 'p\_%'$$,
  'has_valid_waiver,latest_signed_at,member_id');
RESET ROLE;
