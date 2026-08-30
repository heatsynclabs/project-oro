-- Rule 10 asks the schema to document itself, so that the documentation cannot
-- be lost separately from the thing it describes. This is the gate that rule
-- names, widened from tables to columns. Tables were the half already done when
-- somebody counted, and 147 of 159 columns were the half that was missing.
--
-- A comment is prose, so rule 11 applies inside it too. The second detector
-- here reads the comments themselves for an em dash, an en dash, an emoji, or a
-- hyphen followed by a space. That last one is not a taste rule: a file path
-- wrapped across two quoted chunks lands in the database with a space inside it,
-- naming a file nobody can open, and an audit found three of those in
-- 014_column_comments.sql. Reading the comment text is not enough to catch it,
-- because the wrap happens when the text is written into the file.
--
-- Each detector is written once and asked twice: once about the real schema, and
-- once about a table made here that breaks the rule on purpose. A check that has
-- only ever been green proves nothing, so the second half is what makes the
-- first half worth reading.
\pset pager off
\set QUIET on
SET client_min_messages = notice;

CREATE FUNCTION pg_temp.relations_with_no_comment() RETURNS text
LANGUAGE sql STABLE AS $fn$
  SELECT coalesce(string_agg(c.relname, ', ' ORDER BY c.relname), 'none')
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public'
     AND c.relkind IN ('r','v','m','p')
     AND coalesce(btrim(obj_description(c.oid, 'pg_class')), '') = ''
$fn$;

CREATE FUNCTION pg_temp.columns_with_no_comment() RETURNS text
LANGUAGE sql STABLE AS $fn$
  SELECT coalesce(string_agg(c.relname || '.' || a.attname, ', '
                             ORDER BY c.relname, a.attnum), 'none')
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
                       AND a.attnum > 0 AND NOT a.attisdropped
   WHERE n.nspname = 'public'
     AND c.relkind IN ('r','v','m','p')
     AND coalesce(btrim(col_description(c.oid, a.attnum)), '') = ''
$fn$;
CREATE FUNCTION pg_temp.comments_carrying_a_banned_dash() RETURNS text
LANGUAGE sql STABLE AS $fn$
  SELECT coalesce(string_agg(c.relname || '.' || a.attname, ', '
                             ORDER BY c.relname, a.attnum), 'none')
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
                       AND a.attnum > 0 AND NOT a.attisdropped
   WHERE n.nspname = 'public'
     AND col_description(c.oid, a.attnum) ~ '[[:alnum:]]- [[:alnum:]]|[^[:ascii:]]'
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

CALL t.note('the same detector, against a table nobody documented');
\set QUIET on
-- Created in public rather than as a temporary table, because that is where the
-- detector looks and a temporary one would sit in a schema it never reads. The
-- transaction this file runs in rolls back, so it leaves nothing behind.
CREATE TABLE a_table_nobody_documented (
  said_nothing            text,
  said_nothing_at_length  text
);
-- Spaces rather than no comment at all, because a comment of nothing is the
-- shape somebody reaches for to clear a red build.
COMMENT ON COLUMN a_table_nobody_documented.said_nothing_at_length IS '   ';
\set QUIET off

CALL t.must_query('a table with nothing said about it is named',
  $$SELECT pg_temp.relations_with_no_comment()$$, 'a_table_nobody_documented');
CALL t.must_query('an empty comment and a missing one are both named',
  $$SELECT pg_temp.columns_with_no_comment()$$,
  'a_table_nobody_documented.said_nothing, a_table_nobody_documented.said_nothing_at_length');

CALL t.note('and writing the comments clears it, so the check is not stuck red');
\set QUIET on
COMMENT ON TABLE a_table_nobody_documented IS
  'Made and dropped inside this test, so that the check above is watched failing.';
COMMENT ON COLUMN a_table_nobody_documented.said_nothing IS
  'Stands in for a column somebody added and said nothing about.';
COMMENT ON COLUMN a_table_nobody_documented.said_nothing_at_length IS
  'Stands in for a comment made of spaces, which the detector counts as none.';
\set QUIET off

CALL t.must_query('the table list is clean once the table is described',
  $$SELECT pg_temp.relations_with_no_comment()$$, 'none');
CALL t.must_query('the column list is clean once both columns are described',
  $$SELECT pg_temp.columns_with_no_comment()$$, 'none');

CALL t.note('the dash detector, against a comment written to break the rule');
\set QUIET on
-- Assembled with chr() rather than typed, because typing either character here
-- would put it in a file the prose gate reads and this test would be the thing
-- it caught. The first is an em dash. The second is a hyphen followed by a
-- space, which is how a wrapped file path lands in a comment: an audit found
-- exactly that in 014_column_comments.sql, where the concatenation of two
-- quoted chunks left docs/api/contract-review- notes.md in the database.
DO $do$ BEGIN
  EXECUTE format('COMMENT ON COLUMN a_table_nobody_documented.said_nothing IS %L',
    'A sentence broken by a dash ' || chr(8212) || ' the way rule 11 bans.');
  EXECUTE format('COMMENT ON COLUMN a_table_nobody_documented.said_nothing_at_length IS %L',
    'A path split by a wrap, docs/api/contract' || chr(45) || 'review' || chr(45) || ' notes.md.');
END $do$;
\set QUIET off

CALL t.must_query('an em dash and a wrapped path are both named',
  $$SELECT pg_temp.comments_carrying_a_banned_dash()$$,
  'a_table_nobody_documented.said_nothing, a_table_nobody_documented.said_nothing_at_length');

\set QUIET on
DROP TABLE a_table_nobody_documented;
\set QUIET off
