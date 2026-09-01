-- A member edits their own profile. What they may change, and what they may not.
\pset pager off
\set QUIET on
SET client_min_messages = notice;
INSERT INTO members (id,identity_subject,name,email,tier_id,standing) VALUES
 ('dddddddd-0000-0000-0000-000000000001','sub-pat','Pat','pat@example.test','basic','good'),
 ('dddddddd-0000-0000-0000-000000000002','sub-adm','Admin Ann','ann@example.test','basic','good');
INSERT INTO member_roles (member_id,role_id)
 VALUES ('dddddddd-0000-0000-0000-000000000002','admin');
\set QUIET off

SET ROLE oro_api;
SET LOCAL oro.identity_subject = 'sub-pat';

CALL t.note('what a member may change about themselves');
CALL t.must_pass('name and display name',
  $$UPDATE members SET name='Pat Rivera', display_name='Pat' WHERE identity_subject='sub-pat'$$);
CALL t.must_pass('pronouns, phone, postal code',
  $$UPDATE members SET pronouns='they/them', phone='480 555 0199', postal_code='85201'
     WHERE identity_subject='sub-pat'$$);
CALL t.must_pass('emergency contact',
  $$UPDATE members SET emergency_name='R. Rivera', emergency_phone='480 555 0198',
     emergency_email='r@example.test' WHERE identity_subject='sub-pat'$$);
CALL t.must_pass('skills and how they heard about the lab',
  $$UPDATE members SET current_skills='soldering', desired_skills='welding',
     marketing_source='a friend' WHERE identity_subject='sub-pat'$$);
CALL t.must_pass('visibility of their own contact details',
  $$UPDATE members SET email_visible=true, phone_visible=false, listed_in_directory=true
     WHERE identity_subject='sub-pat'$$);
CALL t.must_pass('their own membership tier, as in the current app',
  $$UPDATE members SET tier_id='plus' WHERE identity_subject='sub-pat'$$);
CALL t.must_pass('a social link',
  $$UPDATE members SET github_url='https://github.com/example' WHERE identity_subject='sub-pat'$$);
CALL t.must_fail('a social link that is not a URL',
  $$UPDATE members SET website_url='not a url' WHERE identity_subject='sub-pat'$$,
  'social_urls_are_http');

CALL t.note('what only an admin may change');
CALL t.must_fail('their own standing',
  $$UPDATE members SET standing='lapsed' WHERE identity_subject='sub-pat'$$,
  'set by an admin');
CALL t.must_pass('setting a protected field to the value it already has, which changes nothing',
  $$UPDATE members SET standing='good' WHERE identity_subject='sub-pat'$$);
CALL t.must_fail('their own orientation date',
  $$UPDATE members SET oriented_at=now() WHERE identity_subject='sub-pat'$$,
  'set by an admin');
CALL t.must_fail('how long they are paid through',
  $$UPDATE members SET paid_through='2027-01-01' WHERE identity_subject='sub-pat'$$,
  'set by an admin');
CALL t.must_fail('the identity their account is joined by',
  $$UPDATE members SET identity_subject='sub-somebody-else' WHERE identity_subject='sub-pat'$$,
  'set by an admin');
CALL t.must_fail('marking their own email verified',
  $$UPDATE members SET email_verified_at=now() WHERE identity_subject='sub-pat'$$,
  'cannot mark their own email verified');

CALL t.note('changing your email un-verifies it');
CALL t.must_pass('changing it',
  $$UPDATE members SET email='pat.new@example.test' WHERE identity_subject='sub-pat'$$);
CALL t.must_query('and it is no longer verified',
  $$SELECT coalesce(email_verified_at::text,'null') FROM members WHERE identity_subject='sub-pat'$$,
  'null');

CALL t.note('a member cannot edit anybody else, so nothing matches');
CALL t.must_query('updating another member changes no rows',
  $$WITH u AS (UPDATE members SET name='hacked'
      WHERE identity_subject='sub-adm' RETURNING 1) SELECT count(*) FROM u$$, '0');
RESET ROLE;
CALL t.must_query('and that member is untouched',
  $$SELECT name FROM members WHERE identity_subject='sub-adm'$$, 'Admin Ann');
SET ROLE oro_api;

CALL t.note('an admin may set what a member may not');
SET LOCAL oro.identity_subject = 'sub-adm';
CALL t.must_change('standing',
  $$UPDATE members SET standing='lapsed' WHERE identity_subject='sub-pat'$$);
CALL t.must_change('orientation, recording who ran it',
  $$UPDATE members SET oriented_at=now(),
     oriented_by='dddddddd-0000-0000-0000-000000000002' WHERE identity_subject='sub-pat'$$);

-- The trigger returns early for the owner, so this seeds a confirmation date
-- without going through the rule the checks below are about.
CALL t.note('an admin loses a confirmation date the same way a member does');
RESET ROLE;
\set QUIET on
UPDATE members SET email='ann@example.test', email_verified_at='2026-01-02 03:04:05+00'
  WHERE identity_subject='sub-adm';
\set QUIET off
SET ROLE oro_api;
SET LOCAL oro.identity_subject = 'sub-adm';
CALL t.must_change('an admin changes their own address',
  $$UPDATE members SET email='ann.new@example.test' WHERE identity_subject='sub-adm'$$);
CALL t.must_query('and the confirmation that belonged to the old one is gone',
  $$SELECT coalesce(email_verified_at::text,'null') FROM members WHERE identity_subject='sub-adm'$$,
  'null');
CALL t.must_change('an admin records a confirmation on an address that did not move',
  $$UPDATE members SET email_verified_at='2026-02-03 04:05:06+00'
     WHERE identity_subject='sub-adm'$$);
CALL t.must_query('and it is kept, because an admin may mark an address confirmed',
  $$SELECT email_verified_at::text FROM members WHERE identity_subject='sub-adm'$$,
  '2026-02-03 04:05:06+00');
CALL t.must_change('an admin moves an address and records the new confirmation together',
  $$UPDATE members SET email='ann.third@example.test',
     email_verified_at='2026-03-04 05:06:07+00' WHERE identity_subject='sub-adm'$$);
CALL t.must_query('and what they set in the same statement is what is there',
  $$SELECT email_verified_at::text FROM members WHERE identity_subject='sub-adm'$$,
  '2026-03-04 05:06:07+00');
RESET ROLE;
\set QUIET on
UPDATE members SET email_verified_at='2026-04-05 06:07:08+00'
  WHERE identity_subject='sub-pat';
\set QUIET off
SET ROLE oro_api;
SET LOCAL oro.identity_subject = 'sub-adm';
CALL t.must_change('an admin changes another member address',
  $$UPDATE members SET email='pat.third@example.test' WHERE identity_subject='sub-pat'$$);
CALL t.must_query('and that confirmation goes too',
  $$SELECT coalesce(email_verified_at::text,'null') FROM members WHERE identity_subject='sub-pat'$$,
  'null');
RESET ROLE;
