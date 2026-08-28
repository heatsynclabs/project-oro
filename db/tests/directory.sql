-- The member directory. Row visibility is a policy, column visibility is a view.
\pset pager off
\set QUIET on
SET client_min_messages = notice;
INSERT INTO members (id,identity_subject,name,email,phone,email_visible,phone_visible,listed_in_directory)
VALUES
 ('bbbbbbbb-0000-0000-0000-000000000001','sub-open','Open Olive','olive@example.test','480 555 0001',true,true,true),
 ('bbbbbbbb-0000-0000-0000-000000000002','sub-shy','Shy Sam','sam@example.test','480 555 0002',false,false,true),
 ('bbbbbbbb-0000-0000-0000-000000000003','sub-hidden','Hidden Hal','hal@example.test','480 555 0003',true,true,false);
\set QUIET off

SET ROLE oro_api;
SET LOCAL oro.identity_subject = 'sub-open';
CALL t.must_query('the directory lists members who opted in',
  'SELECT count(*) FROM member_directory', '2');

CALL t.must_query('a member who opted out is not listed',
  $$SELECT count(*) FROM member_directory WHERE name='Hidden Hal'$$, '0');

CALL t.must_query('an email is shown when the member chose to show it',
  $$SELECT email FROM member_directory WHERE name='Open Olive'$$, 'olive@example.test');

CALL t.must_query('an email is hidden when the member did not',
  $$SELECT email FROM member_directory WHERE name='Shy Sam'$$, NULL);

CALL t.must_query('a phone is hidden when the member did not',
  $$SELECT phone FROM member_directory WHERE name='Shy Sam'$$, NULL);

CALL t.note('now as a real member, through the policy rather than as table owner');
SET ROLE oro_api;
SET LOCAL oro.identity_subject = 'sub-shy';

CALL t.must_query('a member sees the directory',
  'SELECT count(*) FROM member_directory', '2');

CALL t.must_query('and reads a phone the owner chose to publish',
  $$SELECT phone FROM member_directory WHERE name='Open Olive'$$, '480 555 0001');

CALL t.must_query('but not one the owner chose to hide',
  $$SELECT phone FROM member_directory WHERE name='Shy Sam'$$, NULL);

CALL t.must_query('and cannot reach a member who opted out of the directory',
  $$SELECT count(*) FROM member_directory WHERE name='Hidden Hal'$$, '0');

RESET ROLE;
