"""GuestGuard — Streamlit chat UI for the B2B guest user diagnostic agent.

Multi-turn chat interface wrapping the same agent logic as main.py.
Run with: streamlit run app.py
"""

import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from src.tools.guest_user_status import get_guest_user_status
from src.tools.invitation_audit_log import get_invitation_audit_log
from src.tools.signin_logs import get_signin_logs
from src.tools.troubleshooting_kb import query_troubleshooting_kb


# ─── Configuration ─────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")
PROJECT_ENDPOINT = os.getenv("PROJECT_ENDPOINT")
MODEL_DEPLOYMENT_NAME = os.getenv("MODEL_DEPLOYMENT_NAME")

SYSTEM_PROMPT = """You are GuestGuard, a diagnostic assistant for IT teams troubleshooting Microsoft Entra ID B2B guest user provisioning failures.

INTERACTION GUIDELINES:
- If the user greets you or asks what you can do, briefly explain your role and ask for a guest user email. Example: "I'm GuestGuard. I diagnose why B2B guest users can't access shared resources. Share a guest user email (and optionally their display name) and I'll investigate."
- If the user asks a general question about Microsoft Entra B2B that isn't about a specific guest user, briefly answer if you can ground it in the knowledge base (call query_troubleshooting_kb), then offer to diagnose a specific user.
- If the user asks a follow-up about a user you already diagnosed, use the conversation context. You can reference earlier evidence without re-calling tools unless new information is needed.
- If the user's input is unclear, ask for clarification (e.g., "Which guest user's email should I investigate?") rather than guessing.
- For actual diagnostic questions, follow the DIAGNOSTIC APPROACH and RESPONSE FORMAT below.

DIAGNOSTIC APPROACH — identify ROOT CAUSE, not symptom. You gather evidence with four tools, recognize failure patterns, and ground every recommendation in cited Microsoft documentation.

TOOLS:
1. get_guest_user_status(email) - ALWAYS CALL FIRST for diagnostic questions. Returns directory state and redemption status.
2. get_invitation_audit_log(email) - timeline of invitation, redemption, group adds, MFA attempts.
3. get_signin_logs(email, display_name) - sign-in attempts. PASS display_name when investigating whether the user might be signing in with a different identity than they were invited with.
4. query_troubleshooting_kb(symptom) - Microsoft documentation. MANDATORY for every diagnosis.

FAILURE PATTERNS (match the evidence to one of these):

Pattern A — INVITATION DELIVERY FAILURE (typo, wrong domain):
  Signals: invitation sent, never redeemed, ZERO sign-in attempts anywhere (even with display_name).
  Inference: User never received the invitation. Likely email typo or non-existent domain.
  Check the invited email closely: common typos include .co vs .com, missing letters, transposed characters.
  Remediation: Verify correct email with requester, revoke this invitation, reissue to corrected address.

Pattern B — WRONG IDENTITY SIGN-IN:
  Signals: invitation sent, never redeemed, BUT sign-ins exist under a different email matching the same display name.
  Inference: User received invitation but is signing in with the wrong identity.
  You MUST call get_signin_logs WITH display_name to detect this pattern.
  Remediation: Either ask user to sign in with the invited email, or revoke and reissue invitation to the email they actually use.

Pattern C — REDEEMED BUT NO RESOURCE ACCESS (missing group or license):
  Signals: invitation redeemed, sign-ins successful, but user still denied access. Audit log shows access denial events.
  Inference: Provisioning succeeded but downstream group/license assignment did not complete.
  Remediation: Manually assign required groups or licenses.

Pattern D — MFA REGISTRATION BLOCKED:
  Signals: redemption successful, but sign-ins failing with MFA error codes (50158, etc.).
  Common cause: User provided a landline number; MFA requires mobile.
  Remediation: Have user retry with mobile, or configure alternative MFA method.

Pattern E — IDENTITY PROVIDER NOT CONFIGURED:
  Signals: invitation sent, redemption ATTEMPTED and FAILED, user email is from external identity (e.g., Gmail).
  Inference: Tenant does not trust the user identity provider, and email one-time passcode is not enabled as fallback.
  Remediation: Configure federation for that identity provider, or enable email one-time passcode.

REASONING DISCIPLINE:
- "Invitation is pending" is a SYMPTOM. The root cause is WHY it is still pending. Always look one level deeper.
- If you see no redemption AND no sign-in attempts AND no cross-identity sign-ins, that strongly suggests Pattern A (delivery failure), not Pattern B (wrong identity).
- Always call get_signin_logs WITH display_name when redemption is pending.
- Cross-reference all relevant tools before concluding.

KNOWLEDGE BASE USE — STRICT RULES:
- You MUST call query_troubleshooting_kb at least once before producing any diagnosis. This is non-negotiable.
- After the KB returns results, the Source line in your response MUST cite a filename that ACTUALLY APPEARS in the results.
- Indexed source files all end in .pdf. Valid examples: 01-troubleshoot-b2b.pdf, 02-google-federation.pdf, 03-one-time-passcode.pdf, 04-guest-user-properties.pdf, 05-add-b2b-users.pdf, 06-signin-log-details.pdf, 07-audit-logs.pdf.
- NEVER invent or paraphrase a filename.
- If no KB result is relevant, write "Source: No directly relevant Microsoft documentation found in knowledge base" instead of inventing one.

RESPONSE FORMAT for diagnoses (use exactly this structure):

**Diagnosis:** [Root cause in one sentence — the WHY, not just the WHAT.]

**Evidence:**
- [Bullets showing how each tool result contributed to your conclusion]

**Recommended Remediation:**
[Numbered steps the IT admin can take]

**Source:** [Exact .pdf filename from your query_troubleshooting_kb results]

IMPORTANT:
- If get_guest_user_status returns "found: false", say so clearly. Do not invent scenarios for non-existent users.
- For non-diagnostic conversational turns (greetings, capability questions, follow-ups), respond naturally without the rigid format.
- Be concise.
"""


TOOL_REGISTRY = {
    "get_guest_user_status": get_guest_user_status,
    "get_invitation_audit_log": get_invitation_audit_log,
    "get_signin_logs": get_signin_logs,
    "query_troubleshooting_kb": query_troubleshooting_kb,
}

CUSTOM_TOOLS = [
    {
        "type": "function",
        "name": "get_guest_user_status",
        "description": "Retrieve the directory presence and invitation redemption state of a B2B guest user. Use this FIRST when diagnosing any guest user issue.",
        "parameters": {
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address of the guest user"}},
            "required": ["email"],
        },
    },
    {
        "type": "function",
        "name": "get_invitation_audit_log",
        "description": "Retrieve audit events for a B2B guest user (invitations, redemptions, group adds, MFA attempts) in chronological order.",
        "parameters": {
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address of the guest user"}},
            "required": ["email"],
        },
    },
    {
        "type": "function",
        "name": "get_signin_logs",
        "description": "Retrieve sign-in attempts for a guest user. Pass both email AND display_name when you suspect a wrong-identity scenario.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Email address the user was invited with"},
                "display_name": {"type": "string", "description": "Optional. User's display name. When provided, returns sign-ins from OTHER emails matching this name."},
            },
            "required": ["email"],
        },
    },
    {
        "type": "function",
        "name": "query_troubleshooting_kb",
        "description": "Search authoritative Microsoft documentation for guidance on a B2B troubleshooting symptom. Use AFTER gathering evidence.",
        "parameters": {
            "type": "object",
            "properties": {
                "symptom": {"type": "string", "description": "Natural-language description of the problem"},
                "top_results": {"type": "integer", "description": "Number of passages to return (default 3, max 5)"},
            },
            "required": ["symptom"],
        },
    },
]


# ─── Cached Foundry client ─────────────────────────────────────────────────────
@st.cache_resource
def get_openai_client():
    credential = DefaultAzureCredential(
        exclude_environment_credential=True,
        exclude_managed_identity_credential=True,
    )
    project_client = AIProjectClient(credential=credential, endpoint=PROJECT_ENDPOINT)
    return project_client.get_openai_client()


def execute_tool_call(tool_name: str, arguments: dict) -> str:
    if tool_name not in TOOL_REGISTRY:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = TOOL_REGISTRY[tool_name](**arguments)
        return json.dumps(result)
    except TypeError as e:
        return json.dumps({"error": f"Invalid arguments for {tool_name}: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Tool {tool_name} failed: {e}"})


def run_agent_turn(user_input: str, conversation_id: str, trace_container):
    """Run one agent turn. Display traces in real time and return (response_text, traces_list)."""
    openai_client = get_openai_client()

    openai_client.conversations.items.create(
        conversation_id=conversation_id,
        items=[{"type": "message", "role": "user", "content": user_input}],
    )

    captured_traces = []
    final_response = None

    for iteration in range(10):
        response = openai_client.responses.create(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=SYSTEM_PROMPT,
            conversation=conversation_id,
            input="",
            tools=CUSTOM_TOOLS,
        )

        tool_calls = []
        if hasattr(response, "output") and response.output:
            for item in response.output:
                if hasattr(item, "type") and item.type == "function_call":
                    tool_calls.append(item)

        if not tool_calls:
            final_response = response.output_text or ""
            break

        for call in tool_calls:
            tool_name = call.name
            try:
                args = json.loads(call.arguments) if isinstance(call.arguments, str) else call.arguments
            except json.JSONDecodeError:
                args = {}

            arg_summary = ", ".join(f"{k}={v!r}" for k, v in args.items())
            trace_line = f"🔧 **`{tool_name}`**({arg_summary})"
            captured_traces.append(trace_line)

            with trace_container:
                st.markdown(trace_line)

            result = execute_tool_call(tool_name, args)
            openai_client.conversations.items.create(
                conversation_id=conversation_id,
                items=[{
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": result,
                }],
            )

    return final_response, captured_traces


# ─── Session state initialization ──────────────────────────────────────────────
def init_session_state():
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "conversation_id" not in st.session_state:
        client = get_openai_client()
        conv = client.conversations.create(items=[])
        st.session_state["conversation_id"] = conv.id
    if "pending_input" not in st.session_state:
        st.session_state["pending_input"] = None


def load_scenario(question: str):
    """Sidebar button callback — inject question into chat as user input."""
    st.session_state["pending_input"] = question


def reset_chat():
    """Start a fresh conversation."""
    client = get_openai_client()
    conv = client.conversations.create(items=[])
    st.session_state["conversation_id"] = conv.id
    st.session_state["messages"] = []
    st.session_state["pending_input"] = None


# ─── UI ────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GuestGuard — B2B Guest User Diagnostic Agent",
    page_icon="🛡️",
    layout="wide",
)

if not PROJECT_ENDPOINT or not MODEL_DEPLOYMENT_NAME:
    st.error("Missing required environment variables. Check `.env` for PROJECT_ENDPOINT and MODEL_DEPLOYMENT_NAME.")
    st.stop()

init_session_state()

with st.sidebar:
    st.markdown("## 🛡️ GuestGuard")
    st.markdown("Diagnoses B2B guest user provisioning failures using Microsoft Foundry and Foundry IQ.")
    st.markdown("---")

    st.markdown("### Try a scenario")
    st.caption("Click to inject the question into the chat.")

    scenarios = [
        ("Domain typo", "Why can't jane.doe@partner.co access SharePoint? The user's name is Jane Doe."),
        ("Wrong identity sign-in", "Why can't bob@personalemail.com access SharePoint? The user's name is Bob Martinez."),
        ("Google identity (no federation)", "Why can't mike@gmail.com access SharePoint?"),
        ("MFA landline failure", "Why can't david@contoso.com access Teams?"),
        ("Missing license", "Why can't sarah@vendor.com access SharePoint?"),
        ("No group membership", "Why can't alice@partner.com access SharePoint?"),
        ("Happy path (no issues)", "Why can't lisa@partner.com access SharePoint?"),
        ("Unknown user", "Why can't unknown@example.com access SharePoint?"),
    ]

    for label, question in scenarios:
        st.button(
            label,
            key=f"btn_{label}",
            on_click=load_scenario,
            args=(question,),
            use_container_width=True,
        )

    st.markdown("---")
    st.button("🔄 Reset chat", on_click=reset_chat, use_container_width=True)

    st.markdown("---")
    st.markdown("### About this demo")
    st.markdown(
        "The scenario buttons above use **mock data** representing realistic B2B failure modes. "
        "Custom emails will return *'user not found'* — that's the agent honestly reporting it has no record, "
        "not a bug. In production, the tools would query Microsoft Graph API live against your tenant. "
        "The Foundry IQ knowledge base is real and queried live."
    )
    st.markdown(
        "Built for the [Microsoft Agents League Hackathon](https://innovationstudio.microsoft.com/hackathons/Agents-League-Hackathon) — Reasoning Agents track."
    )

# Main panel
st.markdown("# 🛡️ GuestGuard")
st.markdown(
    "**A reasoning agent that diagnoses why a B2B guest user can't access shared resources, "
    "grounded in cited Microsoft documentation.**"
)
st.markdown("---")

# ─── Display chat history ──────────────────────────────────────────────────────
for i, msg in enumerate(st.session_state["messages"]):
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(msg["content"])
    elif msg["role"] == "assistant":
        # If there were tool calls, show them in a collapsed expander above the response
        if msg.get("traces"):
            with st.expander(f"🔍 Investigation steps ({len(msg['traces'])} tool calls)", expanded=False):
                for trace in msg["traces"]:
                    st.markdown(trace)
        with st.chat_message("assistant"):
            if msg.get("content"):
                st.markdown(msg["content"])
    # Visual separator between Q&A pairs (after each assistant response, except the last)
    if msg["role"] == "assistant" and i < len(st.session_state["messages"]) - 1:
        st.divider()

# Welcome message if chat is empty
if not st.session_state["messages"]:
    with st.chat_message("assistant"):
        st.markdown(
            "👋 Hi! I'm **GuestGuard**, a diagnostic agent for Microsoft Entra ID B2B guest user "
            "provisioning failures. \n\nShare a guest user's email (and optionally their display name) "
            "and I'll investigate why they can't access shared resources. You can also click a "
            "**scenario button in the sidebar** to try a pre-loaded example."
        )

# ─── Handle new input ──────────────────────────────────────────────────────────
user_input = st.chat_input("Ask about a guest user...")
if not user_input and st.session_state["pending_input"]:
    user_input = st.session_state["pending_input"]
    st.session_state["pending_input"] = None

if user_input:
    # Display user message immediately in this run
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Show the agent's work in an st.status — visually distinct from chat bubbles
    response_text = None
    traces = []
    with st.status("🔍 Investigating...", expanded=True) as status:
        try:
            response_text, traces = run_agent_turn(
                user_input,
                st.session_state["conversation_id"],
                status,
            )
            tool_count = len(traces)
            status.update(
                label=f"✅ Investigation complete · {tool_count} tool call{'s' if tool_count != 1 else ''}",
                state="complete",
                expanded=False,
            )
        except Exception as e:
            status.update(label=f"❌ Error: {e}", state="error")

    # Display final response in proper assistant chat bubble
    if response_text:
        with st.chat_message("assistant"):
            st.markdown(response_text)

    # Store assistant turn in history
    st.session_state["messages"].append({
        "role": "assistant",
        "content": response_text or "(no response)",
        "traces": traces or [],
    })

    # Rerun to clean up the live st.status (so history loop takes over with expander)
    st.rerun()
