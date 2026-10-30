"""Simulate a small company's invoicing and payment-chasing work.

The simulation produces two kinds of output:

* Observable data, the only thing ShadowCost gets to see: end-of-day snapshots
  of the invoice spreadsheet, the bank's payment export and an email log.
* Ground truth, which ShadowCost never sees: every action the office manager
  took, the workflow it belonged to and how many minutes it took. It is used to
  score workflow discovery and to check savings estimates.

The office manager is deliberately imperfect. Payments are recorded a day or
two late, reminders are occasionally forgotten or sent for invoices that have
already been paid, and the same email is phrased slightly differently each time.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from shadowcost.synth import emails
from shadowcost.synth.emails import ACCOUNTS

OFFICE_MANAGER = "office_manager"
CHASE_DAYS = (0, 3)  # overdue invoices are reviewed on Mondays and Thursdays

LEDGER_COLUMNS = [
    "invoice_id",
    "customer",
    "customer_email",
    "issue_date",
    "due_date",
    "amount",
    "status",
    "paid_date",
    "reminders_sent",
    "last_reminder_date",
    "notes",
]

WORKFLOWS = [
    {
        "name": "send_invoice",
        "repetitive": True,
        "trigger": "Work is delivered to a customer.",
        "steps": ["add_ledger_row", "send_invoice_email"],
        "observable_in": ["ledger", "email"],
    },
    {
        "name": "record_payment",
        "repetitive": True,
        "trigger": "A payment reaches the bank; it is recorded 0-2 business days later.",
        "steps": ["match_payment", "update_ledger"],
        "observable_in": ["bank", "ledger"],
    },
    {
        "name": "chase_overdue",
        "repetitive": True,
        "trigger": "On Mondays and Thursdays, invoices 7, 14 and 30+ days overdue get a first "
        "reminder, a second reminder and a final notice.",
        "steps": ["send_reminder", "update_ledger"],
        "observable_in": ["email", "ledger"],
    },
    {
        "name": "ad_hoc",
        "repetitive": False,
        "trigger": "Judgment calls and one-off requests.",
        "steps": ["misc_email", "edit_ledger", "note_promise", "resend_invoice", "answer_query"],
        "observable_in": ["email", "ledger"],
    },
]

_PREFIXES = [
    "Alder", "Birch", "Cobalt", "Dune", "Ember", "Fjord", "Granite", "Harbor", "Ivory",
    "Juniper", "Kestrel", "Lumen", "Maple", "Nimbus", "Orchid", "Pioneer", "Quarry", "Ridge",
    "Summit", "Tidal", "Upland", "Vale", "Willow", "Yarrow", "Zephyr",
]  # fmt: skip
_TRADES = [
    "Bakery", "Builders", "Cafe", "Dental", "Design", "Florists", "Fitness", "Joinery",
    "Logistics", "Studio", "Plumbing", "Vets", "Landscaping", "Optics", "Printers",
]  # fmt: skip


@dataclass(frozen=True)
class Config:
    seed: int = 7
    start: date = date(2026, 1, 5)
    days: int = 120  # calendar days; only business days are simulated
    n_customers: int = 25
    invoices_per_day: float = 1.5
    forget_reminder_prob: float = 0.08
    reply_prob: float = 0.35  # chance a customer replies to a reminder
    misc_email_prob: float = 0.35  # chance per day of an unrelated outbound email
    ledger_edit_prob: float = 0.06  # chance per day of a one-off spreadsheet edit
    inbound_noise_prob: float = 0.5  # chance per day of a newsletter or supplier email


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str
    email: str
    bank_name: str  # how the name appears on bank statements
    terms_days: int
    payer_type: str  # "prompt", "slow" or "chronic"; hidden ground truth


@dataclass
class Invoice:
    invoice_id: str
    customer: Customer
    issue_date: date
    due_date: date
    amount: float
    status: str = "sent"
    paid_date: date | None = None
    reminders_sent: int = 0
    last_reminder_date: date | None = None
    notes: str = ""
    # Hidden simulation state, not part of the spreadsheet.
    thread_id: str = ""
    pays_on: date = field(default=date.max)
    bank_paid: bool = False
    promised_until: date | None = None

    def ledger_row(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "customer": self.customer.name,
            "customer_email": self.customer.email,
            "issue_date": _iso(self.issue_date),
            "due_date": _iso(self.due_date),
            "amount": self.amount,
            "status": self.status,
            "paid_date": _iso(self.paid_date),
            "reminders_sent": self.reminders_sent,
            "last_reminder_date": _iso(self.last_reminder_date),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Email:
    message_id: str
    thread_id: str
    timestamp: datetime
    direction: str  # "outbound" or "inbound"
    from_addr: str
    to_addr: str
    subject: str
    body: str
    in_reply_to: str


@dataclass(frozen=True)
class Payment:
    payment_id: str
    date: date
    payer: str
    amount: float
    reference: str


@dataclass(frozen=True)
class Action:
    timestamp: datetime
    actor: str
    workflow: str
    step: str
    case_id: str  # invoice id, or "" for work not tied to an invoice
    minutes: float
    artifact: str  # message id, payment id, or "ledger" for a spreadsheet edit


@dataclass
class SimulationResult:
    config: Config
    customers: list[Customer]
    snapshots: dict[date, list[dict]]  # ledger rows at the end of each business day
    payments: list[Payment]
    emails: list[Email]
    actions: list[Action]


def simulate(config: Config | None = None) -> SimulationResult:
    return _Simulator(config or Config()).run()


class _Simulator:
    def __init__(self, config: Config):
        self.cfg = config
        self.rng = random.Random(config.seed)
        self.customers = _make_customers(self.rng, config.n_customers)
        self._weights = [self.rng.uniform(0.3, 3.0) for _ in self.customers]
        self.invoices: dict[str, Invoice] = {}
        self.payments: list[Payment] = []
        self.emails: list[Email] = []
        self.actions: list[Action] = []
        self.snapshots: dict[date, list[dict]] = {}
        self._pending_payments: list[tuple[date, Payment]] = []
        self._pending_replies: list[tuple[date, Email, str, str, date]] = []
        self._payment_invoice: dict[str, str] = {}
        self._thread_subject: dict[str, str] = {}
        self._thread_last: dict[str, str] = {}
        self._next_invoice = 1001
        self._next_msg = 1
        self._next_thread = 1
        self._next_payment = 1
        self._clock = datetime.min

    def run(self) -> SimulationResult:
        end = self.cfg.start + timedelta(days=self.cfg.days)
        for offset in range(self.cfg.days):
            today = self.cfg.start + timedelta(days=offset)
            if today.weekday() >= 5:
                continue
            self._clock = datetime.combine(today, time(9)) + timedelta(
                minutes=self.rng.uniform(0, 25)
            )
            self._bank_receives(today)
            self._record_payments(today)
            self._handle_replies(today)
            self._issue_invoices(today)
            if today.weekday() in CHASE_DAYS:
                self._chase_overdue(today)
            self._ad_hoc(today)
            self._inbound_noise(today)
            self.snapshots[today] = [inv.ledger_row() for inv in self.invoices.values()]

        # Customer replies can be scheduled past the end of the simulated period.
        in_period = [e for e in self.emails if e.timestamp.date() < end]
        return SimulationResult(
            config=self.cfg,
            customers=self.customers,
            snapshots=self.snapshots,
            payments=self.payments,
            emails=sorted(in_period, key=lambda e: e.timestamp),
            actions=sorted(self.actions, key=lambda a: a.timestamp),
        )

    # --- the office manager's daily work -------------------------------------------------

    def _record_payments(self, today: date) -> None:
        due_now = [p for d, p in self._pending_payments if d <= today]
        self._pending_payments = [(d, p) for d, p in self._pending_payments if d > today]
        for payment in due_now:
            inv = self.invoices[self._payment_invoice[payment.payment_id]]
            # Payments without a usable reference have to be matched by payer and amount.
            minutes = (2, 4) if payment.reference else (6, 12)
            self._work(
                "record_payment", "match_payment", inv.invoice_id, minutes, payment.payment_id
            )
            inv.status = "paid"
            # Usually the bank date, but sometimes the day it was recorded.
            inv.paid_date = payment.date if self.rng.random() < 0.95 else today
            self._work("record_payment", "update_ledger", inv.invoice_id, (1, 2))

    def _handle_replies(self, today: date) -> None:
        due_now = [r for r in self._pending_replies if r[0] <= today]
        self._pending_replies = [r for r in self._pending_replies if r[0] > today]
        for _, reply, kind, invoice_id, pay_by in due_now:
            inv = self.invoices[invoice_id]
            if kind == "promise":
                # Promises are sometimes noted in the spreadsheet, sometimes just remembered.
                if inv.status != "paid" and self.rng.random() < 0.6:
                    inv.notes = f"Promised payment by {_iso(pay_by)}"
                    self._work("ad_hoc", "note_promise", invoice_id, (1, 3))
                continue
            body = emails.human_reply(
                self.rng, kind, inv.customer.name, invoice_id, inv.amount, inv.due_date
            )
            msg = self._email(
                self._clock, inv.thread_id, "outbound", ACCOUNTS, inv.customer.email,
                reply.subject, body,
            )  # fmt: skip
            step, minutes = (
                ("resend_invoice", (4, 8)) if kind == "resend" else ("answer_query", (5, 10))
            )
            self._work("ad_hoc", step, invoice_id, minutes, msg.message_id)

    def _issue_invoices(self, today: date) -> None:
        for _ in range(_poisson(self.rng, self.cfg.invoices_per_day)):
            customer = self.rng.choices(self.customers, weights=self._weights)[0]
            invoice_id = f"INV-{self._next_invoice}"
            self._next_invoice += 1
            due = today + timedelta(days=customer.terms_days)
            amount = round(self.rng.lognormvariate(6.6, 0.6), 2)
            inv = Invoice(invoice_id, customer, today, due, amount)
            delay = timedelta(days=self._payment_delay(customer))
            inv.pays_on = max(today + timedelta(days=1), due + delay)
            subject, body = emails.invoice(self.rng, customer.name, invoice_id, amount, due)
            inv.thread_id = self._new_thread(subject)
            self.invoices[invoice_id] = inv

            def add_row(inv: Invoice = inv) -> None:
                self._work("send_invoice", "add_ledger_row", inv.invoice_id, (2, 4))

            def send_email(inv: Invoice = inv, subject: str = subject, body: str = body) -> None:
                msg = self._email(
                    self._clock, inv.thread_id, "outbound", ACCOUNTS, inv.customer.email,
                    subject, body,
                )  # fmt: skip
                self._work(
                    "send_invoice", "send_invoice_email", inv.invoice_id, (3, 6), msg.message_id
                )

            # Usually the row goes in first, but not always.
            steps = [add_row, send_email] if self.rng.random() > 0.15 else [send_email, add_row]
            for step in steps:
                step()

    def _chase_overdue(self, today: date) -> None:
        for inv in sorted(self.invoices.values(), key=lambda i: i.due_date):
            if inv.status == "paid":
                continue
            if inv.promised_until and today <= inv.promised_until:
                continue
            kind = _reminder_due(inv, today)
            if kind is None or self.rng.random() < self.cfg.forget_reminder_prob:
                continue
            overdue = (today - inv.due_date).days
            subject, body = emails.reminder(
                self.rng, kind, inv.customer.name, inv.invoice_id, inv.amount, inv.due_date, overdue
            )
            msg = self._email(
                self._clock, inv.thread_id, "outbound", ACCOUNTS, inv.customer.email, subject, body
            )
            minutes = (8, 15) if kind == "final" else (3, 7)
            self._work("chase_overdue", "send_reminder", inv.invoice_id, minutes, msg.message_id)
            inv.reminders_sent += 1
            inv.last_reminder_date = today
            inv.status = "overdue"
            self._work("chase_overdue", "update_ledger", inv.invoice_id, (1, 2))
            self._customer_reacts(inv, today)

    def _ad_hoc(self, today: date) -> None:
        if self.rng.random() < self.cfg.misc_email_prob:
            to_addr, subject, body = emails.misc_outbound(self.rng)
            msg = self._email(
                self._clock, self._new_thread(subject), "outbound", ACCOUNTS, to_addr, subject, body
            )
            self._work("ad_hoc", "misc_email", "", (5, 20), msg.message_id)

        if self.rng.random() < self.cfg.ledger_edit_prob:
            recent = [
                inv
                for inv in self.invoices.values()
                if not inv.bank_paid and (today - inv.issue_date).days <= 30
            ]
            if not recent:
                return
            inv = self.rng.choice(recent)
            if self.rng.random() < 0.5:
                factor = self.rng.choice(
                    [self.rng.uniform(0.85, 0.95), self.rng.uniform(1.05, 1.15)]
                )
                inv.amount = round(inv.amount * factor, 2)
                inv.notes = "Amount corrected"
            else:
                inv.notes = self.rng.choice(
                    [
                        "PO number required on remittance",
                        "Customer asked for itemised invoice",
                        "Deliver to new address",
                    ]
                )
            self._work("ad_hoc", "edit_ledger", inv.invoice_id, (3, 10))

    # --- the outside world ---------------------------------------------------------------

    def _bank_receives(self, today: date) -> None:
        for inv in self.invoices.values():
            if inv.bank_paid or inv.pays_on > today:
                continue
            inv.bank_paid = True
            payment = Payment(
                f"PAY-{self._next_payment:05d}",
                today,
                inv.customer.bank_name,
                inv.amount,
                self._reference(inv.invoice_id),
            )
            self._next_payment += 1
            self.payments.append(payment)
            self._payment_invoice[payment.payment_id] = inv.invoice_id
            lag = self.rng.choices([0, 1, 2], weights=[0.5, 0.35, 0.15])[0]
            self._pending_payments.append((_add_business_days(today, lag), payment))

    def _customer_reacts(self, inv: Invoice, today: date) -> None:
        # Reminders work: some late payers bring their payment forward.
        if not inv.bank_paid and inv.pays_on > today + timedelta(days=7):
            if self.rng.random() < 0.5:
                inv.pays_on = today + timedelta(days=self.rng.randint(2, 8))

        if self.rng.random() >= self.cfg.reply_prob:
            return
        reply_day = _add_business_days(today, self.rng.randint(1, 2))
        if inv.bank_paid:
            kind = "paid_already"
        else:
            kind = self.rng.choices(["promise", "resend"], weights=[0.75, 0.25])[0]
        pay_by = reply_day + timedelta(days=self.rng.randint(1, 6))
        if kind == "promise":
            inv.promised_until = reply_day + timedelta(days=7)
            if self.rng.random() < 0.7:  # not every promise is kept
                inv.pays_on = min(inv.pays_on, pay_by)
        timestamp = datetime.combine(reply_day, time(8)) + timedelta(
            minutes=self.rng.uniform(0, 600)
        )
        body = emails.customer_reply(self.rng, kind, inv.invoice_id, pay_by)
        subject = "Re: " + self._thread_subject[inv.thread_id]
        msg = self._email(
            timestamp, inv.thread_id, "inbound", inv.customer.email, ACCOUNTS, subject, body
        )
        handle_on = _add_business_days(reply_day, 1)
        self._pending_replies.append((handle_on, msg, kind, inv.invoice_id, pay_by))

    def _inbound_noise(self, today: date) -> None:
        if self.rng.random() < self.cfg.inbound_noise_prob:
            from_addr, subject, body = emails.inbound_noise(self.rng)
            timestamp = datetime.combine(today, time(7)) + timedelta(
                minutes=self.rng.uniform(0, 660)
            )
            thread = self._new_thread(subject)
            self._email(timestamp, thread, "inbound", from_addr, ACCOUNTS, subject, body)

    # --- helpers -------------------------------------------------------------------------

    def _work(
        self,
        workflow: str,
        step: str,
        case_id: str,
        minutes_range: tuple[float, float],
        artifact: str = "ledger",
    ) -> None:
        """Log an action at the office manager's current clock time and advance the clock."""
        minutes = round(self.rng.uniform(*minutes_range), 1)
        self.actions.append(
            Action(self._clock, OFFICE_MANAGER, workflow, step, case_id, minutes, artifact)
        )
        self._clock += timedelta(minutes=minutes + self.rng.uniform(0.5, 3))

    def _email(
        self,
        timestamp: datetime,
        thread_id: str,
        direction: str,
        from_addr: str,
        to_addr: str,
        subject: str,
        body: str,
    ) -> Email:
        msg = Email(
            message_id=f"msg-{self._next_msg:05d}",
            thread_id=thread_id,
            timestamp=timestamp.replace(microsecond=0),
            direction=direction,
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            body=body,
            in_reply_to=self._thread_last.get(thread_id, ""),
        )
        self._next_msg += 1
        self._thread_last[thread_id] = msg.message_id
        self.emails.append(msg)
        return msg

    def _new_thread(self, subject: str) -> str:
        thread_id = f"thr-{self._next_thread:05d}"
        self._next_thread += 1
        self._thread_subject[thread_id] = subject
        return thread_id

    def _payment_delay(self, customer: Customer) -> int:
        """Days after the due date that a customer pays, before any chasing."""
        if customer.payer_type == "prompt":
            return self.rng.randint(-10, 3)
        if customer.payer_type == "slow":
            return self.rng.randint(0, 20)
        return self.rng.randint(10, 50)

    def _reference(self, invoice_id: str) -> str:
        """The payment reference a customer types: often right, sometimes mangled or missing."""
        r = self.rng.random()
        if r < 0.7:
            return invoice_id
        if r < 0.85:
            number = invoice_id.split("-")[1]
            return self.rng.choice([invoice_id.replace("-", " "), f"INV{number}", number])
        return ""


def _reminder_due(inv: Invoice, today: date) -> str | None:
    overdue = (today - inv.due_date).days
    since_last = (today - inv.last_reminder_date).days if inv.last_reminder_date else 0
    if inv.reminders_sent == 0 and overdue >= 7:
        return "first"
    if inv.reminders_sent == 1 and overdue >= 14 and since_last >= 5:
        return "second"
    if inv.reminders_sent == 2 and overdue >= 30 and since_last >= 7:
        return "final"
    return None


def _make_customers(rng: random.Random, n: int) -> list[Customer]:
    names = [f"{prefix} {trade}" for prefix in _PREFIXES for trade in _TRADES]
    rng.shuffle(names)
    # A fixed 40/40/20 mix of payer types, so every seed has a comparable amount of
    # chasing work; only which customer gets which type is random.
    n_prompt, n_slow = round(0.4 * n), round(0.4 * n)
    payer_types = ["prompt"] * n_prompt + ["slow"] * n_slow + ["chronic"] * (n - n_prompt - n_slow)
    rng.shuffle(payer_types)
    customers = []
    for i, (name, payer_type) in enumerate(zip(names[:n], payer_types, strict=True), start=1):
        slug = name.lower().replace(" ", "-")
        mailbox = rng.choice(["accounts", "billing", "finance", "admin"])
        # Bank statements show an upper-cased, often truncated version of the name.
        bank_name = (name.upper() + rng.choice([" LTD", "", " LIMITED"]))[:18]
        customers.append(
            Customer(
                customer_id=f"C{i:03d}",
                name=f"{name} Ltd",
                email=f"{mailbox}@{slug}.example",
                bank_name=bank_name,
                terms_days=rng.choices([30, 14], weights=[0.7, 0.3])[0],
                payer_type=payer_type,
            )
        )
    return customers


def _poisson(rng: random.Random, lam: float) -> int:
    threshold, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


def _add_business_days(day: date, n: int) -> date:
    """``n`` business days after ``day``; 0 rolls a weekend forward to Monday."""
    while day.weekday() >= 5:
        day += timedelta(days=1)
    for _ in range(n):
        day += timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
    return day


def _iso(d: date | None) -> str:
    return d.isoformat() if d else ""
