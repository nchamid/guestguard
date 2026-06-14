"""Tool: get_signin_logs

Retrieves sign-in attempts for a B2B guest user — both successful sign-ins and
failures. Reads from mock_data/signin_logs.json. In production, this would call
the Microsoft Graph API endpoint: GET /auditLogs/signIns.

Important: This tool searches by email AND by display name. This is intentional
— in B2B guest scenarios, users sometimes attempt sign-in with a DIFFERENT email
than the one they were invited with. Catching those cross-identity attempts is
critical for diagnosis.
"""

import json
from pathlib import Path


MOCK_DATA_PATH = Path(__file__).parent.parent.parent / "mock_data" / "signin_logs.json"


def get_signin_logs(email: str, display_name: str = None) -> dict:
    """Retrieve sign-in attempts for a B2B guest user, including any cross-identity attempts.

    Use this tool to determine:
    - Whether the user has attempted to sign in at all
    - Whether sign-ins succeeded or failed, and why
    - Whether sign-in attempts came from the EXPECTED email or from a DIFFERENT identity
    - Which apps and IP addresses the user is attempting to access from

    If you suspect a wrong-identity scenario (invitation sent to email A, user signing in
    as email B), pass both arguments: the invited email AND the user's display name.
    The tool will return sign-ins matching either, exposing the mismatch.

    Args:
        email: The email address the user was invited with (or any email to look up).
        display_name: Optional. The user's display name (e.g., "Bob Martinez"). When
            provided, the tool also returns sign-ins from OTHER emails that match this
            display name — useful for catching wrong-identity sign-in attempts.

    Returns:
        A dict containing:
        - email: the email queried
        - directMatches: list of sign-ins where userPrincipalName equals the email
        - crossIdentityMatches: list of sign-ins from a DIFFERENT email but matching
            the display name (only populated if display_name argument was provided)
        - totalSignIns: total number of sign-ins returned
        - message: human-readable summary

    Sign-ins are sorted chronologically (oldest first).
    """
    try:
        with open(MOCK_DATA_PATH, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"error": "Mock data file not found", "path": str(MOCK_DATA_PATH)}
    except json.JSONDecodeError as e:
        return {"error": f"Mock data is not valid JSON: {e}"}

    email_lower = email.lower().strip()
    display_name_lower = display_name.lower().strip() if display_name else None

    direct_matches = []
    cross_identity_matches = []

    for signin in data.get("signIns", []):
        upn = signin.get("userPrincipalName", "").lower()
        signin_display = signin.get("userDisplayName", "").lower()

        if upn == email_lower:
            direct_matches.append(signin)
        elif display_name_lower and signin_display == display_name_lower and upn != email_lower:
            # Same person (display name), different email — cross-identity attempt
            cross_identity_matches.append(signin)

    # Sort each list chronologically
    direct_matches.sort(key=lambda s: s.get("createdDateTime", ""))
    cross_identity_matches.sort(key=lambda s: s.get("createdDateTime", ""))

    total = len(direct_matches) + len(cross_identity_matches)

    # Build a human-readable summary message
    if total == 0:
        message = f"No sign-in attempts found for {email}"
        if display_name:
            message += f" or for display name '{display_name}'"
    elif direct_matches and not cross_identity_matches:
        message = f"Found {len(direct_matches)} sign-in attempts under {email}"
    elif cross_identity_matches and not direct_matches:
        cross_emails = sorted(set(s["userPrincipalName"] for s in cross_identity_matches))
        message = (
            f"NO sign-ins found under {email}, but {len(cross_identity_matches)} "
            f"sign-ins found under different identities for display name "
            f"'{display_name}': {', '.join(cross_emails)}. This indicates the user "
            f"may be signing in with a different email than they were invited with."
        )
    else:
        message = (
            f"Found {len(direct_matches)} direct sign-ins under {email}, plus "
            f"{len(cross_identity_matches)} sign-ins under other identities matching "
            f"the same display name."
        )

    return {
        "email": email,
        "displayNameQueried": display_name,
        "totalSignIns": total,
        "directMatches": direct_matches,
        "crossIdentityMatches": cross_identity_matches,
        "message": message,
    }


if __name__ == "__main__":
    print("Test 1: Bob WITHOUT display_name (should find nothing under his invited email)")
    print(json.dumps(get_signin_logs("bob@personalemail.com"), indent=2))

    print("\nTest 2: Bob WITH display_name 'Bob Martinez' (should find sign-ins under bob@workco.com)")
    print(json.dumps(get_signin_logs("bob@personalemail.com", "Bob Martinez"), indent=2))

    print("\nTest 3: David (should find MFA-blocked sign-in attempts)")
    print(json.dumps(get_signin_logs("david@contoso.com"), indent=2))

    print("\nTest 4: Lisa (happy path, successful sign-ins)")
    print(json.dumps(get_signin_logs("lisa@partner.com"), indent=2))

    print("\nTest 5: Jane (typo scenario, no sign-ins at all)")
    print(json.dumps(get_signin_logs("jane.doe@partner.co", "Jane Doe"), indent=2))
