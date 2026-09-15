/**
 * Expand a "weekly_package" (combo) order item into the individual dish picks
 * with quantities — mirrors the backend logic used for the pivot XLS.
 *
 * Handles two artifacts that leaked into the stored pick strings:
 *   - trailing " × N" from the combo +/- qty steppers
 *   - trailing "(+CA$5.00 ea)" from the premium-surcharge display
 * Both are peeled off so we always show clean names like "Kolkata Chicken Biryani".
 */

const QTY_SUFFIX = /\s*[×xX]\s*(\d+)\s*$/;
const SURCHARGE_TAG = /\s*\(\+?[^)]*(ea|each)\s*\)\s*$/i;

function splitQtySuffix(name: string): { name: string; mult: number } {
  if (!name) return { name: "(unnamed)", mult: 1 };
  let s = name;
  let mult = 1;
  for (let i = 0; i < 4; i++) {
    const m1 = QTY_SUFFIX.exec(s);
    const m2 = SURCHARGE_TAG.exec(s);
    if (m1 && (!m2 || m1.index > m2.index)) {
      const n = parseInt(m1[1], 10);
      if (Number.isInteger(n) && n >= 1) mult *= n;
      s = s.slice(0, m1.index).trimEnd();
    } else if (m2) {
      s = s.slice(0, m2.index).trimEnd();
    } else {
      break;
    }
  }
  return { name: s || "(unnamed)", mult };
}

export type ComboItem = {
  name?: string;
  quantity?: number;
  package_selection_names?: string[];
  [k: string]: any;
};

/** Returns [{name, qty}] for the individual dishes in a combo, with duplicates
 * summed and any " × N" suffix folded into the qty. */
export function expandComboPicks(item: ComboItem): { name: string; qty: number }[] {
  const baseQty = Math.max(1, Number(item.quantity || 1));
  const totals = new Map<string, number>();
  for (const raw of item.package_selection_names || []) {
    if (!raw) continue;
    const { name, mult } = splitQtySuffix(raw);
    totals.set(name, (totals.get(name) || 0) + baseQty * mult);
  }
  return [...totals.entries()].map(([name, qty]) => ({ name, qty }));
}
