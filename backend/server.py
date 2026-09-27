"""
Curry & Co. — Backend API
FastAPI + MongoDB + Emergent Google Auth + Stripe Checkout + Emergent Push
"""
from fastapi import FastAPI, APIRouter, HTTPException, Header, Request, Depends, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv, dotenv_values
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
import logging
import html as _html
import uuid
import hashlib
import httpx
import stripe
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone, timedelta, date

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
# The preview container can export a stray global STRIPE_API_KEY that shadows
# backend/.env (load_dotenv does NOT override already-set env vars). For the
# Stripe secret we therefore trust backend/.env as the source of truth.
_ENV_FILE = dotenv_values(ROOT_DIR / ".env")


def _stripe_secret() -> str:
    """Stripe secret key — prefer backend/.env (authoritative for this tenant)
    then fall back to the process environment."""
    return (_ENV_FILE.get("STRIPE_API_KEY") or os.environ.get("STRIPE_API_KEY", "")).strip()

# --- Brand config (name/emails/region — one file to swap on rebrand)
from brand import (
    BRAND_NAME, BRAND_LEGAL_NAME, BRAND_EMAIL_FROM,
    BRAND_ADMIN_EMAIL, BRAND_SUPPORT_EMAIL, BRAND_GUEST_DOMAIN,
    BRAND_DELIVERY_EMAIL, BRAND_REGION,
    as_dict as brand_as_dict,
)

# --- Env
mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
# Stripe secret — required in every environment that processes card payments.
# Do NOT provide a source default here (deployment policy: no secrets in source).
# In preview/dev, `backend/.env` is expected to set STRIPE_API_KEY (Stripe test
# key is fine). In production, Emergent injects the live/test key via the deploy
# panel. If completely unset, the checkout endpoint will refuse to charge.
STRIPE_API_KEY = _stripe_secret()
EMERGENT_PUSH_KEY = os.environ.get("EMERGENT_PUSH_KEY", "placeholder")
# Brand-driven defaults with env overrides (Emergent Deploy Secrets can still
# override for production without touching brand.json).
EMAIL_FROM = os.environ.get("EMAIL_FROM", BRAND_EMAIL_FROM)

# Emergent Auth session-exchange endpoint. Overridable via env for future
# self-hosted auth backends; the default is the managed Emergent Auth relay.
EMERGENT_AUTH_URL = os.environ.get(
    "EMERGENT_AUTH_URL",
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
)

# ---- Auth secrets — MUST come from env in production. -----------------
# Both dev pod (backend/.env) and Emergent Deploy Secrets are expected to
# provide these. We fail fast on prod-only deploys where env vars are missing.
JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALG = "HS256"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", BRAND_ADMIN_EMAIL)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

if not JWT_SECRET:
    raise RuntimeError(
        "SECURITY: JWT_SECRET env var is required. Set it in backend/.env "
        "for local dev or in the Emergent Deploy Secrets panel for production."
    )
if not ADMIN_PASSWORD:
    raise RuntimeError(
        "SECURITY: ADMIN_PASSWORD env var is required. Set it in backend/.env "
        "for local dev or in the Emergent Deploy Secrets panel for production."
    )

# --- Admin auth deps
from passlib.context import CryptContext
from jose import jwt, JWTError

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Mongo
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# --- App
app = FastAPI(title=f"{BRAND_NAME} API")
api = APIRouter(prefix="/api")

# ----------------------------------------------------------------------
# Kubernetes health / readiness probes.
# Deployment ingress hits `GET /health` (root, not /api/health) — MUST return
# 200 OK, otherwise K8s marks the pod NotReady and stops routing traffic to it.
# Keep these responses cheap (no DB calls, no external I/O).
# ----------------------------------------------------------------------
@app.get("/health", include_in_schema=False)
async def _health():
    return {"status": "ok", "service": "curryco-api"}


@app.get("/healthz", include_in_schema=False)
async def _healthz():
    # Alternate probe path used by some K8s configurations.
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def _root():
    # If the Expo web bundle exists (production deploy), serve the SPA entry
    # so admins hitting the root see the app; otherwise return JSON status
    # (K8s probes rely on this being fast).
    if WEB_DIST.exists() and (WEB_DIST / "index.html").exists():
        return FileResponse(str(WEB_DIST / "index.html"), headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        })
    return {"service": "curryco-api", "status": "ok", "docs": "/docs", "web_bundle": "missing"}


# --- Uploaded images (AI-generated menu photos, etc.) served under /api/uploads/*
UPLOADS_DIR = Path("/app/backend/uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
(UPLOADS_DIR / "menu").mkdir(parents=True, exist_ok=True)
(UPLOADS_DIR / "delivery").mkdir(parents=True, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# ---------------------------------------------------------------
# SPA static serving — production + preview.
# The Expo web bundle can live in one of two locations:
#   1. /app/backend/web_dist/       (production — bundled inside backend so it
#                                    ships with the K8s image regardless of
#                                    whether the frontend directory is copied)
#   2. /app/frontend/dist/          (preview — created by `expo export` during
#                                    local dev / `yarn install` postinstall)
# We prefer (1) so production always has a working admin webapp. Any refresh
# in preview automatically re-syncs (1) via the sync helper below.
# ---------------------------------------------------------------
_WEB_DIST_PROD = Path("/app/backend/web_dist")
_WEB_DIST_PREVIEW = Path("/app/frontend/dist")

def _resolve_web_dist() -> Optional[Path]:
    for p in (_WEB_DIST_PROD, _WEB_DIST_PREVIEW):
        if p.exists() and (p / "index.html").exists():
            return p
    return None

WEB_DIST = _resolve_web_dist() or _WEB_DIST_PROD  # used by handlers below

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("curryco")

# --- Emergent Push relay
_push_client = httpx.AsyncClient(
    base_url="https://integrations.emergentagent.com",
    headers={"X-Push-Key": EMERGENT_PUSH_KEY},
    timeout=10.0,
)


async def send_push(recipients: List[str], data: dict, idempotency_key: Optional[str] = None):
    if not recipients:
        return
    if "title" not in data or "message" not in data:
        raise ValueError("push data must include title and message")
    payload: dict = {"recipients": recipients, "data": data}
    if idempotency_key:
        payload["$idempotency_key"] = idempotency_key
    try:
        resp = await _push_client.post("/api/v1/push/trigger", json=payload)
        if resp.status_code >= 400:
            log.warning(f"push relay non-2xx {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log.warning(f"push relay error (non-blocking): {e}")


# --- Email (MOCKED — logs only)
async def send_email(to: str, subject: str, body: str):
    log.info(f"[EMAIL MOCK] to={to} subject={subject!r} body={body[:120]}...")


# --- Stripe (hosted Checkout Session) -----------------------------------
# Card payments (incl. Apple Pay / Google Pay / cards) run through Stripe's
# hosted Checkout page. The secret key lives ONLY here in the backend.
# Enable eligible methods (Cards, Apple Pay, Google Pay) in the Stripe
# Dashboard → Settings → Payment methods; Checkout shows them automatically.
def _stripe():
    """Return the configured Stripe SDK, or 503 if STRIPE_API_KEY is unset."""
    key = _stripe_secret()
    if not key:
        raise HTTPException(
            503,
            "Card payments are not configured on this deployment yet. "
            "Please use Cash on Delivery or Interac e-Transfer.",
        )
    stripe.api_key = key
    return stripe


# ==========================================================
# MODELS
# ==========================================================
class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    phone: Optional[str] = None
    default_address: Optional[dict] = None
    loyalty_points: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    role: str = "customer"  # customer | admin | delivery_partner


class MenuItem(BaseModel):
    item_id: str = Field(default_factory=lambda: f"item_{uuid.uuid4().hex[:10]}")
    name: str
    description: str
    price_cents: int
    image_url: str
    category: str  # "veg", "non-veg", "rice", "dessert", "starter", "curry"
    tags: List[str] = []
    is_featured: bool = False


class MasterMenuItem(BaseModel):
    """Permanent menu item repository. Reused across weekly menus."""
    item_id: str = Field(default_factory=lambda: f"mi_{uuid.uuid4().hex[:10]}")
    name: str
    short_description: str = ""
    full_description: str = ""
    category: str  # starter | main-veg | main-non-veg | dessert | beverage | rice | curry | side | bread
    cuisine: str = "bengali"  # bengali | north-indian | south-indian | indo-chinese | fusion
    default_price_cents: int
    cost_price_cents: int = 0  # visible to super admin only (client should mask for others)
    image_url: str = ""  # public URL OR data URI (base64)
    extra_images: List[str] = []
    veg_type: str = "vegetarian"  # vegetarian | non-vegetarian | eggitarian
    spice_level: str = "medium"  # mild | medium | hot
    allergens: List[str] = []  # dairy | nuts | seafood | gluten
    is_active: bool = True
    always_available: bool = False  # orderable any time, independent of weekly menu
    prep_notes: str = ""
    kitchen_notes: str = ""
    display_order: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WeeklyMenuLine(BaseModel):
    """Line in a weekly menu — references a MasterMenuItem with optional overrides."""
    line_id: str = Field(default_factory=lambda: f"wl_{uuid.uuid4().hex[:10]}")
    master_item_id: str
    price_override_cents: Optional[int] = None
    availability: str = "available"  # available | low_inventory | sold_out
    stock_limit: Optional[int] = None
    stock_used: int = 0
    is_featured: bool = False
    display_order: int = 0
    # Per-week à-la-carte visibility. When a new week copies ALL master items,
    # they are added hidden (is_visible=False) and the admin turns on the ones
    # they want customers to see this week. Manually-added lines default visible.
    is_visible: bool = True


class WeeklyMenuPackage(BaseModel):
    """Weekly-menu combo: customer picks X items from an eligible pool for a flat price."""
    package_id: str = Field(default_factory=lambda: f"wpkg_{uuid.uuid4().hex[:10]}")
    name: str = "This Week's Combo"
    description: str = ""
    price_cents: int = 0
    pick_count: int = 3  # X — number of items customer must pick
    eligible_master_ids: List[str] = []  # subset of master items in this week's lines; empty = all
    # Per-item surcharge (in cents) added on TOP of the flat package price for every portion
    # the customer picks of that specific item. e.g. {"mi_mutton": 500, "mi_ilish": 1000}.
    item_surcharges_cents: Dict[str, int] = {}
    image_url: str = ""
    # ---- Composition-based pricing (Mustard Garden weekly plan) ----
    # When pricing_mode == "composition", the flat `price_cents` is ignored and
    # the total is chosen by the veg/non-veg makeup of the customer's picks:
    #   all picks vegetarian            -> veg_price_cents
    #   all picks non-veg (incl. egg)   -> nonveg_price_cents
    #   any mix of veg + non-veg        -> mixed_price_cents
    # Egg dishes (veg_type == "eggitarian") count as NON-VEG here.
    pricing_mode: str = "flat"          # "flat" | "composition"
    veg_price_cents: int = 0
    mixed_price_cents: int = 0
    nonveg_price_cents: int = 0
    # Display-only freebies shown with the plan; customer CANNOT select these.
    complimentary_master_ids: List[str] = []


class WeeklyMenu(BaseModel):
    menu_id: str = Field(default_factory=lambda: f"menu_{uuid.uuid4().hex[:10]}")
    week_start: str  # ISO date string of Sunday (YYYY-MM-DD)
    week_end: Optional[str] = None
    title: str
    description: str = ""
    banner_image_url: str = ""
    items: List[MenuItem] = []  # legacy embedded — deprecated but kept for back-compat
    lines: List[WeeklyMenuLine] = []  # new: references to Master Menu with overrides
    # Week-level complimentary dishes (display-only freebies). Shown to customers
    # ONLY when the Weekly Package is enabled. Selected from the Master Menu.
    complimentary_master_ids: List[str] = []
    published: bool = True
    status: str = "published"  # draft | scheduled | published
    # Weekly-menu mode toggles (v3)
    alacarte_enabled: bool = True
    package_enabled: bool = False
    package: Optional[WeeklyMenuPackage] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaymentMethodConfig(BaseModel):
    """Per-payment-method config. Each method has its own enable/HST toggle plus method-specific settings."""
    enabled: bool = True
    tax_enabled: bool = True   # apply HST to orders using this method?
    # method-specific (all optional):
    publishable_key: Optional[str] = None   # Stripe
    secret_key: Optional[str] = None        # Stripe (SENSITIVE — never returned to public /settings)
    client_id: Optional[str] = None         # PayPal
    client_secret: Optional[str] = None     # PayPal (SENSITIVE)
    email: Optional[str] = None             # Interac e-Transfer email address
    instructions: Optional[str] = None      # Free-text shown to customer (e.g. Interac note pattern)


class BusinessSettings(BaseModel):
    key: str = "default"
    business_name: str = BRAND_NAME
    kitchen_address: str = "6941 Derry Rd West, Milton, ON, Canada"
    phone: str = ""
    email: str = BRAND_EMAIL_FROM
    operating_hours: str = "Sun–Thu ordering · Fri/Sat delivery"
    # Structured schedule (0=Sun, 1=Mon, ..., 6=Sat). Drives the customer-app
    # "orders open/closed" banner and next-delivery-slot logic.
    ordering_days: List[int] = [0, 1, 2, 3, 4]   # Sun–Thu
    delivery_days: List[int] = [5, 6]            # Fri–Sat
    delivery_areas: List[str] = ["Toronto", "Mississauga", "Brampton", "Markham"]
    default_delivery_fee_cents: int = 599
    minimum_order_cents: int = 0
    # Distance-based delivery fee tiers, measured (driving) from `kitchen_address`.
    # Each tier: {max_km, fee_cents}. A destination is charged the first tier whose
    # max_km it falls within (ascending). Beyond the largest tier, `delivery_fee_over_max_cents`.
    delivery_fee_tiers: List[dict] = [
        {"max_km": 20, "fee_cents": 0},
        {"max_km": 40, "fee_cents": 500},
        {"max_km": 75, "fee_cents": 1000},
    ]
    delivery_fee_over_max_cents: int = 1500
    # Restaurant owner notification targets. Every new order + every delivery
    # sends a copy here (email always; SMS if a phone + Twilio are set).
    notify_email: str = ""
    notify_phone: str = ""
    # Customer-app home-hero tagline. Explains the ordering model in one line,
    # e.g. "We take orders all week and deliver on Monday." Configurable per
    # tenant because different restaurants operate on different schedules.
    home_hero_tagline: str = "Order anytime this week — we deliver every weekend."
    # Global "Always Available" menu — master item ids orderable any time,
    # independent of the weekly plan. Admin picks these from the Master Menu on
    # a dedicated screen; changes reflect on the customer app immediately.
    always_available_master_ids: List[str] = []
    # Legacy global tax toggle — kept as a fallback for methods that don't specify their own.
    tax_enabled: bool = True
    tax_rate_bps: int = 1300  # basis points; 1300 = 13% HST
    tax_label: str = "HST"
    currency: str = BRAND_REGION.get("currency", "CAD")
    company_info: str = ""
    # ----- Loyalty points program -----
    # Only logged-in (non-guest) customers earn/redeem. Fully configurable:
    #   earn:   loyalty_earn_points_per_dollar points for every $1 spent (subtotal)
    #   redeem: loyalty_redeem_points_per_dollar points = $1 off a future order
    loyalty_enabled: bool = True
    loyalty_earn_points_per_dollar: int = 1
    loyalty_redeem_points_per_dollar: int = 100
    # Per-payment-method configuration.
    # Card (Stripe) shows Apple Pay / Google Pay / cards on the hosted page.
    payment_methods: Dict[str, PaymentMethodConfig] = Field(default_factory=lambda: {
        "stripe":  PaymentMethodConfig(enabled=True,  tax_enabled=False),
        "paypal":  PaymentMethodConfig(enabled=False, tax_enabled=True),
        "cod":     PaymentMethodConfig(enabled=True,  tax_enabled=True),
        "interac": PaymentMethodConfig(enabled=True,  tax_enabled=True,
                                        email=BRAND_EMAIL_FROM,
                                        instructions="Please note your order ID in the message field."),
    })


class CateringChoiceGroup(BaseModel):
    """A group of dishes where customer must pick N (min–max) options."""
    group_id: str = Field(default_factory=lambda: f"grp_{uuid.uuid4().hex[:8]}")
    title: str  # e.g. "Snack", "3 Veg Items", "Dessert"
    subtitle: str = ""  # e.g. "Choose Any 3"
    min_select: int = 1
    max_select: int = 1
    option_master_ids: List[str] = []  # references to MasterMenuItem.item_id
    display_order: int = 0


class CateringUpgradeTier(BaseModel):
    """Alternate per-person price tier that may override choice-group counts."""
    tier_id: str = Field(default_factory=lambda: f"tier_{uuid.uuid4().hex[:8]}")
    title: str  # "Base tier" | "Snack + Tea upgrade"
    subtitle: str = ""
    per_person_cents: int
    # Overrides group min/max in this tier: {group_id: {"min_select": N, "max_select": N}}
    group_overrides: Dict[str, Dict[str, int]] = {}
    is_default: bool = True


class CateringPremiumItem(BaseModel):
    """Marks a master item as premium — customer pays extra per-person if selected."""
    master_item_id: str
    upcharge_per_person_cents: int


class CateringPackage(BaseModel):
    package_id: str = Field(default_factory=lambda: f"cat_{uuid.uuid4().hex[:10]}")
    name: str
    tagline: str = ""
    description: str = ""
    emoji: str = "🍽️"
    perfect_for: str = ""  # e.g. "Weddings · Puja Celebrations"
    price_cents: int = 0  # per-person price (fallback if no tiers)
    min_guests: int = 10
    image_url: str = ""
    includes: List[str] = []  # legacy free-text (back-compat + always-included display)
    included_master_ids: List[str] = []  # always-served master items
    choice_groups: List[CateringChoiceGroup] = []
    upgrade_tiers: List[CateringUpgradeTier] = []
    premium_items: List[CateringPremiumItem] = []
    is_custom_quote: bool = False  # if True, show contact form instead of Add-to-Bag
    contact_email: str = ""
    contact_phone: str = ""
    is_featured: bool = False
    is_active: bool = True
    sort_order: int = 0


class Coupon(BaseModel):
    code: str
    discount_type: str  # "percent" | "fixed"
    value: int  # percent (0-100) OR cents
    active: bool = True
    min_order_cents: int = 0
    description: str = ""
    first_time_only: bool = False  # redeemable only by logged-in users on their first order


class CateringSelection(BaseModel):
    """Customer's picks when adding a catering package to bag."""
    tier_id: Optional[str] = None
    # {group_id: [master_item_id, ...]}
    group_selections: Dict[str, List[str]] = {}
    # Master item IDs from the premium list — each adds its upcharge per person.
    premium_selections: List[str] = []


class OrderItemIn(BaseModel):
    kind: str  # "menu" | "catering" | "weekly_package"
    ref_id: str  # item_id | package_id | weekly_menu_id
    quantity: int
    catering_guest_count: Optional[int] = None  # for catering only
    catering_selections: Optional[CateringSelection] = None
    package_selections: Optional[List[str]] = None  # weekly_package master_ids picked


class Address(BaseModel):
    # Optional recipient name attached to this address. When present, the
    # admin Orders list uses it as `customer_name` (see the resolver in
    # /admin/orders + admin_orders/list). Lets guests type their real name
    # at checkout so orders don't show up as "Guest 1", "Guest 2".
    name: Optional[str] = ""
    email: Optional[str] = ""   # customer email captured at checkout (order confirmation + invoice)
    line1: str
    line2: Optional[str] = ""
    city: str = "Toronto"
    province: str = "ON"
    postal_code: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    instructions: Optional[str] = ""


class DeliverySlot(BaseModel):
    date: str  # YYYY-MM-DD
    window: str  # "friday_evening" | "saturday_morning"


class QuoteOrderReq(BaseModel):
    """Pre-checkout quote. Phone optional (customer may not have filled it yet)."""
    items: List[OrderItemIn]
    address: Address
    slot: DeliverySlot
    phone: Optional[str] = ""
    coupon_code: Optional[str] = None
    redeem_points: int = 0
    special_instructions: Optional[str] = ""
    payment_method: str = "card"


class CreateOrderReq(BaseModel):
    items: List[OrderItemIn]
    address: Address
    slot: DeliverySlot
    phone: str  # REQUIRED — contact phone captured at checkout
    coupon_code: Optional[str] = None
    redeem_points: int = 0  # points to redeem (1 pt = 1 cent)
    special_instructions: Optional[str] = ""
    payment_method: str = "card"  # "card" (Stripe) | "cod" (Cash on Delivery)
    # The public origin the customer is on (e.g. https://xyz.preview...). Used as a
    # fallback to build absolute invoice/tracking links in SMS/email.
    client_base_url: Optional[str] = None


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: f"ord_{uuid.uuid4().hex[:10]}")
    user_id: str
    items_snapshot: List[dict]
    address: dict
    slot: dict
    phone: str = ""
    subtotal_cents: int
    delivery_fee_cents: int
    tax_cents: int = 0
    tax_label: str = "HST"
    discount_cents: int
    points_redeemed_cents: int
    total_cents: int
    coupon_code: Optional[str] = None
    special_instructions: Optional[str] = ""
    payment_method: str = "card"  # "card" | "cod"
    status: str = "pending_payment"
    payment_status: str = "pending"
    stripe_session_id: Optional[str] = None
    points_awarded: int = 0
    refund_status: Optional[str] = None  # None | "requested" | "refunded"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tracking_events: List[dict] = []
    # Public origin captured at checkout for building absolute invoice/tracking links.
    public_base_url: Optional[str] = None
    # ---- Delivery assignment (v3) ----
    delivery_partner_id: Optional[str] = None  # DeliveryPartner.partner_id
    delivery_status: Optional[str] = None      # unassigned | assigned | picked_up | on_the_way | arrived | delivered
    delivery_partner_name: Optional[str] = None
    delivery_partner_phone: Optional[str] = None
    delivery_partner_lat: Optional[float] = None
    delivery_partner_lng: Optional[float] = None
    delivery_partner_updated_at: Optional[datetime] = None
    delivery_eta_seconds: Optional[int] = None
    delivery_eta_updated_at: Optional[datetime] = None
    delivery_route_order: Optional[int] = None  # index in optimized route
    delivery_proof_photo_url: Optional[str] = None  # proof-of-delivery photo

class DeliveryPartner(BaseModel):
    partner_id: str = Field(default_factory=lambda: f"dp_{uuid.uuid4().hex[:10]}")
    name: str
    email: str
    phone: str = ""
    vehicle: str = "car"           # "car" | "bike" | "scooter"
    password_hash: str = ""
    is_active: bool = True
    # Live location
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    current_location_updated_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeliveryPartnerApplication(BaseModel):
    app_id: str = Field(default_factory=lambda: f"dp_{uuid.uuid4().hex[:10]}")
    user_id: Optional[str] = None
    full_name: str
    email: str
    phone: str
    city: str
    vehicle: str  # "car" | "bike" | "scooter"
    availability: str  # "part_time" | "full_time" | "weekends"
    experience: Optional[str] = ""
    status: str = "submitted"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PushRegisterReq(BaseModel):
    user_id: str
    platform: str
    device_token: str


# ==========================================================
# AUTH
# ==========================================================
async def _current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    exp = session.get("expires_at")
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired")
    user_doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    return User(**user_doc)


async def _current_admin(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing admin bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(401, "Invalid admin token")
    if payload.get("role") != "admin":
        raise HTTPException(403, "Not an admin token")
    return {"email": payload.get("sub"), "role": "admin"}


class SessionInReq(BaseModel):
    session_token: str


@api.post("/auth/guest")
async def create_guest_session():
    """Create a lightweight guest user + 7-day session token. No email verification."""
    guest_id = f"guest_{uuid.uuid4().hex[:12]}"
    user = User(
        user_id=guest_id,
        email=f"{guest_id}@{BRAND_GUEST_DOMAIN}",
        name="Guest",
        role="guest",
    )
    await db.users.insert_one(user.model_dump())
    token = f"guest-{uuid.uuid4().hex}"
    session_doc = {
        "session_token": token,
        "user_id": user.user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
    }
    await db.user_sessions.insert_one(session_doc)
    return {"session_token": token, "user": user.model_dump()}


@api.post("/auth/session")
async def create_session(req: SessionInReq):
    """Frontend exchanges Emergent's session_token for our session (validates + upserts user)."""
    async with httpx.AsyncClient(timeout=10.0) as hc:
        r = await hc.get(
            EMERGENT_AUTH_URL,
            headers={"X-Session-ID": req.session_token},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session token")
    data = r.json()
    email = data["email"]
    name = data.get("name") or email.split("@")[0]
    picture = data.get("picture")

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user = User(**existing)
    else:
        user = User(
            user_id=f"user_{uuid.uuid4().hex[:12]}",
            email=email,
            name=name,
            picture=picture,
        )
        await db.users.insert_one(user.model_dump())

    session_doc = {
        "session_token": data["session_token"],
        "user_id": user.user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
    }
    await db.user_sessions.update_one(
        {"session_token": data["session_token"]},
        {"$set": session_doc},
        upsert=True,
    )
    return {"session_token": data["session_token"], "user": user.model_dump()}


@api.get("/auth/me")
async def me(user: User = Depends(_current_user)):
    return user.model_dump()


@api.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}


# --------------------------------------------------------------
# Email + password auth. Issues the SAME opaque session_token that
# Google/guest login use, so `_current_user` keeps working unchanged.
# Password reset uses a 6-digit code emailed via the Resend integration.
# --------------------------------------------------------------
_RESET_CODE_TTL_MIN = 15
_RESET_MAX_ATTEMPTS = 5
_DUMMY_PW_HASH = _pwd.hash("dummy-password-to-equalize-timing")


async def _issue_customer_session(user_id: str, days: int = 30) -> str:
    token = f"pw-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    await db.user_sessions.insert_one({
        "session_token": token,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=days),
    })
    return token


def _norm_email(v: str) -> str:
    return (v or "").strip().lower()


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class EmailRegisterReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = None


class EmailLoginReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordReq(BaseModel):
    email: EmailStr


class ResetPasswordReq(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)
    password: str = Field(min_length=8, max_length=128)


@api.post("/auth/register")
async def register_with_email(req: EmailRegisterReq):
    """Create a customer account with email + password; returns a session token."""
    email = _norm_email(str(req.email))
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        raise HTTPException(409, "An account with this email already exists. Try signing in instead.")
    name = (req.name or "").strip() or email.split("@")[0]
    user = User(user_id=f"user_{uuid.uuid4().hex[:12]}", email=email, name=name, role="customer")
    doc = user.model_dump()
    doc["password_hash"] = _pwd.hash(req.password)
    doc["provider"] = "password"
    await db.users.insert_one(doc)
    token = await _issue_customer_session(user.user_id)
    return {"session_token": token, "user": user.model_dump()}


@api.post("/auth/login")
async def login_with_email(req: EmailLoginReq):
    """Log in an existing customer with email + password."""
    email = _norm_email(str(req.email))
    user_doc = await db.users.find_one({"email": email}, {"_id": 0})
    stored = user_doc.get("password_hash") if user_doc else None
    ok = False
    try:
        # Always run a verify (against a dummy hash when missing) to equalize timing.
        ok = _pwd.verify(req.password, stored or _DUMMY_PW_HASH)
    except Exception:
        ok = False
    if not user_doc or not stored or not ok:
        raise HTTPException(401, "Incorrect email or password")
    user = User(**user_doc)
    token = await _issue_customer_session(user.user_id)
    return {"session_token": token, "user": user.model_dump()}


@api.post("/auth/forgot-password")
async def forgot_password(req: ForgotPasswordReq):
    """Email a single-use 6-digit reset code. Always returns a generic response."""
    email = _norm_email(str(req.email))
    generic = {"ok": True, "message": "If an account exists for that email, a reset code has been sent."}
    user_doc = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
    if not user_doc:
        return generic
    code = f"{_secrets.randbelow(1000000):06d}"
    await db.password_reset_codes.delete_many({"email": email})
    await db.password_reset_codes.insert_one({
        "email": email,
        "code_hash": _code_hash(code),
        "attempts": 0,
        "used": False,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=_RESET_CODE_TTL_MIN),
    })
    try:
        html_body = (
            "<p>Hi,</p>"
            f"<p>Your {_html.escape(BRAND_NAME)} password reset code is:</p>"
            f"<p style='font-size:28px;font-weight:700;letter-spacing:4px'>{code}</p>"
            f"<p>This code expires in {_RESET_CODE_TTL_MIN} minutes. "
            "If you did not request this, you can safely ignore this email.</p>"
        )
        await _email.send_email(to=email, subject=f"{BRAND_NAME} — Your password reset code", html=html_body)
    except Exception as e:
        log.warning(f"reset email send failed: {e}")
    return generic


@api.post("/auth/reset-password")
async def reset_password(req: ResetPasswordReq):
    """Verify the emailed code and set a new password; invalidates all sessions."""
    email = _norm_email(str(req.email))
    now = datetime.now(timezone.utc)
    rec = await db.password_reset_codes.find_one({"email": email})

    def _bad():
        raise HTTPException(400, "Invalid or expired reset code")

    if not rec or rec.get("used"):
        _bad()
    exp = rec.get("expires_at")
    if isinstance(exp, datetime) and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if not exp or exp < now:
        _bad()
    if rec.get("attempts", 0) >= _RESET_MAX_ATTEMPTS:
        _bad()
    if _code_hash(req.code) != rec.get("code_hash"):
        await db.password_reset_codes.update_one({"_id": rec["_id"]}, {"$inc": {"attempts": 1}})
        _bad()
    user_doc = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
    if not user_doc:
        _bad()
    await db.password_reset_codes.update_one({"_id": rec["_id"]}, {"$set": {"used": True, "used_at": now}})
    await db.users.update_one(
        {"email": email},
        {"$set": {"password_hash": _pwd.hash(req.password), "provider": "password"}},
    )
    # Force re-login everywhere after a password change.
    await db.user_sessions.delete_many({"user_id": user_doc["user_id"]})
    return {"ok": True, "message": "Password updated. You can now sign in."}


# --------------------------------------------------------------
# Account deletion — required for App Store & Play Store review.
# Hard-deletes profile + sessions; anonymises past orders (kept for
# tax/legal recordkeeping but with PII stripped).
# --------------------------------------------------------------
@api.delete("/user/me")
async def delete_my_account(user: User = Depends(_current_user)):
    uid = user.user_id
    # Anonymise historical orders so financial records survive audit,
    # but no personal data (name / email / phone / address) remains.
    await db.orders.update_many(
        {"user_id": uid},
        {"$set": {
            "user_id": f"deleted_{uid[:8]}",
            "customer_name": "Deleted user",
            "customer_email": "",
            "customer_phone": "",
            "delivery_address": {"line1": "REDACTED", "line2": "", "city": "", "postal_code": ""},
            "instructions": "",
        }}
    )
    # Delete auth sessions, push tokens, saved addresses.
    await db.user_sessions.delete_many({"user_id": uid})
    await db.push_tokens.delete_many({"user_id": uid})
    # Finally, delete the user record itself.
    await db.users.delete_one({"user_id": uid})
    return {"ok": True, "deleted": True}


# ==========================================================
# USER PROFILE — saved address
# ==========================================================
class SavedAddressReq(BaseModel):
    line1: str
    line2: Optional[str] = ""
    city: Optional[str] = "Toronto"
    province: Optional[str] = "ON"
    postal_code: str


@api.post("/me/address")
async def save_default_address(req: SavedAddressReq, user: User = Depends(_current_user)):
    """Store this customer's default delivery address so the Bag screen can pre-fill it next time."""
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"default_address": req.model_dump()}},
    )
    return {"ok": True}


@api.delete("/me/address")
async def clear_default_address(user: User = Depends(_current_user)):
    await db.users.update_one({"user_id": user.user_id}, {"$unset": {"default_address": ""}})
    return {"ok": True}


# ==========================================================
# GOOGLE PLACES AUTOCOMPLETE (proxied so the API key stays on the server)
# ==========================================================
@api.get("/places/autocomplete")
async def places_autocomplete(q: str, session_token: Optional[str] = None):
    """Return address suggestions for the given partial query. Restricted to Canada."""
    q = (q or "").strip()
    if len(q) < 3:
        return {"predictions": []}
    if not GOOGLE_MAPS_API_KEY or GOOGLE_MAPS_API_KEY.startswith("AIzaSy_PLACEHOLDER"):
        return {"predictions": []}
    params = {
        "input": q,
        "key": GOOGLE_MAPS_API_KEY,
        "types": "address",
        "components": "country:ca",   # keep the deliverable zone tight
        "language": "en",
    }
    if session_token:
        params["sessiontoken"] = session_token
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://maps.googleapis.com/maps/api/place/autocomplete/json", params=params)
            data = r.json()
            if data.get("status") not in ("OK", "ZERO_RESULTS"):
                logging.warning(f"[places.autocomplete] status={data.get('status')} error={data.get('error_message')}")
                return {"predictions": [], "warning": data.get("status")}
            return {
                "predictions": [
                    {
                        "place_id": p["place_id"],
                        "description": p["description"],
                        "main_text": p.get("structured_formatting", {}).get("main_text", ""),
                        "secondary_text": p.get("structured_formatting", {}).get("secondary_text", ""),
                    }
                    for p in data.get("predictions", [])[:6]
                ],
            }
    except Exception as e:
        logging.exception(f"[places.autocomplete] {e}")
        return {"predictions": []}


@api.get("/places/details")
async def places_details(place_id: str, session_token: Optional[str] = None):
    """Fetch a Places details record and return a structured address (line1/city/postal)."""
    if not GOOGLE_MAPS_API_KEY or GOOGLE_MAPS_API_KEY.startswith("AIzaSy_PLACEHOLDER"):
        return {"ok": False, "error": "Google Maps API key not configured"}
    params = {
        "place_id": place_id,
        "key": GOOGLE_MAPS_API_KEY,
        "fields": "formatted_address,address_components,geometry",
        "language": "en",
    }
    if session_token:
        params["sessiontoken"] = session_token
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://maps.googleapis.com/maps/api/place/details/json", params=params)
            data = r.json()
            if data.get("status") != "OK":
                return {"ok": False, "error": data.get("status")}
            result = data["result"]
            comps = result.get("address_components", [])

            def find(*types) -> str:
                for c in comps:
                    if any(t in c["types"] for t in types):
                        return c.get("short_name") or c.get("long_name") or ""
                return ""

            street_number = find("street_number")
            route = find("route")
            line1 = " ".join([x for x in [street_number, route] if x]).strip()
            city = find("locality", "sublocality", "sublocality_level_1", "administrative_area_level_2")
            province = find("administrative_area_level_1")
            postal = find("postal_code")
            country = find("country")
            geom = result.get("geometry", {}).get("location", {})
            return {
                "ok": True,
                "address": {
                    "line1": line1,
                    "city": city or "",
                    "province": province or "ON",
                    "postal_code": postal or "",
                    "country": country or "CA",
                    "lat": geom.get("lat"),
                    "lng": geom.get("lng"),
                    "formatted": result.get("formatted_address"),
                },
            }
    except Exception as e:
        logging.exception(f"[places.details] {e}")
        return {"ok": False, "error": str(e)}


# ==========================================================
# MENU
# ==========================================================
def _sunday_of(d: date) -> date:
    """Sunday of the week containing d (weekday: Mon=0..Sun=6). We want Sunday."""
    # weekday: Sun == 6 in python
    days_since_sun = (d.weekday() + 1) % 7  # Sun->0, Mon->1, ..., Sat->6
    return d - timedelta(days=days_since_sun)


async def _hydrate_menu(doc: dict) -> dict:
    """If the weekly menu uses `lines` (master-refs), inflate them to a `items` array
    the frontend already understands, applying price overrides & availability."""
    if not doc:
        return doc
    lines = doc.get("lines") or []
    if not lines:
        return doc
    inflated = []
    for line in lines:
        if line.get("is_visible", True) is False:
            continue  # hidden this week — admin hasn't turned it on for customers
        mi = await db.master_menu.find_one({"item_id": line["master_item_id"]}, {"_id": 0})
        if not mi or not mi.get("is_active", True):
            continue
        price = line.get("price_override_cents") or mi["default_price_cents"]
        avail = line.get("availability", "available")
        stock_limit = line.get("stock_limit")
        stock_used = line.get("stock_used", 0)
        if stock_limit is not None and stock_used >= stock_limit:
            avail = "sold_out"
        inflated.append({
            "item_id": line["master_item_id"],
            "line_id": line["line_id"],
            "name": mi["name"],
            "description": mi.get("short_description") or mi.get("full_description", ""),
            "price_cents": price,
            "image_url": mi.get("image_url", ""),
            "category": mi.get("category", "curry"),
            "tags": [mi.get("veg_type", ""), mi.get("spice_level", "")],
            "is_featured": line.get("is_featured", False),
            "availability": avail,
            "veg_type": mi.get("veg_type"),
            "spice_level": mi.get("spice_level"),
            "allergens": mi.get("allergens", []),
        })
    # If there are also legacy embedded items, keep them appended for back-compat.
    inflated.extend(doc.get("items", []) or [])
    out = dict(doc)
    out["items"] = inflated
    # Resolve complimentary items (display-only). Week-level list takes priority,
    # falling back to the legacy package-level list. Shown to customers ONLY when
    # the Weekly Package is enabled (per product spec).
    pkg = out.get("package") or {}
    comp_ids: List[str] = []
    if out.get("package_enabled"):
        comp_ids = out.get("complimentary_master_ids") or pkg.get("complimentary_master_ids") or []
    comps = []
    if comp_ids:
        by_id = {}
        async for m in db.master_menu.find({"item_id": {"$in": comp_ids}}, {"_id": 0}):
            by_id[m["item_id"]] = m
        for cid in comp_ids:  # preserve admin's chosen order
            m = by_id.get(cid)
            if not m or m.get("is_active") is False:
                continue
            comps.append({
                "item_id": m["item_id"],
                "name": m["name"],
                "description": m.get("short_description") or m.get("full_description", ""),
                "image_url": m.get("image_url", ""),
                "category": m.get("category", ""),
            })
    out["complimentary_items"] = comps
    return out


@api.get("/menu/current")
async def menu_current():
    today = datetime.now(timezone.utc).date()
    week_start = _sunday_of(today).isoformat()
    doc = await db.weekly_menus.find_one(
        {"week_start": week_start, "published": True, "status": {"$ne": "draft"}},
        {"_id": 0},
    )
    if not doc:
        cur = db.weekly_menus.find(
            {"published": True, "status": {"$ne": "draft"}}, {"_id": 0}
        ).sort("week_start", -1).limit(1)
        docs = await cur.to_list(1)
        doc = docs[0] if docs else None
    return await _hydrate_menu(doc) if doc else None


@api.get("/menu/upcoming")
async def menu_upcoming():
    today = datetime.now(timezone.utc).date()
    week_start = _sunday_of(today).isoformat()
    cur = db.weekly_menus.find(
        {"week_start": {"$gt": week_start}, "published": True, "status": {"$ne": "draft"}}, {"_id": 0}
    ).sort("week_start", 1)
    docs = await cur.to_list(20)
    return [await _hydrate_menu(d) for d in docs]


@api.get("/menu/history")
async def menu_history():
    cur = db.weekly_menus.find({}, {"_id": 0}).sort("week_start", -1).limit(20)
    return await cur.to_list(20)


@api.get("/menu/anytime")
async def menu_anytime():
    """Global "Always Available" menu — master items the admin picked on the
    Always Available screen (settings.always_available_master_ids). Orderable any
    time, independent of the weekly plan (e.g. Roti, Biryani, Rolls). Falls back
    to the legacy `always_available` master flag when no global list is set."""
    settings = await _get_settings()
    ids = settings.get("always_available_master_ids") or []
    out = []
    if ids:
        by_id = {}
        async for m in db.master_menu.find(
            {"item_id": {"$in": ids}, "is_active": {"$ne": False}}, {"_id": 0}
        ):
            by_id[m["item_id"]] = m
        ordered = [by_id[i] for i in ids if i in by_id]
        ordered.sort(key=lambda m: (m.get("name") or "").lower())
        cur_items = ordered
    else:
        cur = db.master_menu.find(
            {"always_available": True, "is_active": {"$ne": False}}, {"_id": 0}
        ).sort([("display_order", 1), ("name", 1)])
        cur_items = [m async for m in cur]
    for m in cur_items:
        out.append({
            "item_id": m["item_id"],
            "name": m["name"],
            "description": m.get("short_description") or m.get("full_description", ""),
            "price_cents": m.get("default_price_cents", 0),
            "image_url": m.get("image_url", ""),
            "category": m.get("category", ""),
            "tags": [m.get("veg_type", ""), m.get("spice_level", "")],
            "veg_type": m.get("veg_type", "vegetarian"),
            "spice_level": m.get("spice_level", "medium"),
            "allergens": m.get("allergens", []),
            "is_featured": False,
        })
    return out


@api.post("/menu/upsert")
async def menu_upsert(menu: WeeklyMenu, admin=Depends(_current_admin)):
    """Admin endpoint — requires an admin bearer token."""
    doc = menu.model_dump()
    await db.weekly_menus.update_one(
        {"week_start": menu.week_start}, {"$set": doc}, upsert=True
    )
    return {"ok": True, "week_start": menu.week_start}


@api.get("/catering")
async def catering_list():
    cur = db.catering_packages.find({}, {"_id": 0}).sort([("sort_order", 1), ("price_cents", 1)])
    return await cur.to_list(50)


@api.get("/catering/{package_id}")
async def catering_detail(package_id: str):
    pkg = await db.catering_packages.find_one({"package_id": package_id}, {"_id": 0})
    if not pkg:
        raise HTTPException(404, "Package not found")
    # Collect all master IDs referenced and return their public summary.
    ids: set = set()
    for g in pkg.get("choice_groups", []) or []:
        ids.update(g.get("option_master_ids", []) or [])
    ids.update(pkg.get("included_master_ids") or [])
    ids.update((p.get("master_item_id") for p in (pkg.get("premium_items") or [])))
    master_map: Dict[str, dict] = {}
    if ids:
        async for m in db.master_menu.find({"item_id": {"$in": list(ids)}}, {"_id": 0}):
            master_map[m["item_id"]] = {
                "item_id": m["item_id"],
                "name": m["name"],
                "short_description": m.get("short_description", ""),
                "image_url": m.get("image_url", ""),
                "veg_type": m.get("veg_type", "vegetarian"),
                "category": m.get("category", ""),
                "allergens": m.get("allergens", []),
            }
    return {"package": pkg, "master_items": master_map}


@api.post("/catering/quote-request")
async def catering_quote_request(body: dict):
    """Store a custom-quote request from customer for the Grand Feast."""
    doc = {
        "request_id": f"cqr_{uuid.uuid4().hex[:10]}",
        "package_id": body.get("package_id"),
        "name": body.get("name", ""),
        "email": body.get("email", ""),
        "phone": body.get("phone", ""),
        "guest_count": int(body.get("guest_count") or 0),
        "event_date": body.get("event_date", ""),
        "notes": body.get("notes", ""),
        "status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.catering_quote_requests.insert_one(doc)
    return {"ok": True, "request_id": doc["request_id"]}


# ==========================================================
# COUPONS
# ==========================================================
@api.get("/coupons/first-time")
async def first_time_coupon(user: User = Depends(_current_user)):
    """Return the active first-time coupon IF this logged-in user is eligible
    (non-guest and has never ordered). Used to auto-apply at checkout."""
    if getattr(user, "role", "customer") == "guest":
        return {"coupon": None}
    prior = await db.orders.count_documents({"user_id": user.user_id, "status": {"$ne": "cancelled"}})
    if prior > 0:
        return {"coupon": None}
    c = await db.coupons.find_one({"active": True, "first_time_only": True}, {"_id": 0})
    return {"coupon": c}


async def _apply_coupon(code: Optional[str], subtotal: int, user):
    """Validate a coupon for this user/order and return (discount_cents, code_or_None).
    Enforces min-order and first-time-only (logged-in, no prior orders) rules."""
    if not code:
        return 0, None
    c = await db.coupons.find_one({"code": code.upper(), "active": True}, {"_id": 0})
    if not c:
        return 0, None
    if subtotal < int(c.get("min_order_cents", 0) or 0):
        return 0, None
    if c.get("first_time_only"):
        if getattr(user, "role", "customer") == "guest":
            return 0, None
        prior = await db.orders.count_documents({"user_id": user.user_id, "status": {"$ne": "cancelled"}})
        if prior > 0:
            return 0, None
    if c["discount_type"] == "percent":
        discount = subtotal * int(c["value"]) // 100
    else:
        discount = min(int(c["value"]), subtotal)
    return discount, c["code"]


@api.get("/coupons/{code}")
async def coupon_lookup(code: str):
    c = await db.coupons.find_one({"code": code.upper(), "active": True}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Coupon not found")
    return c


# ==========================================================
# ORDERS
# ==========================================================
DELIVERY_FEE_CENTS = 599  # $5.99 default GTA delivery fee


# --- Distance-based delivery fee (measured from the Milton kitchen) ---
MILTON_ORIGIN = "6941 Derry Rd West, Milton, ON, Canada"
# Fallback tiers if none configured in settings: {max_km, fee_cents}
DEFAULT_DELIVERY_FEE_TIERS = [
    {"max_km": 20, "fee_cents": 0},
    {"max_km": 40, "fee_cents": 500},
    {"max_km": 75, "fee_cents": 1000},
]
DEFAULT_DELIVERY_FEE_OVER_MAX_CENTS = 1500
DELIVERY_TIME_WINDOW = "6:00 PM – 10:00 PM"
DELIVERY_CONDO_POLICY = (
    "Condo & apartment deliveries: please collect your food from the building gate — "
    "our drivers cannot deliver to individual unit doors."
)


def _num(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fee_for_km(km, tiers, over_max_cents):
    """Pick the first tier (ascending max_km) the distance falls within.
    Returns (fee_cents, human_label like "0–20 km")."""
    clean = sorted(
        [{"max_km": _num(t.get("max_km")), "fee_cents": int(_num(t.get("fee_cents")))}
         for t in (tiers or []) if t.get("max_km") is not None],
        key=lambda t: t["max_km"],
    )
    if not clean:
        clean = DEFAULT_DELIVERY_FEE_TIERS
    lower = 0
    for t in clean:
        upper = t["max_km"]
        if km <= upper:
            lo = int(lower) if float(lower).is_integer() else lower
            up = int(upper) if float(upper).is_integer() else upper
            return t["fee_cents"], f"{lo}–{up} km"
        lower = upper
    top = int(lower) if float(lower).is_integer() else lower
    return int(over_max_cents), f"{top}+ km"


async def _driving_distance_km(address, origin):
    """Driving distance (km) from the kitchen (`origin`) to the customer address.
    Returns None if Google Maps is unavailable so callers can fall back."""
    if not GOOGLE_MAPS_API_KEY or GOOGLE_MAPS_API_KEY.startswith("AIzaSy_PLACEHOLDER"):
        return None
    if getattr(address, "lat", None) is not None and getattr(address, "lng", None) is not None:
        dest = f"{address.lat},{address.lng}"
    else:
        parts = [address.line1, address.city, address.province, address.postal_code, "Canada"]
        dest = ", ".join([p for p in parts if p])
    params = {"origins": origin or MILTON_ORIGIN, "destinations": dest,
              "key": GOOGLE_MAPS_API_KEY, "units": "metric", "mode": "driving"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://maps.googleapis.com/maps/api/distancematrix/json", params=params)
            data = r.json()
            el = (data.get("rows") or [{}])[0].get("elements", [{}])[0]
            if el.get("status") == "OK":
                return el["distance"]["value"] / 1000.0
            logging.warning(f"[delivery.distance] element status={el.get('status')} top={data.get('status')}")
    except Exception as e:
        logging.exception(f"[delivery.distance] {e}")
    return None


async def compute_delivery_fee(address, settings):
    """Returns (fee_cents, distance_km_or_None, tier_label). Origin + tiers are
    read from BusinessSettings so the admin can configure them in Settings."""
    origin = (settings.get("kitchen_address") or "").strip() or MILTON_ORIGIN
    km = await _driving_distance_km(address, origin)
    if km is None:
        return settings.get("default_delivery_fee_cents", DELIVERY_FEE_CENTS), None, "standard"
    tiers = settings.get("delivery_fee_tiers") or DEFAULT_DELIVERY_FEE_TIERS
    over = settings.get("delivery_fee_over_max_cents", DEFAULT_DELIVERY_FEE_OVER_MAX_CENTS)
    fee, tier = _fee_for_km(km, tiers, over)
    return fee, round(km, 1), tier



async def _resolve_items(items: List[OrderItemIn]):
    """Fetch authoritative prices from DB and return (snapshots, subtotal_cents).
    For catering, price is per-person; line_total = per_person * catering_guest_count * quantity.
    Menu items are looked up in weekly menus (v1 embedded or v2 lines) or master_menu.
    """
    snapshots = []
    subtotal = 0
    for it in items:
        if it.kind == "menu":
            src = None
            avail = "available"
            # 1) legacy embedded weekly item
            m = await db.weekly_menus.find_one(
                {"items.item_id": it.ref_id}, {"_id": 0, "items.$": 1}
            )
            if m and m.get("items"):
                src = m["items"][0]
            else:
                # 2) v2 line: try master_menu direct, applying any current-week override
                mi = await db.master_menu.find_one({"item_id": it.ref_id}, {"_id": 0})
                if mi:
                    src = {
                        "name": mi["name"],
                        "price_cents": mi["default_price_cents"],
                        "image_url": mi.get("image_url", ""),
                    }
                    # Try to find a matching line in a published weekly menu for override.
                    wm = await db.weekly_menus.find_one(
                        {"lines.master_item_id": it.ref_id, "published": True,
                         "status": {"$ne": "draft"}},
                        {"_id": 0, "lines.$": 1},
                    )
                    if wm and wm.get("lines"):
                        ln = wm["lines"][0]
                        if ln.get("price_override_cents"):
                            src["price_cents"] = ln["price_override_cents"]
                        avail = ln.get("availability", "available")
                        stock_limit = ln.get("stock_limit")
                        if stock_limit is not None and ln.get("stock_used", 0) >= stock_limit:
                            avail = "sold_out"
            if not src:
                raise HTTPException(400, f"Menu item {it.ref_id} not found")
            if avail == "sold_out":
                raise HTTPException(400, f"'{src.get('name')}' is sold out this week")
            line_total = src["price_cents"] * it.quantity
            line = {
                "kind": "menu",
                "ref_id": it.ref_id,
                "name": src.get("name"),
                "unit_price_cents": src.get("price_cents"),
                "quantity": it.quantity,
                "image_url": src.get("image_url"),
                "line_total_cents": line_total,
            }
        elif it.kind == "catering":
            pkg = await db.catering_packages.find_one({"package_id": it.ref_id}, {"_id": 0})
            if not pkg:
                raise HTTPException(400, f"Catering package {it.ref_id} not found")
            if pkg.get("is_custom_quote"):
                raise HTTPException(400, "This catering package is quote-only; contact us to book.")
            guests = it.catering_guest_count or pkg.get("min_guests", 10)
            min_g = pkg.get("min_guests", 10)
            if guests < min_g:
                raise HTTPException(400, f"Catering package requires at least {min_g} guests")

            # ---- Resolve per-person price from tier (or fallback price_cents) ----
            per_person = pkg.get("price_cents", 0)
            selection = it.catering_selections or CateringSelection()
            tiers = pkg.get("upgrade_tiers", []) or []
            active_tier = None
            if selection.tier_id and tiers:
                active_tier = next((t for t in tiers if t.get("tier_id") == selection.tier_id), None)
                if not active_tier:
                    raise HTTPException(400, "Invalid catering tier")
                per_person = active_tier["per_person_cents"]
            elif tiers:
                active_tier = next((t for t in tiers if t.get("is_default")), tiers[0])
                per_person = active_tier["per_person_cents"]

            # ---- Validate choice-group selections (with tier overrides) ----
            groups = pkg.get("choice_groups", []) or []
            group_by_id = {g["group_id"]: g for g in groups}
            picks_by_group = selection.group_selections or {}
            for g in groups:
                gid = g["group_id"]
                override = (active_tier or {}).get("group_overrides", {}).get(gid) if active_tier else None
                min_sel = override.get("min_select") if override else g.get("min_select", 1)
                max_sel = override.get("max_select") if override else g.get("max_select", 1)
                picks = picks_by_group.get(gid, [])
                # dedupe & keep only valid options
                picks = [p for p in dict.fromkeys(picks) if p in g.get("option_master_ids", [])]
                if len(picks) < min_sel or len(picks) > max_sel:
                    raise HTTPException(400, f"Group '{g['title']}' requires {min_sel}–{max_sel} selections (got {len(picks)})")

            # ---- Premium upcharges (only allowed items from pkg.premium_items) ----
            premium_list = {p["master_item_id"]: p["upcharge_per_person_cents"] for p in (pkg.get("premium_items") or [])}
            premium_picks = [pid for pid in dict.fromkeys(selection.premium_selections or []) if pid in premium_list]
            premium_upcharge_per_person = sum(premium_list[pid] for pid in premium_picks)

            unit_per_person = per_person + premium_upcharge_per_person
            line_total = unit_per_person * guests * it.quantity

            # Build human-readable selection summary for the order snapshot.
            id_to_name: Dict[str, str] = {}
            all_master_ids = set()
            for g in groups:
                all_master_ids.update(g.get("option_master_ids", []))
            all_master_ids.update(pkg.get("included_master_ids") or [])
            all_master_ids.update(premium_list.keys())
            if all_master_ids:
                async for m in db.master_menu.find({"item_id": {"$in": list(all_master_ids)}}, {"_id": 0, "item_id": 1, "name": 1}):
                    id_to_name[m["item_id"]] = m["name"]

            selection_summary = []
            for g in groups:
                names = [id_to_name.get(pid, pid) for pid in picks_by_group.get(g["group_id"], [])]
                if names:
                    selection_summary.append({"title": g["title"], "items": names})
            included_names = [id_to_name.get(mid, mid) for mid in (pkg.get("included_master_ids") or [])]
            premium_names = [id_to_name.get(pid, pid) for pid in premium_picks]

            line = {
                "kind": "catering",
                "ref_id": it.ref_id,
                "name": pkg.get("name"),
                "unit_price_cents": unit_per_person,
                "per_person_price_cents": unit_per_person,
                "base_per_person_cents": per_person,
                "premium_upcharge_per_person_cents": premium_upcharge_per_person,
                "tier_id": (active_tier or {}).get("tier_id"),
                "tier_title": (active_tier or {}).get("title"),
                "catering_guest_count": guests,
                "quantity": it.quantity,
                "image_url": pkg.get("image_url"),
                "line_total_cents": line_total,
                "selection_summary": selection_summary,
                "included_names": included_names,
                "premium_names": premium_names,
            }
        elif it.kind == "weekly_package":
            wm = await db.weekly_menus.find_one({"menu_id": it.ref_id}, {"_id": 0})
            if not wm:
                raise HTTPException(400, f"Weekly menu {it.ref_id} not found")
            if not wm.get("package_enabled") or not wm.get("package"):
                raise HTTPException(400, "Weekly package is not enabled for this menu")
            pkg = wm["package"]
            pick_count = int(pkg.get("pick_count") or 0)
            price_cents = int(pkg.get("price_cents") or 0)
            picks = list(it.package_selections or [])  # KEEP ORDER + DUPLICATES (quantities)

            # Eligible pool: explicit list, else all master items in the week's lines
            line_master_ids = [ln.get("master_item_id") for ln in (wm.get("lines") or []) if ln.get("master_item_id")]
            eligible = pkg.get("eligible_master_ids") or line_master_ids
            eligible_set = set(eligible)

            # Validate all picks are in eligible pool
            invalid = [p for p in picks if p not in eligible_set]
            if invalid:
                raise HTTPException(400, "Some items are not eligible for this week's package")
            if len(picks) != pick_count:
                raise HTTPException(400, f"Weekly package requires exactly {pick_count} portions (got {len(picks)})")

            # Resolve names for snapshot (dedupe id list only for the lookup query)
            unique_picks = list(dict.fromkeys(picks))
            names_map: Dict[str, str] = {}
            vt_map: Dict[str, str] = {}
            async for m in db.master_menu.find({"item_id": {"$in": unique_picks}}, {"_id": 0, "item_id": 1, "name": 1, "veg_type": 1}):
                names_map[m["item_id"]] = m["name"]
                vt_map[m["item_id"]] = m.get("veg_type", "vegetarian")

            # ---- Composition-based pricing (veg / mixed / non-veg) ----
            # Egg (eggitarian) counts as NON-VEG, per the poster grouping.
            pricing_mode = pkg.get("pricing_mode") or "flat"
            if pricing_mode == "composition":
                nonveg_count = sum(1 for p in picks if vt_map.get(p, "vegetarian") != "vegetarian")
                if nonveg_count == 0:
                    price_cents = int(pkg.get("veg_price_cents") or 0)
                    composition = "all-veg"
                elif nonveg_count == len(picks):
                    price_cents = int(pkg.get("nonveg_price_cents") or 0)
                    composition = "all-non-veg"
                else:
                    price_cents = int(pkg.get("mixed_price_cents") or 0)
                    composition = "mixed"
                if price_cents <= 0:
                    raise HTTPException(400, "Weekly plan price is not configured for this selection")
            else:
                composition = None

            # Human-readable display list — aggregate repeats as "Biryani × 3"
            from collections import Counter as _Counter
            counts = _Counter(picks)

            # Per-item surcharges add on top of the flat package price for each portion.
            surcharge_map = pkg.get("item_surcharges_cents") or {}
            surcharge_total = sum(int(surcharge_map.get(mid, 0) or 0) for mid in picks)
            effective_unit_cents = price_cents + surcharge_total

            display_names = []
            for mid, q in counts.items():
                base = names_map.get(mid, mid)
                extra = int(surcharge_map.get(mid, 0) or 0)
                # Show " (+$X)" per-portion so kitchen/receipt lists surcharge context.
                suffix = f" (+CA${extra/100:.2f} ea)" if extra > 0 else ""
                display_names.append(f"{base} × {q}{suffix}" if q > 1 else f"{base}{suffix}")

            line = {
                "kind": "weekly_package",
                "ref_id": it.ref_id,
                "name": pkg.get("name") or "Weekly Combo",
                "unit_price_cents": effective_unit_cents,        # base + surcharges
                "quantity": it.quantity,
                "image_url": pkg.get("image_url") or wm.get("banner_image_url", ""),
                "line_total_cents": effective_unit_cents * it.quantity,
                "package_selection_ids": picks,                  # expanded (preserves qty)
                "package_selection_names": display_names,        # aggregated for display
                "package_pick_count": pick_count,
                "package_base_cents": price_cents,               # transparency for receipts
                "package_composition": composition,              # all-veg | mixed | all-non-veg | None
                "package_pricing_mode": pkg.get("pricing_mode") or "flat",
                "package_surcharge_cents": surcharge_total,      # transparency for receipts
                "weekly_menu_id": it.ref_id,
                "weekly_menu_week_start": wm.get("week_start"),
            }
        else:
            raise HTTPException(400, f"Unknown item kind {it.kind}")
        subtotal += line["line_total_cents"]
        snapshots.append(line)
    return snapshots, subtotal


async def _get_settings() -> dict:
    doc = await db.business_settings.find_one({"key": "default"}, {"_id": 0})
    if not doc:
        return BusinessSettings().model_dump()
    # Merge over defaults so a partially-written doc never misses fields
    # (e.g. an upsert that only touched always_available_master_ids).
    return {**BusinessSettings().model_dump(), **doc}


def _loyalty_cfg(settings: dict):
    """(enabled, earn_points_per_dollar, redeem_points_per_dollar)."""
    return (
        bool(settings.get("loyalty_enabled", True)),
        max(0, int(settings.get("loyalty_earn_points_per_dollar", 1) or 0)),
        max(1, int(settings.get("loyalty_redeem_points_per_dollar", 100) or 100)),
    )


def _compute_redemption(settings: dict, user, requested_points: int, cap_cents: int):
    """Convert requested loyalty points into a dollar discount, honouring the
    configured redeem rate. Guests never redeem. Returns (points_used, cents_off)."""
    enabled, _earn, redeem_rate = _loyalty_cfg(settings)
    if not enabled or getattr(user, "role", "customer") == "guest":
        return 0, 0
    pts = min(max(0, int(requested_points or 0)), int(getattr(user, "loyalty_points", 0) or 0))
    if pts <= 0:
        return 0, 0
    cents = (pts * 100) // redeem_rate
    if cents > cap_cents:
        cents = max(0, cap_cents)
        pts = (cents * redeem_rate + 99) // 100  # points actually needed for that discount
        pts = min(pts, int(getattr(user, "loyalty_points", 0) or 0))
    return pts, cents


def _compute_earned(settings: dict, user, subtotal_cents: int) -> int:
    """Points earned for this order. Guests earn nothing."""
    enabled, earn_rate, _redeem = _loyalty_cfg(settings)
    if not enabled or getattr(user, "role", "customer") == "guest":
        return 0
    return (subtotal_cents // 100) * earn_rate


async def _record_loyalty(user_id: str, order_id: str, earned: int, redeemed: int, balance_after: int):
    """Append earn/redeem rows to the loyalty ledger for admin history."""
    now = datetime.now(timezone.utc)
    docs = []
    if earned:
        docs.append({"entry_id": f"ll_{uuid.uuid4().hex[:10]}", "user_id": user_id,
                     "order_id": order_id, "type": "earn", "points": int(earned),
                     "balance_after": int(balance_after), "created_at": now,
                     "note": f"Earned on order #{order_id[-6:].upper()}"})
    if redeemed:
        docs.append({"entry_id": f"ll_{uuid.uuid4().hex[:10]}", "user_id": user_id,
                     "order_id": order_id, "type": "redeem", "points": int(redeemed),
                     "balance_after": int(balance_after), "created_at": now,
                     "note": f"Redeemed on order #{order_id[-6:].upper()}"})
    if docs:
        await db.loyalty_ledger.insert_many(docs)


def _tax_enabled_for_method(settings: dict, payment_method: str) -> bool:
    """Return whether HST should be applied for the given payment_method.

    Priority:
      1. `payment_methods[<method>].tax_enabled` if configured
      2. Legacy global `settings.tax_enabled` as fallback
    Note: `payment_method == "card"` is used for Stripe by the client.
    """
    key_map = {"card": "stripe", "stripe": "stripe", "cod": "cod",
               "paypal": "paypal", "interac": "interac"}
    key = key_map.get((payment_method or "").lower(), "stripe")
    pm = (settings.get("payment_methods") or {}).get(key)
    if pm is not None and "tax_enabled" in pm:
        return bool(pm["tax_enabled"])
    return bool(settings.get("tax_enabled", True))


@api.post("/orders/quote")
async def order_quote(req: QuoteOrderReq, user: User = Depends(_current_user)):
    snaps, subtotal = await _resolve_items(req.items)
    settings = await _get_settings()
    discount, coupon = await _apply_coupon(req.coupon_code, subtotal, user)
    _pts_used, points_redeem_cents = _compute_redemption(settings, user, req.redeem_points, max(0, subtotal - discount))
    delivery_fee, dist_km, fee_tier = await compute_delivery_fee(req.address, settings)
    taxable = max(0, subtotal + delivery_fee - discount - points_redeem_cents)
    tax_on = _tax_enabled_for_method(settings, req.payment_method)
    tax_cents = (taxable * settings.get("tax_rate_bps", 1300)) // 10000 if tax_on else 0
    total = taxable + tax_cents
    return {
        "subtotal_cents": subtotal,
        "delivery_fee_cents": delivery_fee,
        "delivery_distance_km": dist_km,
        "delivery_fee_tier": fee_tier,
        "delivery_time_window": DELIVERY_TIME_WINDOW,
        "delivery_condo_policy": DELIVERY_CONDO_POLICY,
        "tax_cents": tax_cents,
        "tax_label": settings.get("tax_label", "HST"),
        "tax_enabled": tax_on,
        "discount_cents": discount,
        "points_redeemed_cents": points_redeem_cents,
        "total_cents": total,
        "coupon_code": coupon,
        "items_snapshot": snaps,
        "points_available": user.loyalty_points,
    }


@api.post("/orders")
async def create_order(req: CreateOrderReq, request: Request, user: User = Depends(_current_user)):
    # Platform gate — if the Suparna Dey Platform flags this tenant as
    # non-operational or hide_checkout, block new orders with a 402 (Payment
    # Required) so the frontend can surface a "subscription lapsed" screen.
    from platform_client import is_operational, should_hide_checkout, snapshot
    if not is_operational() or should_hide_checkout():
        snap = snapshot()
        raise HTTPException(
            402,
            snap.get("banner_text") or (
                f"{BRAND_NAME} is temporarily paused because the restaurant owner "
                "has not completed their platform subscription payment. Please try again shortly."
            )
        )
    snaps, subtotal = await _resolve_items(req.items)
    settings = await _get_settings()
    discount, coupon_code = await _apply_coupon(req.coupon_code, subtotal, user)
    points_redeem, points_redeem_cents = _compute_redemption(settings, user, req.redeem_points, max(0, subtotal - discount))
    delivery_fee, dist_km, fee_tier = await compute_delivery_fee(req.address, settings)
    taxable = max(0, subtotal + delivery_fee - discount - points_redeem_cents)
    tax_cents = (taxable * settings.get("tax_rate_bps", 1300)) // 10000 if _tax_enabled_for_method(settings, req.payment_method) else 0
    total = taxable + tax_cents

    # "card"|"stripe" → Stripe, "cod" → Cash on Delivery, "interac" → Interac e-Transfer (manual), "paypal" → PayPal (config-ready)
    payment_method = req.payment_method if req.payment_method in ("card", "cod", "interac", "paypal") else "card"
    now = datetime.now(timezone.utc)

    if payment_method in ("cod", "interac"):
        status = "confirmed"
        payment_status = "cod_pending" if payment_method == "cod" else "interac_pending"
        label = "Cash on Delivery" if payment_method == "cod" else "Interac e-Transfer"
        tracking = [
            {"status": "new", "ts": now.isoformat(), "note": "Order created"},
            {"status": "confirmed", "ts": now.isoformat(), "note": f"Order confirmed ({label})"},
        ]
        points_awarded = _compute_earned(settings, user, subtotal)
    else:
        status = "pending_payment"
        payment_status = "pending"
        tracking = [{"status": "new", "ts": now.isoformat(), "note": "Order created, awaiting payment"}]
        points_awarded = 0

    order = Order(
        user_id=user.user_id,
        items_snapshot=snaps,
        address=req.address.model_dump(),
        slot=req.slot.model_dump(),
        phone=req.phone,
        subtotal_cents=subtotal,
        delivery_fee_cents=delivery_fee,
        tax_cents=tax_cents,
        tax_label=settings.get("tax_label", "HST"),
        discount_cents=discount,
        points_redeemed_cents=points_redeem_cents,
        total_cents=total,
        coupon_code=coupon_code,
        special_instructions=req.special_instructions or "",
        payment_method=payment_method,
        status=status,
        payment_status=payment_status,
        points_awarded=points_awarded,
        tracking_events=tracking,
    )
    order_doc = order.model_dump()
    order_doc["points_redeemed"] = points_redeem  # points count actually spent (for ledger)
    # Stamp the public base URL (from the request / env) so invoice + tracking
    # links in SMS/email are absolute & clickable, and so later delivery
    # notifications reuse the same origin.
    order_doc["public_base_url"] = _public_base_from_request(request, req.client_base_url)
    order.public_base_url = order_doc["public_base_url"]
    await db.orders.insert_one(order_doc)

    # Save phone on user if not already saved.
    if req.phone and not user.phone:
        await db.users.update_one({"user_id": user.user_id}, {"$set": {"phone": req.phone}})

    # Save name on user record when the customer typed a real name on the
    # address. This is what turns a "Guest" into "Priya Roy" on future
    # orders. We only overwrite when the user's current name is empty
    # OR is an auto-generated placeholder like "Guest" / "Guest 12".
    addr_name = (req.address.name or "").strip() if hasattr(req.address, "name") else ""
    if addr_name:
        current_name = (user.name or "").strip()
        looks_placeholder = (
            not current_name
            or current_name.lower() == "guest"
            or current_name.lower().startswith("guest ")
            or current_name.lower().startswith("guest_")
        )
        if looks_placeholder:
            await db.users.update_one(
                {"user_id": user.user_id},
                {"$set": {"name": addr_name}},
            )

    # Auto-save this order's address as the user's default (so next time it's pre-filled).
    # Skip if the line1 was a placeholder ("TBD") — only real addresses get saved.
    if req.address.line1 and req.address.line1.strip().lower() != "tbd":
        await db.users.update_one(
            {"user_id": user.user_id},
            {"$set": {"default_address": req.address.model_dump()}},
        )

    if payment_method in ("cod", "interac"):
        # Decrement stock immediately (COD + Interac are both confirmed on placement).
        await _decrement_stock_for_order(order.model_dump())
        net = points_awarded - points_redeem
        updated = await db.users.find_one_and_update(
            {"user_id": user.user_id},
            {"$inc": {"loyalty_points": net}},
            return_document=True,
        )
        try:
            bal = int((updated or {}).get("loyalty_points", 0))
            await _record_loyalty(user.user_id, order.order_id, points_awarded, points_redeem, bal)
        except Exception as e:
            log.warning(f"loyalty ledger fail: {e}")
        try:
            pay_line = (
                f"Pay CA${total/100:.2f} at delivery." if payment_method == "cod"
                else f"Send CA${total/100:.2f} via Interac e-Transfer to {(settings.get('payment_methods') or {}).get('interac', {}).get('email', '')}."
            )
            await send_push(
                recipients=[user.user_id],
                data={"title": "Order confirmed 🎉",
                      "message": f"Your {BRAND_NAME} order is being prepared. {pay_line}",
                      "action_url": f"/order/{order.order_id}"},
            )
        except Exception as e:
            log.warning(f"push fail: {e}")

        # Order confirmation → customer (email + SMS) and owner (email + SMS).
        try:
            fresh = await db.orders.find_one({"order_id": order.order_id}, {"_id": 0})
            u = await db.users.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
            await _notify_order_created(fresh or order.model_dump(), settings, u)
        except Exception as e:
            log.warning(f"order notify fail: {e}")

    return order.model_dump()


async def _decrement_stock_for_order(order: dict):
    """For each menu line in the order, decrement stock_used on the matching weekly line
    (if the current-week weekly menu references this master item)."""
    today = datetime.now(timezone.utc).date()
    week_start = _sunday_of(today).isoformat()
    for it in order.get("items_snapshot", []):
        if it.get("kind") != "menu":
            continue
        ref = it["ref_id"]
        qty = it["quantity"]
        # Try v2 line first.
        await db.weekly_menus.update_one(
            {"week_start": week_start, "lines.master_item_id": ref},
            {"$inc": {"lines.$.stock_used": qty}},
        )


@api.get("/orders")
async def list_my_orders(user: User = Depends(_current_user)):
    # Hide unpaid card orders — they only exist during Stripe handoff and are
    # cleaned up on failure. Users should not see "awaiting payment" lines.
    query = {
        "user_id": user.user_id,
        "status": {"$ne": "pending_payment"},
    }
    cur = db.orders.find(query, {"_id": 0}).sort("created_at", -1).limit(50)
    return await cur.to_list(50)


@api.get("/orders/{order_id}")
async def get_order(order_id: str, user: User = Depends(_current_user)):
    o = await db.orders.find_one({"order_id": order_id, "user_id": user.user_id}, {"_id": 0})
    if not o:
        raise HTTPException(404, "Order not found")
    return o


@api.post("/orders/{order_id}/cancel-unpaid")
async def cancel_unpaid_order(order_id: str, user: User = Depends(_current_user)):
    """Called by frontend after Stripe checkout is cancelled or fails.
    Deletes the pending-payment order so the user never sees an 'awaiting payment' row,
    and sends a courtesy email letting them know."""
    order = await db.orders.find_one(
        {"order_id": order_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not order:
        raise HTTPException(404, "Order not found")
    if order.get("payment_status") == "paid" or order.get("status") != "pending_payment":
        # Already paid or already moved past pending — refuse to delete.
        raise HTTPException(400, "Order is not pending payment and cannot be cancelled here")
    await db.orders.delete_one({"order_id": order_id, "user_id": user.user_id})
    # Cleanup Stripe tx row too.
    if order.get("stripe_session_id"):
        await db.payment_transactions.delete_many({"session_id": order["stripe_session_id"]})
    try:
        await send_email(
            to=user.email,
            subject=f"{BRAND_NAME} — Your order was not completed",
            body=(
                f"Hi {user.name}, we noticed the payment for your order was cancelled. "
                f"Nothing was charged. Come back anytime — this week's menu is still open. "
                f"Total attempted: CA${order['total_cents']/100:.2f}."
            ),
        )
    except Exception as e:
        log.warning(f"email fail: {e}")
    return {"ok": True, "deleted": True}


# ==========================================================
# CHECKOUT (Stripe hosted session via emergentintegrations)
# ==========================================================
class CheckoutReq(BaseModel):
    order_id: str
    origin_url: str  # frontend origin to build success/cancel URLs


@api.post("/checkout/session")
async def create_checkout_session(req: CheckoutReq, request: Request, user: User = Depends(_current_user)):
    """Create a Stripe hosted Checkout Session for a pending-payment order.
    The hosted page shows Cards + Apple Pay + Google Pay (per Dashboard config).
    Success/cancel are routed through the backend so it works on web AND Expo Go."""
    sdk = _stripe()
    order = await db.orders.find_one({"order_id": req.order_id, "user_id": user.user_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if order.get("payment_status") == "paid":
        raise HTTPException(400, "Order already paid")
    amount = int(order.get("total_cents", 0))
    if amount <= 0:
        raise HTTPException(400, "Invalid order total")

    api_base = _public_base_from_request(request, order.get("public_base_url")).rstrip("/")
    origin = (req.origin_url or api_base).rstrip("/")
    ref = order["order_id"][-6:].upper()

    session = sdk.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "cad",
                "product_data": {"name": f"{BRAND_NAME} — Order #{ref}"},
                "unit_amount": amount,
            },
            "quantity": 1,
        }],
        client_reference_id=order["order_id"],
        metadata={"order_id": order["order_id"], "origin": origin},
        success_url=f"{api_base}/api/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{api_base}/api/checkout/cancel?session_id={{CHECKOUT_SESSION_ID}}",
        customer_email=((order.get("address") or {}).get("email") or None),
    )

    await db.payment_transactions.update_one(
        {"session_id": session.id},
        {"$set": {
            "session_id": session.id, "order_id": order["order_id"],
            "user_id": user.user_id, "amount_cents": amount,
            "currency": "cad", "status": "initiated", "payment_status": "pending",
            "created_at": datetime.now(timezone.utc),
        }}, upsert=True,
    )
    await db.orders.update_one(
        {"order_id": order["order_id"]},
        {"$set": {"stripe_session_id": session.id, "stripe_return_origin": origin,
                  "payment_method": "card", "payment_status": "pending",
                  "updated_at": datetime.now(timezone.utc)}},
    )
    return {"url": session.url, "session_id": session.id}


async def _finalize_paid_card_order(order: dict, session: dict | None = None):
    """Mark a card order as paid + confirmed and run the same post-order side
    effects as COD/Interac (stock, points, notifications). Idempotent."""
    now = datetime.now(timezone.utc)
    res = await db.orders.update_one(
        {"order_id": order["order_id"], "payment_status": {"$ne": "paid"}},
        {"$set": {
            "payment_status": "paid",
            "status": "confirmed",
            "paid_at": now.isoformat(),
            "stripe_payment_intent": (session or {}).get("payment_intent"),
            "updated_at": now,
        },
         "$push": {"tracking_events": {
             "status": "confirmed", "ts": now.isoformat(),
             "note": "Payment received (card) — order confirmed",
         }}},
    )
    if res.modified_count == 0:
        return  # already finalized elsewhere
    if session and session.get("id"):
        await db.payment_transactions.update_one(
            {"session_id": session["id"]},
            {"$set": {"status": "complete", "payment_status": "paid", "paid_at": now}},
        )
    fresh = await db.orders.find_one({"order_id": order["order_id"]}, {"_id": 0}) or order
    try:
        await _decrement_stock_for_order(fresh)
    except Exception as e:
        log.warning(f"card stock fail: {e}")
    settings_fin = await _get_settings()
    u_doc = await db.users.find_one({"user_id": fresh["user_id"]}, {"_id": 0}) or {}
    enabled_fin, earn_rate_fin, _rr = _loyalty_cfg(settings_fin)
    is_guest = (u_doc.get("role") == "guest")
    subtotal = fresh.get("subtotal_cents", 0)
    points_awarded = 0 if (not enabled_fin or is_guest) else (subtotal // 100) * earn_rate_fin
    points_redeemed = int(fresh.get("points_redeemed", 0) or 0)
    try:
        updated = await db.users.find_one_and_update(
            {"user_id": fresh["user_id"]},
            {"$inc": {"loyalty_points": points_awarded - points_redeemed}},
            return_document=True,
        )
        bal = int((updated or {}).get("loyalty_points", 0))
        await db.orders.update_one({"order_id": fresh["order_id"]}, {"$set": {"points_awarded": points_awarded}})
        await _record_loyalty(fresh["user_id"], fresh["order_id"], points_awarded, points_redeemed, bal)
    except Exception as e:
        log.warning(f"card points fail: {e}")
    try:
        settings = await _get_settings()
        u = await db.users.find_one({"user_id": fresh["user_id"]}, {"_id": 0}) or {}
        await _notify_order_created(fresh, settings, u)
    except Exception as e:
        log.warning(f"card notify fail: {e}")
    try:
        await send_push(
            recipients=[fresh["user_id"]],
            data={"title": "Payment received 🎉",
                  "message": f"Your {BRAND_NAME} order is confirmed and being prepared.",
                  "action_url": f"/order/{fresh['order_id']}"},
        )
    except Exception as e:
        log.warning(f"card push fail: {e}")


@api.get("/checkout/success")
async def checkout_success(session_id: str):
    """Stripe redirects the browser here. We verify payment server-side (source
    of truth), finalize the order, then bounce back into the app with paid=1."""
    sdk = _stripe()
    try:
        session = sdk.checkout.Session.retrieve(session_id)
    except Exception:
        raise HTTPException(404, "Checkout session not found")
    meta = session.get("metadata") or {}
    order_id = meta.get("order_id") or session.get("client_reference_id") or ""
    origin = (meta.get("origin") or "").rstrip("/")
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0}) if order_id else None
    if order and not origin:
        origin = (order.get("stripe_return_origin") or _order_base(order)).rstrip("/")
    if order and session.get("payment_status") == "paid":
        await _finalize_paid_card_order(order, dict(session))
    target = f"{origin}/order/{order_id}?paid=1" if (origin and order_id) else (origin or "/")
    return RedirectResponse(target, status_code=302)


@api.get("/checkout/cancel")
async def checkout_cancel(session_id: str = ""):
    """Stripe cancel redirect — bounce back into the app with paid=0."""
    order = None
    if session_id:
        order = await db.orders.find_one({"stripe_session_id": session_id}, {"_id": 0})
    origin = ((order or {}).get("stripe_return_origin") or _order_base(order or {})).rstrip("/")
    oid = (order or {}).get("order_id", "")
    target = f"{origin}/order/{oid}?paid=0" if (origin and oid) else (origin or "/")
    return RedirectResponse(target, status_code=302)


@api.get("/checkout/status/{session_id}")
async def checkout_status(session_id: str, user: User = Depends(_current_user)):
    """Polling fallback: server verifies the session directly with Stripe."""
    sdk = _stripe()
    try:
        session = sdk.checkout.Session.retrieve(session_id)
    except Exception:
        raise HTTPException(404, "Checkout session not found")
    order_id = (session.get("metadata") or {}).get("order_id") or session.get("client_reference_id")
    paid = session.get("payment_status") == "paid"
    if paid and order_id:
        order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
        if order:
            await _finalize_paid_card_order(order, dict(session))
    return {"session_id": session_id, "payment_status": session.get("payment_status"),
            "paid": paid, "order_id": order_id}


@api.post("/checkout/webhook")
async def checkout_webhook(request: Request):
    """Authoritative fulfillment. Verifies the signature when STRIPE_WEBHOOK_SECRET
    is set; either way it re-retrieves the session from Stripe before finalizing."""
    sdk = _stripe()
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    try:
        if secret and sig:
            event = sdk.Webhook.construct_event(payload, sig, secret)
        else:
            import json as _json
            event = _json.loads(payload.decode() or "{}")
    except Exception:
        raise HTTPException(400, "Invalid webhook")
    if (event.get("type") or "") == "checkout.session.completed":
        obj = (event.get("data") or {}).get("object") or {}
        sess_id = obj.get("id")
        if sess_id:
            try:
                session = sdk.checkout.Session.retrieve(sess_id)  # re-verify from Stripe
                order_id = (session.get("metadata") or {}).get("order_id") or session.get("client_reference_id")
                if session.get("payment_status") == "paid" and order_id:
                    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
                    if order:
                        await _finalize_paid_card_order(order, dict(session))
            except Exception as e:
                log.warning(f"webhook finalize fail: {e}")
    return {"received": True}


# ==========================================================
# ADMIN ORDER STATUS SIMULATION (public in MVP — protect later)
# ==========================================================
class OrderStatusUpdate(BaseModel):
    status: str  # "preparing" | "out_for_delivery" | "delivered"
    note: Optional[str] = ""


@api.post("/orders/{order_id}/status")
async def update_order_status(order_id: str, upd: OrderStatusUpdate, admin=Depends(_current_admin)):
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    events = order.get("tracking_events", []) + [{
        "status": upd.status,
        "ts": datetime.now(timezone.utc).isoformat(),
        "note": upd.note or "",
    }]
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {"status": upd.status, "tracking_events": events,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    try:
        await send_push(
            recipients=[order["user_id"]],
            data={"title": f"Order update: {upd.status.replace('_',' ').title()}",
                  "message": upd.note or "Your order status changed.",
                  "action_url": f"/order/{order_id}"},
        )
    except Exception:
        pass
    return {"ok": True}


# ==========================================================
# DELIVERY PARTNER
# ==========================================================
@api.post("/delivery-partner/apply")
async def apply_delivery(app_in: DeliveryPartnerApplication):
    doc = app_in.model_dump()
    await db.delivery_applications.insert_one(doc)
    try:
        await send_email(app_in.email, f"{BRAND_NAME} — Application received",
                         f"Hi {app_in.full_name}, we received your delivery partner application.")
    except Exception:
        pass
    return {"ok": True, "app_id": app_in.app_id}


# ==========================================================
# PUSH REGISTRATION
# ==========================================================
@api.post("/register-push", status_code=201)
async def register_push(body: PushRegisterReq):
    try:
        resp = await _push_client.post("/api/v1/push/users/register", json=body.model_dump())
        if resp.status_code >= 400:
            log.warning(f"register-push non-2xx {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log.warning(f"register-push error (non-blocking): {e}")
    return {"status": "registered"}


# ==========================================================
# SEED / HEALTH
# ==========================================================
@api.get("/")
async def root():
    return {"service": "curry-co-api", "ok": True}


BENGALI_MENU_TEMPLATES = [
    {
        "name": "Kolkata Chicken Biryani",
        "description": "Slow-cooked long-grain basmati with tender chicken, potatoes, boiled egg and Kolkata masala.",
        "price_cents": 1899,
        "image_url": "https://images.pexels.com/photos/31537385/pexels-photo-31537385.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "category": "rice",
        "tags": ["signature", "spicy"],
        "is_featured": True,
    },
    {
        "name": "Shorshe Ilish",
        "description": "Hilsa fish steamed in traditional mustard-poppy paste. Bengali monsoon classic.",
        "price_cents": 2299,
        "image_url": "https://images.pexels.com/photos/9345647/pexels-photo-9345647.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "category": "curry",
        "tags": ["seafood", "signature"],
        "is_featured": True,
    },
    {
        "name": "Kosha Mangsho",
        "description": "Rich slow-cooked Bengali mutton in caramelized onion & warm spices.",
        "price_cents": 2099,
        "image_url": "https://images.pexels.com/photos/35267281/pexels-photo-35267281.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "category": "curry",
        "tags": ["mutton", "signature"],
        "is_featured": False,
    },
    {
        "name": "Cholar Dal",
        "description": "Bengal gram dal tempered with coconut, ghee, raisins and warm spices.",
        "price_cents": 999,
        "image_url": "https://images.pexels.com/photos/35539325/pexels-photo-35539325.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "category": "veg",
        "tags": ["vegetarian"],
        "is_featured": False,
    },
    {
        "name": "Aloo Posto",
        "description": "Baby potatoes in creamy poppy-seed paste, a Bengali comfort classic.",
        "price_cents": 1099,
        "image_url": "https://images.pexels.com/photos/9345647/pexels-photo-9345647.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "category": "veg",
        "tags": ["vegetarian"],
        "is_featured": False,
    },
    {
        "name": "Luchi & Aloor Dom",
        "description": "Fluffy fried flatbread with spicy potato curry — the ultimate Bengali brunch.",
        "price_cents": 1299,
        "image_url": "https://images.pexels.com/photos/35267281/pexels-photo-35267281.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "category": "starter",
        "tags": ["breakfast"],
        "is_featured": False,
    },
    {
        "name": "Mishti Doi",
        "description": "Traditional Bengali sweet yogurt with caramelized jaggery, served chilled.",
        "price_cents": 599,
        "image_url": "https://images.pexels.com/photos/35539325/pexels-photo-35539325.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "category": "dessert",
        "tags": ["sweet"],
        "is_featured": False,
    },
    {
        "name": "Rosogolla (6 pcs)",
        "description": "Soft cottage cheese dumplings soaked in fragrant sugar syrup.",
        "price_cents": 799,
        "image_url": "https://images.pexels.com/photos/31537385/pexels-photo-31537385.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "category": "dessert",
        "tags": ["sweet", "signature"],
        "is_featured": True,
    },
]

CATERING_PACKAGES = []  # deprecated — packages are now built dynamically in seed() below.

# Additional master menu items required by catering packages.
# category values match the existing MasterMenuItem set: starter | veg | curry | rice | dessert | beverage | side | bread
CATERING_MASTER_EXTRAS = [
    # ---- Snacks / starters ----
    {"name": "Kolkata Egg Roll", "description": "Flaky paratha wrapped around spiced egg, onions and green chutney.",
     "price_cents": 649, "category": "starter", "veg_type": "eggitarian",
     "image_url": "https://images.unsplash.com/photo-1631515243349-e0cb75fb8d3a?auto=format&fit=crop&w=800&q=80"},
    {"name": "Chicken Kathi Roll", "description": "Grilled chicken tikka in a soft paratha with mint chutney.",
     "price_cents": 799, "category": "starter", "veg_type": "non-vegetarian",
     "image_url": "https://images.unsplash.com/photo-1633945274309-2c16c96d020a?auto=format&fit=crop&w=800&q=80"},
    {"name": "Fish Fry", "description": "Bengali-style crumb-fried bhetki with lemon and kasundi.",
     "price_cents": 849, "category": "starter", "veg_type": "non-vegetarian", "allergens": ["seafood"],
     "image_url": "https://images.unsplash.com/photo-1544025162-d76694265947?auto=format&fit=crop&w=800&q=80"},
    {"name": "Veg Chop", "description": "Beetroot-and-peanut croquettes with muri and kasundi.",
     "price_cents": 499, "category": "starter", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=800&q=80"},
    {"name": "Mochar Chop", "description": "Banana-flower cutlets, a Kolkata tea-time favourite.",
     "price_cents": 499, "category": "starter", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1625944230945-1b7dd3b949ab?auto=format&fit=crop&w=800&q=80"},
    {"name": "Chicken Pakora", "description": "Crispy gram-flour fritters with spiced chicken.",
     "price_cents": 699, "category": "starter", "veg_type": "non-vegetarian",
     "image_url": "https://images.unsplash.com/photo-1626777552726-4a6b54c97e46?auto=format&fit=crop&w=800&q=80"},
    {"name": "Egg Devil", "description": "Boiled egg encased in spiced potato and fried golden.",
     "price_cents": 549, "category": "starter", "veg_type": "eggitarian",
     "image_url": "https://images.unsplash.com/photo-1541544741938-0af808871cc0?auto=format&fit=crop&w=800&q=80"},

    # ---- Beverages ----
    {"name": "Masala Tea Pitcher", "description": "Cardamom-clove chai brewed the Kolkata way (serves ~6).",
     "price_cents": 1499, "category": "beverage", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1571934811356-5cc061b6821f?auto=format&fit=crop&w=800&q=80"},
    {"name": "Bengali Doodh Cha Pitcher", "description": "Extra-milky, extra-sweet Bengali tea (serves ~6).",
     "price_cents": 1499, "category": "beverage", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1517701550927-30cf4ba1dba5?auto=format&fit=crop&w=800&q=80"},
    {"name": "Coffee Pitcher", "description": "South-Indian filter coffee — smooth and aromatic.",
     "price_cents": 1499, "category": "beverage", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=800&q=80"},
    {"name": "Tea & Coffee Station", "description": "Full self-serve tea + coffee service for events.",
     "price_cents": 0, "category": "beverage", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1511920170033-f8396924c348?auto=format&fit=crop&w=800&q=80"},
    {"name": "Soft Drink Service", "description": "Assorted chilled soft drinks (Coke, Sprite, Thums Up).",
     "price_cents": 0, "category": "beverage", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?auto=format&fit=crop&w=800&q=80"},

    # ---- Veg mains ----
    {"name": "Aloor Dom", "description": "Baby potatoes slow-cooked in spiced tomato-onion gravy.",
     "price_cents": 999, "category": "veg", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1567337710282-00832b415979?auto=format&fit=crop&w=800&q=80"},
    {"name": "Mochar Ghonto", "description": "Banana-flower cooked with coconut, cumin and ghee.",
     "price_cents": 1099, "category": "veg", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1625944230945-1b7dd3b949ab?auto=format&fit=crop&w=800&q=80"},
    {"name": "Shukto", "description": "Bengali medley of bitter and sweet vegetables in a milky broth.",
     "price_cents": 999, "category": "veg", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1631515243349-e0cb75fb8d3a?auto=format&fit=crop&w=800&q=80"},
    {"name": "Mixed Vegetable Curry", "description": "Seasonal vegetables in a light Bengali panch-phoron gravy.",
     "price_cents": 999, "category": "veg", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1585032226651-759b368d7246?auto=format&fit=crop&w=800&q=80"},
    {"name": "Paneer Butter Masala", "description": "Cottage cheese in a rich tomato-butter gravy.",
     "price_cents": 1299, "category": "veg", "veg_type": "vegetarian", "allergens": ["dairy"],
     "image_url": "https://images.unsplash.com/photo-1631452180519-c014fe946bc7?auto=format&fit=crop&w=800&q=80"},

    # ---- Non-veg mains ----
    {"name": "Chicken Kosha", "description": "Bengali-style caramelised chicken with warm mustard-cumin masala.",
     "price_cents": 1799, "category": "curry", "veg_type": "non-vegetarian",
     "image_url": "https://images.unsplash.com/photo-1603894584373-5ac82b2ae398?auto=format&fit=crop&w=800&q=80"},
    {"name": "Rui Kalia", "description": "Rohu fish curry in a rich onion-tomato gravy.",
     "price_cents": 1599, "category": "curry", "veg_type": "non-vegetarian", "allergens": ["seafood"],
     "image_url": "https://images.unsplash.com/photo-1626777552726-4a6b54c97e46?auto=format&fit=crop&w=800&q=80"},
    {"name": "Egg Curry", "description": "Boiled eggs simmered in Bengali onion-tomato curry.",
     "price_cents": 1199, "category": "curry", "veg_type": "eggitarian",
     "image_url": "https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=800&q=80"},
    {"name": "Chicken Rezala", "description": "White chicken curry cooked in yogurt, cashew and rosewater.",
     "price_cents": 1899, "category": "curry", "veg_type": "non-vegetarian",
     "image_url": "https://images.unsplash.com/photo-1603894584373-5ac82b2ae398?auto=format&fit=crop&w=800&q=80"},
    {"name": "Chingri Malaikari", "description": "Prawns in a creamy coconut-milk gravy — Bengali royalty.",
     "price_cents": 2299, "category": "curry", "veg_type": "non-vegetarian", "allergens": ["seafood"],
     "image_url": "https://images.unsplash.com/photo-1626777552726-4a6b54c97e46?auto=format&fit=crop&w=800&q=80"},
    {"name": "Chicken Chaap", "description": "Slow-braised chicken in yogurt-cashew Mughlai gravy.",
     "price_cents": 1999, "category": "curry", "veg_type": "non-vegetarian",
     "image_url": "https://images.unsplash.com/photo-1603894584373-5ac82b2ae398?auto=format&fit=crop&w=800&q=80"},

    # ---- Rice & bread ----
    {"name": "Basanti Pulao", "description": "Saffron-turmeric sweet pulao with cashews and raisins.",
     "price_cents": 1099, "category": "rice", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1585032226651-759b368d7246?auto=format&fit=crop&w=800&q=80"},
    {"name": "Steamed Rice", "description": "Long-grain white rice served hot.",
     "price_cents": 399, "category": "rice", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1516684732162-798a0062be99?auto=format&fit=crop&w=800&q=80"},

    # ---- Desserts ----
    {"name": "Payesh", "description": "Bengali rice pudding slow-cooked with jaggery and cardamom.",
     "price_cents": 549, "category": "dessert", "veg_type": "vegetarian", "allergens": ["dairy"],
     "image_url": "https://images.unsplash.com/photo-1571934811356-5cc061b6821f?auto=format&fit=crop&w=800&q=80"},
    {"name": "Pantua", "description": "Deep-fried khoya dumplings in cardamom sugar syrup.",
     "price_cents": 599, "category": "dessert", "veg_type": "vegetarian", "allergens": ["dairy"],
     "image_url": "https://images.unsplash.com/photo-1571877227200-a0d98ea607e9?auto=format&fit=crop&w=800&q=80"},
    {"name": "Rajbhog", "description": "King-sized rosogolla stuffed with saffron and cardamom.",
     "price_cents": 699, "category": "dessert", "veg_type": "vegetarian", "allergens": ["dairy"],
     "image_url": "https://images.unsplash.com/photo-1571877227200-a0d98ea607e9?auto=format&fit=crop&w=800&q=80"},

    # ---- Accompaniments (as starters/sides) ----
    {"name": "Bengali Salad", "description": "Fresh cucumber, radish, onion and lemon salad.",
     "price_cents": 299, "category": "starter", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?auto=format&fit=crop&w=800&q=80"},
    {"name": "Aam Kasundi Chutney", "description": "Sweet-tangy mango chutney with Bengali mustard.",
     "price_cents": 299, "category": "starter", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=800&q=80"},
    {"name": "Papad Platter", "description": "Assorted roasted and fried papads.",
     "price_cents": 299, "category": "starter", "veg_type": "vegetarian",
     "image_url": "https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=800&q=80"},
]

COUPONS_SEED = [
    {"code": "FIRST10", "discount_type": "percent", "value": 10, "active": True,
     "min_order_cents": 0, "first_time_only": True,
     "description": "10% off your first order from the app"},
    {"code": "WELCOME10", "discount_type": "percent", "value": 10, "active": True,
     "min_order_cents": 2000, "description": "10% off first order over $20"},
    {"code": "BENGALI15", "discount_type": "percent", "value": 15, "active": True,
     "min_order_cents": 5000, "description": "15% off orders over $50"},
    {"code": "MISHTI5", "discount_type": "fixed", "value": 500, "active": True,
     "min_order_cents": 3000, "description": "$5 off orders over $30"},
]


@api.post("/dev/seed")
async def seed(admin=Depends(_current_admin)):
    """Seed default weekly menu, master menu items, catering packages, coupons, settings."""
    today = datetime.now(timezone.utc).date()
    sun = _sunday_of(today)

    # Ensure business settings row exists.
    if not await db.business_settings.find_one({"key": "default"}, {"_id": 0}):
        await db.business_settings.insert_one(BusinessSettings().model_dump())

    # Seed Master Menu (idempotent by name).
    master_items = []
    for tpl in BENGALI_MENU_TEMPLATES:
        existing = await db.master_menu.find_one({"name": tpl["name"]}, {"_id": 0})
        if existing:
            master_items.append(existing)
            continue
        veg = "vegetarian" if tpl["category"] in ("veg", "dessert") else "non-vegetarian"
        mi = MasterMenuItem(
            name=tpl["name"],
            short_description=tpl["description"],
            full_description=tpl["description"],
            category=tpl["category"],
            cuisine="bengali",
            default_price_cents=tpl["price_cents"],
            image_url=tpl["image_url"],
            veg_type=veg,
            spice_level="hot" if "spicy" in tpl.get("tags", []) else "medium",
            allergens=["seafood"] if "seafood" in tpl.get("tags", []) else [],
        )
        await db.master_menu.insert_one(mi.model_dump())
        master_items.append(mi.model_dump())

    # Seed additional Master Menu items required by catering (idempotent by name).
    for tpl in CATERING_MASTER_EXTRAS:
        existing = await db.master_menu.find_one({"name": tpl["name"]}, {"_id": 0})
        if existing:
            continue
        mi = MasterMenuItem(
            name=tpl["name"],
            short_description=tpl["description"],
            full_description=tpl["description"],
            category=tpl["category"],
            cuisine="bengali",
            default_price_cents=tpl.get("price_cents", 0),
            image_url=tpl.get("image_url", ""),
            veg_type=tpl.get("veg_type", "vegetarian"),
            spice_level=tpl.get("spice_level", "medium"),
            allergens=tpl.get("allergens", []),
        )
        await db.master_menu.insert_one(mi.model_dump())

    for i in range(3):
        wk = (sun + timedelta(weeks=i)).isoformat()
        we = (sun + timedelta(weeks=i, days=6)).isoformat()
        title = ["This Week's Bengali Table", "Next Week: Riverside Specials",
                 "Week After: Kolkata Street Feast"][i]
        # Build v2 lines pointing at ORIGINAL master items (not catering extras — keeps weekly menu tidy).
        lines = []
        for j, mi in enumerate(master_items):
            lines.append(WeeklyMenuLine(
                master_item_id=mi["item_id"],
                is_featured=(j + i) % 4 == 0 or mi.get("category") in ("rice", "dessert"),
                display_order=j,
            ).model_dump())
        # For the CURRENT week (i==0), enable a demo weekly-menu package so the feature
        # is visible out of the box. Admin can toggle it off / edit from the admin portal.
        pkg_doc = None
        if i == 0:
            pkg_doc = WeeklyMenuPackage(
                name="This Week's Combo",
                description="Build your own mini-thali — pick 3 dishes from this week's menu and save.",
                price_cents=3499,
                pick_count=3,
                eligible_master_ids=[],  # empty = all items in this week's lines
                image_url="https://images.unsplash.com/photo-1728910156510-77488f19b152?crop=entropy&cs=srgb&fm=jpg&w=1200&q=80",
            ).model_dump()
        wm = WeeklyMenu(
            week_start=wk, week_end=we, title=title,
            description="Slow-cooked Bengali comfort food, delivered fresh.",
            items=[], lines=lines, published=True, status="published",
            alacarte_enabled=True,
            package_enabled=(i == 0),
            package=pkg_doc if isinstance(pkg_doc, dict) else None,
        )
        # Preserve any admin edits — do NOT overwrite package/toggle/menu_id fields once set.
        existing = await db.weekly_menus.find_one({"week_start": wk}, {"_id": 0})
        if existing:
            merged = wm.model_dump()
            for keep in ("package", "package_enabled", "alacarte_enabled", "menu_id"):
                if keep in existing:
                    merged[keep] = existing[keep]
            await db.weekly_menus.update_one({"week_start": wk}, {"$set": merged}, upsert=True)
        else:
            await db.weekly_menus.update_one(
                {"week_start": wk}, {"$set": wm.model_dump()}, upsert=True,
            )

    # ---- Build 5 new catering packages, referencing master item IDs by name ----
    async def _mid(name: str) -> Optional[str]:
        doc = await db.master_menu.find_one({"name": name}, {"_id": 0, "item_id": 1})
        return doc["item_id"] if doc else None

    async def _mids(names: List[str]) -> List[str]:
        out = []
        for n in names:
            mid = await _mid(n)
            if mid:
                out.append(mid)
        return out

    def _group(title: str, subtitle: str, min_s: int, max_s: int, mids: List[str], order: int = 0) -> dict:
        return CateringChoiceGroup(
            title=title, subtitle=subtitle, min_select=min_s, max_select=max_s,
            option_master_ids=mids, display_order=order,
        ).model_dump()

    # 1. Kolkata Adda Snack Box — $9 base / $12 upgrade
    snack_opts = await _mids(["Kolkata Egg Roll", "Chicken Kathi Roll", "Fish Fry",
                              "Veg Chop", "Mochar Chop", "Chicken Pakora"])
    tea_opts = await _mids(["Masala Tea Pitcher", "Bengali Doodh Cha Pitcher", "Coffee Pitcher"])
    snack_group = _group("Snack", "Choose 1 snack", 1, 1, snack_opts, 0)
    tea_group = _group("Tea / Coffee Service", "Choose 1", 1, 1, tea_opts, 1)
    pkg1 = CateringPackage(
        name="Kolkata Adda Snack Box",
        tagline="Perfect for small gatherings, tea-time parties, office meetups, birthdays",
        description="Handpicked Kolkata street snacks paired with your favourite tea or coffee.",
        emoji="🫖",
        perfect_for="Small gatherings · Tea-time parties · Office meetups · Birthdays",
        price_cents=900,
        min_guests=10,
        image_url="https://images.unsplash.com/photo-1633945274309-2c16c96d020a?auto=format&fit=crop&w=1200&q=80",
        includes=["1 Snack + Tea/Coffee Service"],
        choice_groups=[snack_group, tea_group],
        upgrade_tiers=[
            CateringUpgradeTier(title="Base — 1 Snack + Tea/Coffee",
                                subtitle="$9 / person",
                                per_person_cents=900, is_default=True).model_dump(),
            CateringUpgradeTier(title="Upgrade — 2 Snacks + Tea/Coffee",
                                subtitle="$12 / person",
                                per_person_cents=1200, is_default=False,
                                group_overrides={snack_group["group_id"]: {"min_select": 2, "max_select": 2}}).model_dump(),
        ],
        is_featured=True,
        sort_order=1,
    ).model_dump()

    # 2. Sunday Bari'r Lunch — $24.99
    veg_opts_2 = await _mids(["Cholar Dal", "Aloor Dom", "Mochar Ghonto", "Shukto",
                              "Mixed Vegetable Curry", "Paneer Butter Masala"])
    nv_opts_2 = await _mids(["Chicken Kosha", "Rui Kalia", "Egg Curry", "Chicken Rezala", "Chingri Malaikari"])
    dessert_opts_2 = await _mids(["Mishti Doi", "Payesh", "Rosogolla (6 pcs)"])
    included_2 = await _mids(["Steamed Rice", "Bengali Salad"])
    chingri_id = await _mid("Chingri Malaikari")
    pkg2 = CateringPackage(
        name="Sunday Bari'r Lunch",
        tagline="Homestyle Bengali Comfort Feast",
        description="A cosy Bengali Sunday spread — three vegetables, three non-veg curries, rice and a sweet finish.",
        emoji="🍽️",
        perfect_for="Sunday family lunches · Small home gatherings",
        price_cents=2499,
        min_guests=10,
        image_url="https://images.unsplash.com/photo-1728910156510-77488f19b152?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzNDR8MHwxfHNlYXJjaHwyfHxpbmRpYW4lMjBjYXRlcmluZyUyMGZlYXN0fGVufDB8fHx8MTc4NDY0OTgzNHww&ixlib=rb-4.1.0&q=85",
        includes=["3 Veg + 3 Non-Veg + Dessert", "Rice & Salad included"],
        included_master_ids=included_2,
        choice_groups=[
            _group("3 Veg Items", "Choose Any 3", 3, 3, veg_opts_2, 0),
            _group("3 Non-Veg Items", "Choose Any 3", 3, 3, nv_opts_2, 1),
            _group("Dessert", "Choose Any 1", 1, 1, dessert_opts_2, 2),
        ],
        premium_items=[CateringPremiumItem(master_item_id=chingri_id,
                                           upcharge_per_person_cents=400).model_dump()] if chingri_id else [],
        is_featured=True,
        sort_order=2,
    ).model_dump()

    # 3. Royal Bengali Dinner Feast — $34.99
    veg_opts_3 = await _mids(["Cholar Dal", "Aloor Dom", "Mochar Ghonto", "Shukto",
                              "Mixed Vegetable Curry", "Paneer Butter Masala"])
    nv_opts_3 = await _mids(["Kosha Mangsho", "Chingri Malaikari", "Shorshe Ilish",
                             "Chicken Rezala", "Rui Kalia"])
    dessert_opts_3 = await _mids(["Mishti Doi", "Rosogolla (6 pcs)", "Pantua", "Payesh"])
    included_3 = await _mids(["Basanti Pulao", "Luchi & Aloor Dom", "Bengali Salad"])
    pkg3 = CateringPackage(
        name="Royal Bengali Dinner Feast",
        tagline="Perfect for Family Celebrations & Special Gatherings",
        description="Premium proteins and Basanti Pulao — a sit-down dinner spread fit for celebrations.",
        emoji="👑",
        perfect_for="Family celebrations · Anniversaries · Special gatherings",
        price_cents=3499,
        min_guests=15,
        image_url="https://images.unsplash.com/photo-1589778655375-3e622a9fc91c?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzNDR8MHwxfHNlYXJjaHwzfHxpbmRpYW4lMjBjYXRlcmluZyUyMGZlYXN0fGVufDB8fHx8MTc4NDY0OTgzNHww&ixlib=rb-4.1.0&q=85",
        includes=["3 Veg + 3 Premium Non-Veg + 2 Desserts", "Basanti Pulao, Luchi & Salad included"],
        included_master_ids=included_3,
        choice_groups=[
            _group("3 Veg Items", "Choose Any 3", 3, 3, veg_opts_3, 0),
            _group("3 Premium Non-Veg Items", "Choose Any 3", 3, 3, nv_opts_3, 1),
            _group("Dessert", "Choose Any 2", 2, 2, dessert_opts_3, 2),
        ],
        is_featured=True,
        sort_order=3,
    ).model_dump()

    # 4. Bonedi Bengali Celebration Buffet — $39.99
    veg_opts_4 = await _mids(["Cholar Dal", "Aloor Dom", "Mochar Ghonto", "Shukto",
                              "Mixed Vegetable Curry", "Paneer Butter Masala", "Aloo Posto"])
    nv_opts_4 = await _mids(["Kosha Mangsho", "Chingri Malaikari", "Shorshe Ilish",
                             "Chicken Rezala", "Rui Kalia", "Chicken Kosha", "Egg Curry"])
    dessert_opts_4 = await _mids(["Mishti Doi", "Rosogolla (6 pcs)", "Pantua", "Payesh", "Rajbhog"])
    bev_opts_4 = await _mids(["Tea & Coffee Station", "Soft Drink Service"])
    included_4 = await _mids(["Basanti Pulao", "Luchi & Aloor Dom", "Bengali Salad",
                              "Aam Kasundi Chutney", "Papad Platter"])
    pkg4 = CateringPackage(
        name="Bonedi Bengali Celebration Buffet",
        tagline="Traditional Bengali Banquet for Large Gatherings",
        description="A full Bonedi Bari buffet with 4+4 mains, live sides, a dessert bar and beverage service.",
        emoji="🎉",
        perfect_for="Annaprashan · Birthday parties · Housewarming · Community events",
        price_cents=3999,
        min_guests=20,
        image_url="https://images.pexels.com/photos/31537385/pexels-photo-31537385.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        includes=["4 Veg + 4 Non-Veg + 2 Desserts", "Pulao, Luchi, Salad, Chutney, Papad included",
                  "Tea / Soft Drink service"],
        included_master_ids=included_4,
        choice_groups=[
            _group("4 Veg Items", "Choose Any 4", 4, 4, veg_opts_4, 0),
            _group("4 Non-Veg Items", "Choose Any 4", 4, 4, nv_opts_4, 1),
            _group("Dessert", "Choose Any 2", 2, 2, dessert_opts_4, 2),
            _group("Beverage Service", "Choose 1", 1, 1, bev_opts_4, 3),
        ],
        is_featured=True,
        sort_order=4,
    ).model_dump()

    # 5. Shonar Bangla Signature Grand Feast — CUSTOM QUOTE
    welcome_opts_5 = await _mids(["Fish Fry", "Egg Devil", "Chicken Pakora", "Veg Chop"])
    veg_opts_5 = await _mids(["Cholar Dal", "Aloor Dom", "Mochar Ghonto", "Shukto",
                              "Mixed Vegetable Curry", "Paneer Butter Masala", "Aloo Posto"])
    nv_opts_5 = await _mids(["Shorshe Ilish", "Chingri Malaikari", "Kosha Mangsho",
                             "Chicken Chaap", "Chicken Rezala"])
    dessert_opts_5 = await _mids(["Mishti Doi", "Rosogolla (6 pcs)", "Pantua", "Payesh", "Rajbhog"])
    bev_opts_5 = await _mids(["Tea & Coffee Station"])
    included_5 = await _mids(["Basanti Pulao", "Luchi & Aloor Dom", "Steamed Rice",
                              "Aam Kasundi Chutney", "Bengali Salad", "Papad Platter"])
    settings = await _get_settings()
    pkg5 = CateringPackage(
        name="Shonar Bangla Signature Grand Feast",
        tagline="Our Premium Catering Experience",
        description="A chef-curated multi-course banquet with welcome snacks, four premium mains, a dessert bar and beverage station.",
        emoji="🏆",
        perfect_for="Weddings · Puja celebrations · Corporate events · Cultural functions",
        price_cents=0,
        min_guests=30,
        image_url="https://images.pexels.com/photos/31537385/pexels-photo-31537385.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        includes=["Welcome snacks · 4 Veg + 4 Premium Non-Veg · 3 Desserts · Beverage Station",
                  "Pulao, Luchi, Rice, Chutney, Salad, Papad included"],
        included_master_ids=included_5,
        choice_groups=[
            _group("Welcome Snacks", "Choose Any 2", 2, 2, welcome_opts_5, 0),
            _group("4 Veg Items", "Choose Any 4", 4, 4, veg_opts_5, 1),
            _group("4 Premium Non-Veg Items", "Choose Any 4", 4, 4, nv_opts_5, 2),
            _group("Dessert", "Choose Any 3", 3, 3, dessert_opts_5, 3),
            _group("Beverage Station", "Included", 1, 1, bev_opts_5, 4),
        ],
        is_custom_quote=True,
        contact_email=settings.get("email", BRAND_EMAIL_FROM),
        contact_phone=settings.get("phone", ""),
        is_featured=True,
        sort_order=5,
    ).model_dump()

    await db.catering_packages.delete_many({})
    for pkg in [pkg1, pkg2, pkg3, pkg4, pkg5]:
        await db.catering_packages.insert_one(pkg)

    for c in COUPONS_SEED:
        await db.coupons.update_one({"code": c["code"]}, {"$set": c}, upsert=True)

    # Seed a demo delivery partner (idempotent by email)
    demo_email = BRAND_DELIVERY_EMAIL
    if not await db.delivery_partners.find_one({"email": demo_email}, {"_id": 0}):
        dp = DeliveryPartner(
            name="Rahul Das", email=demo_email, phone="+1 416-555-0101",
            vehicle="car", password_hash=_pwd.hash("curry@delivery2026"),
        )
        await db.delivery_partners.insert_one(dp.model_dump())

    total_master = await db.master_menu.count_documents({})
    return {"ok": True, "weeks_seeded": 3, "master_items": total_master,
            "packages": 5, "coupons": len(COUPONS_SEED)}


# ==========================================================
# ADMIN
# ==========================================================
class AdminLoginReq(BaseModel):
    email: str
    password: str


@api.post("/admin/login")
async def admin_login(req: AdminLoginReq):
    admin = await db.admins.find_one({"email": req.email.lower()}, {"_id": 0})
    if not admin or not _pwd.verify(req.password, admin["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = jwt.encode(
        {"sub": admin["email"], "role": "admin",
         "exp": datetime.now(timezone.utc) + timedelta(hours=12)},
        JWT_SECRET, algorithm=JWT_ALG,
    )
    return {"access_token": token, "token_type": "bearer",
            "admin": {"email": admin["email"]}}


@api.get("/admin/me")
async def admin_me(admin=Depends(_current_admin)):
    return admin


# ----- Menu management -----
@api.get("/admin/menus")
async def admin_list_menus(admin=Depends(_current_admin)):
    cur = db.weekly_menus.find({}, {"_id": 0}).sort("week_start", -1).limit(52)
    return await cur.to_list(52)


@api.post("/admin/menus")
async def admin_upsert_menu(menu: WeeklyMenu, admin=Depends(_current_admin)):
    doc = menu.model_dump()
    await db.weekly_menus.update_one(
        {"week_start": menu.week_start}, {"$set": doc}, upsert=True
    )
    return {"ok": True, "menu": doc}


@api.delete("/admin/menus/{week_start}")
async def admin_delete_menu(week_start: str, admin=Depends(_current_admin)):
    r = await db.weekly_menus.delete_one({"week_start": week_start})
    return {"ok": True, "deleted": r.deleted_count}


class MenuItemUpsertReq(BaseModel):
    item: MenuItem


@api.post("/admin/menus/{week_start}/items")
async def admin_add_menu_item(week_start: str, req: MenuItemUpsertReq,
                              admin=Depends(_current_admin)):
    menu = await db.weekly_menus.find_one({"week_start": week_start}, {"_id": 0})
    if not menu:
        raise HTTPException(404, "Menu not found for that week")
    items = menu.get("items", [])
    # If item_id already exists → update; else append.
    replaced = False
    for i, it in enumerate(items):
        if it.get("item_id") == req.item.item_id:
            items[i] = req.item.model_dump()
            replaced = True
            break
    if not replaced:
        items.append(req.item.model_dump())
    await db.weekly_menus.update_one(
        {"week_start": week_start}, {"$set": {"items": items}}
    )
    return {"ok": True, "item": req.item.model_dump(), "replaced": replaced}


@api.delete("/admin/menus/{week_start}/items/{item_id}")
async def admin_delete_menu_item(week_start: str, item_id: str,
                                 admin=Depends(_current_admin)):
    r = await db.weekly_menus.update_one(
        {"week_start": week_start}, {"$pull": {"items": {"item_id": item_id}}}
    )
    return {"ok": True, "modified": r.modified_count}


# ----- Catering management -----
@api.get("/admin/catering")
async def admin_list_catering(admin=Depends(_current_admin)):
    cur = db.catering_packages.find({}, {"_id": 0}).sort([("sort_order", 1), ("price_cents", 1)])
    return await cur.to_list(100)


@api.post("/admin/catering")
async def admin_upsert_catering(pkg: CateringPackage, admin=Depends(_current_admin)):
    doc = pkg.model_dump()
    await db.catering_packages.update_one(
        {"package_id": pkg.package_id}, {"$set": doc}, upsert=True
    )
    return {"ok": True, "package": doc}


@api.delete("/admin/catering/{package_id}")
async def admin_delete_catering(package_id: str, admin=Depends(_current_admin)):
    r = await db.catering_packages.delete_one({"package_id": package_id})
    return {"ok": True, "deleted": r.deleted_count}


# ----- Orders management -----
@api.get("/admin/orders")
async def admin_list_orders(status_filter: Optional[str] = None,
                            statuses: Optional[str] = None,
                            admin=Depends(_current_admin)):
    q: dict = {}
    if status_filter:
        q["status"] = status_filter
    elif statuses:
        vals = [s.strip() for s in statuses.split(",") if s.strip()]
        if vals:
            q["status"] = {"$in": vals}
    cur = db.orders.find(q, {"_id": 0}).sort("created_at", -1).limit(200)
    orders = await cur.to_list(200)
    # Batch-resolve linked users → attach a friendly customer_name + a user_summary blob.
    user_ids = list({o["user_id"] for o in orders if o.get("user_id")})
    users: dict = {}
    if user_ids:
        async for u in db.users.find({"user_id": {"$in": user_ids}},
                                     {"_id": 0, "user_id": 1, "name": 1, "email": 1, "phone": 1}):
            users[u["user_id"]] = u
    for o in orders:
        u = users.get(o.get("user_id")) or {}
        addr_name = ((o.get("address") or {}).get("name") or "").strip()
        user_name = (u.get("name") or "").strip()
        o["customer_name"] = addr_name or user_name or "Guest"
        o["user_summary"] = u
    return orders


class AdminOrderStatusReq(BaseModel):
    status: str
    note: Optional[str] = ""


@api.post("/admin/orders/{order_id}/status")
async def admin_update_order_status(order_id: str, req: AdminOrderStatusReq,
                                    admin=Depends(_current_admin)):
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    events = order.get("tracking_events", []) + [{
        "status": req.status,
        "ts": datetime.now(timezone.utc).isoformat(),
        "note": req.note or "",
    }]
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {"status": req.status, "tracking_events": events,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    try:
        await send_push(
            recipients=[order["user_id"]],
            data={"title": f"Order update: {req.status.replace('_',' ').title()}",
                  "message": req.note or "Your order status changed.",
                  "action_url": f"/order/{order_id}"},
        )
    except Exception:
        pass
    return {"ok": True}


@api.get("/admin/stats")
async def admin_stats(admin=Depends(_current_admin)):
    total_orders = await db.orders.count_documents({"status": {"$ne": "pending_payment"}})
    delivered = await db.orders.count_documents({"status": "delivered"})
    active = await db.orders.count_documents({
        "status": {"$in": ["preparing", "out_for_delivery"]}
    })
    users = await db.users.count_documents({})
    # gross revenue (paid + cod combined)
    pipe = [
        {"$match": {"status": {"$ne": "pending_payment"}}},
        {"$group": {"_id": None, "sum": {"$sum": "$total_cents"}}},
    ]
    agg = await db.orders.aggregate(pipe).to_list(1)
    revenue_cents = (agg[0]["sum"] if agg else 0) or 0
    return {
        "total_orders": total_orders,
        "delivered": delivered,
        "active": active,
        "users": users,
        "revenue_cents": revenue_cents,
    }


# ==========================================================
# PUBLIC SETTINGS (customer app reads tax label etc.)
# ==========================================================
@api.get("/brand")
async def brand_info():
    """Public brand metadata — consumed by the web admin bundle so it can
    show the tenant's brand name/legal name/support email without needing
    a build-time recompile per tenant. Never returns secrets."""
    return brand_as_dict()


@api.get("/platform/status")
async def platform_status():
    """Public snapshot of what the Suparna Dey Platform last told us about
    this tenant. Consumed by the admin dashboard banner and the customer
    cart to decide whether to hide checkout.

    Returns `{known: false, operational: true}` when the tenant isn't wired
    to a platform (safe fail-open for dev/preview)."""
    from platform_client import snapshot
    return snapshot()


# ---------------------------------------------------------------------------
# Suparna Dey Platform · Billing (Phase 3)
# ---------------------------------------------------------------------------
# These endpoints are the tenant-side proxy in front of the central hub's
# Stripe integration. The hub owns Stripe entirely; we just pass through
# the tenant's own API key on every request so the hub can identify us.
#
# UI contract (see /app/frontend/app/admin/billing.tsx):
#   GET  /admin/billing/summary   → { status, plan, card, invoices, ... }
#   POST /admin/billing/subscribe → { url }   Stripe Checkout URL
#   POST /admin/billing/portal    → { url }   Stripe Customer Portal URL

class _BillingUrlsReq(BaseModel):
    success_url: Optional[str] = None
    cancel_url:  Optional[str] = None
    return_url:  Optional[str] = None


@api.get("/admin/billing/summary")
async def admin_billing_summary(force: bool = False, admin=Depends(_current_admin)):
    """Returns the current billing state as seen from the hub. Cached 60s
    server-side. Pass `?force=true` to bust the cache after a Stripe redirect."""
    from billing_client import get_summary
    return await get_summary(force=force)


@api.post("/admin/billing/subscribe")
async def admin_billing_subscribe(req: _BillingUrlsReq, admin=Depends(_current_admin)):
    """Kick off a Stripe Checkout session on the hub. The frontend opens
    the returned URL in a new tab; the hub webhook flips this tenant to
    `active` and our poller picks it up within 5 minutes (or force-refresh)."""
    from billing_client import create_checkout
    if not req.success_url or not req.cancel_url:
        raise HTTPException(400, "success_url and cancel_url are required")
    return await create_checkout(req.success_url, req.cancel_url)


@api.post("/admin/billing/portal")
async def admin_billing_portal(req: _BillingUrlsReq, admin=Depends(_current_admin)):
    """Get a Stripe Customer Portal URL for the restaurant owner to update
    card, download invoices, or cancel. Requires an existing subscription."""
    from billing_client import create_portal
    if not req.return_url:
        raise HTTPException(400, "return_url is required")
    return await create_portal(req.return_url)


@api.get("/settings")
async def public_settings():
    s = await _get_settings()
    # Only expose non-sensitive fields
    return {
        "business_name": s.get("business_name"),
        "phone": s.get("phone"),
        "email": s.get("email"),
        "delivery_areas": s.get("delivery_areas", []),
        "operating_hours": s.get("operating_hours", ""),
        "ordering_days": s.get("ordering_days", [0, 1, 2, 3, 4]),
        "delivery_days": s.get("delivery_days", [5, 6]),
        "default_delivery_fee_cents": s.get("default_delivery_fee_cents", 599),
        "minimum_order_cents": s.get("minimum_order_cents", 0),
        "tax_enabled": s.get("tax_enabled", True),
        "tax_rate_bps": s.get("tax_rate_bps", 1300),
        "tax_label": s.get("tax_label", "HST"),
        "currency": s.get("currency", "CAD"),
        "loyalty_enabled": bool(s.get("loyalty_enabled", True)),
        "loyalty_earn_points_per_dollar": int(s.get("loyalty_earn_points_per_dollar", 1) or 0),
        "loyalty_redeem_points_per_dollar": int(s.get("loyalty_redeem_points_per_dollar", 100) or 100),
        "home_hero_tagline": s.get("home_hero_tagline", "Order anytime this week — we deliver every weekend."),
        # Expose ONLY safe payment-method fields (never secret keys) so the customer app
        # can render the right method list, apply per-method tax, and show Interac email.
        "payment_methods": {
            k: {
                "enabled":       bool(v.get("enabled", False)),
                "tax_enabled":   bool(v.get("tax_enabled", True)),
                # Interac needs its e-Transfer email in the customer flow
                **({"email": v.get("email", "")} if k == "interac" else {}),
                **({"instructions": v.get("instructions", "")} if k == "interac" else {}),
                # Stripe/PayPal publishable client-side identifiers ARE safe to return
                **({"publishable_key": v.get("publishable_key", "")} if k == "stripe" else {}),
                **({"client_id": v.get("client_id", "")} if k == "paypal" else {}),
            }
            for k, v in (s.get("payment_methods") or {}).items()
        },
    }


# ==========================================================
# ADMIN — Master Menu, Settings, Invoice
# ==========================================================
@api.get("/admin/settings")
async def admin_get_settings(admin=Depends(_current_admin)):
    return await _get_settings()


@api.put("/admin/settings")
async def admin_put_settings(payload: BusinessSettings, admin=Depends(_current_admin)):
    doc = payload.model_dump()
    doc["key"] = "default"
    await db.business_settings.update_one({"key": "default"}, {"$set": doc}, upsert=True)
    return {"ok": True, "settings": doc}


# ---------------- Admin: Coupons CRUD ----------------
def _clean_coupon_payload(payload: Coupon) -> dict:
    """Validate + normalise a coupon payload into a storable dict."""
    doc = payload.model_dump()
    doc["code"] = (doc.get("code") or "").strip().upper()
    if not doc["code"]:
        raise HTTPException(400, "Coupon code is required")
    if doc["discount_type"] not in ("percent", "fixed"):
        raise HTTPException(400, "discount_type must be 'percent' or 'fixed'")
    try:
        doc["value"] = int(doc.get("value") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "value must be a number")
    if doc["discount_type"] == "percent" and not (1 <= doc["value"] <= 100):
        raise HTTPException(400, "Percent discount must be between 1 and 100")
    if doc["discount_type"] == "fixed" and doc["value"] < 1:
        raise HTTPException(400, "Fixed discount must be at least 1 cent")
    doc["min_order_cents"] = max(0, int(doc.get("min_order_cents") or 0))
    return doc


async def _assert_single_first_time(doc: dict, exclude_code: Optional[str] = None):
    """Enforce only ONE active first-time coupon at a time."""
    if not (doc.get("active") and doc.get("first_time_only")):
        return
    q = {"active": True, "first_time_only": True, "code": {"$ne": doc["code"]}}
    if exclude_code and exclude_code != doc["code"]:
        q["code"] = {"$nin": [doc["code"], exclude_code]}
    existing = await db.coupons.find_one(q, {"_id": 0, "code": 1})
    if existing:
        raise HTTPException(
            400,
            f"'{existing['code']}' is already the active first-time coupon. "
            f"Deactivate it before making this one first-time-only.",
        )


@api.get("/admin/coupons")
async def admin_list_coupons(admin=Depends(_current_admin)):
    coupons = await db.coupons.find({}, {"_id": 0}).sort("code", 1).to_list(500)
    return {"coupons": coupons}


@api.post("/admin/coupons")
async def admin_create_coupon(payload: Coupon, admin=Depends(_current_admin)):
    doc = _clean_coupon_payload(payload)
    if await db.coupons.find_one({"code": doc["code"]}):
        raise HTTPException(400, f"Coupon '{doc['code']}' already exists")
    await _assert_single_first_time(doc)
    await db.coupons.insert_one(dict(doc))
    return {"ok": True, "coupon": doc}


@api.put("/admin/coupons/{code}")
async def admin_update_coupon(code: str, payload: Coupon, admin=Depends(_current_admin)):
    orig = (code or "").strip().upper()
    existing = await db.coupons.find_one({"code": orig})
    if not existing:
        raise HTTPException(404, "Coupon not found")
    doc = _clean_coupon_payload(payload)
    # Renaming to an already-taken code is not allowed.
    if doc["code"] != orig and await db.coupons.find_one({"code": doc["code"]}):
        raise HTTPException(400, f"Coupon '{doc['code']}' already exists")
    await _assert_single_first_time(doc, exclude_code=orig)
    await db.coupons.update_one({"code": orig}, {"$set": doc})
    return {"ok": True, "coupon": doc}


@api.delete("/admin/coupons/{code}")
async def admin_delete_coupon(code: str, admin=Depends(_current_admin)):
    orig = (code or "").strip().upper()
    r = await db.coupons.delete_one({"code": orig})
    if r.deleted_count == 0:
        raise HTTPException(404, "Coupon not found")
    return {"ok": True}


@api.get("/admin/master-menu")
async def admin_master_list(
    q: Optional[str] = None,
    category: Optional[str] = None,
    cuisine: Optional[str] = None,
    active: Optional[str] = None,
    admin=Depends(_current_admin),
):
    query: dict = {}
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    if category:
        query["category"] = category
    if cuisine:
        query["cuisine"] = cuisine
    if active in ("true", "false"):
        query["is_active"] = (active == "true")
    cur = db.master_menu.find(query, {"_id": 0}).sort([("display_order", 1), ("name", 1)]).limit(500)
    return await cur.to_list(500)


@api.get("/admin/master-menu/{item_id}")
async def admin_master_get(item_id: str, admin=Depends(_current_admin)):
    it = await db.master_menu.find_one({"item_id": item_id}, {"_id": 0})
    if not it:
        raise HTTPException(404, "Not found")
    return it


@api.post("/admin/master-menu")
async def admin_master_upsert(item: MasterMenuItem, admin=Depends(_current_admin)):
    item.updated_at = datetime.now(timezone.utc)
    await db.master_menu.update_one(
        {"item_id": item.item_id}, {"$set": item.model_dump()}, upsert=True
    )
    return {"ok": True, "item": item.model_dump()}


# ----------------------------------------------------------
# BULK AI-ENRICHED IMPORT (name + price CSV → AI fills the rest)
# ----------------------------------------------------------
from menu_ai import enrich_item as _ai_enrich_item

class BulkPreviewRow(BaseModel):
    name: str
    default_price_cents: int = 0

class BulkPreviewReq(BaseModel):
    rows: List[BulkPreviewRow]
    generate_images: bool = True

@api.post("/admin/master-menu/bulk-preview")
async def admin_master_bulk_preview(req: BulkPreviewReq, admin=Depends(_current_admin)):
    """Take a list of {name, price} rows, ask the LLM to fill in all remaining fields
    (description / category / cuisine / veg-type / spice / allergens) AND generate a food
    image per row. Runs enrichment in parallel for speed.
    Nothing is written to the DB yet — the admin must call /bulk-save after review.
    Image URLs are returned as RELATIVE paths (`/api/uploads/menu/xxx.png`) — the
    frontend prepends its BACKEND_URL so images work in both web preview & native builds.
    """
    import asyncio as _asyncio

    if not req.rows:
        raise HTTPException(400, "No rows provided")
    if len(req.rows) > 25:
        raise HTTPException(400, "Max 25 rows per bulk upload")

    # Filter blanks & keep original order for the response.
    clean = [(r.name.strip(), max(0, int(r.default_price_cents or 0))) for r in req.rows if r.name and r.name.strip()]
    if not clean:
        raise HTTPException(400, "All rows are blank")

    # Enrich in parallel, but cap concurrency so we don't slam the LLM.
    sem = _asyncio.Semaphore(5)
    async def _one(name: str, price: int) -> dict:
        async with sem:
            try:
                ai = await _ai_enrich_item(name, price, want_image=req.generate_images)
            except Exception as e:
                log.warning(f"bulk-preview enrich failed for {name!r}: {e}")
                # graceful fallback
                from menu_ai import _fallback_text
                ai = {**_fallback_text(name), "image_url": ""}
            return {
                "item_id": f"mi_{uuid.uuid4().hex[:10]}",
                "name": name,
                "default_price_cents": price,
                "cost_price_cents": 0,
                "short_description": ai["short_description"],
                "full_description":  ai["full_description"],
                "category":     ai["category"],
                "cuisine":      ai["cuisine"],
                "veg_type":     ai["veg_type"],
                "spice_level":  ai["spice_level"],
                "allergens":    ai["allergens"],
                "image_url":    ai["image_url"],   # RELATIVE — frontend prepends host
                "extra_images": [],
                "is_active":    True,
                "prep_notes":   "",
                "kitchen_notes":"",
                "display_order": 0,
            }

    previews = await _asyncio.gather(*[_one(n, p) for (n, p) in clean])
    return {"ok": True, "previews": previews}


class BulkSaveReq(BaseModel):
    items: List[MasterMenuItem]

@api.post("/admin/master-menu/bulk-save")
async def admin_master_bulk_save(req: BulkSaveReq, admin=Depends(_current_admin)):
    """Persist the reviewed items in one batch. Returns count saved."""
    if not req.items:
        raise HTTPException(400, "No items to save")
    saved = 0
    for it in req.items:
        it.updated_at = datetime.now(timezone.utc)
        await db.master_menu.update_one(
            {"item_id": it.item_id}, {"$set": it.model_dump()}, upsert=True
        )
        saved += 1
    return {"ok": True, "saved": saved}


@api.post("/admin/master-menu/{item_id}/duplicate")
async def admin_master_duplicate(item_id: str, admin=Depends(_current_admin)):
    src = await db.master_menu.find_one({"item_id": item_id}, {"_id": 0})
    if not src:
        raise HTTPException(404, "Not found")
    src["item_id"] = f"mi_{uuid.uuid4().hex[:10]}"
    src["name"] = f"{src['name']} (Copy)"
    src["created_at"] = datetime.now(timezone.utc)
    src["updated_at"] = src["created_at"]
    await db.master_menu.insert_one(src)
    return {"ok": True, "item_id": src["item_id"]}


@api.delete("/admin/master-menu/{item_id}")
async def admin_master_delete(item_id: str, admin=Depends(_current_admin)):
    r = await db.master_menu.delete_one({"item_id": item_id})
    return {"ok": True, "deleted": r.deleted_count}


class BulkActionReq(BaseModel):
    item_ids: List[str]
    action: str  # "activate" | "deactivate" | "delete"


@api.post("/admin/master-menu/bulk")
async def admin_master_bulk(req: BulkActionReq, admin=Depends(_current_admin)):
    if req.action == "activate":
        r = await db.master_menu.update_many({"item_id": {"$in": req.item_ids}}, {"$set": {"is_active": True}})
        return {"ok": True, "modified": r.modified_count}
    if req.action == "deactivate":
        r = await db.master_menu.update_many({"item_id": {"$in": req.item_ids}}, {"$set": {"is_active": False}})
        return {"ok": True, "modified": r.modified_count}
    if req.action == "delete":
        r = await db.master_menu.delete_many({"item_id": {"$in": req.item_ids}})
        return {"ok": True, "deleted": r.deleted_count}
    raise HTTPException(400, "Unknown action")


# Weekly Menu v2 — line-level control
class WeeklyLineUpsertReq(BaseModel):
    line: WeeklyMenuLine


@api.post("/admin/menus/{week_start}/lines")
async def admin_add_weekly_line(week_start: str, req: WeeklyLineUpsertReq,
                                admin=Depends(_current_admin)):
    menu = await db.weekly_menus.find_one({"week_start": week_start}, {"_id": 0})
    if not menu:
        raise HTTPException(404, "Weekly menu not found")
    lines = menu.get("lines", [])
    replaced = False
    for i, ln in enumerate(lines):
        if ln.get("line_id") == req.line.line_id:
            lines[i] = req.line.model_dump()
            replaced = True
            break
    if not replaced:
        lines.append(req.line.model_dump())
    await db.weekly_menus.update_one(
        {"week_start": week_start}, {"$set": {"lines": lines}}
    )
    return {"ok": True, "line": req.line.model_dump(), "replaced": replaced}


@api.delete("/admin/menus/{week_start}/lines/{line_id}")
async def admin_delete_weekly_line(week_start: str, line_id: str,
                                   admin=Depends(_current_admin)):
    r = await db.weekly_menus.update_one(
        {"week_start": week_start}, {"$pull": {"lines": {"line_id": line_id}}}
    )
    return {"ok": True, "modified": r.modified_count}


class WeeklyMenuSettingsReq(BaseModel):
    alacarte_enabled: Optional[bool] = None
    package_enabled: Optional[bool] = None
    package: Optional[WeeklyMenuPackage] = None


@api.post("/admin/menus/{week_start}/settings")
async def admin_update_weekly_settings(week_start: str, req: WeeklyMenuSettingsReq,
                                       admin=Depends(_current_admin)):
    """Update per-week toggles + package config (alacarte/package mode)."""
    menu = await db.weekly_menus.find_one({"week_start": week_start}, {"_id": 0})
    if not menu:
        raise HTTPException(404, "Weekly menu not found")
    patch: Dict[str, Any] = {}
    if req.alacarte_enabled is not None:
        patch["alacarte_enabled"] = req.alacarte_enabled
    if req.package_enabled is not None:
        patch["package_enabled"] = req.package_enabled
    if req.package is not None:
        patch["package"] = req.package.model_dump()
    if not patch:
        return {"ok": True, "unchanged": True}
    # Safety: don't allow both toggles off (customer would see nothing)
    final_alac = patch.get("alacarte_enabled", menu.get("alacarte_enabled", True))
    final_pkg = patch.get("package_enabled", menu.get("package_enabled", False))
    if not final_alac and not final_pkg:
        raise HTTPException(400, "At least one of à la carte or package must be enabled.")
    await db.weekly_menus.update_one({"week_start": week_start}, {"$set": patch})
    doc = await db.weekly_menus.find_one({"week_start": week_start}, {"_id": 0})
    return {"ok": True, "menu": doc}


class CreateWeekReq(BaseModel):
    week_start: str
    title: Optional[str] = None
    copy_all_master: bool = False


@api.post("/admin/menus/create")
async def admin_create_week(req: CreateWeekReq, admin=Depends(_current_admin)):
    """Create a new weekly menu. Optionally seed the à-la-carte section with ALL
    active Master Menu items (added hidden — the admin turns on the ones they
    want visible this week)."""
    existing = await db.weekly_menus.find_one({"week_start": req.week_start}, {"_id": 0})
    if existing:
        raise HTTPException(400, "A menu for that week already exists.")
    lines: List[dict] = []
    if req.copy_all_master:
        cur = db.master_menu.find({"is_active": {"$ne": False}}, {"_id": 0})
        items = [m async for m in cur]
        items.sort(key=lambda m: (m.get("name") or "").lower())
        for i, m in enumerate(items):
            lines.append(WeeklyMenuLine(
                master_item_id=m["item_id"],
                is_visible=False,          # hidden by default per spec
                display_order=i + 1,
            ).model_dump())
    menu = WeeklyMenu(
        week_start=req.week_start,
        title=(req.title or "").strip() or f"Week of {req.week_start}",
        lines=lines,
        published=True,
        status="published",
    )
    doc = menu.model_dump()
    await db.weekly_menus.update_one(
        {"week_start": req.week_start}, {"$set": doc}, upsert=True
    )
    return {"ok": True, "menu": doc}


class ComplimentaryReq(BaseModel):
    master_ids: List[str] = []


@api.post("/admin/menus/{week_start}/complimentary")
async def admin_set_complimentary(week_start: str, req: ComplimentaryReq,
                                  admin=Depends(_current_admin)):
    """Set the week's Complimentary This Week dishes (picked from Master Menu)."""
    menu = await db.weekly_menus.find_one({"week_start": week_start}, {"_id": 0})
    if not menu:
        raise HTTPException(404, "Weekly menu not found")
    await db.weekly_menus.update_one(
        {"week_start": week_start},
        {"$set": {"complimentary_master_ids": req.master_ids}},
    )
    doc = await db.weekly_menus.find_one({"week_start": week_start}, {"_id": 0})
    return {"ok": True, "menu": doc}


class LineVisibilityReq(BaseModel):
    is_visible: bool


@api.post("/admin/menus/{week_start}/lines/{line_id}/visibility")
async def admin_set_line_visibility(week_start: str, line_id: str,
                                    req: LineVisibilityReq,
                                    admin=Depends(_current_admin)):
    """Toggle whether a single à-la-carte dish is visible to customers this week."""
    r = await db.weekly_menus.update_one(
        {"week_start": week_start, "lines.line_id": line_id},
        {"$set": {"lines.$.is_visible": req.is_visible}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Line not found")
    return {"ok": True, "is_visible": req.is_visible}


class AlwaysAvailableReq(BaseModel):
    master_ids: List[str] = []


@api.get("/admin/always-available")
async def admin_get_always_available(admin=Depends(_current_admin)):
    """Return the global Always Available master-id list."""
    settings = await _get_settings()
    return {"master_ids": settings.get("always_available_master_ids") or []}


@api.post("/admin/always-available")
async def admin_set_always_available(req: AlwaysAvailableReq,
                                     admin=Depends(_current_admin)):
    """Replace the global Always Available master-id list. Reflects on the
    customer app immediately (customer screens poll /menu/anytime)."""
    await db.business_settings.update_one(
        {"key": "default"},
        {"$set": {"always_available_master_ids": req.master_ids}},
        upsert=True,
    )
    return {"ok": True, "master_ids": req.master_ids}


# Refund
@api.post("/admin/orders/{order_id}/refund")
async def admin_refund_order(order_id: str, admin=Depends(_current_admin)):
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {"refund_status": "refunded", "status": "cancelled",
                  "updated_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True}


# ==========================================================
# ADMIN — Integrations (Google Drive + Twilio SMS)
# ==========================================================
# Credentials are stored encrypted in business_settings.integrations.
# Only the encryption key lives in .env (INTEGRATIONS_FERNET_KEY).
# ==========================================================
from settings_crypto import (
    encrypt_service_account_json, encrypt_str, is_configured as crypto_configured,
)
from exports import build_orders_xlsx, build_customers_xlsx, default_filename, expand_order_items
import drive_client as _drive
import twilio_client as _twilio
import email_client as _email


# ==========================================================
# Temporary XLSX host — used by "email" and "sms" export
# destinations. Files live in MongoDB for 48 hours, then are
# auto-cleaned by a TTL index.
# ==========================================================
import secrets as _secrets
import base64 as _b64

async def _stash_xlsx(data: bytes, filename: str) -> str:
    """Store XLSX bytes with a random token; returns the token.
    Also opportunistically evicts already-expired rows to keep the collection lean
    (we removed the destructive TTL index — see startup notes)."""
    try:
        await db.export_files.delete_many({
            "expires_at": {"$lt": datetime.now(timezone.utc)}
        })
    except Exception as _cleanup_err:
        log.warning(f"export_files lazy-cleanup skipped: {_cleanup_err}")
    token = _secrets.token_urlsafe(24)
    await db.export_files.insert_one({
        "token": token,
        "filename": filename,
        "content_b64": _b64.b64encode(data).decode(),
        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=48),
    })
    return token


def _download_url(token: str) -> str:
    """Build the full public download URL from the current request context.
    Falls back to a relative path if not available.
    """
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if base:
        return f"{base}/api/exports/{token}"
    # In production the K8s ingress serves this at same origin; caller can
    # append their frontend host. Return a full-ish URL that Twilio/Resend
    # will accept via `PUBLIC_BASE_URL` env or the request.base_url in the
    # handler below.
    return f"/api/exports/{token}"


@app.get("/api/exports/{token}")
async def get_export_file(token: str):
    """Public download endpoint. Time-limited via `expires_at`.
    The token is 32 URL-safe bytes → 256 bits of entropy, unguessable."""
    doc = await db.export_files.find_one({"token": token})
    if not doc:
        raise HTTPException(404, "Download link expired or invalid")
    expires = doc.get("expires_at")
    if expires:
        # MongoDB may return naive datetime — coerce to UTC before comparing.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            # Best-effort cleanup (TTL index also runs)
            await db.export_files.delete_one({"token": token})
            raise HTTPException(410, "Download link expired")
    import base64
    data = base64.b64decode(doc["content_b64"])
    from fastapi.responses import Response
    return Response(
        content=data,
        media_type=doc.get("content_type",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={
            "Content-Disposition": f'attachment; filename="{doc["filename"]}"',
            "Cache-Control": "no-store, private",
        },
    )


class DriveSettingsIn(BaseModel):
    service_account_json: Optional[str] = None  # full JSON blob; None = leave unchanged
    folder_id: str
    user_email: EmailStr


class TwilioSettingsIn(BaseModel):
    account_sid: str
    auth_token: Optional[str] = None  # None = leave unchanged
    from_number: str


class TestSmsIn(BaseModel):
    to_number: str


class TestDriveIn(BaseModel):
    # No fields needed; uses stored config
    pass


async def _get_integrations() -> dict:
    doc = await db.business_settings.find_one({"key": "default"}, {"_id": 0}) or {}
    return (doc.get("integrations") or {})


@api.get("/admin/integrations")
async def admin_get_integrations(admin=Depends(_current_admin)):
    """Return integration settings WITH secrets masked (never return ciphertext)."""
    ints = await _get_integrations()
    drive = ints.get("google_drive") or {}
    twilio = ints.get("twilio") or {}
    email_cfg = ints.get("email") or {}
    return {
        "crypto_ready": crypto_configured(),
        "email": {
            "configured": _email.is_configured(),  # Emergent key present
            "recipient": email_cfg.get("recipient", ""),  # where exports get emailed to
            "last_test_ok": email_cfg.get("last_test_ok"),
            "last_test_at": email_cfg.get("last_test_at"),
        },
        "google_drive": {
            "configured": bool(drive.get("service_account_json_encrypted")),
            "folder_id": drive.get("folder_id", ""),
            "user_email": drive.get("user_email", ""),
            "client_email": drive.get("client_email", ""),  # service-account email (non-secret)
            "last_test_ok": drive.get("last_test_ok"),
            "last_test_at": drive.get("last_test_at"),
        },
        "twilio": {
            "configured": bool(twilio.get("auth_token_encrypted")),
            "account_sid": twilio.get("account_sid", ""),
            "from_number": twilio.get("from_number", ""),
            "last_test_ok": twilio.get("last_test_ok"),
            "last_test_at": twilio.get("last_test_at"),
        },
    }


class EmailSettingsIn(BaseModel):
    recipient: EmailStr


class TestEmailIn(BaseModel):
    to: Optional[EmailStr] = None  # override recipient for testing


@api.put("/admin/integrations/email")
async def admin_save_email_settings(payload: EmailSettingsIn,
                                     admin=Depends(_current_admin)):
    await db.business_settings.update_one(
        {"key": "default"},
        {"$set": {"integrations.email.recipient": str(payload.recipient)}},
        upsert=True,
    )
    return {"ok": True}


@api.post("/admin/integrations/email/test")
async def admin_test_email(payload: TestEmailIn, admin=Depends(_current_admin)):
    ints = await _get_integrations()
    to = (payload.to and str(payload.to)) or (ints.get("email") or {}).get("recipient")
    if not to:
        raise HTTPException(400, "Add a recipient email in Settings first")
    subject = f"{_email.EMAIL_FROM_NAME} — email integration test"
    html = (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;'
        'font-family:Arial,sans-serif;color:#2A1D18">'
        f'<h2 style="margin:0 0 12px;color:#B14F36">{_email.EMAIL_FROM_NAME}</h2>'
        f'<p>This is a test email from your {BRAND_NAME} Admin Portal.</p>'
        '<p>If you received this, your email integration is working — every '
        'export you trigger with the &quot;Email me&quot; button will land in this inbox.</p>'
        '<p style="font-size:12px;color:#888;margin-top:24px">Sent by '
        f'{_email.EMAIL_FROM_NAME} · Admin Exports. We never ask for your password '
        'or card details by email.</p>'
        '</td></tr></table>'
    )
    try:
        msg_id = await _email.send_email(to=to, subject=subject, html=html)
    except _email.EmailError as e:
        await db.business_settings.update_one(
            {"key": "default"},
            {"$set": {"integrations.email.last_test_ok": False,
                      "integrations.email.last_test_at": datetime.now(timezone.utc).isoformat(),
                      "integrations.email.last_test_error": e.message}},
        )
        raise HTTPException(e.status, e.message)
    await db.business_settings.update_one(
        {"key": "default"},
        {"$set": {"integrations.email.last_test_ok": True,
                  "integrations.email.last_test_at": datetime.now(timezone.utc).isoformat(),
                  "integrations.email.last_test_error": ""}},
    )
    return {"ok": True, "message_id": msg_id, "to": to}


@api.put("/admin/integrations/google-drive")
async def admin_save_drive_settings(payload: DriveSettingsIn,
                                     admin=Depends(_current_admin)):
    if not crypto_configured():
        raise HTTPException(500, "INTEGRATIONS_FERNET_KEY not configured on backend")
    upd: dict = {
        "integrations.google_drive.folder_id": payload.folder_id.strip(),
        "integrations.google_drive.user_email": str(payload.user_email),
    }
    if payload.service_account_json and payload.service_account_json.strip():
        try:
            enc = encrypt_service_account_json(payload.service_account_json)
            # Extract non-secret client_email for display in UI
            import json as _json
            client_email = _json.loads(payload.service_account_json).get("client_email", "")
        except Exception as e:
            raise HTTPException(400, f"Invalid service-account JSON: {e}")
        upd["integrations.google_drive.service_account_json_encrypted"] = enc
        upd["integrations.google_drive.client_email"] = client_email
    await db.business_settings.update_one(
        {"key": "default"}, {"$set": upd}, upsert=True,
    )
    return {"ok": True}


@api.post("/admin/integrations/google-drive/test")
async def admin_test_drive(admin=Depends(_current_admin)):
    ints = await _get_integrations()
    gd = ints.get("google_drive") or {}
    if not gd.get("service_account_json_encrypted") or not gd.get("folder_id"):
        raise HTTPException(400, "Google Drive settings incomplete — paste JSON + folder ID first")
    try:
        folder = await _drive.test_folder(
            gd["service_account_json_encrypted"], gd["folder_id"],
        )
    except _drive.DriveError as e:
        # Store last test failure so UI can surface it
        await db.business_settings.update_one(
            {"key": "default"},
            {"$set": {"integrations.google_drive.last_test_ok": False,
                      "integrations.google_drive.last_test_at": datetime.now(timezone.utc).isoformat(),
                      "integrations.google_drive.last_test_error": e.message}},
        )
        raise HTTPException(e.status, e.message)
    if folder.get("mimeType") != "application/vnd.google-apps.folder":
        raise HTTPException(400, "Configured ID is not a Drive folder")
    await db.business_settings.update_one(
        {"key": "default"},
        {"$set": {"integrations.google_drive.last_test_ok": True,
                  "integrations.google_drive.last_test_at": datetime.now(timezone.utc).isoformat(),
                  "integrations.google_drive.last_test_error": ""}},
    )
    return {"ok": True, "folder": {"id": folder["id"], "name": folder["name"]}}


@api.put("/admin/integrations/twilio")
async def admin_save_twilio_settings(payload: TwilioSettingsIn,
                                      admin=Depends(_current_admin)):
    if not crypto_configured():
        raise HTTPException(500, "INTEGRATIONS_FERNET_KEY not configured on backend")
    upd: dict = {
        "integrations.twilio.account_sid": payload.account_sid.strip(),
        "integrations.twilio.from_number": payload.from_number.strip(),
    }
    if payload.auth_token and payload.auth_token.strip():
        upd["integrations.twilio.auth_token_encrypted"] = encrypt_str(payload.auth_token.strip())
    await db.business_settings.update_one(
        {"key": "default"}, {"$set": upd}, upsert=True,
    )
    return {"ok": True}


@api.post("/admin/integrations/twilio/test")
async def admin_test_twilio(payload: TestSmsIn, admin=Depends(_current_admin)):
    ints = await _get_integrations()
    tw = ints.get("twilio") or {}
    if not tw.get("auth_token_encrypted") or not tw.get("account_sid") or not tw.get("from_number"):
        raise HTTPException(400, "Twilio settings incomplete — enter SID, token & from number first")
    try:
        res = await _twilio.send_test_sms(
            tw["account_sid"], tw["auth_token_encrypted"],
            tw["from_number"], payload.to_number,
        )
    except _twilio.TwilioError as e:
        await db.business_settings.update_one(
            {"key": "default"},
            {"$set": {"integrations.twilio.last_test_ok": False,
                      "integrations.twilio.last_test_at": datetime.now(timezone.utc).isoformat(),
                      "integrations.twilio.last_test_error": e.message}},
        )
        raise HTTPException(e.status, e.message)
    await db.business_settings.update_one(
        {"key": "default"},
        {"$set": {"integrations.twilio.last_test_ok": True,
                  "integrations.twilio.last_test_at": datetime.now(timezone.utc).isoformat(),
                  "integrations.twilio.last_test_error": ""}},
    )
    return {"ok": True, "message_sid": res["sid"], "status": res["status"]}


# ==========================================================
# ADMIN — Orders export (download / drive / sms)
# ==========================================================
class OrdersExportReq(BaseModel):
    order_ids: List[str] = Field(default_factory=list)  # empty = ALL current filter
    destination: str  # "download" | "email" | "sms" | "drive"
    sms_to: Optional[str] = None  # required if destination == "sms"
    sms_message: Optional[str] = None  # optional custom SMS body
    email_to: Optional[EmailStr] = None  # override recipient; else use configured


async def _resolve_orders(order_ids: List[str]) -> List[dict]:
    q: dict = {}
    if order_ids:
        q["order_id"] = {"$in": order_ids}
    cur = db.orders.find(q, {"_id": 0}).sort("created_at", -1).limit(2000)
    orders = await cur.to_list(2000)
    # Attach user summary like admin_list_orders does
    user_ids = list({o["user_id"] for o in orders if o.get("user_id")})
    users: dict = {}
    if user_ids:
        async for u in db.users.find({"user_id": {"$in": user_ids}},
                                     {"_id": 0, "user_id": 1, "name": 1, "email": 1, "phone": 1}):
            users[u["user_id"]] = u
    for o in orders:
        u = users.get(o.get("user_id")) or {}
        addr_name = ((o.get("address") or {}).get("name") or "").strip()
        o["customer_name"] = addr_name or u.get("name") or "Guest"
        o["user_summary"] = u
    return orders


def _abs_export_url(request: Request, token: str) -> str:
    """Build an absolute /api/exports/{token} URL using the incoming request host.
    Always returns an https URL — the email guardrail rejects http links, and in
    production K8s always terminates TLS at the ingress anyway.
    """
    env = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if env:
        return f"{env}/api/exports/{token}"
    # Take request.base_url and force scheme to https.
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(str(request.base_url))
    # If we're on localhost dev, prefer the preview tunnel host if set.
    host = parts.hostname or ""
    if host in ("localhost", "127.0.0.1"):
        preview = os.environ.get("EXPO_PACKAGER_HOSTNAME", "").rstrip("/")
        if preview:
            return f"{preview.replace('http://', 'https://')}/api/exports/{token}"
    forced = urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))
    return forced.rstrip("/") + f"/api/exports/{token}"


async def _finalize_export(
    request: Request,
    kind_label: str,  # "orders" | "customers"
    payload_destination: str,
    payload_sms_to: Optional[str],
    payload_sms_message: Optional[str],
    payload_email_to: Optional[str],
    xlsx: bytes,
    filename: str,
    count: int,
    sms_default_body: Optional[str] = None,  # detailed body built by caller
) -> dict:
    """Shared final step for both export endpoints. Handles download/email/sms/drive."""
    import base64
    if payload_destination == "download":
        return {
            "kind": "download", "filename": filename,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "b64": base64.b64encode(xlsx).decode(),
            "count": count,
        }

    ints = await _get_integrations()

    if payload_destination == "email":
        recipient = (payload_email_to and str(payload_email_to)) or \
                    (ints.get("email") or {}).get("recipient")
        if not recipient:
            raise HTTPException(400, "No recipient email — set one in Settings or pass email_to")
        if not _email.is_configured():
            raise HTTPException(500, "Email integration is not configured on the backend")
        token = await _stash_xlsx(xlsx, filename)
        link = _abs_export_url(request, token)
        subject = f"{_email.EMAIL_FROM_NAME} — {kind_label.capitalize()} export ({count})"
        html = (
            '<table role="presentation" width="100%"><tr><td style="padding:24px;'
            'font-family:Arial,sans-serif;color:#2A1D18;max-width:560px">'
            f'<h2 style="margin:0 0 12px;color:#B14F36">{_email.EMAIL_FROM_NAME}</h2>'
            f'<p>Your <strong>{kind_label}</strong> export is ready — {count} '
            f'{"row" if count == 1 else "rows"}.</p>'
            f'<p style="margin:20px 0"><a href="{link}" style="background:#B14F36;'
            'color:#fff;padding:12px 20px;border-radius:24px;text-decoration:none;'
            'font-weight:800;display:inline-block">Download report</a></p>'
            f'<p style="font-size:12px;color:#666">File name: {filename}<br>'
            'Link expires in 48 hours.</p>'
            '<p style="font-size:11px;color:#aaa;margin-top:24px;border-top:1px solid #eee;padding-top:12px">'
            f'Sent by {_email.EMAIL_FROM_NAME} · Admin Exports. We never ask for '
            'your password or card details by email.</p>'
            '</td></tr></table>'
        )
        try:
            msg_id = await _email.send_email(to=recipient, subject=subject, html=html)
        except _email.EmailError as e:
            raise HTTPException(e.status, e.message)
        return {"kind": "email", "filename": filename, "recipient": recipient,
                "download_link": link, "message_id": msg_id, "count": count}

    if payload_destination == "sms":
        if not payload_sms_to or not payload_sms_to.strip():
            raise HTTPException(400, "sms_to (phone number) is required")
        tw = ints.get("twilio") or {}
        if not tw.get("auth_token_encrypted") or not tw.get("account_sid") or not tw.get("from_number"):
            raise HTTPException(400, "Twilio is not configured — set it up in Settings first")
        token = await _stash_xlsx(xlsx, filename)
        link = _abs_export_url(request, token)
        if payload_sms_message:
            body = payload_sms_message
        elif sms_default_body:
            body = sms_default_body.replace("{link}", link)
        else:
            body = (f"{_email.EMAIL_FROM_NAME}: {kind_label} export ({count}). "
                    f"Download (48h): {link}")
        try:
            sms = await _twilio.send_sms(
                tw["account_sid"], tw["auth_token_encrypted"],
                tw["from_number"], payload_sms_to.strip(), body,
            )
        except _twilio.TwilioError as e:
            raise HTTPException(e.status, e.message)
        return {"kind": "sms", "filename": filename, "download_link": link,
                "sms_status": sms["status"], "count": count}

    if payload_destination == "drive":
        gd = ints.get("google_drive") or {}
        if not gd.get("service_account_json_encrypted") or not gd.get("folder_id"):
            raise HTTPException(400, "Google Drive is not configured — set it up in Settings first")
        try:
            result = await _drive.upload_xlsx(
                gd["service_account_json_encrypted"], gd["folder_id"],
                gd.get("user_email"), filename, xlsx,
            )
        except _drive.DriveError as e:
            raise HTTPException(e.status, e.message)
        return {"kind": "drive", "filename": filename, "web_view_link": result["web_view_link"],
                "count": count}

    raise HTTPException(400, "destination must be download|email|sms|drive")


def _build_orders_sms_body(orders: list[dict]) -> str:
    """Build a delivery-driver-friendly SMS body listing each order's customer,
    address and itemized dishes. Uses `{link}` placeholder so the actual URL
    is substituted after the file is stashed. Safety-capped at ~1400 chars so
    Twilio doesn't fragment into 15+ segments.
    """
    def _addr(a: dict) -> str:
        parts = [a.get("line1", "")]
        if a.get("line2"): parts.append(a["line2"])
        parts.append(a.get("city", ""))
        if a.get("postal_code"): parts.append(a["postal_code"])
        return ", ".join([p for p in parts if p])

    lines: list[str] = ["{link}", ""]
    over = 0
    for i, o in enumerate(orders):
        us = o.get("user_summary") or {}
        addr = o.get("address") or {}
        name = ((addr.get("name") or "").strip()
                or us.get("name") or o.get("customer_name") or "Guest")
        phone = us.get("phone") or o.get("phone") or ""
        block: list[str] = []
        block.append(name)
        if phone:
            block.append(f"📞 {phone}")
        block.append(_addr(addr))
        block.append("Orders:")
        items = expand_order_items(o)
        if items:
            for nm, q in items:
                block.append(f"  • {nm} x {q}")
        else:
            block.append("  (no items)")
        candidate = "\n".join(block)
        # Length safety: if we'd blow past 1400 chars, stop and mention omitted count
        projected = sum(len(s) + 1 for s in lines) + len(candidate) + 40
        if projected > 1400 and i > 0:
            over = len(orders) - i
            break
        lines.append(candidate)
        if i < len(orders) - 1:
            lines.append("-" * 25)
    if over > 0:
        lines.append(f"\n… +{over} more in the XLS")
    return "\n".join(lines)


@api.post("/admin/orders/export")
async def admin_export_orders(payload: OrdersExportReq, request: Request,
                              admin=Depends(_current_admin)):
    if payload.destination not in ("download", "email", "sms", "drive"):
        raise HTTPException(400, "destination must be download|email|sms|drive")
    orders = await _resolve_orders(payload.order_ids)
    if not orders:
        raise HTTPException(400, "No orders match the selection")
    xlsx = build_orders_xlsx(orders)
    filename = default_filename("orders")
    sms_default = _build_orders_sms_body(orders) if payload.destination == "sms" else None
    return await _finalize_export(
        request, "orders", payload.destination,
        payload.sms_to, payload.sms_message, payload.email_to,
        xlsx, filename, len(orders),
        sms_default_body=sms_default,
    )


# ==========================================================
# ADMIN — Manual order creation (Admin creates an order on behalf of a customer)
# ==========================================================
class AdminCustomerIn(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    address: Optional[Address] = None


class AdminCreateOrderReq(BaseModel):
    # Customer selection: EITHER pass user_id (existing customer) OR new_customer (create inline)
    user_id: Optional[str] = None
    new_customer: Optional[AdminCustomerIn] = None
    # Order details (same shape as customer flow, but no coupon/redeem/stripe)
    items: List[OrderItemIn]
    address: Address
    slot: DeliverySlot
    phone: str
    special_instructions: Optional[str] = ""
    payment_method: str = "cod"  # "cod" | "interac" | "card" — admin-created always non-Stripe
    mark_as_paid: bool = False  # if True, order marked paid immediately
    driver_partner_id: Optional[str] = None  # optional driver assignment


@api.post("/admin/customers")
async def admin_create_customer(payload: AdminCustomerIn, admin=Depends(_current_admin)):
    """Create a new customer inline (from Admin New Order flow)."""
    if not payload.name.strip() or not payload.phone.strip():
        raise HTTPException(400, "Name and phone are required")

    # De-dupe: if a user already exists with this phone, return that instead.
    existing = None
    if payload.email:
        existing = await db.users.find_one({"email": str(payload.email).lower()}, {"_id": 0})
    if not existing:
        existing = await db.users.find_one({"phone": payload.phone.strip()}, {"_id": 0})
    if existing:
        return {"user_id": existing["user_id"], "existed": True, "user": existing}

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "user_id": user_id,
        "name": payload.name.strip(),
        "phone": payload.phone.strip(),
        "role": "customer",
        "loyalty_points": 0,
        "created_at": datetime.now(timezone.utc),
        "default_address": payload.address.model_dump() if payload.address else None,
    }
    if payload.email:
        doc["email"] = str(payload.email).lower()
    await db.users.insert_one(doc)
    doc.pop("_id", None)
    return {"user_id": user_id, "existed": False, "user": doc}


@api.get("/admin/order-builder")
async def admin_order_builder(admin=Depends(_current_admin)):
    """One-shot helper: returns everything the admin needs to build a new order.
    Cuts down on the client's parallel-fetch dance."""
    from datetime import date as _date
    settings = await _get_settings()
    today = _date.today()

    # Current + next 3 weekly menus (published or draft) so admin has options
    weeks = await db.weekly_menus.find({}, {"_id": 0}).sort("week_start", -1).limit(6).to_list(6)

    # Master menu items keyed by item_id for enrichment
    master = {m["item_id"]: m async for m in db.master_menu.find({"is_active": {"$ne": False}}, {"_id": 0})}

    # Normalize each week: build a unified `items[]` list from BOTH the legacy embedded
    # `items[]` shape AND the newer `lines[]` (v2) shape so the Admin New Order modal
    # can render à la carte + combo picks regardless of which schema the menu uses.
    today_iso = today.isoformat()
    current_week_start: Optional[str] = None
    for wk in weeks:
        merged: list[dict] = []
        # legacy embedded items
        for it in (wk.get("items") or []):
            m = master.get(it.get("item_id"))
            if m:
                it.setdefault("name", m.get("name", ""))
                it.setdefault("image_url", m.get("image_url", ""))
                it.setdefault("veg_type", m.get("veg_type"))
                it.setdefault("price_cents", it.get("price_cents") or m.get("default_price_cents"))
            merged.append(it)
        # v2 lines[] → each line references a master_menu doc
        for ln in (wk.get("lines") or []):
            mid = ln.get("master_item_id")
            m = master.get(mid)
            if not m:
                continue
            merged.append({
                "item_id": mid,
                "master_item_id": mid,
                "name": m.get("name", ""),
                "image_url": m.get("image_url", ""),
                "veg_type": m.get("veg_type"),
                "price_cents": ln.get("price_override_cents") or m.get("default_price_cents"),
                "default_price_cents": m.get("default_price_cents"),
                "availability": ln.get("availability", "available"),
                "is_featured": ln.get("is_featured", False),
                "display_order": ln.get("display_order", 0),
            })
        # De-dupe by item_id preserving first (legacy wins if both present).
        seen_ids: set = set()
        deduped: list[dict] = []
        for it in merged:
            iid = it.get("item_id")
            if iid and iid in seen_ids:
                continue
            if iid:
                seen_ids.add(iid)
            deduped.append(it)
        wk["items"] = deduped
        # Backfill package.eligible_master_ids from lines[] when not explicitly set
        if wk.get("package_enabled") and wk.get("package"):
            pkg = wk["package"]
            if not pkg.get("eligible_master_ids"):
                pkg["eligible_master_ids"] = [
                    ln.get("master_item_id") for ln in (wk.get("lines") or [])
                    if ln.get("master_item_id")
                ]
        # Determine which week is "current" (today falls within week_start..+6)
        ws = wk.get("week_start")
        if ws and ws <= today_iso:
            wk_end = (datetime.fromisoformat(ws).date() + timedelta(days=6)).isoformat()
            if today_iso <= wk_end and current_week_start is None:
                current_week_start = ws

    # Active catering packages
    catering = await db.catering_packages.find({"is_active": True}, {"_id": 0}).sort("sort_order", 1).to_list(20)

    # Active delivery partners for the driver dropdown
    partners = await db.delivery_partners.find({"is_active": True},
        {"_id": 0, "partner_id": 1, "name": 1, "phone": 1, "vehicle": 1}).sort("name", 1).to_list(50)

    # Compute delivery slots — next 4 weeks of configured delivery_days
    delivery_days = settings.get("delivery_days", [5, 6])
    slots: list[dict] = []
    for wk_offset in range(4):
        for dow in sorted(set(int(d) for d in delivery_days if 0 <= int(d) <= 6)):
            # dow is 0=Sun..6=Sat (JS convention)
            # Python weekday(): 0=Mon..6=Sun. Convert.
            py_dow = (dow - 1) % 7  # 0=Sun → 6, 1=Mon → 0 …
            days_ahead = (py_dow - today.weekday()) % 7 + wk_offset * 7
            if days_ahead == 0 and wk_offset == 0:
                # today: only allow if there's still time (skip past dates)
                pass
            d = today + timedelta(days=days_ahead)
            slots.append({
                "date": d.isoformat(),
                "window": f"{['sunday','monday','tuesday','wednesday','thursday','friday','saturday'][dow]}_delivery",
                "label": d.strftime("%a, %b %d, %Y"),
            })
    # De-dupe (same date might sneak in with different offsets) + sort
    seen: set = set()
    unique_slots = []
    for s in sorted(slots, key=lambda x: x["date"]):
        if s["date"] < today.isoformat():
            continue
        if s["date"] in seen:
            continue
        seen.add(s["date"])
        unique_slots.append(s)

    return {
        "weeks": weeks,
        "current_week_start": current_week_start,
        "master_menu": list(master.values()),
        "catering": catering,
        "delivery_partners": partners,
        "delivery_slots": unique_slots,
        "settings": {
            "delivery_fee_cents": settings.get("default_delivery_fee_cents", DELIVERY_FEE_CENTS),
            "tax_rate_bps": settings.get("tax_rate_bps", 1300),
            "tax_label": settings.get("tax_label", "HST"),
            "tax_enabled": settings.get("tax_enabled", True),
            "currency": settings.get("currency", "CAD"),
            "payment_methods": settings.get("payment_methods", {}),
        },
    }


@api.post("/admin/orders/create")
async def admin_create_manual_order(req: AdminCreateOrderReq, admin=Depends(_current_admin)):
    """Admin creates an order on behalf of a customer. Optionally assigns a driver.

    Flow:
      1. Resolve or create the customer
      2. Compute totals (uses same _resolve_items + settings as customer flow)
      3. Insert the order (status="confirmed" for paid, "new" for unpaid)
      4. If driver_partner_id → assign & bump status to "packed"
    """
    # 1) Resolve customer
    if req.user_id:
        user_doc = await db.users.find_one({"user_id": req.user_id}, {"_id": 0})
        if not user_doc:
            raise HTTPException(404, "Customer not found")
    elif req.new_customer:
        if not req.new_customer.name.strip() or not req.new_customer.phone.strip():
            raise HTTPException(400, "New customer needs name + phone")
        # De-dupe check
        existing = None
        if req.new_customer.email:
            existing = await db.users.find_one({"email": str(req.new_customer.email).lower()}, {"_id": 0})
        if not existing:
            existing = await db.users.find_one({"phone": req.new_customer.phone.strip()}, {"_id": 0})
        if existing:
            user_doc = existing
        else:
            uid = f"user_{uuid.uuid4().hex[:12]}"
            user_doc = {
                "user_id": uid,
                "name": req.new_customer.name.strip(),
                "phone": req.new_customer.phone.strip(),
                "role": "customer",
                "loyalty_points": 0,
                "created_at": datetime.now(timezone.utc),
                "default_address": (req.new_customer.address or req.address).model_dump(),
            }
            if req.new_customer.email:
                user_doc["email"] = str(req.new_customer.email).lower()
            await db.users.insert_one(user_doc)
    else:
        raise HTTPException(400, "Must supply either user_id or new_customer")

    # 2) Compute pricing (reuse existing helpers)
    snaps, subtotal = await _resolve_items(req.items)
    if not snaps:
        raise HTTPException(400, "Order must include at least one item")
    settings = await _get_settings()
    delivery_fee = settings.get("default_delivery_fee_cents", DELIVERY_FEE_CENTS)
    taxable = max(0, subtotal + delivery_fee)
    tax_cents = (taxable * settings.get("tax_rate_bps", 1300)) // 10000 \
        if _tax_enabled_for_method(settings, req.payment_method) else 0
    total = taxable + tax_cents

    # 3) Build order
    now = datetime.now(timezone.utc)
    payment_method = req.payment_method if req.payment_method in ("card", "cod", "interac", "paypal") else "cod"
    if req.mark_as_paid:
        payment_status = "paid"
        status = "confirmed"
    else:
        payment_status = {"cod": "cod_pending", "interac": "interac_pending",
                          "card": "pending", "paypal": "pending"}.get(payment_method, "pending")
        status = "confirmed"  # admin-entered = trust it, never "pending_payment"
    tracking = [
        {"status": "new", "ts": now.isoformat(), "note": "Order created by admin"},
        {"status": "confirmed", "ts": now.isoformat(),
         "note": f"Admin entered · {payment_method.upper()} · {'PAID' if req.mark_as_paid else 'unpaid'}"},
    ]

    order = Order(
        user_id=user_doc["user_id"],
        items_snapshot=snaps,
        address=req.address.model_dump(),
        slot=req.slot.model_dump(),
        phone=req.phone,
        subtotal_cents=subtotal,
        delivery_fee_cents=delivery_fee,
        tax_cents=tax_cents,
        tax_label=settings.get("tax_label", "HST"),
        discount_cents=0,
        points_redeemed_cents=0,
        total_cents=total,
        coupon_code=None,
        special_instructions=req.special_instructions or "",
        payment_method=payment_method,
        status=status,
        payment_status=payment_status,
        points_awarded=0,
        tracking_events=tracking,
    )
    order_doc = order.model_dump()
    # Extra marker: created_by_admin
    order_doc["created_by_admin"] = True
    await db.orders.insert_one(order_doc)
    order_doc.pop("_id", None)  # Motor mutates the dict with the ObjectId — strip it

    # Save default address on customer if they don't have one yet
    if not user_doc.get("default_address"):
        await db.users.update_one(
            {"user_id": user_doc["user_id"]},
            {"$set": {"default_address": req.address.model_dump()}},
        )

    # 4) Optional driver assignment → status "packed" + tracking event
    if req.driver_partner_id:
        partner = await db.delivery_partners.find_one(
            {"partner_id": req.driver_partner_id, "is_active": True}, {"_id": 0})
        if not partner:
            raise HTTPException(400, f"Driver {req.driver_partner_id} not found or inactive")
        await db.orders.update_one(
            {"order_id": order_doc["order_id"]},
            {"$set": {
                "delivery_partner_id": partner["partner_id"],
                "delivery_status": "assigned",
                "status": "packed",
                "updated_at": now,
            },
             "$push": {"tracking_events": {
                 "status": "packed", "ts": now.isoformat(),
                 "note": f"Auto-packed & assigned to driver {partner.get('name', partner['partner_id'])}"
             }}},
        )
        order_doc["delivery_partner_id"] = partner["partner_id"]
        order_doc["delivery_status"] = "assigned"
        order_doc["status"] = "packed"

    return {"ok": True, "order": order_doc,
            "customer": {"user_id": user_doc["user_id"],
                         "name": user_doc.get("name"),
                         "phone": user_doc.get("phone")}}


# ==========================================================
# ADMIN — Customers (list, detail, export)
# ==========================================================
async def _customer_summaries(user_ids: Optional[List[str]] = None) -> List[dict]:
    """
    Aggregate customers with their order stats.
    If user_ids is provided, restrict to those. Otherwise all customers (limit 500).
    """
    match: dict = {"role": {"$ne": "delivery_partner"}}
    if user_ids:
        match["user_id"] = {"$in": user_ids}
    users_cur = db.users.find(match, {"_id": 0}).sort("created_at", -1).limit(500)
    users_list = await users_cur.to_list(500)
    ids = [u["user_id"] for u in users_list]
    if not ids:
        return []

    # Aggregate per-user order stats in a single pipeline
    pipe = [
        {"$match": {"user_id": {"$in": ids},
                    "status": {"$ne": "pending_payment"}}},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$user_id",
            "total_orders": {"$sum": 1},
            "total_spent_cents": {"$sum": "$total_cents"},
            "last_order_date": {"$first": "$created_at"},
            "last_order_status": {"$first": "$status"},
        }},
    ]
    stats_map: dict = {}
    async for row in db.orders.aggregate(pipe):
        stats_map[row["_id"]] = row

    out: List[dict] = []
    for u in users_list:
        st = stats_map.get(u["user_id"]) or {}
        addresses = u.get("addresses") or []
        out.append({
            "user_id": u["user_id"],
            "name": u.get("name") or "",
            "email": u.get("email") or "",
            "phone": u.get("phone") or "",
            "role": u.get("role") or "customer",
            "created_at": u.get("created_at"),
            "loyalty_points": int(u.get("loyalty_points") or 0),
            "total_orders": st.get("total_orders", 0),
            "total_spent_cents": st.get("total_spent_cents", 0),
            "last_order_date": st.get("last_order_date"),
            "last_order_status": st.get("last_order_status", ""),
            "addresses": addresses,
            # Include default_address so the admin "New Order" flow can
            # pre-populate the delivery address when picking an existing
            # customer + render the address preview line in the picker.
            "default_address": u.get("default_address"),
        })
    return out


@api.get("/admin/customers")
async def admin_list_customers(admin=Depends(_current_admin),
                               q: Optional[str] = None):
    """List customers with aggregated order stats. Optional 'q' searches name/email/phone."""
    rows = await _customer_summaries()
    if q:
        needle = q.strip().lower()
        rows = [r for r in rows
                if needle in (r["name"] or "").lower()
                or needle in (r["email"] or "").lower()
                or needle in (r["phone"] or "").lower()]
    return rows


@api.get("/admin/customers/{user_id}")
async def admin_customer_detail(user_id: str, admin=Depends(_current_admin)):
    summary = await _customer_summaries([user_id])
    if not summary:
        raise HTTPException(404, "Customer not found")
    orders = await db.orders.find({"user_id": user_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(200)
    loyalty_history = await db.loyalty_ledger.find({"user_id": user_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(200)
    return {"customer": summary[0], "orders": orders, "loyalty_history": loyalty_history}


class CustomersExportReq(BaseModel):
    user_ids: List[str] = Field(default_factory=list)  # empty = ALL
    destination: str  # "download" | "email" | "sms" | "drive"
    include_order_history: bool = True
    sms_to: Optional[str] = None
    sms_message: Optional[str] = None
    email_to: Optional[EmailStr] = None


@api.post("/admin/customers/export")
async def admin_export_customers(payload: CustomersExportReq, request: Request,
                                  admin=Depends(_current_admin)):
    if payload.destination not in ("download", "email", "sms", "drive"):
        raise HTTPException(400, "destination must be download|email|sms|drive")
    customers = await _customer_summaries(payload.user_ids or None)
    if not customers:
        raise HTTPException(400, "No customers match the selection")

    orders_by_user: dict[str, list[dict]] = {}
    if payload.include_order_history:
        uids = [c["user_id"] for c in customers]
        async for o in db.orders.find({"user_id": {"$in": uids}}, {"_id": 0}).sort("created_at", -1):
            orders_by_user.setdefault(o["user_id"], []).append(o)

    xlsx = build_customers_xlsx(customers, orders_by_user)
    filename = default_filename("customers")
    return await _finalize_export(
        request, "customers", payload.destination,
        payload.sms_to, payload.sms_message, payload.email_to,
        xlsx, filename, len(customers),
    )


# Invoice HTML (print-friendly, no auth for now — order_id is opaque)
@app.get("/api/invoice/{order_id}")
async def invoice_html(order_id: str):
    from fastapi.responses import HTMLResponse
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Not found")
    settings = await _get_settings()
    user = await db.users.find_one({"user_id": order["user_id"]}, {"_id": 0})
    dollars = lambda c: f"CA${(c/100):.2f}"
    esc = lambda v: _html.escape(str(v if v is not None else ""))
    rows = "".join(
        f"<tr><td>{esc(it['name'])}"
        f"{' · '+esc(it.get('catering_guest_count'))+' guests' if it.get('catering_guest_count') else ''}"
        f"</td><td class='r'>{esc(it['quantity'])}</td>"
        f"<td class='r'>{dollars(it['unit_price_cents'])}</td>"
        f"<td class='r'>{dollars(it['line_total_cents'])}</td></tr>"
        for it in order.get("items_snapshot", [])
    )
    tax_row = (f"<tr><td colspan='3' class='r muted'>{esc(order.get('tax_label','HST'))}</td>"
               f"<td class='r'>{dollars(order.get('tax_cents',0))}</td></tr>") if order.get("tax_cents") else ""
    discount_row = (f"<tr><td colspan='3' class='r muted'>Discount ({esc(order.get('coupon_code',''))})</td>"
                    f"<td class='r'>−{dollars(order.get('discount_cents',0))}</td></tr>") if order.get("discount_cents") else ""
    points_row = (f"<tr><td colspan='3' class='r muted'>Loyalty points</td>"
                  f"<td class='r'>−{dollars(order.get('points_redeemed_cents',0))}</td></tr>") if order.get("points_redeemed_cents") else ""
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Invoice {order_id}</title>
<style>
:root{{--brand:#B14F36;--muted:#6B7280;}}
*{{box-sizing:border-box}}body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111;max-width:720px;margin:24px auto;padding:20px}}
.head{{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid #eee;padding-bottom:16px;margin-bottom:16px}}
.brand{{color:var(--brand);font-size:26px;font-weight:800;letter-spacing:-.5px}}.sub{{color:var(--muted);font-size:12px;margin-top:4px}}
.badge{{display:inline-block;background:#FBF3EF;color:var(--brand);padding:4px 10px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:2px}}
h2{{margin:0;font-size:20px}}h3{{margin:16px 0 4px;font-size:12px;letter-spacing:2px;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:14px}}th,td{{padding:8px 6px;border-bottom:1px solid #eee}}th{{text-align:left;background:#FAF9F6;font-size:11px;letter-spacing:2px;color:var(--muted)}}
.r{{text-align:right}}.muted{{color:var(--muted)}}.total{{font-size:20px;font-weight:800;color:var(--brand)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.card{{border:1px solid #eee;border-radius:12px;padding:12px}}
@media print{{body{{margin:0}}.no-print{{display:none}}}}
button{{background:var(--brand);color:#fff;border:0;padding:10px 16px;border-radius:999px;cursor:pointer;font-weight:800}}
</style></head><body>
<div class="head"><div><div class="brand">{BRAND_NAME}</div><div class="sub">{esc(settings.get('kitchen_address','Greater Toronto Area · GTA'))} · {esc(settings.get('phone',''))}</div></div>
<div style="text-align:right"><span class="badge">INVOICE</span><h2>#{order_id[-6:].upper()}</h2><div class="sub">{(order['created_at'].isoformat() if hasattr(order['created_at'], 'isoformat') else str(order['created_at']))[:10]}</div></div></div>
<div class="grid"><div class="card"><h3>BILL TO</h3><div><strong>{esc((user or {{}}).get('name','Guest'))}</strong></div><div class="muted">{esc((user or {{}}).get('email',''))}</div><div>{esc(order.get('phone',''))}</div></div>
<div class="card"><h3>DELIVER TO</h3><div>{esc(order['address'].get('line1',''))}{', '+esc(order['address']['line2']) if order['address'].get('line2') else ''}</div><div class="muted">{esc(order['address'].get('city',''))}, {esc(order['address'].get('postal_code',''))}</div><div>Slot: {esc(order['slot'].get('window','').replace('_',' '))} · {esc(order['slot'].get('date',''))}</div></div></div>
<h3>ITEMS</h3><table><thead><tr><th>Description</th><th class="r">Qty</th><th class="r">Unit</th><th class="r">Total</th></tr></thead>
<tbody>{rows}
<tr><td colspan="3" class="r muted">Subtotal</td><td class="r">{dollars(order['subtotal_cents'])}</td></tr>
<tr><td colspan="3" class="r muted">Delivery</td><td class="r">{dollars(order['delivery_fee_cents'])}</td></tr>
{discount_row}{points_row}{tax_row}
<tr><td colspan="3" class="r"><strong>Total</strong></td><td class="r total">{dollars(order['total_cents'])}</td></tr>
</tbody></table>
<h3>PAYMENT</h3><div>{'Cash on Delivery' if order.get('payment_method')=='cod' else 'Card (Stripe) · '+order.get('payment_status','').title()}</div>
<div class="no-print" style="margin-top:24px;text-align:right"><button onclick="window.print()">Print / Save PDF</button></div>
</body></html>"""
    return HTMLResponse(content=html)


@app.get("/api/track/{order_id}")
async def track_html(order_id: str):
    """Public, no-login order tracking page (for the SMS tracking link). Shows the
    live delivery status + ETA and auto-refreshes."""
    from fastapi.responses import HTMLResponse
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    settings = await _get_settings()
    dstatus = order.get("delivery_status") or order.get("status") or "confirmed"
    labels = {
        "confirmed": ("Order confirmed", "We're getting your order ready."),
        "preparing": ("Preparing your food", "Our kitchen is cooking your order."),
        "assigned": ("Driver assigned", "A driver has been assigned to your order."),
        "picked_up": ("Picked up", "Your order has left the kitchen."),
        "on_the_way": ("On the way 🚗", "Your driver is heading to you."),
        "arrived": ("Driver has arrived 🛵", "Your driver is at your location."),
        "delivered": ("Delivered ✅", "Enjoy your meal!"),
    }
    title, sub = labels.get(dstatus, ("Order received", "We're processing your order."))
    steps = ["confirmed", "preparing", "on_the_way", "delivered"]
    idx_map = {"confirmed": 0, "preparing": 1, "assigned": 1, "picked_up": 2, "on_the_way": 2, "arrived": 2, "delivered": 3}
    cur_idx = idx_map.get(dstatus, 0)
    eta_s = order.get("delivery_eta_seconds") or 0
    eta_html = ""
    if dstatus in ("on_the_way", "arrived") and eta_s:
        mins = max(1, round(eta_s / 60))
        eta_html = f"<div class='eta'>Estimated arrival: <strong>~{mins} min</strong></div>"
    dollars = lambda c: f"CA${(c/100):.2f}"
    esc = lambda v: _html.escape(str(v if v is not None else ""))
    item_rows = "".join(
        f"<li>{esc(it['name'])} × {esc(it.get('quantity',1))}{esc(_item_selection_suffix(it))}</li>"
        for it in order.get("items_snapshot", [])
    )
    step_html = "".join(
        f"<div class='step {'on' if i <= cur_idx else ''}'><div class='dot'></div>"
        f"<div class='lbl'>{s.replace('_',' ').title()}</div></div>"
        for i, s in enumerate(steps)
    )
    invoice_url = _invoice_link(order)
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Track order #{order_id[-6:].upper()}</title>
<style>
:root{{--brand:#B14F36;--muted:#6B7280}}
*{{box-sizing:border-box}}body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111;max-width:560px;margin:0 auto;padding:20px;background:#FAF9F6}}
.brand{{color:var(--brand);font-size:24px;font-weight:800}}.badge{{display:inline-block;background:#FBF3EF;color:var(--brand);padding:4px 10px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:2px}}
.card{{background:#fff;border:1px solid #eee;border-radius:16px;padding:20px;margin-top:16px}}
h1{{font-size:22px;margin:8px 0 4px}}.sub{{color:var(--muted)}}
.eta{{margin-top:12px;background:#FFF7F3;border:1px solid var(--brand);color:var(--brand);padding:10px 14px;border-radius:12px;font-size:15px}}
.steps{{display:flex;justify-content:space-between;margin:20px 0 4px}}
.step{{flex:1;text-align:center;position:relative}}
.step .dot{{width:16px;height:16px;border-radius:50%;background:#ddd;margin:0 auto 6px}}
.step.on .dot{{background:var(--brand)}}
.step .lbl{{font-size:11px;color:var(--muted)}}.step.on .lbl{{color:#111;font-weight:700}}
ul{{padding-left:18px;color:#333}}li{{margin:4px 0}}
a.btn{{display:inline-block;margin-top:8px;background:var(--brand);color:#fff;padding:10px 18px;border-radius:999px;text-decoration:none;font-weight:800}}
</style>
<meta http-equiv="refresh" content="30"></head><body>
<div class="brand">{BRAND_NAME}</div>
<div class="card">
<span class="badge">ORDER #{order_id[-6:].upper()}</span>
<h1>{title}</h1><div class="sub">{sub}</div>
{eta_html}
<div class="steps">{step_html}</div>
</div>
<div class="card"><h3>Your items</h3><ul>{item_rows}</ul>
<div class="sub">Deliver to: {esc(order['address'].get('line1',''))}, {esc(order['address'].get('city',''))}</div>
<div class="sub" style="margin-top:6px">Total: <strong>{dollars(order.get('total_cents',0))}</strong></div>
<a class="btn" href="{invoice_url}">View invoice / PDF</a></div>
<div class="sub" style="text-align:center;margin-top:14px;font-size:12px">This page refreshes automatically · {esc(settings.get('phone',''))}</div>
</body></html>"""
    return HTMLResponse(content=html)


# ==========================================================
# DELIVERY PARTNER APP (v3)
# ==========================================================
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


class DeliveryLoginReq(BaseModel):
    email: str
    password: str


class DeliveryPartnerCreateReq(BaseModel):
    name: str
    email: str
    phone: str = ""
    vehicle: str = "car"
    password: str


class DeliveryPartnerUpdateReq(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    vehicle: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class DeliveryLocationReq(BaseModel):
    lat: float
    lng: float


class DeliveryStatusReq(BaseModel):
    status: str  # "picked_up" | "on_the_way" | "arrived" | "delivered"
    note: Optional[str] = None


class DeliveryRouteReq(BaseModel):
    origin_lat: float
    origin_lng: float
    order_ids: List[str]
    optimize: bool = True  # False = respect order_ids order (used after user manually reorders stops)


async def _current_partner(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing partner bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(401, "Invalid partner token")
    if payload.get("role") != "delivery_partner":
        raise HTTPException(403, "Not a delivery partner token")
    partner_id = payload.get("sub")
    partner = await db.delivery_partners.find_one({"partner_id": partner_id}, {"_id": 0, "password_hash": 0})
    if not partner or not partner.get("is_active", True):
        raise HTTPException(403, "Partner not active")
    return partner


def _partner_public(p: dict) -> dict:
    out = {k: v for k, v in p.items() if k not in ("password_hash", "_id")}
    return out


# ---- Google Maps helpers ----
async def _google_directions_optimize(origin: str, destination: str, waypoints: List[str], optimize: bool = True) -> Optional[dict]:
    """Call Google Directions API.
    optimize=True → let Google reorder waypoints (waypoints:optimize:true).
    optimize=False → preserve given waypoint order (used after user manually reorders stops).
    origin/destination/waypoints must be "lat,lng" strings (or addresses).
    Returns { waypoint_order: [int], legs: [{duration_sec, distance_m, end_address}] } or None on failure.
    """
    if not GOOGLE_MAPS_API_KEY or GOOGLE_MAPS_API_KEY.startswith("AIzaSy_PLACEHOLDER"):
        return None
    params = {
        "origin": origin,
        "destination": destination,
        "key": GOOGLE_MAPS_API_KEY,
        "mode": "driving",
    }
    if waypoints:
        prefix = "optimize:true|" if optimize else ""
        params["waypoints"] = prefix + "|".join(waypoints)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get("https://maps.googleapis.com/maps/api/directions/json", params=params)
        data = r.json()
        if data.get("status") != "OK" or not data.get("routes"):
            logging.warning(f"Google Directions status={data.get('status')} err={data.get('error_message')}")
            return None
        route = data["routes"][0]
        legs = [
            {
                "duration_sec": (leg.get("duration") or {}).get("value", 0),
                "distance_m": (leg.get("distance") or {}).get("value", 0),
                "start_address": leg.get("start_address"),
                "end_address": leg.get("end_address"),
                "end_location": leg.get("end_location"),
            }
            for leg in route.get("legs", [])
        ]
        return {
            "waypoint_order": route.get("waypoint_order", []),
            "legs": legs,
            "overview_polyline": (route.get("overview_polyline") or {}).get("points"),
        }
    except Exception as e:
        logging.error(f"Google Directions call failed: {e}")
        return None


async def _google_geocode(address: str) -> Optional[dict]:
    if not GOOGLE_MAPS_API_KEY or GOOGLE_MAPS_API_KEY.startswith("AIzaSy_PLACEHOLDER"):
        return None
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": GOOGLE_MAPS_API_KEY},
            )
        data = r.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        loc = data["results"][0]["geometry"]["location"]
        return {"lat": loc["lat"], "lng": loc["lng"],
                "formatted": data["results"][0]["formatted_address"]}
    except Exception as e:
        logging.error(f"Geocode failed: {e}")
        return None


async def _google_reverse_geocode(lat: float, lng: float) -> Optional[dict]:
    if not GOOGLE_MAPS_API_KEY or GOOGLE_MAPS_API_KEY.startswith("AIzaSy_PLACEHOLDER"):
        return None
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"latlng": f"{lat},{lng}", "key": GOOGLE_MAPS_API_KEY},
            )
        data = r.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        return {"lat": lat, "lng": lng,
                "formatted": data["results"][0]["formatted_address"]}
    except Exception as e:
        logging.error(f"Reverse-geocode failed: {e}")
        return None


def _address_string(addr: dict) -> str:
    parts = [addr.get(k) for k in ("line1", "line2", "city", "province", "postal_code")]
    return ", ".join([p for p in parts if p])


async def _ensure_order_coords(order: dict) -> Optional[dict]:
    """Ensure the order.address has lat/lng — geocode & persist if missing."""
    addr = order.get("address") or {}
    if addr.get("lat") and addr.get("lng"):
        return addr
    geo = await _google_geocode(_address_string(addr))
    if not geo:
        return None
    addr["lat"] = geo["lat"]
    addr["lng"] = geo["lng"]
    addr["geocoded_at"] = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one({"order_id": order["order_id"]}, {"$set": {"address": addr}})
    return addr


# ---- Admin: Delivery Partner CRUD ----
@api.post("/admin/delivery-partners")
async def admin_create_partner(req: DeliveryPartnerCreateReq, admin=Depends(_current_admin)):
    if await db.delivery_partners.find_one({"email": req.email.lower()}, {"_id": 0}):
        raise HTTPException(409, "A partner with this email already exists")
    partner = DeliveryPartner(
        name=req.name, email=req.email.lower(), phone=req.phone,
        vehicle=req.vehicle, password_hash=_pwd.hash(req.password),
    ).model_dump()
    await db.delivery_partners.insert_one(partner)
    return {"ok": True, "partner": _partner_public(partner)}


@api.get("/admin/delivery-partners")
async def admin_list_partners(admin=Depends(_current_admin)):
    cur = db.delivery_partners.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
    partners = await cur.to_list(200)
    # Attach live counts
    for p in partners:
        p["active_orders"] = await db.orders.count_documents({
            "delivery_partner_id": p["partner_id"],
            "delivery_status": {"$in": ["assigned", "picked_up", "on_the_way", "arrived"]},
        })
    return partners


@api.patch("/admin/delivery-partners/{partner_id}")
async def admin_update_partner(partner_id: str, req: DeliveryPartnerUpdateReq, admin=Depends(_current_admin)):
    patch: Dict[str, Any] = {}
    for f in ("name", "phone", "vehicle", "is_active"):
        v = getattr(req, f)
        if v is not None:
            patch[f] = v
    if req.password:
        patch["password_hash"] = _pwd.hash(req.password)
    if patch:
        patch["updated_at"] = datetime.now(timezone.utc)
        r = await db.delivery_partners.update_one({"partner_id": partner_id}, {"$set": patch})
        if r.matched_count == 0:
            raise HTTPException(404, "Partner not found")
    partner = await db.delivery_partners.find_one({"partner_id": partner_id}, {"_id": 0, "password_hash": 0})
    return {"ok": True, "partner": partner}


@api.delete("/admin/delivery-partners/{partner_id}")
async def admin_delete_partner(partner_id: str, admin=Depends(_current_admin)):
    # Soft delete: deactivate + unassign live orders
    await db.delivery_partners.update_one(
        {"partner_id": partner_id}, {"$set": {"is_active": False}}
    )
    await db.orders.update_many(
        {"delivery_partner_id": partner_id,
         "delivery_status": {"$in": [None, "assigned", "picked_up", "on_the_way", "arrived"]}},
        {"$set": {"delivery_partner_id": None, "delivery_status": None,
                  "delivery_partner_name": None, "delivery_partner_phone": None}},
    )
    return {"ok": True}


# ---- Admin: Assign order to a partner ----
class OrderAssignReq(BaseModel):
    partner_id: Optional[str] = None  # None -> unassign


@api.post("/admin/orders/{order_id}/assign")
async def admin_assign_order(order_id: str, req: OrderAssignReq, admin=Depends(_current_admin)):
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    if req.partner_id is None:
        await db.orders.update_one(
            {"order_id": order_id},
            {"$set": {"delivery_partner_id": None, "delivery_status": None,
                      "delivery_partner_name": None, "delivery_partner_phone": None,
                      "updated_at": datetime.now(timezone.utc)}},
        )
        return {"ok": True, "unassigned": True}
    partner = await db.delivery_partners.find_one({"partner_id": req.partner_id, "is_active": True}, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Delivery partner not found or inactive")
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {
            "delivery_partner_id": partner["partner_id"],
            "delivery_partner_name": partner["name"],
            "delivery_partner_phone": partner.get("phone", ""),
            "delivery_status": "assigned",
            "status": "preparing" if order.get("status") in ("new", "confirmed") else order.get("status"),
            "updated_at": datetime.now(timezone.utc),
        }, "$push": {"tracking_events": {
            "event": "assigned_to_partner",
            "partner_id": partner["partner_id"],
            "partner_name": partner["name"],
            "ts": datetime.now(timezone.utc).isoformat(),
        }}},
    )
    # TODO push notify partner (MOCKED — real delivery needs prod build).
    logging.info(f"[push MOCK] order {order_id} assigned to partner {partner['partner_id']}")
    return {"ok": True, "assigned_to": partner["partner_id"]}


# ---- Delivery Partner: Auth ----
@api.post("/delivery/login")
async def delivery_login(req: DeliveryLoginReq):
    # Platform gate — driver app is blocked when the tenant is suspended.
    from platform_client import should_block_driver, snapshot
    if should_block_driver():
        snap = snapshot()
        raise HTTPException(
            402,
            snap.get("banner_text") or (
                f"Delivery is paused because the {BRAND_NAME} owner has not completed "
                "their platform subscription payment. Please contact the restaurant."
            )
        )
    partner = await db.delivery_partners.find_one({"email": req.email.lower()}, {"_id": 0})
    if not partner or not partner.get("is_active", True) or not _pwd.verify(req.password, partner.get("password_hash", "")):
        raise HTTPException(401, "Invalid credentials")
    token = jwt.encode(
        {"sub": partner["partner_id"], "role": "delivery_partner",
         "exp": datetime.now(timezone.utc) + timedelta(days=14)},
        JWT_SECRET, algorithm=JWT_ALG,
    )
    return {"access_token": token, "token_type": "bearer",
            "partner": _partner_public(partner)}


@api.get("/delivery/me")
async def delivery_me(partner=Depends(_current_partner)):
    return partner


class GeocodeReq(BaseModel):
    address: str


class ReverseGeocodeReq(BaseModel):
    lat: float
    lng: float


@api.post("/delivery/geocode")
async def delivery_geocode(req: GeocodeReq, partner=Depends(_current_partner)):
    """Turn a free-form address into {lat, lng, formatted}. Partner-scoped to avoid key abuse."""
    if not req.address or not req.address.strip():
        raise HTTPException(400, "Address is required")
    result = await _google_geocode(req.address.strip())
    if not result:
        raise HTTPException(404, "Could not geocode that address")
    return result


@api.post("/delivery/reverse-geocode")
async def delivery_reverse_geocode(req: ReverseGeocodeReq, partner=Depends(_current_partner)):
    """Turn {lat,lng} into a human-readable address for display."""
    result = await _google_reverse_geocode(req.lat, req.lng)
    if not result:
        raise HTTPException(404, "Could not resolve that location")
    return result


@api.get("/delivery/orders")
async def delivery_list_orders(partner=Depends(_current_partner),
                               status: Optional[str] = None):
    q: Dict[str, Any] = {"delivery_partner_id": partner["partner_id"]}
    if status == "active":
        q["delivery_status"] = {"$in": ["assigned", "picked_up", "on_the_way", "arrived"]}
    elif status == "completed":
        q["delivery_status"] = "delivered"
    elif status:
        q["delivery_status"] = status
    cur = db.orders.find(q, {"_id": 0, "stripe_session_id": 0}).sort("created_at", 1)
    orders = await cur.to_list(200)
    # Enrich each order with customer_name resolved from the linked user
    user_ids = list({o.get("user_id") for o in orders if o.get("user_id")})
    users = {}
    if user_ids:
        async for u in db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1}):
            users[u["user_id"]] = u
    for o in orders:
        u = users.get(o.get("user_id")) or {}
        # priority: address.name (checkout override) > user.name > "Guest"
        addr_name = ((o.get("address") or {}).get("name") or "").strip()
        user_name = (u.get("name") or "").strip()
        o["customer_name"] = addr_name or user_name or "Guest"
    return orders


@api.post("/delivery/location")
async def delivery_update_location(req: DeliveryLocationReq, partner=Depends(_current_partner)):
    """Live GPS heartbeat from the delivery-partner app.

    Alongside stashing the coords, we:
      1. Broadcast the fresh lat/lng onto every ACTIVE order for this partner
         (assigned / picked_up / on_the_way / arrived), so admins + fallback
         readers stay in sync.
      2. Recompute each order's `delivery_eta_seconds` using a straight-line
         (haversine) distance ÷ 30 km/h — this keeps the customer's
         "Arriving in ~X min" *decreasing* on every ping without spending
         a Directions call per heartbeat.
      3. Optionally refresh the per-order `route_polyline` (driver → home)
         via Google Directions, but ONLY when the driver has moved ≥300m
         since the last refresh OR the polyline is >60s stale. Throttled so
         a moving driver at 40 km/h costs at most ~1 Directions call/min/order.
    """
    ts = datetime.now(timezone.utc)
    await db.delivery_partners.update_one(
        {"partner_id": partner["partner_id"]},
        {"$set": {"current_lat": req.lat, "current_lng": req.lng, "current_location_updated_at": ts}},
    )

    # Pull all active orders for this partner — we'll fan out per-order updates below.
    active_orders = await db.orders.find(
        {"delivery_partner_id": partner["partner_id"],
         "delivery_status": {"$in": ["assigned", "picked_up", "on_the_way", "arrived"]}},
        {"_id": 0, "order_id": 1, "address": 1, "route_polyline": 1,
         "route_polyline_updated_at": 1, "route_polyline_origin": 1},
    ).to_list(50)

    for o in active_orders:
        addr = o.get("address") or {}
        dlat, dlng = addr.get("lat"), addr.get("lng")
        patch: Dict[str, Any] = {
            "delivery_partner_lat": req.lat,
            "delivery_partner_lng": req.lng,
            "delivery_partner_updated_at": ts,
        }
        if dlat is not None and dlng is not None:
            dist_m = _haversine_m(req.lat, req.lng, dlat, dlng)
            # 30 km/h avg city speed + 20s idle buffer. This is a straight-line
            # heuristic — Directions is the source of truth when it refreshes.
            eta_s = max(0, int((dist_m / 1000.0) / 30.0 * 3600) + 20)
            patch["delivery_eta_seconds"] = eta_s
            patch["delivery_distance_m"] = int(dist_m)
            patch["delivery_eta_updated_at"] = ts

            # Refresh the per-order polyline if we've moved far enough or it's stale.
            last_ts = o.get("route_polyline_updated_at")
            last_origin = o.get("route_polyline_origin") or {}
            moved_m = _haversine_m(
                req.lat, req.lng,
                last_origin.get("lat", req.lat), last_origin.get("lng", req.lng),
            ) if last_origin else 999_999
            # MongoDB round-trips datetimes as offset-naive; normalise to UTC
            # so the (ts - last_ts) subtraction against our offset-aware `ts`
            # doesn't raise TypeError.
            if last_ts and last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            stale = not last_ts or (ts - last_ts).total_seconds() > 60
            if (moved_m >= 300 or stale) and not o.get("route_polyline_refreshing"):
                # Fire-and-forget so we don't stall the heartbeat.
                asyncio.create_task(_refresh_order_polyline(
                    order_id=o["order_id"], from_lat=req.lat, from_lng=req.lng,
                    to_lat=dlat, to_lng=dlng,
                ))
        await db.orders.update_one({"order_id": o["order_id"]}, {"$set": patch})

    return {"ok": True}


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres. Good enough for ETA + arrival alerts."""
    import math
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


async def _refresh_order_polyline(order_id: str, from_lat: float, from_lng: float,
                                   to_lat: float, to_lng: float) -> None:
    """Fetch a fresh driver→home polyline from Google Directions and store it
    on the order. Best-effort — silently no-ops if the Maps key isn't set."""
    try:
        # Flag so concurrent heartbeats don't stack refresh calls.
        await db.orders.update_one({"order_id": order_id},
                                    {"$set": {"route_polyline_refreshing": True}})
        route = await _google_directions_optimize(
            origin=f"{from_lat},{from_lng}",
            destination=f"{to_lat},{to_lng}",
            waypoints=[],
            optimize=False,
        )
        patch: Dict[str, Any] = {"route_polyline_refreshing": False}
        if route and route.get("overview_polyline"):
            patch["route_polyline"] = route["overview_polyline"]
            patch["route_polyline_updated_at"] = datetime.now(timezone.utc)
            patch["route_polyline_origin"] = {"lat": from_lat, "lng": from_lng}
            # Also use Directions' real duration if we got one (more accurate than haversine).
            legs = route.get("legs") or []
            if legs and legs[0].get("duration_sec"):
                patch["delivery_eta_seconds"] = int(legs[0]["duration_sec"]) + 20
        await db.orders.update_one({"order_id": order_id}, {"$set": patch})
    except Exception as e:
        logging.warning(f"polyline refresh failed for {order_id}: {e}")
        await db.orders.update_one({"order_id": order_id},
                                    {"$set": {"route_polyline_refreshing": False}})


def _public_url(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http"):
        return path
    base = (os.environ.get("PUBLIC_BASE_URL", "") or os.environ.get("EXPO_PUBLIC_BACKEND_URL", "")).rstrip("/")
    return f"{base}{path}" if base else path


def _public_base_from_request(request: Request, client_base_url: Optional[str] = None) -> str:
    """Resolve the public origin for building clickable links. Priority:
    explicit env → forwarded/host header from the ingress → client-provided origin.
    Never returns a localhost origin (unusable in SMS/email)."""
    env = (os.environ.get("PUBLIC_BASE_URL", "") or os.environ.get("EXPO_PUBLIC_BACKEND_URL", "")).rstrip("/")
    if env:
        return env
    try:
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
        host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
        if host and "localhost" not in host and "127.0.0.1" not in host:
            return f"{proto}://{host}"
    except Exception:
        pass
    if client_base_url:
        return client_base_url.rstrip("/")
    return ""


def _order_base(order: dict) -> str:
    """Absolute base origin stored on the order (falls back to env)."""
    base = (order or {}).get("public_base_url") or ""
    if base:
        return base.rstrip("/")
    return (os.environ.get("PUBLIC_BASE_URL", "") or os.environ.get("EXPO_PUBLIC_BACKEND_URL", "")).rstrip("/")


def _invoice_link(order: dict) -> str:
    base = _order_base(order)
    return f"{base}/api/invoice/{order.get('order_id','')}" if base else f"/api/invoice/{order.get('order_id','')}"


def _track_link(order: dict) -> str:
    base = _order_base(order)
    return f"{base}/api/track/{order.get('order_id','')}" if base else f"/api/track/{order.get('order_id','')}"


NOTIFY_PHONE_DEFAULT = "+14374999453"  # restaurant owner's number


async def _notify_owner_delivered(order: dict):
    """Best-effort Email + SMS to the restaurant owner when an order is delivered.
    Never raises — notification failures must not block the delivery flow."""
    settings = await _get_settings()
    oid = order.get("order_id", "")
    cust = (order.get("address") or {}).get("name") or "Customer"
    total = order.get("total_cents", 0) / 100
    partner = order.get("delivery_partner_name") or "driver"
    proof = order.get("delivery_proof_photo_url") or ""
    proof_line = f" Proof photo: {_public_url(proof)}" if proof else ""

    # ---- Email (Emergent Resend) ----
    to_email = settings.get("notify_email") or ADMIN_EMAIL
    try:
        if to_email and _email.is_configured():
            html = (
                f"<h2>Order {oid} delivered ✅</h2>"
                f"<p><b>{BRAND_NAME}</b></p>"
                f"<p>Customer: {cust}<br/>Total: ${total:.2f}<br/>Delivered by: {partner}</p>"
                + (f'<p><a href="{_public_url(proof)}">View delivery proof photo</a></p>' if proof else "")
            )
            await _email.send_email(to=to_email, subject=f"{BRAND_NAME} — Order {oid} delivered", html=html)
    except Exception as e:
        logging.warning(f"[notify.email] {e}")

    # ---- SMS (Twilio, using owner-captured settings) ----
    tw = (settings.get("integrations") or {}).get("twilio") or {}
    to_phone = settings.get("notify_phone") or NOTIFY_PHONE_DEFAULT
    try:
        if tw.get("account_sid") and tw.get("auth_token_encrypted") and tw.get("from_number") and to_phone:
            body = f"{BRAND_NAME}: Order {oid} delivered to {cust}. Total ${total:.2f} by {partner}.{proof_line}"
            await _twilio.send_sms(tw["account_sid"], tw["auth_token_encrypted"], tw["from_number"], to_phone, body)
    except Exception as e:
        logging.warning(f"[notify.sms] {e}")


def _item_selection_suffix(it: dict) -> str:
    """Human bracket listing the actual dishes chosen for a weekly plan / catering
    line, e.g. ' (Chicken Biryani × 2, Paneer Butter Masala)'."""
    if it.get("kind") == "weekly_package":
        names = it.get("package_selection_names") or []
        if names:
            return f" ({', '.join(names)})"
    if it.get("kind") == "catering":
        picks = []
        for grp in it.get("selection_summary") or []:
            picks.extend(grp.get("items") or [])
        if picks:
            return f" ({', '.join(picks)})"
    return ""


def _order_items_text(order: dict) -> str:
    """One line per item: 'Weekly Combo x1 (Chicken Biryani × 2, Paneer) — CA$69.99'."""
    lines = []
    for it in order.get("items_snapshot", []):
        qty = it.get("quantity", 1)
        lines.append(f"• {it['name']} x{qty}{_item_selection_suffix(it)} — CA${it.get('line_total_cents', 0)/100:.2f}")
    return "\n".join(lines)


def _payment_note(order: dict, settings: dict) -> str:
    pm = order.get("payment_method")
    total = order.get("total_cents", 0) / 100
    if pm == "cod":
        return f"Cash on Delivery — please keep CA${total:.2f} ready for the driver."
    if pm == "interac":
        interac_email = (settings.get("payment_methods") or {}).get("interac", {}).get("email", "")
        return f"Interac e-Transfer — please send CA${total:.2f} to {interac_email} (add order {order.get('order_id','')} in the note)."
    return f"Total CA${total:.2f}."


async def _send_sms_via_settings(settings: dict, to: str, body: str):
    tw = (settings.get("integrations") or {}).get("twilio") or {}
    if to and tw.get("account_sid") and tw.get("auth_token_encrypted") and tw.get("from_number"):
        await _twilio.send_sms(tw["account_sid"], tw["auth_token_encrypted"], tw["from_number"], to, body)


async def _notify_order_created(order: dict, settings: dict, user_doc: dict):
    """Best-effort order-confirmation to the customer (Email + SMS) and the owner
    (Email + SMS). Never raises — a messaging failure must not fail the order."""
    oid = order.get("order_id", "")
    cust = (order.get("address") or {}).get("name") or (user_doc or {}).get("name") or "Customer"
    cust_email = (order.get("address") or {}).get("email") or (user_doc or {}).get("email") or ""
    cust_phone = order.get("phone") or ""
    total = order.get("total_cents", 0) / 100
    items_txt = _order_items_text(order)
    pay_note = _payment_note(order, settings)
    invoice_url = _invoice_link(order)
    ref = oid[-6:].upper()

    # ---- Customer email (Resend) ----
    try:
        if cust_email and _email.is_configured():
            rows = "".join(
                f"<tr><td style='padding:4px 0'>{it['name']} × {it.get('quantity',1)}{_item_selection_suffix(it)}</td>"
                f"<td style='padding:4px 0;text-align:right'>CA${it.get('line_total_cents',0)/100:.2f}</td></tr>"
                for it in order.get("items_snapshot", [])
            )
            html = (
                f"<h2>Thanks for your order, {cust}! 🎉</h2>"
                f"<p><b>{BRAND_NAME}</b> — Order #{ref}</p>"
                f"<table style='width:100%;max-width:420px;border-collapse:collapse'>{rows}"
                f"<tr><td style='padding:6px 0;border-top:1px solid #eee'><b>Total</b></td>"
                f"<td style='padding:6px 0;border-top:1px solid #eee;text-align:right'><b>CA${total:.2f}</b></td></tr></table>"
                f"<p>{pay_note}</p>"
                f"<p><a href='{invoice_url}' style='background:#B14F36;color:#fff;padding:10px 18px;border-radius:24px;text-decoration:none;font-weight:800'>View / download invoice (PDF)</a></p>"
                f"<p style='color:#666;font-size:12px'>Delivery: {order.get('slot',{}).get('window','').replace('_',' ')} · {order.get('slot',{}).get('date','')}</p>"
            )
            await _email.send_email(to=cust_email, subject=f"{BRAND_NAME} — Order #{ref} confirmed", html=html)
    except Exception as e:
        logging.warning(f"[order.notify.cust_email] {e}")

    # ---- Customer SMS (Twilio) ----
    try:
        first = (cust or "there").split()[0]
        body = (
            f"Hi {first}! Thank you for ordering with {BRAND_NAME}. "
            f"We're delighted to cook for you and can't wait to serve you.\n\n"
            f"Order #{ref}\n"
            f"{items_txt}\n"
            f"Total: CA${total:.2f}\n"
            f"{pay_note}\n\n"
            f"Invoice: {invoice_url}\n\n"
            f"We'll keep you posted. Bon appetit!"
        )
        await _send_sms_via_settings(settings, cust_phone, body)
    except Exception as e:
        logging.warning(f"[order.notify.cust_sms] {e}")

    # ---- Owner email + SMS ----
    owner_email = settings.get("notify_email") or ADMIN_EMAIL
    owner_phone = settings.get("notify_phone") or ""
    try:
        if owner_email and _email.is_configured():
            html = (
                f"<h2>New order #{ref} 🛎️</h2>"
                f"<p><b>{BRAND_NAME}</b></p>"
                f"<p><b>Customer:</b> {cust}<br/>"
                f"<b>Phone:</b> {cust_phone or '—'}<br/>"
                f"<b>Email:</b> {cust_email or '—'}</p>"
                f"<p><b>Order total: CA${total:.2f}</b> · Payment: {order.get('payment_method','').upper()}</p>"
                f"<p><b>Order details:</b></p>"
                f"<pre style='font-family:inherit;background:#f7f7f7;padding:10px;border-radius:8px'>{items_txt}</pre>"
                f"<p><b>Deliver to:</b> {(order.get('address') or {}).get('line1','')}, {(order.get('address') or {}).get('city','')}<br/>"
                f"<b>When:</b> {order.get('slot',{}).get('window','').replace('_',' ')} · {order.get('slot',{}).get('date','')}</p>"
                f"<p><a href='{invoice_url}'>View invoice (PDF)</a></p>"
            )
            await _email.send_email(to=owner_email, subject=f"{BRAND_NAME} — New order #{ref} from {cust} (CA${total:.2f})", html=html)
    except Exception as e:
        logging.warning(f"[order.notify.owner_email] {e}")
    try:
        if owner_phone:
            await _send_sms_via_settings(settings, owner_phone, f"{BRAND_NAME}: New order #{ref} from {cust}. Total CA${total:.2f} ({order.get('payment_method','').upper()}).")
    except Exception as e:
        logging.warning(f"[order.notify.owner_sms] {e}")


async def _notify_customer_eta(order: dict, settings: dict, exact: bool):
    """Notify the customer of a delivery ETA. Registered users get an in-app push;
    guests get an SMS with a tracking link. Best-effort (never raises)."""
    oid = order.get("order_id", "")
    eta_s = order.get("delivery_eta_seconds") or 0
    mins = max(1, round(eta_s / 60)) if eta_s else None
    when = (f"in {mins} min" if mins else "shortly")
    title = "Your order is on the way 🚗" if not exact else "Arriving soon 🛵"
    msg = (f"Your {BRAND_NAME} order is out for delivery — arriving {('~' if not exact else '')}{when}."
           if not exact else f"Your {BRAND_NAME} order is arriving {when}. Please be ready!")
    track_url = _track_link(order)
    user_doc = await db.users.find_one({"user_id": order.get("user_id")}, {"_id": 0}) or {}
    is_guest = (user_doc.get("role") == "guest")
    # In-app push (works on real builds; no-op otherwise)
    try:
        await send_push(recipients=[order.get("user_id")],
                        data={"title": title, "message": msg, "action_url": f"/order/{oid}"})
    except Exception as e:
        logging.warning(f"[eta.push] {e}")
    # Guests: SMS with tracking link
    if is_guest:
        try:
            await _send_sms_via_settings(settings, order.get("phone") or "",
                                         f"{BRAND_NAME}: {msg} Track: {track_url}")
        except Exception as e:
            logging.warning(f"[eta.sms] {e}")


@api.post("/delivery/orders/{order_id}/proof")
async def delivery_upload_proof(order_id: str, photo: UploadFile = File(...), partner=Depends(_current_partner)):
    """Delivery partner uploads a proof-of-delivery photo."""
    order = await db.orders.find_one({"order_id": order_id, "delivery_partner_id": partner["partner_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found for this partner")
    ext = (photo.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "heic"):
        ext = "jpg"
    fname = f"{uuid.uuid4().hex}.{ext}"
    dest = UPLOADS_DIR / "delivery" / fname
    data = await photo.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(400, "Photo too large (max 12 MB)")
    dest.write_bytes(data)
    url = f"/api/uploads/delivery/{fname}"
    await db.orders.update_one({"order_id": order_id}, {"$set": {"delivery_proof_photo_url": url, "updated_at": datetime.now(timezone.utc)}})
    return {"ok": True, "delivery_proof_photo_url": url}


@api.post("/delivery/orders/{order_id}/status")
async def delivery_update_order_status(order_id: str, req: DeliveryStatusReq, partner=Depends(_current_partner)):
    allowed = {"picked_up", "on_the_way", "arrived", "delivered"}
    if req.status not in allowed:
        raise HTTPException(400, f"Invalid delivery status. Allowed: {sorted(allowed)}")
    order = await db.orders.find_one({"order_id": order_id, "delivery_partner_id": partner["partner_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found for this partner")
    patch: Dict[str, Any] = {
        "delivery_status": req.status,
        "updated_at": datetime.now(timezone.utc),
    }
    if req.status == "picked_up":
        patch["status"] = "out_for_delivery"
    elif req.status == "on_the_way":
        patch["status"] = "out_for_delivery"
    elif req.status == "delivered":
        patch["status"] = "delivered"
        patch["delivery_eta_seconds"] = 0
        # Also stop refreshing the polyline once we're done — prevents a stale
        # driver→home path from lingering on the customer's post-delivery view.
        patch["route_polyline"] = None
        patch["route_polyline_refreshing"] = False
    await db.orders.update_one({"order_id": order_id}, {"$set": patch, "$push": {"tracking_events": {
        "event": req.status, "note": req.note or "", "ts": datetime.now(timezone.utc).isoformat(),
    }}})
    # Push customer notification MOCK
    logging.info(f"[push MOCK] order {order_id} status → {req.status}")
    if req.status == "delivered":
        fresh = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
        if fresh:
            await _notify_owner_delivered(fresh)
        # The next stop is now "1 stop away" — send it an exact ETA (once).
        try:
            settings = await _get_settings()
            nxt = await db.orders.find({
                "delivery_partner_id": partner["partner_id"],
                "delivery_status": {"$in": ["assigned", "picked_up", "on_the_way", "arrived"]},
                "exact_eta_sent": {"$ne": True},
            }, {"_id": 0}).sort("delivery_eta_seconds", 1).to_list(1)
            if nxt:
                await _notify_customer_eta(nxt[0], settings, exact=True)
                await db.orders.update_one({"order_id": nxt[0]["order_id"]}, {"$set": {"exact_eta_sent": True}})
        except Exception as e:
            logging.warning(f"[next.eta] {e}")
    return {"ok": True, "status": req.status}


class JourneyStopSnapshot(BaseModel):
    order_id: str
    route_index: int
    eta_seconds: int
    duration_sec: int
    distance_m: int
    address: str
    lat: float
    lng: float


class DeliveryJourneyStartReq(BaseModel):
    order_ids: List[str]
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None
    origin_address: Optional[str] = None
    # Full snapshot of the route so we can restore the same view on re-login.
    stops: Optional[List[JourneyStopSnapshot]] = None
    polyline: Optional[str] = None
    total_duration_sec: Optional[int] = None
    optimized: Optional[bool] = None


@api.post("/delivery/journey/start")
async def delivery_start_journey(req: DeliveryJourneyStartReq, partner=Depends(_current_partner)):
    """Delivery partner presses START DELIVERY.
    - Marks all provided orders (must belong to partner and currently 'assigned' or 'picked_up') as 'on_the_way'.
    - Stamps a journey_started_at and delivery_partner location so the customer tracking screen shows a live ETA.
    - Persists the full route snapshot on the partner doc so re-login restores the same plan.
    - Returns the count of orders flipped.
    """
    now = datetime.now(timezone.utc)
    # Update partner journey state + last known location + persisted route snapshot
    partner_patch: Dict[str, Any] = {
        "journey_started_at": now,
        "journey_active": True,
        "journey_order_ids": req.order_ids,
    }
    if req.origin_lat is not None and req.origin_lng is not None:
        partner_patch["current_lat"] = req.origin_lat
        partner_patch["current_lng"] = req.origin_lng
        partner_patch["current_location_updated_at"] = now
        partner_patch["journey_origin_lat"] = req.origin_lat
        partner_patch["journey_origin_lng"] = req.origin_lng
    if req.origin_address:
        partner_patch["journey_origin_address"] = req.origin_address
    if req.stops is not None:
        partner_patch["journey_stops"] = [s.dict() for s in req.stops]
    if req.polyline is not None:
        partner_patch["journey_polyline"] = req.polyline
    if req.total_duration_sec is not None:
        partner_patch["journey_total_duration_sec"] = req.total_duration_sec
    if req.optimized is not None:
        partner_patch["journey_optimized"] = req.optimized
    await db.delivery_partners.update_one(
        {"partner_id": partner["partner_id"]}, {"$set": partner_patch}
    )
    # Flip orders → on_the_way (customer sees ETA) AND back-fill the customer's
    # status timeline: preparing → packed → out_for_delivery.
    # We do this per-order (not update_many) so we can append MISSING events without
    # duplicating any that already exist (e.g. if admin already marked "preparing").
    orders_to_flip = await db.orders.find({
        "order_id": {"$in": req.order_ids},
        "delivery_partner_id": partner["partner_id"],
        "delivery_status": {"$in": ["assigned", "picked_up"]},
    }, {"_id": 0}).to_list(200)

    flipped = 0
    now_iso = now.isoformat()
    for o in orders_to_flip:
        existing = [e.get("status") for e in (o.get("tracking_events") or []) if e.get("status")]
        # Any of these steps that haven't been logged yet should be logged now,
        # sequentially, so the customer app ticks them all green.
        auto_steps = [
            ("preparing",         "Kitchen prepared your order"),
            ("packed",            "Order packed and ready"),
            ("out_for_delivery",  "Driver started the delivery journey"),
        ]
        to_add = [
            {"status": s, "ts": now_iso, "note": note}
            for s, note in auto_steps if s not in existing
        ]
        patch: Dict[str, Any] = {
            "delivery_status": "on_the_way",
            "status": "out_for_delivery",
            "journey_started_at": now,
            "updated_at": now,
        }
        if req.origin_lat is not None and req.origin_lng is not None:
            patch["delivery_partner_lat"] = req.origin_lat
            patch["delivery_partner_lng"] = req.origin_lng
            patch["delivery_partner_updated_at"] = now
        push: Dict[str, Any] = {}
        if to_add:
            push["tracking_events"] = {"$each": to_add}
        update: Dict[str, Any] = {"$set": patch}
        if push:
            update["$push"] = push
        r = await db.orders.update_one({"order_id": o["order_id"]}, update)
        if r.modified_count:
            flipped += 1

    logging.info(f"[journey start] partner={partner['partner_id']} flipped={flipped}")

    # ETA notifications: the immediate next stop gets an EXACT ETA; the rest get
    # a tentative "on the way" heads-up. Guests receive an SMS w/ tracking link.
    try:
        settings = await _get_settings()
        stop_eta = {s.order_id: s.eta_seconds for s in (req.stops or [])}
        ordered_ids = ([s.order_id for s in sorted(req.stops, key=lambda x: x.route_index)]
                       if req.stops else [o["order_id"] for o in orders_to_flip])
        for idx, oid in enumerate(ordered_ids):
            od = await db.orders.find_one({"order_id": oid}, {"_id": 0})
            if not od:
                continue
            if oid in stop_eta:
                await db.orders.update_one({"order_id": oid}, {"$set": {"delivery_eta_seconds": stop_eta[oid]}})
                od["delivery_eta_seconds"] = stop_eta[oid]
            is_next = (idx == 0)
            await _notify_customer_eta(od, settings, exact=is_next)
            if is_next:
                await db.orders.update_one({"order_id": oid}, {"$set": {"exact_eta_sent": True}})
    except Exception as e:
        logging.warning(f"[journey.eta] {e}")

    return {"ok": True, "flipped": flipped, "journey_started_at": now.isoformat()}


@api.post("/delivery/journey/end")
async def delivery_end_journey(partner=Depends(_current_partner)):
    """Delivery partner presses END DELIVERY (or all orders delivered)."""
    await db.delivery_partners.update_one(
        {"partner_id": partner["partner_id"]},
        {"$set": {"journey_active": False, "journey_ended_at": datetime.now(timezone.utc)},
         "$unset": {"journey_stops": "", "journey_polyline": "",
                    "journey_origin_lat": "", "journey_origin_lng": "",
                    "journey_origin_address": "", "journey_total_duration_sec": "",
                    "journey_optimized": "", "journey_order_ids": ""}},
    )
    return {"ok": True}


@api.get("/delivery/journey/current")
async def delivery_current_journey(partner=Depends(_current_partner)):
    """Return the persisted active journey for this partner (or `null` if none).

    Used by the delivery app on login to restore the exact same route the driver
    was working on before they closed / logged out.
    """
    doc = await db.delivery_partners.find_one({"partner_id": partner["partner_id"]}, {"_id": 0})
    if not doc or not doc.get("journey_active"):
        return {"active": False, "journey": None}
    started = doc.get("journey_started_at")
    return {
        "active": True,
        "journey": {
            "started_at": (started.isoformat() if hasattr(started, "isoformat") else started),
            "origin_lat": doc.get("journey_origin_lat"),
            "origin_lng": doc.get("journey_origin_lng"),
            "origin_address": doc.get("journey_origin_address"),
            "order_ids": doc.get("journey_order_ids", []),
            "stops": doc.get("journey_stops", []),
            "polyline": doc.get("journey_polyline"),
            "total_duration_sec": doc.get("journey_total_duration_sec", 0),
            "optimized": doc.get("journey_optimized", True),
        },
    }


@api.post("/delivery/route")
async def delivery_optimize_route(req: DeliveryRouteReq, partner=Depends(_current_partner)):
    """Build a route from origin through all provided orders back to origin.
    When req.optimize is True, Google reorders waypoints for shortest total time.
    When False, the given order_ids order is respected (used after user drags stops)."""
    orders = await db.orders.find(
        {"order_id": {"$in": req.order_ids}, "delivery_partner_id": partner["partner_id"]},
        {"_id": 0}
    ).to_list(50)
    if not orders:
        raise HTTPException(404, "No matching orders for this partner")
    # Ensure every order has a lat/lng
    resolved: List[dict] = []
    for o in orders:
        addr = await _ensure_order_coords(o)
        if not addr or not addr.get("lat") or not addr.get("lng"):
            continue
        resolved.append({**o, "address": addr})
    if not resolved:
        raise HTTPException(400, "Could not geocode any of the order addresses.")

    # If user manually reordered, honour that order — sort `resolved` by req.order_ids position.
    if not req.optimize:
        order_pos = {oid: i for i, oid in enumerate(req.order_ids)}
        resolved.sort(key=lambda o: order_pos.get(o["order_id"], 999))

    origin = f"{req.origin_lat},{req.origin_lng}"
    waypoints = [f"{o['address']['lat']},{o['address']['lng']}" for o in resolved]
    # Return-to-origin route: destination == origin, all stops as waypoints
    result = await _google_directions_optimize(origin, origin, waypoints, optimize=req.optimize)

    if not result:
        # Fallback: preserve given order, compute a naive Haversine ETA per leg (5min per stop)
        stops = []
        total_dur = 0
        for idx, o in enumerate(resolved):
            eta = (idx + 1) * 900  # 15min per stop
            stops.append({
                "order_id": o["order_id"], "route_index": idx,
                "eta_seconds": eta,
                "duration_sec": 900, "distance_m": 5000,
                "address": _address_string(o["address"]),
                "lat": o["address"]["lat"], "lng": o["address"]["lng"],
            })
            total_dur += 900
        return {"ok": True, "optimized": False, "stops": stops, "total_duration_sec": total_dur,
                "polyline": None, "note": "Google Maps unavailable — using naive ETA."}

    # Reorder resolved based on Google's optimized waypoint_order
    order_indices = result.get("waypoint_order") or list(range(len(resolved)))
    stops = []
    cumulative_dur = 0
    for pos, orig_idx in enumerate(order_indices):
        o = resolved[orig_idx]
        # legs[pos] is origin → this stop; legs[pos].duration is time from previous stop to this stop
        leg = result["legs"][pos] if pos < len(result["legs"]) else {"duration_sec": 0, "distance_m": 0}
        cumulative_dur += leg.get("duration_sec", 0)
        stops.append({
            "order_id": o["order_id"], "route_index": pos,
            "eta_seconds": cumulative_dur,
            "duration_sec": leg.get("duration_sec", 0),
            "distance_m": leg.get("distance_m", 0),
            "address": _address_string(o["address"]),
            "lat": o["address"]["lat"], "lng": o["address"]["lng"],
        })

    # Persist route order + ETA on each order for customer polling
    now = datetime.now(timezone.utc)
    for s in stops:
        await db.orders.update_one(
            {"order_id": s["order_id"]},
            {"$set": {
                "delivery_route_order": s["route_index"],
                "delivery_eta_seconds": s["eta_seconds"],
                "delivery_leg_duration_sec": s["duration_sec"],  # time for THIS leg only (previous → this)
                "delivery_leg_distance_m": s["distance_m"],
                "delivery_eta_updated_at": now,
            }},
        )

    return {"ok": True, "optimized": req.optimize, "stops": stops,
            "total_duration_sec": cumulative_dur,
            "polyline": result.get("overview_polyline")}


# ---- Customer: Tracking endpoint (polling) ----
@api.get("/orders/{order_id}/tracking")
async def order_tracking(order_id: str, user: User = Depends(_current_user)):
    order = await db.orders.find_one({"order_id": order_id, "user_id": user.user_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")

    # Compute how many stops are between the driver's current position and this order.
    # Only meaningful if this order is on an active route (assigned/picked_up/on_the_way/arrived).
    stops_away: Optional[int] = None
    partner_id = order.get("delivery_partner_id")
    my_route_idx = order.get("delivery_route_order")
    my_delivery_status = order.get("delivery_status")
    if partner_id and my_route_idx is not None and my_delivery_status not in ("delivered", None):
        stops_away = await db.orders.count_documents({
            "delivery_partner_id": partner_id,
            "delivery_status": {"$in": ["assigned", "picked_up", "on_the_way", "arrived"]},
            "delivery_route_order": {"$lt": my_route_idx},
        })
    elif my_delivery_status == "delivered":
        stops_away = 0

    # Live partner location — read directly from the delivery_partners doc so
    # we always show the driver's CURRENT GPS ping, not the stale snapshot that
    # was stamped onto the order when the journey started. Falls back to the
    # order's copy if the partner doc has no live coords yet.
    partner_loc: Optional[dict] = None
    partner_doc: Optional[dict] = None
    if partner_id:
        partner_doc = await db.delivery_partners.find_one(
            {"partner_id": partner_id},
            {"_id": 0, "current_lat": 1, "current_lng": 1,
             "current_location_updated_at": 1, "journey_polyline": 1},
        )
    if partner_doc and partner_doc.get("current_lat") is not None:
        partner_loc = {
            "lat": partner_doc.get("current_lat"),
            "lng": partner_doc.get("current_lng"),
            "updated_at": partner_doc.get("current_location_updated_at"),
        }
    elif order.get("delivery_partner_lat") is not None:
        partner_loc = {
            "lat": order.get("delivery_partner_lat"),
            "lng": order.get("delivery_partner_lng"),
            "updated_at": order.get("delivery_partner_updated_at"),
        }

    return {
        "order_id": order_id,
        "status": order.get("status"),
        "delivery_status": order.get("delivery_status"),
        "delivery_partner": {
            "name": order.get("delivery_partner_name"),
            "phone": order.get("delivery_partner_phone"),
        } if order.get("delivery_partner_id") else None,
        "partner_location": partner_loc,
        "destination": {
            "lat": (order.get("address") or {}).get("lat"),
            "lng": (order.get("address") or {}).get("lng"),
            "address": _address_string(order.get("address") or {}),
        } if (order.get("address") or {}).get("lat") else None,
        "eta_seconds": order.get("delivery_eta_seconds"),              # cumulative from driver's start location
        "leg_duration_sec": order.get("delivery_leg_duration_sec"),   # time for JUST this leg (previous → me)
        "eta_updated_at": order.get("delivery_eta_updated_at"),
        "stops_away": stops_away,
        "route_polyline": order.get("route_polyline") or (partner_doc or {}).get("journey_polyline"),
        "tracking_events": order.get("tracking_events", [])[-6:],
    }


# ============================================================
# Public downloads (marketing collateral)
# ============================================================
@api.get("/downloads/pitch-deck")
async def download_pitch_deck():
    """Serve the Curry & Co. sales pitch deck PDF for download.

    Public — no auth required so it can be shared with prospects directly.
    """
    from pathlib import Path
    pdf_path = Path("/app/exports/CurryCo_Sales_Pitch.pdf")
    if not pdf_path.exists():
        raise HTTPException(404, "Pitch deck not generated yet.")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename="CurryCo_Sales_Pitch.pdf",
    )


@api.get("/legal/privacy")
async def public_privacy_policy():
    """Publicly-hosted Privacy Policy + Terms — used by Apple/Google store metadata."""
    from pathlib import Path
    p = Path("/app/exports/privacy.html")
    if not p.exists():
        raise HTTPException(404, "Privacy policy not found.")
    return FileResponse(path=str(p), media_type="text/html")


@api.get("/health/web-bundle")
async def health_web_bundle():
    """Diagnostic endpoint for the SPA web-bundle deploy status.

    Lets us (and Emergent Support) inspect production state without shell:
      * present:   is any dist/index.html available?
      * source:    which of the two candidate dirs is being served
      * dist_size: total bytes of the served bundle
      * frontend_source_shipped: was /app/frontend/package.json included in the
                                 production image (i.e. can we self-build)?
    """
    import shutil as _sh
    served = _resolve_web_dist()
    size = 0
    if served and served.exists():
        for p in served.rglob("*"):
            if p.is_file():
                try:
                    size += p.stat().st_size
                except Exception:
                    pass
    return {
        "present": served is not None,
        "source": str(served) if served else None,
        "prod_dir_exists": _WEB_DIST_PROD.exists(),
        "prod_dir_has_index": (_WEB_DIST_PROD / "index.html").exists(),
        "preview_dir_exists": _WEB_DIST_PREVIEW.exists(),
        "preview_dir_has_index": (_WEB_DIST_PREVIEW / "index.html").exists(),
        "dist_size_bytes": size,
        "frontend_source_shipped": Path("/app/frontend/package.json").exists(),
        "npx_available": _sh.which("npx") is not None,
        "yarn_available": _sh.which("yarn") is not None,
    }


# --- Register router
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------
# SPA static mounts + catch-all fallback.
# MUST be registered AFTER include_router(api) so that /api/* routes
# resolve first — anything else falls back to index.html which lets Expo
# Router handle client-side routing (/admin, /customer, /order/[id] etc.).
# ---------------------------------------------------------------

def _try_build_web_bundle() -> bool:
    """Ensure /app/backend/web_dist/ (or the preview alt) has a working Expo
    web bundle. If NEITHER location has index.html, attempt to build in
    /app/frontend/ and then MIRROR the result into /app/backend/web_dist/ so
    the next production deploy will ship the bundle inside the backend image.

    Returns True if a web bundle is available after this call.
    """
    import subprocess, shutil

    # Fast path — anything already usable?
    if _resolve_web_dist():
        # Make sure production copy exists (mirror if only preview has it).
        preview = _WEB_DIST_PREVIEW / "index.html"
        prod = _WEB_DIST_PROD / "index.html"
        if preview.exists() and not prod.exists():
            try:
                if _WEB_DIST_PROD.exists():
                    shutil.rmtree(_WEB_DIST_PROD)
                shutil.copytree(_WEB_DIST_PREVIEW, _WEB_DIST_PROD)
                log.info(f"[web-build] mirrored preview dist -> {_WEB_DIST_PROD}")
            except Exception as e:
                log.warning(f"[web-build] mirror to prod dir failed: {e}")
        return True

    log.info(f"[web-build] no dist at {_WEB_DIST_PROD} or {_WEB_DIST_PREVIEW} — attempting to build")

    frontend_dir = Path("/app/frontend")
    if not (frontend_dir / "package.json").exists():
        log.warning(
            f"[web-build] frontend source not present at {frontend_dir} — "
            "cannot build web bundle in this container. "
            "Ship /app/backend/web_dist/ pre-built with the image instead."
        )
        return False

    npx = shutil.which("npx") or shutil.which("yarn") or shutil.which("npm")
    if not npx:
        log.warning("[web-build] npx/yarn/npm not on PATH; cannot build")
        return False

    if not (frontend_dir / "node_modules").exists():
        yarn = shutil.which("yarn")
        if yarn:
            log.info("[web-build] node_modules missing — running yarn install …")
            try:
                subprocess.run(
                    [yarn, "install", "--frozen-lockfile", "--production=false"],
                    cwd=str(frontend_dir),
                    timeout=180, check=False,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env={**os.environ, "CI": "1", "SKIP_PREINSTALL_GUARD": "1"},
                )
            except Exception as e:
                log.warning(f"[web-build] yarn install failed: {e}")

    try:
        cmd = [npx, "expo", "export", "--platform", "web", "--output-dir", "dist"]
        if npx.endswith("yarn"):
            cmd = [npx, "run", "build:web"]
        log.info(f"[web-build] running: {' '.join(cmd)} (cwd={frontend_dir})")
        proc = subprocess.run(
            cmd, cwd=str(frontend_dir), timeout=240, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "APP_VARIANT": os.environ.get("APP_VARIANT", "customer"), "CI": "1"},
        )
        tail = (proc.stdout[-800:] + proc.stderr[-800:]).decode(errors="replace")
        log.info(f"[web-build] exit={proc.returncode}, tail: {tail}")
    except subprocess.TimeoutExpired:
        log.error("[web-build] expo export timed out after 240s")
    except Exception as e:
        log.error(f"[web-build] exception: {e}")

    # Mirror preview → prod dir if build succeeded.
    if (_WEB_DIST_PREVIEW / "index.html").exists():
        try:
            if _WEB_DIST_PROD.exists():
                shutil.rmtree(_WEB_DIST_PROD)
            shutil.copytree(_WEB_DIST_PREVIEW, _WEB_DIST_PROD)
            log.info(f"[web-build] mirrored to {_WEB_DIST_PROD}")
        except Exception as e:
            log.warning(f"[web-build] mirror step failed: {e}")

    ok = _resolve_web_dist() is not None
    log.info(f"[web-build] result: dist available={ok}")
    return ok


# Fire the build check ONCE at module import.
_try_build_web_bundle()

WEB_DIST = _resolve_web_dist() or _WEB_DIST_PROD  # re-resolve after build
_WEB_DIST_PRESENT = _resolve_web_dist() is not None
log.info(f"[web-build] serving SPA={_WEB_DIST_PRESENT} from {WEB_DIST}")

if _WEB_DIST_PRESENT:
    # Serve the JS bundle & static assets folders that Expo emits.
    if (WEB_DIST / "_expo").exists():
        app.mount("/_expo", StaticFiles(directory=str(WEB_DIST / "_expo")), name="expo-static")
    if (WEB_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")), name="web-assets")


_INDEX_HTML = WEB_DIST / "index.html"
_FAVICON = WEB_DIST / "favicon.ico"


@app.get("/favicon.ico", include_in_schema=False)
async def _favicon():
    if _FAVICON.exists():
        return FileResponse(str(_FAVICON))
    raise HTTPException(404)


# Diagnostic page shown when the Expo web bundle isn't shipped with the deploy.
# This is a fallback so the user gets a clear message instead of a bare JSON 404.
_NO_WEB_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{BRAND_NAME} — Web Bundle Missing</title>
<style>body{font-family:-apple-system,sans-serif;max-width:640px;margin:60px auto;padding:20px;line-height:1.6;color:#2A1D18}
h1{color:#B14F36}code{background:#f4efe9;padding:2px 6px;border-radius:4px}
.card{background:#FFF7E6;border:1px solid #FCD9A5;padding:16px;border-radius:8px;margin:20px 0}
a{color:#B14F36}
</style></head>
<body>
<h1>🛠  Web bundle not deployed</h1>
<p>The FastAPI backend is running (see <a href="/docs">/docs</a> for the API), but the Expo web bundle
<code>/app/frontend/dist/</code> was not included in this Kubernetes deployment.</p>

<div class="card">
<strong>What's missing:</strong> the pre-built <code>dist/index.html</code>, <code>_expo/static/*</code> and
<code>assets/*</code> files that let the admin webapp run in the browser.
</div>

<p><strong>Working URLs on this deploy:</strong></p>
<ul>
  <li><a href="/health">/health</a> — Kubernetes probe (should return JSON <code>{"status":"ok"}</code>)</li>
  <li><a href="/docs">/docs</a> — API Swagger docs</li>
  <li><code>/api/menu/current</code>, <code>/api/admin/login</code>, etc. — all API routes work</li>
</ul>

<p><strong>Fix path:</strong> the deploy pipeline needs to include the pre-built <code>/app/frontend/dist/</code>
directory in the production container.  Contact <a href="mailto:support@emergent.sh">support@emergent.sh</a>
with your job ID and this message.</p>

<p style="color:#7F6E68;font-size:13px">Requested path: <code id="p"></code></p>
<script>document.getElementById('p').textContent = window.location.pathname;</script>
</body></html>"""


# Catch-all: anything that isn't /api/* → served from the web bundle (or SPA fallback).
# This is how single-page apps (SPAs) handle client-side routing — the client
# JS reads the URL and mounts the correct screen (admin, customer tabs, etc.).
# Registered UNCONDITIONALLY so that even without dist/ we give the user a
# helpful diagnostic page instead of a bare FastAPI JSON 404.
#
# IMPORTANT: We intentionally DO NOT exclude /_expo/* and /assets/* here.
# StaticFiles mounts above take precedence when present, but if they weren't
# registered (e.g. dist wasn't materialized when the module first imported),
# we fall through to disk-serving here so icon fonts / images still work.
@app.get("/{full_path:path}", include_in_schema=False)
async def _spa_fallback(full_path: str):
    # Reserved backend-only prefixes MUST NOT be intercepted here.
    if full_path.startswith(("api/", "api", "docs", "openapi.json", "redoc", "health", "healthz")):
        raise HTTPException(404)

    # Try to serve any static file directly if it exists under dist/.
    # This is a safety net for /_expo/* and /assets/* in case the StaticFiles
    # mounts didn't register (e.g. the folder was created after startup).
    web_root = _resolve_web_dist() or WEB_DIST
    if web_root and web_root.exists():
        candidate = web_root / full_path
        if candidate.is_file():
            # Set a long cache header for hashed static assets (JS bundles + fonts + images).
            headers = {}
            if any(s in full_path for s in ("_expo/static/", "assets/")) and "." in full_path.rsplit("/", 1)[-1]:
                headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return FileResponse(str(candidate), headers=headers)
        # Non-file (SPA route like /admin/menu) → serve index.html with no-cache
        # so the browser always picks up the newest JS bundle hash after a deploy.
        index_html = web_root / "index.html"
        if index_html.exists():
            return FileResponse(str(index_html), headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            })

    # No bundle at all — show the diagnostic page.
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=_NO_WEB_HTML, status_code=200)


@app.on_event("startup")
async def _startup():
    try:
        # Migrate: any legacy docs with email:null cause DuplicateKeyError on new
        # partial-unique index. Strip the null field before recreating the index.
        try:
            await db.users.update_many({"email": None}, {"$unset": {"email": 1}})
        except Exception as _mig_err:
            logger.warning(f"user email null-cleanup skipped: {_mig_err}")

        # Recreate `email` index as partial-unique (only enforces uniqueness when
        # email is a real string) — allows phone-only customers created via Admin
        # New Order flow without collisions.
        try:
            existing_idx = await db.users.index_information()
            if "email_1" in existing_idx and not existing_idx["email_1"].get("partialFilterExpression"):
                await db.users.drop_index("email_1")
        except Exception as _drop_err:
            logger.warning(f"user email index drop skipped: {_drop_err}")

        await db.users.create_index(
            "email",
            unique=True,
            partialFilterExpression={"email": {"$type": "string"}},
            name="email_1",
        )
        await db.users.create_index("user_id", unique=True)
        await db.user_sessions.create_index("session_token", unique=True)
        await db.user_sessions.create_index("user_id")
        await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
        await db.password_reset_codes.create_index("email")
        await db.password_reset_codes.create_index("expires_at", expireAfterSeconds=0)
        await db.weekly_menus.create_index("week_start", unique=True)
        await db.orders.create_index("order_id", unique=True)
        await db.orders.create_index("user_id")
        await db.payment_transactions.create_index("session_id", unique=True)
        await db.catering_packages.create_index("package_id", unique=True)
        await db.admins.create_index("email", unique=True)
        await db.master_menu.create_index("item_id", unique=True)
        await db.master_menu.create_index([("category", 1), ("cuisine", 1)])
        await db.business_settings.create_index("key", unique=True)
        # Export download tokens: unique-token lookup only. Expiration is
        # enforced LAZILY on read/create instead of via a MongoDB TTL — this
        # keeps startup non-destructive (no auto-hard-delete of user data by
        # the DB engine on cold-boot in production).
        # Migration: if an older deploy created the TTL variant of this index,
        # drop it so the engine stops silently reaping records.
        try:
            _existing_idx = await db.export_files.index_information()
            _exp_idx = _existing_idx.get("expires_at_1") or {}
            if _exp_idx.get("expireAfterSeconds") is not None:
                await db.export_files.drop_index("expires_at_1")
        except Exception as _drop_ttl_err:
            log.warning(f"export_files TTL drop skipped: {_drop_ttl_err}")
        await db.export_files.create_index("token", unique=True)
        await db.export_files.create_index("expires_at")
        # seed default admin (idempotent — password hashed in Python to avoid $ expansion)
        existing = await db.admins.find_one({"email": ADMIN_EMAIL.lower()}, {"_id": 0})
        if not existing:
            await db.admins.insert_one({
                "email": ADMIN_EMAIL.lower(),
                "password_hash": _pwd.hash(ADMIN_PASSWORD),
                "created_at": datetime.now(timezone.utc),
            })
            log.info(f"seeded default admin: {ADMIN_EMAIL}")

        # seed App Store / Play Store REVIEWER test account (idempotent).
        # These credentials are used ONLY by Apple/Google reviewers to log in
        # during app review. Configure via env vars — if REVIEWER_EMAIL is unset,
        # skip seeding entirely (so production deploys can turn this off).
        reviewer_email = os.environ.get("REVIEWER_EMAIL", "").strip().lower()
        reviewer_pw   = os.environ.get("REVIEWER_PASSWORD", "").strip()
        if reviewer_email and reviewer_pw:
            existing_r = await db.users.find_one({"email": reviewer_email}, {"_id": 0})
            if not existing_r:
                await db.users.insert_one({
                    "user_id": f"user_reviewer_{uuid.uuid4().hex[:6]}",
                    "email": reviewer_email,
                    "name": "App Reviewer",
                    "phone": "+14165550100",
                    "password_hash": _pwd.hash(reviewer_pw),
                    "provider": "password",
                    "loyalty_points": 500,
                    "created_at": datetime.now(timezone.utc),
                    "is_reviewer_account": True,
                })
                log.info(f"seeded reviewer test account: {reviewer_email}")
        log.info("indexes ready")
    except Exception as e:
        log.warning(f"index setup: {e}")

    # Kick off the Suparna Dey platform phone-home poller. Fires every N
    # seconds (default 300) to fetch tenant + subscription enforcement flags.
    # No-op when brand.json has no `platform.tenant_id`, so preview/dev boots
    # cleanly without a control-plane URL.
    try:
        from platform_client import start_platform_poller
        start_platform_poller()
    except Exception as _plat_err:
        log.warning(f"platform poller start skipped: {_plat_err}")


@app.on_event("shutdown")
async def _shutdown():
    from platform_client import stop_platform_poller
    await stop_platform_poller()
    await _push_client.aclose()
    client.close()
