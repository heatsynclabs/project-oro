-- Rule 10 asks the schema to document itself, so that the documentation cannot
-- be lost separately from the thing it describes. This is the gate that rule
-- names, widened from tables to columns. Tables were the half already done when
-- somebody counted, and 147 of 159 columns were the half that was missing.
--
-- Every detector below reads table comments and column comments through one
-- source, pg_temp.every_documented_thing(). An earlier version of the dash
-- detector called col_description alone while its label promised it read every
-- comment, so an em dash and an emoji planted in a table comment both went past
-- it green. Rule 11 calls the emoji case a correctness rule.
--
-- A comment is prose, so rule 11 applies inside it too. The dash detector reads
-- for any character outside ASCII, which takes the em dash, the en dash and the
-- emoji together, and for the two substitutes rule 11 names in the same breath:
-- a hyphen with a space either side, and two hyphens. Last, it reads for a
-- hyphen left in front of whitespace. That one is not a taste rule. A file path
-- wrapped across two quoted chunks lands in the database with a space inside it,
-- naming a file nobody can open, and an audit found three of those in
-- 014_column_comments.sql. Reading the comment text is not enough to catch it,
-- because the wrap happens when the text is written into the file.
--
-- Three further detectors ask whether a comment still reads as a sentence. They
-- look for the damage that has already happened here and for nothing else:
-- quoting that leaked out of the migration into the rendered text, one sentence
-- written twice inside a single comment, and a full stop spliced onto a comma.
-- A gate that judges prose quality gets switched off within a week, so these
-- judge nothing. Each names a shape a reader can look at and agree is broken.
--
-- Each detector is written once and asked twice: once about the real schema, and
-- once about a table made here that breaks the rule on purpose. A check that has
-- only ever been green proves nothing, so the second half is what makes the
-- first half worth reading. The second ask passes the scratch table's name, so a
-- control keeps meaning what it says on the day the real schema goes wrong.
\pset pager off
\set QUIET on
SET client_min_messages = notice;

CREATE FUNCTION pg_temp.every_documented_thing()
RETURNS TABLE (kind text, what text, body text)
LANGUAGE sql STABLE AS $fn$
  SELECT 'relation'::text, c.relname::text, obj_description(c.oid, 'pg_class')
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public'
     AND c.relkind IN ('r','v','m','p')
  UNION ALL
  SELECT 'column'::text, c.relname || '.' || a.attname,
         col_description(c.oid, a.attnum)
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
                       AND a.attnum > 0 AND NOT a.attisdropped
   WHERE n.nspname = 'public'
     AND c.relkind IN ('r','v','m','p')
$fn$;

-- btrim with one argument strips spaces and nothing else, so a comment of a
-- single tab or a single newline used to read as documentation here.
CREATE FUNCTION pg_temp.says_nothing(body text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $fn$
  SELECT regexp_replace(coalesce(body, ''), '[[:space:]]', '', 'g') = ''
$fn$;

-- COLLATE "C" so the list reads in the same order on a laptop and on the runner,
-- which sort punctuation differently under their own collations.
CREATE FUNCTION pg_temp.relations_with_no_comment(only_within text DEFAULT '')
RETURNS text LANGUAGE sql STABLE AS $fn$
  SELECT coalesce(string_agg(what, ', ' ORDER BY what COLLATE "C"), 'none')
    FROM pg_temp.every_documented_thing()
   WHERE kind = 'relation'
     AND starts_with(what, only_within)
     AND pg_temp.says_nothing(body)
$fn$;

CREATE FUNCTION pg_temp.columns_with_no_comment(only_within text DEFAULT '')
RETURNS text LANGUAGE sql STABLE AS $fn$
  SELECT coalesce(string_agg(what, ', ' ORDER BY what COLLATE "C"), 'none')
    FROM pg_temp.every_documented_thing()
   WHERE kind = 'column'
     AND starts_with(what, only_within)
     AND pg_temp.says_nothing(body)
$fn$;

CREATE FUNCTION pg_temp.comments_carrying_a_banned_dash(only_within text DEFAULT '')
RETURNS text LANGUAGE sql STABLE AS $fn$
  SELECT coalesce(string_agg(what, ', ' ORDER BY what COLLATE "C"), 'none')
    FROM pg_temp.every_documented_thing()
   WHERE starts_with(what, only_within)
     AND body ~ '[[:alnum:]]-[[:space:]]|[[:space:]]-[[:space:]]|--|[^[:ascii:]]'
$fn$;

-- Read against the rendered text and not the migration source, because that is
-- what \d+ prints to whoever is reading the schema at 2am. An apostrophe inside
-- a word is ordinary English and comes out before the test, so member's does not
-- trip it and a quote standing on its own does. chr(39) rather than a typed
-- quote: four in a row is a puzzle at that hour.
CREATE FUNCTION pg_temp.comments_with_leaked_quoting(only_within text DEFAULT '')
RETURNS text LANGUAGE sql STABLE AS $fn$
  SELECT coalesce(string_agg(what, ', ' ORDER BY what COLLATE "C"), 'none')
    FROM pg_temp.every_documented_thing()
   WHERE starts_with(what, only_within)
     AND strpos(regexp_replace(body,
                  '([[:alnum:]])' || chr(39) || '([[:alnum:]])', '\1\2', 'g'),
                chr(39)) > 0
$fn$;

-- The trailing full stop comes off before the comparison. A sentence repeated at
-- the end of a comment keeps its stop and the copy in the middle loses it to the
-- split, and without the trim those two read as different sentences.
CREATE FUNCTION pg_temp.comments_saying_it_twice(only_within text DEFAULT '')
RETURNS text LANGUAGE sql STABLE AS $fn$
  SELECT coalesce(string_agg(thing.what, ', ' ORDER BY thing.what COLLATE "C"), 'none')
    FROM pg_temp.every_documented_thing() thing
   WHERE starts_with(thing.what, only_within)
     AND EXISTS (
           SELECT 1
             FROM regexp_split_to_table(thing.body, '\.[[:space:]]+') AS sentence
            GROUP BY btrim(sentence, E' \t\r\n.')
           HAVING count(*) > 1
              AND btrim(sentence, E' \t\r\n.') <> ''
         )
$fn$;

CREATE FUNCTION pg_temp.comments_with_a_stop_then_a_comma(only_within text DEFAULT '')
RETURNS text LANGUAGE sql STABLE AS $fn$
  SELECT coalesce(string_agg(what, ', ' ORDER BY what COLLATE "C"), 'none')
    FROM pg_temp.every_documented_thing()
   WHERE starts_with(what, only_within)
     AND strpos(body, '.,') > 0
$fn$;
\set QUIET off

CALL t.note('rule 10: the schema documents itself');
CALL t.must_query('every table and view carries a comment',
  $$SELECT pg_temp.relations_with_no_comment()$$, 'none');
CALL t.must_query('every column of every table and view carries a comment',
  $$SELECT pg_temp.columns_with_no_comment()$$, 'none');

CALL t.note('and rule 11 holds inside them, because they are prose too');
CALL t.must_query('no comment carries a dash rule 11 bans',
  $$SELECT pg_temp.comments_carrying_a_banned_dash()$$, 'none');

CALL t.note('and every comment still reads as the sentence somebody wrote');
CALL t.must_query('no comment carries quoting that leaked out of the migration',
  $$SELECT pg_temp.comments_with_leaked_quoting()$$, 'none');
CALL t.must_query('no comment says the same sentence twice',
  $$SELECT pg_temp.comments_saying_it_twice()$$, 'none');
CALL t.must_query('no comment splices a full stop onto a comma',
  $$SELECT pg_temp.comments_with_a_stop_then_a_comma()$$, 'none');

CALL t.note('the same detectors, against a table nobody documented');
\set QUIET on
-- Created in public rather than as a temporary table, because that is where the
-- detectors look and a temporary one would sit in a schema they never read. The
-- transaction this file runs in rolls back, so it leaves nothing behind.
CREATE TABLE a_table_nobody_documented (
  said_nothing             text,
  said_nothing_at_length   text,
  said_nothing_with_a_tab  text
);
-- Whitespace rather than no comment at all, because a comment of nothing is the
-- shape somebody reaches for to clear a red build. The tab is assembled with
-- chr() so that it survives an editor that trims the file.
COMMENT ON COLUMN a_table_nobody_documented.said_nothing_at_length IS '   ';
DO $do$ BEGIN
  EXECUTE format('COMMENT ON COLUMN a_table_nobody_documented.said_nothing_with_a_tab IS %L',
    chr(9));
END $do$;
\set QUIET off

CALL t.must_query('a table with nothing said about it is named',
  $$SELECT pg_temp.relations_with_no_comment('a_table_nobody_documented')$$,
  'a_table_nobody_documented');
CALL t.must_query('spaces, a tab, and no comment at all are all named',
  $$SELECT pg_temp.columns_with_no_comment('a_table_nobody_documented')$$,
  'a_table_nobody_documented.said_nothing, a_table_nobody_documented.said_nothing_at_length, a_table_nobody_documented.said_nothing_with_a_tab');

CALL t.note('and writing the comments clears it, so the check is not stuck red');
\set QUIET on
COMMENT ON TABLE a_table_nobody_documented IS
  'Made and dropped inside this test, so that the checks above are watched failing.';
COMMENT ON COLUMN a_table_nobody_documented.said_nothing IS
  'Stands in for a column somebody added and said nothing about.';
COMMENT ON COLUMN a_table_nobody_documented.said_nothing_at_length IS
  'Stands in for a comment made of spaces, which the detector counts as none.';
COMMENT ON COLUMN a_table_nobody_documented.said_nothing_with_a_tab IS
  'Stands in for a comment made of one tab, which the detector counted as prose.';
\set QUIET off

CALL t.must_query('the table list is clean once the table is described',
  $$SELECT pg_temp.relations_with_no_comment()$$, 'none');
CALL t.must_query('the column list is clean once every column is described',
  $$SELECT pg_temp.columns_with_no_comment()$$, 'none');

CALL t.note('the dash detector, against comments written to break the rule');
\set QUIET on
-- Assembled with chr() rather than typed, because typing any of these here would
-- put them in a file the prose gate reads and this test would be the thing it
-- caught. chr(8212) is an em dash and chr(128512) is an emoji. chr(45) is a
-- plain hyphen, and the second column shows how a wrapped file path lands in a
-- comment: an audit found exactly that in 014_column_comments.sql, where the
-- concatenation of two quoted chunks left docs/api/contract-review- notes.md in
-- the database. The table comment carries the emoji because the detector used to
-- read column comments only and said none.
DO $do$ BEGIN
  EXECUTE format('COMMENT ON TABLE a_table_nobody_documented IS %L',
    'A table comment nobody read, carrying an emoji ' || chr(128512) || '.');
  EXECUTE format('COMMENT ON COLUMN a_table_nobody_documented.said_nothing IS %L',
    'A sentence broken by a dash ' || chr(8212) || ' the way rule 11 bans.');
  EXECUTE format('COMMENT ON COLUMN a_table_nobody_documented.said_nothing_at_length IS %L',
    'A path split by a wrap, docs/api/contract' || chr(45) || 'review' || chr(45) || ' notes.md.');
END $do$;
\set QUIET off

CALL t.must_query('an emoji in a table comment is named, and so are an em dash and a wrapped path',
  $$SELECT pg_temp.comments_carrying_a_banned_dash('a_table_nobody_documented')$$,
  'a_table_nobody_documented, a_table_nobody_documented.said_nothing, a_table_nobody_documented.said_nothing_at_length');

CALL t.note('and the two substitutes rule 11 names, which used to walk through');
\set QUIET on
-- The shapes rule 11 calls the same tell wearing a hat. Both passed the old
-- regex, which asked for an alphanumeric immediately before the hyphen.
DO $do$ BEGIN
  EXECUTE format('COMMENT ON TABLE a_table_nobody_documented IS %L',
    'A table comment with nothing wrong in it.');
  EXECUTE format('COMMENT ON COLUMN a_table_nobody_documented.said_nothing IS %L',
    'A clause ' || chr(45) || ' set off with a spaced hyphen.');
  EXECUTE format('COMMENT ON COLUMN a_table_nobody_documented.said_nothing_at_length IS %L',
    'A clause ' || chr(45) || chr(45) || ' set off with two hyphens.');
END $do$;
\set QUIET off

CALL t.must_query('a spaced hyphen and a double hyphen are both named',
  $$SELECT pg_temp.comments_carrying_a_banned_dash('a_table_nobody_documented')$$,
  'a_table_nobody_documented.said_nothing, a_table_nobody_documented.said_nothing_at_length');

CALL t.note('and the three shapes of garble that reached the database once already');
\set QUIET on
-- Each column carries one shape and only that shape, so a detector that fires on
-- the wrong one says so by naming a column its author did not write it for.
DO $do$ BEGIN
  EXECUTE format('COMMENT ON COLUMN a_table_nobody_documented.said_nothing IS %L',
    'Quoting that leaked out of the migration file, ' || chr(39) ||
    ' left standing in the rendered text.');
END $do$;
COMMENT ON COLUMN a_table_nobody_documented.said_nothing_at_length IS
  'The holder reads it and cannot edit it. The holder reads it and cannot edit it.';
COMMENT ON COLUMN a_table_nobody_documented.said_nothing_with_a_tab IS
  'Two absences to know about. The first is given., and the second arrives spliced on.';
\set QUIET off

CALL t.must_query('a leaked quote is named, and the two other garbled columns are not',
  $$SELECT pg_temp.comments_with_leaked_quoting('a_table_nobody_documented')$$,
  'a_table_nobody_documented.said_nothing');
CALL t.must_query('a sentence written twice is named on its own',
  $$SELECT pg_temp.comments_saying_it_twice('a_table_nobody_documented')$$,
  'a_table_nobody_documented.said_nothing_at_length');
CALL t.must_query('a full stop spliced onto a comma is named on its own',
  $$SELECT pg_temp.comments_with_a_stop_then_a_comma('a_table_nobody_documented')$$,
  'a_table_nobody_documented.said_nothing_with_a_tab');

\set QUIET on
DROP TABLE a_table_nobody_documented;
\set QUIET off
