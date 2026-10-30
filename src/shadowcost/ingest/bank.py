"""Turn a bank export into payment events linked to cases."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from shadowcost.ingest.detect import (
    BANK_AMOUNT,
    BANK_DATE,
    BANK_PAYER,
    BANK_REFERENCE,
    DetectedFile,
    find_column,
    read_table,
)
from shadowcost.ingest.events import event
from shadowcost.ingest.linking import CaseIndex, to_amount

BANK_ID = ("payment_id", "transaction_id", "id", "transaction")


def bank_events(root: Path, file: DetectedFile, index: CaseIndex) -> tuple[list[dict], list[str]]:
    df = read_table(root / file.path)
    columns = list(df.columns)
    date_col = find_column(columns, BANK_DATE)
    amount_col = find_column(columns, BANK_AMOUNT)
    payer_col = find_column(columns, BANK_PAYER)
    reference_col = find_column(columns, BANK_REFERENCE)
    id_col = find_column(columns, BANK_ID)

    events, warnings = [], []
    for i, row in enumerate(df.to_dict("records"), start=1):
        when = pd.to_datetime(row[date_col], errors="coerce")
        amount = to_amount(row[amount_col])
        if pd.isna(when) or amount is None:
            warnings.append(f"{file.path} row {i}: unreadable date or amount, skipped")
            continue
        payer = row[payer_col] if payer_col else ""
        reference = row[reference_col] if reference_col else ""
        case_id, method = index.link_payment(reference, amount, payer)
        events.append(
            event(
                when.normalize(),
                "day",
                "bank",
                "bank.credit" if amount >= 0 else "bank.debit",
                object_id=row[id_col] if id_col else f"{file.path.stem}/{i}",
                case_id=case_id,
                link_method=method,
                actor=payer,
                payload={"amount": amount, "payer": payer, "reference": reference},
            )
        )
    return events, warnings
