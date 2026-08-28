-- A waiver is a reference to a document held somewhere else, not a copy of it.
\pset pager off
\set QUIET on
SET client_min_messages = notice;
INSERT INTO members (id,identity_subject,name,email) VALUES
 ('eeeeeeee-0000-0000-0000-000000000001','sub-sofia','Signed Sofia','sofia@example.test'),
 ('eeeeeeee-0000-0000-0000-000000000002','sub-uma','Unsigned Uma','uma@example.test');
\set QUIET off

CALL t.must_pass('recording that a member signed, and where it is kept',
  $$INSERT INTO waivers (member_id,signed_at,storage,reference)
    VALUES ('eeeeeeee-0000-0000-0000-000000000001', now(),
            'google-form','1FAIpQLSc-response-8814')$$);

CALL t.must_fail('recording one without saying where the document is',
  $$INSERT INTO waivers (member_id,signed_at,storage)
    VALUES ('eeeeeeee-0000-0000-0000-000000000002', now(), NULL)$$,
  'null value');

CALL t.note('the table holds no personal information at all');
CALL t.must_query('no column mentions a name, address, signature or guardian',
  $$SELECT count(*) FROM information_schema.columns
     WHERE table_name='waivers'
       AND column_name ~ 'name|address|phone|guardian|signature|minor|email'$$, '0');

CALL t.note('what a host or instructor gets to see');
SET ROLE oro_api;
SET LOCAL oro.identity_subject = 'sub-sofia';
CALL t.must_query('a member who signed shows valid',
  $$SELECT has_valid_waiver::text
      FROM waiver_status('eeeeeeee-0000-0000-0000-000000000001')$$, 'true');
SET LOCAL oro.identity_subject = 'sub-uma';
CALL t.must_query('a member who never signed has no row at all, asking about themselves',
  $$SELECT count(*) FROM waiver_status('eeeeeeee-0000-0000-0000-000000000002')$$, '0');
SET LOCAL oro.identity_subject = 'sub-sofia';

RESET ROLE;
CALL t.note('an expired waiver stops counting');
CALL t.must_pass('recording one that has lapsed',
  $$INSERT INTO waivers (member_id,signed_at,expires_at,storage,reference)
    VALUES ('eeeeeeee-0000-0000-0000-000000000002', now() - interval '2 years',
            now() - interval '1 year','paper-file','drawer B')$$);
SET LOCAL oro.identity_subject = 'sub-sofia';
CALL t.must_fail('a member cannot check somebody else without a role',
  $$SELECT has_valid_waiver FROM waiver_status('eeeeeeee-0000-0000-0000-000000000002')$$,
  'hosting or instructing role');
RESET ROLE;
CALL t.must_query('and the expired one does not count as valid',
  $$SELECT bool_or(expires_at IS NULL OR expires_at > now())::text FROM waivers
     WHERE member_id='eeeeeeee-0000-0000-0000-000000000002'$$, 'false');
