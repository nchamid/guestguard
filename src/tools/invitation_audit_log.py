"""Tool: get_invitation_audit_log

Retrieves all audit events for a specific guest user — invitations, redemptions,
group assignments, MFA registration attempts, license assignments, and access attempts.
Reads from mock_data/audit_logs.json. In production, this would call the Microsoft Graph
API endpoint: GET /auditLogs/directoryAudits.
"""

import json
from pathlib import Path


MOCK_DATA_PATH = Path(__file__).parent.parent.parent / "mock_data" / "audit_logs.json"


def get_invitation_audit_log(email: str) -> dict:
    """Retrieve audit events for a B2B guest user across their entire provisioning lifecycle.

    Use this tool to understand WHAT HAPPENED with a guest user over time: when their
    invitation was sent, whether they redeemed it, whether they were added to groups,
    whether MFA registration succeeded or failed, and whether they hit access denial
    errors. This builds the timeline you need to diagnose multi-step failures.

    Args:
        email: The email address of the guest user. Returns events where this user
            is either the initiator or the target.

    Returns:
        A dict containing:
        - email: the email queried
        - eventCount: number of events found
        - events: list of audit event dicts, each containing:
            - id, activityDisplayName, activityDateTime
            - initiatedBy, targetEmail, result ("success" or "failure")
            - failureReason (if failure), details
        - message (if no events found)

    The events are returned in chronological order (oldest first) so you can reason
    about the timeline of what happened.
    """
    try:
        with open(MOCK_DATA_PATH, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"error": "Mock data file not found", "path": str(MOCK_DATA_PATH)}
    except json.JSONDecodeError as e:
        return {"error": f"Mock data is not valid JSON: {e}"}

    email_lower = email.lower().strip()
    matching_events = []

    for event in data.get("auditEvents", []):
        target = event.get("targetEmail", "").lower()
        initiator = event.get("initiatedBy", "").lower()
        if email_lower in (target, initiator):
            matching_events.append(event)

    # Sort by activityDateTime ascending (oldest first) for chronological reasoning
    matching_events.sort(key=lambda e: e.get("activityDateTime", ""))

    if not matching_events:
        return {
            "email": email,
            "eventCount": 0,
            "events": [],
            "message": "No audit events found for this email address",
        }

    return {
        "email": email,
        "eventCount": len(matching_events),
        "events": matching_events,
    }


if __name__ == "__main__":
    print("Test 1: Jane (typo scenario — should show only invitation event, no redemption)")
    print(json.dumps(get_invitation_audit_log("jane.doe@partner.co"), indent=2))

    print("\nTest 2: David (MFA scenario — should show invitation, redemption, group add, MFA failures)")
    print(json.dumps(get_invitation_audit_log("david@contoso.com"), indent=2))

    print("\nTest 3: Lisa (happy path — should show full successful lifecycle)")
    print(json.dumps(get_invitation_audit_log("lisa@partner.com"), indent=2))

    print("\nTest 4: Unknown user (should return no events)")
    print(json.dumps(get_invitation_audit_log("unknown@example.com"), indent=2))
