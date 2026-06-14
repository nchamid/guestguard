# GuestGuard

> **A reasoning agent that diagnoses Microsoft Entra ID B2B guest user provisioning failures, grounded in cited Microsoft documentation via Foundry IQ.**

Built for the [Microsoft Agents League Hackathon](https://innovationstudio.microsoft.com/hackathons/Agents-League-Hackathon) — Reasoning Agents track.

---

## The problem

When a business stakeholder reports *"I invited a guest user but they can't access the site,"* IT teams have to manually piece together what went wrong by checking three different places in Microsoft Entra ID:

- The guest user's directory record and redemption state
- The invitation audit log (was it created? redeemed? did group assignment succeed?)
- The sign-in logs (did they try to sign in? with which identity? what failed?)

The failure modes look identical from the outside but require very different fixes:

- A typo in the invitation email — *user never received it*
- A user signing in with the wrong identity — *invitation was sent but redeemed under a different email*
- Successful redemption but missing group membership — *user can sign in but has no permissions*
- MFA registration blocked by a landline phone number
- A non-Microsoft identity (Gmail) with no federation configured
- A guest user missing the required SharePoint license

This diagnostic work falls on IT every time. Business users get no visibility. The process is repetitive, time-consuming, and well-defined enough that it shouldn't require a human pulling logs.

## What GuestGuard does

GuestGuard is a reasoning agent built on **Microsoft Foundry** that takes a guest user's email and returns a diagnosis: what went wrong, why, and how to fix it. It does this by correlating evidence across multiple sources and grounding every remediation recommendation in cited Microsoft Learn documentation via **Foundry IQ**.

### Example interaction

```
You: Why can't bob@personalemail.com access SharePoint? His name is Bob Martinez.

  [calling get_guest_user_status({'email': 'bob@personalemail.com'})]
  [calling get_invitation_audit_log({'email': 'bob@personalemail.com'})]
  [calling get_signin_logs({'email': 'bob@personalemail.com', 'display_name': 'Bob Martinez'})]
  [calling query_troubleshooting_kb({'symptom': 'B2B guest signing in with different identity than invited'})]

GuestGuard:
**Diagnosis:** Bob Martinez was invited as bob@personalemail.com but is attempting
to access SharePoint by signing in with bob@workco.com, which is not associated
with the guest account in the tenant.

**Evidence:**
- get_guest_user_status shows invitation pending acceptance for bob@personalemail.com.
- get_signin_logs found no sign-ins under the invited email, but 3 failed sign-in
  attempts by bob@workco.com matching the display name Bob Martinez.
- KB documents confirm this pattern points to wrong-identity sign-in.

**Recommended Remediation:**
1. Inform Bob to sign in with the invited email address bob@personalemail.com.
2. If Bob prefers to use bob@workco.com, revoke the existing invitation and
   reissue it to bob@workco.com.
3. Verify the correct identity provider is configured for the alternate email.

**Source:** 01-troubleshoot-b2b.pdf
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Python CLI (main.py) — interactive conversation loop            │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  Microsoft Foundry — gpt-4.1-mini (Global Standard deployment)   │
│  System prompt: 6 failure-mode patterns, reasoning discipline    │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (decides which tools to call)
┌──────────────────────────────────────────────────────────────────┐
│  4 custom Python tools (executed locally, results fed back)      │
├──────────────────────────────────────────────────────────────────┤
│  • get_guest_user_status(email)                                  │
│      → reads mock_data/guest_users.json                          │
│  • get_invitation_audit_log(email)                               │
│      → reads mock_data/audit_logs.json                           │
│  • get_signin_logs(email, display_name)                          │
│      → reads mock_data/signin_logs.json                          │
│      → smart cross-identity matching when display_name provided  │
│  • query_troubleshooting_kb(symptom)                             │
│      → Azure AI Search REST API → Foundry IQ knowledge base      │
└──────────────────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
                                ┌──────────────────────────────────┐
                                │  Foundry IQ knowledge base       │
                                │  7 indexed Microsoft Learn PDFs  │
                                │  on B2B guest user troubleshoot. │
                                └──────────────────────────────────┘
```

The agent runs a classic **ReAct (Reason + Act) loop**: it decides which tool to call based on the current evidence, executes the tool, observes the result, and decides what to do next. The loop continues until the agent has enough evidence to produce a grounded diagnosis.

## Failure scenarios covered

The agent diagnoses six realistic B2B guest user provisioning failures plus the happy path and unknown-user cases:

| # | Scenario | Example user | Root cause | KB grounding |
|---|----------|--------------|------------|--------------|
| 1 | Domain typo in invitation | `jane.doe@partner.co` | Invitation sent to invalid domain; user never received it | `04-guest-user-properties.pdf` |
| 2 | Wrong identity sign-in | `bob@personalemail.com` | Invited at one email, signing in with another | `01-troubleshoot-b2b.pdf` |
| 3 | Non-Microsoft identity | `mike@gmail.com` | Google IdP not configured; OTP fallback not enabled | `03-one-time-passcode.pdf` |
| 4 | MFA registration failure | `david@contoso.com` | User provided landline; mobile required for SMS/authenticator | `06-signin-log-details.pdf` |
| 5 | Missing required license | `sarah@vendor.com` | Redeemed and grouped but no SharePoint license assigned | `01-troubleshoot-b2b.pdf` |
| 6 | No group membership | `alice@partner.com` | Redeemed successfully but post-redemption group add did not run | `04-guest-user-properties.pdf` |
| — | Happy path | `lisa@partner.com` | No issue — agent correctly identifies that user is fully provisioned | (none needed) |
| — | Unknown user | `unknown@example.com` | User not in directory; agent declines to fabricate scenarios | (honestly returns "no relevant doc") |

## Microsoft IQ integration

**Foundry IQ** is the grounding layer for every diagnosis. Seven official Microsoft Learn pages on B2B guest user troubleshooting are indexed into the knowledge base:

| File | Source |
|------|--------|
| `01-troubleshoot-b2b.pdf` | [Troubleshoot B2B issues](https://learn.microsoft.com/en-us/entra/external-id/troubleshoot) |
| `02-google-federation.pdf` | [Add Google as identity provider](https://learn.microsoft.com/en-us/entra/external-id/google-federation) |
| `03-one-time-passcode.pdf` | [Email one-time passcode](https://learn.microsoft.com/en-us/entra/external-id/one-time-passcode) |
| `04-guest-user-properties.pdf` | [B2B guest user properties](https://learn.microsoft.com/en-us/entra/external-id/user-properties) |
| `05-add-b2b-users.pdf` | [Add B2B collaboration users](https://learn.microsoft.com/en-us/entra/external-id/add-users-administrator) |
| `06-signin-log-details.pdf` | [Sign-in log activity details](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/concept-sign-in-log-activity-details) |
| `07-audit-logs.pdf` | [Microsoft Entra audit logs](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/concept-audit-logs) |

After the agent forms a hypothesis from its diagnostic tools, it queries the knowledge base with a description of the specific failure pattern. The KB returns ranked passages from the indexed PDFs. The agent then cites the most relevant source filename in its response — so every remediation step the IT admin sees is backed by an authoritative Microsoft Learn document.

This directly addresses the most common LLM failure mode in technical advice: **confidently wrong recommendations with no traceable source.**

## Tech stack

- **Microsoft Foundry** — agent platform, project, model hosting (gpt-4.1-mini Global Standard)
- **Foundry IQ** — knowledge retrieval over indexed Microsoft documentation
- **Azure AI Search** — underlying vector + keyword search backing Foundry IQ
- **Python 3.12** with:
  - `azure-ai-projects` — Foundry project client
  - `azure-identity` — authentication via `DefaultAzureCredential`
  - `requests` — direct REST calls to Azure AI Search
  - `python-dotenv` — environment configuration

## Demo data

For this hackathon submission, the three diagnostic tools (`get_guest_user_status`, `get_invitation_audit_log`, `get_signin_logs`) read from mock JSON files representing realistic guest user scenarios. In a production deployment, these tools would call the Microsoft Graph API endpoints (`users`, `auditLogs/directoryAudits`, `auditLogs/signIns`) against the customer's tenant with appropriate read permissions.

The mock data approach lets the agent's reasoning be demonstrated end-to-end without requiring judges to provision tenant access. The agent's behavior is identical — the tool functions simply swap their data source.

The Foundry IQ knowledge base, by contrast, is **real** — it indexes actual Microsoft Learn pages and is queried live via the Azure AI Search REST API.

## How to run

### Prerequisites

- Python 3.12+
- An Azure subscription
- A Microsoft Foundry project with:
  - A deployed chat model (e.g., `gpt-4.1-mini`)
  - A Foundry IQ resource with a knowledge base of B2B troubleshooting docs indexed
- `az login` completed in your terminal

### Setup

```bash
# Clone the repo
git clone https://github.com/<your-username>/guestguard.git
cd guestguard

# Create a Python virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your Foundry endpoint, search endpoint, and search API key
```

### Run

```bash
python main.py
```

You'll see a prompt:

```
You:
```

Try any of the scenarios from the table above. Example:

```
You: Why can't bob@personalemail.com access SharePoint? His name is Bob Martinez.
```

The agent will call tools (visible as `[calling toolname(args)]` in the output), correlate evidence, query the knowledge base, and respond with a structured diagnosis. Type `quit` to exit.

## What I'd build with more time

- **Wire tools to live Microsoft Graph API** with proper OAuth and tenant authorization
- **Expand failure-mode coverage** — conditional access blocks, B2B direct connect failures, federated identity claim mismatches
- **Remediation execution mode** — with human approval, let the agent apply the fix (assign group, reissue invitation, etc.) directly rather than only recommending
- **Web frontend (Streamlit or React)** — currently CLI only; a web UI would let business stakeholders self-diagnose without IT pulling logs
- **Slack / Teams integration** — paste a user email into a slash command, get the diagnosis posted back in thread
- **Persistent ticket integration** — log every diagnosis to a ticket system so IT has an audit trail of agent-assisted resolutions

## Project background

Built solo by [Nagarjuna Chamidisetty](https://nagarjunac.dev), a senior Microsoft 365 / Azure engineer who has manually triaged guest user provisioning failures at a global organization for years. The diagnostic pattern is well-defined enough that an agent should be able to absorb it. This project demonstrates that the answer is yes.

## Acknowledgments

GuestGuard was built with AI-assisted development. Claude (Anthropic) was used as a coding pair throughout the build — for Python implementation, debugging, and documentation — while project design, architecture decisions, scenario selection, infrastructure setup, and all testing were owned by the author.

## License

MIT
