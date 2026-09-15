"""
XLSX export builders for the Admin Portal.

Uses openpyxl to build in-memory workbooks that can be:
  * downloaded directly (returned as a StreamingResponse from FastAPI)
  * uploaded to Google Drive (raw bytes fed into drive_client)
  * (indirectly) SMSed as a Drive share link

Two workbooks:
  * build_orders_xlsx(orders) — flat sheet of order rows + a per-item detail sheet
  * build_customers_xlsx(customers, orders_by_user) — customers sheet + full order history sheet
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# ------------------------------------------------------------------ helpers ---
_HEADER_FILL = PatternFill("solid", fgColor="B14F36")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
_MONEY_FMT = '"$"#,##0.00'
_DATE_FMT = "yyyy-mm-dd hh:mm"


def _cents(v) -> float:
    try:
        return (v or 0) / 100.0
    except Exception:
        return 0.0


def _fmt_date(v) -> str:
    if not v:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    return str(v)


def _autosize(ws, min_width: int = 8, max_width: int = 60) -> None:
    for col_idx, col in enumerate(ws.columns, start=1):
        length = min_width
        for cell in col:
            v = "" if cell.value is None else str(cell.value)
            length = max(length, min(len(v) + 2, max_width))
        ws.column_dimensions[get_column_letter(col_idx)].width = length


def _write_header(ws, headers: list[str]) -> None:
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.freeze_panes = "A2"


# ------------------------------------------------------------------ orders ---
_ORDER_HEADERS = [
    "Order ID", "Placed", "Customer", "Email", "Phone",
    "Delivery date", "Slot", "Status", "Payment", "Payment status",
    "Subtotal", "Delivery fee", "Discount", "Total",
    "Items", "Address", "City", "Postal code",
]


def _order_row(o: dict) -> list:
    us = o.get("user_summary") or {}
    slot = o.get("slot") or {}
    addr = o.get("address") or {}
    items = o.get("items_snapshot") or []
    items_str = "; ".join(
        f"{i.get('quantity', 1)}× {i.get('name', '?')}" for i in items
    )
    return [
        o.get("order_id", ""),
        _fmt_date(o.get("created_at")),
        us.get("name") or o.get("customer_name") or "",
        us.get("email") or "",
        us.get("phone") or o.get("phone") or "",
        slot.get("date", ""),
        slot.get("window", ""),
        o.get("status", ""),
        o.get("payment_method", ""),
        o.get("payment_status", ""),
        _cents(o.get("subtotal_cents")),
        _cents(o.get("delivery_fee_cents")),
        _cents(o.get("discount_cents")),
        _cents(o.get("total_cents")),
        items_str,
        addr.get("line1", "") + (f" {addr['line2']}" if addr.get("line2") else ""),
        addr.get("city", ""),
        addr.get("postal_code", ""),
    ]


def build_orders_xlsx(orders: Iterable[dict]) -> bytes:
    """
    Kitchen-friendly pivot layout.

    Tab 1..N — one sheet per delivery week, named "Week of YYYY-MM-DD".
        Columns: Order ID | Customer | Phone | Delivery date | Slot | Status | Payment | Total
                 followed by ONE COLUMN PER UNIQUE ITEM in that week.
        Cell value: quantity ordered (empty if 0). For catering items, uses the
        guest count as the qty.

    Tab N+1 — "Details": the itemized flat layout (one row per order, all fields
        including items concatenated + address + totals). Kept for reference.
    """
    orders = list(orders)
    wb = Workbook()
    # Remove default sheet — we'll add our own.
    wb.remove(wb.active)

    # ---------- Group orders by delivery week (Sunday-anchored) ----------
    from collections import defaultdict
    def _week_start(iso: str) -> str:
        if not iso:
            return "unknown"
        try:
            d = datetime.strptime(iso[:10], "%Y-%m-%d")
        except Exception:
            return "unknown"
        sunday = d - timedelta(days=d.weekday() + 1 if d.weekday() < 6 else 0)
        # Python's weekday(): Mon=0..Sun=6. We want Sunday=0.
        # Rebuild: shift so Sunday starts the week.
        offset = (d.weekday() + 1) % 7  # Sun=0, Mon=1, ..., Sat=6
        sunday = d - timedelta(days=offset)
        return sunday.strftime("%Y-%m-%d")

    buckets: dict[str, list[dict]] = defaultdict(list)
    for o in orders:
        wk = _week_start((o.get("slot") or {}).get("date", "") or "")
        buckets[wk].append(o)

    # Sort weeks: current/upcoming first, then reverse chronological
    today = datetime.now().date()
    current_wk_offset = (today.weekday() + 1) % 7
    current_wk = (today - timedelta(days=current_wk_offset)).strftime("%Y-%m-%d")

    def _sort_key(wk: str):
        if wk == "unknown":
            return (2, "")  # last
        # Distance from current week (nearest first), then descending date
        try:
            wk_date = datetime.strptime(wk, "%Y-%m-%d").date()
            cur_date = datetime.strptime(current_wk, "%Y-%m-%d").date()
            days_diff = abs((wk_date - cur_date).days)
            return (0, days_diff, -wk_date.toordinal())
        except Exception:
            return (1, wk)

    sorted_weeks = sorted(buckets.keys(), key=_sort_key)

    # ---------- Build one pivot sheet per week ----------
    def _qty_for(order: dict, item_name: str) -> int:
        total = 0
        for nm, q in expand_order_items(order):
            if nm == item_name:
                total += q
        return total

    def _sheet_title(wk: str) -> str:
        if wk == "unknown":
            base = "No delivery date"
        else:
            try:
                d = datetime.strptime(wk, "%Y-%m-%d")
                base = f"Week of {d.strftime('%b %d')}"  # "Week of Aug 23"
            except Exception:
                base = f"Week of {wk}"
        # Excel sheet name: max 31 chars, no \ / ? * [ ] :
        return "".join(c for c in base if c not in r"\/?*[]:")[:31]

    base_cols = ["Order ID", "Customer", "Phone", "Delivery date", "Slot",
                 "Status", "Payment", "Total"]

    for wk in sorted_weeks:
        orders_in_wk = buckets[wk]
        # Collect unique item names (preserve order-of-first-appearance).
        # For combos we use the exploded dish names, NOT "This Week's Combo".
        seen: dict[str, None] = {}  # ordered dict
        for o in orders_in_wk:
            for nm, _q in expand_order_items(o):
                seen.setdefault(nm, None)
        item_cols = list(seen.keys())

        ws = wb.create_sheet(_sheet_title(wk))
        _write_header(ws, base_cols + item_cols)
        ws.freeze_panes = "I2"  # freeze first 8 static cols + header row

        money_col = 8  # "Total"
        for r_i, o in enumerate(orders_in_wk, start=2):
            us = o.get("user_summary") or {}
            slot = o.get("slot") or {}
            row_static = [
                o.get("order_id", ""),
                us.get("name") or o.get("customer_name") or "",
                us.get("phone") or o.get("phone") or "",
                slot.get("date", ""),
                slot.get("window", ""),
                o.get("status", ""),
                o.get("payment_method", ""),
                _cents(o.get("total_cents")),
            ]
            for c_i, v in enumerate(row_static, start=1):
                cell = ws.cell(row=r_i, column=c_i, value=v)
                if c_i == money_col:
                    cell.number_format = _MONEY_FMT
            for c_off, item_name in enumerate(item_cols, start=len(base_cols) + 1):
                q = _qty_for(o, item_name)
                if q > 0:
                    ws.cell(row=r_i, column=c_off, value=q)
        _autosize(ws, min_width=6, max_width=28)

    # ---------- Details sheet (legacy detailed layout) ----------
    ws2 = wb.create_sheet("Details")
    _write_header(ws2, _ORDER_HEADERS)
    money_cols = [11, 12, 13, 14]
    for r_i, o in enumerate(orders, start=2):
        for c_i, v in enumerate(_order_row(o), start=1):
            cell = ws2.cell(row=r_i, column=c_i, value=v)
            if c_i in money_cols:
                cell.number_format = _MONEY_FMT
    _autosize(ws2)

    # Fallback: if nothing was written (empty orders list) create a placeholder
    if not wb.sheetnames:
        ws = wb.create_sheet("Orders")
        _write_header(ws, base_cols)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------- customers ---
_CUSTOMER_HEADERS = [
    "User ID", "Name", "Email", "Phone",
    "Joined", "Loyalty points", "Total orders",
    "Total spent", "Last order date", "Last order status",
]
_CUSTOMER_ORDER_HEADERS = [
    "User ID", "Customer name",
    "Order ID", "Placed", "Delivery date", "Status",
    "Payment", "Total", "Items",
]


def _customer_row(c: dict) -> list:
    return [
        c.get("user_id", ""),
        c.get("name", ""),
        c.get("email", ""),
        c.get("phone", ""),
        _fmt_date(c.get("created_at")),
        c.get("loyalty_points", 0),
        c.get("total_orders", 0),
        _cents(c.get("total_spent_cents", 0)),
        _fmt_date(c.get("last_order_date")),
        c.get("last_order_status", ""),
    ]


def build_customers_xlsx(customers: Iterable[dict],
                        orders_by_user: dict[str, list[dict]] | None = None) -> bytes:
    """
    customers: list of customer summary dicts (with total_orders, total_spent_cents,
               last_order_date, last_order_status pre-computed)
    orders_by_user: optional {user_id: [order_dict, ...]} to write a second sheet
                    with the full order history per customer.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Customers"
    _write_header(ws, _CUSTOMER_HEADERS)

    customers_list = list(customers)
    for r, c in enumerate(customers_list, start=2):
        for cc, v in enumerate(_customer_row(c), start=1):
            cell = ws.cell(row=r, column=cc, value=v)
            if cc == 8:  # total spent
                cell.number_format = _MONEY_FMT
    _autosize(ws)

    if orders_by_user:
        ws2 = wb.create_sheet("Order history")
        _write_header(ws2, _CUSTOMER_ORDER_HEADERS)
        r = 2
        # Build a quick user_id -> name map so the order sheet is human-readable.
        name_map = {c.get("user_id", ""): c.get("name", "") for c in customers_list}
        for uid, orders in orders_by_user.items():
            for o in orders:
                slot = o.get("slot") or {}
                items = o.get("items_snapshot") or []
                items_str = "; ".join(
                    f"{i.get('quantity', 1)}× {i.get('name', '?')}" for i in items
                )
                row = [
                    uid, name_map.get(uid, ""),
                    o.get("order_id", ""),
                    _fmt_date(o.get("created_at")),
                    slot.get("date", ""),
                    o.get("status", ""),
                    o.get("payment_method", ""),
                    _cents(o.get("total_cents")),
                    items_str,
                ]
                for cc, v in enumerate(row, start=1):
                    cell = ws2.cell(row=r, column=cc, value=v)
                    if cc == 8:
                        cell.number_format = _MONEY_FMT
                r += 1
        _autosize(ws2)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def default_filename(kind: str) -> str:
    """kind ∈ {'orders', 'customers'} → 'orders-2026-08-31.xlsx' etc."""
    return f"curryco-{kind}-{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M')}.xlsx"


# --------------------------------------------------- shared combo expansion ---
import re as _re

# Trailing " × 3" quantity suffix from the combo +/- steppers.
_QTY_SUFFIX_RE = _re.compile(r"\s*[×xX]\s*(\d+)\s*$")
# Trailing "(+CA$5.00 ea)" premium-item surcharge tag baked into the pick name.
_SURCHARGE_TAG_RE = _re.compile(r"\s*\(\+?[^)]*(?:ea|each)\s*\)\s*$", _re.IGNORECASE)


def _split_qty_suffix(name: str) -> tuple[str, int]:
    """Normalize a combo pick name to (clean_name, effective_qty).

    Handles two artifacts that leaked into the stored strings:
      1) trailing " × N" from the combo +/- steppers
      2) trailing "(+CA$5.00 ea)" from the premium-surcharge display

    Both can appear together in either order, e.g.
        'Kolkata Chicken Biryani × 3 (+CA$5.00 ea)'
        'Kolkata Chicken Biryani (+CA$5.00 ea) × 3'
    """
    if not name:
        return ("(unnamed)", 1)
    s = name
    mult = 1
    # Strip up to a few times so both tags peel off regardless of order.
    for _ in range(4):
        m1 = _QTY_SUFFIX_RE.search(s)
        m2 = _SURCHARGE_TAG_RE.search(s)
        if m1 and (not m2 or m1.start() > m2.start()):
            n = int(m1.group(1))
            if n >= 1:
                mult *= n
            s = s[:m1.start()].rstrip()
        elif m2:
            s = s[:m2.start()].rstrip()
        else:
            break
    return (s or "(unnamed)", mult)


def expand_order_items(order: dict) -> list[tuple[str, int]]:
    """Return (item_name, qty) tuples for one order.

    Combos (kind='weekly_package') are exploded into their individual dishes
    listed in `package_selection_names` — each occurrence in the list counts,
    multiplied by the combo's own `quantity`. Same-name picks are summed.
    Catering items use `catering_guest_count` as their effective qty.
    """
    from collections import OrderedDict
    totals: "OrderedDict[str, int]" = OrderedDict()
    for it in (order.get("items_snapshot") or []):
        kind = it.get("kind") or ""
        base_qty = int(it.get("quantity") or 0) or 1
        if kind == "weekly_package":
            for pick_name in (it.get("package_selection_names") or []):
                if not pick_name:
                    continue
                clean, mult = _split_qty_suffix(pick_name)
                totals[clean] = totals.get(clean, 0) + base_qty * mult
        elif kind == "catering":
            guests = int(it.get("catering_guest_count") or base_qty or 0)
            nm = it.get("name") or "(unnamed)"
            totals[nm] = totals.get(nm, 0) + guests
        else:
            nm = it.get("name") or "(unnamed)"
            totals[nm] = totals.get(nm, 0) + base_qty
    return list(totals.items())
