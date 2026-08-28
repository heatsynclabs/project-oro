-- Row level security. A policy without a refusal test is untested, because a
-- policy that returns everything passes every positive test.
\pset pager off
\set QUIET on
SET client_min_messages = notice;

INSERT INTO members (id,identity_subject,name,email,phone) VALUES
 ('cccccccc-0000-0000-0000-000000000001','sub-mia','Mia','mia@example.test','480 555 0101'),
 ('cccccccc-0000-0000-0000-000000000002','sub-noor','Noor','noor@example.test','480 555 0102'),
 ('cccccccc-0000-0000-0000-000000000003','sub-ada','Ada the admin','ada@example.test','480 555 0103');
INSERT INTO member_roles (member_id,role_id) VALUES
 ('cccccccc-0000-0000-0000-000000000003','admin');
INSERT INTO cards (member_id,tag_number,controller_slot) VALUES
 ('cccccccc-0000-0000-0000-000000000001','0000C0DE',60),
 ('cccccccc-0000-0000-0000-000000000002','0000C0DF',61);
INSERT INTO door_events (occurred_at,source,event_key,member_id,dedupe_key) VALUES
 (now(),'controller','G','cccccccc-0000-0000-0000-000000000001','ev-mia-1'),
 (now(),'controller','G','cccccccc-0000-0000-0000-000000000002','ev-noor-1');
INSERT INTO waivers (member_id,signed_name,signed_email,signed_at,document_version,document_sha256) VALUES
 ('cccccccc-0000-0000-0000-000000000001','Mia','mia@example.test',now(),'v1','abc'),
 ('cccccccc-0000-0000-0000-000000000002','Noor','noor@example.test',now(),'v1','def');
INSERT INTO certifications (id,name) VALUES ('laser','Laser cutter');
INSERT INTO member_certifications (member_id,certification_id) VALUES
 ('cccccccc-0000-0000-0000-000000000001','laser');
\set QUIET off

CALL t.note('anonymous: no identity set at all');
SET ROLE oro_api;

CALL t.must_fail('reading members with no identity raises rather than returning nothing',
  'SELECT count(*) FROM members', 'No identity set');
CALL t.must_fail('reading cards with no identity raises',
  'SELECT count(*) FROM cards', 'No identity set');
CALL t.must_fail('reading door events with no identity raises',
  'SELECT count(*) FROM door_events', 'No identity set');

CALL t.note('an identity that matches no member: null, not an error');
SET LOCAL oro.identity_subject = 'sub-nobody';
CALL t.must_query('an unknown subject sees no cards',
  'SELECT count(*) FROM cards', '0');
CALL t.must_query('an unknown subject sees no door events',
  'SELECT count(*) FROM door_events', '0');

CALL t.note('Mia, an ordinary member');
SET LOCAL oro.identity_subject = 'sub-mia';
CALL t.must_query('sees her own card', 'SELECT count(*) FROM cards', '1');
CALL t.must_query('and it is hers',
  $$SELECT tag_number FROM cards$$, '0000C0DE');
CALL t.must_query('sees her own door events', 'SELECT count(*) FROM door_events', '1');
CALL t.must_query('sees her own waiver', 'SELECT count(*) FROM waivers', '1');
CALL t.must_query('sees her own certification',
  'SELECT count(*) FROM member_certifications', '1');

CALL t.note('Noor, who holds nothing of Mia''s');
SET LOCAL oro.identity_subject = 'sub-noor';
CALL t.must_query('cannot see Mia''s card',
  $$SELECT count(*) FROM cards WHERE tag_number='0000C0DE'$$, '0');
CALL t.must_query('cannot see Mia''s door events',
  $$SELECT count(*) FROM door_events WHERE dedupe_key='ev-mia-1'$$, '0');
CALL t.must_query('cannot see Mia''s waiver',
  $$SELECT count(*) FROM waivers WHERE signed_name='Mia'$$, '0');
CALL t.must_query('cannot see Mia''s certification',
  'SELECT count(*) FROM member_certifications', '0');

CALL t.note('Ada, an admin');
SET LOCAL oro.identity_subject = 'sub-ada';
CALL t.must_query('sees every card', 'SELECT count(*) FROM cards', '2');
CALL t.must_query('sees every door event', 'SELECT count(*) FROM door_events', '2');
CALL t.must_query('sees every waiver', 'SELECT count(*) FROM waivers', '2');
CALL t.must_query('sees every member', 'SELECT count(*) FROM members', '3');

CALL t.note('the door path, which must not depend on any of this');
RESET ROLE;
CALL t.must_query('reads the full active card table with no identity set',
  'SELECT count(*) FROM door.active_card_table()', '2');

CALL t.note('the audit trail resists the application role');
SET ROLE oro_api;
SET LOCAL oro.identity_subject = 'sub-ada';
CALL t.must_fail('the app role cannot rewrite a door event',
  $$UPDATE door_events SET member_id=NULL WHERE dedupe_key='ev-mia-1'$$,
  'permission denied');
CALL t.must_fail('the app role cannot delete a door event',
  $$DELETE FROM door_events WHERE dedupe_key='ev-mia-1'$$, 'permission denied');
CALL t.must_fail('the app role cannot edit governance history',
  $$UPDATE governance_parameter_history SET new_value='"x"'$$,
  'permission denied');
RESET ROLE;

CALL t.note('and the trigger is the second layer, for anyone who does hold the grant');
CALL t.must_fail('even the owner cannot rewrite a door event',
  $$UPDATE door_events SET member_id=NULL WHERE dedupe_key='ev-mia-1'$$,
  'append only');
CALL t.must_fail('even the owner cannot delete a door event',
  $$DELETE FROM door_events WHERE dedupe_key='ev-mia-1'$$, 'append only');

CALL t.note('a recorded decision stays recorded');
INSERT INTO approvals (id,kind,target_member_id,role_id,proposed_by,decided_by,decided_at,status)
  VALUES (900,'grant_role','cccccccc-0000-0000-0000-000000000001','admin',
          'cccccccc-0000-0000-0000-000000000003',
          'cccccccc-0000-0000-0000-000000000002', now(), 'approved');

CALL t.must_fail('repointing an approved approval at a different member',
  $$UPDATE approvals SET target_member_id='cccccccc-0000-0000-0000-000000000002'
     WHERE id=900$$,
  'cannot be changed after it is created');
CALL t.must_fail('repointing an approved approval at a different role',
  $$UPDATE approvals SET role_id='accountant' WHERE id=900$$,
  'cannot be changed after it is created');
CALL t.must_fail('reversing a decision',
  $$UPDATE approvals SET status='rejected' WHERE id=900$$, 'A decision is final');

CALL t.must_pass('granting on that approval',
  $$INSERT INTO member_roles (member_id,role_id,approval_id)
    VALUES ('cccccccc-0000-0000-0000-000000000001','admin',900)$$);
CALL t.must_fail('moving a grant to another member after the fact',
  $$UPDATE member_roles SET member_id='cccccccc-0000-0000-0000-000000000002'
     WHERE approval_id=900$$,
  'historical record');
CALL t.must_pass('revoking it, which is a legitimate update',
  $$UPDATE member_roles SET revoked_at=now(), revoked_reason='left the board'
     WHERE approval_id=900$$);
CALL t.must_fail('un-revoking by clearing the field',
  $$UPDATE member_roles SET revoked_at=NULL WHERE approval_id=900$$,
  'cannot be undone');
