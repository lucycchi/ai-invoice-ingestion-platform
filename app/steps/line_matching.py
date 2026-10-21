"""Step 3: Claude suggests a catalog item for each invoice line, checked and saved as answers arrive."""

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from sqlalchemy import select

from app.clients.claude import PROMPTS, ClaudeFailed, SharedPrompt, Usage, min_cacheable_tokens
from app.checks import price_flag
from app.clients.reference_api import ReferenceUnavailable
from app.logs import log_error
from app.clock import now_iso
from app.models import CatalogSnapshotItem, Invoice, LineItem, LineMatch, Run
from app.schemas import GroupAnswer, LineResult
from app.status import Status, StatusConflict, claim, fail, locked_invoice

log = logging.getLogger(__name__)

GROUP_SIZE = 6
MAX_AT_ONCE = 5
MAX_ALTERNATIVES = 2


def group_lines(lines: list, size: int = GROUP_SIZE) -> list[list]:
    ordered = sorted(lines, key=lambda line: line.position)
    return [ordered[i : i + size] for i in range(0, len(ordered), size)]


def catalog_text(items) -> str:
    """The catalog as Claude sees it: one item per line, in ID order, the same text every time (so it caches)."""
    header = "Catalog items (ID | code | description | category | unit price):"
    rows = [
        f"{item.catalog_item_id} | {item.item_code} | {item.description} | {item.category or 'uncategorized'} | "
        f"{item.unit_price if item.unit_price is not None else 'no fixed price'}"
        for item in sorted(items, key=lambda item: item.catalog_item_id)
    ]
    return "\n".join([header, *rows])


def check_answer(answer: GroupAnswer, positions: set[int], catalog_ids: set[int]) -> tuple[dict[int, LineResult], set[int]]:
    """Accept each line that got exactly one result whose catalog IDs are all in the catalog."""
    seen: dict[int, list[LineResult]] = {}
    for result in answer.results:
        if result.position in positions:
            seen.setdefault(result.position, []).append(result)
    accepted = {}
    for position, results in seen.items():
        if len(results) != 1:
            continue
        result = results[0]
        ids = [result.catalog_item_id] if result.catalog_item_id is not None else []
        ids += result.alternatives
        if len(result.alternatives) <= MAX_ALTERNATIVES and all(i in catalog_ids for i in ids):
            accepted[position] = result
    return accepted, positions - set(accepted)


class _Tally:
    """What every group worker reports back, shared safely between threads."""

    def __init__(self):
        self.lock = threading.Lock()
        self.usage = Usage()
        self.errors: list[str] = []
        self.unusable = 0
        self.last_saved: str | None = None

    def add(self, usage: Usage) -> None:
        with self.lock:
            self.usage += usage


def _line_payload(line: LineItem) -> dict:
    return {
        "position": line.position,
        "description": line.description,
        "quantity": None if line.quantity is None else f"{line.quantity:g}",
        "unit_price": None if line.unit_price is None else str(line.unit_price),
    }


def run_matching(app, invoice_id: int) -> None:
    sessions, claude = app.state.sessions, app.state.claude
    tally = _Tally()

    with sessions() as s:
        invoice = s.get(Invoice, invoice_id)
        snapshot = s.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id).all()
    if not snapshot:  # a first run; a Retry reuses the saved snapshot
        try:
            items = app.state.reference.list_catalog(invoice.confirmed_sponsor_id, invoice.confirmed_study_id)
        except ReferenceUnavailable as down:
            _finish(sessions, invoice_id, tally, cache_applied=False, failure=str(down))
            return
        with sessions() as s:
            for item in items:
                s.add(CatalogSnapshotItem(
                    invoice_id=invoice_id, catalog_item_id=item["id"], item_code=item["item_code"],
                    description=item["description"], category=item.get("category"),
                    unit_price=None if item.get("unit_price") is None else Decimal(str(item["unit_price"])),
                ))
            s.commit()
            snapshot = s.query(CatalogSnapshotItem).filter_by(invoice_id=invoice_id).all()

    with sessions() as s:
        matched = select(LineMatch.line_item_id)
        pending = (s.query(LineItem).filter(LineItem.invoice_id == invoice_id, LineItem.id.not_in(matched))
                   .order_by(LineItem.position).all())
    line_ids = {line.position: line.id for line in pending}
    unit_prices = {line.position: line.unit_price for line in pending}
    catalog_prices = {item.catalog_item_id: item.unit_price for item in snapshot}
    catalog_ids = {item.catalog_item_id for item in snapshot}
    shared = SharedPrompt(instructions=(PROMPTS / "matching_instructions.md").read_text(),
                          catalog_text=catalog_text(snapshot))
    groups = [[_line_payload(line) for line in group] for group in group_lines(pending)]

    def work(group: list[dict]) -> bool:
        """Match one group. True if Claude answered (whether or not every line could be used)."""
        try:
            to_send = group
            for _ in range(2):  # the group's answer, and one resend of any lines it couldn't be used for
                try:
                    answer, usage = claude.match_group(shared, to_send)
                except ClaudeFailed as failed:
                    tally.add(failed.usage)
                    with tally.lock:
                        tally.errors.append(failed.reason)
                    return False
                tally.add(usage)
                accepted, failed_positions = check_answer(answer, {line["position"] for line in to_send}, catalog_ids)
                _save(sessions, invoice_id, accepted, line_ids, unit_prices, catalog_prices, tally)
                to_send = [line for line in to_send if line["position"] in failed_positions]
                if not to_send:
                    return True
            with tally.lock:
                tally.unusable += len(to_send)
            return True
        except Exception as err:  # e.g. a database lock: recorded so the run still gets its counts
            log_error(log, "Unexpected error matching a group", invoice_id, err)
            with tally.lock:
                tally.errors.append(f"Unexpected error ({type(err).__name__}); details are in the app log")
            return False

    cache_applied = False
    if groups:
        try:
            shared_tokens = claude.count_shared_tokens(shared)
            tally.add(Usage(requests=1))  # counting tokens is a request to Claude too
        except Exception:  # counting is only an optimisation; without it, nothing is warmed
            shared_tokens = 0
        rest = groups
        if shared_tokens >= min_cacheable_tokens(app.state.settings.anthropic_model) and len(groups) > 1:
            # The first group writes the cache before the others read it; it only counts if it worked.
            cache_applied = work(groups[0])
            rest = groups[1:]
        with ThreadPoolExecutor(max_workers=MAX_AT_ONCE) as pool:
            list(pool.map(work, rest))
    _finish(sessions, invoice_id, tally, cache_applied)


def _save(sessions, invoice_id: int, accepted: dict[int, LineResult], line_ids: dict[int, int], unit_prices: dict,
          catalog_prices: dict, tally: _Tally) -> None:
    """Save accepted results, but only while the invoice is still matching (checked in the same write)."""
    if not accepted:
        return
    with sessions() as s:
        try:
            with locked_invoice(s, invoice_id, allowed={Status.MATCHING}):
                _add_matches(s, accepted, line_ids, unit_prices, catalog_prices)
        except StatusConflict:
            log.info("Discarded late matching results for invoice %s: it is no longer matching", invoice_id)
            return
    with tally.lock:
        tally.last_saved = now_iso()


def _add_matches(s, accepted, line_ids, unit_prices, catalog_prices) -> None:
    for position, result in accepted.items():
        flag = None
        if result.catalog_item_id is not None:
            flag = price_flag(unit_prices[position], catalog_prices[result.catalog_item_id])
        s.add(LineMatch(
            price_flag=flag.to_json() if flag else None,
            line_item_id=line_ids[position],
            ai_catalog_item_id=result.catalog_item_id,
            ai_confidence=result.confidence,
            ai_reason=result.reason,
            ai_alternatives=json.dumps(result.alternatives),
        ))


def _finish(sessions, invoice_id: int, tally: _Tally, cache_applied: bool, failure: str | None = None) -> None:
    with sessions() as s:
        matched = select(LineMatch.line_item_id)
        missing = s.query(LineItem).filter(LineItem.invoice_id == invoice_id, LineItem.id.not_in(matched)).count()
        if failure is None and missing:
            if tally.errors:
                failure = f"Couldn't match {missing} line{'s' if missing != 1 else ''}: {tally.errors[0]}"
            else:
                failure = f"The AI's answer for {missing} line{'s' if missing != 1 else ''} could not be used"
        run = s.query(Run).filter_by(invoice_id=invoice_id, step="matching").order_by(Run.id.desc()).first()
        if run is not None:
            # A failed run has no "last result stored" moment, so its stored time stays empty.
            run.stored_at = (tally.last_saved or now_iso()) if failure is None else None
            run.claude_requests = tally.usage.requests
            run.input_tokens = tally.usage.input_tokens
            run.output_tokens = tally.usage.output_tokens
            run.cache_read_tokens = tally.usage.cache_read_tokens
            run.cache_applied = cache_applied
            run.outcome = "succeeded" if failure is None else f"failed: {failure}"
        try:
            if failure is None:
                claim(s, invoice_id, expected={Status.MATCHING}, new=Status.IN_REVIEW)
            else:
                fail(s, invoice_id, failure)
        except StatusConflict:  # the user changed the metadata while matching ran; their change stands
            if run is not None:
                run.outcome = "stopped: the invoice was changed while matching ran"
        s.commit()
