"""Email templates for the synthetic company.

The office manager writes from memory rather than with a mail merge, so each
kind of email comes in a few phrasings. Discovery has to recognise them as the
same template despite the variation.
"""

from __future__ import annotations

import random
from datetime import date

COMPANY = "Fernhill Supplies"
DOMAIN = "fernhill.example"
ACCOUNTS = f"accounts@{DOMAIN}"

_SIGN_OFFS = [
    f"Thanks,\nAccounts\n{COMPANY}",
    f"Kind regards,\nAccounts team\n{COMPANY}",
    f"Best,\n{COMPANY} Accounts",
]

_MISC_OUTBOUND = [
    (
        f"ops@{DOMAIN}",
        "Delivery schedule next week",
        "Can you confirm the delivery slots for next week? Two customers have asked.",
    ),
    (
        f"director@{DOMAIN}",
        "Monthly numbers",
        "I've pulled together this month's sales and outstanding invoices. "
        "Shall we go through them on Friday?",
    ),
    (
        "orders@packwell.example",
        "Packaging order",
        "We'd like to reorder the medium boxes, same quantity as last time.",
    ),
    (
        "support@ledgerly.example",
        "Login problem",
        "I can't log in to the accounting portal since this morning. Can you help?",
    ),
    (
        f"team@{DOMAIN}",
        "Office closed Monday",
        "Reminder that the office is closed on Monday for maintenance.",
    ),
    (
        f"hr@{DOMAIN}",
        "Holiday request",
        "I'd like to book two days off at the end of the month.",
    ),
]

_INBOUND_NOISE = [
    (
        "news@tradeweekly.example",
        "This week in wholesale",
        "Corrugated board prices rose again this month. Read the full roundup online.",
    ),
    (
        "billing@packwell.example",
        "Your Packwell invoice",
        "Your invoice PW-{n} is attached. Thank you for your order.",
    ),
    (
        "noreply@ledgerly.example",
        "Your monthly statement is ready",
        "Log in to your Ledgerly account to view statement {n}.",
    ),
    (
        "events@chamber.example",
        "Networking breakfast",
        "Join local business owners for breakfast on Thursday at 8am.",
    ),
]


def money(amount: float) -> str:
    return f"${amount:,.2f}"


def _day(d: date) -> str:
    return d.strftime("%d %b %Y")


def _compose(rng: random.Random, customer: str, *paragraphs: str) -> str:
    short = customer.removesuffix(" Ltd")
    greeting = rng.choice([f"Hi {short} team,", "Hello,", f"Dear {short},"])
    return "\n\n".join([greeting, *paragraphs, rng.choice(_SIGN_OFFS)])


def invoice(
    rng: random.Random, customer: str, invoice_id: str, amount: float, due: date
) -> tuple[str, str]:
    subject = rng.choice(
        [f"Invoice {invoice_id} from {COMPANY}", f"{COMPANY} invoice {invoice_id}"]
    )
    body = _compose(
        rng,
        customer,
        rng.choice(
            [
                f"Please find attached invoice {invoice_id} for {money(amount)}, "
                f"due on {_day(due)}.",
                f"Attached is invoice {invoice_id} ({money(amount)}). "
                f"Payment is due by {_day(due)}.",
            ]
        ),
        rng.choice(
            [
                "Please include the invoice number as your payment reference.",
                f"When paying, please quote {invoice_id} as the reference.",
            ]
        ),
    )
    return subject, body


def reminder(
    rng: random.Random,
    kind: str,
    customer: str,
    invoice_id: str,
    amount: float,
    due: date,
    days_overdue: int,
) -> tuple[str, str]:
    if kind == "first":
        subject = rng.choice(
            [
                f"Reminder: invoice {invoice_id} is overdue",
                f"Invoice {invoice_id} - payment reminder",
            ]
        )
        text = rng.choice(
            [
                f"Just a friendly reminder that invoice {invoice_id} for {money(amount)} "
                f"was due on {_day(due)}.",
                f"Our records show invoice {invoice_id} ({money(amount)}, due {_day(due)}) "
                "is still unpaid.",
            ]
        )
        ask = rng.choice(
            [
                "If you've already paid, please ignore this email.",
                "Could you let us know when we can expect payment?",
            ]
        )
    elif kind == "second":
        subject = rng.choice(
            [
                f"Second reminder: invoice {invoice_id}",
                f"Invoice {invoice_id} now {days_overdue} days overdue",
            ]
        )
        text = rng.choice(
            [
                f"Following up on invoice {invoice_id} for {money(amount)}, which is now "
                f"{days_overdue} days overdue.",
                f"We still haven't received payment for invoice {invoice_id} "
                f"({money(amount)}), due {_day(due)}.",
            ]
        )
        ask = rng.choice(
            [
                "Please arrange payment this week.",
                "Please let us know if there is a problem with the invoice.",
            ]
        )
    elif kind == "final":
        subject = f"FINAL NOTICE: invoice {invoice_id}"
        text = (
            f"Invoice {invoice_id} for {money(amount)} is now {days_overdue} days overdue "
            "despite previous reminders."
        )
        ask = rng.choice(
            [
                "If payment isn't received within 7 days we will have to pause further orders.",
                "Please pay within 7 days to avoid your account being put on hold.",
            ]
        )
    else:
        raise ValueError(f"unknown reminder kind: {kind}")
    return subject, _compose(rng, customer, text, ask)


def customer_reply(rng: random.Random, kind: str, invoice_id: str, pay_by: date) -> str:
    if kind == "promise":
        return rng.choice(
            [
                f"Sorry for the delay. We'll pay {invoice_id} by {_day(pay_by)}.",
                f"Apologies, this got stuck in approvals. Payment should go out by {_day(pay_by)}.",
                "Thanks for the reminder, we'll get this paid this week.",
            ]
        )
    if kind == "resend":
        return rng.choice(
            [
                f"We can't find {invoice_id} on our system. Could you resend it?",
                "Could you send a copy of the invoice please? It never reached our accounts team.",
            ]
        )
    if kind == "paid_already":
        return rng.choice(
            [
                f"We paid {invoice_id} a few days ago, can you check?",
                "This was paid last week. Please check your bank.",
            ]
        )
    raise ValueError(f"unknown reply kind: {kind}")


def human_reply(
    rng: random.Random, kind: str, customer: str, invoice_id: str, amount: float, due: date
) -> str:
    if kind == "resend":
        text = (
            f"Of course, invoice {invoice_id} for {money(amount)} is attached again. "
            f"It was due on {_day(due)}."
        )
    elif kind == "paid_already":
        text = rng.choice(
            [
                f"Thanks, we've found your payment for {invoice_id} and updated our records.",
                f"Thanks for letting us know. We'll check our bank statement for {invoice_id} "
                "and confirm.",
            ]
        )
    else:
        raise ValueError(f"unknown reply kind: {kind}")
    return _compose(rng, customer, text)


def misc_outbound(rng: random.Random) -> tuple[str, str, str]:
    to_addr, subject, text = rng.choice(_MISC_OUTBOUND)
    return to_addr, subject, f"Hi,\n\n{text}\n\nThanks"


def inbound_noise(rng: random.Random) -> tuple[str, str, str]:
    from_addr, subject, text = rng.choice(_INBOUND_NOISE)
    return from_addr, subject, text.format(n=rng.randint(10000, 99999))
