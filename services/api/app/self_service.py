"""The four things a member reads about themselves that are not their record.

Cards, certifications, the waiver, and whether they may be nominated for card
access. Read app/members.py first: everything it says about the policies
deciding the answer holds here too, and this module is separate from it only
because rule 6 of CLAUDE.md puts a ceiling on a file.

Every query below is scoped to `current_member_id()`, and that is not a policy
written twice. The policy decides what this caller may read; the WHERE decides
which member the path is about, and they are different questions for two kinds
of caller. An admin holds `admin_reads_all_cards` in
db/migrations/004_security.sql, and an instructor holds
`instructor_reads_their_certifications` in 012_close_remaining.sql, so an
unscoped `SELECT ... FROM cards` under `/me/cards` would answer an admin with
the whole lab's cards. app/members.py scopes `/me` the same way.
"""

# right() rather than a mask applied after the row arrives, so the full tag
# number never leaves Postgres and no later change to this module can put it in
# a response. The contract says the last four characters, and a tag is 1 to 8
# uppercase hex characters by `tag_is_normalised_hex` in
# db/migrations/002_access.sql, so a short tag comes back whole and is still
# the last four characters of itself.
#
# controller_slot and permission_mask are absent on purpose. A slot is an
# EEPROM address on the door controller, finding 1 of
# docs/api/contract-review-notes.md, and the contract answers this path with
# MyCard rather than Card for exactly that reason.
OWN_CARDS = """
SELECT id, right(tag_number, 4) AS tag_number, label, active,
       issued_at, revoked_at, revoked_reason
  FROM cards
 WHERE member_id = current_member_id()
 ORDER BY issued_at DESC
"""

# A LEFT JOIN, so a certification row this caller cannot read does not take the
# member's own grant out of the list with it. What comes back then is a grant
# with no tool on it, which the contract allows: `id` is the only required
# property of a MemberCertification.
OWN_CERTIFICATIONS = """
SELECT held.id, held.member_id, held.certification_id, held.granted_at,
       held.expires_at, held.revoked_at, held.revoked_reason, held.note,
       tool.name AS tool_name, tool.description AS tool_description,
       tool.prerequisite_id, tool.validity_months, tool.active AS tool_active
  FROM member_certifications held
  LEFT JOIN certifications tool ON tool.id = held.certification_id
 WHERE held.member_id = current_member_id()
 ORDER BY held.granted_at DESC
"""

# The most recent one, which is what the contract answers with. Somebody can
# sign a waiver again when the old one expires, and both rows stay.
OWN_WAIVER = """
SELECT id, member_id, signed_at, expires_at, storage, reference, note,
       created_at
  FROM waivers
 WHERE member_id = current_member_id()
 ORDER BY signed_at DESC
 LIMIT 1
"""

# card_eligibility in db/migrations/012_close_remaining.sql is the one place
# that decides this. It reads the tenure and the minimum tier out of
# governance_parameters, so correcting a bylaws number is an admin editing a
# row. Nothing here re-decides any of it: the three values it returns are the
# three this service passes on.
CARD_ELIGIBILITY = """
SELECT eligible, eligible_on, reason
  FROM card_eligibility(current_member_id())
"""

# What happens after somebody is eligible. It is not in the database, and that
# is not an omission: card access is not a workflow in this system, on purpose,
# so there is no row to read it from. The sentence is the lab's, from the card
# access entry in docs/glossary.md, and it is the same one the contract's own
# example carries.
THE_NOMINATION_PROCESS = (
    "A current card member nominates you, posts the proposal publicly at "
    "least two weeks before Hack Your Hackerspace, and a majority of at least "
    "five card members present votes."
)


def read_own_cards(connection) -> list[dict]:
    return connection.execute(OWN_CARDS).fetchall()


def _member_certification(row: dict) -> dict:
    """One grant, with the tool it is on.

    granted_by and revoked_by are contract fields this cannot fill. Both are
    Member objects, and after db/migrations/011_close_read_holes.sql no policy
    lets one member read another member's row, so the instructor who signed
    somebody off cannot be named to them. Finding 3 of
    docs/api/contract-review-notes.md is the decision nobody has made yet, and
    it covers seven properties of which these are two.
    """
    held = {
        "id": row["id"],
        "member_id": row["member_id"],
        "certification_id": row["certification_id"],
        "granted_at": row["granted_at"],
        "expires_at": row["expires_at"],
        "revoked_at": row["revoked_at"],
        "revoked_reason": row["revoked_reason"],
        "note": row["note"],
    }
    if row["tool_name"] is not None:
        held["certification"] = {
            "id": row["certification_id"],
            "name": row["tool_name"],
            "description": row["tool_description"],
            "prerequisite_id": row["prerequisite_id"],
            "validity_months": row["validity_months"],
            "active": row["tool_active"],
        }
    return held


def read_own_certifications(connection) -> list[dict]:
    return [_member_certification(row)
            for row in connection.execute(OWN_CERTIFICATIONS).fetchall()]


def read_own_waiver(connection) -> dict | None:
    return connection.execute(OWN_WAIVER).fetchone()


def read_card_eligibility(connection) -> dict:
    """Where this member stands, and what happens next.

    The contract carried a `requirements` array here until 2026-08-30, one
    entry per rule with a `met` flag on each, and nothing could fill it. The
    function returns a boolean, a date and one sentence naming the first rule
    that failed, and it never reads `waivers` at all, so one of the four rules
    that array declared had no source anywhere. Building it here meant deciding
    eligibility a second time out of `governance_parameters`, which rule 5
    forbids. Finding 6 of docs/api/contract-review-notes.md is where that was
    found, and the contract now declares what this returns.
    """
    standing = connection.execute(CARD_ELIGIBILITY).fetchone()
    standing["process"] = THE_NOMINATION_PROCESS
    return standing
