-- The two approver rule on admin access changes.
-- Every case it must refuse, and the cases it must not.
\pset pager off
\set QUIET on
SET client_min_messages = notice;

INSERT INTO members (id,name,email) VALUES
  ('11111111-1111-1111-1111-111111111111','Alice','alice@example.test'),
  ('22222222-2222-2222-2222-222222222222','Bob','bob@example.test'),
  ('33333333-3333-3333-3333-333333333333','Carol','carol@example.test'),
  ('44444444-4444-4444-4444-444444444444','Dan','dan@example.test');
\set QUIET off

CALL t.must_pass('an ordinary role needs no approval',
  $$INSERT INTO member_roles (member_id,role_id)
    VALUES ('44444444-4444-4444-4444-444444444444','accountant')$$);

CALL t.must_pass('bootstrap: the first admin, when no approval could exist',
  $$INSERT INTO member_roles (member_id,role_id)
    VALUES ('11111111-1111-1111-1111-111111111111','admin')$$);

CALL t.must_pass('bootstrap: the second admin, the rule cannot bind at one',
  $$INSERT INTO member_roles (member_id,role_id)
    VALUES ('22222222-2222-2222-2222-222222222222','admin')$$);

CALL t.must_equal('two admins now exist', admin_count(), 2);

CALL t.must_fail('a bare admin grant, once the rule can bind',
  $$INSERT INTO member_roles (member_id,role_id)
    VALUES ('33333333-3333-3333-3333-333333333333','admin')$$,
  'needs an approval');

CALL t.must_fail('an approver who is also the proposer',
  $$INSERT INTO approvals (kind,target_member_id,role_id,proposed_by,decided_by,decided_at,status)
    VALUES ('grant_role','33333333-3333-3333-3333-333333333333','admin',
            '11111111-1111-1111-1111-111111111111',
            '11111111-1111-1111-1111-111111111111', now(), 'approved')$$,
  'approver_is_not_proposer');

CALL t.must_fail('an approval decided by somebody who is not an admin',
  $$INSERT INTO approvals (kind,target_member_id,role_id,proposed_by,decided_by,decided_at,status)
    VALUES ('grant_role','33333333-3333-3333-3333-333333333333','admin',
            '11111111-1111-1111-1111-111111111111',
            '44444444-4444-4444-4444-444444444444', now(), 'approved')$$,
  'not an admin');

CALL t.must_pass('an approval by two real admins',
  $$INSERT INTO approvals (id,kind,target_member_id,role_id,proposed_by,decided_by,decided_at,status)
    VALUES (100,'grant_role','33333333-3333-3333-3333-333333333333','admin',
            '11111111-1111-1111-1111-111111111111',
            '22222222-2222-2222-2222-222222222222', now(), 'approved')$$);

CALL t.must_pass('the grant that approval authorises',
  $$INSERT INTO member_roles (member_id,role_id,approval_id)
    VALUES ('33333333-3333-3333-3333-333333333333','admin',100)$$);

CALL t.must_fail('reusing one approval for a second grant',
  $$INSERT INTO member_roles (member_id,role_id,approval_id)
    VALUES ('44444444-4444-4444-4444-444444444444','admin',100)$$,
  'member_roles_one_grant_per_approval');

CALL t.must_pass('an approval naming Carol',
  $$INSERT INTO approvals (id,kind,target_member_id,role_id,proposed_by,decided_by,decided_at,status)
    VALUES (101,'grant_role','33333333-3333-3333-3333-333333333333','admin',
            '11111111-1111-1111-1111-111111111111',
            '22222222-2222-2222-2222-222222222222', now(), 'approved')$$);

CALL t.must_fail('using Carol''s approval to grant Dan',
  $$INSERT INTO member_roles (member_id,role_id,approval_id)
    VALUES ('44444444-4444-4444-4444-444444444444','admin',101)$$,
  'approval_authorises_this_exact_grant');

CALL t.must_pass('a pending approval exists',
  $$INSERT INTO approvals (id,kind,target_member_id,role_id,proposed_by,status)
    VALUES (102,'grant_role','44444444-4444-4444-4444-444444444444','admin',
            '11111111-1111-1111-1111-111111111111','pending')$$);

CALL t.must_fail('granting on a pending approval',
  $$INSERT INTO member_roles (member_id,role_id,approval_id)
    VALUES ('44444444-4444-4444-4444-444444444444','admin',102)$$,
  'not approved');

CALL t.must_pass('revoking an admin role',
  $$UPDATE member_roles SET revoked_at=now(), revoked_reason='rotated off ops'
     WHERE member_id='33333333-3333-3333-3333-333333333333' AND role_id='admin'$$);

CALL t.must_pass('a fresh approval for the same person',
  $$INSERT INTO approvals (id,kind,target_member_id,role_id,proposed_by,decided_by,decided_at,status)
    VALUES (103,'grant_role','33333333-3333-3333-3333-333333333333','admin',
            '11111111-1111-1111-1111-111111111111',
            '22222222-2222-2222-2222-222222222222', now(), 'approved')$$);

CALL t.must_pass('re-granting a revoked role, with no key collision',
  $$INSERT INTO member_roles (member_id,role_id,approval_id)
    VALUES ('33333333-3333-3333-3333-333333333333','admin',103)$$);

CALL t.must_equal('three live admins at the end', admin_count(), 3);
