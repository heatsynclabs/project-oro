-- Carry the legacy members and cards across.
--
-- Runs only after 010_preflight.sql has passed, so everything here can assume
-- there is nothing left for a person to decide.
--
-- Members and cards only. Certifications, waivers, payments and door events are
-- phase 3 as well and are not written here, because nothing yet reads them and
-- rule 10 forbids shipping what does not exist.

-- Tiers, from the bands in the legacy application's own member_level_string.
-- app/models/user.rb in Open-Source-Access-Control-Web-Interface:
--   0 None, 1 Unable, 10 to 24 Volunteer, 25 to 49 Associate,
--   50 to 99 Basic, 100 to 999 Plus
-- Levels 2 to 9 fall through that case statement and have no name, so they get
-- no tier here either rather than being rounded into one.
INSERT INTO members (
  legacy_id, name, email, phone, postal_code,
  tier_id, legacy_member_level, joined_on,
  current_skills, desired_skills, marketing_source,
  emergency_name, emergency_phone, emergency_email,
  twitter_url, facebook_url, github_url, website_url,
  email_visible, phone_visible, listed_in_directory,
  oriented_at, created_at, updated_at)
SELECT
  u.id,
  u.name,
  -- Devise downcases before it stores, per config.case_insensitive_keys in
  -- config/initializers/devise.rb, and citext makes it moot on this side. A
  -- blank becomes NULL, because citext UNIQUE treats two blanks as a collision
  -- and NULL as absent.
  nullif(lower(btrim(u.email)), ''),
  nullif(btrim(u.phone), ''),
  nullif(btrim(u.postal_code), ''),
  CASE
    WHEN u.member_level IS NULL THEN NULL
    WHEN u.member_level = 0             THEN 'none'
    WHEN u.member_level = 1             THEN 'unable'
    WHEN u.member_level BETWEEN 10 AND 24  THEN 'volunteer'
    WHEN u.member_level BETWEEN 25 AND 49  THEN 'associate'
    WHEN u.member_level BETWEEN 50 AND 99  THEN 'basic'
    WHEN u.member_level BETWEEN 100 AND 999 THEN 'plus'
    ELSE NULL
  END,
  u.member_level,
  u.created_at::date,
  nullif(btrim(u.current_skills), ''),
  nullif(btrim(u.desired_skills), ''),
  nullif(btrim(u.marketing_source), ''),
  nullif(btrim(u.emergency_name), ''),
  nullif(btrim(u.emergency_phone), ''),
  nullif(lower(btrim(u.emergency_email)), ''),
  -- The new schema refuses a social link that is not http, and the legacy one
  -- validated the same way but allowed blanks through. Anything that would be
  -- refused is dropped rather than carried, and the count is reported below.
  CASE WHEN u.twitter_url  ~* '^https?://' THEN u.twitter_url  END,
  CASE WHEN u.facebook_url ~* '^https?://' THEN u.facebook_url END,
  CASE WHEN u.github_url   ~* '^https?://' THEN u.github_url   END,
  CASE WHEN u.website_url  ~* '^https?://' THEN u.website_url  END,
  coalesce(u.email_visible, false),
  coalesce(u.phone_visible, false),
  -- hidden is the legacy opt out of the directory.
  NOT coalesce(u.hidden, false),
  u.orientation,
  u.created_at,
  u.updated_at
FROM legacy.users u
ORDER BY u.id;

-- Cards. The slot is the legacy primary key and nothing else.
-- app/models/card.rb builds its request to the controller as "m#{self.id}",
-- so that integer is an EEPROM address. data-model.md section 6.2 calls keeping
-- it not negotiable.
INSERT INTO cards (
  legacy_id, member_id, tag_number, controller_slot,
  permission_mask, label, active, issued_at, created_at, updated_at)
SELECT
  c.id,
  m.id,
  -- Uppercase with no leading zeros, on both sides. The reconcile loop diffs
  -- what the controller returns against what the database holds, and a tag
  -- that differs only in case or padding rewrites every slot on every pass
  -- while reporting success. services/door/README.md.
  upper(regexp_replace(c.card_number, '^0+', '')),
  c.id,
  c.card_permissions,
  nullif(btrim(c.name), ''),
  -- The legacy schema has no way to say a card is revoked: no active column and
  -- no revoked_at. Every row it holds is a card the controller is told about,
  -- so every row arrives active. Anything else would be inventing a fact.
  true,
  c.created_at,
  c.created_at,
  c.updated_at
FROM legacy.cards c
JOIN members m ON m.legacy_id = c.user_id
ORDER BY c.id;
