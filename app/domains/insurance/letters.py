"""Acknowledgement letter templates. Shared by the seed (historic letters) and the router (new drafts).
Letters carry claim facts only; they never include national IDs, bank details or health information."""
from datetime import date

from app.domains.insurance.reference import (
    DOCUMENTS_BY_LOSS,
    FIRST_CONTACT_COMMITMENT,
    LOSS_TYPES,
    QUEUE_BY_CODE,
)

CLAIMS_LINE = "1-800-555-0199"

LOSS_LABEL = {
    "collision": "auto collision", "glass": "auto glass", "theft": "theft", "water_damage": "water damage",
    "fire": "fire damage", "wind_hail": "wind and hail damage", "liability": "liability", "bodily_injury": "injury",
    "travel_medical": "travel medical", "trip_cancellation": "trip cancellation",
}


ESTIMATE_KINDS = {"repair_estimate", "contractor_estimate", "invoice"}
DOC_KIND_HINTS = [("photo", {"photo"}), ("estimate", ESTIMATE_KINDS), ("quote", ESTIMATE_KINDS), ("invoice", ESTIMATE_KINDS),
                  ("police report", {"police_report"}),
                  ("fire department", {"fire_report"}), ("medical bill", {"medical_bill"}), ("booking", {"booking_receipt"}),
                  ("list of stolen", {"inventory_list"}), ("list of damaged", {"inventory_list"})]


def _doc_kinds(label: str) -> set[str]:
    low = label.lower()
    return set().union(*[kinds for hint, kinds in DOC_KIND_HINTS if hint in low])


def _fmt(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def render_ack(template_code: str, *, claim: dict, holder: dict, policy_number: str, handler_name: str | None,
               cat_name: str | None = None, extra_documents: list[str] | None = None, note: str | None = None,
               channel: str = "email", received_kinds: set[str] | None = None) -> tuple[str | None, str]:
    """Return (subject, body) for an acknowledgement."""
    queue = QUEUE_BY_CODE[claim["queue"]]
    commitment = FIRST_CONTACT_COMMITMENT[claim["queue"]]
    loss_label = LOSS_LABEL.get(claim["loss_type"], LOSS_TYPES.get(claim["loss_type"], "property"))
    first = holder.get("first_name") or holder.get("display_name")
    contact = handler_name or f"our {queue['name']} team"
    who = handler_name.split(" (")[0] if handler_name else f"Our {queue['name']} team"
    if template_code == "siu_neutral_ack":  # never reveal the SIU referral to the claimant
        contact = f"{who} (Claims)" if handler_name else "our claims team"

    if channel == "sms":
        body = (f"Harborline Mutual: we received your {loss_label} claim, ref {claim['claim_number']}. "
                f"{contact.split(' (')[0]} will contact you {commitment.split(',')[0]}. Questions? Call {CLAIMS_LINE}.")
        return None, body

    paragraph = {
        "fast_track_ack": (f"Good news: your claim qualifies for our Fast Track service, which settles straightforward claims "
                           f"quickly. {who} will be in touch {commitment}."),
        "standard_ack": (f"Your claim has been assigned to our {queue['name']} team. {who} will contact you {commitment} "
                         "to talk through next steps, which may include an estimate review or an inspection."),
        "large_loss_ack": (f"Given the extent of the damage, your claim has been assigned to our Large Loss team. {who} will "
                           f"contact you {commitment}. Please take reasonable steps to protect the property from further damage "
                           "and keep receipts for any emergency repairs or temporary accommodation; these are normally recoverable "
                           "under your policy."),
        "catastrophe_ack": (f"We know {cat_name or 'the recent severe weather'} has affected many of our customers, and our "
                            f"catastrophe response team is working in your area. We will contact you {commitment}. If it is safe "
                            "to do so, please make temporary repairs to prevent further damage (for example, tarping a roof) and "
                            "keep your receipts."),
        "coverage_review_ack": ("We are reviewing the policy details that applied on the date of loss and will contact you "
                                f"{commitment} with an update. This letter confirms receipt only; it is not a decision on coverage."),
        "siu_neutral_ack": (f"Your claim has been assigned to a member of our claims team, who will contact you {commitment}. "
                            "As part of our standard review we may ask for additional documents or a short recorded statement."),
    }[template_code]

    docs = list(DOCUMENTS_BY_LOSS.get(claim["loss_type"], []))
    for d in extra_documents or []:
        if d not in docs:
            docs.append(d)
    have = set(received_kinds or ())
    if claim.get("police_report_number"):
        have |= {"police_report", "fire_report"}
    docs = [d for d in docs if not (_doc_kinds(d) & have)]
    lines = [
        f"Dear {first},",
        "",
        f"Thank you for getting in touch with Harborline Mutual. We have registered your {loss_label} claim under policy {policy_number}.",
        "",
        f"Claim number: {claim['claim_number']}",
        f"Date of loss: {_fmt(claim['loss_date'])}",
        f"Your claims contact: {contact}",
        "",
        paragraph,
    ]
    if note:
        lines += ["", note.strip()]
    if docs:
        lines += ["", "To help us move quickly, please reply with:"] + [f"  - {d}" for d in docs]
    lines += [
        "",
        (f"Please quote your claim number in all correspondence. You can reply to this email or call our claims line on "
         f"{CLAIMS_LINE}, 24 hours a day."),
        "",
        "Kind regards,",
        handler_name.split(" (")[0] if handler_name else "Claims Intake Team",
        "Claims Intake, Harborline Mutual Insurance",
    ]
    subject = f"Your claim {claim['claim_number']} has been received - Harborline Mutual"
    return subject, "\n".join(lines)
