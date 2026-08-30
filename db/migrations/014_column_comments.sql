-- The column comments rule 10 asks for, all 147 of them.
--
-- 006_policies_and_comments.sql wrote the table comments and said why: a table
-- without a comment is a table whose meaning lives only in somebody's memory.
-- It left the columns. Measured on 2026-08-29 against a database built from
-- these migrations and this seed, every one of the 17 relations carried a
-- comment and 12 of their 159 columns did.
--
-- Each comment below is meant to say something the column name and the type do
-- not already say. A column the legacy import fills names where its value comes
-- from. A column a policy or a trigger reads names the file that reads it. Two
-- columns turned out to be read by nothing at all, and they say so, because a
-- reader deserves to know that before building on one.
--
-- One rule worth knowing before adding a comment here: no standalone quote
-- character. An apostrophe inside a word is fine and a quoted SQL literal is
-- not, so this file says at time zone UTC rather than quoting it. The gate
-- refuses the second shape, because that is what leaked SQL string syntax looks
-- like and no rule that has to tell the two apart survives contact with 2am.
--
-- db/tests/comments.sql is the gate. It asks a database built from nothing for
-- any table or column carrying no comment, and then asks the same question
-- about a table it makes with nothing said about it, because a check that has
-- only ever been green proves nothing.

BEGIN;

-- --------------------------------------------------------- The member record

COMMENT ON COLUMN members.id IS
  'A fresh uuid from gen_random_uuid, never the legacy users.id, which is '
  'kept in legacy_id instead. current_member_id, defined in '
  'db/migrations/004_security.sql and narrowed in 012_close_remaining.sql, '
  'resolves the identity on the transaction to this value, so every policy '
  'that turns on who is asking compares against it. A real DELETE is '
  'usually refused rather than cascaded: approvals.target_member_id, '
  'payments.member_id and members.oriented_by all reference this column '
  'with no ON DELETE action. Where nothing blocks it, waivers, '
  'certifications, instructor rows and role grants go by cascade. A member '
  'who holds a card, or who is named on a door event, cannot be deleted at '
  'all: both references are ON DELETE SET NULL, the SET NULL is an UPDATE, '
  'and freeze_card_history in db/migrations/012_close_remaining.sql and '
  'door_events_are_append_only in db/migrations/005_immutability.sql each '
  'raise on it, so the delete is refused rather than leaving a card behind '
  'with nobody on it. Removing somebody is a deleted_at timestamp instead.';

COMMENT ON COLUMN members.email IS
  'citext and unique, so two addresses differing only in case collide. That '
  'is what tools/migration/010_preflight.sql refuses to start over, along '
  'with blanks, because citext UNIQUE treats two empty strings as a '
  'collision and null as absent. Nothing keys authorisation on this column. '
  'Policies read identity_subject, since Devise :confirmable was never '
  'enabled in the legacy application and no address there was ever proven '
  'to belong to anybody. The one thing that matches on it is '
  'link_or_create_member in db/migrations/008_system_paths.sql, at first '
  'sign in, to claim a member row an admin created earlier, and 012 taught '
  'it to refuse a row that already holds a live role.';

COMMENT ON COLUMN members.email_verified_at IS
  'When the lab last confirmed it can reach this address. Nothing in this '
  'project ever writes a date into it. tools/migration/020_migrate.sql does '
  'not name the column and link_or_create_member inserts only the subject, '
  'the address and a name, so a carried over member and a first sign in '
  'both land here null. The single writer is enforce_profile_self_edit in '
  'db/migrations/004_security.sql, and all it does is clear the column when '
  'a member changes their own email. The same trigger refuses a member '
  'marking their own address verified. Null gates nothing anywhere in this '
  'schema, and the isVerified flag in tools/bootstrap/identity_accounts.py '
  'belongs to the identity service rather than to this column.';

COMMENT ON COLUMN members.name IS
  'The only column on this table that is NOT NULL with no default, which is '
  'why tools/migration/010_preflight.sql refuses to start while any legacy '
  'user carries a blank one. link_or_create_member falls back to the email '
  'address when a first sign in arrives with no name, so a row always has '
  'something to call the person by. Where a member set a display_name, '
  'member_directory shows that instead and returns it under this key.';

COMMENT ON COLUMN members.display_name IS
  'What the member wants shown in place of their name. The legacy users '
  'table has no such column, so every migrated row has this null. '
  'member_directory in db/migrations/011_close_read_holes.sql coalesces it '
  'over name and publishes one key rather than both, so the directory shows '
  'the name a member goes by and never the one the lab has on file beside '
  'it.';

COMMENT ON COLUMN members.pronouns IS
  'Free text, never a list to choose from. member_directory publishes it to '
  'any signed in member for every listed member, with no visibility flag '
  'over it, unlike email and phone. A member who does not want it shown '
  'leaves it empty. No legacy column feeds it, so every migrated row starts '
  'null.';

COMMENT ON COLUMN members.phone IS
  'No format is enforced. The legacy column is free text and holds whatever '
  'people typed, and normalising it on import would rewrite data nobody has '
  'checked against the person it belongs to. member_directory publishes '
  'this only where phone_visible is true, and after '
  'db/migrations/011_close_read_holes.sql dropped member_reads_directory '
  'the only SELECT policies left on this table are member_reads_self and '
  'admin_reads_all, so the view is the only route to another member''s '
  'number for anybody who is not an admin.';

COMMENT ON COLUMN members.postal_code IS
  'Published nowhere: member_directory does not select it, so through the '
  'API the member themselves and an admin are the only readers. Every '
  'member could read it on every listed member until '
  'db/migrations/011_close_read_holes.sql dropped the '
  'member_reads_directory policy, which sat on the base table where row '
  'level security cannot hide a column.';

COMMENT ON COLUMN members.tier_id IS
  'The tier the member declared for themselves. enforce_profile_self_edit '
  'in db/migrations/004_security.sql deliberately leaves it unprotected, '
  'because the current application works the same way: dues are a donation '
  'rather than a subscription, so a person states a level and arranges '
  'payment separately. Declaring one grants nothing, since card access is '
  'decided by a vote. card_eligibility compares tiers.sort_order against '
  'the card_access.min_tier governance parameter, so this is read by the '
  'eligibility answer and never by anything that opens a door. Null on a '
  'migrated row means the legacy member_level was null or fell outside the '
  'bands tools/migration/020_migrate.sql names, 2 to 9 among them: the '
  'legacy member_level_string case statement never named those either, so '
  'there is no band to put them in.';

COMMENT ON COLUMN members.legacy_member_level IS
  'users.member_level from the Rails database, carried verbatim so the tier '
  'mapping stays auditable. The legacy integer encoded the tier and the '
  'dollar amount at once, and the bands tools/migration/020_migrate.sql '
  'reads it through are quoted there from app/models/user.rb. Nothing in '
  'this schema decides anything from it. enforce_profile_self_edit refuses '
  'a member editing their own, so it changes only when an admin or an '
  'operator changes it, and after an import that is nobody.';

COMMENT ON COLUMN members.joined_on IS
  'A date rather than a timestamp, and the one legacy time value that '
  'survives the import with no zone question, because '
  'tools/migration/020_migrate.sql casts users.created_at to date and a '
  'cast from timestamp to date involves no zone at all. card_eligibility in '
  'db/migrations/012_close_remaining.sql starts the tenure clock here and '
  'falls back to created_at when it is null, so editing this date moves '
  'when somebody becomes eligible to be nominated for card access.';

COMMENT ON COLUMN members.paid_through IS
  'Set by an admin, and no service code in this repository writes it. '
  'Payments are out of scope for this build, so it is a hand kept date '
  'until something records dues. enforce_profile_self_edit refuses a member '
  'changing their own. Card eligibility does not read it: '
  'db/migrations/012_close_remaining.sql reads standing instead, so a date '
  'here on its own opens nothing.';

COMMENT ON COLUMN members.oriented_at IS
  'When the member had their walk through of the lab. From '
  'users.orientation, read at time zone UTC by '
  'tools/migration/020_migrate.sql, because Rails 3.2 stores UTC and '
  'reading it in the lab''s own zone would move every row seven hours. It '
  'gates nothing here, on purpose. The legacy application gated the member '
  'directory and the equipment list on it, so a volunteer never getting '
  'round to running the walk through locked a paying member out of both.';

COMMENT ON COLUMN members.oriented_by IS
  'Who ran the orientation. Filled by a second pass in '
  'tools/migration/040_not_carried.sql from users.oriented_by_id, after '
  'every member row exists, and tools/migration/030_verify.sql refuses to '
  'finish if any member lost that link. The pass turns members_updated_at '
  'off around itself, because a BEFORE UPDATE trigger would otherwise stamp '
  'now() over the legacy updated_at the import had just carried, for those '
  'members and no others. Do not expect the API to resolve this to a '
  'person. Finding 3 in docs/api/contract-review-notes.md records that no '
  'policy lets one member read another member''s row, so '
  'services/api/app/members.py leaves the column out rather than promising '
  'a name it cannot fetch.';

COMMENT ON COLUMN members.current_skills IS
  'Free text the member writes about themselves. member_directory publishes '
  'it to any signed in member with no visibility flag over it, which is the '
  'point of the directory: somebody wants to find the person who knows the '
  'mill. Carried from the legacy column of the same name, trimmed, with a '
  'blank written as null.';

COMMENT ON COLUMN members.desired_skills IS
  'What the member wants to learn, and the half of the directory that makes '
  'it worth reading in the other direction. Published through '
  'member_directory to any signed in member, again with no visibility flag '
  'over it. Carried from the legacy column of the same name.';

COMMENT ON COLUMN members.marketing_source IS
  'How the member heard about the lab, in their own words. Free text '
  'carried from the legacy column of the same name. Nothing counts or '
  'groups it today, so anybody who wants a report from it is reading prose. '
  'A member may edit their own.';

COMMENT ON COLUMN members.emergency_name IS
  'Emergency contact lives on the member rather than on the waiver, because '
  'the waivers table here holds nothing that is on the document and this is '
  'a fact that has to stay current. Readable by the member it belongs to '
  'and by admins, and by nobody else. Rule 13 of CLAUDE.md applies with '
  'force: this names a third party who never signed up for anything.';

COMMENT ON COLUMN members.emergency_phone IS
  'The number somebody calls from the floor when a person is hurt. Stale is '
  'the failure mode that matters, which is why this sits on the member and '
  'is theirs to edit rather than being copied off a signed waiver that '
  'nobody revisits. No format is enforced, for the same reason as phone.';

COMMENT ON COLUMN members.emergency_email IS
  'citext like email, and deliberately not unique: two members may name the '
  'same person, and a household will. Carried lowercased and trimmed by '
  'tools/migration/020_migrate.sql, with a blank written as null. Visible '
  'to the member and to admins only.';

COMMENT ON COLUMN members.twitter_url IS
  'One of the four social links the current signup form collects. The '
  'social_urls_are_http constraint refuses anything that does not begin '
  'http or https, and tools/migration/020_migrate.sql drops a legacy value '
  'that would fail rather than carrying it, because the legacy application '
  'validated the same way and still let blanks through. Published nowhere: '
  'member_directory does not select it.';

COMMENT ON COLUMN members.facebook_url IS
  'Under social_urls_are_http with the other three links, so a bare domain '
  'is refused at write time rather than stored and rendered as a broken '
  'link later. The import drops a legacy value that fails that pattern '
  'instead of repairing it, since a guess at what somebody meant is not '
  'data.';

COMMENT ON COLUMN members.github_url IS
  'Same constraint and the same import rule as the other three social '
  'links. The API returns it on a member''s own record and nothing else in '
  'this project acts on it; member_directory does not select it. It exists '
  'because the current signup form collects it, and dropping a field at '
  'import would be losing what a member typed in order to save a column.';

COMMENT ON COLUMN members.website_url IS
  'The fourth social link, and the only one that names no particular '
  'service, so it is where a member puts anything else. Constrained to an '
  'http or https prefix by social_urls_are_http along with the other three.';

COMMENT ON COLUMN members.email_visible IS
  'Acted on in exactly one place, the CASE expression in member_directory '
  '(db/migrations/011_close_read_holes.sql). Row level security filters '
  'rows and cannot hide a column, so no policy can enforce this and the '
  'directory endpoints must read that view and never the base table. False '
  'by default, and tools/migration/020_migrate.sql coalesces the nullable '
  'legacy boolean to false, so a member who never answered stays '
  'unpublished.';

COMMENT ON COLUMN members.phone_visible IS
  'The same shape as email_visible and read in the same CASE expression in '
  'member_directory. Setting it false does not hide the number from an '
  'admin, who reads the base table through admin_reads_all in '
  'db/migrations/004_security.sql. What this flag decides is publication to '
  'other members.';

COMMENT ON COLUMN members.listed_in_directory IS
  'NOT NULL with a default of true, and that is the fix for a real legacy '
  'defect: the legacy hidden column was nullable and filtered with = false, '
  'so every row where nobody had ever answered quietly vanished from the '
  'directory. tools/migration/020_migrate.sql writes NOT coalesce(hidden, '
  'false). member_directory filters on it, so a member who opts out is '
  'unreachable through the directory even by a member who is listed.';

COMMENT ON COLUMN members.created_at IS
  'Carried from the legacy users.created_at, read at time zone UTC rather '
  'than in the session zone, because the lab''s own zone is America/Phoenix '
  'and reading it there moves every row seven hours. It is also what '
  'card_eligibility in db/migrations/012_close_remaining.sql starts the '
  'tenure clock from when joined_on is null.';

COMMENT ON COLUMN members.updated_at IS
  'Maintained by the members_updated_at trigger, which runs set_updated_at '
  'from db/migrations/001_schema.sql, borrowed from '
  'heatsynclabs/members_api. The import is the exception: it writes the '
  'legacy value, and tools/migration/040_not_carried.sql disables that '
  'trigger around the oriented_by pass so the pass does not stamp now() '
  'over what the import had just carried. tools/migration/030_verify.sql '
  'fails the whole migration if any member did not keep the timestamp it '
  'arrived with.';

COMMENT ON COLUMN members.deleted_at IS
  'Soft delete, and what makes a person nobody. current_member_id, '
  'is_admin, admin_count, member_directory and link_or_create_member all '
  'read it after db/migrations/011 and 012, so a deleted member resolves to '
  'no identity, holds no admin role, and stops counting toward the two '
  'approver rule. No migration and no service code writes it: '
  'docs/api/members-v1.yaml declares no delete operation, so today it is an '
  'operator acting at the database. Finding 13 in '
  'docs/api/contract-review-notes.md is open against it: admin_reads_all '
  'carries no filter on this column, so an admin listing members gets '
  'deleted rows mixed in with live ones and nothing in the response tells '
  'the two apart.';

-- ------------------------------------------------ The directory view over it

COMMENT ON COLUMN member_directory.id IS
  'members.id, projected unchanged, and the only identifier this system '
  'hands one member for another. services/api/app/members.py matches it as '
  'id::text against a lowercased parameter, because Postgres prints a uuid '
  'in lowercase and RFC 4122 allows either case. A row missing from here '
  'says nothing about whether that member exists. The view drops anybody '
  'unlisted or deleted, and after db/migrations/011_close_read_holes.sql '
  'dropped member_reads_directory no policy lets an ordinary member read '
  'the members row of somebody else.';

COMMENT ON COLUMN member_directory.name IS
  'coalesce(display_name, name), so it is what the member chose to be '
  'called and falls back to the name on the membership record. The legacy '
  'users table has no display name column, so every migrated row reads the '
  'legacy name until its member sets one. The directory query in '
  'services/api/app/members.py sorts on this expression, which means '
  'setting a display name moves the row. Do not read it as a legal name and '
  'do not match it against one.';

COMMENT ON COLUMN member_directory.pronouns IS
  'members.pronouns, projected with no visibility flag over it, unlike '
  'email and phone. A member who does not want it shown clears the field. '
  'Null is an empty field and not a statement about a person, and it is the '
  'value on every migrated row: the legacy users table has no such column, '
  'so tools/migration/020_migrate.sql carries nothing into it.';

COMMENT ON COLUMN member_directory.email IS
  'A CASE over members.email_visible rather than a projection of the '
  'column, so null here means one of two things and does not say which: no '
  'address on file, or an address the member chose not to publish. Never '
  'read it as proof that a member has no email. '
  'tools/migration/020_migrate.sql reads the legacy flag through coalesce '
  'to false, so a legacy row that never answered the question arrives '
  'hidden. db/tests/directory.sql asserts the shown case and the hidden '
  'case.';

COMMENT ON COLUMN member_directory.phone IS
  'A CASE over members.phone_visible, the same shape as email. This '
  'expression is the whole of the protection: after '
  'db/migrations/011_close_read_holes.sql the view runs as its owner, so no '
  'policy filters underneath it, and row level security could not hide a '
  'column in any case. Rewriting it as a plain projection of members.phone '
  'publishes every listed member number in one line. db/tests/attacks.sql '
  'counts the rows here carrying a phone number and expects zero under a '
  'fixture where nobody opted in.';

COMMENT ON COLUMN member_directory.current_skills IS
  'Free text the member typed, carried from the legacy users column of the '
  'same name with blanks turned into null by '
  'tools/migration/020_migrate.sql. No vocabulary and no list structure '
  'sits behind it, so do not parse it into tags without asking members '
  'first. No visibility flag covers it either, which means anything written '
  'here is readable by every member who can reach the directory.';

COMMENT ON COLUMN member_directory.desired_skills IS
  'What the member wants to learn, from the legacy users column of the same '
  'name. Handled like current_skills: free text, blanks nulled on import, '
  'no visibility flag. It is the one field where a member writes down what '
  'they cannot do yet, so widening its audience past signed in members is '
  'worth asking about rather than assuming.';

COMMENT ON COLUMN member_directory.joined_on IS
  'members.joined_on. On a migrated row tools/migration/020_migrate.sql '
  'sets it from legacy users.created_at cast to a date, which is when the '
  'legacy account row was made and not necessarily when the person first '
  'came to the lab. That cast involves no time zone, so this column needs '
  'no zone decision at all. The seven timestamp columns the import carries '
  'do need one, and 020_migrate.sql and 024_waivers.sql read every one of '
  'them at time zone UTC so the seven hour shift into America/Phoenix never '
  'lands. HANDOFF.md section 7 lists them. The value is load bearing '
  'outside the directory too: card_eligibility() adds the '
  'card_access.tenure_months parameter to it to work out the date a member '
  'becomes eligible, falling back to created_at where it is null.';

-- ---------------------------------------------------- Cards and the door log

COMMENT ON COLUMN cards.id IS
  'A uuid with no hardware meaning, which is the whole point of it. In the '
  'legacy application the card primary key was the EEPROM slot: '
  'app/models/card.rb builds its request to the controller as m followed by '
  'the id, so an integer key was a physical address and a 200 slot ceiling '
  'sat inside the primary key of a table that will outlive the Arduino. '
  'Here the address is controller_slot and this column is identity alone. '
  'door_events.card_id is the only thing in the schema that references it.';

COMMENT ON COLUMN cards.member_id IS
  'Who the card was issued to. On migration it comes from legacy '
  'cards.user_id, joined through members.legacy_id. It cannot be changed '
  'afterwards: freeze_card_history in db/migrations/012_close_remaining.sql '
  'refuses the update and tells the caller to revoke the card and issue '
  'another, so the record of who held a card stays true. Nullable, and '
  'nothing in the table requires a value, but the ON DELETE SET NULL on the '
  'reference can never fire: the SET NULL is an UPDATE, freeze_card_history '
  'raises on any change to this column, and so deleting a member who holds '
  'a card is refused rather than leaving the card behind with nobody on it. '
  'An active card belonging to nobody is a security finding rather than a '
  'data error, which is why tools/migration/010_preflight.sql refuses to '
  'start while any legacy card points at a user that does not exist. '
  'Indexed by cards_member.';

COMMENT ON COLUMN cards.permission_mask IS
  'The one byte permission value held in the controller slot beside the tag '
  'number, defined in docs/glossary.md. Mask 1 is full access and mask 255 '
  'is no access, and holding at least one card with mask 1 is what '
  'card_access_enabled meant in the legacy application. Despite the name it '
  'is a lookup value rather than a bitmask: processTagAccess switches on '
  'it, and 0, 10, 20 and 255 each mean something of their own, recorded in '
  'services/door/domain/slots.py. Nothing in the database bounds the range. '
  'SlotEntry refuses anything outside 0 to 255 before it can reach the '
  'controller, and tools/migration/010_preflight.sql refuses any legacy '
  'card carrying a permission other than 1, because nobody here has decided '
  'what the other values mean.';

COMMENT ON COLUMN cards.label IS
  'What this card is, in plain words. For example, front desk spare. On '
  'migration it is the legacy cards.name with a blank stored as null. An '
  'admin writes it through the API, because admin_updates_cards in '
  'db/migrations/007_write_policies.sql is the sole UPDATE policy on this '
  'table and CardUpdate in docs/api/members-v1.yaml lets nothing but this '
  'and permission_mask change on a card that already exists. A superuser at '
  'the database bypasses that policy like any other. The holder reads it '
  'and cannot edit it.';

COMMENT ON COLUMN cards.active IS
  'What the door is actually given. door.active_card_table() in '
  'db/migrations/004_security.sql returns only rows that are active and '
  'hold a slot, so this column decides whether a card is in the table the '
  'controller holds. The partial unique index cards_active_tag lets a tag '
  'number be issued again once the older card is inactive, so several rows '
  'may carry one tag while at most one of them is live. A revoked card '
  'never comes back: revoked_cards_are_inactive refuses the combination, '
  'and freeze_card_history in db/migrations/012_close_remaining.sql refuses '
  'to turn one on again. Every migrated card arrives active, because the '
  'legacy schema has no column that could say otherwise and inventing a '
  'revocation would be inventing a fact.';

COMMENT ON COLUMN cards.issued_at IS
  'When the card was handed over. On migration it is the legacy '
  'cards.created_at, read AT TIME ZONE UTC and not in the session zone. The '
  'legacy column is timestamp without time zone, Rails 3.2 stores UTC, and '
  'the lab runs in America/Phoenix, so an implicit read moves every card by '
  'seven hours and a verify written with the same implicit cast agrees with '
  'it. HANDOFF.md section 7 lists this among the seven columns that carried '
  'that defect. It is filled from the same legacy value as created_at, so '
  'on a migrated row the two are equal and neither confirms the other.';

COMMENT ON COLUMN cards.revoked_at IS
  'When the card was taken back. The legacy database records no revocation '
  'at all, so no migrated row carries a value here. Setting it does not by '
  'itself take the card off the controller, because '
  'door.active_card_table() reads active, and revoked_cards_are_inactive is '
  'the check that keeps the two in step. Once it holds a value, '
  'freeze_card_history refuses to clear it, so a card revoked by mistake is '
  'replaced rather than restored.';

COMMENT ON COLUMN cards.revoked_by IS
  'The admin who took the card back. The MyCard shape in '
  'docs/api/members-v1.yaml gives it to the member, on the reasoning that '
  'an action taken on somebody is not a secret, and the same schema records '
  'that the name cannot be filled in yet: '
  'db/migrations/011_close_read_holes.sql dropped the policy that let one '
  'member read another, so a member resolves this id only when they revoked '
  'the card themselves. Nothing in the database fills the column in. '
  'stamp_actor in db/migrations/012_close_remaining.sql is a BEFORE INSERT '
  'trigger that sets granted_by and recorded_by, never a revoked_by, so no '
  'revocation column on any table is stamped from the caller and this one '
  'is no exception. Whatever the caller sends is what lands here, and the '
  'foreign key checks that it is a member rather than that it is the member '
  'who did it.';

COMMENT ON COLUMN cards.revoked_reason IS
  'Why the card was taken back. There is no constraint here requiring one, '
  'unlike member_roles and member_certifications, where '
  'cert_revocations_have_a_reason and role_revocations_have_a_reason in '
  'db/migrations/002_access.sql refuse a revocation with no reason. '
  'CardRevoke in docs/api/members-v1.yaml makes it required with a minimum '
  'length of one, so that endpoint is the only thing enforcing it today and '
  'a row written by any other path can leave it null.';

COMMENT ON COLUMN cards.legacy_id IS
  'cards.id from the Rails database, kept for audit and so the import can '
  'be run again. That number is also the EEPROM slot the card occupied, '
  'because the legacy application wrote the primary key to the controller '
  'as the address, so tools/migration/020_migrate.sql writes the same value '
  'into controller_slot and tools/migration/030_verify.sql refuses to '
  'finish while any row has the two disagreeing. Null on a card this system '
  'issued.';

COMMENT ON COLUMN cards.created_at IS
  'When the row was written. On a migrated card it is the legacy '
  'cards.created_at, read AT TIME ZONE UTC, which is the same value that '
  'lands in issued_at, so the pair tells you nothing about how long a card '
  'waited before it was handed over. HANDOFF.md section 7 lists it among '
  'the seven columns where reading a naive legacy timestamp in the session '
  'zone moved the instant by seven hours.';

COMMENT ON COLUMN cards.updated_at IS
  'Maintained by the cards_updated_at trigger, which calls set_updated_at() '
  'from db/migrations/001_schema.sql. The import writes the legacy '
  'cards.updated_at straight into it and the trigger never fires, because '
  'it runs BEFORE UPDATE and tools/migration/020_migrate.sql only inserts. '
  'Worth knowing before anybody adds a second pass over cards: '
  'tools/migration/040_not_carried.sql makes one over members, and it has '
  'to disable the matching trigger and write the legacy value back by hand, '
  'or the import silently overwrites a timestamp it had just carried.';

COMMENT ON COLUMN door_events.id IS
  'A bigserial that nothing else references. The row it names can never '
  'change or go away: db/migrations/004_security.sql revokes UPDATE and '
  'DELETE from the application role, and door_events_are_append_only in '
  'db/migrations/005_immutability.sql raises on either. A gap in the '
  'sequence is therefore an insert that rolled back or a duplicate that the '
  'dedupe key refused. Nothing the application role can do removes an '
  'entry. On this table it holds SELECT and INSERT only: the blanket grant '
  'in 004_security.sql covers SELECT, INSERT and UPDATE on every table, and '
  'the same file then revokes UPDATE and DELETE on door_events. It holds no '
  'TRUNCATE anywhere. The append only trigger is the second layer, and it '
  'is a row level trigger, which TRUNCATE does not fire, so an operator '
  'with the owner''s rights is the one hole and it takes the whole table.';

COMMENT ON COLUMN door_events.occurred_at IS
  'When it happened at the door, as the source reported it. That is not '
  'when the row arrived, which is recorded_at. The two come apart on a '
  'buffered flush: the door service is meant to hold events while the link '
  'is down and send them on reconnect, so a row can carry a time hours '
  'older than the moment it was stored. That buffer is phase 5 work and is '
  'not built, per services/door/domain/reconcile.py. door_events_time leads '
  'on this column, and door_events_member reaches it second, after '
  'member_id, so a whole table page of entries is served by the first index '
  'and one member''s own page by the second. Nothing pages it yet: no '
  'endpoint in services/api/app reads this table.';

COMMENT ON COLUMN door_events.source IS
  'Which of the three things reported the event, rather than what happened, '
  'which is event_key. The vocabulary is fixed by a CHECK in '
  'db/migrations/002_access.sql to controller, service and portal, so a '
  'fourth source is a migration and not a value a caller can send. '
  'door.record_event() in db/migrations/008_system_paths.sql takes it as a '
  'parameter and does not examine it, which leaves that constraint as the '
  'only thing standing behind the value.';

COMMENT ON COLUMN door_events.event_key IS
  'What happened, in the vocabulary of the door service, per the DoorEvent '
  'schema in docs/api/members-v1.yaml. Nothing in this repository '
  'enumerates those values and no constraint bounds them, unlike source '
  'beside it. The legacy door_logs table put three different shapes of '
  'event under one key column and could not be parsed without a special '
  'case for each, which is why the columns around this one are typed and '
  'why anything that does not fit belongs in detail rather than encoded '
  'into this string. No legacy row reaches this table: '
  'tools/migration/020_migrate.sql carries members and cards and says so.';

COMMENT ON COLUMN door_events.raw_data IS
  'The raw value the controller sent alongside the event, where it sent '
  'one, per the DoorEvent schema in docs/api/members-v1.yaml. It is stored '
  'as it arrived and nothing in this repository reads it or interprets it. '
  'Which events carry a value here, and what a given number means, are open '
  'until the door service grows its event handling: services/door/README.md '
  'records that there is no HTTP API and no reconcile loop yet.';

COMMENT ON COLUMN door_events.card_id IS
  'The card that was presented, where a card was involved. It is recorded '
  'at the time of the event rather than worked out by joining later, so an '
  'entry still names a card whatever happens to the card row afterwards. '
  'The reference is declared ON DELETE SET NULL, and that clause can never '
  'fire: the SET NULL is an UPDATE on this table, and '
  'door_events_are_append_only in db/migrations/005_immutability.sql raises '
  'on it, so deleting a card any entry names is refused rather than quietly '
  'editing the record of who came into a building. In practice nothing '
  'deletes a card: revoking is an update, and the application role holds no '
  'DELETE on any table in db/migrations/004_security.sql.';

COMMENT ON COLUMN door_events.member_id IS
  'Who the entry belongs to, and the column the access record turns on. '
  'member_reads_own_door_events in db/migrations/004_security.sql compares '
  'it against the caller, so a row with a null here is readable by admins '
  'alone and by no member at all. door_events_member indexes it with '
  'occurred_at, which is the read a member''s own history is meant to use. '
  'Nothing issues that read yet. Like card_id it is written when the event '
  'is recorded rather than derived at read time, so a later change to a '
  'card cannot move an entry onto a different member.';

COMMENT ON COLUMN door_events.door IS
  'Which door, by the name the lab uses for it rather than the number the '
  'hardware uses. services/door/domain/status.py names front and rear, and '
  'which physical door is controller door 1 is configuration held in the '
  'adapter, written down as an unconfirmed assumption at the top of '
  'services/door/adapters/oac_ethernet/controller.py. Null where the event '
  'names no door. Nothing in the database constrains the value.';

COMMENT ON COLUMN door_events.detail IS
  'Whatever else the source reported, kept as it arrived. The legacy '
  'door_logs table crammed three shapes of event under one key column, so '
  'the typed columns beside this one carry what is known and this holds the '
  'remainder without a special case for each shape. Two things to weigh '
  'before putting anything in here. Under rule 13 of CLAUDE.md this table '
  'is an access record for a physical building, readable by the member it '
  'concerns and by admins and by nobody else, so anything dropped into this '
  'object inherits exactly that audience and nothing narrower. And it '
  'cannot be corrected later, because door_events_are_append_only in '
  'db/migrations/005_immutability.sql refuses every UPDATE and DELETE on '
  'the table.';

-- ------------------------------------------------------------------- Waivers

COMMENT ON COLUMN waivers.id IS
  'A surrogate key nothing else holds. No foreign key points at this table, '
  'and waiver_status in db/migrations/011_close_read_holes.sql aggregates '
  'by member and never returns it, because the question asked here is about '
  'a person rather than about one document. There is no legacy_id either: '
  'the legacy users table carries a waiver date and nothing more, so a '
  'carried row has no identifier to keep.';

COMMENT ON COLUMN waivers.member_id IS
  'Whose waiver it is. ON DELETE CASCADE rather than the SET NULL that '
  'cards and door_events use, because a waiver with no member records '
  'nothing at all. member_reads_own_waiver in '
  'db/migrations/004_security.sql and waiver_status both key on this '
  'column, and tools/migration/024_waivers.sql resolves it by joining '
  'members on legacy_id.';

COMMENT ON COLUMN waivers.signed_at IS
  'When the person signed. The trap in HANDOFF.md section 7 lands here: the '
  'legacy users.waiver column is timestamp without time zone and this one '
  'is timestamptz, so something has to say which zone the naive value is '
  'in. tools/migration/024_waivers.sql reads it AT TIME ZONE UTC, because '
  'Rails 3.2 stores UTC and reading it in the lab zone of America/Phoenix '
  'would move every waiver seven hours. A verify written as signed_at '
  'equals the legacy column casts both sides the same way and passes '
  'whatever the session is set to, so it proves nothing. waiver_status '
  'returns the newest of these.';

COMMENT ON COLUMN waivers.expires_at IS
  'Null means the waiver has not lapsed, and waiver_status reads it exactly '
  'that way. tools/migration/024_waivers.sql writes null for every carried '
  'row on purpose: the legacy system recorded no expiry and the lab has no '
  'written rule giving a waiver one, so a date computed here would invent a '
  'policy nobody agreed to.';

COMMENT ON COLUMN waivers.recorded_by IS
  'Which admin recorded the waiver, stamped rather than accepted: the '
  'stamp_actor trigger in db/migrations/012_close_remaining.sql overwrites '
  'whatever the caller sent on every insert under oro_api, because one '
  'admin could otherwise attribute their own action to somebody else. Null '
  'on a carried row, because the legacy system did not record who entered a '
  'waiver date and naming a member would be inventing one.';

COMMENT ON COLUMN waivers.note IS
  'Free text, and the one field on this table where something off the '
  'document itself can arrive. db/tests/waivers.sql asserts that no column '
  'here is named for a name, an address, a phone, a guardian or a '
  'signature, and a check over column names cannot see inside free text, so '
  'the rule holds only while whoever writes here keeps to the record rather '
  'than its contents. tools/migration/024_waivers.sql writes one fixed '
  'sentence saying the row came from the legacy database.';

COMMENT ON COLUMN waivers.created_at IS
  'When this row was written, which is not when the person signed. That is '
  'signed_at. tools/migration/024_waivers.sql leaves this at its default, '
  'so on a carried row it is the clock of the import rather than anything '
  'out of the legacy database, unlike members.created_at, which '
  'tools/migration/020_migrate.sql reads across AT TIME ZONE UTC. No '
  'updated_at column here, and nothing like the set_updated_at trigger '
  'members and cards carry.';

-- ------------------------------------------------------------ Certifications

COMMENT ON COLUMN certifications.id IS
  'A short key chosen by whoever adds the tool, used in the grant path of '
  'the contract in docs/api/members-v1.yaml and written as laser and mill '
  'in db/tests. Three foreign keys point at it: '
  'member_certifications.certification_id, '
  'certification_instructors.certification_id, and prerequisite_id on this '
  'table. None of them cascades on update, so once a single grant exists '
  'this value can no longer be renamed. Change name instead.';

COMMENT ON COLUMN certifications.name IS
  'The word the lab actually uses for the tool, per rule 7 of CLAUDE.md and '
  'docs/glossary.md. Safe to change whenever the lab renames something, '
  'because the foreign keys hold id and nothing keys on this. '
  'db/seed/001_reference.sql seeds no certifications at all, and '
  'docs/api/members-v1.yaml declares no operation that adds a row to this '
  'table, so every row today is written at the database. '
  'admin_writes_certifications in 007_write_policies.sql is what holds when '
  'one arrives: under oro_api only an admin may insert, and a superuser '
  'bypasses that policy like any other.';

COMMENT ON COLUMN certifications.description IS
  'Copy a member is meant to read, so docs/conventions/voice.md governs it. '
  'Where certification is required before somebody may use a tool, this '
  'says required and never recommended, which voice.md bans under No safety '
  'softening. Nothing checks that: tools/voice-check reads files rather '
  'than rows, and docs/api/members-v1.yaml declares no operation that '
  'writes a row in this table, so a description here is typed at the '
  'database and read by nobody with a gate. Null where the name says '
  'everything.';

COMMENT ON COLUMN certifications.prerequisite_id IS
  'Another row on this table, the one docs/api/members-v1.yaml describes as '
  'having to be held before this certification is granted. Nothing in this '
  'database enforces that. No trigger reads the column at grant time and no '
  'constraint stops a row naming itself or two rows naming each other, so '
  'whoever builds the grant path owns the check and the cycle.';

COMMENT ON COLUMN certifications.validity_months IS
  'Months a grant lasts where the lab wants an expiry, and null means no '
  'default. docs/api/members-v1.yaml says a grant sent with no expiry '
  'should take one from here, and nothing does that yet: '
  'member_certifications.expires_at is only ever the value the writer '
  'supplied. Set it on the tools where a skill goes stale, and leave it '
  'null where an hour of instruction holds forever.';

COMMENT ON COLUMN certifications.active IS
  'The intended way to retire a tool, and nothing acts on it yet. oro_api '
  'holds no DELETE on any table, and a delete by an operator is refused by '
  'the foreign keys while any member_certifications row, '
  'certification_instructors row, or prerequisite_id on this table points '
  'at it, so clear this rather than deleting. Nothing in db/migrations '
  'reads the column and no endpoint filters on it, so a false value neither '
  'refuses a grant nor hides the row.';

COMMENT ON COLUMN certifications.legacy_id IS
  'Reserved, and empty in every database this repository builds. Nothing '
  'imports certifications: tools/migration carries members, cards, roles '
  'and waivers, and tools/migration/fixtures/legacy-schema.sql declares '
  'only legacy.users and legacy.cards, so which legacy table an id here '
  'would come from is not established anywhere. Do not read it as '
  'members.legacy_id, which is users.id from the Rails database and has a '
  'source.';

COMMENT ON COLUMN member_certifications.id IS
  'A surrogate key for the reason written on member_roles in '
  '002_access.sql: revocation is a recorded row rather than a delete, so a '
  'composite key on member and certification would make it impossible to '
  'certify somebody again after revoking them. Nothing holds a foreign key '
  'to this. The sequence counts rows written rather than certifications '
  'held, because every revoked grant stays.';

COMMENT ON COLUMN member_certifications.member_id IS
  'Who was certified. member_reads_own_certs in 004_security.sql compares '
  'it against current_member_id(), which is how an ordinary member reaches '
  'their own row. Two other SELECT policies ignore this column: '
  'admin_reads_all_certs in the same file, and '
  'instructor_reads_their_certifications added in 012_close_remaining.sql. '
  'The cascade on delete means a hard DELETE of a member takes their '
  'certification history with it. Nothing in db/migrations issues one: '
  'is_admin(), current_member_id() and member_directory all read '
  'members.deleted_at instead.';

COMMENT ON COLUMN member_certifications.certification_id IS
  'Which tool, and also the value the instructor policies match on. '
  'instructor_grants_certification in 007_write_policies.sql and '
  'instructor_reads_their_certifications in 012_close_remaining.sql both '
  'look for a certification_instructors row holding the caller and this '
  'exact id, so somebody who instructs the laser can write laser rows and '
  'nothing else. db/tests/write_policies.sql proves the mill is refused.';

COMMENT ON COLUMN member_certifications.granted_by IS
  'Who signed the person off. The stamp_actor trigger in '
  '012_close_remaining.sql overwrites this on insert with the identity set '
  'on the transaction whenever the caller is oro_api, so whatever a client '
  'sends is discarded and an admin cannot record their own grant under '
  'another name. A row written by an operator or by an import keeps '
  'whatever that writer supplied, because the trigger acts only for the '
  'application role.';

COMMENT ON COLUMN member_certifications.granted_at IS
  'When the row was written, which is not necessarily when the person was '
  'taught. Nothing freezes it. member_roles has freeze_role_grant in '
  '005_immutability.sql and this table has no equivalent, so the instructor '
  'who may revoke a grant under instructor_revokes_certification in '
  '007_write_policies.sql may also rewrite the date it was made: that '
  'policy tests who is asking and never what the row becomes. Read that as '
  'a gap somebody should close, not as permission.';

COMMENT ON COLUMN member_certifications.expires_at IS
  'Meant to be the date this grant lapses, with null meaning it does not. '
  'Nothing in db/migrations reads the column, so a date here changes '
  'nothing on its own. member_certifications_one_live is partial on '
  'revoked_at alone, so a grant that expired years ago still holds the one '
  'live slot for that member and tool, and a fresh grant is refused until '
  'the old row is revoked. docs/api/members-v1.yaml describes a grant with '
  'no expiry taking one from certifications.validity_months, and no code '
  'does that yet.';

COMMENT ON COLUMN member_certifications.revoked_at IS
  'Set rather than deleting the row, because who was certified and who took '
  'it away is exactly what an audit asks. member_certifications_one_live is '
  'a unique index over member and certification limited to rows where this '
  'is null, which is what lets a person be certified, revoked, and '
  'certified again on the same tool. No trigger ever sets it.';

COMMENT ON COLUMN member_certifications.revoked_by IS
  'Who took the certification away. Unlike granted_by, nothing stamps it: '
  'stamp_actor fires on insert only, so this is whatever the writer '
  'supplied. It is not required either. cert_revocations_have_a_reason '
  'makes the reason mandatory when revoked_at is set and says nothing about '
  'the person, so a revocation can be recorded with no name against it.';

COMMENT ON COLUMN member_certifications.revoked_reason IS
  'Required whenever revoked_at is set, by the '
  'cert_revocations_have_a_reason constraint in 002_access.sql. The member '
  'concerned reads their own row under member_reads_own_certs, so write it '
  'as something you would say to them rather than about them. A tool going '
  'out of service and a person needing more instruction both land here, and '
  'they read very differently.';

COMMENT ON COLUMN member_certifications.note IS
  'Free text about this one grant. It is not private: the member reads '
  'their own row, admins read every row, and any instructor for that tool '
  'reads it under instructor_reads_their_certifications. Rule 13 of '
  'CLAUDE.md treats what is here as belonging to the member, so nothing '
  'about anybody else belongs in it.';

COMMENT ON COLUMN certification_instructors.member_id IS
  'The person who may sign others off on this tool. A row here carries a '
  'second power that is easy to miss: waiver_status in '
  '011_close_read_holes.sql lets any instructor ask whether any member has '
  'a valid waiver, because somebody running a class has to check before it '
  'starts. Only an admin may add one: admin_sets_instructors in '
  '007_write_policies.sql is the sole INSERT policy. No endpoint does it, '
  'since docs/api/members-v1.yaml declares no operation that appoints an '
  'instructor, so today it is an admin at the database.';

COMMENT ON COLUMN certification_instructors.certification_id IS
  'The tool, which is the whole scope of the appointment. An instructor '
  'here instructs on one thing, the rule docs/glossary.md states and the '
  'legacy global instructor boolean got wrong, so somebody trusted with the '
  'laser has no standing on the mill. tools/migration/010_preflight.sql '
  'refuses to start an import while any legacy user still carries that '
  'boolean, because nobody can guess which ids belong in these rows.';

COMMENT ON COLUMN certification_instructors.granted_by IS
  'Who appointed the instructor. This column is not stamped. stamp_actor in '
  '012_close_remaining.sql fills granted_by on member_roles and '
  'member_certifications and recorded_by on waivers and payments, and it '
  'does not fire on this table, so the value is whatever the writer '
  'supplied rather than the caller''s own identity the way those four are '
  'when oro_api writes them.';

COMMENT ON COLUMN certification_instructors.granted_at IS
  'When the appointment was recorded. There is no revoked_at beside it, so '
  'taking somebody off a tool is a DELETE and this table keeps no trace '
  'that they ever instructed, which is the reverse of how member_roles '
  'treats the same question. oro_api holds no DELETE on any table and no '
  'UPDATE policy exists here, so that removal is an operator acting at the '
  'database.';

-- ----------------------------- Roles, and the two approver control over them

COMMENT ON COLUMN approvals.id IS
  'The target of a composite foreign key rather than a plain one, which is '
  'why this table also carries UNIQUE (id, target_member_id, role_id) even '
  'though the primary key already makes id unique. A foreign key needs a '
  'unique constraint over exactly the columns it references, and '
  'member_roles references all three together. Dropping that second unique '
  'constraint as redundant is refused while member_roles carries the '
  'composite foreign key, and dropping it with CASCADE takes that key away, '
  'and that key is what ties one approval to one specific grant.';

COMMENT ON COLUMN approvals.kind IS
  'grant_role or revoke_role, and only grant_role does anything today. '
  'enforce_role_grant_rules, written in db/migrations/003_rules.sql and '
  'replaced in 013_bootstrap_three_admins.sql, refuses a grant whose '
  'approval is not a grant_role, and nothing acts on a revoke_role row, '
  'because revoking is single actor by design: a rule that needs two people '
  'to remove a compromised admin fails at the worst moment. The value '
  'exists so the table can record a revocation proposal if the lab later '
  'decides it wants one. ApprovalCreate in docs/api/members-v1.yaml accepts '
  'grant_role and nothing else.';

COMMENT ON COLUMN approvals.target_member_id IS
  'Who the change is about, and half of what makes an approval authorise '
  'one grant instead of any grant. member_roles references (approval_id, '
  'member_id, role_id) against (id, target_member_id, role_id) here, so an '
  'approval naming Dan cannot be spent granting admin to Erin. '
  'freeze_approval_proposal, written in db/migrations/005_immutability.sql '
  'and rewritten in 010_close_approval_holes.sql, refuses any change to it, '
  'because otherwise a single admin could repoint an already approved row '
  'at somebody else and the foreign key would faithfully follow.';

COMMENT ON COLUMN approvals.role_id IS
  'The role being proposed, which in practice is a role whose grants_roles '
  'is true, and db/seed/001_reference.sql seeds exactly one of those: '
  'admin. Nothing refuses a row naming an ordinary role. Such a row is '
  'inert rather than dangerous, since enforce_role_grant_rules only '
  'consults an approval when the role being granted can itself grant roles, '
  'so the proposal sits in the queue and authorises nothing. Frozen after '
  'insert, alongside target_member_id, by freeze_approval_proposal.';

COMMENT ON COLUMN approvals.reason IS
  'Free text for the second admin to read before deciding, and nullable '
  'because nothing requires one. freeze_approval_proposal, as rewritten in '
  'db/migrations/010_close_approval_holes.sql, does not freeze this column, '
  'so the stated reason can still be edited after the decision it '
  'justified.';

COMMENT ON COLUMN approvals.proposed_by IS
  'The first of the two admins. enforce_proposer_is_caller in '
  'db/migrations/010_close_approval_holes.sql refuses any insert where this '
  'differs from current_member_id() when the writer is the oro_api role, so '
  'an admin cannot file a proposal in somebody else''s name, and the '
  'admin_proposes policy requires that caller to hold admin when the row is '
  'filed. Whether the proposer still holds it is checked again by '
  'enforce_approval_is_by_two_admins when the approval is decided, rather '
  'than when the grant is written, so a proposer who later loses the role '
  'does not retroactively invalidate a decision a second admin already '
  'made. The approver_is_not_proposer check compares decided_by against '
  'this column, and no bylaws amendment makes self approval acceptable.';

COMMENT ON COLUMN approvals.proposed_at IS
  'When the proposal was filed, frozen by freeze_approval_proposal so it '
  'cannot be backdated afterwards. Expiry does not read it. expires_at '
  'carries its own default of now() plus thirty days, evaluated '
  'independently at insert, so a row written with an explicit proposed_at '
  'does not shift when it expires.';

COMMENT ON COLUMN approvals.decided_by IS
  'The second admin, null until somebody decides. The admin_decides policy '
  'as rewritten in db/migrations/010_close_approval_holes.sql permits '
  'writing only your own member id here, freeze_approval_proposal refuses '
  'any change once it is set, and approver_is_not_proposer refuses the '
  'proposer. Before 010 that policy carried no WITH CHECK and this column '
  'was not frozen, so one admin could write another member id into it, '
  'approve, and grant, while the second admin never touched the row.';

COMMENT ON COLUMN approvals.decided_at IS
  'When the decision was made, and the timestamp expiry is measured '
  'against. enforce_role_grant_rules compares it with expires_at, so an '
  'approval decided inside its window still authorises its grant '
  'afterwards, and one decided late is refused. The '
  'decided_rows_have_a_time check added in '
  'db/migrations/010_close_approval_holes.sql keeps it in step with status, '
  'because a decided row carrying no decision time made that comparison a '
  'no-op. Under the oro_api role freeze_approval_proposal fills it from '
  'now() when a decision arrives without one.';

COMMENT ON COLUMN approvals.status IS
  'pending, approved, rejected, or withdrawn, and that vocabulary is the '
  'CHECK on this column. Only approved authorises anything, since '
  'enforce_role_grant_rules refuses a grant against any other value. '
  'approved and rejected are final: freeze_approval_proposal refuses a '
  'change out of either, so withdrawn is the only way to retire a proposal '
  'without deciding it, and it applies while the row is still pending. Two '
  'checks tie this column to the decision, decided_rows_have_a_decider and '
  'decided_rows_have_a_time, so pending and withdrawn are exactly the rows '
  'with no decider and no decision time.';

COMMENT ON COLUMN approvals.expires_at IS
  'Thirty days from insert by default. It is a deadline on the decision, '
  'not on the grant: enforce_role_grant_rules compares it against '
  'decided_at, so a grant written long afterwards on an approval that was '
  'decided in time is still allowed. Nothing sweeps expired rows. A '
  'proposal that passes this date keeps its pending status until somebody '
  'withdraws it, and the refusal comes when a grant is attempted.';

COMMENT ON COLUMN member_roles.id IS
  'A surrogate key, and it exists because (member_id, role_id) cannot be '
  'the key here. Revocation is a recorded row rather than a DELETE, so a '
  'natural key would make it impossible to grant a role back to somebody it '
  'was revoked from, which happens whenever a person rotates off operations '
  'and later returns. No foreign key points at this column: the composite '
  'foreign key to approvals runs the other way, out of approval_id. The API '
  'does return it, as RoleGrant.id in docs/api/members-v1.yaml.';

COMMENT ON COLUMN member_roles.member_id IS
  'Who holds the role, read far more widely than by this table. is_admin '
  'and admin_count as rewritten in db/migrations/012_close_remaining.sql '
  'resolve an admin through it, and the composite foreign key matches it '
  'against approvals.target_member_id so an approval cannot be spent on a '
  'different person. freeze_role_grant refuses to move a grant to another '
  'member. One consequence sets the order of the legacy import: '
  'link_or_create_member refuses to claim a member row that holds any live '
  'role, so identity subjects have to land before '
  'tools/migration/022_roles.sql runs, which is the order '
  'docs/plan/data-model.md section 6.1 sets. With roles first, every '
  'migrated role holder needs linking by hand.';

COMMENT ON COLUMN member_roles.role_id IS
  'Which role, from the vocabulary seeded in db/seed/001_reference.sql: '
  'admin, accountant, board, operations, host. Whether grants_roles is true '
  'on the row it points at is what decides whether this grant needs an '
  'approval, so the scope of the two approver rule is data rather than a '
  'literal in a trigger. Policies and functions do compare specific values '
  'though. The waiver_status function in '
  'db/migrations/011_close_read_holes.sql names host, operations and board, '
  'and the accountant_records_payments policy in '
  'db/migrations/012_close_remaining.sql names accountant, so renaming an '
  'id means editing those as well. Frozen after insert by '
  'freeze_role_grant.';

COMMENT ON COLUMN member_roles.granted_by IS
  'The admin who made the grant, taken from the caller rather than from the '
  'request: stamp_actor in db/migrations/012_close_remaining.sql overwrites '
  'whatever was sent with current_member_id() when the writer is oro_api, '
  'and leaves the column alone for any other writer. Before that trigger '
  'existed, an admin could attribute their own grant to somebody else. '
  'tools/migration/022_roles.sql writes null deliberately, because the '
  'legacy admin and accountant flags are bare booleans with nobody recorded '
  'behind them and inventing a granter would be a lie in an audit trail '
  'that exists to be trusted.';

COMMENT ON COLUMN member_roles.granted_at IS
  'When the grant was recorded, defaulted at insert and then frozen by '
  'freeze_role_grant. On a migrated row it is when the import ran, not when '
  'the lab gave somebody the role, which the legacy users table never '
  'recorded: admin and accountant are boolean columns with no date beside '
  'them. tools/migration/022_roles.sql prints the same warning in its own '
  'log, because a reader who assumes otherwise will date an admin '
  'appointment years wrong.';

COMMENT ON COLUMN member_roles.approval_id IS
  'The approval that authorised this grant, or null where no approval '
  'stands behind it. Null is ordinary for a role whose grants_roles is '
  'false, since a single admin grants those. On a role that can itself '
  'grant roles, null means a bootstrap grant, and the bootstrap is a quota '
  'rather than a threshold: bootstrap_admin_grants_used in '
  'db/migrations/013_bootstrap_three_admins.sql counts exactly these rows, '
  'revoked ones included, and the fourth such grant is refused. A threshold '
  'on the live admin count would instead hold the escape open for as long '
  'as the lab had only two admins, which is the point at which two people '
  'could have satisfied the rule. Revoking admins does not hand it back '
  'either: two_approver_armed latches once the bootstrap runs out. Nothing '
  'separate records the quota, which makes this column the record of it, '
  'and no application role holds DELETE here so the count only rises. Also '
  'frozen by freeze_role_grant, unique across its non-null values so one '
  'approval cannot authorise two grants, and one of the three columns of '
  'the composite foreign key tying this grant to an approval naming this '
  'exact member and role.';

COMMENT ON COLUMN member_roles.expires_at IS
  'Null means the grant does not expire. Since '
  'db/migrations/012_close_remaining.sql, is_admin and admin_count read it, '
  'so an expired admin role stops resolving as admin; before that nothing '
  'read the column and an expired role still counted. It does not release '
  'the live slot, though. member_roles_one_live keys on revoked_at alone, '
  'so an expired row still blocks a fresh grant of the same role to the '
  'same member until somebody revokes it.';

COMMENT ON COLUMN member_roles.revoked_at IS
  'Set this to revoke, never DELETE, because who used to be an admin and '
  'who removed them is exactly what an audit asks and a deleted row cannot '
  'answer it. Setting it takes the row out of is_admin and admin_count and '
  'out of the member_roles_one_live partial index, which is what allows the '
  'same role to be granted again later. freeze_role_grant refuses to clear '
  'it once set. Revoking needs no approval even for a role that grants '
  'roles, and enforce_role_grant_rules returns early to say so, because a '
  'rule that makes removing a compromised admin need two people fails at '
  'the worst moment. A revoked bootstrap grant still counts against the '
  'bootstrap quota.';

COMMENT ON COLUMN member_roles.revoked_by IS
  'Who removed the role. Not stamped from the caller, unlike granted_by: '
  'stamp_actor is a BEFORE INSERT trigger and a revocation is an UPDATE, so '
  'this is whatever the writer supplied. The admin_revokes_roles policy in '
  'db/migrations/007_write_policies.sql still requires an admin for a '
  'revocation written through the application role, so such a row was '
  'written by an admin even where this column names somebody else.';

COMMENT ON COLUMN member_roles.revoked_reason IS
  'Required whenever revoked_at is set, by the '
  'role_revocations_have_a_reason check. Free text with no vocabulary, and '
  'it is the part of a revocation a person actually reads two years later. '
  'The check exists because the row is the whole record. A revocation with '
  'no reason leaves an audit able to say only that somebody removed '
  'somebody.';

COMMENT ON COLUMN roles.id IS
  'The word this role is called by everywhere, which is why it is a text '
  'key rather than a serial. Policies and functions compare it as a '
  'literal: accountant in the payments policy in '
  'db/migrations/012_close_remaining.sql, and host, operations and board in '
  'waiver_status in db/migrations/011_close_read_holes.sql. Renaming a row '
  'means editing those too. No application role holds INSERT or UPDATE on '
  'this table, revoked in db/migrations/004_security.sql, so adding or '
  'changing a role is a migration.';

COMMENT ON COLUMN roles.name IS
  'The label a person sees. Nothing compares it, so rewording it touches no '
  'SQL: code reads roles.id instead. db/seed/001_reference.sql pairs Board '
  'member with the id board and Admin with admin, so the two are not '
  'interchangeable.';

COMMENT ON COLUMN roles.description IS
  'What the role is for, in the words the lab uses. It carries no authority '
  'of its own. What a role can actually do lives in grants_roles and in the '
  'policies that name the id, so a description that drifts from those '
  'misleads a reader rather than misconfiguring the system.';

COMMENT ON COLUMN two_approver_armed.armed_at IS
  'When a write to member_roles first found the bootstrap spent, which is '
  'three live admins or three unapproved admin grants, whichever came '
  'first. arm_two_approver_rule is a statement trigger on member_roles '
  'alone, so a lab that reaches three live admins by another route, '
  'restoring a soft deleted admin for instance, arms on its next role write '
  'rather than at that moment. Nothing reads the value: '
  'two_approver_rule_can_bind only tests whether the row is present, so '
  'this is a record for whoever asks later why the escape closed rather '
  'than an input to any decision. arm_two_approver_rule writes it and is '
  'SECURITY DEFINER, which it has to be, because the application role holds '
  'no privilege on this table at all. The GRANT in '
  'db/migrations/004_security.sql covered the tables existing at that point '
  'and this one arrived in db/migrations/010_close_approval_holes.sql.';

COMMENT ON COLUMN two_approver_armed.one_row IS
  'Not data. It is the whole of how this table is held to a single row: '
  'true is the only value the CHECK admits, a primary key cannot be null, '
  'and a primary key makes true unique, so a second arming collides on the '
  'key instead of adding a second row. arm_two_approver_rule inserts '
  'DEFAULT VALUES and never names the column, which is how the idiom is '
  'meant to be used. Do not read it, and do not add a row to record a later '
  'arming. Deleting the row is the shape an attempt to reopen the bootstrap '
  'escape takes, and it reopens nothing once member_roles holds three '
  'unapproved admin grants or the lab holds three live admins, because that '
  'is what two_approver_rule_can_bind falls back to.';

-- ------------------------------- Tiers, payments and the governance numbers

COMMENT ON COLUMN tiers.id IS
  'A stable identifier rather than a label. db/seed/001_reference.sql seeds '
  'none, unable, volunteer, associate, basic and plus. members.tier_id '
  'points here, tools/migration/020_migrate.sql maps the legacy '
  'member_level bands onto these exact strings, and the '
  'card_access.min_tier row in governance_parameters holds one of them as a '
  'JSON string. Rename the tier card_access.min_tier names and '
  'card_eligibility finds no rank for it, so every member is refused, with '
  'a reason naming a tier that no longer exists rather than an error.';

COMMENT ON COLUMN tiers.name IS
  'What a member reads, where the id is what code keys on. The six seeded '
  'names are the bands in the legacy member_level_string, from '
  'app/models/user.rb in Open-Source-Access-Control-Web-Interface, and '
  'docs/plan/changes-from-the-original.md turns the Level column in the '
  'members directory into this name.';

COMMENT ON COLUMN tiers.monthly_cents IS
  'Cents per month. The seeded figures are the floor of the legacy '
  'member_level band that becomes each tier rather than what any one member '
  'pays: associate 2500 for a band of 25 to 49, basic 5000 for 50 to 99, '
  'which is the fifty dollar level the bylaws card access rule names. '
  'Volunteer is seeded at 0 while the band mapping onto it is 10 to 24, so '
  'those two disagree and the seeded row is the one anything reads. The '
  'members API returns this figure for display and nothing charges anybody, '
  'because payments are out of scope.';

COMMENT ON COLUMN tiers.sort_order IS
  'Rank, and it is what decides card access rather than the price in '
  'monthly_cents. card_eligibility in db/migrations/012_close_remaining.sql '
  'reads the sort_order of the tier named by card_access.min_tier and '
  'refuses any member whose tier ranks below it, so renumbering these '
  'changes who may hold a card. It reads this column and not card_eligible, '
  'which docs/api/contract-review-notes.md section 6 records as a '
  'disagreement between the contract and the database.';

COMMENT ON COLUMN tiers.storage IS
  'What storage the tier includes at the lab. Seeded as bankers box for '
  'basic and lockable locker for plus, null where a tier includes none. '
  'Free text that the members API returns for display. No relation to '
  'waivers.storage, which names the system holding a signed document.';

COMMENT ON COLUMN tiers.active IS
  'Whether the lab still offers this tier. Deactivating rather than '
  'deleting keeps every member row whose tier_id points here resolving. '
  'Nothing filters on it: services/api/app/members.py selects this column '
  'with the rest of the tier and returns it for display, but nothing '
  'decides anything from it, card_eligibility never reads it, and nothing '
  'stops a member choosing a tier that is false. It is a fact for a person '
  'to act on rather than a rule the database enforces.';

COMMENT ON COLUMN tiers.notes IS
  'Unused, and measured so on 2026-08-29. No row in '
  'db/seed/001_reference.sql sets it, nothing under db, services or tools '
  'selects it, and the Tier object in docs/api/members-v1.yaml does not '
  'carry it, so a value written here reaches nobody. Whoever finds a use '
  'for it replaces this sentence with what it holds.';

COMMENT ON COLUMN payments.id IS
  'Internal. No foreign key anywhere points at payments, and '
  'docs/api/members-v1.yaml declares no payments path, so nothing outside '
  'this table holds one of these. legacy_id is what ties a row back to '
  'where it came from, and it is what a re-run of an import has to match '
  'on, because a bigserial hands out fresh values every time.';

COMMENT ON COLUMN payments.member_id IS
  'Who the money was for. Nullable because a payment can arrive from '
  'somebody the lab has not matched to a member yet, and the legacy '
  'database has no foreign keys at all, so a carried user_id may name a row '
  'that does not exist. member_reads_own_payments in '
  'db/migrations/012_close_remaining.sql compares this against the caller, '
  'which makes a row with no member readable by admins only. No import and '
  'no endpoint writes this table yet.';

COMMENT ON COLUMN payments.amount_cents IS
  'Cents, so the 12.50 dollar teacher rate is 1250. Nothing constrains the '
  'value on purpose: the legacy PayPal whitelist took seven specific '
  'amounts and silently dropped everything else, and '
  'docs/plan/data-model.md section 1.4 names that half rate as the payment '
  'it made unrecordable. There is no sign check either, so a correction can '
  'be negative. NOT NULL, so anything imported here later has to arrive '
  'with an amount.';

COMMENT ON COLUMN payments.paid_on IS
  'The day the money arrived. Nothing writes it: no import reads a legacy '
  'payments table, and the payments row in docs/plan/data-model.md section '
  '5 is the only record this repository holds of one. A date rather than a '
  'timestamp, so the naive timestamp trap in HANDOFF.md section 7 does not '
  'reach it. Deliberately not unique with member_id: that same row records '
  'that the legacy unique constraint on (user_id, date) made a second '
  'payment on the same day impossible to record. Today members.paid_through '
  'and members.standing are set by hand.';

COMMENT ON COLUMN payments.method IS
  'How the money arrived. Free text with no CHECK and no vocabulary defined '
  'anywhere in this repository, so whoever builds payments picks the words '
  'and writes them down where the next person can find them. The legacy '
  'system kept payment_method on the member rather than on a payment, and '
  'tools/migration/040_not_carried.sql counts it among the columns the '
  'import drops. Nothing reads this.';

COMMENT ON COLUMN payments.external_ref IS
  'The identifier the paying system knows a payment by. There is no unique '
  'index on it, so it does not by itself stop one payment being recorded '
  'twice. Nothing writes it today. Rule 13 governs whatever ends up here: '
  'an identifier, never a payer name.';

COMMENT ON COLUMN payments.note IS
  'Free text about the payment, and therefore where personal information '
  'can arrive without anybody meaning it to. This table holds no payer name '
  'and no payer email, and a note is not the place to put one back. The '
  'legacy payee, the name of somebody paying on behalf of a member, has no '
  'column anywhere in this schema, and tools/migration/010_preflight.sql '
  'refuses to start while a legacy row still carries one, which makes it a '
  'decision somebody owns rather than something to slide in here.';

COMMENT ON COLUMN payments.recorded_by IS
  'Which member keyed the payment in, stamped rather than accepted from the '
  'caller. The stamp_actor trigger in db/migrations/012_close_remaining.sql '
  'overwrites it with the caller on every insert under oro_api, because one '
  'admin could otherwise attribute their own action to somebody else. A row '
  'written by an operator or by a migration keeps whatever that writer '
  'supplied, because the trigger acts only for the application role, and is '
  'null only where the writer named nobody.';

COMMENT ON COLUMN payments.legacy_id IS
  'The id this row had in the legacy database, the same idea as '
  'members.legacy_id and cards.legacy_id: an import can be re-run without '
  'doubling every row, and an audit can trace a row back. Nothing writes it '
  'yet. tools/migration/020_migrate.sql carries members and cards only, and '
  'the staged legacy schema in tools/migration/fixtures/legacy-schema.sql '
  'holds no payments table to read.';

COMMENT ON COLUMN payments.created_at IS
  'When the row was written, which is not when the money arrived. That is '
  'paid_on. There is no updated_at column here and nothing like the '
  'set_updated_at trigger members and cards carry, and '
  'db/migrations/012_close_remaining.sql gives payments a select policy and '
  'an insert policy and no update policy, so under forced row level '
  'security an update through the API matches no rows at all.';

COMMENT ON COLUMN governance_parameters.key IS
  'The lookup name, written as a dotted path. Two exist, '
  'card_access.tenure_months and card_access.min_tier, seeded in '
  'db/seed/001_reference.sql. card_eligibility() in '
  'db/migrations/012_close_remaining.sql selects both by that exact '
  'literal, and with either one missing it reports that the card access '
  'rules are not configured and nobody is eligible. Renaming a key '
  'therefore switches a rule off rather than moving it. '
  'governance_parameter_history.key is a copy of this text with no foreign '
  'key behind it.';

COMMENT ON COLUMN governance_parameters.value IS
  'jsonb rather than text because a parameter is not always a number. The '
  'two readers in card_eligibility(), in '
  'db/migrations/012_close_remaining.sql, cast it straight back: the tenure '
  'is taken as an integer, and the minimum tier is taken as a string with '
  'the JSON quotes trimmed off. Both want a scalar, and they fail '
  'differently on anything else. An object or an array under '
  'card_access.tenure_months raises on the integer cast when somebody asks '
  'about eligibility, rather than when the value is written. The same value '
  'under card_access.min_tier raises nothing at all: it matches no '
  'tiers.id, and the tier check then refuses every member. The '
  'governance_change_is_recorded trigger watches this column alone.';

COMMENT ON COLUMN governance_parameters.unit IS
  'For the person reading the row. Nothing in the database, the API or the '
  'migration tooling reads it, so changing months to something else does '
  'not change how card_eligibility() treats the number. Null where the '
  'value is not a quantity: card_access.min_tier names a tier and has no '
  'unit, which is how db/seed/001_reference.sql seeds it.';

COMMENT ON COLUMN governance_parameters.effective IS
  'When the value quoted in source took effect. Nothing reads it. '
  'card_eligibility() applies whichever row is in the table, so a row dated '
  'in the future is in force today and backdating one changes no decision '
  'already made. The seeded card_access.tenure_months row holds 2025-05-22 '
  'under protest: db/seed/001_reference.sql marks it DATE UNCONFIRMED '
  'because two research passes disagree, the other candidate being '
  '2025-12-13. They agree the value is two months. Check the bylaws page '
  'history before anybody quotes the date.';

COMMENT ON COLUMN governance_parameters.updated_by IS
  'Who last changed the value, as a members.id, with the foreign key added '
  'at the foot of db/migrations/001_schema.sql. No trigger maintains it. '
  'record_governance_change() fills governance_parameter_history.changed_by '
  'and leaves this column untouched, so it holds whatever the writing '
  'statement put there and the two can disagree. Null on both seeded rows, '
  'because db/seed/001_reference.sql runs before any member exists. The '
  'history table does not settle it either: read the comment on '
  'governance_parameter_history.changed_by before treating either column as '
  'an answer.';

COMMENT ON COLUMN governance_parameters.updated_at IS
  'Defaulted at insert and never maintained afterwards. set_updated_at() is '
  'attached to members and cards only, so an UPDATE that does not name this '
  'column leaves it reading the moment the row was seeded, however many '
  'times the number has moved since. governance_parameter_history gets a '
  'row on every value change, from the trigger in '
  'db/migrations/012_close_remaining.sql, and its changed_at comes from '
  'that column''s own default.';

COMMENT ON COLUMN governance_parameter_history.id IS
  'Nothing references this. It earns its place as a tiebreak: changed_at '
  'comes from now(), which is the start of the transaction, so two '
  'parameters amended together share a timestamp and only this column puts '
  'them in order. A gap in the sequence means an update that rolled back. '
  'Sequences do not roll back, and the application role was never granted '
  'DELETE on any table in db/migrations/004_security.sql.';

COMMENT ON COLUMN governance_parameter_history.key IS
  'The parameter as it was named at the time, copied from the row being '
  'updated by record_governance_change(). No foreign key stands behind it. '
  'That is what keeps a record readable after somebody renames or removes a '
  'parameter, and it means a join back to governance_parameters can return '
  'nothing.';

COMMENT ON COLUMN governance_parameter_history.old_value IS
  'The value the parameter held before the change, copied straight from the '
  'row being updated. Never null on anything the trigger wrote, because '
  'governance_parameters.value is NOT NULL. Worth knowing what is absent: '
  'record_governance_change() is AFTER UPDATE only, so inserting a '
  'parameter records nothing here and the first value a key ever held lives '
  'in db/seed/001_reference.sql or in the migration that added it.';

COMMENT ON COLUMN governance_parameter_history.new_value IS
  'The value as it stood after the change. The '
  'governance_change_is_recorded trigger carries WHEN (OLD.value IS '
  'DISTINCT FROM NEW.value), so this never equals old_value and no row here '
  'records an update that moved nothing.';

COMMENT ON COLUMN governance_parameter_history.source IS
  'The citation as it read after the change, copied from the updated row '
  'rather than from the one it replaced. Because the trigger fires only on '
  'a value change, an admin who edits the number and leaves the old '
  'citation in place records that old citation against the new number, and '
  'nothing refuses it. Correcting a citation on its own writes no row here '
  'at all.';

COMMENT ON COLUMN governance_parameter_history.changed_by IS
  'Which member made the change, where the database can work that out. '
  'record_governance_change() reads current_member_id() only when '
  'current_user is oro_api, and that test cannot pass: the function is '
  'declared SECURITY DEFINER, so current_user inside it is the role that '
  'owns the function, which is the role that applied the migration and '
  'never the application role. HANDOFF.md section 7 records the same trap. '
  'Every row the trigger writes therefore carries a null here, whatever '
  'path the change came in by, so a null tells you nothing about who did '
  'it.';

COMMENT ON COLUMN governance_parameter_history.changed_at IS
  'Left to the default, because record_governance_change() does not pass '
  'it. now() is the start of the transaction rather than the instant of the '
  'statement, so amendments made together all read the same time and id '
  'breaks the tie. db/migrations/005_immutability.sql revokes UPDATE on '
  'this table from the application role and '
  'db/migrations/012_close_remaining.sql revokes INSERT, so nothing '
  'reachable by the API can move this value once it is written.';

-- ------------------------------------------------------ The migration ledger

COMMENT ON COLUMN schema_migrations.filename IS
  'The basename as applied, never a path, because db/tests/run.sh inserts '
  'the output of basename and records no directory. It is the primary key, '
  'so a second file of the same basename cannot be recorded even from '
  'elsewhere in the tree. Two absences to know about. 000_migrations.sql is '
  'skipped on purpose: it is the file that creates this table, and '
  'db/tests/run.sh chooses not to have the ledger record itself even though '
  'the table exists by the time it could. The second absence is the whole '
  'import path, since tools/migration/run.sh applies every migration for '
  'the import test while writing no rows here at all.';

COMMENT ON COLUMN schema_migrations.sha256 IS
  'The digest of the file at the moment it was applied, so a migration '
  'edited afterwards can be caught by comparing this against the file on '
  'disk. Nothing in the repository does that comparison yet. '
  'db/tests/run.sh computes it with shasum or sha256sum, whichever the '
  'machine has, and stores the first field of the output, which is the '
  'digest on its own.';

COMMENT ON COLUMN schema_migrations.applied_at IS
  'Defaulted, always. The INSERT in db/tests/run.sh names filename and '
  'sha256 and nothing else, so this is the clock at the moment the row was '
  'recorded, which is a separate statement from the one that ran the '
  'migration. Do not order the migrations by it. They apply in filename '
  'order, and a file applied out of that order, or a row written by hand '
  'long afterwards, sorts by when somebody wrote it down rather than by '
  'where it belongs in the sequence.';

COMMENT ON COLUMN schema_migrations.applied_by IS
  'Defaulted from current_user, so it records the role that ran the '
  'recording INSERT rather than a person. On a throwaway test database it '
  'always reads postgres, because db/tests/run.sh connects as that role, '
  'and the column only carries information where operators have roles of '
  'their own. It can never read oro_api: '
  'db/migrations/012_close_remaining.sql revokes every privilege on this '
  'table from the application role, and db/tests/write_policies.sql asserts '
  'that reading the table and forging a row both come back permission '
  'denied.';

COMMIT;
