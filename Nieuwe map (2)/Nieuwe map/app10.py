import os
import random
import sqlite3
import time
from flask import Flask, request, redirect, url_for, session, render_template_string, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "peaky-blinders-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///peaky_blinders.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

GAME_NAME = "Peaky Blinders"
CRIME_COOLDOWN = 20
TRAVEL_COST = 100
BRIBE_WAIT_RATIO = 0.45
BRIBE_ATTEMPT_COOLDOWN = 15
HONEST_OFFICER_CHANCE = 5
LUCKY_OFFICER_CHANCE = 1

# Single source of truth for every city shown anywhere in the game.
# Keep this order consistent across Smuggling, Travel, Cargo, Garages,
# Distilleries, Casino Licenses/Casinos, and Territory Wars.
CITIES = [
    "Birmingham",
    "London",
    "Liverpool",
    "Manchester",
    "Dublin",
    "Glasgow",
    "Amsterdam",
    "Paris",
    "Havana",
    "Chicago",
    "New York",
]

CITY_CASINOS = {
    "Birmingham": 3,
    "London": 5,
    "Liverpool": 2,
    "Manchester": 2,
    "Dublin": 2,
    "Glasgow": 2,
    "Amsterdam": 3,
    "Paris": 3,
    "Havana": 2,
    "Chicago": 4,
    "New York": 6,
}
CASINOS_PER_CITY = 3  # fallback for older templates/helpers
CASINO_LICENSE_COST = 250000
CASINO_LICENSE_REQUIRED_RANK = "Family Boss"
CASINO_BASE_PRICE = 100000
CASINO_PRICE_MULTIPLIER = 1.35
CASINO_HOUSE_CUT_PERCENT = 10

HEIST_COOLDOWN = 90
HEIST_PLANS = {
    "bookmaker": {
        "name": "Bookmaker Shakedown",
        "min_power": 200,
        "bullets": 5,
        "base_success": 62,
        "cash_min": 700,
        "cash_max": 1800,
        "exp": 25,
        "jail": 45,
    },
    "train": {
        "name": "Train Payroll Robbery",
        "min_power": 900,
        "bullets": 20,
        "base_success": 48,
        "cash_min": 3500,
        "cash_max": 8500,
        "exp": 70,
        "jail": 90,
    },
    "armory": {
        "name": "Police Armory Raid",
        "min_power": 1800,
        "bullets": 45,
        "base_success": 36,
        "cash_min": 9000,
        "cash_max": 22000,
        "exp": 140,
        "jail": 150,
    },
}

PROPERTY_TYPES = {
    "small_pub": {"name": "Small Pub", "cost": 25000, "income_per_hour": 250, "prestige": 0},
    "betting_shop": {"name": "Betting Shop", "cost": 75000, "income_per_hour": 750, "prestige": 0},
    "jazz_club": {"name": "Jazz Club", "cost": 150000, "income_per_hour": 1500, "prestige": 0},
    "nightclub": {"name": "Nightclub", "cost": 500000, "income_per_hour": 5000, "prestige": 0},
    "luxury_hotel": {"name": "Luxury Hotel", "cost": 2500000, "income_per_hour": 25000, "prestige": 0},
    "grand_estate": {"name": "Grand Estate", "cost": 10000000, "income_per_hour": 0, "prestige": 1000},
}

INFLUENCE_TYPES = {
    "police_chief": {
        "name": "Police Chief",
        "cost": 150000,
        "effect": "-10% arrest risk and +15% corrupt officer chance",
        "description": "Control patrol pressure and make jail escapes easier.",
    },
    "judge": {
        "name": "Judge",
        "cost": 300000,
        "effect": "-25% jail time and -20% fines",
        "description": "Courtroom influence keeps your people out of prison longer.",
    },
    "mayor": {
        "name": "Mayor",
        "cost": 750000,
        "effect": "+10% property income and +10% casino vault income",
        "description": "Political cover turns businesses into a stronger empire.",
    },
    "customs_officer": {
        "name": "Customs Officer",
        "cost": 500000,
        "effect": "+10% smuggling profit and -8% smuggling arrest risk",
        "description": "Move contraband through ports and rail depots with less heat.",
    },
}

INTERNATIONAL_CITIES = ["Dublin", "Glasgow", "Amsterdam", "Paris", "Havana"]
# Self-smuggling/travel requires a paid ticket.
# Carrying contraband can also trigger customs/police risk.
DEFAULT_DOMESTIC_TRAVEL_COST = 100
TRAVEL_TICKET_COSTS = {
    "Birmingham": 100,
    "London": 100,
    "Liverpool": 100,
    "Manchester": 100,
    "Dublin": 400,
    "Glasgow": 400,
    "Amsterdam": 500,
    "Paris": 500,
    "Havana": 2500,
    "Chicago": 5000,
    "New York": 5000,
}
INTERNATIONAL_TRAVEL_COST = 500

# Cargo transport options: higher transport cost = faster arrival.
# Economy is the baseline "about an hour" option.
SHIPMENT_SPEEDS = {
    "economy": {"label": "Economy Cargo", "seconds": 3600, "cost_multiplier": 1.0},
    "standard": {"label": "Standard Cargo", "seconds": 1800, "cost_multiplier": 1.75},
    "express": {"label": "Express Cargo", "seconds": 900, "cost_multiplier": 3.0},
    "priority": {"label": "Priority Cargo", "seconds": 300, "cost_multiplier": 6.0},
}
SHIPMENT_BASE_COST = 250
SHIPMENT_COST_PER_UNIT = 15
SHIPMENT_CUSTOMS_RISK_DOMESTIC = 4
SHIPMENT_CUSTOMS_RISK_INTERNATIONAL = 16

TERRITORY_WAR_COST = 500000
TERRITORY_WAR_BULLETS = 5000
TERRITORY_MIN_MEMBERS = 5
TERRITORY_ATTACK_COOLDOWN = 24 * 60 * 60
TERRITORY_PROTECTION_TIME = 12 * 60 * 60

CITY_TERRITORY_DATA = {
    "Birmingham": {"tax_per_hour": 25000, "bonus": "+5% crime income, +5% property income"},
    "London": {"tax_per_hour": 40000, "bonus": "+10% casino income"},
    "Liverpool": {"tax_per_hour": 30000, "bonus": "+10% smuggling profit"},
    "Manchester": {"tax_per_hour": 30000, "bonus": "-10% warehouse upgrade costs"},
    "Dublin": {"tax_per_hour": 35000, "bonus": "+5% cargo safety"},
    "Glasgow": {"tax_per_hour": 35000, "bonus": "+5% property income"},
    "Paris": {"tax_per_hour": 55000, "bonus": "-10% customs risk"},
    "Amsterdam": {"tax_per_hour": 50000, "bonus": "-15% cargo costs"},
    "Havana": {"tax_per_hour": 70000, "bonus": "+15% rum profit"},
    "Chicago": {"tax_per_hour": 60000, "bonus": "+15% weapons income"},
    "New York": {"tax_per_hour": 75000, "bonus": "+15% business income"},
}

MARKET_PRICES = {
    "Birmingham": {"gin": 18},
    "London": {"gin": 35},
    "Liverpool": {"gin": 28},
    "Manchester": {"gin": 30},
    "Chicago": {"gin": 55},
    "New York": {"gin": 42},
    "Dublin": {"gin": 48},
    "Glasgow": {"gin": 46},
    "Paris": {"gin": 62},
    "Amsterdam": {"gin": 58},
    "Havana": {"gin": 70},
}

CONTRABAND = {
    "gin": {"label": "Gin", "risk": 2, "prices": {"Birmingham": 18, "London": 35, "Liverpool": 28, "Manchester": 30, "Chicago": 55, "New York": 42, "Dublin": 48, "Glasgow": 46, "Paris": 62, "Amsterdam": 58, "Havana": 70}},
    "whiskey": {"label": "Whiskey", "risk": 4, "prices": {"Birmingham": 40, "London": 22, "Liverpool": 35, "Manchester": 38, "Chicago": 60, "New York": 58, "Dublin": 30, "Glasgow": 32, "Paris": 75, "Amsterdam": 68, "Havana": 85}},
    "rum": {"label": "Rum", "risk": 5, "prices": {"Birmingham": 55, "London": 40, "Liverpool": 30, "Manchester": 35, "Chicago": 22, "New York": 25, "Dublin": 48, "Glasgow": 52, "Paris": 70, "Amsterdam": 66, "Havana": 18}},
    "cigars": {"label": "Cigars", "risk": 6, "prices": {"Birmingham": 80, "London": 45, "Liverpool": 65, "Manchester": 70, "Chicago": 95, "New York": 100, "Dublin": 88, "Glasgow": 82, "Paris": 120, "Amsterdam": 110, "Havana": 35}},
    "luxury_watches": {"label": "Luxury Watches", "risk": 8, "prices": {"Birmingham": 150, "London": 250, "Liverpool": 180, "Manchester": 200, "Chicago": 300, "New York": 320, "Dublin": 230, "Glasgow": 220, "Paris": 360, "Amsterdam": 340, "Havana": 280}},
    "weapons": {"label": "Weapons", "risk": 12, "prices": {"Birmingham": 250, "London": 280, "Liverpool": 240, "Manchester": 260, "Chicago": 180, "New York": 190, "Dublin": 300, "Glasgow": 290, "Paris": 360, "Amsterdam": 330, "Havana": 160}},
}


# Re-order the market dictionary to match CITIES exactly.
# All city-based pages iterate over CITIES, so this keeps city order identical everywhere.
MARKET_PRICES = {city: MARKET_PRICES[city] for city in CITIES}

# Safety check: every city must have casino limits, territory data, ticket prices,
# and every contraband item must have a price in every city.
def validate_city_configuration():
    missing = []
    for city in CITIES:
        if city not in MARKET_PRICES:
            missing.append(f"MARKET_PRICES missing {city}")
        if city not in CITY_CASINOS:
            missing.append(f"CITY_CASINOS missing {city}")
        if city not in CITY_TERRITORY_DATA:
            missing.append(f"CITY_TERRITORY_DATA missing {city}")
        if city not in TRAVEL_TICKET_COSTS:
            missing.append(f"TRAVEL_TICKET_COSTS missing {city}")
    for item_key, data in CONTRABAND.items():
        for city in CITIES:
            if city not in data.get("prices", {}):
                missing.append(f"CONTRABAND {item_key} missing price for {city}")
    if missing:
        raise RuntimeError("City configuration mismatch: " + "; ".join(missing))

validate_city_configuration()

WAREHOUSE_LEVELS = {
    0: {"name": "Starter Storage", "capacity": 50, "upgrade_cost": 10000},
    1: {"name": "Small Warehouse", "capacity": 500, "upgrade_cost": 50000},
    2: {"name": "Medium Warehouse", "capacity": 2000, "upgrade_cost": 200000},
    3: {"name": "Large Warehouse", "capacity": 5000, "upgrade_cost": 750000},
    4: {"name": "Empire Warehouse", "capacity": 10000, "upgrade_cost": None},
}

OLDTIMER_VEHICLES = [
    {"key": "street_hand_cart", "year": 1919, "name": "Street Hand Cart", "price": 250, "bonus": 1},
    {"key": "birmingham_courier_bicycle", "year": 1920, "name": "Birmingham Courier Bicycle", "price": 500, "bonus": 2},
    {"key": "canal_work_horse", "year": 1921, "name": "Canal Work Horse", "price": 1000, "bonus": 3},
    {"key": "raleigh_motor_bicycle", "year": 1922, "name": "Raleigh Motor Bicycle", "price": 2500, "bonus": 5},
    {"key": "horse_goods_cart", "year": 1923, "name": "Horse & Goods Cart", "price": 5000, "bonus": 7},
    {"key": "luxury_carriage_pair", "year": 1924, "name": "Luxury Carriage & Pair", "price": 10000, "bonus": 10},
    {"key": "ford_model_t", "year": 1925, "name": "Ford Model T", "price": 25000, "bonus": 15},
    {"key": "austin_12_heavy", "year": 1926, "name": "Austin 12 Heavy", "price": 50000, "bonus": 20},
    {"key": "rolls_royce_silver_ghost", "year": 1927, "name": "Rolls-Royce Silver Ghost", "price": 100000, "bonus": 30},
    {"key": "bentley_4_5_litre", "year": 1928, "name": "Bentley 4½ Litre", "price": 250000, "bonus": 40},
]

VEHICLE_BY_KEY = {vehicle["key"]: vehicle for vehicle in OLDTIMER_VEHICLES}

VEHICLE_DESIGN = {
    "street_hand_cart": {"category": "Starter Transport", "tone": "#7a5b35", "icon": "HAND CART"},
    "birmingham_courier_bicycle": {"category": "Starter Transport", "tone": "#6d7355", "icon": "BICYCLE"},
    "canal_work_horse": {"category": "Starter Transport", "tone": "#6b4a2b", "icon": "WORK HORSE"},
    "raleigh_motor_bicycle": {"category": "Middle Class", "tone": "#4f5d6b", "icon": "MOTOR BIKE"},
    "horse_goods_cart": {"category": "Middle Class", "tone": "#80643d", "icon": "GOODS CART"},
    "luxury_carriage_pair": {"category": "Middle Class", "tone": "#8a6a3a", "icon": "CARRIAGE"},
    "ford_model_t": {"category": "Elite Motors", "tone": "#2f3c46", "icon": "MODEL T"},
    "austin_12_heavy": {"category": "Elite Motors", "tone": "#374338", "icon": "AUSTIN 12"},
    "rolls_royce_silver_ghost": {"category": "Legendary Collection", "tone": "#7d7d7d", "icon": "SILVER GHOST"},
    "bentley_4_5_litre": {"category": "Legendary Collection", "tone": "#244032", "icon": "BENTLEY"},
}

for vehicle in OLDTIMER_VEHICLES:
    vehicle.update(VEHICLE_DESIGN.get(vehicle["key"], {"category": "Transport", "tone": "#555", "icon": "MOTOR"}))

VEHICLE_CATEGORY_ORDER = ["Starter Transport", "Middle Class", "Elite Motors", "Legendary Collection"]

def vehicle_categories_for_showroom(vehicles):
    grouped = []
    for category in VEHICLE_CATEGORY_ORDER:
        rows = [vehicle for vehicle in vehicles if vehicle.get("category") == category]
        if rows:
            grouped.append({"name": category, "vehicles": rows})
    return grouped

def garage_city_value(citydata):
    total = 0
    for row in citydata.get("rows", []):
        total += int(safe_number(row.get("quantity", 0))) * int(row.get("vehicle", {}).get("price", 0))
    return total


RANKS = [
    (5000, "Head of the Shelby Company"),
    (3500, "Family Boss"),
    (2500, "Underboss"),
    (1800, "Chief Enforcer"),
    (1200, "Caporegime"),
    (800, "Trusted Lieutenant"),
    (500, "Crew Leader"),
    (300, "Made Man"),
    (100, "Shelby Associate"),
    (0, "Street Runner"),
]

RANK_BONUSES = {
    "Street Runner": {"crime_chance": 0, "crime_income": 0, "smuggling": 0, "attack": 0},
    "Shelby Associate": {"crime_chance": 5, "crime_income": 0, "smuggling": 0, "attack": 0},
    "Made Man": {"crime_chance": 8, "crime_income": 5, "smuggling": 0, "attack": 0},
    "Crew Leader": {"crime_chance": 10, "crime_income": 8, "smuggling": 5, "attack": 0},
    "Trusted Lieutenant": {"crime_chance": 12, "crime_income": 10, "smuggling": 8, "attack": 5},
    "Caporegime": {"crime_chance": 14, "crime_income": 12, "smuggling": 10, "attack": 8},
    "Chief Enforcer": {"crime_chance": 16, "crime_income": 15, "smuggling": 12, "attack": 12},
    "Underboss": {"crime_chance": 18, "crime_income": 18, "smuggling": 15, "attack": 15},
    "Family Boss": {"crime_chance": 20, "crime_income": 22, "smuggling": 20, "attack": 20},
    "Head of the Shelby Company": {"crime_chance": 25, "crime_income": 25, "smuggling": 25, "attack": 25},
}


RANK_BRIBE_CHANCES = {
    "Street Runner": 5,
    "Shelby Associate": 8,
    "Made Man": 12,
    "Crew Leader": 16,
    "Trusted Lieutenant": 22,
    "Caporegime": 30,
    "Chief Enforcer": 40,
    "Underboss": 55,
    "Family Boss": 70,
    "Head of the Shelby Company": 85,
}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    money = db.Column(db.Integer, default=500)
    bank = db.Column(db.Integer, default=0)
    exp = db.Column(db.Integer, default=0)
    rank = db.Column(db.String(60), default="Street Runner")
    location = db.Column(db.String(40), default="Birmingham")

    gin = db.Column(db.Integer, default=0)
    bullets = db.Column(db.Integer, default=0)
    bodyguards = db.Column(db.Integer, default=0)
    bulletproof_vests = db.Column(db.Integer, default=0)
    safehouses = db.Column(db.Integer, default=0)
    lookouts = db.Column(db.Integer, default=0)
    warehouse_level = db.Column(db.Integer, default=0)
    family_id = db.Column(db.Integer, db.ForeignKey("family.id"), nullable=True)
    family_role = db.Column(db.String(40), default="Solo")
    cars = db.Column(db.Integer, default=0)
    distilleries = db.Column(db.Integer, default=0)
    casino_license = db.Column(db.Boolean, default=False)
    police_chief_influence = db.Column(db.Boolean, default=False)
    judge_influence = db.Column(db.Boolean, default=False)
    mayor_influence = db.Column(db.Boolean, default=False)
    customs_officer_influence = db.Column(db.Boolean, default=False)

    last_crime = db.Column(db.Float, default=0.0)
    last_collect = db.Column(db.Float, default=0.0)
    is_dead = db.Column(db.Boolean, default=False)
    jail_until = db.Column(db.Float, default=0.0)
    arrests = db.Column(db.Integer, default=0)
    bribe_available_at = db.Column(db.Float, default=0.0)
    last_bribe_attempt = db.Column(db.Float, default=0.0)
    last_heist = db.Column(db.Float, default=0.0)
    heists_successful = db.Column(db.Integer, default=0)
    last_property_collect = db.Column(db.Float, default=0.0)

    def update_rank(self):
        if self.exp is None:
            self.exp = 0
        if not self.rank:
            self.rank = "Street Runner"
        for needed_exp, rank_name in RANKS:
            if self.exp >= needed_exp:
                self.rank = rank_name
                break


class Family(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    boss_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    bank = db.Column(db.Integer, default=0)
    created_at = db.Column(db.Float, default=time.time)

    boss = db.relationship("User", foreign_keys=[boss_id])
    members = db.relationship("User", foreign_keys="User.family_id", backref=db.backref("family", lazy=True))

class CityBusiness(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    city = db.Column(db.String(40), nullable=False)
    distilleries = db.Column(db.Integer, default=0)
    # pending_gin stores production that is ready but not yet collected.
    # This lets distilleries keep stock waiting when the warehouse is full.
    pending_gin = db.Column(db.Integer, default=0)
    last_collect = db.Column(db.Float, default=0.0)

    user = db.relationship("User", backref=db.backref("city_businesses", lazy=True))


class CityVehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    city = db.Column(db.String(40), nullable=False)
    vehicle_key = db.Column(db.String(60), nullable=False)
    quantity = db.Column(db.Integer, default=0)

    user = db.relationship("User", backref=db.backref("city_vehicles", lazy=True))


class WarehouseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    item_key = db.Column(db.String(60), nullable=False)
    quantity = db.Column(db.Integer, default=0)

    user = db.relationship("User", backref=db.backref("warehouse_items", lazy=True))






class Shipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    item_key = db.Column(db.String(60), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    origin = db.Column(db.String(40), nullable=False)
    destination = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.Float, default=time.time)
    arrives_at = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(30), default="in_transit")

    user = db.relationship("User", backref=db.backref("shipments", lazy=True))

class UserProperty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    property_key = db.Column(db.String(60), nullable=False)
    quantity = db.Column(db.Integer, default=0)

    user = db.relationship("User", backref=db.backref("properties", lazy=True))

class CityCasino(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(40), nullable=False)
    slot_number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    heir_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    price = db.Column(db.Integer, default=CASINO_BASE_PRICE)
    vault = db.Column(db.Integer, default=0)
    created_at = db.Column(db.Float, default=time.time)

    owner = db.relationship("User", foreign_keys=[owner_id], backref=db.backref("owned_casinos", lazy=True))
    heir = db.relationship("User", foreign_keys=[heir_id])


class CityTerritory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(40), unique=True, nullable=False)
    family_id = db.Column(db.Integer, db.ForeignKey("family.id"), nullable=True)
    last_tax_collect = db.Column(db.Float, default=time.time)
    last_war_at = db.Column(db.Float, default=0.0)
    protected_until = db.Column(db.Float, default=0.0)

    family = db.relationship("Family", backref=db.backref("territories", lazy=True))


def current_user():
    username = session.get("username")
    if not username:
        return None
    user = User.query.filter_by(username=username).first()
    if user:
        user.update_rank()
        db.session.commit()
    return user


def login_required():
    user = current_user()
    if not user:
        return None, redirect(url_for("index", msg="Please log in first."))
    if user.is_dead:
        session.clear()
        return None, redirect(url_for("index", msg="You were killed by a rival. Create a new account."))
    if safe_number(user.jail_until) > time.time() and request.endpoint not in ["jail", "bribe_officer"]:
        remaining = int(user.jail_until - time.time())
        return None, redirect(url_for("jail", msg=f"You are in jail for {remaining} more seconds."))
    return user, None


def safe_int(value):
    try:
        return int(value)
    except Exception:
        return 0


def rank_bonus(user, key):
    return RANK_BONUSES.get(user.rank, RANK_BONUSES["Street Runner"]).get(key, 0)


def safe_number(value):
    return value if value is not None else 0


def protection_loss_reduction(user):
    return min(int(safe_number(user.safehouses)) * 10 + family_bonus(user, "protection"), 55)


def lookout_arrest_reduction(user):
    return min(int(safe_number(user.lookouts)) * 2, 15)


def reduce_loss_by_protection(user, amount):
    reduction = protection_loss_reduction(user)
    protected = max(0, int(amount * (100 - reduction) / 100))
    return max(0, int(protected * influence_fine_multiplier(user)))

def ensure_city_businesses(user):
    """Create one business row per city for the player and return them in city order."""
    if not user or not user.id:
        return []

    existing = {b.city: b for b in CityBusiness.query.filter_by(user_id=user.id).all()}
    changed = False

    for city in CITIES:
        if city not in existing:
            existing[city] = CityBusiness(user_id=user.id, city=city, distilleries=0, pending_gin=0, last_collect=0.0)
            db.session.add(existing[city])
            changed = True

    # One-time migration: old versions stored all distilleries directly on User.
    # Move them into the player's current city so no purchased businesses vanish.
    old_total = int(safe_number(user.distilleries))
    if old_total > 0:
        current_city = user.location if user.location in MARKET_PRICES else "Birmingham"
        existing[current_city].distilleries = int(safe_number(existing[current_city].distilleries)) + old_total
        user.distilleries = 0
        changed = True

    if changed:
        db.session.commit()

    return [existing[city] for city in CITIES]


def business_for_current_city(user):
    ensure_city_businesses(user)
    city = user.location if user.location in MARKET_PRICES else "Birmingham"
    business = CityBusiness.query.filter_by(user_id=user.id, city=city).first()
    if not business:
        business = CityBusiness(user_id=user.id, city=city, distilleries=0, pending_gin=0, last_collect=0.0)
        db.session.add(business)
        db.session.commit()
    return business


def update_business_production(business):
    """Move elapsed distillery production into pending_gin without losing overflow."""
    now = time.time()
    distilleries = int(safe_number(business.distilleries))

    if distilleries <= 0:
        business.last_collect = now
        business.pending_gin = int(safe_number(getattr(business, "pending_gin", 0)))
        return 0

    if safe_number(business.last_collect) <= 0:
        business.last_collect = now
        business.pending_gin = int(safe_number(getattr(business, "pending_gin", 0)))
        return 0

    elapsed = int(now - safe_number(business.last_collect))
    produced = (elapsed // 60) * distilleries

    if produced > 0:
        business.pending_gin = int(safe_number(getattr(business, "pending_gin", 0))) + produced
        # Keep the leftover seconds so production timing stays fair.
        business.last_collect = safe_number(business.last_collect) + ((elapsed // 60) * 60)

    return produced


def business_ready_gin(business):
    update_business_production(business)
    return int(safe_number(getattr(business, "pending_gin", 0)))


def total_ready_gin(user):
    return sum(business_ready_gin(b) for b in ensure_city_businesses(user))


def total_distilleries(user):
    if not user or not user.id:
        return 0
    try:
        city_total = sum(int(safe_number(b.distilleries)) for b in ensure_city_businesses(user))
        return city_total
    except Exception:
        return int(safe_number(getattr(user, "distilleries", 0)))


def ensure_city_vehicles(user):
    if not user or not user.id:
        return []
    rows = []
    for city in CITIES:
        for vehicle in OLDTIMER_VEHICLES:
            row = CityVehicle.query.filter_by(user_id=user.id, city=city, vehicle_key=vehicle["key"]).first()
            if not row:
                row = CityVehicle(user_id=user.id, city=city, vehicle_key=vehicle["key"], quantity=0)
                db.session.add(row)
            rows.append(row)
    db.session.commit()
    return rows

def vehicle_quantity(user, city, vehicle_key):
    row = CityVehicle.query.filter_by(user_id=user.id, city=city, vehicle_key=vehicle_key).first()
    return int(safe_number(row.quantity)) if row else 0

def total_vehicles(user):
    if not user or not user.id:
        return 0
    try:
        ensure_city_vehicles(user)
        total = sum(int(safe_number(v.quantity)) for v in CityVehicle.query.filter_by(user_id=user.id).all())
        return max(total, int(safe_number(getattr(user, "cars", 0))))
    except Exception:
        return int(safe_number(getattr(user, "cars", 0)))

def vehicle_bonus(user):
    if not user or not user.id:
        return 0
    try:
        ensure_city_vehicles(user)
        bonus = 0
        for row in CityVehicle.query.filter_by(user_id=user.id).all():
            data = VEHICLE_BY_KEY.get(row.vehicle_key)
            if data:
                bonus += int(safe_number(row.quantity)) * int(data["bonus"])
        return min(bonus, 35)
    except Exception:
        return min(int(safe_number(getattr(user, "cars", 0))) * 3, 15)

def garage_overview(user):
    ensure_city_vehicles(user)
    overview = []
    for city in CITIES:
        total = 0
        rows = []
        for vehicle in OLDTIMER_VEHICLES:
            qty = vehicle_quantity(user, city, vehicle["key"])
            total += qty
            rows.append({"vehicle": vehicle, "quantity": qty})
        overview.append({"city": city, "total": total, "rows": rows})
    return overview

def owned_vehicles_in_city(user, city=None):
    if not user or not user.id:
        return []
    ensure_city_vehicles(user)
    city = city or user.location
    owned = []
    for vehicle in OLDTIMER_VEHICLES:
        qty = vehicle_quantity(user, city, vehicle["key"])
        if qty > 0:
            owned.append({"vehicle": vehicle, "quantity": qty})
    return owned


def get_selected_city_vehicle(user, vehicle_key):
    if not vehicle_key:
        return None, None
    vehicle = VEHICLE_BY_KEY.get(vehicle_key)
    if not vehicle:
        return None, None
    ensure_city_vehicles(user)
    row = CityVehicle.query.filter_by(user_id=user.id, city=user.location, vehicle_key=vehicle_key).first()
    if not row or safe_number(row.quantity) <= 0:
        return None, None
    return vehicle, row


def warehouse_level_info(user):
    level = int(safe_number(getattr(user, "warehouse_level", 0)))
    level = max(0, min(level, max(WAREHOUSE_LEVELS.keys())))
    return WAREHOUSE_LEVELS[level]


def warehouse_capacity(user):
    return int(warehouse_level_info(user)["capacity"])


def ensure_warehouse_items(user):
    if not user or not user.id:
        return []
    existing = {item.item_key: item for item in WarehouseItem.query.filter_by(user_id=user.id).all()}
    changed = False
    for item_key in CONTRABAND.keys():
        if item_key not in existing:
            existing[item_key] = WarehouseItem(user_id=user.id, item_key=item_key, quantity=0)
            db.session.add(existing[item_key])
            changed = True

    old_gin = int(safe_number(getattr(user, "gin", 0)))
    if old_gin > 0:
        existing["gin"].quantity = int(safe_number(existing["gin"].quantity)) + old_gin
        user.gin = 0
        changed = True

    if changed:
        db.session.commit()
    return [existing[key] for key in CONTRABAND.keys()]


def warehouse_item(user, item_key):
    ensure_warehouse_items(user)
    row = WarehouseItem.query.filter_by(user_id=user.id, item_key=item_key).first()
    if not row:
        row = WarehouseItem(user_id=user.id, item_key=item_key, quantity=0)
        db.session.add(row)
        db.session.commit()
    return row


def warehouse_quantity(user, item_key):
    if not user or not user.id:
        return 0
    row = WarehouseItem.query.filter_by(user_id=user.id, item_key=item_key).first()
    return int(safe_number(row.quantity)) if row else 0


def warehouse_used(user):
    if not user or not user.id:
        return 0
    ensure_warehouse_items(user)
    return sum(int(safe_number(item.quantity)) for item in WarehouseItem.query.filter_by(user_id=user.id).all())


def warehouse_free_space(user):
    return max(0, warehouse_capacity(user) - warehouse_used(user))


def warehouse_overview(user):
    ensure_warehouse_items(user)
    rows = []
    for key, data in CONTRABAND.items():
        rows.append({
            "key": key,
            "label": data["label"],
            "quantity": warehouse_quantity(user, key),
            "price": int(data["prices"].get(user.location, 0)),
            "risk": int(data["risk"]),
        })
    return rows


def is_international_city(city):
    return city in INTERNATIONAL_CITIES

def travel_cost_to(destination):
    return int(TRAVEL_TICKET_COSTS.get(destination, INTERNATIONAL_TRAVEL_COST if is_international_city(destination) else DEFAULT_DOMESTIC_TRAVEL_COST))

def shipment_speed_options():
    return SHIPMENT_SPEEDS

def shipment_seconds_for_speed(speed_key):
    return int(SHIPMENT_SPEEDS.get(speed_key, SHIPMENT_SPEEDS["economy"])["seconds"])

def shipment_customs_risk(user, destination, item_key):
    base = SHIPMENT_CUSTOMS_RISK_INTERNATIONAL if is_international_city(destination) else SHIPMENT_CUSTOMS_RISK_DOMESTIC
    item = CONTRABAND.get(item_key, {})
    return max(1, int(base + int(item.get("risk", 0)) - influence_arrest_reduction(user)))

def shipment_cost(destination, amount, speed_key="economy"):
    route_fee = 500 if is_international_city(destination) else SHIPMENT_BASE_COST
    per_unit = 25 if is_international_city(destination) else SHIPMENT_COST_PER_UNIT
    multiplier = float(SHIPMENT_SPEEDS.get(speed_key, SHIPMENT_SPEEDS["economy"])["cost_multiplier"])
    return int((route_fee + per_unit * amount) * multiplier)

def shipment_speed_label(speed_key):
    return SHIPMENT_SPEEDS.get(speed_key, SHIPMENT_SPEEDS["economy"])["label"]

def format_duration(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h" if minutes == 0 else f"{hours}h {minutes}m"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"

def process_arrived_shipments(user):
    now = time.time()
    for shipment in Shipment.query.filter_by(user_id=user.id, status="in_transit").all():
        if safe_number(shipment.arrives_at) <= now:
            shipment.status = "arrived"
    db.session.commit()

def shipment_overview(user):
    process_arrived_shipments(user)
    rows = []
    for shipment in Shipment.query.filter_by(user_id=user.id).order_by(Shipment.created_at.desc()).limit(30).all():
        data = CONTRABAND.get(shipment.item_key, {"label": shipment.item_key})
        rows.append({
            "id": shipment.id,
            "label": data["label"],
            "quantity": int(safe_number(shipment.quantity)),
            "origin": shipment.origin,
            "destination": shipment.destination,
            "status": shipment.status,
            "remaining": max(0, int(safe_number(shipment.arrives_at) - time.time())),
            "can_collect": shipment.status == "arrived" and shipment.destination == user.location,
        })
    return rows



def ensure_user_properties(user):
    if not user or not user.id:
        return []
    existing = {row.property_key: row for row in UserProperty.query.filter_by(user_id=user.id).all()}
    changed = False
    for key in PROPERTY_TYPES.keys():
        if key not in existing:
            existing[key] = UserProperty(user_id=user.id, property_key=key, quantity=0)
            db.session.add(existing[key])
            changed = True
    if safe_number(getattr(user, "last_property_collect", 0)) <= 0:
        user.last_property_collect = time.time()
        changed = True
    if changed:
        db.session.commit()
    return [existing[key] for key in PROPERTY_TYPES.keys()]


def property_quantity(user, property_key):
    row = UserProperty.query.filter_by(user_id=user.id, property_key=property_key).first()
    return int(safe_number(row.quantity)) if row else 0


def property_income_per_hour(user):
    ensure_user_properties(user)
    total = 0
    for row in UserProperty.query.filter_by(user_id=user.id).all():
        data = PROPERTY_TYPES.get(row.property_key)
        if data:
            total += int(safe_number(row.quantity)) * int(data["income_per_hour"])
    return total


def property_prestige(user):
    ensure_user_properties(user)
    total = 0
    for row in UserProperty.query.filter_by(user_id=user.id).all():
        data = PROPERTY_TYPES.get(row.property_key)
        if data:
            total += int(safe_number(row.quantity)) * int(data.get("prestige", 0))
    return total


def property_collectable_income(user):
    hourly = property_income_per_hour(user)
    if hourly <= 0:
        return 0
    elapsed = max(0, int(time.time() - safe_number(getattr(user, "last_property_collect", 0))))
    return int(hourly * elapsed / 3600)


def property_overview(user):
    ensure_user_properties(user)
    rows = []
    for key, data in PROPERTY_TYPES.items():
        qty = property_quantity(user, key)
        rows.append({
            "key": key,
            "name": data["name"],
            "cost": int(data["cost"]),
            "income_per_hour": int(data["income_per_hour"]),
            "prestige": int(data.get("prestige", 0)),
            "quantity": qty,
            "total_income": qty * int(data["income_per_hour"]),
        })
    return rows


def casino_price_for_slot(slot_number):
    return int(CASINO_BASE_PRICE * (CASINO_PRICE_MULTIPLIER ** (slot_number - 1)))


def ensure_city_casinos():
    """Create a limited number of casino licenses per city."""
    changed = False
    for city in CITIES:
        max_slots = int(CITY_CASINOS.get(city, CASINOS_PER_CITY))
        for slot in range(1, max_slots + 1):
            casino = CityCasino.query.filter_by(city=city, slot_number=slot).first()
            if not casino:
                casino = CityCasino(
                    city=city,
                    slot_number=slot,
                    name=f"{city} Casino #{slot}",
                    owner_id=None,
                    heir_id=None,
                    price=casino_price_for_slot(slot),
                    vault=0,
                )
                db.session.add(casino)
                changed = True
    if changed:
        db.session.commit()


def settle_casino_estate(casino):
    """Transfer a dead owner's casino to a living heir, otherwise return it to the State."""
    if not casino or not casino.owner_id:
        return False
    if casino.owner and not casino.owner.is_dead:
        return False
    if casino.heir and not casino.heir.is_dead:
        casino.owner_id = casino.heir_id
        casino.heir_id = None
        return True
    casino.owner_id = None
    casino.heir_id = None
    casino.vault = 0
    return True

def casino_owner_status(casino):
    settle_casino_estate(casino)
    if not casino.owner_id:
        return "State Owned"
    if casino.owner and casino.owner.is_dead:
        if casino.heir and not casino.heir.is_dead:
            return f"Estate of {casino.owner.username} - Heir: {casino.heir.username}"
        return "State Controlled Estate"
    return f"Owned by {casino.owner.username}"


def casino_seller(casino):
    """Return (seller_user_or_none, seller_label). None means payment goes to the state."""
    settle_casino_estate(casino)
    if not casino.owner_id:
        return None, "the State"
    if casino.owner and casino.owner.is_dead:
        if casino.heir and not casino.heir.is_dead:
            return casino.heir, f"heir {casino.heir.username}"
        return None, "the State"
    return casino.owner, casino.owner.username


def casinos_for_city(city):
    ensure_city_casinos()
    return CityCasino.query.filter_by(city=city).order_by(CityCasino.slot_number.asc()).all()


def all_casinos():
    ensure_city_casinos()
    return CityCasino.query.order_by(CityCasino.city.asc(), CityCasino.slot_number.asc()).all()


def user_casinos(user):
    if not user or not user.id:
        return []
    ensure_city_casinos()
    return CityCasino.query.filter_by(owner_id=user.id).order_by(CityCasino.city.asc(), CityCasino.slot_number.asc()).all()


def has_influence(user, key):
    if not user:
        return False
    field = f"{key}_influence"
    return bool(getattr(user, field, False))


def influence_count(user):
    return sum(1 for key in INFLUENCE_TYPES if has_influence(user, key))


def influence_arrest_reduction(user):
    reduction = 0
    if has_influence(user, "police_chief"):
        reduction += 10
    if has_influence(user, "customs_officer"):
        reduction += 8
    return reduction


def influence_jail_multiplier(user):
    return 0.75 if has_influence(user, "judge") else 1.0


def influence_fine_multiplier(user):
    return 0.80 if has_influence(user, "judge") else 1.0


def influence_smuggling_bonus(user):
    return 10 if has_influence(user, "customs_officer") else 0


def influence_property_income_bonus(user):
    return 10 if has_influence(user, "mayor") else 0


def influence_casino_income_bonus(user):
    return 10 if has_influence(user, "mayor") else 0


def casino_house_income(city, amount):
    """Give a small house cut from lost bets to a random living casino owner in the city."""
    if amount <= 0:
        return
    city_casinos = [c for c in casinos_for_city(city) if c.owner and not c.owner.is_dead]
    if not city_casinos:
        return
    casino = random.choice(city_casinos)
    house_percent = CASINO_HOUSE_CUT_PERCENT + influence_casino_income_bonus(casino.owner)
    cut = max(1, amount * house_percent // 100)
    casino.vault = int(safe_number(casino.vault)) + cut


def power_score(user):
    money = safe_number(user.money)
    bank = safe_number(user.bank)
    exp = safe_number(user.exp)
    bodyguards = safe_number(user.bodyguards)
    vests = safe_number(user.bulletproof_vests)
    safehouses = safe_number(user.safehouses)
    lookouts = safe_number(user.lookouts)
    cars = total_vehicles(user)
    distilleries = total_distilleries(user)
    warehouse_stock = warehouse_used(user)
    bullets = safe_number(user.bullets)
    heists_successful = safe_number(getattr(user, "heists_successful", 0))
    properties_score = property_income_per_hour(user) // 2 + property_prestige(user)
    influence_score = influence_count(user) * 350
    wealth_score = (money + bank) // 10
    return (
        exp
        + wealth_score
        + bodyguards * 75
        + vests * 40
        + safehouses * 250
        + lookouts * 60
        + cars * 50
        + distilleries * 150
        + warehouse_stock * 2
        + bullets * 2
        + heists_successful * 120
        + properties_score
        + influence_score
    )


def bribe_chance(user):
    rank = user.rank or "Street Runner"
    chance = RANK_BRIBE_CHANCES.get(rank, 25)
    if has_influence(user, "police_chief"):
        chance += 15
    return min(chance, 95)


def bribe_cost(user):
    wealth_part = int((safe_number(user.money) + safe_number(user.bank)) * 0.08)
    return max(500, wealth_part)


def jail_remaining(user):
    return max(0, int(safe_number(user.jail_until) - time.time()))


def family_member_count(family):
    if not family:
        return 0
    return User.query.filter_by(family_id=family.id).count()


def family_power(family):
    if not family:
        return 0
    members = User.query.filter_by(family_id=family.id).all()
    return sum(power_score(member) for member in members) + int(safe_number(family.bank)) // 5


def family_bonus(user, key):
    if not user or not user.family_id:
        return 0
    members = family_member_count(user.family)
    if key == "crime_income":
        return min(members * 2, 10)
    if key == "smuggling":
        return min(members * 2, 10)
    if key == "protection":
        return min(members * 1, 8)
    return 0


def ensure_city_territories():
    changed = False
    for city in CITIES:
        territory = CityTerritory.query.filter_by(city=city).first()
        if not territory:
            territory = CityTerritory(city=city, family_id=None, last_tax_collect=time.time(), last_war_at=0.0, protected_until=0.0)
            db.session.add(territory)
            changed = True
    if changed:
        db.session.commit()


def all_territories():
    ensure_city_territories()
    return CityTerritory.query.order_by(CityTerritory.city.asc()).all()


def territory_for_city(city):
    ensure_city_territories()
    return CityTerritory.query.filter_by(city=city).first()


def territory_tax_ready(territory):
    if not territory or not territory.family_id:
        return 0
    data = CITY_TERRITORY_DATA.get(territory.city, {"tax_per_hour": 25000})
    elapsed = max(0, int(time.time() - safe_number(territory.last_tax_collect)))
    hours = elapsed // 3600
    return int(hours * data["tax_per_hour"])


def family_territory_count(family):
    if not family:
        return 0
    ensure_city_territories()
    return CityTerritory.query.filter_by(family_id=family.id).count()


def family_territory_tax_per_hour(family):
    if not family:
        return 0
    ensure_city_territories()
    return sum(CITY_TERRITORY_DATA.get(t.city, {"tax_per_hour": 25000})["tax_per_hour"] for t in CityTerritory.query.filter_by(family_id=family.id).all())


def territory_bonus_text(city):
    return CITY_TERRITORY_DATA.get(city, {"bonus": "No special bonus"})["bonus"]


def war_attack_score(family):
    if not family:
        return 0
    return family_power(family) + int(safe_number(family.bank)) // 2 + family_territory_count(family) * 2500


def war_defense_score(territory):
    if not territory or not territory.family:
        return 5000
    return war_attack_score(territory.family) + 2500


def heist_success_chance(user, plan):
    family_edge = family_bonus(user, "crime_income")
    rank_edge = rank_bonus(user, "attack") // 2
    vehicle_edge = vehicle_bonus(user) // 3
    lookout_edge = lookout_arrest_reduction(user)
    chance = int(plan["base_success"] + family_edge + rank_edge + vehicle_edge + lookout_edge)
    return max(5, min(chance, 92))


def heist_cooldown_remaining(user):
    return max(0, int(HEIST_COOLDOWN - (time.time() - safe_number(getattr(user, "last_heist", 0)))))


def heist_plan_rows(user):
    rows = []
    for key, plan in HEIST_PLANS.items():
        row = dict(plan)
        row["key"] = key
        row["success_chance"] = heist_success_chance(user, plan)
        row["ready"] = power_score(user) >= plan["min_power"] and safe_number(user.bullets) >= plan["bullets"]
        rows.append(row)
    return rows


def migrate_database():
    """Small SQLite migration helper so old databases do not crash after updates."""
    db_path = os.path.join(app.instance_path, "peaky_blinders.db")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(user)")
    columns = {row[1] for row in cur.fetchall()}
    migrations = {
        "cars": "ALTER TABLE user ADD COLUMN cars INTEGER DEFAULT 0",
        "distilleries": "ALTER TABLE user ADD COLUMN distilleries INTEGER DEFAULT 0",
        "last_collect": "ALTER TABLE user ADD COLUMN last_collect FLOAT DEFAULT 0.0",
        "jail_until": "ALTER TABLE user ADD COLUMN jail_until FLOAT DEFAULT 0.0",
        "arrests": "ALTER TABLE user ADD COLUMN arrests INTEGER DEFAULT 0",
        "bribe_available_at": "ALTER TABLE user ADD COLUMN bribe_available_at FLOAT DEFAULT 0.0",
        "last_bribe_attempt": "ALTER TABLE user ADD COLUMN last_bribe_attempt FLOAT DEFAULT 0.0",
        "last_heist": "ALTER TABLE user ADD COLUMN last_heist FLOAT DEFAULT 0.0",
        "heists_successful": "ALTER TABLE user ADD COLUMN heists_successful INTEGER DEFAULT 0",
        "casino_license": "ALTER TABLE user ADD COLUMN casino_license BOOLEAN DEFAULT 0",
        "last_property_collect": "ALTER TABLE user ADD COLUMN last_property_collect FLOAT DEFAULT 0.0",
        "police_chief_influence": "ALTER TABLE user ADD COLUMN police_chief_influence BOOLEAN DEFAULT 0",
        "judge_influence": "ALTER TABLE user ADD COLUMN judge_influence BOOLEAN DEFAULT 0",
        "mayor_influence": "ALTER TABLE user ADD COLUMN mayor_influence BOOLEAN DEFAULT 0",
        "customs_officer_influence": "ALTER TABLE user ADD COLUMN customs_officer_influence BOOLEAN DEFAULT 0",
        "bulletproof_vests": "ALTER TABLE user ADD COLUMN bulletproof_vests INTEGER DEFAULT 0",
        "safehouses": "ALTER TABLE user ADD COLUMN safehouses INTEGER DEFAULT 0",
        "lookouts": "ALTER TABLE user ADD COLUMN lookouts INTEGER DEFAULT 0",
        "warehouse_level": "ALTER TABLE user ADD COLUMN warehouse_level INTEGER DEFAULT 0",
        "family_id": "ALTER TABLE user ADD COLUMN family_id INTEGER DEFAULT NULL",
        "family_role": "ALTER TABLE user ADD COLUMN family_role TEXT DEFAULT 'Solo'",
    }
    for column, sql in migrations.items():
        if column not in columns:
            cur.execute(sql)

    # Fix old rows that may contain NULL values from earlier versions.
    defaults = {
        "money": 500,
        "bank": 0,
        "exp": 0,
        "rank": "Street Runner",
        "location": "Birmingham",
        "gin": 0,
        "bullets": 0,
        "bodyguards": 0,
        "bulletproof_vests": 0,
        "safehouses": 0,
        "lookouts": 0,
        "warehouse_level": 0,
        "family_role": "Solo",
        "cars": 0,
        "distilleries": 0,
        "last_crime": 0.0,
        "last_collect": 0.0,
        "is_dead": 0,
        "jail_until": 0.0,
        "arrests": 0,
        "bribe_available_at": 0.0,
        "last_bribe_attempt": 0.0,
        "last_heist": 0.0,
        "heists_successful": 0,
        "casino_license": 0,
        "last_property_collect": 0.0,
        "police_chief_influence": 0,
        "judge_influence": 0,
        "mayor_influence": 0,
        "customs_officer_influence": 0,
    }
    cur.execute("PRAGMA table_info(user)")
    columns = {row[1] for row in cur.fetchall()}
    for column, default in defaults.items():
        if column in columns:
            if isinstance(default, str):
                cur.execute(f"UPDATE user SET {column} = ? WHERE {column} IS NULL", (default,))
            else:
                cur.execute(f"UPDATE user SET {column} = ? WHERE {column} IS NULL", (default,))

    # CityBusiness table migrations for city-based distillery stock.
    cur.execute("PRAGMA table_info(city_business)")
    city_business_columns = {row[1] for row in cur.fetchall()}
    if "pending_gin" not in city_business_columns:
        cur.execute("ALTER TABLE city_business ADD COLUMN pending_gin INTEGER DEFAULT 0")
    cur.execute("UPDATE city_business SET pending_gin = 0 WHERE pending_gin IS NULL")
    cur.execute("UPDATE city_business SET last_collect = 0.0 WHERE last_collect IS NULL")
    cur.execute("UPDATE city_business SET distilleries = 0 WHERE distilleries IS NULL")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS city_territory (
            id INTEGER PRIMARY KEY,
            city VARCHAR(40) UNIQUE NOT NULL,
            family_id INTEGER DEFAULT NULL,
            last_tax_collect FLOAT DEFAULT 0.0,
            last_war_at FLOAT DEFAULT 0.0,
            protected_until FLOAT DEFAULT 0.0,
            FOREIGN KEY(family_id) REFERENCES family(id)
        )
    """)

    conn.commit()
    conn.close()


HTML_UI = """
<!DOCTYPE html>
<html>
<head>
<title>{{ game_name }}</title>
<style>
:root { --bg:#080808; --panel:rgba(20,20,20,.92); --gold:#d6a85f; --gold2:#9b6a32; --wine:#5c1010; --text:#e7dbc8; --muted:#a79a88; --green:#5cff73; --blue:#62b7ff; --red:#ff5555; }
*{box-sizing:border-box} body{margin:0;min-height:100vh;background:radial-gradient(circle at top left,rgba(214,168,95,.12),transparent 28%),linear-gradient(rgba(0,0,0,.78),rgba(0,0,0,.95)),url('/static/login_bg.jpg') center/cover fixed;color:var(--text);font-family:Georgia,'Times New Roman',serif} a{color:inherit}
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:30px}.login-card{width:430px;background:rgba(8,8,8,.91);border:2px solid var(--gold2);padding:35px;box-shadow:0 0 45px #000;text-align:center;border-radius:18px}.login-card h1{color:var(--gold);letter-spacing:5px;font-size:38px;margin-bottom:5px}.login-card p{color:#aaa;margin-bottom:25px}
.app-shell{min-height:100vh;display:grid;grid-template-columns:260px minmax(0,1fr);align-items:start}.sidebar{position:relative;top:auto;min-height:100vh;height:auto;background:linear-gradient(180deg,rgba(10,10,10,.98),rgba(30,12,12,.96));border-right:1px solid rgba(214,168,95,.35);padding:22px 16px;overflow:visible;box-shadow:10px 0 35px rgba(0,0,0,.35)}.brand{padding:10px 10px 22px;border-bottom:1px solid rgba(214,168,95,.25);margin-bottom:16px}.brand-title{color:var(--gold);font-size:24px;letter-spacing:3px;font-weight:bold;line-height:1.1}.brand-sub{color:var(--muted);font-size:12px;letter-spacing:1px;margin-top:7px}.nav{display:flex;flex-direction:column;gap:7px;margin:0}.nav a{background:rgba(255,255,255,.035);color:var(--text);border:1px solid rgba(214,168,95,.16);padding:11px 12px;text-decoration:none;font-weight:bold;border-radius:12px;display:block;transition:.18s ease}.nav a:hover{background:linear-gradient(90deg,rgba(92,16,16,.9),rgba(92,16,16,.18));border-color:var(--gold);transform:translateX(3px)}
.content-wrap{min-width:0;padding:24px}.topbar{background:linear-gradient(135deg,rgba(19,19,19,.95),rgba(36,21,12,.88));border:1px solid rgba(214,168,95,.28);border-radius:18px;padding:18px 20px;box-shadow:0 15px 45px rgba(0,0,0,.35);display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:18px}.hero-title{color:var(--gold);font-size:28px;letter-spacing:4px;font-weight:bold}.player-strip{display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-end;color:var(--muted);font-size:14px}.pill{border:1px solid rgba(214,168,95,.22);background:rgba(0,0,0,.25);padding:7px 10px;border-radius:999px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 18px}.stat-card{background:var(--panel);border:1px solid rgba(214,168,95,.22);border-radius:16px;padding:14px;box-shadow:0 12px 30px rgba(0,0,0,.25)}.stat-card small{color:var(--muted);display:block;margin-bottom:7px;text-transform:uppercase;letter-spacing:1px}.stat-card b{color:var(--gold);font-size:20px}.box{background:rgba(13,13,13,.88);border:1px solid rgba(214,168,95,.22);padding:20px;margin-top:18px;box-shadow:0 0 22px #000;border-radius:18px;overflow-x:auto}.dashboard-hero{display:grid;grid-template-columns:1.3fr .7fr;gap:16px;margin-bottom:18px}.panel{background:var(--panel);border:1px solid rgba(214,168,95,.22);border-radius:18px;padding:18px;box-shadow:0 14px 35px rgba(0,0,0,.28)}.panel h2,.box h2{color:var(--gold);margin-top:0;letter-spacing:1px}.quick-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
.input{width:100%;padding:11px;margin:8px 0 14px;background:#111;border:1px solid var(--gold2);color:#fff;border-radius:10px}.msg{background:rgba(70,15,15,.75);border-left:5px solid #c40000;padding:12px;margin:0 0 15px;color:#ff9999;border-radius:10px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:15px}.card{background:linear-gradient(145deg,rgba(17,17,17,.96),rgba(32,24,16,.88));border:1px solid rgba(214,168,95,.20);padding:16px;border-radius:16px;box-shadow:0 10px 28px rgba(0,0,0,.22)}.card h3{color:var(--gold);margin-top:0}.btn{background:linear-gradient(#721818,#260707);color:#fff;border:1px solid var(--gold2);padding:10px 14px;text-decoration:none;font-weight:bold;cursor:pointer;display:inline-block;margin:3px;border-radius:10px}.btn:hover{background:linear-gradient(#9b1b1b,#3a0909)}table{width:100%;border-collapse:collapse;background:rgba(0,0,0,.18);border-radius:14px;overflow:hidden}th,td{border:1px solid rgba(214,168,95,.16);padding:10px}th{background:rgba(26,18,12,.95);color:var(--gold)}.gold{color:var(--gold)}.good{color:var(--green)}.blue{color:var(--blue)}.red{color:var(--red)}.muted{color:var(--muted)}

.garage-hero{display:grid;grid-template-columns:1.15fr .85fr;gap:16px;margin-bottom:18px}
.showroom-banner{min-height:220px;border-radius:20px;border:1px solid rgba(214,168,95,.32);background:linear-gradient(135deg,rgba(15,15,15,.88),rgba(92,16,16,.34)),radial-gradient(circle at 80% 20%,rgba(214,168,95,.22),transparent 28%);padding:24px;display:flex;flex-direction:column;justify-content:end;box-shadow:0 18px 45px rgba(0,0,0,.35)}
.showroom-banner h2{font-size:34px;letter-spacing:3px;margin:0;color:var(--gold)}
.showroom-banner p{max-width:650px;color:var(--muted);font-size:15px}
.garage-kpi{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.garage-kpi .stat-card{min-height:104px}
.vehicle-section{margin-top:22px}.vehicle-section-title{color:var(--gold);letter-spacing:2px;text-transform:uppercase;border-bottom:1px solid rgba(214,168,95,.22);padding-bottom:8px;margin-bottom:14px}
.vehicle-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:16px}
.vehicle-card{position:relative;overflow:hidden;background:linear-gradient(145deg,rgba(15,15,15,.96),rgba(34,23,14,.9));border:1px solid rgba(214,168,95,.28);border-radius:18px;box-shadow:0 14px 34px rgba(0,0,0,.32);transition:.18s ease}
.vehicle-card:hover{transform:translateY(-3px);border-color:var(--gold);box-shadow:0 20px 46px rgba(0,0,0,.42)}
.vehicle-image{height:180px;border-bottom:1px solid rgba(214,168,95,.20);background:linear-gradient(135deg,var(--vehicle-tone),#101010);position:relative;overflow:hidden;display:flex;align-items:center;justify-content:center}
.vehicle-image:before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.22),transparent 20%),linear-gradient(rgba(0,0,0,.05),rgba(0,0,0,.58))}
.vehicle-silhouette{position:relative;z-index:1;text-align:center;color:rgba(231,219,200,.92);letter-spacing:3px;font-weight:bold;text-shadow:0 3px 14px rgba(0,0,0,.9)}
.vehicle-silhouette .year{font-size:18px;color:var(--gold)}.vehicle-silhouette .icon{font-size:28px;margin-top:8px}
.vehicle-body{padding:16px}.vehicle-body h3{margin:0 0 10px;color:var(--gold)}
.vehicle-meta{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:12px 0}.vehicle-meta div{background:rgba(0,0,0,.25);border:1px solid rgba(214,168,95,.14);border-radius:12px;padding:10px}.vehicle-meta small{display:block;color:var(--muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px;font-size:10px}.vehicle-meta b{color:var(--text)}
.garage-city-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:15px}.garage-city-card{background:linear-gradient(145deg,rgba(17,17,17,.96),rgba(24,18,12,.9));border:1px solid rgba(214,168,95,.22);border-radius:18px;padding:16px}.garage-city-card h3{margin-top:0;color:var(--gold)}.owned-list{line-height:1.8;color:var(--text)}
@media(max-width:900px){.garage-hero{grid-template-columns:1fr}.garage-kpi{grid-template-columns:1fr}.vehicle-image{height:150px}}

@media(max-width:900px){.app-shell{grid-template-columns:1fr}.sidebar{position:relative;min-height:auto;height:auto;overflow:visible}.content-wrap{padding:14px}.topbar,.dashboard-hero{grid-template-columns:1fr;flex-direction:column;align-items:flex-start}.nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr))}}
</style>
</head>
<body>

{% if not user %}
<div class="login-wrap">
    <div class="login-card">
        <h1>PEAKY BLINDERS</h1>
        <p>By Order of the Shelby Family</p>
        {% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
        <form action="/login_action" method="post">
            Name:<br><input class="input" name="username" required maxlength="80">
            Password:<br><input class="input" type="password" name="password" required>
            <button class="btn" name="action" value="login">Login</button>
            <button class="btn" name="action" value="register">Register</button>
        </form>
    </div>
</div>
{% else %}

<div class="app-shell">
    <aside class="sidebar">
        <div class="brand"><div class="brand-title">PEAKY<br>EMPIRE</div><div class="brand-sub">By Order of the Shelby Family</div></div>
        <div class="nav">
            <a href="/dashboard">🏠 Dashboard</a><a href="/">⚡ Crimes</a><a href="/bank">🏦 Bank</a><a href="/market">🍾 Smuggling</a><a href="/warehouse">🏚 Warehouse</a><a href="/assets">🏭 Businesses</a><a href="/properties">🏛 Properties</a><a href="/garage">🚗 Garage</a><a href="/casino">🃏 Casinos</a><a href="/licenses">🎫 Licenses</a><a href="/influence">🏛 Influence</a><a href="/family">👪 Family</a><a href="/territories">⚔️ Territories</a><a href="/bullets">🔫 Weapons</a><a href="/protection">🛡️ Protection</a><a href="/heists">💼 Heists</a><a href="/jail">🚔 Jail</a><a href="/ranking">🏆 Rankings</a><a href="/logout">🚪 Logout</a>
        </div>
    </aside>
    <main class="content-wrap">
        <div class="topbar"><div><div class="hero-title">PEAKY BLINDERS EMPIRE</div><div class="muted">{{ user.username }} · {{ user.rank }} · {{ user.location }}</div></div><div class="player-strip"><span class="pill">👪 {% if user.family %}{{ user.family.name }}{% else %}Solo{% endif %}</span><span class="pill">⚡ {{ power_score(user) }}</span><span class="pill">🏴 {{ family_territory_count(user.family) if user.family else 0 }} territories</span><span class="pill">🎫 {% if user.casino_license %}Licensed{% else %}No License{% endif %}</span></div></div>
        <div class="stats"><div class="stat-card"><small>💰 Cash</small><b class="good">${{ user.money }}</b></div><div class="stat-card"><small>🏦 Bank</small><b class="blue">${{ user.bank }}</b></div><div class="stat-card"><small>💎 Empire Value</small><b>${{ empire_value(user) }}</b></div><div class="stat-card"><small>🏚 Warehouse</small><b>{{ warehouse_used(user) }}/{{ warehouse_capacity(user) }}</b></div><div class="stat-card"><small>🏛 Property Income</small><b>${{ property_income_per_hour(user) }}/h</b></div><div class="stat-card"><small>🏭 Distilleries</small><b>{{ total_distilleries(user) }}</b></div></div>
        {% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
    <div class="box">

    {% if page == "dashboard" %}
        <div class="dashboard-hero"><div class="panel"><h2>🏠 Empire Dashboard</h2><p>Welkom terug, <b class="gold">{{ user.username }}</b>. Beheer je imperium vanuit één command center.</p><div class="quick-actions"><a class="btn" href="/">⚡ Commit Crime</a><a class="btn" href="/market">🍾 Smuggling Market</a><a class="btn" href="/properties">🏛 Collect Properties</a><a class="btn" href="/casino">🃏 Casino Vaults</a><a class="btn" href="/territories">⚔️ Territory Command</a></div></div><div class="panel"><h2>📍 Current Status</h2><p>Location: <b class="gold">{{ user.location }}</b></p><p>Family: <b class="gold">{% if user.family %}{{ user.family.name }}{% else %}None{% endif %}</b></p><p>Influence: <b class="gold">{{ influence_count(user) }}/4</b></p><p>Arrests: <b class="red">{{ user.arrests }}</b></p></div></div>
        <div class="grid"><div class="card"><h3>📦 Active Cargo</h3>{% set shipments = active_shipments(user) %}{% if shipments %}{% for shipment in shipments[:5] %}<p><b>{{ shipment.origin }}</b> → <b>{{ shipment.destination }}</b><br>{{ shipment.quantity }} {{ shipment.item_key }} · ETA {{ ((shipment.arrives_at - now_time) | int) if shipment.arrives_at > now_time else 0 }}s</p>{% endfor %}{% else %}<p class="muted">No active cargo shipments.</p>{% endif %}</div><div class="card"><h3>🏛 Passive Income</h3><p>Properties: <b class="good">${{ property_income_per_hour(user) }}/hour</b></p><p>Collectable now: <b class="gold">${{ property_collectable_income(user) }}</b></p><p>Territory tax: <b class="good">${{ family_territory_tax_per_hour(user.family) if user.family else 0 }}/hour</b></p></div><div class="card"><h3>🃏 Casino Empire</h3><p>Owned casinos: <b class="gold">{{ user_casinos(user)|length }}</b></p><p>Total vaults: <b class="good">${{ casino_vault_total(user) }}</b></p><p>License: {% if user.casino_license %}<b class="good">Owned</b>{% else %}<b class="red">Required</b>{% endif %}</p></div><div class="card"><h3>🏴 Territories</h3><p>Controlled cities: <b class="gold">{{ family_territory_count(user.family) if user.family else 0 }}</b></p><p>Family tax: <b class="good">${{ family_territory_tax_per_hour(user.family) if user.family else 0 }}/hour</b></p><a class="btn" href="/territories">Open Command</a></div></div>
    {% endif %}

    {% if page == "crime" %}
        <h2>⚡ Street Crimes</h2>
        <p>Commit crimes for cash and EXP. Cooldown: {{ cooldown }} seconds. Your rank gives +{{ rank_bonus(user, 'crime_chance') }}% success chance and +{{ rank_bonus(user, 'crime_income') }}% cash.</p>
        <p>Your selected local vehicle adds its own crime bonus. If the crime fails, there is a small <b class="red">3%</b> chance the vehicle is discovered and lost.</p>
        <p class="red">Police risk: Pickpocket 5%, Store Robbery 12%, Bank Transport 25%.</p>
        <div class="grid">
            <div class="card">
                <h3>Pickpocket</h3><p>Low risk, small reward.</p>
                <form action="/crime_action" method="post">
                    Vehicle from {{ user.location }}:<br>
                    <select class="input" name="vehicle_key">
                        <option value="">No vehicle</option>
                        {% for item in local_vehicles %}<option value="{{ item.vehicle.key }}">{{ item.vehicle.year }} {{ item.vehicle.name }} (+{{ item.vehicle.bonus }}%) x{{ item.quantity }}</option>{% endfor %}
                    </select>
                    <button class="btn" name="crime" value="pickpocket">Start</button>
                </form>
            </div>
            <div class="card">
                <h3>Store Robbery</h3><p>Medium risk, good reward.</p>
                <form action="/crime_action" method="post">
                    Vehicle from {{ user.location }}:<br>
                    <select class="input" name="vehicle_key">
                        <option value="">No vehicle</option>
                        {% for item in local_vehicles %}<option value="{{ item.vehicle.key }}">{{ item.vehicle.year }} {{ item.vehicle.name }} (+{{ item.vehicle.bonus }}%) x{{ item.quantity }}</option>{% endfor %}
                    </select>
                    <button class="btn" name="crime" value="robbery">Start</button>
                </form>
            </div>
            <div class="card">
                <h3>Bank Transport</h3><p>High risk, high reward.</p>
                <form action="/crime_action" method="post">
                    Vehicle from {{ user.location }}:<br>
                    <select class="input" name="vehicle_key">
                        <option value="">No vehicle</option>
                        {% for item in local_vehicles %}<option value="{{ item.vehicle.key }}">{{ item.vehicle.year }} {{ item.vehicle.name }} (+{{ item.vehicle.bonus }}%) x{{ item.quantity }}</option>{% endfor %}
                    </select>
                    <button class="btn" name="crime" value="truck">Start</button>
                </form>
            </div>
        </div>
    {% endif %}

    {% if page == "bank" %}
        <h2>🏦 Shelby Bank</h2>
        <form action="/bank_action" method="post">
            Amount:<br><input class="input" type="number" name="amount" min="1" required>
            <button class="btn" name="action" value="deposit">Deposit</button>
            <button class="btn" name="action" value="withdraw">Withdraw</button>
        </form>
    {% endif %}

    {% if page == "market" %}
        <h2>🍾 Smuggling Market</h2>
        <p>Buy low, sell high, or send stock ahead to another city. Goods are stored in your warehouse. Your rank gives +{{ rank_bonus(user, 'smuggling') }}% selling bonus.</p>
        <p>Warehouse space: <b class="gold">{{ warehouse_used(user) }}/{{ warehouse_capacity(user) }}</b> | International routes: <b class="gold">Dublin, Glasgow, Paris, Amsterdam, Havana</b></p>

        <table>
            <tr>
                <th>Goods</th>
                <th>Price in {{ user.location }}</th>
                <th>Owned</th>
                <th>Police Risk</th>
                <th>Buy</th>
                <th>Sell</th>
                <th>Send Stock</th>
            </tr>
            {% for item in contraband %}
            <tr>
                <td>{{ item.label }}</td>
                <td class="gold">${{ item.price }}</td>
                <td>{{ item.quantity }}</td>
                <td class="red">+{{ item.risk }}%</td>
                <td>
                    <form action="/market_action" method="post">
                        <input type="hidden" name="item_key" value="{{ item.key }}">
                        <input class="input" style="margin:0; width:90px;" type="number" name="amount" min="1" value="1">
                        <button class="btn" name="action" value="buy">Buy</button>
                    </form>
                </td>
                <td>
                    <form action="/market_action" method="post">
                        <input type="hidden" name="item_key" value="{{ item.key }}">
                        <input class="input" style="margin:0; width:90px;" type="number" name="amount" min="1" value="1">
                        <button class="btn" name="action" value="sell">Sell</button>
                        <button class="btn" name="action" value="sell_all">Sell All</button>
                    </form>
                </td>
                <td>
                    <form action="/shipment_action" method="post">
                        <input type="hidden" name="item_key" value="{{ item.key }}">
                        <input class="input" style="margin:0; width:80px;" type="number" name="amount" min="1" value="1">
                        <select class="input" style="margin:0;" name="destination">
                            {% for city in cities %}<option value="{{ city }}" {% if city == user.location %}disabled{% endif %}>{{ city }}{% if is_international_city(city) %} 🌍{% endif %}</option>{% endfor %}
                        </select>
                        <button class="btn" name="action" value="send">Send</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>

        <hr><h2>📦 Stock Shipments</h2>
        <p>Send goods to another city without travelling. Economy cargo takes about 1 hour. Paying more unlocks faster cargo. Self-smuggling by travelling yourself is free, but carrying stock still has police/customs risk.</p>
        <table>
            <tr><th>Goods</th><th>Route</th><th>Status</th><th>Time</th><th>Action</th></tr>
            {% for shipment in shipments %}
            <tr>
                <td>{{ shipment.quantity }}x {{ shipment.label }}</td>
                <td>{{ shipment.origin }} → {{ shipment.destination }}</td>
                <td>{% if shipment.status == 'arrived' %}<span class="good">Arrived</span>{% elif shipment.status == 'seized' %}<span class="red">Seized</span>{% else %}<span class="gold">In transit</span>{% endif %}</td>
                <td>{% if shipment.remaining > 0 %}{{ format_duration(shipment.remaining) }}{% else %}-{% endif %}</td>
                <td>
                    {% if shipment.can_collect %}
                    <form action="/shipment_action" method="post">
                        <input type="hidden" name="shipment_id" value="{{ shipment.id }}">
                        <button class="btn" name="action" value="collect">Collect Shipment</button>
                    </form>
                    {% elif shipment.status == 'arrived' %}
                        <span class="red">Travel to {{ shipment.destination }}</span>
                    {% else %}-{% endif %}
                </td>
            </tr>
            {% endfor %}
            {% if shipments|length == 0 %}<tr><td colspan="5" style="color:#777;">No shipments yet.</td></tr>{% endif %}
        </table>

        <hr><h2>🚂 Self-Smuggling Travel</h2><p>Travelling yourself requires a paid ticket. If you carry warehouse stock, police/customs can still catch you.</p>
        <form action="/travel_action" method="post">
            <select class="input" name="destination">
            {% for city in cities %}<option value="{{ city }}" {% if city == user.location %}disabled{% endif %}>{{ city }} - ${{ travel_cost_to(city) }}{% if is_international_city(city) %} 🌍{% endif %}</option>{% endfor %}
            </select>
            <button class="btn">Buy Ticket & Travel</button>
        </form>
    {% endif %}

    {% if page == "warehouse" %}
        <h2>🏚 Warehouse</h2>
        <p>Your warehouse stores smuggling goods. Upgrade it to carry more stock and make bigger trades between cities.</p>

        <div class="grid">
            <div class="card">
                <h3>{{ warehouse_info.name }}</h3>
                <p>Capacity: <b class="gold">{{ warehouse_used(user) }}/{{ warehouse_capacity(user) }}</b></p>
                {% if next_upgrade %}
                    <p>Next upgrade: <b class="gold">{{ next_upgrade.name }}</b></p>
                    <p>Cost: <b class="good">${{ next_upgrade.upgrade_cost }}</b></p>
                    <form action="/warehouse_action" method="post">
                        <button class="btn" name="action" value="upgrade">Upgrade Warehouse</button>
                    </form>
                {% else %}
                    <p class="good">Maximum warehouse level reached.</p>
                {% endif %}
            </div>

            <div class="card">
                <h3>Smuggling Strategy</h3>
                <p>Check city prices, buy cheap goods, travel, and sell them where prices are higher.</p>
                <p>Riskier goods like Weapons have higher police risk but can earn much more.</p>
            </div>
        </div>

        <hr>
        <h2>Current Stock</h2>
        <table>
            <tr><th>Goods</th><th>Quantity</th><th>Current City Price</th><th>Total Value Here</th><th>Risk</th></tr>
            {% for item in contraband %}
            <tr>
                <td>{{ item.label }}</td>
                <td>{{ item.quantity }}</td>
                <td class="gold">${{ item.price }}</td>
                <td class="good">${{ item.quantity * item.price }}</td>
                <td class="red">+{{ item.risk }}%</td>
            </tr>
            {% endfor %}
        </table>
    {% endif %}


    {% if page == "family" %}
        <h2>👪 Mafia Family</h2>
        {% if user.family %}
            <div class="grid">
                <div class="card">
                    <h3>{{ user.family.name }}</h3>
                    <p>Your role: <b class="gold">{{ user.family_role }}</b></p>
                    <p>Members: <b class="gold">{{ family_member_count(user.family) }}</b></p>
                    <p>Family power: <b class="gold">{{ family_power(user.family) }}</b></p>
                    <p>Family bank: <b class="good">${{ user.family.bank }}</b></p>
                </div>
                <div class="card">
                    <h3>Family Bonuses</h3>
                    <p>Crime income bonus: <b class="gold">+{{ family_bonus(user, 'crime_income') }}%</b></p>
                    <p>Smuggling bonus: <b class="gold">+{{ family_bonus(user, 'smuggling') }}%</b></p>
                    <p>Protection bonus: <b class="gold">+{{ family_bonus(user, 'protection') }}%</b></p>
                    <p>Bonuses grow with the number of members, but are capped for balance.</p>
                </div>
                <div class="card">
                    <h3>Family Bank</h3>
                    <form action="/family_action" method="post">
                        Amount:<br><input class="input" type="number" name="amount" min="1" required>
                        <button class="btn" name="action" value="deposit">Deposit</button>
                        {% if user.family_role in ["Boss", "Underboss"] %}
                            <button class="btn" name="action" value="withdraw">Withdraw</button>
                        {% endif %}
                    </form>
                </div>
                <div class="card">
                    <h3>Leave Family</h3>
                    <p>Bosses cannot leave while other members remain.</p>
                    <form action="/family_action" method="post">
                        <button class="btn" name="action" value="leave">Leave Family</button>
                    </form>
                </div>
            </div>

            <hr>
            <h2>Members</h2>
            <table>
                <tr><th>Name</th><th>Role</th><th>Rank</th><th>Power</th><th>Wealth</th></tr>
                {% for member in family_members %}
                <tr>
                    <td>{{ member.username }}</td>
                    <td>{{ member.family_role }}</td>
                    <td>{{ member.rank }}</td>
                    <td class="gold">{{ power_score(member) }}</td>
                    <td class="good">${{ member.money + member.bank }}</td>
                </tr>
                {% endfor %}
            </table>
        {% else %}
            <div class="grid">
                <div class="card">
                    <h3>Create Family</h3>
                    <p>Cost: <b class="good">$50,000</b></p>
                    <p>You become the Boss and can build a crew around your empire.</p>
                    <form action="/family_action" method="post">
                        Family name:<br><input class="input" name="family_name" required maxlength="80">
                        <button class="btn" name="action" value="create">Create Family</button>
                    </form>
                </div>
                <div class="card">
                    <h3>Join Family</h3>
                    <p>Enter the exact family name to join as an Associate.</p>
                    <form action="/family_action" method="post">
                        Family name:<br><input class="input" name="family_name" required maxlength="80">
                        <button class="btn" name="action" value="join">Join Family</button>
                    </form>
                </div>
            </div>
        {% endif %}

        <hr>
        <h2>Family Rankings</h2>
        <table>
            <tr><th>#</th><th>Family</th><th>Boss</th><th>Members</th><th>Bank</th><th>Power</th></tr>
            {% for fam in families %}
            <tr>
                <td>{{ loop.index }}</td>
                <td>{{ fam.name }}</td>
                <td>{{ fam.boss.username if fam.boss else 'Unknown' }}</td>
                <td>{{ family_member_count(fam) }}</td>
                <td class="good">${{ fam.bank }}</td>
                <td class="gold">{{ family_power(fam) }}</td>
            </tr>
            {% endfor %}
            {% if families|length == 0 %}
            <tr><td colspan="6" style="color:#777;">No families created yet.</td></tr>
            {% endif %}
        </table>
    {% endif %}

    {% if page == "assets" %}
        <h2>🏭 Shelby Businesses</h2>
        <p>Distilleries are tied to the city where you buy them. You can only collect gin production while you are physically in that city.</p>
        <p>Warehouse space: <b class="gold">{{ warehouse_used(user) }}/{{ warehouse_capacity(user) }}</b> | Free space: <b class="good">{{ warehouse_free_space(user) }}</b> | Total gin waiting in all distilleries: <b class="gold">{{ total_ready_gin(user) }}</b></p>

        <div class="grid">
            <div class="card">
                <h3>Buy Distillery in {{ user.location }}</h3>
                <p>Price: $2500</p>
                <form action="/asset_action" method="post">
                    <button class="btn" name="action" value="buy_distillery">Buy here</button>
                </form>
            </div>

            <div class="card">
                <h3>Collect in {{ user.location }}</h3>
                <p>Ready in this city: <b class="gold">{{ business_ready_gin(current_business) }}</b> gin.</p>
                <p>You can only collect up to your remaining warehouse space. Any extra gin stays waiting inside the local distillery.</p>
                <form action="/collect_action" method="post">
                    <button class="btn">Collect local gin</button>
                </form>
            </div>
        </div>

        <hr>
        <h2>🌍 Business Overview by City</h2>
        <table>
            <tr>
                <th>City</th>
                <th>Distilleries</th>
                <th>Ready to Collect</th>
                <th>Status</th>
                <th>Production</th>
            </tr>
            {% for business in businesses %}
            <tr>
                <td>{{ business.city }}</td>
                <td>{{ business.distilleries }}</td>
                <td class="gold">{{ business_ready_gin(business) }} gin</td>
                <td>{% if business.city == user.location %}<span class="good">You are here - collect allowed</span>{% else %}<span class="red">Travel here to collect</span>{% endif %}</td>
                <td>{{ business.distilleries }} gin per minute</td>
            </tr>
            {% endfor %}
        </table>
    {% endif %}

    {% if page == "garage" %}
        <div class="garage-hero">
            <div class="showroom-banner">
                <h2>🚗 Shelby Motor Company</h2>
                <p>Luxury transport, street runners and legendary oldtimers. Vehicles are stored per city and only local vehicles can be used from your current location.</p>
                <div>
                    <span class="pill">📍 Showroom: {{ user.location }}</span>
                    <span class="pill">⚙️ Total bonus: <b class="gold">+{{ vehicle_bonus(user) }}%</b></span>
                </div>
            </div>
            <div class="garage-kpi">
                <div class="stat-card"><small>Total Vehicles</small><b>{{ total_vehicles(user) }}</b></div>
                <div class="stat-card"><small>Local Garage</small><b>{{ owned_vehicles_in_city(user)|length }}</b></div>
                <div class="stat-card"><small>Crime Bonus</small><b>+{{ vehicle_bonus(user) }}%</b></div>
                <div class="stat-card"><small>Current City</small><b>{{ user.location }}</b></div>
            </div>
        </div>

        {% for group in vehicle_categories %}
        <div class="vehicle-section">
            <h2 class="vehicle-section-title">{{ group.name }}</h2>
            <div class="vehicle-grid">
                {% for vehicle in group.vehicles %}
                <div class="vehicle-card">
                    <div class="vehicle-image" style="--vehicle-tone: {{ vehicle.tone }};">
                        <div class="vehicle-silhouette">
                            <div class="year">{{ vehicle.year }}</div>
                            <div class="icon">{{ vehicle.icon }}</div>
                        </div>
                    </div>
                    <div class="vehicle-body">
                        <h3>{{ vehicle.name }}</h3>
                        <div class="vehicle-meta">
                            <div><small>Price</small><b class="good">${{ vehicle.price }}</b></div>
                            <div><small>Crime Bonus</small><b class="gold">+{{ vehicle.bonus }}%</b></div>
                            <div><small>Owned Here</small><b>{{ vehicle_quantity(user, user.location, vehicle.key) }}</b></div>
                            <div><small>Class</small><b>{{ vehicle.category }}</b></div>
                        </div>
                        <form action="/garage_action" method="post">
                            <input type="hidden" name="vehicle_key" value="{{ vehicle.key }}">
                            <button class="btn">Purchase Vehicle</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endfor %}

        <hr>
        <h2>🌍 Garage Overview by City</h2>
        <div class="garage-city-grid">
            {% for citydata in garages %}
            <div class="garage-city-card">
                <h3>🚗 {{ citydata.city }} Garage</h3>
                <p>{% if citydata.city == user.location %}<span class="good">You are here</span>{% else %}<span class="muted">Travel here to buy locally</span>{% endif %}</p>
                <p>Total vehicles: <b class="gold">{{ citydata.total }}</b></p>
                <p>Total value: <b class="good">${{ garage_city_value(citydata) }}</b></p>
                <div class="owned-list">
                    {% for row in citydata.rows %}
                        {% if row.quantity > 0 %}
                            {{ row.vehicle.year }} {{ row.vehicle.name }} x{{ row.quantity }}<br>
                        {% endif %}
                    {% endfor %}
                    {% if citydata.total == 0 %}<span class="muted">No vehicles stored here.</span>{% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    {% endif %}

    {% if page == "bullets" %}
        <h2>🔫 Black Market</h2>
        <p>Your rank gives +{{ rank_bonus(user, 'attack') }}% attack power.</p>
        <form action="/bullet_action" method="post">
            <button class="btn" name="action" value="buy_bullet">Buy 10 bullets - $200</button>
        </form>
        <p>Bodyguards, bulletproof vests, lookouts, and safe houses are now managed on the Protection page.</p>
        <hr><h2 class="red">🎯 Attack a Rival</h2>
        <form action="/kill_action" method="post">
            Target name:<br><input class="input" name="target" required>
            Bullets to use:<br><input class="input" type="number" name="bullets_spent" min="1" required>
            <button class="btn">Attack</button>
        </form>
    {% endif %}


    {% if page == "protection" %}
        <h2>🛡️ Protection & Special Services</h2>
        <p>Buy and hire protection for your organization. These upgrades improve survival, reduce arrest risk, and protect your cash.</p>

        <div class="grid">
            <div class="card">
                <h3>Bodyguard</h3>
                <p>Price: <b class="good">$1000</b></p>
                <p>Bodyguards make it harder for rivals to kill you.</p>
                <form action="/protection_action" method="post">
                    <button class="btn" name="action" value="buy_guard">Hire Bodyguard</button>
                </form>
            </div>

            <div class="card">
                <h3>Bulletproof Vest</h3>
                <p>Price: <b class="good">$750</b></p>
                <p>When a rival would kill you, a vest has a 25% chance to save your life. The vest is consumed if it saves you.</p>
                <form action="/protection_action" method="post">
                    <button class="btn" name="action" value="buy_vest">Buy Vest</button>
                </form>
            </div>

            <div class="card">
                <h3>Safe House</h3>
                <p>Price: <b class="good">$5000</b></p>
                <p>Safe houses reduce arrest fines and cash losses by 10% each, up to 50%. They also add extra protection against attacks.</p>
                <form action="/protection_action" method="post">
                    <button class="btn" name="action" value="buy_safehouse">Buy Safe House</button>
                </form>
            </div>

            <div class="card">
                <h3>Street Lookout</h3>
                <p>Price: <b class="good">$1500</b></p>
                <p>Lookouts reduce police arrest chance by 2% each, up to 15% total.</p>
                <form action="/protection_action" method="post">
                    <button class="btn" name="action" value="hire_lookout">Hire Lookout</button>
                </form>
            </div>
        </div>

        <hr>
        <h2>Current Protection</h2>
        <table>
            <tr><th>Protection</th><th>Owned</th><th>Effect</th></tr>
            <tr><td>Bodyguards</td><td>{{ user.bodyguards }}</td><td>+15 bullets required per bodyguard to kill you</td></tr>
            <tr><td>Bulletproof Vests</td><td>{{ user.bulletproof_vests }}</td><td>25% chance to survive a successful assassination attempt</td></tr>
            <tr><td>Safe Houses</td><td>{{ user.safehouses }}</td><td>{{ protection_loss_reduction(user) }}% reduced fines/losses, +20 bullets required per safe house</td></tr>
            <tr><td>Street Lookouts</td><td>{{ user.lookouts }}</td><td>{{ lookout_arrest_reduction(user) }}% lower police arrest chance</td></tr>
        </table>
    {% endif %}


    {% if page == "properties" %}
        <h2>🏛 Properties & Passive Income</h2>
        <p>Buy buildings for long-term passive income. Income builds up over time and can be collected into cash.</p>
        <p>Current income: <b class="gold">${{ property_income_per_hour(user) }}/hour</b> | Collectable now: <b class="good">${{ property_collectable_income(user) }}</b> | Prestige: <b class="gold">{{ property_prestige(user) }}</b></p>

        <div class="card">
            <h3>💰 Collect Property Income</h3>
            <p>Income is calculated from the time since your last collection. Grand Estate gives prestige instead of hourly cash.</p>
            <form action="/property_action" method="post">
                <button class="btn" name="action" value="collect_income">Collect Income</button>
            </form>
        </div>

        <hr>
        <h2>Property Market</h2>
        <div class="grid">
            {% for item in properties %}
            <div class="card">
                <h3>{{ item.name }}</h3>
                <p>Owned: <b class="gold">{{ item.quantity }}</b></p>
                <p>Cost: <b class="good">${{ item.cost }}</b></p>
                {% if item.income_per_hour > 0 %}
                    <p>Income: <b class="gold">${{ item.income_per_hour }}/hour</b></p>
                    <p>Total from owned: <b class="good">${{ item.total_income }}/hour</b></p>
                {% else %}
                    <p>Prestige: <b class="gold">+{{ item.prestige }}</b></p>
                    <p>This is an endgame status property.</p>
                {% endif %}
                <form action="/property_action" method="post">
                    <input type="hidden" name="property_key" value="{{ item.key }}">
                    <button class="btn" name="action" value="buy_property">Buy Property</button>
                </form>
            </div>
            {% endfor %}
        </div>

        <hr>
        <h2>Your Property Empire</h2>
        <table>
            <tr><th>Property</th><th>Owned</th><th>Income/hour</th><th>Prestige</th></tr>
            {% for item in properties %}
            <tr>
                <td>{{ item.name }}</td>
                <td>{{ item.quantity }}</td>
                <td class="good">${{ item.total_income }}</td>
                <td class="gold">{{ item.quantity * item.prestige }}</td>
            </tr>
            {% endfor %}
        </table>
    {% endif %}


    {% if page == "influence" %}
        <h2>🏛 Influence</h2>
        <p>Buy political and criminal influence to improve jail, smuggling, casino and property systems. Each influence can be bought once.</p>
        <p>Owned influence: <b class="gold">{{ influence_count(user) }}/4</b></p>

        <div class="grid">
            {% for item in influences %}
            <div class="card">
                <h3>{{ item.name }}</h3>
                <p>{{ item.description }}</p>
                <p>Cost: <b class="good">${{ item.cost }}</b></p>
                <p>Effect: <b class="gold">{{ item.effect }}</b></p>
                {% if item.owned %}
                    <p class="good">Owned</p>
                {% else %}
                    <form action="/influence_action" method="post">
                        <input type="hidden" name="influence_key" value="{{ item.key }}">
                        <button class="btn" name="action" value="buy_influence">Buy Influence</button>
                    </form>
                {% endif %}
            </div>
            {% endfor %}
        </div>

        <hr>
        <h2>Current Bonuses</h2>
        <table>
            <tr><th>Bonus</th><th>Current Value</th></tr>
            <tr><td>Smuggling profit bonus</td><td class="gold">+{{ influence_smuggling_bonus(user) }}%</td></tr>
            <tr><td>Extra arrest risk reduction</td><td class="gold">{{ influence_arrest_reduction(user) }}%</td></tr>
            <tr><td>Property income bonus</td><td class="gold">+{{ influence_property_income_bonus(user) }}%</td></tr>
            <tr><td>Casino vault income bonus</td><td class="gold">+{{ influence_casino_income_bonus(user) }}%</td></tr>
            <tr><td>Corrupt officer chance</td><td class="gold">{{ bribe_chance(user) }}%</td></tr>
        </table>
    {% endif %}

    {% if page == "licenses" %}
        <h2>🎰 Casino License Office</h2>
        <p>Casino ownership is reserved for elite Shelby operators. A license is required before you can buy or operate any casino in the territories.</p>

        <div class="grid">
            <div class="card">
                <h3>🎫 Casino License</h3>
                <p>Required rank: <b class="gold">{{ casino_license_required_rank }}</b></p>
                <p>Cost: <b class="good">${{ casino_license_cost }}</b></p>
                <p>This license grants permission to own and operate casinos within the Shelby territories.</p>
                {% if user.casino_license %}
                    <p class="good">You already own a Casino License.</p>
                {% else %}
                    <form action="/license_action" method="post">
                        <button class="btn" name="action" value="purchase_casino_license">Purchase License</button>
                    </form>
                {% endif %}
            </div>

            <div class="card">
                <h3>🏛 City Casino Limits</h3>
                <p>Every city has a limited number of casino licenses, so ownership stays exclusive.</p>
                <table>
                    <tr><th>City</th><th>Casino Slots</th></tr>
                    {% for city, slots in city_casino_limits.items() %}
                    <tr><td>{{ city }}</td><td class="gold">{{ slots }}</td></tr>
                    {% endfor %}
                </table>
            </div>
        </div>

        <hr>
        <h2>Later Expansion</h2>
        <table>
            <tr><th>License</th><th>Cost</th><th>Bonus</th></tr>
            <tr><td>Standard License</td><td class="good">$250,000</td><td>Own and operate casinos</td></tr>
            <tr><td>Elite License</td><td class="good">$1,000,000</td><td>Future: +10% casino income and +5% house edge</td></tr>
        </table>
    {% endif %}

    {% if page == "casino" %}
        <h2>🃏 City Casinos</h2>
        <p>Each city has a limited number of casino licenses. Casinos can be bought from the State, from other players, or from an heir if the owner is dead.</p>
        <p>You need a <b class="gold">Casino License</b> before you can buy a casino. Casino owners receive a house cut from lost bets in their city. House cut: <b class="gold">{{ house_cut }}%</b>.</p>

        <div class="grid">
            <div class="card">
                <h3>🪙 Coin Flip</h3>
                <p>50% chance. Win doubles your bet.</p>
                <form action="/casino_action" method="post">
                    Bet:<br><input class="input" type="number" name="bet" min="1" required>
                    <button class="btn" name="game" value="coin">Play Coin Flip</button>
                </form>
            </div>

            <div class="card">
                <h3>🎲 Dice Six</h3>
                <p>Roll a 6 to win 5x your bet.</p>
                <form action="/casino_action" method="post">
                    Bet:<br><input class="input" type="number" name="bet" min="1" required>
                    <button class="btn" name="game" value="dice">Roll Dice</button>
                </form>
            </div>

            <div class="card">
                <h3>🎰 Slot Machine</h3>
                <p>Rare jackpot. Win up to 10x.</p>
                <form action="/casino_action" method="post">
                    Bet:<br><input class="input" type="number" name="bet" min="1" required>
                    <button class="btn" name="game" value="slots">Spin Slots</button>
                </form>
            </div>

            <div class="card">
                <h3>⚫🔴 Roulette</h3>
                <p>Choose red or black. Win doubles your bet.</p>
                <form action="/casino_action" method="post">
                    Bet:<br><input class="input" type="number" name="bet" min="1" required>
                    Pick:<br>
                    <select class="input" name="choice">
                        <option value="red">Red</option>
                        <option value="black">Black</option>
                    </select>
                    <button class="btn" name="game" value="roulette">Play Roulette</button>
                </form>
            </div>

            <div class="card">
                <h3>🃏 High Card</h3>
                <p>Draw higher than the dealer. Win doubles your bet.</p>
                <form action="/casino_action" method="post">
                    Bet:<br><input class="input" type="number" name="bet" min="1" required>
                    <button class="btn" name="game" value="highcard">Draw Card</button>
                </form>
            </div>
        </div>

        <hr>
        <h2>🏛 Casino Licenses in {{ user.location }}</h2>
        <table>
            <tr><th>License</th><th>Status</th><th>Owner/Heir</th><th>Price</th><th>Vault</th><th>Action</th></tr>
            {% for casino in city_casinos %}
            <tr>
                <td>{{ casino.name }}</td>
                <td>
                    {% if casino.owner_id == user.id %}
                        <span class="good">Yours</span>
                    {% elif casino.owner and casino.owner.is_dead %}
                        <span class="red">Owner Dead</span>
                    {% elif casino.owner_id %}
                        <span class="gold">Player Owned</span>
                    {% else %}
                        <span class="blue">State Owned</span>
                    {% endif %}
                </td>
                <td>{{ casino_owner_status(casino) }}</td>
                <td class="good">${{ casino.price }}</td>
                <td class="gold">${{ casino.vault }}</td>
                <td>
                    {% if casino.owner_id == user.id %}
                        <form action="/casino_property_action" method="post">
                            <input type="hidden" name="casino_id" value="{{ casino.id }}">
                            Heir username:<br>
                            <input class="input" name="heir_username" placeholder="Optional heir">
                            <button class="btn" name="action" value="set_heir">Set Heir</button>
                            <button class="btn" name="action" value="collect_vault">Collect Vault</button>
                        </form>
                    {% else %}
                        <form action="/casino_property_action" method="post">
                            <input type="hidden" name="casino_id" value="{{ casino.id }}">
                            <button class="btn" name="action" value="buy">Buy Casino</button>
                        </form>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>

        <hr>
        <h2>🌍 Casino Overview by City</h2>
        <table>
            <tr><th>City</th><th>Casino</th><th>Status</th><th>Price</th></tr>
            {% for casino in all_casino_rows %}
            <tr>
                <td>{{ casino.city }}</td>
                <td>{{ casino.name }}</td>
                <td>{{ casino_owner_status(casino) }}</td>
                <td class="good">${{ casino.price }}</td>
            </tr>
            {% endfor %}
        </table>
    {% endif %}


    {% if page == "heists" %}
        <h2>💼 Shelby Heists</h2>
        <p>Plan bigger jobs for serious money and EXP. Heists use bullets, check your power, and can send you to jail if they fail.</p>
        <p>Cooldown: <b class="gold">{{ heist_cooldown }}</b> seconds. Successful heists completed: <b class="gold">{{ user.heists_successful }}</b>.</p>
        {% if heist_wait > 0 %}<p class="red">You can start another heist in {{ heist_wait }} seconds.</p>{% endif %}

        <div class="grid">
            {% for plan in heist_plans %}
            <div class="card">
                <h3>{{ plan.name }}</h3>
                <p>Required power: <b class="gold">{{ plan.min_power }}</b></p>
                <p>Bullets used: <b class="red">{{ plan.bullets }}</b></p>
                <p>Reward: <b class="good">${{ plan.cash_min }} - ${{ plan.cash_max }}</b> + {{ plan.exp }} EXP</p>
                <p>Success chance: <b class="gold">{{ plan.success_chance }}%</b></p>
                <p>Failure jail time: <b class="red">{{ plan.jail }}</b> seconds</p>
                <form action="/heist_action" method="post">
                    <input type="hidden" name="heist_key" value="{{ plan.key }}">
                    <button class="btn" {% if heist_wait > 0 or not plan.ready %}disabled{% endif %}>Start Heist</button>
                </form>
                {% if not plan.ready %}<p class="red">Not enough power or bullets yet.</p>{% endif %}
            </div>
            {% endfor %}
        </div>
    {% endif %}

    {% if page == "jail" %}
        <h2>🚔 Birmingham Prison</h2>
        {% if remaining > 0 %}
            <p class="red">You are currently in jail.</p>
            <p>Time remaining: <b class="gold">{{ remaining }}</b> seconds.</p>
            <p>You cannot commit crimes, travel, gamble, attack rivals, buy weapons, or use businesses while jailed.</p>

            <div class="card">
                <h3>🕴️ Find a Corrupt Officer</h3>
                <p>Search for a corrupt officer who can release you early for a bribe.</p>
                <p>Bribe cost if found: <b class="gold">${{ bribe_cost(user) }}</b></p>
                <p>Chance to find one: <b class="gold">{{ bribe_chance(user) }}%</b></p>
                <p>Searching unlocks after 45% of your sentence. Failed searches have a 15 second cooldown.</p>
                {% if bribe_wait > 0 %}
                    <p class="red">You can search again in <b>{{ bribe_wait }}</b> seconds.</p>
                {% else %}
                    <form action="/bribe_officer" method="post">
                        <button class="btn">Search for a Corrupt Officer</button>
                    </form>
                {% endif %}
            </div>
        {% else %}
            <p class="good">You are free. Stay sharp out there.</p>
            <a class="btn" href="/">Back to Crimes</a>
        {% endif %}
        <p>Total arrests: <b>{{ user.arrests }}</b></p>
    {% endif %}

    {% if page == "territories" %}
        <h2>⚔️ Territory Wars & City Control</h2>
        <p>Families can fight for cities. City owners earn hourly tax income and strategic bonuses.</p>
        <p>War cost: <b class="good">${{ territory_war_cost }}</b> and <b class="gold">{{ territory_war_bullets }}</b> bullets from the attacker. Minimum members: <b class="gold">{{ territory_min_members }}</b>.</p>

        {% if user.family %}
            <div class="grid">
                <div class="card">
                    <h3>{{ user.family.name }} Empire</h3>
                    <p>Controlled cities: <b class="gold">{{ family_territory_count(user.family) }}</b></p>
                    <p>Tax income: <b class="good">${{ family_territory_tax_per_hour(user.family) }}/hour</b></p>
                    <p>Family bank: <b class="good">${{ user.family.bank }}</b></p>
                </div>
                <div class="card">
                    <h3>Collect Taxes</h3>
                    <p>Taxes go directly into the family bank. Only Boss and Underboss can collect.</p>
                    <form action="/territory_action" method="post">
                        <button class="btn" name="action" value="collect_tax">Collect Territory Taxes</button>
                    </form>
                </div>
            </div>
        {% else %}
            <p class="red">You need to join or create a family before using territory wars.</p>
        {% endif %}

        <hr>
        <h2>City Map</h2>
        <table>
            <tr><th>City</th><th>Controller</th><th>Hourly Tax</th><th>Bonus</th><th>Status</th><th>Action</th></tr>
            {% for territory in territories %}
            <tr>
                <td>{{ territory.city }}</td>
                <td>{% if territory.family %}<span class="gold">{{ territory.family.name }}</span>{% else %}<span class="blue">State Controlled</span>{% endif %}</td>
                <td class="good">${{ territory_tax_data[territory.city].tax_per_hour }}</td>
                <td>{{ territory_tax_data[territory.city].bonus }}</td>
                <td>
                    {% if territory.protected_until and territory.protected_until > now_time %}
                        <span class="red">Protected for {{ ((territory.protected_until - now_time) | int) }}s</span>
                    {% else %}
                        <span class="good">Open</span>
                    {% endif %}
                </td>
                <td>
                    {% if user.family and (not territory.family_id or territory.family_id != user.family_id) %}
                    <form action="/territory_action" method="post">
                        <input type="hidden" name="city" value="{{ territory.city }}">
                        <button class="btn" name="action" value="attack">Declare War</button>
                    </form>
                    {% else %}
                        <span style="color:#777;">No action</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    {% endif %}

    {% if page == "ranking" %}
        <h2>🏆 Rankings</h2>
        <p>Rankings are sorted by Power first, then Wealth.</p>
        <table>
            <tr><th>#</th><th>Name</th><th>Status</th><th>Rank</th><th>City</th><th>EXP</th><th>Power</th><th>Wealth</th></tr>
            {% for u in users %}
            <tr>
                <td>{{ loop.index }}</td><td>{{ u.username }}</td>
                <td>{% if u.is_dead %}<span class="red">💀 Dead</span>{% else %}<span class="good">🟢 Active</span>{% endif %}</td>
                <td>{{ u.rank }}</td><td>{{ u.location }}</td><td>{{ u.exp }}</td>
                <td class="gold">{{ power_score(u) }}</td><td class="good">${{ u.money + u.bank }}</td>
            </tr>
            {% endfor %}
        </table>
    {% endif %}

    </div>
    </main>
</div>
{% endif %}
</body>
</html>
"""



def casino_vault_total(user):
    if not user or not user.id:
        return 0
    try:
        ensure_city_casinos()
        return sum(int(safe_number(c.vault)) for c in CityCasino.query.filter_by(owner_id=user.id).all())
    except Exception:
        return 0


def active_shipments(user):
    if not user or not user.id:
        return []
    try:
        return Shipment.query.filter_by(user_id=user.id, status="in_transit").order_by(Shipment.arrives_at.asc()).limit(10).all()
    except Exception:
        return []


def empire_value(user):
    if not user or not user.id:
        return 0
    total = int(safe_number(user.money)) + int(safe_number(user.bank))
    try:
        total += warehouse_used(user) * 50
        total += total_distilleries(user) * 2500
        for row in ensure_user_properties(user):
            data = PROPERTY_TYPES.get(row.property_key)
            if data:
                total += int(safe_number(row.quantity)) * int(data["cost"])
        ensure_city_casinos()
        total += sum(int(safe_number(c.price)) + int(safe_number(c.vault)) for c in CityCasino.query.filter_by(owner_id=user.id).all())
        ensure_city_vehicles(user)
        for row in CityVehicle.query.filter_by(user_id=user.id).all():
            data = VEHICLE_BY_KEY.get(row.vehicle_key)
            if data:
                total += int(safe_number(row.quantity)) * int(data["price"])
        total += influence_count(user) * 250000
        if user.family:
            total += family_territory_count(user.family) * 1000000
    except Exception:
        pass
    return int(total)

def render_page(user, page, **kwargs):
    return render_template_string(
        HTML_UI,
        game_name=GAME_NAME,
        user=user,
        page=page,
        power_score=power_score,
        rank_bonus=rank_bonus,
        bribe_cost=bribe_cost,
        bribe_chance=bribe_chance,
        total_distilleries=total_distilleries,
        business_ready_gin=business_ready_gin,
        total_ready_gin=total_ready_gin,
        warehouse_free_space=warehouse_free_space,
        total_vehicles=total_vehicles,
        vehicle_bonus=vehicle_bonus,
        vehicle_quantity=vehicle_quantity,
        vehicle_categories_for_showroom=vehicle_categories_for_showroom,
        garage_city_value=garage_city_value,
        owned_vehicles_in_city=owned_vehicles_in_city,
        family_power=family_power,
        family_member_count=family_member_count,
        family_bonus=family_bonus,
        casino_owner_status=casino_owner_status,
        user_casinos=user_casinos,
        casino_license_cost=CASINO_LICENSE_COST,
        casino_license_required_rank=CASINO_LICENSE_REQUIRED_RANK,
        city_casino_limits=CITY_CASINOS,
        warehouse_used=warehouse_used,
        warehouse_capacity=warehouse_capacity,
        warehouse_level_info=warehouse_level_info,
        travel_cost_to=travel_cost_to,
        is_international_city=is_international_city,
        protection_loss_reduction=protection_loss_reduction,
        lookout_arrest_reduction=lookout_arrest_reduction,
        heist_success_chance=heist_success_chance,
        property_income_per_hour=property_income_per_hour,
        property_collectable_income=property_collectable_income,
        property_prestige=property_prestige,
        influence_count=influence_count,
        influence_smuggling_bonus=influence_smuggling_bonus,
        influence_arrest_reduction=influence_arrest_reduction,
        influence_property_income_bonus=influence_property_income_bonus,
        influence_casino_income_bonus=influence_casino_income_bonus,
        family_territory_count=family_territory_count,
        family_territory_tax_per_hour=family_territory_tax_per_hour,
        territory_bonus_text=territory_bonus_text,
        empire_value=empire_value,
        active_shipments=active_shipments,
        casino_vault_total=casino_vault_total,
        now_time=time.time(),
        **kwargs,
    )



@app.route("/dashboard")
def dashboard():
    user, redirect_response = login_required()
    if redirect_response:
        return redirect_response
    return render_page(user, "dashboard", msg=request.args.get("msg"))

@app.route("/")
def index():
    user = current_user()
    if not user:
        return render_page(None, "login", msg=request.args.get("msg"))

    if user.is_dead:
        session.clear()
        return redirect(url_for("index", msg="You were killed by a rival. Create a new account."))

    # If the player is jailed, the home page must show the jail screen too.
    # This prevents jailed players from seeing the crime page after login.
    if safe_number(user.jail_until) > time.time():
        remaining = int(safe_number(user.jail_until) - time.time())
        return render_page(
            user,
            "jail",
            remaining=remaining,
            bribe_wait=max(0, int(safe_number(user.bribe_available_at) - time.time())),
            msg=request.args.get("msg") or f"🚔 You are in jail for {remaining} more seconds.",
        )

    return render_page(
        user,
        "crime",
        cooldown=CRIME_COOLDOWN,
        local_vehicles=owned_vehicles_in_city(user),
        msg=request.args.get("msg"),
    )


@app.route("/login_action", methods=["POST"])
def login_action():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    action = request.form.get("action")

    if len(username) < 3 or len(password) < 3:
        return redirect(url_for("index", msg="Name and password must be at least 3 characters."))

    user = User.query.filter_by(username=username).first()

    if action == "register":
        if user:
            return redirect(url_for("index", msg="That name already exists."))
        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            money=500,
            bank=0,
            exp=0,
            rank="Street Runner",
            location="Birmingham",
            gin=0,
            bullets=0,
            bodyguards=0,
            bulletproof_vests=0,
            safehouses=0,
            lookouts=0,
            warehouse_level=0,
            family_role="Solo",
            cars=0,
            distilleries=0,
            last_crime=0.0,
            last_collect=0.0,
            is_dead=False,
            jail_until=0.0,
            arrests=0,
            bribe_available_at=0.0,
            last_bribe_attempt=0.0,
            last_heist=0.0,
            heists_successful=0,
            casino_license=False,
            police_chief_influence=False,
            judge_influence=False,
            mayor_influence=False,
            customs_officer_influence=False,
        )
        new_user.update_rank()
        db.session.add(new_user)
        db.session.commit()
        session["username"] = username
        return redirect(url_for("index", msg="Welcome to the Shelby Family."))

    if action == "login":
        if not user or not check_password_hash(user.password_hash, password):
            return redirect(url_for("index", msg="Incorrect login."))
        if user.is_dead:
            return redirect(url_for("index", msg="This account is dead."))
        user.update_rank()
        db.session.commit()
        session["username"] = username
        return redirect(url_for("index", msg="Welcome back."))

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index", msg="Logged out."))


@app.route("/jail")
def jail():
    user = current_user()
    if not user:
        return redirect(url_for("index", msg="Please log in first."))
    remaining = jail_remaining(user)
    bribe_wait = max(0, int(safe_number(user.bribe_available_at) - time.time()))
    return render_page(user, "jail", remaining=remaining, bribe_wait=bribe_wait, msg=request.args.get("msg"))


@app.route("/bribe_officer", methods=["POST"])
def bribe_officer():
    user = current_user()
    if not user:
        return redirect(url_for("index", msg="Please log in first."))

    remaining = jail_remaining(user)
    if remaining <= 0:
        user.jail_until = 0.0
        user.bribe_available_at = 0.0
        db.session.commit()
        return redirect(url_for("index", msg="You are already free."))

    wait = int(safe_number(user.bribe_available_at) - time.time())
    if wait > 0:
        return redirect(url_for("jail", msg=f"You cannot search yet. Try again in {wait} seconds."))

    # Rare bad luck: the officer is honest and reports the bribe attempt.
    if random.randint(1, 100) <= HONEST_OFFICER_CHANCE:
        user.jail_until = safe_number(user.jail_until) + 60
        user.bribe_available_at = time.time() + BRIBE_ATTEMPT_COOLDOWN
        user.last_bribe_attempt = time.time()
        db.session.commit()
        return redirect(url_for("jail", msg="🚔 The officer was honest and reported you. Your jail time increased by 60 seconds."))

    # Most searches fail. Higher ranks have better connections, but it should still feel rare.
    if random.randint(1, 100) > bribe_chance(user):
        user.bribe_available_at = time.time() + BRIBE_ATTEMPT_COOLDOWN
        user.last_bribe_attempt = time.time()
        db.session.commit()
        return redirect(url_for("jail", msg=f"No corrupt officer was willing to help. Try again in {BRIBE_ATTEMPT_COOLDOWN} seconds."))

    cost = bribe_cost(user)
    if safe_number(user.money) < cost:
        user.bribe_available_at = time.time() + BRIBE_ATTEMPT_COOLDOWN
        db.session.commit()
        return redirect(url_for("jail", msg=f"You found a corrupt officer, but you need ${cost} cash to pay the bribe."))

    user.money = safe_number(user.money) - cost
    user.jail_until = 0.0
    user.bribe_available_at = 0.0
    user.last_bribe_attempt = time.time()
    db.session.commit()
    return redirect(url_for("index", msg=f"🕴️ You found a corrupt officer and paid ${cost}. You are free."))


@app.route("/crime_action", methods=["POST"])
def crime_action():
    user, error = login_required()
    if error:
        return error

    now = time.time()
    remaining = int(CRIME_COOLDOWN - (now - user.last_crime))
    if remaining > 0:
        return redirect(url_for("index", msg=f"Wait {remaining} more seconds."))

    crimes = {
        "pickpocket": {"name": "Pickpocket", "chance": 85, "min_cash": 30, "max_cash": 100, "min_exp": 2, "max_exp": 6, "loss": 25},
        "robbery": {"name": "Store Robbery", "chance": 65, "min_cash": 100, "max_cash": 350, "min_exp": 8, "max_exp": 18, "loss": 120},
        "truck": {"name": "Bank Transport", "chance": 40, "min_cash": 400, "max_cash": 1000, "min_exp": 20, "max_exp": 45, "loss": 300},
    }
    crime_key = request.form.get("crime", "pickpocket")
    data = crimes.get(crime_key, crimes["pickpocket"])

    vehicle_key = request.form.get("vehicle_key", "").strip()
    selected_vehicle, selected_vehicle_row = get_selected_city_vehicle(user, vehicle_key)
    if vehicle_key and not selected_vehicle:
        return redirect(url_for("index", msg="That vehicle is not available in your current city."))

    vehicle_bonus_value = int(selected_vehicle["bonus"]) if selected_vehicle else 0
    chance = min(data["chance"] + vehicle_bonus_value + rank_bonus(user, "crime_chance"), 95)
    user.last_crime = now

    arrest_chances = {"pickpocket": 5, "robbery": 12, "truck": 25}
    arrest_chance = max(1, arrest_chances.get(crime_key, 5) - lookout_arrest_reduction(user))
    if random.randint(1, 100) <= arrest_chance:
        jail_time = random.randint(120, 300)
        fine = reduce_loss_by_protection(user, int(safe_number(user.money) * 0.10))
        user.money = max(0, safe_number(user.money) - fine)
        user.jail_until = time.time() + jail_time
        if random.randint(1, 100) <= LUCKY_OFFICER_CHANCE:
            user.bribe_available_at = time.time() + random.randint(2, 10)
            bribe_msg = " A corrupt officer might be available very soon."
        else:
            user.bribe_available_at = time.time() + int(jail_time * BRIBE_WAIT_RATIO)
            bribe_msg = ""
        user.arrests = safe_number(user.arrests) + 1
        db.session.commit()
        return redirect(url_for("jail", msg=f"🚔 You were arrested! Fine: ${fine}. Jail time: {jail_time} seconds.{bribe_msg}"))

    if random.randint(1, 100) <= chance:
        cash = random.randint(data["min_cash"], data["max_cash"])
        cash += cash * (rank_bonus(user, "crime_income") + family_bonus(user, "crime_income")) // 100
        exp = random.randint(data["min_exp"], data["max_exp"])
        user.money += cash
        user.exp += exp
        msg = f"{data['name']} successful. You earned ${cash} and {exp} EXP."
    else:
        loss = min(user.money, random.randint(30, data["loss"]))
        user.money -= loss
        msg = f"{data['name']} failed. You lost ${loss}."

        if selected_vehicle and selected_vehicle_row and random.randint(1, 100) <= 3:
            selected_vehicle_row.quantity = max(0, safe_number(selected_vehicle_row.quantity) - 1)
            user.cars = max(0, safe_number(user.cars) - 1)
            msg += f" The police discovered your {selected_vehicle['name']} and you lost it."

    user.update_rank()
    db.session.commit()
    return redirect(url_for("index", msg=msg))


@app.route("/bank")
def bank():
    user, error = login_required()
    if error:
        return error
    return render_page(user, "bank", msg=request.args.get("msg"))


@app.route("/bank_action", methods=["POST"])
def bank_action():
    user, error = login_required()
    if error:
        return error
    amount = safe_int(request.form.get("amount"))
    action = request.form.get("action")
    if amount <= 0:
        return redirect(url_for("bank", msg="Invalid amount."))
    if action == "deposit":
        if user.money < amount:
            return redirect(url_for("bank", msg="Not enough cash."))
        user.money -= amount
        user.bank += amount
        msg = f"${amount} deposited."
    elif action == "withdraw":
        if user.bank < amount:
            return redirect(url_for("bank", msg="Not enough money in the bank."))
        user.bank -= amount
        user.money += amount
        msg = f"${amount} withdrawn."
    else:
        msg = "Invalid action."
    db.session.commit()
    return redirect(url_for("bank", msg=msg))


@app.route("/market")
def market():
    user, error = login_required()
    if error:
        return error
    return render_page(
        user,
        "market",
        contraband=warehouse_overview(user),
        cities=CITIES,
        travel_cost=TRAVEL_COST,
        international_travel_cost=INTERNATIONAL_TRAVEL_COST,
        shipment_speeds=shipment_speed_options(),
        shipments=shipment_overview(user),
        format_duration=format_duration,
        msg=request.args.get("msg"),
    )


@app.route("/market_action", methods=["POST"])
def market_action():
    user, error = login_required()
    if error:
        return error

    item_key = request.form.get("item_key", "gin")
    item_data = CONTRABAND.get(item_key)
    if not item_data:
        return redirect(url_for("market", msg="Invalid goods."))

    amount = safe_int(request.form.get("amount"))
    if amount <= 0:
        return redirect(url_for("market", msg="Invalid amount."))

    action = request.form.get("action")
    price = int(item_data["prices"].get(user.location, 0))
    row = warehouse_item(user, item_key)

    if action == "buy":
        if warehouse_free_space(user) < amount:
            return redirect(url_for("market", msg="Not enough warehouse space. Upgrade your warehouse."))
        total = price * amount
        if safe_number(user.money) < total:
            return redirect(url_for("market", msg="Not enough cash."))
        user.money = int(safe_number(user.money)) - total
        row.quantity = int(safe_number(row.quantity)) + amount
        msg = f"You bought {amount} {item_data['label']} for ${total}."

    elif action in ["sell", "sell_all"]:
        owned = int(safe_number(row.quantity))
        if owned <= 0:
            return redirect(url_for("market", msg=f"You do not own any {item_data['label']}."))
        if action == "sell_all":
            amount = owned
        if amount > owned:
            return redirect(url_for("market", msg="You do not own that much stock."))

        base = price * amount
        bonus = base * (rank_bonus(user, "smuggling") + family_bonus(user, "smuggling") + influence_smuggling_bonus(user)) // 100
        earned = base + bonus
        risk = max(0, int(item_data["risk"]) - lookout_arrest_reduction(user) - influence_arrest_reduction(user))

        if random.randint(1, 100) <= risk:
            fine = reduce_loss_by_protection(user, int(earned * 0.25))
            user.money = max(0, int(safe_number(user.money)) - fine)
            row.quantity = max(0, owned - amount)
            jail_time = int(random.randint(60, 180) * influence_jail_multiplier(user))
            user.jail_until = time.time() + jail_time
            user.bribe_available_at = time.time() + int(jail_time * BRIBE_WAIT_RATIO)
            user.arrests = int(safe_number(user.arrests)) + 1
            db.session.commit()
            return redirect(url_for("jail", msg=f"🚔 Police caught your smuggling deal. You lost the goods, paid a ${fine} fine, and got {jail_time} seconds jail time."))

        row.quantity = owned - amount
        user.money = int(safe_number(user.money)) + earned
        user.exp = int(safe_number(user.exp)) + amount
        user.update_rank()
        msg = f"You sold {amount} {item_data['label']} for ${earned}."

    else:
        msg = "Invalid action."

    db.session.commit()
    return redirect(url_for("market", msg=msg))


@app.route("/shipment_action", methods=["POST"])
def shipment_action():
    user, error = login_required()
    if error:
        return error

    action = request.form.get("action")

    if action == "send":
        item_key = request.form.get("item_key", "gin")
        item_data = CONTRABAND.get(item_key)
        destination = request.form.get("destination")
        amount = safe_int(request.form.get("amount"))
        if not item_data or destination not in MARKET_PRICES or destination == user.location:
            return redirect(url_for("market", msg="Invalid shipment route."))
        if amount <= 0:
            return redirect(url_for("market", msg="Invalid shipment amount."))

        row = warehouse_item(user, item_key)
        owned = int(safe_number(row.quantity))
        if amount > owned:
            return redirect(url_for("market", msg="You do not own that much stock to send."))

        speed = request.form.get("speed", "economy")
        if speed not in SHIPMENT_SPEEDS:
            speed = "economy"
        cost = shipment_cost(destination, amount, speed)
        if safe_number(user.money) < cost:
            return redirect(url_for("market", msg=f"Not enough cash. {shipment_speed_label(speed)} costs ${cost}."))

        risk = shipment_customs_risk(user, destination, item_key)
        row.quantity = owned - amount
        user.money = int(safe_number(user.money)) - cost

        if random.randint(1, 100) <= risk:
            fine = reduce_loss_by_protection(user, int(cost * 2))
            user.money = max(0, int(safe_number(user.money)) - fine)
            shipment = Shipment(user_id=user.id, item_key=item_key, quantity=amount, origin=user.location, destination=destination, arrives_at=time.time(), status="seized")
            db.session.add(shipment)
            db.session.commit()
            return redirect(url_for("market", msg=f"🚔 Customs seized your shipment of {amount} {item_data['label']}. You paid ${cost} transport and ${fine} fine."))

        seconds = shipment_seconds_for_speed(speed)
        shipment = Shipment(user_id=user.id, item_key=item_key, quantity=amount, origin=user.location, destination=destination, arrives_at=time.time() + seconds, status="in_transit")
        db.session.add(shipment)
        db.session.commit()
        route_type = "international" if is_international_city(destination) else "domestic"
        return redirect(url_for("market", msg=f"📦 Sent {amount} {item_data['label']} to {destination} with {shipment_speed_label(speed)}. {route_type.title()} shipment arrives in {format_duration(seconds)}. Cost: ${cost}."))

    if action == "collect":
        shipment_id = safe_int(request.form.get("shipment_id"))
        shipment = Shipment.query.filter_by(id=shipment_id, user_id=user.id).first()
        if not shipment:
            return redirect(url_for("market", msg="Shipment not found."))
        process_arrived_shipments(user)
        if shipment.status != "arrived":
            return redirect(url_for("market", msg="Shipment has not arrived yet."))
        if shipment.destination != user.location:
            return redirect(url_for("market", msg=f"Travel to {shipment.destination} to collect this shipment."))
        amount = int(safe_number(shipment.quantity))
        if warehouse_free_space(user) < amount:
            return redirect(url_for("market", msg="Not enough warehouse space to collect this shipment."))
        row = warehouse_item(user, shipment.item_key)
        row.quantity = int(safe_number(row.quantity)) + amount
        label = CONTRABAND.get(shipment.item_key, {"label": shipment.item_key})["label"]
        db.session.delete(shipment)
        db.session.commit()
        return redirect(url_for("market", msg=f"✅ Collected {amount} {label} from the shipment."))

    return redirect(url_for("market", msg="Invalid shipment action."))


@app.route("/warehouse")
def warehouse():
    user, error = login_required()
    if error:
        return error
    current_level = int(safe_number(getattr(user, "warehouse_level", 0)))
    next_level = current_level + 1 if current_level + 1 in WAREHOUSE_LEVELS else None
    next_upgrade = WAREHOUSE_LEVELS[next_level] if next_level is not None else None
    return render_page(
        user,
        "warehouse",
        warehouse_info=warehouse_level_info(user),
        next_upgrade=next_upgrade,
        contraband=warehouse_overview(user),
        msg=request.args.get("msg"),
    )


@app.route("/warehouse_action", methods=["POST"])
def warehouse_action():
    user, error = login_required()
    if error:
        return error

    if request.form.get("action") != "upgrade":
        return redirect(url_for("warehouse", msg="Invalid warehouse action."))

    current_level = int(safe_number(getattr(user, "warehouse_level", 0)))
    next_level = current_level + 1
    if next_level not in WAREHOUSE_LEVELS:
        return redirect(url_for("warehouse", msg="Warehouse is already fully upgraded."))

    cost = WAREHOUSE_LEVELS[current_level]["upgrade_cost"]
    if cost is None:
        return redirect(url_for("warehouse", msg="Warehouse is already fully upgraded."))
    if safe_number(user.money) < cost:
        return redirect(url_for("warehouse", msg="Not enough cash to upgrade your warehouse."))

    user.money = int(safe_number(user.money)) - int(cost)
    user.warehouse_level = next_level
    db.session.commit()
    return redirect(url_for("warehouse", msg=f"Warehouse upgraded to {WAREHOUSE_LEVELS[next_level]['name']}."))


@app.route("/travel_action", methods=["POST"])
def travel_action():
    user, error = login_required()
    if error:
        return error
    destination = request.form.get("destination")
    if destination not in MARKET_PRICES:
        return redirect(url_for("market", msg="Invalid destination."))
    if destination == user.location:
        return redirect(url_for("market", msg="You are already there."))
    cost = travel_cost_to(destination)
    if safe_number(user.money) < cost:
        return redirect(url_for("market", msg=f"Not enough cash for a ticket to {destination}. Ticket cost: ${cost}."))

    carried_stock = warehouse_used(user)
    if carried_stock > 0:
        risk = max(1, (10 if is_international_city(destination) else 3) - influence_arrest_reduction(user))
        if random.randint(1, 100) <= risk:
            fine = reduce_loss_by_protection(user, int(carried_stock * 10))
            user.money = max(0, int(safe_number(user.money)) - fine)
            jail_time = int((90 if is_international_city(destination) else 45) * influence_jail_multiplier(user))
            user.jail_until = time.time() + jail_time
            user.bribe_available_at = time.time() + int(jail_time * BRIBE_WAIT_RATIO)
            user.arrests = int(safe_number(user.arrests)) + 1
            db.session.commit()
            return redirect(url_for("jail", msg=f"🚔 Customs caught you travelling with contraband. Fine: ${fine}. Jail time: {jail_time} seconds."))

    user.money = int(safe_number(user.money)) - int(cost)
    user.location = destination
    db.session.commit()
    return redirect(url_for("market", msg=f"You bought a ticket for ${cost} and travelled to {destination}."))


@app.route("/family")
def family():
    user, error = login_required()
    if error:
        return error
    families = Family.query.all()
    families = sorted(families, key=family_power, reverse=True)[:50]
    family_members = []
    if user.family_id:
        family_members = User.query.filter_by(family_id=user.family_id).all()
        for member in family_members:
            member.update_rank()
        family_members = sorted(family_members, key=power_score, reverse=True)
    return render_page(user, "family", families=families, family_members=family_members, msg=request.args.get("msg"))


@app.route("/family_action", methods=["POST"])
def family_action():
    user, error = login_required()
    if error:
        return error

    action = request.form.get("action")
    name = request.form.get("family_name", "").strip()
    amount = safe_int(request.form.get("amount"))

    if action == "create":
        if user.family_id:
            return redirect(url_for("family", msg="You are already in a family."))
        if len(name) < 3:
            return redirect(url_for("family", msg="Family name must be at least 3 characters."))
        if Family.query.filter_by(name=name).first():
            return redirect(url_for("family", msg="That family name already exists."))
        cost = 50000
        if safe_number(user.money) < cost:
            return redirect(url_for("family", msg="Creating a family costs $50,000 cash."))
        user.money = int(safe_number(user.money)) - cost
        fam = Family(name=name, boss_id=user.id, bank=0, created_at=time.time())
        db.session.add(fam)
        db.session.flush()
        user.family_id = fam.id
        user.family_role = "Boss"
        db.session.commit()
        return redirect(url_for("family", msg=f"Family created: {name}."))

    if action == "join":
        if user.family_id:
            return redirect(url_for("family", msg="You are already in a family."))
        fam = Family.query.filter_by(name=name).first()
        if not fam:
            return redirect(url_for("family", msg="Family not found. Use the exact name."))
        user.family_id = fam.id
        user.family_role = "Associate"
        db.session.commit()
        return redirect(url_for("family", msg=f"You joined {fam.name}."))

    if action == "deposit":
        if not user.family_id or not user.family:
            return redirect(url_for("family", msg="You are not in a family."))
        if amount <= 0:
            return redirect(url_for("family", msg="Invalid amount."))
        if safe_number(user.money) < amount:
            return redirect(url_for("family", msg="Not enough cash."))
        user.money = int(safe_number(user.money)) - amount
        user.family.bank = int(safe_number(user.family.bank)) + amount
        db.session.commit()
        return redirect(url_for("family", msg=f"You deposited ${amount} into the family bank."))

    if action == "withdraw":
        if not user.family_id or not user.family:
            return redirect(url_for("family", msg="You are not in a family."))
        if user.family_role not in ["Boss", "Underboss"]:
            return redirect(url_for("family", msg="Only the Boss or Underboss can withdraw from the family bank."))
        if amount <= 0:
            return redirect(url_for("family", msg="Invalid amount."))
        if safe_number(user.family.bank) < amount:
            return redirect(url_for("family", msg="Not enough money in the family bank."))
        user.family.bank = int(safe_number(user.family.bank)) - amount
        user.money = int(safe_number(user.money)) + amount
        db.session.commit()
        return redirect(url_for("family", msg=f"You withdrew ${amount} from the family bank."))

    if action == "leave":
        if not user.family_id or not user.family:
            return redirect(url_for("family", msg="You are not in a family."))
        fam = user.family
        if user.family_role == "Boss" and family_member_count(fam) > 1:
            return redirect(url_for("family", msg="Bosses cannot leave while other members remain."))
        if user.family_role == "Boss" and family_member_count(fam) == 1:
            db.session.delete(fam)
        user.family_id = None
        user.family_role = "Solo"
        db.session.commit()
        return redirect(url_for("family", msg="You left the family."))

    return redirect(url_for("family", msg="Invalid family action."))


@app.route("/assets")
def assets():
    user, error = login_required()
    if error:
        return error
    businesses = ensure_city_businesses(user)
    for business in businesses:
        update_business_production(business)
    db.session.commit()
    current_business = business_for_current_city(user)
    return render_page(user, "assets", businesses=businesses, current_business=current_business, msg=request.args.get("msg"))


@app.route("/asset_action", methods=["POST"])
def asset_action():
    user, error = login_required()
    if error:
        return error
    if request.form.get("action") == "buy_distillery":
        price = 2500
        if user.money < price:
            return redirect(url_for("assets", msg="Not enough cash."))

        business = business_for_current_city(user)
        user.money -= price
        business.distilleries = int(safe_number(business.distilleries)) + 1
        msg = f"You bought a distillery in {user.location}."
    else:
        msg = "Invalid action."
    db.session.commit()
    return redirect(url_for("assets", msg=msg))


@app.route("/collect_action", methods=["POST"])
def collect_action():
    user, error = login_required()
    if error:
        return error

    business = business_for_current_city(user)
    if int(safe_number(business.distilleries)) <= 0:
        return redirect(url_for("assets", msg=f"You do not own any distilleries in {user.location}. Travel to a city where you own distilleries to collect there."))

    # Update this city's distillery stock first. If the warehouse is full,
    # the gin stays pending inside this city's distillery until space opens.
    update_business_production(business)
    ready = int(safe_number(getattr(business, "pending_gin", 0)))
    if ready <= 0:
        return redirect(url_for("assets", msg=f"No gin ready in {user.location} yet. Wait at least 60 seconds."))

    free_space = warehouse_free_space(user)
    if free_space <= 0:
        db.session.commit()
        return redirect(url_for("assets", msg=f"Your warehouse is full. {ready} gin remains waiting in your {user.location} distilleries."))

    collected = min(ready, free_space)
    remaining = ready - collected

    gin_row = warehouse_item(user, "gin")
    gin_row.quantity = int(safe_number(gin_row.quantity)) + collected
    business.pending_gin = remaining

    db.session.commit()

    if remaining > 0:
        msg = f"You collected {collected} gin from {user.location}. Your warehouse is now full, so {remaining} gin stays waiting in the distillery."
    else:
        msg = f"You collected {collected} gin from your {user.location} distilleries."

    return redirect(url_for("assets", msg=msg))


@app.route("/garage")
def garage():
    user, error = login_required()
    if error:
        return error
    return render_page(user, "garage", vehicles=OLDTIMER_VEHICLES, vehicle_categories=vehicle_categories_for_showroom(OLDTIMER_VEHICLES), garages=garage_overview(user), msg=request.args.get("msg"))


@app.route("/garage_action", methods=["POST"])
def garage_action():
    user, error = login_required()
    if error:
        return error

    vehicle_key = request.form.get("vehicle_key")
    vehicle = VEHICLE_BY_KEY.get(vehicle_key)
    if not vehicle:
        return redirect(url_for("garage", msg="Invalid vehicle."))

    price = int(vehicle["price"])
    if safe_number(user.money) < price:
        return redirect(url_for("garage", msg="Not enough cash."))

    ensure_city_vehicles(user)
    row = CityVehicle.query.filter_by(user_id=user.id, city=user.location, vehicle_key=vehicle_key).first()
    if not row:
        row = CityVehicle(user_id=user.id, city=user.location, vehicle_key=vehicle_key, quantity=0)
        db.session.add(row)

    user.money = int(safe_number(user.money)) - price
    user.cars = int(safe_number(user.cars)) + 1
    row.quantity = int(safe_number(row.quantity)) + 1
    db.session.commit()
    return redirect(url_for("garage", msg=f"You bought a {vehicle['year']} {vehicle['name']} in {user.location}."))



@app.route("/protection")
def protection():
    user, error = login_required()
    if error:
        return error
    return render_page(user, "protection", msg=request.args.get("msg"))


@app.route("/protection_action", methods=["POST"])
def protection_action():
    user, error = login_required()
    if error:
        return error

    action = request.form.get("action")
    items = {
        "buy_guard": {"cost": 1000, "attr": "bodyguards", "msg": "You hired 1 bodyguard."},
        "buy_vest": {"cost": 750, "attr": "bulletproof_vests", "msg": "You bought 1 bulletproof vest."},
        "buy_safehouse": {"cost": 5000, "attr": "safehouses", "msg": "You bought 1 safe house."},
        "hire_lookout": {"cost": 1500, "attr": "lookouts", "msg": "You hired 1 street lookout."},
    }
    item = items.get(action)
    if not item:
        return redirect(url_for("protection", msg="Invalid protection option."))
    if safe_number(user.money) < item["cost"]:
        return redirect(url_for("protection", msg="Not enough cash."))

    user.money = safe_number(user.money) - item["cost"]
    current = safe_number(getattr(user, item["attr"]))
    setattr(user, item["attr"], current + 1)
    db.session.commit()
    return redirect(url_for("protection", msg=item["msg"]))


@app.route("/bullets")
def bullets():
    user, error = login_required()
    if error:
        return error
    return render_page(user, "bullets", msg=request.args.get("msg"))


@app.route("/bullet_action", methods=["POST"])
def bullet_action():
    user, error = login_required()
    if error:
        return error
    action = request.form.get("action")
    if action == "buy_bullet":
        if user.money < 200:
            return redirect(url_for("bullets", msg="Not enough cash."))
        user.money -= 200
        user.bullets += 10
        msg = "You bought 10 bullets."
    elif action == "buy_guard":
        return redirect(url_for("protection", msg="Hire bodyguards from the Protection page."))
    else:
        msg = "Invalid action."
    db.session.commit()
    return redirect(url_for("bullets", msg=msg))


@app.route("/kill_action", methods=["POST"])
def kill_action():
    user, error = login_required()
    if error:
        return error
    target_name = request.form.get("target", "").strip()
    bullets_spent = safe_int(request.form.get("bullets_spent"))
    if bullets_spent <= 0:
        return redirect(url_for("bullets", msg="Invalid number of bullets."))
    if user.bullets < bullets_spent:
        return redirect(url_for("bullets", msg="You do not have enough bullets."))
    if target_name.lower() == user.username.lower():
        return redirect(url_for("bullets", msg="You cannot attack yourself."))
    target = User.query.filter_by(username=target_name).first()
    if not target:
        return redirect(url_for("bullets", msg="Target does not exist."))
    if target.is_dead:
        return redirect(url_for("bullets", msg="Target is already dead."))

    user.bullets -= bullets_spent
    attack_bullets = bullets_spent + bullets_spent * rank_bonus(user, "attack") // 100
    needed = 10 + target.bodyguards * 15
    if attack_bullets >= needed:
        target.is_dead = True
        loot = target.money // 2
        target.money -= loot
        user.money += loot
        user.exp += 75
        user.update_rank()
        msg = f"Target eliminated. Loot: ${loot}."
    else:
        guards_lost = min(target.bodyguards, max(1, attack_bullets // 15))
        target.bodyguards -= guards_lost
        msg = f"Attack failed. You destroyed {guards_lost} bodyguard(s)."
    db.session.commit()
    return redirect(url_for("bullets", msg=msg))



@app.route("/heists")
def heists():
    user, error = login_required()
    if error:
        return error
    return render_page(
        user,
        "heists",
        heist_plans=heist_plan_rows(user),
        heist_wait=heist_cooldown_remaining(user),
        heist_cooldown=HEIST_COOLDOWN,
        msg=request.args.get("msg"),
    )


@app.route("/heist_action", methods=["POST"])
def heist_action():
    user, error = login_required()
    if error:
        return error

    wait = heist_cooldown_remaining(user)
    if wait > 0:
        return redirect(url_for("heists", msg=f"The crew is laying low. Try again in {wait} seconds."))

    heist_key = request.form.get("heist_key", "")
    plan = HEIST_PLANS.get(heist_key)
    if not plan:
        return redirect(url_for("heists", msg="Unknown heist plan."))

    if power_score(user) < plan["min_power"]:
        return redirect(url_for("heists", msg=f"Your organization needs at least {plan['min_power']} power for this heist."))
    if safe_number(user.bullets) < plan["bullets"]:
        return redirect(url_for("heists", msg=f"You need {plan['bullets']} bullets for this heist."))

    user.bullets = int(safe_number(user.bullets)) - int(plan["bullets"])
    user.last_heist = time.time()
    chance = heist_success_chance(user, plan)

    if random.randint(1, 100) <= chance:
        cash = random.randint(plan["cash_min"], plan["cash_max"])
        user.money = int(safe_number(user.money)) + cash
        user.exp = int(safe_number(user.exp)) + int(plan["exp"])
        user.heists_successful = int(safe_number(getattr(user, "heists_successful", 0))) + 1
        user.update_rank()
        db.session.commit()
        return redirect(url_for("heists", msg=f"Success: {plan['name']} earned ${cash} and {plan['exp']} EXP."))

    fine = reduce_loss_by_protection(user, max(250, plan["cash_min"] // 3))
    user.money = max(0, int(safe_number(user.money)) - fine)
    user.arrests = int(safe_number(user.arrests)) + 1
    user.jail_until = time.time() + int(plan["jail"])
    user.bribe_available_at = time.time() + int(plan["jail"] * BRIBE_WAIT_RATIO)
    db.session.commit()
    return redirect(url_for("jail", msg=f"The heist failed. You lost ${fine} and were jailed for {plan['jail']} seconds."))


@app.route("/properties")
def properties():
    user, error = login_required()
    if error:
        return error
    return render_page(user, "properties", properties=property_overview(user), msg=request.args.get("msg"))


@app.route("/property_action", methods=["POST"])
def property_action():
    user, error = login_required()
    if error:
        return error

    ensure_user_properties(user)
    action = request.form.get("action")

    if action == "collect_income":
        amount = property_collectable_income(user)
        if amount <= 0:
            return redirect(url_for("properties", msg="No property income is ready yet."))
        user.money = int(safe_number(user.money)) + amount
        user.last_property_collect = time.time()
        db.session.commit()
        return redirect(url_for("properties", msg=f"You collected ${amount} from your properties."))

    if action == "buy_property":
        property_key = request.form.get("property_key")
        data = PROPERTY_TYPES.get(property_key)
        if not data:
            return redirect(url_for("properties", msg="Invalid property."))
        cost = int(data["cost"])
        if safe_number(user.money) < cost:
            return redirect(url_for("properties", msg=f"Not enough cash. {data['name']} costs ${cost}."))
        row = UserProperty.query.filter_by(user_id=user.id, property_key=property_key).first()
        if not row:
            row = UserProperty(user_id=user.id, property_key=property_key, quantity=0)
            db.session.add(row)
        user.money = int(safe_number(user.money)) - cost
        row.quantity = int(safe_number(row.quantity)) + 1
        if safe_number(getattr(user, "last_property_collect", 0)) <= 0:
            user.last_property_collect = time.time()
        db.session.commit()
        return redirect(url_for("properties", msg=f"You bought {data['name']}."))

    return redirect(url_for("properties", msg="Invalid property action."))


@app.route("/licenses")
def licenses():
    user, error = login_required()
    if error:
        return error
    return render_page(user, "licenses", msg=request.args.get("msg"))


def influence_overview(user):
    rows = []
    for key, data in INFLUENCE_TYPES.items():
        row = dict(data)
        row["key"] = key
        row["owned"] = has_influence(user, key)
        rows.append(row)
    return rows


@app.route("/influence")
def influence():
    user, error = login_required()
    if error:
        return error
    return render_page(user, "influence", influences=influence_overview(user), msg=request.args.get("msg"))


@app.route("/influence_action", methods=["POST"])
def influence_action():
    user, error = login_required()
    if error:
        return error

    action = request.form.get("action")
    key = request.form.get("influence_key")
    data = INFLUENCE_TYPES.get(key)
    if action != "buy_influence" or not data:
        return redirect(url_for("influence", msg="Invalid influence action."))

    if has_influence(user, key):
        return redirect(url_for("influence", msg=f"You already control the {data['name']}."))

    cost = int(data["cost"])
    if safe_number(user.money) < cost:
        return redirect(url_for("influence", msg=f"Not enough cash. {data['name']} costs ${cost}."))

    setattr(user, f"{key}_influence", True)
    user.money = int(safe_number(user.money)) - cost
    db.session.commit()
    return redirect(url_for("influence", msg=f"You bought influence over the {data['name']}."))


@app.route("/license_action", methods=["POST"])
def license_action():
    user, error = login_required()
    if error:
        return error

    action = request.form.get("action")
    if action != "purchase_casino_license":
        return redirect(url_for("licenses", msg="Invalid license action."))

    if user.casino_license:
        return redirect(url_for("licenses", msg="You already own a Casino License."))

    user.update_rank()
    if user.rank != CASINO_LICENSE_REQUIRED_RANK and user.rank != "Head of the Shelby Company":
        return redirect(url_for("licenses", msg=f"You need rank {CASINO_LICENSE_REQUIRED_RANK} to buy a Casino License."))

    if safe_number(user.money) < CASINO_LICENSE_COST:
        return redirect(url_for("licenses", msg=f"You need ${CASINO_LICENSE_COST} cash to buy a Casino License."))

    user.money = int(safe_number(user.money)) - CASINO_LICENSE_COST
    user.casino_license = True
    db.session.commit()
    return redirect(url_for("licenses", msg="Casino License purchased. You can now buy casino properties."))


@app.route("/casino")
def casino():
    user, error = login_required()
    if error:
        return error
    ensure_city_casinos()
    for row in all_casinos():
        settle_casino_estate(row)
    db.session.commit()
    return render_page(
        user,
        "casino",
        city_casinos=casinos_for_city(user.location),
        all_casino_rows=all_casinos(),
        casinos_per_city=CASINOS_PER_CITY,
        house_cut=CASINO_HOUSE_CUT_PERCENT,
        msg=request.args.get("msg"),
    )


@app.route("/casino_action", methods=["POST"])
def casino_action():
    user, error = login_required()
    if error:
        return error

    bet = safe_int(request.form.get("bet"))
    game = request.form.get("game", "coin")
    if bet <= 0:
        return redirect(url_for("casino", msg="Invalid bet."))
    if safe_number(user.money) < bet:
        return redirect(url_for("casino", msg="Not enough cash."))

    user.money = int(safe_number(user.money)) - bet
    payout = 0
    msg = ""

    if game == "coin":
        if random.randint(1, 100) <= 49:
            payout = bet * 2
            msg = f"Coin Flip won. You won ${payout - bet} profit."
        else:
            msg = f"Coin Flip lost. You lost ${bet}."

    elif game == "dice":
        roll = random.randint(1, 6)
        if roll == 6:
            payout = bet * 5
            msg = f"You rolled a 6. You won ${payout - bet} profit."
        else:
            msg = f"You rolled {roll}. You lost ${bet}."

    elif game == "slots":
        symbols = ["Cherry", "Bell", "Seven", "Crown"]
        spin = [random.choice(symbols), random.choice(symbols), random.choice(symbols)]
        if spin[0] == spin[1] == spin[2]:
            payout = bet * 10
            msg = f"Slots: {' | '.join(spin)}. Jackpot! You won ${payout - bet} profit."
        elif spin[0] == spin[1] or spin[1] == spin[2] or spin[0] == spin[2]:
            payout = bet * 2
            msg = f"Slots: {' | '.join(spin)}. Small win: ${payout - bet} profit."
        else:
            msg = f"Slots: {' | '.join(spin)}. You lost ${bet}."

    elif game == "roulette":
        choice = request.form.get("choice", "red")
        result = random.choice(["red", "black", "green"])
        if choice == result:
            payout = bet * 2
            msg = f"Roulette landed on {result}. You won ${payout - bet} profit."
        else:
            msg = f"Roulette landed on {result}. You lost ${bet}."

    elif game == "highcard":
        player_card = random.randint(2, 14)
        dealer_card = random.randint(2, 14)
        if player_card > dealer_card:
            payout = bet * 2
            msg = f"High Card: you drew {player_card}, dealer drew {dealer_card}. You won ${payout - bet} profit."
        elif player_card == dealer_card:
            payout = bet
            msg = f"High Card: both drew {player_card}. Push. Your bet was returned."
        else:
            msg = f"High Card: you drew {player_card}, dealer drew {dealer_card}. You lost ${bet}."
    else:
        user.money = int(safe_number(user.money)) + bet
        return redirect(url_for("casino", msg="Invalid casino game."))

    if payout > 0:
        user.money = int(safe_number(user.money)) + payout
        if payout > bet:
            user.exp = int(safe_number(user.exp)) + 3
            user.update_rank()
    else:
        casino_house_income(user.location, bet)

    db.session.commit()
    return redirect(url_for("casino", msg=msg))


@app.route("/casino_property_action", methods=["POST"])
def casino_property_action():
    user, error = login_required()
    if error:
        return error

    ensure_city_casinos()
    action = request.form.get("action")
    casino_id = safe_int(request.form.get("casino_id"))
    casino = CityCasino.query.get(casino_id)

    if not casino:
        return redirect(url_for("casino", msg="Casino license not found."))

    settle_casino_estate(casino)

    if action == "buy":
        if not user.casino_license:
            return redirect(url_for("licenses", msg="You need a Casino License."))
        if user.rank != CASINO_LICENSE_REQUIRED_RANK and user.rank != "Head of the Shelby Company":
            return redirect(url_for("licenses", msg=f"You need rank {CASINO_LICENSE_REQUIRED_RANK} to own a casino."))
        if casino.owner_id == user.id:
            return redirect(url_for("casino", msg="You already own this casino."))

        seller, seller_label = casino_seller(casino)
        price = int(safe_number(casino.price))
        if safe_number(user.money) < price:
            return redirect(url_for("casino", msg=f"Not enough cash. This casino costs ${price}."))

        user.money = int(safe_number(user.money)) - price
        if seller and seller.id != user.id:
            seller.money = int(safe_number(seller.money)) + price

        previous_owner_name = casino.owner.username if casino.owner else "the State"
        casino.owner_id = user.id
        casino.heir_id = None
        casino.vault = 0
        casino.price = int(price * 1.20)
        db.session.commit()
        return redirect(url_for("casino", msg=f"You bought {casino.name} from {seller_label}. Previous owner: {previous_owner_name}."))

    if action == "set_heir":
        if casino.owner_id != user.id:
            return redirect(url_for("casino", msg="You can only set an heir for your own casino."))
        heir_username = request.form.get("heir_username", "").strip()
        if not heir_username:
            casino.heir_id = None
            db.session.commit()
            return redirect(url_for("casino", msg="Casino heir removed."))
        heir = User.query.filter_by(username=heir_username).first()
        if not heir:
            return redirect(url_for("casino", msg="Heir player not found."))
        if heir.id == user.id:
            return redirect(url_for("casino", msg="You cannot set yourself as heir."))
        casino.heir_id = heir.id
        db.session.commit()
        return redirect(url_for("casino", msg=f"{heir.username} is now heir to {casino.name}."))

    if action == "collect_vault":
        if casino.owner_id != user.id:
            return redirect(url_for("casino", msg="You can only collect income from your own casino."))
        amount = int(safe_number(casino.vault))
        if amount <= 0:
            return redirect(url_for("casino", msg="This casino vault is empty."))
        casino.vault = 0
        user.money = int(safe_number(user.money)) + amount
        db.session.commit()
        return redirect(url_for("casino", msg=f"You collected ${amount} from {casino.name}."))

    return redirect(url_for("casino", msg="Invalid casino action."))


@app.route("/territories")
def territories():
    user, error = login_required()
    if error:
        return error
    ensure_city_territories()
    return render_page(
        user,
        "territories",
        territories=all_territories(),
        territory_tax_data=CITY_TERRITORY_DATA,
        territory_war_cost=TERRITORY_WAR_COST,
        territory_war_bullets=TERRITORY_WAR_BULLETS,
        territory_min_members=TERRITORY_MIN_MEMBERS,
        msg=request.args.get("msg"),
    )


@app.route("/territory_action", methods=["POST"])
def territory_action():
    user, error = login_required()
    if error:
        return error

    if not user.family_id or not user.family:
        return redirect(url_for("territories", msg="You need a family before using territory wars."))
    if user.family_role not in ["Boss", "Underboss"]:
        return redirect(url_for("territories", msg="Only the Boss or Underboss can manage territory wars."))

    action = request.form.get("action")
    ensure_city_territories()

    if action == "collect_tax":
        total = 0
        for territory in CityTerritory.query.filter_by(family_id=user.family_id).all():
            ready = territory_tax_ready(territory)
            if ready > 0:
                total += ready
                hours = int((time.time() - safe_number(territory.last_tax_collect)) // 3600)
                territory.last_tax_collect = safe_number(territory.last_tax_collect) + hours * 3600
        if total <= 0:
            return redirect(url_for("territories", msg="No territory taxes are ready yet."))
        user.family.bank = int(safe_number(user.family.bank)) + total
        db.session.commit()
        return redirect(url_for("territories", msg=f"Collected ${total} in territory taxes into the family bank."))

    if action == "attack":
        city = request.form.get("city", "")
        territory = territory_for_city(city)
        if not territory:
            return redirect(url_for("territories", msg="Unknown city."))
        if territory.family_id == user.family_id:
            return redirect(url_for("territories", msg="Your family already controls this city."))
        if family_member_count(user.family) < TERRITORY_MIN_MEMBERS:
            return redirect(url_for("territories", msg=f"You need at least {TERRITORY_MIN_MEMBERS} family members to start a territory war."))
        if safe_number(user.family.bank) < TERRITORY_WAR_COST:
            return redirect(url_for("territories", msg=f"The family bank needs ${TERRITORY_WAR_COST} to declare war."))
        if safe_number(user.bullets) < TERRITORY_WAR_BULLETS:
            return redirect(url_for("territories", msg=f"You need {TERRITORY_WAR_BULLETS} bullets to arm the attack."))
        now = time.time()
        if safe_number(territory.protected_until) > now:
            wait = int(safe_number(territory.protected_until) - now)
            return redirect(url_for("territories", msg=f"This city is protected for {wait} more seconds."))
        if safe_number(territory.last_war_at) + TERRITORY_ATTACK_COOLDOWN > now:
            wait = int((safe_number(territory.last_war_at) + TERRITORY_ATTACK_COOLDOWN) - now)
            return redirect(url_for("territories", msg=f"This city was attacked recently. Try again in {wait} seconds."))

        attacker = user.family
        defender_name = territory.family.name if territory.family else "the State"
        attack_score = war_attack_score(attacker) + random.randint(0, 5000)
        defense_score = war_defense_score(territory) + random.randint(0, 5000)

        attacker.bank = int(safe_number(attacker.bank)) - TERRITORY_WAR_COST
        user.bullets = int(safe_number(user.bullets)) - TERRITORY_WAR_BULLETS
        territory.last_war_at = now
        territory.protected_until = now + TERRITORY_PROTECTION_TIME

        if attack_score >= defense_score:
            territory.family_id = attacker.id
            territory.last_tax_collect = now
            db.session.commit()
            return redirect(url_for("territories", msg=f"🏴 {attacker.name} captured {city} from {defender_name}!"))

        db.session.commit()
        return redirect(url_for("territories", msg=f"⚔️ The attack on {city} failed. {defender_name} held the territory."))

    return redirect(url_for("territories", msg="Invalid territory action."))


@app.route("/ranking")
def ranking():
    user, error = login_required()
    if error:
        return error
    users = User.query.all()
    for u in users:
        u.update_rank()
    db.session.commit()
    users = sorted(users, key=lambda u: (power_score(u), u.money + u.bank), reverse=True)[:100]
    return render_page(user, "ranking", users=users, msg=request.args.get("msg"))


with app.app_context():
    os.makedirs(app.instance_path, exist_ok=True)
    db.create_all()
    migrate_database()
    ensure_city_casinos()
    ensure_city_territories()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
