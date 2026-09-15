/**
 * Small helpers.
 */
export function centsToCAD(c: number): string {
  return `CA$${(c / 100).toFixed(2)}`;
}

const DAY_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAY_LONG  = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/**
 * Build the human "Mon–Thu" / "Fri, Sat" style label from a list of day indices (0=Sun … 6=Sat).
 * Groups consecutive days into ranges for readability.
 */
export function formatDayList(days: number[], long: boolean = false): string {
  if (!days || days.length === 0) return "—";
  const src = long ? DAY_LONG : DAY_SHORT;
  const sorted = [...new Set(days)].filter(d => d >= 0 && d <= 6).sort((a, b) => a - b);
  if (sorted.length === 7) return "Every day";
  // Group consecutive
  const groups: number[][] = [];
  for (const d of sorted) {
    const g = groups[groups.length - 1];
    if (g && g[g.length - 1] + 1 === d) g.push(d);
    else groups.push([d]);
  }
  return groups
    .map(g => (g.length === 1 ? src[g[0]] : g.length === 2 ? `${src[g[0]]}, ${src[g[1]]}` : `${src[g[0]]}–${src[g[g.length - 1]]}`))
    .join(", ");
}

export function buildOperatingHoursLabel(orderingDays: number[], deliveryDays: number[]): string {
  const ord = formatDayList(orderingDays);
  const del = formatDayList(deliveryDays);
  return `${ord} ordering · ${del} delivery`;
}

export function currentWeekDeliverySlots(deliveryDays: number[] = [5, 6]): { date: string; window: string; label: string }[] {
  // Return the next available delivery dates on a ROLLING 7-day window. Previously
  // we only returned slots within the current calendar week (Sunday–Saturday),
  // which meant if today was Thursday and delivery_days=[3] (Wed only) the user
  // would see "windows closed" until next Sunday. Now we always look forward
  // until the customer has at least ONE selectable date.
  const uniqueSorted = [...new Set(deliveryDays)].filter(d => d >= 0 && d <= 6).sort((a, b) => a - b);
  if (uniqueSorted.length === 0) return [];

  const now = new Date();
  const dow = now.getDay(); // JS: Sun=0..Sat=6
  const fmt = (d: Date) => d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  const out: { date: string; window: string; label: string }[] = [];

  // First pass: this calendar week's remaining slots (today or later).
  for (const target of uniqueSorted) {
    const diff = target - dow;
    if (diff < 0) continue;
    const d = new Date(now);
    d.setDate(now.getDate() + diff);
    out.push({
      date: d.toISOString().slice(0, 10),
      window: `${DAY_LONG[target].toLowerCase()}_delivery`,
      label: fmt(d),
    });
  }
  // Second pass: if we found nothing this week, roll into next week's slots so
  // customers can always place an order.
  if (out.length === 0) {
    for (const target of uniqueSorted) {
      const diff = 7 - dow + target; // next occurrence
      const d = new Date(now);
      d.setDate(now.getDate() + diff);
      out.push({
        date: d.toISOString().slice(0, 10),
        window: `${DAY_LONG[target].toLowerCase()}_delivery`,
        label: fmt(d),
      });
    }
  }
  return out;
}

// Deprecated alias kept for reference — not used anymore.
export function nextDeliverySlots(): { date: string; window: string; label: string }[] {
  return currentWeekDeliverySlots();
}

/**
 * Return the very next scheduled delivery date starting from today.
 * Looks up to 14 days ahead so it always finds one for a valid config.
 * Returns null if deliveryDays is empty.
 */
export function nextUpcomingDelivery(deliveryDays: number[] = [5, 6]): { date: string; day: string; label: string } | null {
  const uniqueSorted = [...new Set(deliveryDays)].filter(d => d >= 0 && d <= 6).sort((a, b) => a - b);
  if (uniqueSorted.length === 0) return null;
  const now = new Date();
  const todayDow = now.getDay();
  for (let i = 0; i < 14; i++) {
    const check = (todayDow + i) % 7;
    if (uniqueSorted.includes(check)) {
      const d = new Date(now);
      d.setDate(now.getDate() + i);
      const day = DAY_LONG[check];
      const label = i === 0
        ? `Today, ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`
        : i === 1
        ? `Tomorrow, ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`
        : `${day}, ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
      return { date: d.toISOString().slice(0, 10), day, label };
    }
  }
  return null;
}

/**
 * Return the next occurrence of EACH configured delivery day (chronological).
 * e.g. delivery days [Sun, Mon] → [{label:"Sun, Sep 6"}, {label:"Mon, Sep 7"}].
 */
export function upcomingDeliveryDates(deliveryDays: number[] = [5, 6]): { date: string; label: string }[] {
  const wanted = [...new Set(deliveryDays)].filter(d => d >= 0 && d <= 6);
  if (wanted.length === 0) return [];
  const now = new Date();
  const todayDow = now.getDay();
  const found: Record<number, { date: string; label: string }> = {};
  for (let i = 0; i < 14 && Object.keys(found).length < wanted.length; i++) {
    const check = (todayDow + i) % 7;
    if (wanted.includes(check) && !(check in found)) {
      const d = new Date(now);
      d.setDate(now.getDate() + i);
      found[check] = {
        date: d.toISOString().slice(0, 10),
        label: `${DAY_SHORT[check]}, ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`,
      };
    }
  }
  return Object.values(found).sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * Determine whether the store is accepting orders right now, given the configured
 * ordering days (0=Sun … 6=Sat). If no config is provided we fall back to the legacy
 * Sun–Thu window so existing behavior is preserved.
 */
export function isOrderingWindow(orderingDays?: number[]): { open: boolean; note: string } {
  const days = (orderingDays && orderingDays.length ? orderingDays : [0, 1, 2, 3, 4]);
  const today = new Date().getDay();
  const isOpen = days.includes(today);

  const label = formatDayList(days);
  if (isOpen) {
    return { open: true, note: `Ordering open — ${label}` };
  }

  // Find the next open day for a friendly reopen message
  let nextDay = -1;
  for (let i = 1; i <= 7; i++) {
    const d = (today + i) % 7;
    if (days.includes(d)) { nextDay = d; break; }
  }
  if (nextDay === -1) return { open: false, note: "Orders are currently closed." };
  return {
    open: false,
    note: `Orders reopen ${DAY_LONG[nextDay]}. Slots for today are closed.`,
  };
}
