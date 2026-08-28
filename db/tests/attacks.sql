-- The attacks a fourth audit actually carried out against this schema. Each one
-- worked once. None of them may work again.
\pset pager off
\set QUIET on
SET client_min_messages = notice;
INSERT INTO members (id,identity_subject,name,email,tier_id,standing,joined_on,
                     phone,email_visible,phone_visible,listed_in_directory) VALUES
 ('dead0000-0000-0000-0000-00000000000d','sub-alice','Alice','alice@example.test','basic','good','2020-01-01','480 555 1111',false,false,true),
 ('dead0000-0000-0000-0000-00000000000e','sub-bob','Bob','bob@example.test','basic','good','2020-01-01','480 555 2222',false,false,true),
 ('dead0000-0000-0000-0000-00000000000c','sub-mallory','Mallory','mal@example.test','basic','good','2020-01-01','480 555 3333',false,false,true);
INSERT INTO member_roles (member_id,role_id) VALUES
 ('dead0000-0000-0000-0000-00000000000d','admin'),
 ('dead0000-0000-0000-0000-00000000000e','admin');
INSERT INTO cards (member_id,tag_number,controller_slot) VALUES
 ('dead0000-0000-0000-0000-00000000000d','0000AAAA',101);
INSERT INTO payments (member_id,amount_cents,paid_on,method) VALUES
 ('dead0000-0000-0000-0000-00000000000d',5000,current_date,'zelle');
\set QUIET off

SET ROLE oro_api;

CALL t.note('one admin cannot satisfy the two approver rule alone');
SET LOCAL oro.identity_subject = 'sub-alice';
CALL t.must_fail('proposing in somebody else''s name',
  $$INSERT INTO approvals (kind,target_member_id,role_id,proposed_by)
    VALUES ('grant_role','dead0000-0000-0000-0000-00000000000c','admin',
            'dead0000-0000-0000-0000-00000000000e')$$,
  'only record yourself as the proposer');
CALL t.must_change('proposing in her own name is fine',
  $$INSERT INTO approvals (id,kind,target_member_id,role_id,proposed_by)
    VALUES (500,'grant_role','dead0000-0000-0000-0000-00000000000c','admin',
            'dead0000-0000-0000-0000-00000000000d')$$);
CALL t.must_fail('then approving it as if she were Bob',
  $$UPDATE approvals SET decided_by='dead0000-0000-0000-0000-00000000000e',
      decided_at=now(), status='approved' WHERE id=500$$,
  'only record yourself as the approver');
CALL t.must_fail('or approving her own proposal',
  $$UPDATE approvals SET decided_by='dead0000-0000-0000-0000-00000000000d',
      decided_at=now(), status='approved' WHERE id=500$$,
  'approver_is_not_proposer');

CALL t.note('a decision always carries a time, so expiry is not a no-op');
SET LOCAL oro.identity_subject = 'sub-bob';
CALL t.must_change('the second admin approves without supplying a time',
  $$UPDATE approvals SET decided_by='dead0000-0000-0000-0000-00000000000e',
      status='approved' WHERE id=500$$);
CALL t.must_query('and the time was stamped rather than left null',
  $$SELECT (decided_at IS NOT NULL)::text FROM approvals WHERE id=500$$, 'true');

CALL t.note('the bootstrap escape does not reopen by revoking admins');
CALL t.must_change('revoking Alice, leaving one admin',
  $$UPDATE member_roles SET revoked_at=now(), revoked_reason='test'
     WHERE member_id='dead0000-0000-0000-0000-00000000000d' AND role_id='admin'$$);
CALL t.must_query('only one admin remains', $$SELECT admin_count()::text$$, '1');
CALL t.must_fail('granting admin with no approval anyway',
  $$INSERT INTO member_roles (member_id,role_id)
    VALUES ('dead0000-0000-0000-0000-00000000000c','admin')$$,
  'needs an approval');

CALL t.note('a member cannot read another member''s row through any route');
SET LOCAL oro.identity_subject = 'sub-mallory';
CALL t.must_query('the base table gives her only herself',
  $$SELECT count(*) FROM members$$, '1');
CALL t.must_query('the directory hides a phone its owner hid',
  $$SELECT count(*) FROM member_directory WHERE phone IS NOT NULL$$, '0');
CALL t.must_query('and exposes no standing or paid_through at all',
  $$SELECT count(*) FROM information_schema.columns
     WHERE table_name='member_directory'
       AND column_name IN ('standing','paid_through','emergency_name','postal_code')$$, '0');
CALL t.must_query('she cannot read another member''s payment',
  $$SELECT count(*) FROM payments$$, '0');
CALL t.must_fail('nor write one, lacking the accountant role',
  $$INSERT INTO payments (member_id,amount_cents,paid_on,method)
    VALUES ('dead0000-0000-0000-0000-00000000000c',1,current_date,'cash')$$,
  'row-level security');

CALL t.note('she cannot read the door card table');
CALL t.must_fail('calling the door function directly',
  $$SELECT count(*) FROM door.active_card_table()$$, 'permission denied');

CALL t.note('attribution is stamped, not accepted from the caller');
SET LOCAL oro.identity_subject = 'sub-bob';
CALL t.must_change('an admin records a waiver, naming somebody else as the recorder',
  $$INSERT INTO waivers (member_id,signed_at,storage,reference,recorded_by)
    VALUES ('dead0000-0000-0000-0000-00000000000c',now(),'paper','x',
            'dead0000-0000-0000-0000-00000000000e')$$);
CALL t.must_query('and it is attributed to who actually did it',
  $$SELECT (recorded_by = 'dead0000-0000-0000-0000-00000000000e')::text
      FROM waivers WHERE reference='x'$$, 'true');

CALL t.note('a card cannot be repointed or brought back');
RESET ROLE;
CALL t.must_fail('moving a card to another member',
  $$UPDATE cards SET member_id='dead0000-0000-0000-0000-00000000000c'
     WHERE tag_number='0000AAAA'$$,
  'belongs to who it was issued to');
CALL t.must_fail('changing its slot',
  $$UPDATE cards SET controller_slot=102 WHERE tag_number='0000AAAA'$$,
  'EEPROM address');
CALL t.must_change('revoking it',
  $$UPDATE cards SET active=false, revoked_at=now(), revoked_reason='lost'
     WHERE tag_number='0000AAAA'$$);
CALL t.must_fail('and bringing it back',
  $$UPDATE cards SET active=true, revoked_at=NULL WHERE tag_number='0000AAAA'$$,
  'cannot be brought back');

CALL t.note('a deleted member is nobody');
CALL t.must_change('deleting Bob',
  $$UPDATE members SET deleted_at=now()
     WHERE id='dead0000-0000-0000-0000-00000000000e'$$);
CALL t.must_query('he no longer counts as an admin',
  $$SELECT is_admin('dead0000-0000-0000-0000-00000000000e')::text$$, 'false');

CALL t.note('changing a bylaws number is recorded');
CALL t.must_change('raising the tenure requirement',
  $$UPDATE governance_parameters SET value='9' WHERE key='card_access.tenure_months'$$);
CALL t.must_query('and the change is in the history',
  $$SELECT count(*) FROM governance_parameter_history
     WHERE key='card_access.tenure_months' AND new_value::text='9'$$, '1');

CALL t.note('a missing rule makes nobody eligible, rather than everybody');
DELETE FROM governance_parameters WHERE key='card_access.tenure_months';
CALL t.must_query('eligibility fails closed',
  $$SELECT eligible::text FROM card_eligibility('dead0000-0000-0000-0000-00000000000d')$$,
  'false');
