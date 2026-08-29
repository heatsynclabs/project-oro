"""Reading members. Every query here runs under the caller's own policies.

Nothing in this module filters by who is asking. It cannot: the service
connects as oro_api, which is not a superuser, owns no table and carries no
BYPASSRLS, so db/migrations/004_security.sql and 011_close_read_holes.sql
decide what comes back. A member reading the directory and an admin reading it
run the same SQL.

The directory is read through member_directory and never through the members
table. Row level security filters rows and not columns, so hiding an email
address a member chose not to publish is the view's job, and reaching around it
would publish every listed member's postal code and standing.
"""

# Everything the contract's Member object carries that lives on the members
# table. The identity subject, the legacy columns and deleted_at are left out
# deliberately: the contract says no client has a use for them.
#
# oriented_by is left out too, and that one is a gap rather than a decision.
# The contract types it as a Member object, and after 011_close_read_holes.sql
# dropped member_reads_directory there is no policy under which one member may
# read another member's row, so this service cannot fill in that person's name.
OWN_MEMBER = """
SELECT id, name, display_name, pronouns, email, email_verified_at, phone,
       postal_code, tier_id, joined_on, paid_through, standing, oriented_at,
       current_skills, desired_skills, marketing_source,
       emergency_name, emergency_phone, emergency_email,
       twitter_url, facebook_url, github_url, website_url,
       email_visible, phone_visible, listed_in_directory,
       created_at, updated_at
  FROM members
 WHERE id = current_member_id()
"""

OWN_ROLES = """
SELECT grant_row.id, grant_row.role_id, grant_row.granted_at,
       grant_row.approval_id, grant_row.expires_at,
       role.name AS role_name, role.description AS role_description,
       role.grants_roles
  FROM member_roles grant_row
  JOIN roles role ON role.id = grant_row.role_id
 WHERE grant_row.member_id = current_member_id()
   AND grant_row.revoked_at IS NULL
 ORDER BY grant_row.granted_at
"""

TIER = """
SELECT id, name, monthly_cents, sort_order, card_eligible, storage, active
  FROM tiers
 WHERE id = %s
"""

DIRECTORY = """
SELECT id, name, pronouns, email, phone, current_skills, desired_skills,
       joined_on
  FROM member_directory
 ORDER BY name
"""

# id::text rather than a cast of the parameter, so an id that is not a uuid at
# all matches nothing instead of raising a type error the caller would see as a
# fault of the server's. Whether the person exists and is unlisted or does not
# exist is not distinguished, which is what the contract's 404 says.
DIRECTORY_MEMBER = """
SELECT id, name, pronouns, email, phone, current_skills, desired_skills,
       joined_on
  FROM member_directory
 WHERE id::text = %s
"""

DIRECTORY_FIELDS = frozenset(
    ["id", "name", "pronouns", "email", "phone", "current_skills",
     "desired_skills", "joined_on"]
)


def _role_grant(row: dict) -> dict:
    """One RoleGrant, with the Role it names embedded.

    granted_by and revoked_by are contract fields this cannot fill: both are
    Member objects and no policy lets one member read another's row. Only live
    grants are returned, per the contract's "the member's live roles", so
    revoked_at and revoked_reason are absent rather than null.
    """
    return {
        "id": row["id"],
        "role_id": row["role_id"],
        "role": {
            "id": row["role_id"],
            "name": row["role_name"],
            "description": row["role_description"],
            "grants_roles": row["grants_roles"],
        },
        "granted_at": row["granted_at"],
        "approval_id": row["approval_id"],
        "expires_at": row["expires_at"],
    }


def read_own_member(connection) -> dict | None:
    """The caller's own member record, with their tier and their live roles."""
    member = connection.execute(OWN_MEMBER).fetchone()
    if member is None:
        return None
    member["roles"] = [
        _role_grant(row) for row in connection.execute(OWN_ROLES).fetchall()
    ]
    if member["tier_id"] is not None:
        member["tier"] = connection.execute(TIER, (member["tier_id"],)).fetchone()
    return member


def read_directory(connection) -> list[dict]:
    return connection.execute(DIRECTORY).fetchall()


def read_directory_member(connection, member_id: str) -> dict | None:
    return connection.execute(DIRECTORY_MEMBER, (member_id,)).fetchone()


def chosen_fields(fields: str | None) -> tuple[list[str], list[str]]:
    """What `?fields=` asked for, and the names the directory has no answer for.

    `id` is always kept. The contract makes it the one required property of a
    Member, so a response that dropped it would not be one.

    The contract types this parameter as a bare string and does not say what
    happens when it names a field the directory does not carry. It carries
    eight columns and the Member object declares about thirty, so
    `fields=emergency_phone` is a legal request with no answer. This service
    names the field back rather than returning something else quietly, and
    docs/api/contract-review-notes.md finding 2 is the same gap seen from the
    contract's side.
    """
    if fields is None:
        return list(DIRECTORY_FIELDS), []
    asked = [name.strip() for name in fields.split(",") if name.strip()]
    unknown = [name for name in asked if name not in DIRECTORY_FIELDS]
    return ["id"] + [name for name in asked if name != "id"], unknown


def keep_fields(row: dict, wanted: list[str]) -> dict:
    return {name: row[name] for name in wanted if name in row}
