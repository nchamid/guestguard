"""Tool: get_guest_user_status

Retrieves a guest user's directory presence and invitation redemption state.
Reads from mock_data/guest_users.json. In production, this would call the
Microsoft Graph API endpoint: GET /users/{email}.
"""

import json
from pathlib import Path
from typing import Optional


# Path to mock data, relative to project root
MOCK_DATA_PATH = Path(__file__).parent.parent.parent / "mock_data" / "guest_users.json"


def get_guest_user_status(email: str) -> dict:
    """Retrieve the directory presence and invitation redemption state of a B2B guest user.

    Use this tool FIRST whenever diagnosing a guest user issue. It tells you whether
    the user exists in the directory, whether their invitation was redeemed, which
    identity provider they used, what groups they belong to, and what licenses are
    assigned.

    Args:
        email: The email address of the guest user to look up. Should be the email
            the invitation was sent to (e.g., "jane.doe@partner.com").

    Returns:
        A dict containing the user's directory record if found, including:
        - email, displayName, userType
        - invitationStatus ("Accepted" or "PendingAcceptance")
        - redeemed (bool), redeemedDateTime
        - identityProvider (e.g., "ExternalAzureAD", "Google", or null if not redeemed)
        - memberOf (list of group names)
        - assignedLicenses, requiredLicenses
        - Optional fields like mfaRegistered, lastRedemptionAttempt

        If the user is not found, returns:
        {"found": false, "email": <email>, "message": "No guest user found with this email"}
    """
    try:
        with open(MOCK_DATA_PATH, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {
            "error": "Mock data file not found",
            "path": str(MOCK_DATA_PATH),
        }
    except json.JSONDecodeError as e:
        return {"error": f"Mock data is not valid JSON: {e}"}

    # Search for user by email (case-insensitive)
    email_lower = email.lower().strip()
    for user in data.get("users", []):
        if user.get("email", "").lower() == email_lower:
            return {"found": True, **user}

    return {
        "found": False,
        "email": email,
        "message": "No guest user found with this email address in the directory",
    }


if __name__ == "__main__":
    # Quick manual test — run this file directly: python src/tools/guest_user_status.py
    print("Test 1: existing user (jane.doe@partner.co)")
    print(json.dumps(get_guest_user_status("jane.doe@partner.co"), indent=2))

    print("\nTest 2: existing user (lisa@partner.com)")
    print(json.dumps(get_guest_user_status("lisa@partner.com"), indent=2))

    print("\nTest 3: unknown user (unknown@example.com)")
    print(json.dumps(get_guest_user_status("unknown@example.com"), indent=2))