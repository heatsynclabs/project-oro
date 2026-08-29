-- Hand authored for tools/migration/tests/run.sh. Not part of the fixture in
-- tools/migration/fixtures/, which a replica of the legacy application wrote
-- through its own models. Nothing here came from that replica, and nothing here
-- should be read as a row the legacy system would have produced.
--
-- Why it exists. db/migrations/013_bootstrap_three_admins.sql lets three admin
-- grants be made with no approval behind them and refuses the fourth. The
-- committed fixture holds one admin, so an import of it never reaches that
-- refusal and never exercises the reason 022_roles.sql turns the role grant
-- trigger off. These four take the import to five admins, which is past the
-- quota, and the suite runs that import twice: once as it ships, where all five
-- arrive, and once with the disable stripped out of a copy of 022_roles.sql,
-- where the fourth is refused and the whole transaction rolls back.
--
-- Rule 13: every address ends in .invalid, which can never resolve. The names
-- are obviously invented. There is no password on any of them because these
-- members never sign in, and the legacy column defaults to an empty string.

INSERT INTO legacy.users (id, name, created_at, updated_at, email, admin, member_level)
VALUES
  (101, 'Second Admin', '2020-01-01 00:00:00', '2020-01-01 00:00:00',
   'admin101@fixture.invalid', true, 50),
  (102, 'Third Admin', '2020-01-02 00:00:00', '2020-01-02 00:00:00',
   'admin102@fixture.invalid', true, 50),
  (103, 'Fourth Admin', '2020-01-03 00:00:00', '2020-01-03 00:00:00',
   'admin103@fixture.invalid', true, 50),
  (104, 'Fifth Admin', '2020-01-04 00:00:00', '2020-01-04 00:00:00',
   'admin104@fixture.invalid', true, 50);
