-- The bylaws card access process. Numbers come from governance_parameters.
\pset pager off
\set QUIET on
SET client_min_messages = notice;
INSERT INTO members (id,name,email) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001','Nominee','nominee@example.test'),
  ('aaaaaaaa-0000-0000-0000-000000000002','Nominator','nominator@example.test');
\set QUIET off

CALL t.must_fail('nominating yourself',
  $$INSERT INTO card_proposals (nominee_id,nominator_id)
    VALUES ('aaaaaaaa-0000-0000-0000-000000000001',
            'aaaaaaaa-0000-0000-0000-000000000001')$$,
  'nominator_is_not_nominee');

CALL t.must_pass('a draft proposal',
  $$INSERT INTO card_proposals (nominee_id,nominator_id)
    VALUES ('aaaaaaaa-0000-0000-0000-000000000001',
            'aaaaaaaa-0000-0000-0000-000000000002')$$);

CALL t.must_fail('approving with four card members present, quorum is five',
  $$INSERT INTO card_proposals (nominee_id,nominator_id,posted_at,meeting_date,
      cardholders_present,votes_for,votes_against,status)
    VALUES ('aaaaaaaa-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000002',
            now()-interval '20 days',(now()-interval '1 day')::date,4,3,1,'approved')$$,
  'require 5 card members');

CALL t.must_fail('approving with the attendance left null',
  $$INSERT INTO card_proposals (nominee_id,nominator_id,posted_at,meeting_date,
      cardholders_present,votes_for,votes_against,status)
    VALUES ('aaaaaaaa-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000002',
            now()-interval '20 days',(now()-interval '1 day')::date,NULL,3,1,'approved')$$,
  'require 5 card members');

CALL t.must_fail('approving three days after posting, notice is fourteen',
  $$INSERT INTO card_proposals (nominee_id,nominator_id,posted_at,meeting_date,
      cardholders_present,votes_for,votes_against,status)
    VALUES ('aaaaaaaa-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000002',
            now()-interval '3 days',now()::date,7,6,1,'approved')$$,
  '14 days notice');

CALL t.must_fail('approving on a tied vote',
  $$INSERT INTO card_proposals (nominee_id,nominator_id,posted_at,meeting_date,
      cardholders_present,votes_for,votes_against,status)
    VALUES ('aaaaaaaa-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000002',
            now()-interval '20 days',(now()-interval '1 day')::date,8,4,4,'approved')$$,
  'simple majority');

CALL t.must_fail('recording more votes than people present',
  $$INSERT INTO card_proposals (nominee_id,nominator_id,posted_at,meeting_date,
      cardholders_present,votes_for,votes_against,status)
    VALUES ('aaaaaaaa-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000002',
            now()-interval '20 days',(now()-interval '1 day')::date,5,4,3,'approved')$$,
  'More votes');

CALL t.must_pass('a proposal that meets every bylaws requirement',
  $$INSERT INTO card_proposals (nominee_id,nominator_id,posted_at,meeting_date,
      cardholders_present,votes_for,votes_against,status)
    VALUES ('aaaaaaaa-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000002',
            now()-interval '20 days',(now()-interval '1 day')::date,7,6,1,'approved')$$);

CALL t.note('amending the bylaws is editing a row, not writing a migration');
UPDATE governance_parameters SET value='8' WHERE key='card_access.quorum';

CALL t.must_fail('seven present, after quorum is raised to eight',
  $$INSERT INTO card_proposals (nominee_id,nominator_id,posted_at,meeting_date,
      cardholders_present,votes_for,votes_against,status)
    VALUES ('aaaaaaaa-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000002',
            now()-interval '20 days',(now()-interval '1 day')::date,7,6,1,'approved')$$,
  'require 8 card members');
