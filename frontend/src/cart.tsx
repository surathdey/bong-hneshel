/**
 * Cart Context — local state, persisted to AsyncStorage.
 * Items reference menu items (kind="menu") or catering packages (kind="catering").
 *
 * v2 (catering customization): catering items may hold a full selection payload
 * (tier + choice-group picks + premium picks + guest count). Two catering entries
 * for the same package with different selections are kept as separate lines
 * (deduped by cart_item_id, not ref_id).
 */
import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { storage } from "@/src/utils/storage";

export type CateringSelection = {
  tier_id?: string;
  group_selections: Record<string, string[]>; // group_id -> [master_item_id]
  premium_selections: string[]; // master_item_ids
};

export type CartItem = {
  cart_item_id: string;             // unique client-side id
  kind: "menu" | "catering" | "weekly_package";
  ref_id: string;
  name: string;
  price_cents: number;              // menu: unit price. catering: per-person price. weekly_package: flat package price.
  image_url: string;
  quantity: number;
  catering_guest_count?: number;
  catering_selections?: CateringSelection;
  tier_title?: string;              // human-readable tier label for UI
  selection_labels?: { title: string; items: string[] }[]; // human-readable choices for UI
  // Weekly-package fields
  package_selections?: string[];        // master item IDs picked
  package_selection_names?: string[];   // human readable names for cart preview
  package_pick_count?: number;          // X — for display
  weekly_menu_id?: string;
};

type CartState = {
  items: CartItem[];
  add: (i: Omit<CartItem, "quantity" | "cart_item_id">, qty?: number) => void;
  remove: (cart_item_id: string) => void;
  setQty: (cart_item_id: string, qty: number) => void;
  clear: () => void;
  subtotalCents: number;
  count: number;
};

const KEY = "curryco.cart.v2";
const CartContext = createContext<CartState>({
  items: [], add: () => {}, remove: () => {}, setQty: () => {}, clear: () => {},
  subtotalCents: 0, count: 0,
});

const genId = () => `ci_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);

  useEffect(() => {
    (async () => {
      const raw = await storage.getItem<string>(KEY, "");
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as any[];
          // Back-compat: rehydrate old cart entries missing cart_item_id.
          const rehydrated = parsed.map(p => ({
            ...p,
            cart_item_id: p.cart_item_id || genId(),
          })) as CartItem[];
          setItems(rehydrated);
        } catch {}
      }
    })();
  }, []);

  useEffect(() => {
    storage.setItem(KEY, JSON.stringify(items));
  }, [items]);

  const add = useCallback((i: Omit<CartItem, "quantity" | "cart_item_id">, qty = 1) => {
    setItems(prev => {
      // Menu items merge by ref_id (stackable). Catering items DO NOT merge —
      // each customisation is its own line so users can order two configs of
      // the same package.
      if (i.kind === "menu") {
        const existing = prev.find(p => p.kind === "menu" && p.ref_id === i.ref_id);
        if (existing) {
          return prev.map(p =>
            p.cart_item_id === existing.cart_item_id ? { ...p, quantity: p.quantity + qty } : p
          );
        }
      }
      return [...prev, { ...i, quantity: qty, cart_item_id: genId() }];
    });
  }, []);

  const remove = useCallback((cart_item_id: string) => {
    setItems(prev => prev.filter(p => p.cart_item_id !== cart_item_id));
  }, []);

  const setQty = useCallback((cart_item_id: string, qty: number) => {
    setItems(prev => {
      if (qty <= 0) return prev.filter(p => p.cart_item_id !== cart_item_id);
      return prev.map(p => (p.cart_item_id === cart_item_id ? { ...p, quantity: qty } : p));
    });
  }, []);

  const clear = useCallback(() => setItems([]), []);

  const subtotalCents = items.reduce((s, i) => {
    const per = i.price_cents;
    const guests = i.kind === "catering" ? (i.catering_guest_count ?? 1) : 1;
    return s + per * guests * i.quantity;
  }, 0);
  const count = items.reduce((s, i) => s + i.quantity, 0);

  return (
    <CartContext.Provider value={{ items, add, remove, setQty, clear, subtotalCents, count }}>
      {children}
    </CartContext.Provider>
  );
}

export function useCart() { return useContext(CartContext); }
