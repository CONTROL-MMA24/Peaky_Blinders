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

PLAYER_AVATARS = {
    "tommy": {"label": "Thomas Shelby", "initials": "TS", "icon": "🎩", "image": "/static/avatars/tommy.jpg", "price": 250000000, "stars": 5},
    "arthur": {"label": "Arthur Shelby", "initials": "AS", "icon": "🥃", "image": "/static/avatars/arthur.jpg", "price": 150000000, "stars": 5},
    "polly": {"label": "Polly Gray", "initials": "PG", "icon": "♛", "image": "/static/avatars/polly.jpg", "price": 125000000, "stars": 5},
    "alfie": {"label": "Alfie Solomons", "initials": "AL", "icon": "🕯️", "image": "/static/avatars/alfie.jpg", "price": 100000000, "stars": 4},
    "luca": {"label": "Luca Changretta", "initials": "LC", "icon": "♠", "image": "/static/avatars/luca.jpg", "price": 75000000, "stars": 4},
    "michael": {"label": "Michael Gray", "initials": "MG", "icon": "💼", "image": "/static/avatars/michael.jpg", "price": 50000000, "stars": 3},
    "ada": {"label": "Ada Shelby", "initials": "AD", "icon": "◆", "image": "/static/avatars/ada.jpg", "price": 35000000, "stars": 3},
    "mosley": {"label": "Mosley", "initials": "MO", "icon": "⚜️", "image": "/static/avatars/mosley.jpg", "price": 25000000, "stars": 2},
    "jimmy": {"label": "Jimmy McCrory", "initials": "JM", "icon": "☘️", "image": "/static/avatars/jimmy.jpg", "price": 20000000, "stars": 2},
    "finn": {"label": "Finn Shelby", "initials": "FS", "icon": "♣", "image": "/static/avatars/finn.jpg", "price": 15000000, "stars": 1},
    "billy": {"label": "Billy Kimber", "initials": "BK", "icon": "♦", "image": "/static/avatars/billy.jpg", "price": 10000000, "stars": 1},
    "dock_worker": {"label": "Dock Worker", "initials": "DW", "icon": "⚓", "image": "/static/avatars/dock_worker.jpg", "price": 5000000, "stars": 1},
    "street_informant": {"label": "Street Informant", "initials": "SI", "icon": "🚬", "image": "/static/avatars/street_informant.jpg", "price": 2500000, "stars": 1},
    "straat_jongen": {"label": "Street Kid", "initials": "SJ", "icon": "🧢", "image": "/static/avatars/straat_jongen.jpg", "price": 0, "stars": 1},
}


def avatar_info(user):


    key = getattr(user, "avatar_key", None) if user else None
    if key not in PLAYER_AVATARS:
        key = "tommy"
    info = dict(PLAYER_AVATARS[key])
    info["key"] = key
    return info


def owned_avatar_keys(user):
    raw = getattr(user, "owned_avatars", "") if user else ""
    keys = {key.strip() for key in str(raw or "").split(",") if key.strip()}
    if not keys:
        keys = {"straat_jongen"}
    keys = {key for key in keys if key in PLAYER_AVATARS}
    keys.add("straat_jongen")
    return keys


def owns_avatar(user, avatar_key):
    return avatar_key in owned_avatar_keys(user)


def set_owned_avatar_keys(user, keys):
    safe_keys = [key for key in PLAYER_AVATARS.keys() if key in set(keys)]
    if "straat_jongen" not in safe_keys:
        safe_keys.append("straat_jongen")
    user.owned_avatars = ",".join(safe_keys)


def avatar_stars(user):
    return int(avatar_info(user).get("stars", 1))


def avatar_star_text(user):
    stars = avatar_stars(user)
    return "★" * stars + "☆" * (5 - stars)


def avatar_prestige_value(user):
    return int(avatar_info(user).get("price", 0))


PAGE_TITLES = {
    "dashboard": "🏠 Dashboard",
    "messages": "📬 Messages",
    "crime": "⚡ Crimes",
    "bank": "🏦 Bank",
    "market": "🍾 Smuggling",
    "traveling": "✈️ Traveling",
    "cargo": "📦 Cargo",
    "warehouse": "🏚 Warehouse",
    "assets": "🏭 Businesses",
    "properties": "🏛 Properties",
    "garage": "🚗 Garage",
    "casino": "🃏 Casinos",
    "licenses": "🎫 Licenses",
    "influence": "🏛 Influence",
    "family": "👪 Family",
    "territories": "⚔️ Territories",
    "bullets": "🔫 Weapons",
    "protection": "🛡️ Protection",
    "heists": "💼 Heists",
    "jail": "🚔 Jail",
    "ranking": "🏆 Rankings",
    "friends": "👥 Friends",
    "settings": "⚙️ Settings",
}
CRIME_COOLDOWN = 20
TRAVEL_COST = 100
BRIBE_WAIT_RATIO = 0.45
BRIBE_ATTEMPT_COOLDOWN = 15
HONEST_OFFICER_CHANCE = 5
LUCKY_OFFICER_CHANCE = 1

# Jail break settings
# Freeing another prisoner gives EXP, which can immediately improve your rank.
JAIL_BREAK_COST = 25000
JAIL_BREAK_BULLETS = 50
JAIL_BREAK_SUCCESS_CHANCE = 65
JAIL_BREAK_EXP_REWARD = 100
JAIL_BREAK_FAIL_JAIL_CHANCE = 20
JAIL_BREAK_FAIL_JAIL_TIME = 60

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


# Bank economy settings
# Interest can be collected once per hour over the money stored in the bank.
BANK_INTEREST_INTERVAL = 60 * 60
BANK_INTEREST_RATE = 0.005  # 0.5% per hour

BANK_LOAN_LIMITS = {
    "Street Runner": 1000,
    "Shelby Associate": 2500,
    "Made Man": 7500,
    "Crew Leader": 15000,
    "Trusted Lieutenant": 30000,
    "Caporegime": 60000,
    "Chief Enforcer": 125000,
    "Underboss": 250000,
    "Family Boss": 500000,
    "Head of the Shelby Company": 1000000,
}

BANK_LOAN_INTEREST = {
    "Street Runner": 0.20,
    "Shelby Associate": 0.18,
    "Made Man": 0.16,
    "Crew Leader": 0.14,
    "Trusted Lieutenant": 0.12,
    "Caporegime": 0.11,
    "Chief Enforcer": 0.10,
    "Underboss": 0.09,
    "Family Boss": 0.08,
    "Head of the Shelby Company": 0.07,
}

HEIST_COOLDOWN = 90

WEAPON_TYPES = {
    "razor": {"name": "Straight Razor", "price": 1500, "attack": 2, "rarity": "Common", "steal_chance": 28},
    "revolver": {"name": "Webley Revolver", "price": 10000, "attack": 8, "rarity": "Common", "steal_chance": 18},
    "shotgun": {"name": "Sawed-Off Shotgun", "price": 35000, "attack": 18, "rarity": "Rare", "steal_chance": 10},
    "tommy_gun": {"name": "Thompson Submachine Gun", "price": 150000, "attack": 35, "rarity": "Elite", "steal_chance": 5},
    "sniper_rifle": {"name": "Lee-Enfield Rifle", "price": 300000, "attack": 50, "rarity": "Legendary", "steal_chance": 2},
}

WEAPON_THEFT_ARREST_RISK = 22

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

TRAVEL_MODE_WALK_SECONDS = 3 * 60 * 60
TRAVEL_MODE_PUBLIC_SECONDS = 60 * 60
TRAVEL_MODE_FLIGHT_SECONDS = 20 * 60
TRAVEL_MODE_PRIVATE_JET_SECONDS = 2 * 60
TRAVEL_MODE_FASTEST_CAR_SECONDS = 5 * 60

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


# Dynamic smuggling market. Prices move once per hour like a small commodity exchange.
# No database table is required: the current hour, city and item generate stable prices
# for everyone until the next hourly tick.
def market_hour_index(timestamp=None):
    return int((timestamp or time.time()) // 3600)


def _market_hour_delta(city, item_key, hour_index):
    seed = f"{city}:{item_key}:{hour_index}:peaky-market"
    rng = random.Random(seed)
    # Small hourly movement: -6% to +6%.
    return rng.randint(-6, 6) / 100.0


def dynamic_market_multiplier(city, item_key, hour_index=None):
    hour_index = market_hour_index() if hour_index is None else int(hour_index)
    # Short deterministic random walk over the last 12 hours.
    multiplier = 1.0
    for h in range(hour_index - 11, hour_index + 1):
        multiplier *= (1 + _market_hour_delta(city, item_key, h))
    # Keep prices playable and prevent extreme drift.
    return max(0.55, min(1.85, multiplier))


def dynamic_market_price(city, item_key, hour_index=None):
    data = CONTRABAND.get(item_key, {})
    base_price = int(data.get("prices", {}).get(city, MARKET_PRICES.get(city, {}).get(item_key, 0)))
    if base_price <= 0:
        return 0
    return max(1, int(round(base_price * dynamic_market_multiplier(city, item_key, hour_index))))


def market_price_change(city, item_key):
    current_hour = market_hour_index()
    now_price = dynamic_market_price(city, item_key, current_hour)
    previous_price = dynamic_market_price(city, item_key, current_hour - 1)
    return now_price - previous_price


def market_price_trend(city, item_key):
    change = market_price_change(city, item_key)
    if change > 0:
        return "up"
    if change < 0:
        return "down"
    return "flat"


def market_price_board():
    rows = []
    for city in CITIES:
        prices = []
        for key, data in CONTRABAND.items():
            price = dynamic_market_price(city, key)
            change = market_price_change(city, key)
            prices.append({
                "key": key,
                "label": data["label"],
                "price": price,
                "change": change,
                "trend": market_price_trend(city, key),
            })
        rows.append({"city": city, "prices": prices})
    return rows


def price_trend_symbol(trend):
    if trend == "up":
        return "▲"
    if trend == "down":
        return "▼"
    return "■"

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
    {"key": "private_jet", "year": 1930, "name": "Private Jet", "price": 25000000, "bonus": 60},
]

VEHICLE_BY_KEY = {vehicle["key"]: vehicle for vehicle in OLDTIMER_VEHICLES}

# Vehicle resale economy:
# Normal vehicles sell below purchase price.
# Exclusive prestige vehicles can be sold for profit.
EXCLUSIVE_PROFIT_VEHICLES = {"rolls_royce_silver_ghost", "bentley_4_5_litre", "private_jet"}
VEHICLE_RESALE_RATE = 0.65
EXCLUSIVE_VEHICLE_RESALE_RATE = 1.20

def vehicle_sell_price(vehicle):
    if not vehicle:
        return 0
    rate = EXCLUSIVE_VEHICLE_RESALE_RATE if vehicle.get("key") in EXCLUSIVE_PROFIT_VEHICLES else VEHICLE_RESALE_RATE
    return max(1, int(int(vehicle.get("price", 0)) * rate))

VEHICLE_IMAGES = {
    "street_hand_cart": "/static/vehicles/street_hand_cart.jpg",
    "birmingham_courier_bicycle": "/static/vehicles/birmingham_courier_bicycle.jpg",
    "canal_work_horse": "/static/vehicles/canal_work_horse.jpg",
    "raleigh_motor_bicycle": "/static/vehicles/raleigh_motor_bicycle.jpg",
    "horse_goods_cart": "/static/vehicles/horse_goods_cart.jpg",
    "luxury_carriage_pair": "/static/vehicles/luxury_carriage_pair.jpg",
    "ford_model_t": "/static/vehicles/ford_model_t.jpg",
    "austin_12_heavy": "/static/vehicles/austin_12_heavy.jpg",
    "rolls_royce_silver_ghost": "/static/vehicles/rolls_royce_silver_ghost.jpg",
    "bentley_4_5_litre": "/static/vehicles/bentley_4_5_litre.jpg",
    "private_jet": "/static/vehicles/private_jet.jpg",
}


VEHICLE_THEFT_KEYS = ["ford_model_t", "austin_12_heavy", "rolls_royce_silver_ghost", "bentley_4_5_litre", "private_jet"]

STREET_THEFT_VEHICLE_CHANCES = {
    "ford_model_t": 8,
    "austin_12_heavy": 5,
    "rolls_royce_silver_ghost": 2,
    "bentley_4_5_litre": 1,
    "private_jet": 0,
}

PLAYER_THEFT_BASE_CHANCES = {
    "ford_model_t": 60,
    "austin_12_heavy": 55,
    "rolls_royce_silver_ghost": 48,
    "bentley_4_5_litre": 42,
    "private_jet": 18,
}

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
    "private_jet": {"category": "Aviation & Luxury", "tone": "#1e344d", "icon": "PRIVATE JET"},
}

for vehicle in OLDTIMER_VEHICLES:
    vehicle.update(VEHICLE_DESIGN.get(vehicle["key"], {"category": "Transport", "tone": "#555", "icon": "MOTOR"}))
    vehicle["image"] = VEHICLE_IMAGES.get(vehicle["key"], "")

VEHICLE_CATEGORY_ORDER = ["Starter Transport", "Middle Class", "Elite Motors", "Legendary Collection", "Aviation & Luxury"]

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


def vehicle_theft_options():
    return [VEHICLE_BY_KEY[key] for key in VEHICLE_THEFT_KEYS if key in VEHICLE_BY_KEY]


def street_theft_vehicle_roll():
    # Street theft is intentionally low yield. Expensive vehicles are rare, and private jets cannot be found on the street.
    roll = random.randint(1, 100)
    running = 0
    for key, chance in STREET_THEFT_VEHICLE_CHANCES.items():
        running += int(chance)
        if roll <= running and chance > 0:
            return VEHICLE_BY_KEY.get(key)
    return None


def player_vehicle_theft_chance(thief, target, vehicle_key):
    base = int(PLAYER_THEFT_BASE_CHANCES.get(vehicle_key, 35))
    security = (int(safe_number(getattr(target, "bodyguards", 0))) * 5)
    security += (int(safe_number(getattr(target, "safehouses", 0))) * 3)
    security += (int(safe_number(getattr(target, "lookouts", 0))) * 2)
    thief_bonus = rank_bonus(thief, "crime_chance") // 2 + vehicle_bonus(thief) // 4
    return max(8, min(78, base + thief_bonus - security))


def random_player_vehicle_theft_target(thief):
    """Pick a random living player with a stealable vehicle in the thief's current city.

    The thief no longer chooses a username or vehicle. The game searches local
    garages, finds stealable vehicles owned by other active players, and picks
    one target vehicle at random. Players with more valuable garage stock are
    therefore naturally more exposed.
    """
    if not thief or not thief.id:
        return None, None, None

    candidates = []
    rows = CityVehicle.query.filter(
        CityVehicle.city == thief.location,
        CityVehicle.quantity > 0,
        CityVehicle.vehicle_key.in_(VEHICLE_THEFT_KEYS),
        CityVehicle.user_id != thief.id,
    ).all()

    for row in rows:
        target = User.query.get(row.user_id)
        if not target or target.is_dead:
            continue
        vehicle = VEHICLE_BY_KEY.get(row.vehicle_key)
        if not vehicle:
            continue
        # Quantity matters: multiple copies slightly increase the chance that
        # this garage is selected without making one player always guaranteed.
        for _ in range(max(1, min(5, int(safe_number(row.quantity))))):
            candidates.append((target, row, vehicle))

    if not candidates:
        return None, None, None
    return random.choice(candidates)


def add_vehicle_to_city(user, city, vehicle_key, amount=1):
    ensure_city_vehicles(user)
    row = CityVehicle.query.filter_by(user_id=user.id, city=city, vehicle_key=vehicle_key).first()
    if not row:
        row = CityVehicle(user_id=user.id, city=city, vehicle_key=vehicle_key, quantity=0)
        db.session.add(row)
    row.quantity = int(safe_number(row.quantity)) + int(amount)
    user.cars = int(safe_number(getattr(user, "cars", 0))) + int(amount)
    return row


def remove_vehicle_from_city(user, city, vehicle_key, amount=1):
    row = CityVehicle.query.filter_by(user_id=user.id, city=city, vehicle_key=vehicle_key).first()
    if not row or int(safe_number(row.quantity)) < amount:
        return False
    row.quantity = int(safe_number(row.quantity)) - int(amount)
    user.cars = max(0, int(safe_number(getattr(user, "cars", 0))) - int(amount))
    return True


RANKS = [
    (5_000_000_000, "Head of the Shelby Company"),
    (1_000_000_000, "Family Boss"),
    (250_000_000, "Underboss"),
    (50_000_000, "Chief Enforcer"),
    (10_000_000, "Caporegime"),
    (2_500_000, "Trusted Lieutenant"),
    (500_000, "Crew Leader"),
    (100_000, "Made Man"),
    (25_000, "Shelby Associate"),
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




def rank_overview_rows():
    # Show from starter rank to highest rank so players understand the progression.
    return [{"score": needed, "name": name} for needed, name in sorted(RANKS, key=lambda row: row[0])]


def normalize_rank_name(rank_name):
    legacy_rank_map = {
        "Street Kid": "Street Runner",
        "Thug": "Shelby Associate",
        "Gangster": "Made Man",
        "Soldier": "Crew Leader",
        "Capo": "Caporegime",
        "Boss": "Chief Enforcer",
        "Don": "Family Boss",
        "Kingpin": "Underboss",
        "Legend": "Family Boss",
        "Godfather": "Head of the Shelby Company",
    }
    return legacy_rank_map.get(rank_name, rank_name)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    avatar_key = db.Column(db.String(40), default="straat_jongen")
    owned_avatars = db.Column(db.Text, default="straat_jongen")

    money = db.Column(db.Integer, default=500)
    bank = db.Column(db.Integer, default=0)
    bank_loan = db.Column(db.Integer, default=0)
    last_bank_interest = db.Column(db.Float, default=0.0)
    exp = db.Column(db.Integer, default=0)
    rank = db.Column(db.String(60), default="Street Runner")
    location = db.Column(db.String(40), default="Birmingham")
    travel_destination = db.Column(db.String(40), nullable=True)
    travel_arrives_at = db.Column(db.Float, default=0.0)
    travel_mode = db.Column(db.String(80), nullable=True)
    travel_origin = db.Column(db.String(40), nullable=True)
    travel_vehicle_key = db.Column(db.String(60), nullable=True)
    travel_smuggle_item_key = db.Column(db.String(60), nullable=True)
    travel_smuggle_quantity = db.Column(db.Integer, default=0)


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
    last_seen = db.Column(db.Float, default=0.0)

    def update_rank(self):
        if self.exp is None:
            self.exp = 0
        if not self.rank:
            self.rank = "Street Runner"

        try:
            score = rank_progress_score(self)
        except Exception:
            score = int(safe_number(self.exp))

        for needed_score, rank_name in RANKS:
            if score >= needed_score:
                self.rank = rank_name
                break


class Family(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    boss_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    bank = db.Column(db.Integer, default=0)
    bank_loan = db.Column(db.Integer, default=0)
    last_bank_interest = db.Column(db.Float, default=0.0)
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


class UserWeapon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    weapon_key = db.Column(db.String(60), nullable=False)
    quantity = db.Column(db.Integer, default=0)

    user = db.relationship("User", backref=db.backref("weapon_items", lazy=True))






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


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category = db.Column(db.String(30), default="system")
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.Float, default=0.0)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.Float, default=time.time)

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("messages", lazy=True))
    sender = db.relationship("User", foreign_keys=[sender_id])



class Friend(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    accepted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.Float, default=time.time)

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("friend_links_sent", lazy=True))
    friend = db.relationship("User", foreign_keys=[friend_id], backref=db.backref("friend_links_received", lazy=True))

def current_user():
    username = session.get("username")
    if not username:
        return None
    user = User.query.filter_by(username=username).first()
    if user:
        if not getattr(user, "owned_avatars", None):
            user.owned_avatars = "straat_jongen"
        if not getattr(user, "avatar_key", None) or user.avatar_key not in PLAYER_AVATARS:
            user.avatar_key = "straat_jongen"
        if not owns_avatar(user, user.avatar_key):
            user.avatar_key = "straat_jongen"
        user.rank = normalize_rank_name(user.rank)
        user.last_seen = time.time()
        user.update_rank()
        complete_timed_travel(user)
        db.session.commit()
    return user


# Pages that are still available while the player is in jail.
# These are read-only / overview-style pages, plus messages and the jail bribe flow.
# Action endpoints such as crimes, heists, casino games, travel, buying, selling,
# attacking, collecting, and territory wars remain blocked while jailed.
JAIL_ALLOWED_ENDPOINTS = {
    "dashboard",
    "messages",
    "friends",
    "message_action",
    "friend_action",
    "send_player_message",
    "avatar_action",
    "jail",
    "bribe_officer",
    "free_prisoner",
    "ranking",
    "bank",
    "market",
    "cargo",
    "warehouse",
    "family",
    "assets",
    "garage",
    "protection",
    "bullets",
    "heists",
    "properties",
    "licenses",
    "influence",
    "casino",
    "territories",
    "logout",
}


def login_required():
    user = current_user()
    if not user:
        return None, redirect(url_for("index", msg="Please log in first."))
    if user.is_dead:
        session.clear()
        return None, redirect(url_for("index", msg="You were killed by a rival. Create a new account."))

    if safe_number(user.jail_until) > time.time() and request.endpoint not in JAIL_ALLOWED_ENDPOINTS:
        remaining = int(user.jail_until - time.time())
        return None, redirect(url_for("jail", msg=f"You are in jail for {remaining} more seconds. You can still view dashboards, messages, rankings, garages, businesses and other overviews."))

    if is_user_traveling(user) and request.endpoint not in ["traveling", "travel_start", "messages", "message_action", "logout"]:
        return None, redirect(url_for("traveling", msg=f"You are travelling to {user.travel_destination}."))
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


def business_collectable_gin(user, business):
    return min(business_ready_gin(business), warehouse_free_space(user)) if user and business else 0


def local_smuggling_gin_price(user):
    city = getattr(user, "location", "Birmingham") if user else "Birmingham"
    return int(dynamic_market_price(city, "gin"))


def local_buyer_gin_price(user):
    return max(1, int(local_smuggling_gin_price(user) * 0.70))


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
            "price": int(dynamic_market_price(user.location, key)),
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



def ensure_user_weapons(user):
    if not user or not user.id:
        return []
    existing = {row.weapon_key: row for row in UserWeapon.query.filter_by(user_id=user.id).all()}
    changed = False
    for key in WEAPON_TYPES.keys():
        if key not in existing:
            existing[key] = UserWeapon(user_id=user.id, weapon_key=key, quantity=0)
            db.session.add(existing[key])
            changed = True
    if changed:
        db.session.commit()
    return [existing[key] for key in WEAPON_TYPES.keys()]


def weapon_quantity(user, weapon_key):
    if not user or not user.id:
        return 0
    row = UserWeapon.query.filter_by(user_id=user.id, weapon_key=weapon_key).first()
    return int(safe_number(row.quantity)) if row else 0


def weapon_inventory_rows(user):
    ensure_user_weapons(user)
    rows = []
    for key, data in WEAPON_TYPES.items():
        qty = weapon_quantity(user, key)
        rows.append({
            "key": key,
            "name": data["name"],
            "price": int(data["price"]),
            "attack": int(data["attack"]),
            "rarity": data["rarity"],
            "quantity": qty,
            "total_attack": qty * int(data["attack"]),
            "steal_chance": int(data.get("steal_chance", 0)),
        })
    return rows


def total_weapon_power(user):
    if not user or not user.id:
        return 0
    try:
        return sum(row["total_attack"] for row in weapon_inventory_rows(user))
    except Exception:
        return 0


def random_stolen_weapon():
    roll = random.randint(1, 100)
    running = 0
    for key, data in WEAPON_TYPES.items():
        running += int(data.get("steal_chance", 0))
        if roll <= running:
            return key, data
    return None, None


def add_weapon(user, weapon_key, amount=1):
    ensure_user_weapons(user)
    row = UserWeapon.query.filter_by(user_id=user.id, weapon_key=weapon_key).first()
    if not row:
        row = UserWeapon(user_id=user.id, weapon_key=weapon_key, quantity=0)
        db.session.add(row)
    row.quantity = int(safe_number(row.quantity)) + int(amount)
    return row


def create_message(user_id, category, title, body, commit=True, sender_id=None):
    if not user_id:
        return None
    message = Message(
        user_id=user_id,
        category=category or "system",
        title=title,
        body=body,
        is_read=False,
        read_at=0.0,
        sender_id=sender_id,
        created_at=time.time(),
    )
    db.session.add(message)
    if commit:
        db.session.commit()
    return message


def unread_message_count(user):
    if not user or not user.id:
        return 0
    return Message.query.filter_by(user_id=user.id, is_read=False).count()


def message_category_icon(category):
    return {
        "crime": "🚨",
        "cargo": "📦",
        "casino": "🎰",
        "security": "🛡️",
        "family": "👪",
        "territory": "⚔️",
        "travel": "✈️",
        "business": "🏭",
        "system": "⚙️",
        "player": "✉️",
    }.get(category or "system", "📬")


def message_age(message):
    if not message:
        return ""
    elapsed = max(0, int(time.time() - safe_number(message.created_at)))
    if elapsed < 60:
        return f"{elapsed}s ago"
    if elapsed < 3600:
        return f"{elapsed // 60}m ago"
    if elapsed < 86400:
        return f"{elapsed // 3600}h ago"
    return f"{elapsed // 86400}d ago"


def message_rows(user, category=None):
    if not user or not user.id:
        return []
    query = Message.query.filter_by(user_id=user.id)
    if category and category != "all":
        query = query.filter_by(category=category)
    return query.order_by(Message.created_at.desc()).limit(100).all()


def sent_message_rows(user):
    if not user or not user.id:
        return []
    return Message.query.filter_by(sender_id=user.id, category="player").order_by(Message.created_at.desc()).limit(100).all()


def message_read_status(message):
    if not message:
        return ""
    if getattr(message, "is_read", False):
        if safe_number(getattr(message, "read_at", 0)) > 0:
            return f"Opened · {message_age(type('ReadAge', (), {'created_at': message.read_at})())}"
        return "Opened"
    return "Not opened yet"


def process_arrived_shipments(user):
    now = time.time()
    for shipment in Shipment.query.filter_by(user_id=user.id, status="in_transit").all():
        if safe_number(shipment.arrives_at) <= now:
            shipment.status = "arrived"
            label = CONTRABAND.get(shipment.item_key, {"label": shipment.item_key})["label"]
            create_message(
                user.id,
                "cargo",
                "Cargo Arrived",
                f"Your shipment of {int(safe_number(shipment.quantity))} {label} arrived in {shipment.destination}.",
                commit=False,
            )
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
            "value": shipment_value(shipment),
            "progress": shipment_progress(shipment),
        })
    return rows





def shipment_value(shipment):
    data = CONTRABAND.get(shipment.item_key, {})
    prices = data.get("prices", {})
    price = int(dynamic_market_price(shipment.destination, shipment.item_key))
    return int(safe_number(shipment.quantity)) * price


def shipment_progress(shipment):
    if shipment.status in ["arrived", "seized"]:
        return 100
    created = safe_number(shipment.created_at)
    arrives = safe_number(shipment.arrives_at)
    now = time.time()
    total = max(1, arrives - created)
    done = max(0, min(total, now - created))
    return int((done / total) * 100)


def cargo_center_stats(user):
    process_arrived_shipments(user)
    stats = {"active": 0, "arrived": 0, "seized": 0, "value": 0}
    for shipment in Shipment.query.filter_by(user_id=user.id).all():
        if shipment.status == "in_transit":
            stats["active"] += 1
            stats["value"] += shipment_value(shipment)
        elif shipment.status == "arrived":
            stats["arrived"] += 1
            stats["value"] += shipment_value(shipment)
        elif shipment.status == "seized":
            stats["seized"] += 1
    return stats


def shipment_redirect_target():
    target = request.form.get("return_to", "market")
    return "cargo" if target == "cargo" else "market"


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



def rank_progress_score(user):
    """Long-term rank score.

    Ranks are no longer based on raw EXP only. A player must build a full
    criminal empire: activity, wealth, vehicles, properties, smuggling stock,
    heists, influence and family/territory power all contribute.
    """
    if not user:
        return 0

    money = int(safe_number(getattr(user, "money", 0)))
    bank = int(safe_number(getattr(user, "bank", 0)))
    exp = int(safe_number(getattr(user, "exp", 0)))

    bodyguards = int(safe_number(getattr(user, "bodyguards", 0)))
    vests = int(safe_number(getattr(user, "bulletproof_vests", 0)))
    safehouses = int(safe_number(getattr(user, "safehouses", 0)))
    lookouts = int(safe_number(getattr(user, "lookouts", 0)))
    bullets = int(safe_number(getattr(user, "bullets", 0)))
    heists_successful = int(safe_number(getattr(user, "heists_successful", 0)))
    arrests = int(safe_number(getattr(user, "arrests", 0)))

    try:
        cars = total_vehicles(user)
    except Exception:
        cars = int(safe_number(getattr(user, "cars", 0)))

    try:
        distilleries = total_distilleries(user)
    except Exception:
        distilleries = int(safe_number(getattr(user, "distilleries", 0)))

    try:
        warehouse_stock = warehouse_used(user)
    except Exception:
        warehouse_stock = 0

    try:
        properties_score = property_income_per_hour(user) * 10 + property_prestige(user) * 100
    except Exception:
        properties_score = 0

    try:
        influence_score = influence_count(user) * 250_000
    except Exception:
        influence_score = 0

    try:
        casino_score = casino_vault_total(user) // 2 + len(user_casinos(user)) * 500_000
    except Exception:
        casino_score = 0

    try:
        family_score = family_territory_count(user.family) * 1_000_000 if getattr(user, "family", None) else 0
    except Exception:
        family_score = 0

    # Wealth contributes, but cannot carry a player alone.
    wealth_score = (money + bank) // 20

    return int(
        exp
        + wealth_score
        + bodyguards * 2_500
        + vests * 1_000
        + safehouses * 10_000
        + lookouts * 2_000
        + cars * 5_000
        + distilleries * 25_000
        + warehouse_stock * 250
        + bullets * 25
        + total_weapon_power(user) * 5
        + heists_successful * 50_000
        - arrests * 2_500
        + properties_score
        + influence_score
        + casino_score
        + family_score
    )


def next_rank_info(user):
    score = rank_progress_score(user)
    current = None
    next_rank = None

    ordered = sorted(RANKS, key=lambda row: row[0])
    for needed, name in ordered:
        if score >= needed:
            current = (needed, name)
        elif next_rank is None:
            next_rank = (needed, name)

    return {
        "score": score,
        "current": current,
        "next": next_rank,
        "remaining": max(0, (next_rank[0] - score) if next_rank else 0),
    }



def rank_progress_percent(user):
    info = next_rank_info(user)
    current = info.get("current")
    next_rank = info.get("next")
    score = int(info.get("score", 0))
    if not next_rank:
        return 100
    current_score = int(current[0]) if current else 0
    next_score = int(next_rank[0])
    span = max(1, next_score - current_score)
    return max(0, min(100, int(((score - current_score) / span) * 100)))


def power_score(user):
    return rank_progress_score(user)


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



def friendship_between(user_id, other_id):
    if not user_id or not other_id:
        return None
    return Friend.query.filter(
        ((Friend.user_id == user_id) & (Friend.friend_id == other_id)) |
        ((Friend.user_id == other_id) & (Friend.friend_id == user_id))
    ).first()


def friendship_status(user, other):
    if not user or not other or user.id == other.id:
        return "self"
    link = friendship_between(user.id, other.id)
    if not link:
        return "none"
    if link.accepted:
        return "friends"
    if link.user_id == user.id:
        return "sent"
    return "incoming"


def incoming_friend_requests(user):
    if not user or not user.id:
        return []
    return Friend.query.filter_by(friend_id=user.id, accepted=False).order_by(Friend.created_at.desc()).all()


def my_friend_links(user):
    if not user or not user.id:
        return []
    return Friend.query.filter(
        ((Friend.user_id == user.id) | (Friend.friend_id == user.id)) &
        (Friend.accepted == True)
    ).order_by(Friend.created_at.desc()).all()


def friend_user_from_link(user, link):
    if not user or not link:
        return None
    return link.friend if link.user_id == user.id else link.user


def is_online(player):
    return bool(player and safe_number(getattr(player, "last_seen", 0)) > time.time() - 300)


def online_status_text(player):
    return "Online" if is_online(player) else "Offline"


def friend_search_results(user, query):
    if not user or not user.id or not query:
        return []
    q = f"%{query.strip()}%"
    return User.query.filter(
        User.id != user.id,
        User.is_dead == False,
        User.username.ilike(q)
    ).order_by(User.username.asc()).limit(25).all()


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



def is_user_traveling(user):
    return bool(user and getattr(user, "travel_destination", None) and safe_number(getattr(user, "travel_arrives_at", 0)) > time.time())


def complete_timed_travel(user):
    if not user or not getattr(user, "travel_destination", None):
        return False
    if safe_number(getattr(user, "travel_arrives_at", 0)) <= time.time():
        destination = user.travel_destination
        origin = getattr(user, "travel_origin", None) or user.location
        vehicle_key = getattr(user, "travel_vehicle_key", None)
        travel_mode = user.travel_mode or "Travel"

        carried_item_key = getattr(user, "travel_smuggle_item_key", None)
        carried_quantity = int(safe_number(getattr(user, "travel_smuggle_quantity", 0)))
        carried_label = CONTRABAND.get(carried_item_key, {}).get("label", "cargo") if carried_item_key else None

        if destination in CITIES:
            # If the player travelled with their own vehicle, move exactly one vehicle
            # from the origin garage to the destination garage. This keeps the car
            # visible in the city where the player arrives.
            if vehicle_key and origin in CITIES and vehicle_key in VEHICLE_BY_KEY:
                origin_row = CityVehicle.query.filter_by(user_id=user.id, city=origin, vehicle_key=vehicle_key).first()
                destination_row = CityVehicle.query.filter_by(user_id=user.id, city=destination, vehicle_key=vehicle_key).first()
                if not destination_row:
                    destination_row = CityVehicle(user_id=user.id, city=destination, vehicle_key=vehicle_key, quantity=0)
                    db.session.add(destination_row)
                if origin_row and int(safe_number(origin_row.quantity)) > 0:
                    origin_row.quantity = int(safe_number(origin_row.quantity)) - 1
                    destination_row.quantity = int(safe_number(destination_row.quantity)) + 1
            user.location = destination

            # Self-smuggled cargo is removed from the warehouse when the trip starts
            # and returned when the player safely arrives. Since warehouse stock is
            # global in this version, the current location determines where it can be sold.
            if carried_item_key in CONTRABAND and carried_quantity > 0:
                item_row = warehouse_item(user, carried_item_key)
                item_row.quantity = int(safe_number(item_row.quantity)) + carried_quantity

        arrived_city = user.location
        user.travel_destination = None
        user.travel_arrives_at = 0.0
        user.travel_mode = None
        user.travel_origin = None
        user.travel_vehicle_key = None
        user.travel_smuggle_item_key = None
        user.travel_smuggle_quantity = 0
        if carried_item_key in CONTRABAND and carried_quantity > 0:
            create_message(user.id, "travel", "Smuggling Trip Complete", f"You arrived in {arrived_city} by {travel_mode} with {carried_quantity}x {carried_label}.", commit=False)
        else:
            create_message(user.id, "travel", "Travel Complete", f"You arrived in {arrived_city} by {travel_mode}.", commit=False)
        return True
    return False


def travel_remaining(user):
    return max(0, int(safe_number(getattr(user, "travel_arrives_at", 0)) - time.time()))


def vehicle_travel_seconds(vehicle):
    if not vehicle:
        return TRAVEL_MODE_WALK_SECONDS
    if vehicle.get("key") == "private_jet":
        return TRAVEL_MODE_PRIVATE_JET_SECONDS
    price = max(0, int(vehicle.get("price", 0)))
    max_price = max(1, int(VEHICLE_BY_KEY.get("bentley_4_5_litre", {"price": 250000})["price"]))
    ratio = min(1.0, price / max_price)
    seconds = int(TRAVEL_MODE_WALK_SECONDS - ratio * (TRAVEL_MODE_WALK_SECONDS - TRAVEL_MODE_FASTEST_CAR_SECONDS))
    return max(TRAVEL_MODE_FASTEST_CAR_SECONDS, seconds)


def travel_option_rows(user, destination=None):
    ticket = travel_cost_to(destination) if destination in CITIES else DEFAULT_DOMESTIC_TRAVEL_COST
    rows = [
        {"key": "walk", "label": "On Foot", "description": "Free, but very slow.", "seconds": TRAVEL_MODE_WALK_SECONDS, "cost": 0, "available": True},
        {"key": "public", "label": "Public Route", "description": "Train, ferry, or coach ticket.", "seconds": TRAVEL_MODE_PUBLIC_SECONDS, "cost": ticket, "available": True},
        {"key": "flight", "label": "Normal Flight", "description": "Fast commercial travel without cargo.", "seconds": TRAVEL_MODE_FLIGHT_SECONDS, "cost": max(1000, ticket * 3), "available": True},
    ]
    owned = owned_vehicles_in_city(user, user.location)
    for item in owned:
        vehicle = item["vehicle"]
        qty = int(safe_number(item.get("quantity", 0)))
        if qty <= 0:
            continue
        seconds = vehicle_travel_seconds(vehicle)
        fuel_cost = max(25, ticket // 2)
        if vehicle.get("key") == "private_jet":
            fuel_cost = max(500, ticket // 4)
        rows.append({
            "key": "vehicle:" + vehicle["key"],
            "label": vehicle["name"],
            "description": f"Your own vehicle in {user.location}. Owned: {qty}.",
            "seconds": seconds,
            "cost": fuel_cost,
            "available": True,
            "vehicle": vehicle,
        })
    return sorted(rows, key=lambda r: (r["seconds"], r["cost"]))


def travel_option_by_key(user, destination, mode_key):
    for option in travel_option_rows(user, destination):
        if option["key"] == mode_key:
            return option
    return None


def bank_interest_rate(user=None):
    return BANK_INTEREST_RATE


def bank_interest_percent(user=None):
    return round(BANK_INTEREST_RATE * 100, 2)


def bank_interest_remaining(user):
    if not user:
        return BANK_INTEREST_INTERVAL
    last = safe_number(getattr(user, "last_bank_interest", 0))
    if last <= 0:
        return 0
    return max(0, int(BANK_INTEREST_INTERVAL - (time.time() - last)))


def bank_interest_ready(user):
    if not user:
        return 0
    if safe_number(getattr(user, "bank", 0)) <= 0:
        return 0
    if bank_interest_remaining(user) > 0:
        return 0
    return max(1, int(safe_number(user.bank) * BANK_INTEREST_RATE))


def bank_loan_limit(user):
    rank = getattr(user, "rank", "Street Runner") or "Street Runner"
    return int(BANK_LOAN_LIMITS.get(rank, 1000))


def bank_loan_interest_rate(user):
    rank = getattr(user, "rank", "Street Runner") or "Street Runner"
    return float(BANK_LOAN_INTEREST.get(rank, 0.20))


def bank_loan_interest_percent(user):
    return int(round(bank_loan_interest_rate(user) * 100))


def bank_available_credit(user):
    return max(0, bank_loan_limit(user) - int(safe_number(getattr(user, "bank_loan", 0))))


def bank_total_worth(user):
    return int(safe_number(getattr(user, "money", 0))) + int(safe_number(getattr(user, "bank", 0))) - int(safe_number(getattr(user, "bank_loan", 0)))

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
        "travel_destination": "ALTER TABLE user ADD COLUMN travel_destination TEXT DEFAULT NULL",
        "travel_arrives_at": "ALTER TABLE user ADD COLUMN travel_arrives_at FLOAT DEFAULT 0.0",
        "travel_mode": "ALTER TABLE user ADD COLUMN travel_mode TEXT DEFAULT NULL",
        "travel_origin": "ALTER TABLE user ADD COLUMN travel_origin TEXT DEFAULT NULL",
        "travel_vehicle_key": "ALTER TABLE user ADD COLUMN travel_vehicle_key TEXT DEFAULT NULL",
        "travel_smuggle_item_key": "ALTER TABLE user ADD COLUMN travel_smuggle_item_key TEXT DEFAULT NULL",
        "travel_smuggle_quantity": "ALTER TABLE user ADD COLUMN travel_smuggle_quantity INTEGER DEFAULT 0",
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
        "bank_loan": "ALTER TABLE user ADD COLUMN bank_loan INTEGER DEFAULT 0",
        "last_bank_interest": "ALTER TABLE user ADD COLUMN last_bank_interest FLOAT DEFAULT 0.0",
        "last_seen": "ALTER TABLE user ADD COLUMN last_seen FLOAT DEFAULT 0.0",
        "avatar_key": "ALTER TABLE user ADD COLUMN avatar_key TEXT DEFAULT 'straat_jongen'",
        "owned_avatars": "ALTER TABLE user ADD COLUMN owned_avatars TEXT DEFAULT 'straat_jongen'",
    }
    for column, sql in migrations.items():
        if column not in columns:
            cur.execute(sql)

    # Fix old rows that may contain NULL values from earlier versions.
    defaults = {
        "money": 500,
        "bank": 0,
        "bank_loan": 0,
        "last_bank_interest": 0.0,
        "last_seen": 0.0,
        "exp": 0,
        "rank": "Street Runner",
        "location": "Birmingham",
        "avatar_key": "straat_jongen",
        "owned_avatars": "straat_jongen",
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
        "travel_arrives_at": 0.0,
        "travel_smuggle_quantity": 0,
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



    # Family table migrations for existing databases after adding bank loan fields.
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='family'")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(family)")
        family_columns = {row[1] for row in cur.fetchall()}
        family_migrations = {
            "bank_loan": "ALTER TABLE family ADD COLUMN bank_loan INTEGER DEFAULT 0",
            "last_bank_interest": "ALTER TABLE family ADD COLUMN last_bank_interest FLOAT DEFAULT 0.0",
        }
        for column, sql in family_migrations.items():
            if column not in family_columns:
                cur.execute(sql)
        cur.execute("UPDATE family SET bank_loan = 0 WHERE bank_loan IS NULL")
        cur.execute("UPDATE family SET last_bank_interest = 0.0 WHERE last_bank_interest IS NULL")

    # Message table migrations for player-to-player messages and read receipts.
    cur.execute("PRAGMA table_info(message)")
    message_columns = {row[1] for row in cur.fetchall()}
    message_migrations = {
        "sender_id": "ALTER TABLE message ADD COLUMN sender_id INTEGER DEFAULT NULL",
        "read_at": "ALTER TABLE message ADD COLUMN read_at FLOAT DEFAULT 0.0",
    }
    for column, sql in message_migrations.items():
        if column not in message_columns:
            cur.execute(sql)
    cur.execute("UPDATE message SET read_at = 0.0 WHERE read_at IS NULL")

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS message (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            category VARCHAR(30) DEFAULT 'system',
            title VARCHAR(120) NOT NULL,
            body TEXT NOT NULL,
            is_read BOOLEAN DEFAULT 0,
            created_at FLOAT DEFAULT 0.0,
            FOREIGN KEY(user_id) REFERENCES user(id)
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
:root{
 --bg:#0f0f0f;
 --panel:#171717;
 --panel2:#1f1f1f;
 --gold:#d4af37;
 --gold-light:#f5d67b;
 --text:#e8e8e8;
}
body{
 background:var(--bg)!important;
 color:var(--text)!important;
}
.sidebar,.sidebar-panel,.menu{
 background:var(--panel)!important;
}
.card,.panel,.content-card{
 background:var(--panel)!important;
 border:1px solid rgba(212,175,55,.35)!important;
 border-radius:16px!important;
}
a.active,.nav-active,.active-page{
 background:var(--gold)!important;
 color:#000!important;
 font-weight:700!important;
}
.page-title,h1,h2,h3{
 color:var(--gold)!important;
}


/* === AAA reference v2: flush sidebar/content, no divider gap === */
html, body { margin:0!important; padding:0!important; overflow-x:hidden!important; }
.app-shell{
  display:grid!important;
  grid-template-columns:258px minmax(0,1fr)!important;
  gap:0!important;
  column-gap:0!important;
  margin:0!important;
  padding:0!important;
  align-items:stretch!important;
  background:#02080b!important;
}
.sidebar{
  margin:0!important;
  border-radius:0!important;
  box-shadow:none!important;
  z-index:5!important;
}
.content-wrap{
  margin:0!important;
  padding:0!important;
  border-left:0!important;
  min-width:0!important;
  background:linear-gradient(90deg,rgba(2,10,14,.92),rgba(2,10,14,.66) 30%,rgba(2,10,14,.42))!important;
}
.aaa-topbar{
  margin-left:0!important;
  border-left:0!important;
  box-shadow:none!important;
}
.box.aaa-page{
  margin:0!important;
  border-left:0!important;
  padding:24px 26px 34px!important;
  background:
    linear-gradient(90deg,rgba(2,10,14,.86),rgba(2,10,14,.34)),
    radial-gradient(circle at 72% 6%,rgba(217,154,43,.10),transparent 24%)!important;
}
.sidebar + .content-wrap{ margin-left:0!important; }

/* closer to the sent reference image */
.aaa-brand{height:98px!important;align-items:center!important;justify-content:center!important;gap:16px!important;padding:0 4px!important;}
.brand-mark{width:48px!important;height:48px!important;background:rgba(217,154,43,.05)!important;}
.brand-title{font-size:34px!important;letter-spacing:2px!important;}
.aaa-player{border-bottom:1px solid rgba(217,154,43,.25)!important;margin-bottom:8px!important;}
.avatar-frame{width:76px!important;height:76px!important;}
.menu-header:after{content:'›';font-size:24px;line-height:14px;color:var(--aaa-gold2);}
.nav a{position:relative!important;display:flex!important;align-items:center!important;justify-content:space-between!important;min-height:27px!important;}
.nav a.active{background:linear-gradient(90deg,#81500a,#3a2406)!important;}

.aaa-topbar{height:74px!important;}
.top-stat{padding:0 10px!important;}
.top-stat span{filter:drop-shadow(0 0 10px rgba(217,154,43,.28));}
.profile-settings-btn{width:56px;height:48px;border:1px solid rgba(255,204,116,.34);border-radius:50%;display:grid;place-items:center;color:var(--aaa-gold2);background:radial-gradient(circle,#182b33,#01080b 72%);font-size:24px;text-decoration:none;transition:.18s ease}
.profile-settings-btn:hover{transform:translateY(-1px);border-color:rgba(255,204,116,.75);box-shadow:0 0 18px rgba(217,154,43,.28)}

.garage-command{margin-top:0!important;}
.garage-summary-panel{border-radius:6px!important;background:rgba(0,8,12,.76)!important;}
.garage-tabs{margin-top:2px!important;}
.aaa-vehicle-card{border-radius:12px!important;}
.aaa-vehicle-card .vehicle-image{height:260px!important;}
.drive-btn:before{content:'☸ ';}

/* === Sprint 2 Garage: AAA vehicle showroom === */
.page-garage .main,
.page-garage .content{max-width:none!important;}
.page-garage .aaa-hero{display:none!important;}
.garage-stage{position:relative;margin-top:0;padding:0 0 10px;}
.sprint2-command{position:relative;min-height:290px;margin:0 0 18px!important;padding:34px 34px 26px;border:1px solid rgba(229,172,71,.42);border-radius:24px;overflow:hidden;background:linear-gradient(90deg,rgba(2,8,12,.92),rgba(4,13,18,.50) 42%,rgba(36,21,7,.76)),url('/static/page_art/garage_header.jpg') center/cover;box-shadow:0 30px 90px rgba(0,0,0,.44),inset 0 1px 0 rgba(255,232,178,.22);}
.sprint2-command:before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 72% 20%,rgba(238,169,65,.28),transparent 34%),linear-gradient(180deg,rgba(255,255,255,.04),transparent 38%,rgba(0,0,0,.44));pointer-events:none;}
.garage-title-stack{position:relative;z-index:1;max-width:720px;}
.eyebrow{display:inline-flex;align-items:center;gap:8px;margin-bottom:10px;color:#e7b35e;font-size:12px;font-weight:900;letter-spacing:3px;text-transform:uppercase;}
.eyebrow:before{content:"";display:inline-block;width:46px;height:2px;background:linear-gradient(90deg,#e3a23b,transparent);}
.sprint2-command h1{font-family:Georgia,serif!important;font-size:78px!important;letter-spacing:14px!important;line-height:.9!important;margin:0!important;color:#ffe6b4!important;text-shadow:0 8px 34px rgba(0,0,0,.9),0 0 20px rgba(226,159,57,.22)!important;}
.sprint2-command p{font-size:17px!important;max-width:520px;color:#f4e7ce!important;text-shadow:0 2px 8px #000;}
.sprint2-summary{position:absolute;right:22px;bottom:22px;z-index:2;display:grid!important;grid-template-columns:repeat(3,150px) 190px!important;gap:10px!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important;}
.s2-kpi{min-height:86px;padding:13px 14px;border:1px solid rgba(231,179,94,.38);border-radius:16px;background:linear-gradient(145deg,rgba(1,8,12,.78),rgba(34,22,10,.58));box-shadow:inset 0 1px 0 rgba(255,240,198,.16),0 14px 35px rgba(0,0,0,.28);backdrop-filter:blur(5px);}
.s2-kpi small{color:#d99b32!important;letter-spacing:1.5px;font-size:10px!important;}
.s2-kpi b{font-size:25px!important;color:#fff6df!important;line-height:1.2;}
.s2-kpi span{display:block;margin-top:4px;color:#b9a17d;font-size:11px;}
.sprint2-summary .buy-vehicle-btn{display:flex;align-items:center;justify-content:center;min-height:86px;padding:0 18px!important;border-radius:16px!important;font-weight:900;letter-spacing:1.5px;background:linear-gradient(135deg,#ffd074,#b06c13 48%,#693305)!important;color:#160b02!important;border:1px solid #ffe0a0!important;box-shadow:0 0 26px rgba(225,156,47,.28),inset 0 1px 0 rgba(255,255,255,.45)!important;}
.sprint2-tabs{position:sticky;top:78px;z-index:9;max-width:none!important;margin:0 0 22px!important;border-radius:16px!important;border:1px solid rgba(255,204,116,.26)!important;background:rgba(0,8,12,.72)!important;backdrop-filter:blur(8px);box-shadow:0 14px 40px rgba(0,0,0,.24);}
.sprint2-tabs a{flex:1;text-align:center;padding:13px 14px!important;font-weight:800;letter-spacing:1px;color:#ead2a7!important;}
.sprint2-tabs a.active{background:linear-gradient(135deg,#d89b32,#7a4305)!important;color:#fff!important;}
.section-heading-row{display:flex;align-items:end;justify-content:space-between;margin:32px 0 14px;border-bottom:1px solid rgba(218,157,55,.22);padding-bottom:10px;}
.section-heading-row span{color:#b99d70;font-size:12px;text-transform:uppercase;letter-spacing:1.5px;}
.sprint2-section .vehicle-section-title{font-size:25px!important;letter-spacing:2.5px!important;margin:0!important;color:#ffe2ad!important;}
.sprint2-vehicle-grid{display:grid!important;grid-template-columns:repeat(4,minmax(245px,1fr))!important;gap:20px!important;}
.sprint2-vehicle-card{position:relative;overflow:hidden;border-radius:22px!important;border:1px solid rgba(225,166,64,.34)!important;background:linear-gradient(145deg,rgba(4,11,15,.92),rgba(21,16,9,.88))!important;box-shadow:0 20px 55px rgba(0,0,0,.34)!important;transition:transform .22s ease,border-color .22s ease,box-shadow .22s ease;}
.sprint2-vehicle-card:hover{transform:translateY(-5px);border-color:rgba(255,203,111,.72)!important;box-shadow:0 24px 70px rgba(0,0,0,.44),0 0 26px rgba(218,157,55,.18)!important;}
.sprint2-vehicle-card.is-owned{border-color:rgba(125,219,135,.56)!important;}
.sprint2-vehicle-image{height:235px!important;background-position:center!important;background-size:cover!important;position:relative;}
.sprint2-vehicle-image:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(255,211,112,.08),transparent 22%,rgba(0,0,0,.18)),radial-gradient(circle at 50% 90%,rgba(221,152,44,.28),transparent 35%);pointer-events:none;}
.vehicle-year-badge{position:absolute;top:13px;left:13px;z-index:2;padding:6px 10px;border-radius:999px;background:rgba(0,0,0,.58);border:1px solid rgba(255,212,137,.35);color:#ffd886;font-weight:900;font-size:12px;letter-spacing:1px;}
.owned-ribbon{position:absolute;top:13px;right:13px;z-index:2;padding:7px 10px;border-radius:10px;background:linear-gradient(135deg,#2e7e36,#163b1b);border:1px solid rgba(166,255,177,.42);color:#e6ffe9;font-weight:900;font-size:11px;letter-spacing:1px;}
.sprint2-nameplate{z-index:2!important;left:18px!important;right:18px!important;bottom:15px!important;text-shadow:0 3px 14px #000!important;}
.sprint2-nameplate .icon{font-family:Georgia,serif;font-size:24px!important;line-height:1.05;color:#fff1d0!important;text-transform:uppercase;letter-spacing:1px;}
.sprint2-nameplate .year{font-size:12px!important;color:#e3a23b!important;font-weight:900;letter-spacing:1.4px;text-transform:uppercase;}
.sprint2-vehicle-body{padding:16px!important;}
.sprint2-specs{display:grid!important;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 13px!important;}
.sprint2-specs span{display:block!important;text-align:center;border:1px solid rgba(218,157,55,.22);background:rgba(0,0,0,.26);border-radius:12px;padding:9px 6px!important;font-size:10px!important;color:#bfa982!important;letter-spacing:1px;}
.sprint2-specs b{display:block;margin-top:4px;color:#fff4d8;font-size:12px;letter-spacing:0;}
.sprint2-meta{display:grid!important;grid-template-columns:1.35fr .65fr!important;gap:10px!important;margin-bottom:13px;}
.sprint2-meta div{border-radius:14px!important;padding:12px!important;border:1px solid rgba(218,157,55,.20);background:linear-gradient(145deg,rgba(0,0,0,.32),rgba(255,183,69,.06));}
.sprint2-buy-btn{width:100%;height:44px;border-radius:14px!important;background:linear-gradient(135deg,#c88820,#7a4106)!important;font-weight:900;letter-spacing:1.5px;}
.sprint2-city-grid .garage-city-card{border-radius:18px!important;}
@media(max-width:1500px){.sprint2-vehicle-grid{grid-template-columns:repeat(3,minmax(230px,1fr))!important}.sprint2-summary{position:relative;right:auto;bottom:auto;margin-top:24px;grid-template-columns:repeat(2,minmax(160px,1fr))!important}.sprint2-summary .buy-vehicle-btn{grid-column:1/-1}}
@media(max-width:920px){.sprint2-command{padding:24px 18px}.sprint2-command h1{font-size:46px!important;letter-spacing:6px!important}.sprint2-vehicle-grid{grid-template-columns:1fr!important}.sprint2-tabs{position:relative;top:auto;overflow:auto}.sprint2-tabs a{min-width:140px}.sprint2-summary{grid-template-columns:1fr!important}}



/* === Sprint 4: Crime & Heists Operation Center === */
.s4-ops-wrap{display:grid;gap:22px;}
.s4-hero{position:relative;overflow:hidden;border:1px solid rgba(217,154,43,.42);border-radius:24px;padding:30px 32px;background:linear-gradient(135deg,rgba(2,10,14,.96),rgba(18,13,8,.74)),radial-gradient(circle at 80% 10%,rgba(217,154,43,.18),transparent 32%);box-shadow:0 24px 70px rgba(0,0,0,.40),inset 0 1px 0 rgba(255,236,184,.14)}
.s4-hero:before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(255,207,116,.06),transparent 30%,rgba(0,0,0,.28)),repeating-linear-gradient(120deg,rgba(255,255,255,.025) 0 1px,transparent 1px 16px);pointer-events:none;}
.s4-hero > *{position:relative;z-index:1}.s4-eyebrow{display:inline-flex;align-items:center;gap:8px;color:#e7b35e;font-size:12px;font-weight:900;letter-spacing:3px;text-transform:uppercase}.s4-eyebrow:before{content:"";display:inline-block;width:48px;height:2px;background:linear-gradient(90deg,#e3a23b,transparent)}
.s4-hero h1{margin:8px 0 8px!important;font-family:Georgia,serif!important;font-size:54px!important;letter-spacing:7px!important;line-height:.95!important;color:#ffe6b4!important;text-shadow:0 8px 34px rgba(0,0,0,.8),0 0 20px rgba(226,159,57,.20)!important}.s4-hero p{max-width:760px;color:#f4e7ce!important;font-size:16px!important;line-height:1.55}.s4-hero-grid{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:end}.s4-cooldown{min-width:270px;border:1px solid rgba(255,204,116,.28);border-radius:18px;padding:14px 16px;background:rgba(0,8,12,.62);box-shadow:inset 0 1px 0 rgba(255,255,255,.08)}.s4-cooldown small{display:block;color:#d99b32;text-transform:uppercase;letter-spacing:1.5px;font-size:10px;margin-bottom:6px}.s4-cooldown b{font-size:24px;color:#fff3d4}.s4-bar{height:9px;border-radius:999px;background:rgba(255,255,255,.10);overflow:hidden;margin-top:10px}.s4-bar span{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#603205,#d99a2b,#ffcc74);box-shadow:0 0 16px rgba(217,154,43,.32)}
.s4-stats{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:12px}.s4-stat{border:1px solid rgba(217,154,43,.27);border-radius:16px;padding:13px 14px;background:linear-gradient(145deg,rgba(1,8,12,.76),rgba(34,22,10,.48));box-shadow:0 14px 35px rgba(0,0,0,.24)}.s4-stat small{display:block;color:#d99b32;text-transform:uppercase;letter-spacing:1.5px;font-size:10px}.s4-stat b{display:block;color:#fff4da;font-size:23px;margin-top:4px}.s4-section-head{display:flex;justify-content:space-between;align-items:end;margin:6px 0 -4px;padding-bottom:10px;border-bottom:1px solid rgba(217,154,43,.18)}.s4-section-head h2{margin:0!important;color:#ffe1aa!important;letter-spacing:2.5px!important}.s4-section-head span{color:#b99d70;text-transform:uppercase;letter-spacing:1.4px;font-size:12px}.s4-grid{display:grid;grid-template-columns:repeat(3,minmax(250px,1fr));gap:18px}.s4-grid.two{grid-template-columns:repeat(2,minmax(280px,1fr))}.s4-operation-card{position:relative;overflow:hidden;border-radius:22px;border:1px solid rgba(225,166,64,.34);background:linear-gradient(145deg,rgba(4,11,15,.92),rgba(21,16,9,.88));box-shadow:0 20px 55px rgba(0,0,0,.32);padding:18px;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}.s4-operation-card:hover{transform:translateY(-4px);border-color:rgba(255,203,111,.70);box-shadow:0 26px 70px rgba(0,0,0,.44),0 0 24px rgba(218,157,55,.16)}.s4-operation-card:before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 82% 0%,rgba(217,154,43,.13),transparent 34%);pointer-events:none}.s4-card-top,.s4-card-body,.s4-card-actions{position:relative;z-index:1}.s4-card-top{display:flex;justify-content:space-between;gap:10px;align-items:start;margin-bottom:14px}.s4-icon{width:48px;height:48px;border:1px solid rgba(255,204,116,.32);border-radius:16px;display:grid;place-items:center;background:radial-gradient(circle,#24343a,#01080b 72%);font-size:24px;box-shadow:inset 0 1px 0 rgba(255,255,255,.12)}.s4-title h3{margin:0 0 5px!important;color:#ffe6b4!important;font-size:23px!important;letter-spacing:1.6px!important}.s4-title p{margin:0;color:#b9a88f;font-size:13px;line-height:1.45}.s4-risk{display:inline-flex;align-items:center;justify-content:center;white-space:nowrap;border-radius:999px;padding:6px 10px;font-size:10px;font-weight:900;letter-spacing:1.4px;text-transform:uppercase;border:1px solid rgba(255,255,255,.18)}.risk-low{color:#dfffe6;background:rgba(29,105,42,.32);border-color:rgba(123,237,139,.38)}.risk-medium{color:#fff0c8;background:rgba(140,90,18,.34);border-color:rgba(255,202,89,.40)}.risk-high{color:#ffe0d0;background:rgba(143,46,20,.34);border-color:rgba(255,116,69,.36)}.risk-extreme{color:#ffd6d6;background:rgba(132,22,33,.40);border-color:rgba(255,82,96,.44)}.s4-metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:14px 0}.s4-metric{background:rgba(0,0,0,.25);border:1px solid rgba(214,168,95,.14);border-radius:13px;padding:10px}.s4-metric small{display:block;color:#b9a88f;text-transform:uppercase;letter-spacing:1.1px;font-size:10px;margin-bottom:3px}.s4-metric b{color:#fff2d2;font-size:16px}.s4-success-ring{height:10px;background:rgba(255,255,255,.10);border-radius:999px;overflow:hidden;margin-top:8px}.s4-success-ring span{display:block;height:100%;background:linear-gradient(90deg,#7a320d,#d99a2b,#ffcc74);border-radius:999px}.s4-select{width:100%;margin:8px 0 12px}.s4-card-actions .btn,.s4-action-btn{width:100%;min-height:44px;border-radius:14px!important;font-weight:900!important;letter-spacing:1.4px!important;text-transform:uppercase!important}.s4-note{font-size:12px;color:#b9a88f;line-height:1.45;margin-top:9px}.s4-disabled{opacity:.66;filter:grayscale(.18)}.s4-warning{border:1px solid rgba(255,111,85,.34);background:linear-gradient(145deg,rgba(75,20,10,.55),rgba(10,8,6,.65));border-radius:16px;padding:12px;color:#ffd6c7}.s4-success-panel{border:1px solid rgba(123,237,139,.35);background:linear-gradient(145deg,rgba(19,72,28,.42),rgba(5,12,7,.78));border-radius:18px;padding:16px}.s4-failure-panel{border:1px solid rgba(255,82,96,.35);background:linear-gradient(145deg,rgba(93,18,25,.42),rgba(12,5,6,.78));border-radius:18px;padding:16px}.s4-jail-panel{border:1px solid rgba(255,202,89,.35);background:linear-gradient(145deg,rgba(100,62,8,.42),rgba(12,8,4,.78));border-radius:18px;padding:16px}.s4-mini-feed{display:grid;gap:10px}.s4-mini-row{display:flex;justify-content:space-between;gap:6px;border:1px solid rgba(214,168,95,.14);background:rgba(0,0,0,.18);border-radius:13px;padding:10px}.s4-mini-row b{color:#fff2d2}.s4-mini-row small{display:block;color:#b9a88f;margin-top:2px}.s4-footer-grid{display:grid;grid-template-columns:1.2fr .8fr;gap:18px}.s4-briefing{border:1px solid rgba(217,154,43,.24);border-radius:18px;padding:16px;background:rgba(0,8,12,.42)}.s4-briefing h3{margin-top:0!important;color:#ffcc74!important}.s4-briefing ul{margin:0;padding-left:18px;color:#d9ccb6;line-height:1.75}.s4-route-buttons{display:grid;gap:10px}.s4-route-buttons a{display:flex;justify-content:space-between;align-items:center;border:1px solid rgba(217,154,43,.24);border-radius:14px;padding:12px;text-decoration:none;background:rgba(0,0,0,.20);color:#f7ead8!important}.s4-route-buttons a:hover{border-color:#d99a2b;background:rgba(217,154,43,.10)}@media(max-width:1250px){.s4-grid{grid-template-columns:repeat(2,minmax(250px,1fr))}.s4-hero-grid,.s4-footer-grid{grid-template-columns:1fr}.s4-cooldown{min-width:0}.s4-stats{grid-template-columns:repeat(2,minmax(140px,1fr))}}@media(max-width:760px){.s4-grid,.s4-grid.two{grid-template-columns:1fr}.s4-hero h1{font-size:38px!important;letter-spacing:4px!important}.s4-stats,.s4-metrics{grid-template-columns:1fr}}


/* === Sprint 5: Family & Territories Command Center === */
.s5-wrap{display:flex;flex-direction:column;gap:20px}.s5-hero{position:relative;overflow:hidden;border:1px solid rgba(217,154,43,.28);border-radius:28px;padding:34px;background:linear-gradient(120deg,rgba(3,8,12,.96),rgba(14,28,31,.78),rgba(144,91,25,.22)),radial-gradient(circle at 82% 18%,rgba(217,154,43,.28),transparent 32%);box-shadow:0 26px 90px rgba(0,0,0,.38),inset 0 1px 0 rgba(255,255,255,.08)}.s5-hero:before{content:"";position:absolute;inset:-60px;background:linear-gradient(135deg,transparent 0 48%,rgba(255,220,150,.08) 49%,transparent 50% 100%);opacity:.5}.s5-eyebrow{position:relative;z-index:1;color:#d99a2b;text-transform:uppercase;letter-spacing:2.8px;font-weight:900;font-size:12px}.s5-hero h1{position:relative;z-index:1;margin:10px 0 10px;color:#fff0c8;font-family:Georgia,serif;font-size:58px;letter-spacing:6px;line-height:.92;text-shadow:0 8px 38px rgba(0,0,0,.85)}.s5-hero p{position:relative;z-index:1;margin:0;max-width:820px;color:#f4e7ce;line-height:1.55}.s5-stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.s5-stat{border:1px solid rgba(217,154,43,.22);border-radius:20px;padding:18px;background:linear-gradient(180deg,rgba(255,255,255,.065),rgba(255,255,255,.02));box-shadow:0 16px 44px rgba(0,0,0,.24),inset 0 1px 0 rgba(255,255,255,.07)}.s5-stat small{display:block;color:#bfb1a0;text-transform:uppercase;letter-spacing:1.4px;font-size:11px}.s5-stat b{display:block;margin-top:8px;color:#ffe6b4;font-size:25px}.s5-command-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:18px}.s5-panel{border:1px solid rgba(217,154,43,.22);border-radius:24px;padding:22px;background:rgba(3,10,14,.72);box-shadow:0 20px 58px rgba(0,0,0,.30),inset 0 1px 0 rgba(255,255,255,.06)}.s5-panel h2,.s5-panel h3{margin:0 0 14px;color:#fff0c8;font-family:Georgia,serif;letter-spacing:1.6px}.s5-panel p{color:#e8ddcc}.s5-treasury{display:grid;gap:12px}.s5-money{font-size:42px;color:#7dffb1;font-weight:900;text-shadow:0 0 24px rgba(125,255,177,.14)}.s5-form-row{display:grid;grid-template-columns:1fr auto auto;gap:10px;align-items:end}.s5-form-row .input{width:100%}.s5-bonus-list{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.s5-bonus{padding:14px;border-radius:16px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08)}.s5-bonus small{display:block;color:#bfb1a0;text-transform:uppercase;font-size:10px;letter-spacing:1.4px}.s5-bonus b{color:#d99a2b;font-size:20px}.s5-member-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}.s5-member{position:relative;overflow:hidden;border-radius:20px;border:1px solid rgba(217,154,43,.20);padding:18px;background:linear-gradient(150deg,rgba(255,255,255,.07),rgba(255,255,255,.025));box-shadow:0 16px 42px rgba(0,0,0,.25)}.s5-member:before{content:"";position:absolute;right:-35px;top:-35px;width:110px;height:110px;border-radius:50%;background:rgba(217,154,43,.12)}.s5-avatar{width:48px;height:48px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#281707,#d99a2b);border:1px solid rgba(255,222,166,.46);color:#fff0c8;font-family:Georgia,serif;font-weight:900}.s5-member h3{margin:12px 0 4px;color:#fff}.s5-role{display:inline-flex;padding:5px 10px;border-radius:999px;background:rgba(217,154,43,.14);border:1px solid rgba(217,154,43,.28);color:#ffd58b;font-size:11px;text-transform:uppercase;letter-spacing:1px}.s5-member dl{display:grid;grid-template-columns:1fr auto;gap:8px;margin:14px 0 0}.s5-member dt{color:#bfb1a0}.s5-member dd{margin:0;color:#fff0c8;font-weight:800}.s5-territory-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}.s5-territory{position:relative;overflow:hidden;border:1px solid rgba(217,154,43,.22);border-radius:24px;background:linear-gradient(150deg,rgba(10,22,26,.86),rgba(3,8,12,.76));box-shadow:0 22px 60px rgba(0,0,0,.28)}.s5-territory .top{padding:20px 20px 12px;border-bottom:1px solid rgba(255,255,255,.07);background:radial-gradient(circle at right top,rgba(217,154,43,.18),transparent 42%)}.s5-territory h3{margin:0;color:#fff0c8;font-family:Georgia,serif;font-size:25px;letter-spacing:2px}.s5-territory .body{padding:18px 20px 20px}.s5-line{display:flex;justify-content:space-between;gap:16px;margin:10px 0;color:#e8ddcc}.s5-line span{color:#bfb1a0}.s5-line b{color:#fff0c8;text-align:right}.s5-status{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:6px 10px;font-size:11px;text-transform:uppercase;letter-spacing:1px;font-weight:900}.s5-status.state{background:rgba(80,160,255,.13);color:#8fc4ff;border:1px solid rgba(80,160,255,.24)}.s5-status.owned{background:rgba(125,255,177,.12);color:#91ffc0;border:1px solid rgba(125,255,177,.24)}.s5-status.enemy{background:rgba(255,92,92,.12);color:#ffb1a7;border:1px solid rgba(255,92,92,.24)}.s5-status.protected{background:rgba(217,154,43,.14);color:#ffd58b;border:1px solid rgba(217,154,43,.28)}.s5-war-room{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.s5-war{border-radius:18px;padding:15px;background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.08)}.s5-war small{display:block;color:#bfb1a0;text-transform:uppercase;letter-spacing:1.2px;font-size:10px}.s5-war b{display:block;margin-top:7px;color:#ffe6b4;font-size:19px}.s5-rank-table{width:100%;border-collapse:separate;border-spacing:0 8px}.s5-rank-table th{color:#d99a2b;text-transform:uppercase;font-size:11px;letter-spacing:1.5px;text-align:left}.s5-rank-table td{background:rgba(255,255,255,.045);border-top:1px solid rgba(255,255,255,.07);border-bottom:1px solid rgba(255,255,255,.07);padding:12px}.s5-rank-table td:first-child{border-left:1px solid rgba(255,255,255,.07);border-radius:14px 0 0 14px}.s5-rank-table td:last-child{border-right:1px solid rgba(255,255,255,.07);border-radius:0 14px 14px 0}@media(max-width:1000px){.s5-stat-grid,.s5-war-room{grid-template-columns:repeat(2,1fr)}.s5-command-grid{grid-template-columns:1fr}.s5-form-row{grid-template-columns:1fr}.s5-bonus-list{grid-template-columns:1fr}}@media(max-width:640px){.s5-stat-grid,.s5-war-room{grid-template-columns:1fr}.s5-hero h1{font-size:40px}.s5-territory-grid{grid-template-columns:1fr}}


/* Sprint bank upgrade */
.s-bank-hero{border-color:rgba(216,155,50,.35)}
.s-bank-form{margin-top:14px;display:flex;flex-direction:column;gap:12px}
.s-bank-actions{display:flex;gap:10px;flex-wrap:wrap}
.s-bank-actions .btn{flex:1;min-width:120px}
.s3-panel .red{color:#ff7b7b}


.language-picker{display:flex;align-items:center;gap:6px;justify-content:flex-end;min-width:72px;padding-left:0}
.language-picker label{display:none!important}
.language-select{appearance:none;background:linear-gradient(135deg,rgba(5,14,18,.95),rgba(28,18,7,.92));border:1px solid rgba(217,154,43,.42);color:#ffe7b0;border-radius:10px;padding:9px 24px 9px 10px;font-size:12px;font-weight:800;width:72px;max-width:72px;cursor:pointer;box-shadow:0 10px 28px rgba(0,0,0,.22)}
.language-picker:after{content:"▾";margin-left:-22px;color:#d99a2b;pointer-events:none;font-size:11px}
.language-select option{background:#071015;color:#ffe7b0}
@media(max-width:900px){.language-picker{justify-content:flex-start;padding:8px 0}.language-select{max-width:72px}}


.avatar-image-frame{overflow:hidden;padding:0!important;background:#03080b!important}
.avatar-img{width:100%;height:100%;object-fit:cover;display:block}
.avatar-picker-form{text-decoration:none}
.settings-profile-hero{display:grid;grid-template-columns:220px 1fr;gap:24px;align-items:center;margin-bottom:22px}
.settings-current-avatar{width:180px;height:240px;border:1px solid rgba(217,154,43,.55);border-radius:14px;overflow:hidden;box-shadow:0 0 28px rgba(217,154,43,.22);background:#04080a}
.settings-current-avatar img{width:100%;height:100%;object-fit:cover}
.avatar-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;margin-top:18px}
.avatar-choice{border:1px solid rgba(217,154,43,.30);border-radius:14px;overflow:hidden;background:linear-gradient(145deg,rgba(5,10,13,.96),rgba(24,18,12,.92));box-shadow:0 10px 24px rgba(0,0,0,.28)}
.avatar-choice img{width:100%;height:210px;object-fit:cover;display:block}
.avatar-choice .avatar-label{padding:10px;text-align:center;color:#f5d58f;font-family:Georgia,serif;font-weight:800;letter-spacing:.8px}
.avatar-choice button{width:100%;border-radius:0;border-left:0;border-right:0;border-bottom:0}
.avatar-choice.is-selected{border-color:#ffd47a;box-shadow:0 0 24px rgba(217,154,43,.30)}

.avatar-price{padding:0 10px 10px;text-align:center;color:#fff;font-size:13px}.avatar-price span{color:#d9b56d;font-weight:800}
.ranking-avatar{width:34px;height:34px;border-radius:50%;overflow:hidden;display:inline-block;vertical-align:middle;border:1px solid rgba(217,154,43,.55);margin-right:8px}.ranking-avatar img{width:100%;height:100%;object-fit:cover;display:block}

/* Exclusive Top 10 Rankings */
.ranking-top10{
    position:relative;
    background:linear-gradient(90deg,rgba(217,154,43,.18),rgba(12,18,22,.92))!important;
    box-shadow:inset 4px 0 0 #d99a2b,0 0 18px rgba(217,154,43,.18);
}
.ranking-top10 td{
    border-top:1px solid rgba(255,212,122,.32)!important;
    border-bottom:1px solid rgba(255,212,122,.20)!important;
}
.ranking-place-badge{
    display:inline-grid;
    place-items:center;
    min-width:36px;
    height:28px;
    padding:0 8px;
    border-radius:999px;
    border:1px solid rgba(255,212,122,.55);
    background:radial-gradient(circle at 50% 30%,rgba(255,220,130,.35),rgba(86,50,5,.75));
    color:#ffe4a3;
    font-weight:900;
    letter-spacing:.5px;
    box-shadow:0 0 16px rgba(217,154,43,.25);
}
.ranking-top3 .ranking-place-badge{
    min-width:42px;
    height:32px;
    font-size:15px;
    border-color:#ffe08a;
    box-shadow:0 0 24px rgba(255,212,122,.38);
}
.ranking-title-crown{
    color:#ffd47a;
    margin-left:6px;
    text-shadow:0 0 10px rgba(217,154,43,.45);
}


/* Ranking Search */
.ranking-search-card{
    margin:0 0 18px;
    padding:16px;
    border:1px solid rgba(217,154,43,.28);
    border-radius:14px;
    background:linear-gradient(135deg,rgba(5,10,13,.92),rgba(24,18,12,.78));
}
.ranking-search-form{
    display:grid;
    grid-template-columns:1fr auto;
    gap:10px;
    align-items:end;
}
.ranking-search-result{
    margin-top:14px;
    padding:14px;
    border-radius:12px;
    border:1px solid rgba(255,212,122,.30);
    background:rgba(0,0,0,.25);
    display:grid;
    grid-template-columns:auto 1fr;
    gap:14px;
    align-items:center;
}
.ranking-search-rank{
    min-width:72px;
    height:52px;
    display:grid;
    place-items:center;
    border-radius:999px;
    border:1px solid rgba(255,212,122,.60);
    color:#ffe4a3;
    font-weight:900;
    background:radial-gradient(circle at 50% 30%,rgba(255,220,130,.32),rgba(86,50,5,.72));
    box-shadow:0 0 18px rgba(217,154,43,.24);
}
.ranking-search-meta{
    display:flex;
    flex-wrap:wrap;
    gap:12px;
    color:#d8c7aa;
}
.ranking-search-meta b{color:#ffd47a}


/* Message delete button: black by default, red/light on hover or click */
.btn-delete{
    background:linear-gradient(180deg,#151515,#030303)!important;
    color:#d8c7aa!important;
    border:1px solid rgba(255,255,255,.18)!important;
    box-shadow:none!important;
}
.btn-delete:hover{
    background:linear-gradient(180deg,#7b1111,#260404)!important;
    color:#fff!important;
    border-color:#ff5c5c!important;
    box-shadow:0 0 16px rgba(255,60,60,.32)!important;
}
.btn-delete:active{
    background:#b31313!important;
    color:#fff!important;
    transform:translateY(1px);
}


/* Rank Overview under Top 100 */
.rank-overview-card{
    margin-top:22px;
    padding:18px;
    border:1px solid rgba(217,154,43,.28);
    border-radius:14px;
    background:linear-gradient(135deg,rgba(5,10,13,.94),rgba(24,18,12,.78));
}
.rank-overview-grid{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
    gap:12px;
    margin-top:14px;
}
.rank-overview-row{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    padding:12px;
    border:1px solid rgba(255,212,122,.18);
    border-radius:12px;
    background:rgba(0,0,0,.24);
}
.rank-overview-row b{
    color:#ffd47a;
}
.rank-overview-row span{
    color:#d8c7aa;
    font-size:13px;
}
.rank-overview-row.top-rank{
    border-color:rgba(255,212,122,.55);
    box-shadow:0 0 18px rgba(217,154,43,.18);
    background:linear-gradient(90deg,rgba(217,154,43,.16),rgba(0,0,0,.24));
}


/* Rankings: player position and next-rank progress */
.ranking-player-panel{
    margin:0 0 18px;
    padding:18px;
    border:1px solid rgba(217,154,43,.34);
    border-radius:14px;
    background:linear-gradient(135deg,rgba(6,12,15,.96),rgba(28,20,10,.82));
    box-shadow:0 0 22px rgba(0,0,0,.28);
}
.ranking-player-grid{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
    gap:12px;
    margin-top:12px;
}
.ranking-player-stat{
    padding:12px;
    border:1px solid rgba(255,212,122,.20);
    border-radius:12px;
    background:rgba(0,0,0,.25);
}
.ranking-player-stat small{
    display:block;
    color:#a99779;
    font-size:11px;
    letter-spacing:1px;
    text-transform:uppercase;
}
.ranking-player-stat b{
    display:block;
    color:#ffd47a;
    font-size:18px;
    margin-top:4px;
}
.rank-progress-track{
    height:11px;
    border-radius:999px;
    background:rgba(255,255,255,.12);
    overflow:hidden;
    border:1px solid rgba(255,212,122,.18);
    margin-top:10px;
}
.rank-progress-track span{
    display:block;
    height:100%;
    border-radius:999px;
    background:linear-gradient(90deg,#8d5a0b,#ffd47a);
    box-shadow:0 0 16px rgba(217,154,43,.34);
}
.rank-next-note{
    color:#d8c7aa;
    margin-top:8px;
    font-size:13px;
}

</style>
<style>
:root { --bg:#080808; --panel:rgba(20,20,20,.92); --gold:#d6a85f; --gold2:#9b6a32; --wine:#5c1010; --text:#e7dbc8; --muted:#a79a88; --green:#5cff73; --blue:#62b7ff; --red:#ff5555; }
*{box-sizing:border-box} body{margin:0;min-height:100vh;background:radial-gradient(circle at top left,rgba(214,168,95,.12),transparent 28%),linear-gradient(rgba(0,0,0,.78),rgba(0,0,0,.95)),url('/static/login_bg.jpg') center/cover fixed;color:var(--text);font-family:Georgia,'Times New Roman',serif} a{color:inherit}
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:30px}.login-card{width:430px;background:rgba(8,8,8,.91);border:2px solid var(--gold2);padding:35px;box-shadow:0 0 45px #000;text-align:center;border-radius:18px}.login-card h1{color:var(--gold);letter-spacing:5px;font-size:38px;margin-bottom:5px}.login-card p{color:#aaa;margin-bottom:25px}
.app-shell{min-height:100vh;display:grid;grid-template-columns:260px minmax(0,1fr);align-items:start}.sidebar{position:relative;top:auto;min-height:100vh;height:auto;background:linear-gradient(180deg,rgba(10,10,10,.98),rgba(30,12,12,.96));border-right:1px solid rgba(214,168,95,.35);padding:22px 16px;overflow:visible;box-shadow:10px 0 35px rgba(0,0,0,.35)}.brand{padding:10px 10px 22px;border-bottom:1px solid rgba(214,168,95,.25);margin-bottom:16px}.brand-title{color:var(--gold);font-size:24px;letter-spacing:3px;font-weight:bold;line-height:1.1}.brand-sub{color:var(--muted);font-size:12px;letter-spacing:1px;margin-top:7px}.sidebar-player{margin:12px 0 16px;padding:10px 11px;border:1px solid rgba(214,168,95,.18);border-radius:12px;background:rgba(0,0,0,.20);font-size:12px;line-height:1.65}.sidebar-player .city{color:var(--gold);font-weight:bold;letter-spacing:1px}.page-city{color:var(--gold);font-size:18px;letter-spacing:1px;white-space:nowrap}.nav{display:flex;flex-direction:column;gap:7px;margin:0}.nav a{background:rgba(255,255,255,.035);color:var(--text);border:1px solid rgba(214,168,95,.16);padding:11px 12px;text-decoration:none;font-weight:bold;border-radius:12px;display:block;transition:.18s ease}.nav a:hover{background:linear-gradient(90deg,rgba(92,16,16,.9),rgba(92,16,16,.18));border-color:var(--gold);transform:translateX(3px)}.nav a.active{background:linear-gradient(90deg,rgba(214,168,95,.96),rgba(155,106,50,.90));color:#111;border-color:#f0c878;box-shadow:0 0 18px rgba(214,168,95,.38);transform:translateX(3px)}.nav a.active .badge{background:#111;color:var(--gold);border-color:#111}
.content-wrap{min-width:0;padding:24px}.topbar{background:linear-gradient(135deg,rgba(19,19,19,.95),rgba(36,21,12,.88));border:1px solid rgba(214,168,95,.28);border-radius:18px;padding:18px 20px;box-shadow:0 15px 45px rgba(0,0,0,.35);display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:18px}.hero-title{color:var(--gold);font-size:28px;letter-spacing:4px;font-weight:bold}.player-strip{display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-end;color:var(--muted);font-size:14px}.pill{border:1px solid rgba(214,168,95,.22);background:rgba(0,0,0,.25);padding:7px 10px;border-radius:999px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:6px;margin:0 0 18px}.stat-card{background:var(--panel);border:1px solid rgba(214,168,95,.22);border-radius:16px;padding:14px;box-shadow:0 12px 30px rgba(0,0,0,.25)}.stat-card small{color:var(--muted);display:block;margin-bottom:7px;text-transform:uppercase;letter-spacing:1px}.stat-card b{color:var(--gold);font-size:20px}.box{background:rgba(13,13,13,.88);border:1px solid rgba(214,168,95,.22);padding:20px;margin-top:18px;box-shadow:0 0 22px #000;border-radius:18px;overflow-x:auto}.dashboard-hero{display:grid;grid-template-columns:1.3fr .7fr;gap:16px;margin-bottom:18px}.panel{background:var(--panel);border:1px solid rgba(214,168,95,.22);border-radius:18px;padding:18px;box-shadow:0 14px 35px rgba(0,0,0,.28)}.panel h2,.box h2{color:var(--gold);margin-top:0;letter-spacing:1px}.quick-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
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
.message-list{display:grid;gap:12px}.message-card{display:grid;grid-template-columns:46px minmax(0,1fr) auto;gap:6px;align-items:start;background:linear-gradient(145deg,rgba(17,17,17,.96),rgba(31,22,14,.9));border:1px solid rgba(214,168,95,.22);border-radius:16px;padding:14px;box-shadow:0 10px 26px rgba(0,0,0,.24)}.message-card.unread{border-color:var(--gold);background:linear-gradient(145deg,rgba(41,27,12,.96),rgba(45,16,16,.88))}.message-icon{font-size:28px;text-align:center}.message-title{color:var(--gold);font-weight:bold;font-size:17px}.message-body{color:var(--text);margin-top:6px;line-height:1.5;white-space:pre-line}.message-meta{color:var(--muted);font-size:12px;margin-top:4px}.badge{display:inline-block;background:var(--wine);border:1px solid var(--gold);border-radius:999px;padding:1px 7px;margin-left:5px;color:#fff;font-size:12px}.category-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:15px}.category-tabs a{border:1px solid rgba(214,168,95,.22);border-radius:999px;padding:8px 11px;text-decoration:none;background:rgba(0,0,0,.25)}

.cargo-hero{display:grid;grid-template-columns:1.2fr .8fr;gap:16px;margin-bottom:18px}.cargo-command{min-height:220px;border-radius:20px;border:1px solid rgba(214,168,95,.32);background:linear-gradient(135deg,rgba(12,12,12,.92),rgba(18,42,48,.34)),radial-gradient(circle at 78% 18%,rgba(98,183,255,.18),transparent 28%);padding:24px;display:flex;flex-direction:column;justify-content:end;box-shadow:0 18px 45px rgba(0,0,0,.35)}.cargo-command h2{font-size:34px;letter-spacing:3px;margin:0;color:var(--gold)}.cargo-command p{max-width:700px;color:var(--muted)}.cargo-kpis{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.cargo-board{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}.cargo-card{background:linear-gradient(145deg,rgba(16,16,16,.96),rgba(25,24,18,.9));border:1px solid rgba(214,168,95,.24);border-radius:18px;padding:16px;box-shadow:0 14px 34px rgba(0,0,0,.28);position:relative;overflow:hidden}.cargo-card:before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 80% 0%,rgba(214,168,95,.10),transparent 32%);pointer-events:none}.cargo-route{position:relative;z-index:1;font-size:18px;color:var(--gold);font-weight:bold;margin-bottom:10px}.cargo-status{display:inline-block;border:1px solid rgba(214,168,95,.2);border-radius:999px;padding:5px 9px;font-size:12px;text-transform:uppercase;letter-spacing:1px;background:rgba(0,0,0,.25)}.cargo-meta{position:relative;z-index:1;display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:13px 0}.cargo-meta div{background:rgba(0,0,0,.25);border:1px solid rgba(214,168,95,.14);border-radius:12px;padding:10px}.cargo-meta small{display:block;color:var(--muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px;font-size:10px}.cargo-progress{height:8px;border-radius:999px;background:rgba(255,255,255,.10);overflow:hidden;margin:12px 0}.cargo-progress span{display:block;height:100%;background:linear-gradient(90deg,var(--wine),var(--gold));border-radius:999px}.cargo-form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:6px;align-items:end}.cargo-send-panel{margin-top:18px}.status-arrived{color:var(--green)}.status-seized{color:var(--red)}.status-transit{color:var(--gold)}
@media(max-width:900px){.cargo-hero{grid-template-columns:1fr}.cargo-kpis{grid-template-columns:1fr}.cargo-meta{grid-template-columns:1fr}}

@media(max-width:900px){.garage-hero{grid-template-columns:1fr}.garage-kpi{grid-template-columns:1fr}.vehicle-image{height:150px}}

@media(max-width:900px){.app-shell{grid-template-columns:1fr}.sidebar{position:relative;min-height:auto;height:auto;overflow:visible}.content-wrap{padding:14px}.topbar,.dashboard-hero{grid-template-columns:1fr;flex-direction:column;align-items:flex-start}.nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr))}}

/* Luxe Peaky Empire v3 visual polish */
body{background:radial-gradient(circle at 15% 0%,rgba(214,168,95,.14),transparent 25%),linear-gradient(rgba(0,0,0,.74),rgba(0,0,0,.96)),url('/static/garage_reference.png') center/cover fixed;color:var(--text)}
body:before{content:"";position:fixed;inset:0;background:rgba(0,0,0,.45);pointer-events:none;z-index:-1}.sidebar{background:linear-gradient(180deg,rgba(2,8,12,.98),rgba(11,17,20,.97) 48%,rgba(30,17,6,.96));border-right:1px solid rgba(214,168,95,.55)}.brand-title{font-size:30px;letter-spacing:2px;text-shadow:0 0 24px rgba(214,168,95,.35)}.sidebar-player{background:linear-gradient(145deg,rgba(0,0,0,.35),rgba(214,168,95,.08));border-color:rgba(214,168,95,.35)}.grouped-nav{gap:0}.menu-section{margin:0 0 13px;padding-bottom:10px;border-bottom:1px solid rgba(214,168,95,.20)}.menu-section:last-child{border-bottom:0}.menu-header{color:var(--gold);font-size:13px;font-weight:800;letter-spacing:1.3px;text-transform:uppercase;margin:0 0 7px;padding:7px 4px 4px}.nav a{padding:8px 10px;margin:3px 0;border-radius:8px;border-color:transparent;background:rgba(255,255,255,.025);font-size:14px}.nav a.active{background:linear-gradient(90deg,rgba(214,168,95,.92),rgba(155,106,50,.78));color:#0c0c0c;border-color:rgba(255,232,168,.7);box-shadow:0 0 18px rgba(214,168,95,.28)}.topbar{background:linear-gradient(135deg,rgba(3,10,14,.96),rgba(20,15,9,.95));border-color:rgba(214,168,95,.42)}.hero-title{font-size:30px;text-shadow:0 0 22px rgba(214,168,95,.22)}.box,.panel,.stat-card,.card{backdrop-filter:blur(2px);background:linear-gradient(145deg,rgba(5,10,13,.92),rgba(24,18,12,.88));border-color:rgba(214,168,95,.30)}.showroom-banner{background:linear-gradient(135deg,rgba(6,12,16,.86),rgba(9,9,9,.55)),url('/static/garage_reference.png') center 48%/cover;border-color:rgba(214,168,95,.55);min-height:260px}.showroom-banner h2{font-size:42px;text-shadow:0 4px 22px #000}.vehicle-grid{grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:18px}.vehicle-card{border-color:rgba(214,168,95,.48);background:rgba(4,10,14,.92)}.vehicle-image{height:220px;background-size:cover;background-position:center}.vehicle-image:before{background:linear-gradient(rgba(0,0,0,.08),rgba(0,0,0,.72))}.vehicle-silhouette{position:absolute;left:14px;bottom:12px;text-align:left}.vehicle-silhouette .year{font-size:15px}.vehicle-silhouette .icon{font-size:22px}.vehicle-body h3{font-size:21px}.vehicle-meta div{background:rgba(0,0,0,.38)}.btn{background:linear-gradient(#b5791c,#4a2205);border-color:#e3b566;color:#fff4d8;box-shadow:0 0 14px rgba(214,168,95,.18)}.btn:hover{background:linear-gradient(#d3972d,#6a3308)}


/* === AAA DARK GOLD UI - generated from supplied reference === */
:root{
  --aaa-bg:#02080b; --aaa-panel:rgba(2,10,14,.88); --aaa-panel2:rgba(5,15,19,.72);
  --aaa-gold:#d99a2b; --aaa-gold2:#ffcc74; --aaa-line:rgba(217,154,43,.48);
  --aaa-text:#f7ead8; --aaa-muted:#b9a88f; --aaa-shadow:0 22px 70px rgba(0,0,0,.55);
}
html,body{min-height:100%;height:auto!important;overflow-x:hidden!important;background:#02080b!important;color:var(--aaa-text)!important;font-family:Inter,Segoe UI,Arial,sans-serif!important}
body{
  background:
    radial-gradient(circle at 55% 0%, rgba(217,154,43,.16), transparent 28%),
    linear-gradient(90deg,rgba(0,10,14,.92),rgba(0,10,14,.72) 38%,rgba(0,0,0,.88)),
    url('/static/garage_reference.png') center/cover fixed!important;
}
body:after{content:"";position:fixed;inset:0;pointer-events:none;background:linear-gradient(180deg,rgba(0,0,0,.08),rgba(0,0,0,.58)),radial-gradient(circle at center,transparent 0,rgba(0,0,0,.45) 80%);z-index:-1}
.app-shell{grid-template-columns:258px minmax(0,1fr)!important;align-items:stretch!important;overflow:visible!important;height:auto!important}
.sidebar{position:relative!important;top:auto!important;height:auto!important;min-height:100vh!important;max-height:none!important;overflow:visible!important;overflow-y:visible!important;background:linear-gradient(180deg,rgba(1,12,17,.98),rgba(0,13,18,.96))!important;border-right:1px solid var(--aaa-line)!important;box-shadow:12px 0 45px rgba(0,0,0,.5)!important;padding:10px 12px!important}
.aaa-brand{height:82px;display:flex;align-items:center;gap:14px;border-bottom:1px solid var(--aaa-line)!important;margin-bottom:10px!important;padding:0 8px!important}
.brand-mark{width:54px;height:54px;border:2px solid var(--aaa-gold);transform:rotate(45deg);display:grid;place-items:center;color:var(--aaa-gold2);font-size:25px;box-shadow:0 0 24px rgba(217,154,43,.25)}
.brand-title{font-family:Georgia,serif!important;font-size:31px!important;line-height:.87!important;color:#fff1d5!important;text-shadow:0 0 18px rgba(217,154,43,.28)!important;letter-spacing:2px!important}
.aaa-player{text-align:left!important;background:transparent!important;border:0!important;border-radius:0!important;padding:8px 6px 14px!important;margin:0 0 8px!important}
.avatar-frame{width:78px;height:78px;margin:4px auto 8px;border-radius:50%;border:2px solid var(--aaa-gold);background:radial-gradient(circle at 50% 35%,#1d2d34,#02080b 72%);box-shadow:0 0 28px rgba(217,154,43,.25);display:grid;place-items:center}
.avatar-face{font-size:42px;color:#f1b753;text-shadow:0 1px 12px #000}
.avatar-picker-form{display:flex;flex-direction:column;align-items:center;gap:6px;margin-bottom:6px}
.avatar-button{cursor:pointer;border-style:solid}
.avatar-face{display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1}
.avatar-face .avatar-icon{font-size:31px;line-height:1}
.avatar-face small{font-size:12px;letter-spacing:1.5px;color:#ffe4a3;margin-top:4px}
.avatar-select{width:132px;max-width:100%;height:27px;border-radius:8px;border:1px solid rgba(217,154,43,.38);background:rgba(0,0,0,.45);color:#f5d58f;font-size:11px;font-weight:700;text-align:center;outline:none}
.avatar-select option{background:#101010;color:#f5d58f}
.player-name{text-align:center;color:var(--aaa-gold2);font-family:Georgia,serif;font-size:17px;font-weight:700;margin-bottom:7px}.player-line{text-align:center;color:#fff;font-size:13px;margin:4px}
.exp-row{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:8px;margin-top:11px;color:var(--aaa-gold2);font-weight:800;font-size:12px}.exp-track{height:8px;background:rgba(255,255,255,.16);border-radius:20px;overflow:hidden}.exp-track i{display:block;height:100%;background:linear-gradient(90deg,#f2b64d,#9f670b);border-radius:20px}
.menu-section{border-bottom:1px solid rgba(217,154,43,.26)!important;margin-bottom:8px!important;padding-bottom:7px!important}.menu-header{font-size:16px!important;color:var(--aaa-gold2)!important;display:flex;justify-content:space-between}
.nav a{font-size:14px!important;padding:6px 14px!important;border-radius:4px!important;background:transparent!important;color:#fff!important;border:1px solid transparent!important;font-weight:600!important}.nav a:hover{background:rgba(217,154,43,.13)!important;transform:none!important}.nav a.active{background:linear-gradient(90deg,rgba(171,104,13,.85),rgba(126,75,5,.66))!important;border-color:rgba(255,202,104,.55)!important;color:#fff6dd!important;box-shadow:inset 0 0 18px rgba(255,194,86,.15),0 0 18px rgba(217,154,43,.25)!important;transform:none!important}
.content-wrap{padding:0!important;min-height:100vh}.aaa-topbar{height:74px;border-radius:0!important;margin:0!important;border-width:0 0 1px 0!important;border-color:var(--aaa-line)!important;background:linear-gradient(180deg,rgba(1,12,17,.98),rgba(0,8,12,.95))!important;display:grid!important;grid-template-columns:repeat(6,minmax(120px,1fr)) auto;gap:0!important;align-items:center!important;padding:0 20px!important;box-shadow:0 10px 38px rgba(0,0,0,.35)!important}
.top-stat{display:grid;grid-template-columns:28px 1fr;grid-template-rows:auto auto;column-gap:8px;align-items:center}.top-stat span{grid-row:1/3;color:var(--aaa-gold2);font-size:23px}.top-stat small{color:var(--aaa-gold2);font-size:13px;font-weight:800;letter-spacing:.6px}.top-stat b{color:#fff;font-size:16px;font-weight:500}.top-icons{display:flex;align-items:center;justify-content:flex-end;gap:6px;margin-right:10px;transform:translateX(-12px)}.notification{position:relative;width:40px;height:40px;border:1px solid rgba(255,204,116,.32);border-radius:9px;display:grid;place-items:center;background:rgba(255,255,255,.04);font-size:20px}.notification i{position:absolute;right:-7px;top:-8px;background:#a56613;border:1px solid #ffcd74;color:#fff;border-radius:50%;font-style:normal;font-size:12px;min-width:22px;height:22px;display:grid;place-items:center}
.stats{display:none!important}.box.aaa-page{margin:0!important;padding:24px 26px 34px!important;background:linear-gradient(90deg,rgba(2,10,14,.72),rgba(2,10,14,.38))!important;border:0!important;border-radius:0!important;box-shadow:none!important;min-height:calc(100vh - 74px)}
.msg{margin:16px 24px 0!important;background:rgba(88,16,16,.88)!important;border:1px solid rgba(255,107,107,.3)!important;border-left:4px solid #dc2929!important}
.garage-command{display:flex;align-items:center;justify-content:space-between;gap:26px;min-height:94px;margin-bottom:14px}.garage-command h1{font-family:Georgia,serif!important;font-size:58px!important;line-height:1;margin:0;color:#f7dfbd!important;letter-spacing:11px;text-shadow:0 5px 25px #000}.garage-command p{margin:6px 0 0;color:#fff;font-size:16px}
.garage-summary-panel{display:grid;grid-template-columns:120px 150px 120px auto;gap:18px;align-items:center;background:rgba(0,8,12,.72);border:1px solid var(--aaa-line);border-radius:6px;padding:11px 14px;box-shadow:var(--aaa-shadow)}.garage-summary-panel small{display:block;color:var(--aaa-gold2);font-size:12px;font-weight:800}.garage-summary-panel b{display:block;color:#fff;font-size:23px;font-weight:500}.buy-vehicle-btn{white-space:nowrap;margin:0!important;padding:14px 20px!important;border-radius:5px!important;background:linear-gradient(#b87816,#7a4705)!important}
.garage-tabs{display:flex;max-width:705px;border:1px solid rgba(255,204,116,.35);border-radius:5px;overflow:hidden;margin-bottom:16px;background:rgba(0,8,12,.55)}.garage-tabs a{padding:10px 27px;border-right:1px solid rgba(255,204,116,.22);color:#f0d2a0;text-decoration:none;font-size:13px}.garage-tabs a.active{background:linear-gradient(#ac720f,#714103);box-shadow:inset 0 0 12px rgba(255,222,124,.3);color:#fff}
.vehicle-section-title{display:none}.city-title{display:block!important;margin-top:24px}.vehicle-section{margin:0!important}.vehicle-grid{grid-template-columns:repeat(4,minmax(230px,1fr))!important;gap:14px!important}.aaa-vehicle-card{border-radius:12px!important;padding:0!important;border:1px solid rgba(255,173,55,.62)!important;background:rgba(1,9,13,.86)!important;box-shadow:0 18px 45px rgba(0,0,0,.45)!important;overflow:hidden!important}.aaa-vehicle-card:hover{transform:translateY(-4px)!important;box-shadow:0 24px 60px rgba(0,0,0,.62)!important}
.aaa-vehicle-card .vehicle-image{height:250px!important;background-color:#142027;background-size:cover!important;background-position:center!important}.aaa-vehicle-card .vehicle-image:before{background:linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,.15) 45%,rgba(0,0,0,.9))!important}.aaa-vehicle-card .vehicle-silhouette{left:14px!important;top:14px!important;bottom:auto!important;text-shadow:0 3px 16px #000!important}.aaa-vehicle-card .vehicle-silhouette .icon{font-family:Georgia,serif!important;font-size:22px!important;color:#fff!important;letter-spacing:0!important}.aaa-vehicle-card .vehicle-silhouette .year{font-size:13px!important;color:#fff!important;letter-spacing:0!important}
.vehicle-body{padding:0 14px 10px!important;margin-top:-58px;position:relative;z-index:2}.vehicle-specs{display:grid;grid-template-columns:1fr 1fr;gap:9px;color:#fff;border-top:1px solid rgba(255,255,255,.12);padding-top:10px;margin-bottom:9px;font-size:14px}.vehicle-meta.compact{grid-template-columns:1fr 1fr!important;margin:0 0 8px!important}.vehicle-meta.compact div{padding:7px!important;background:rgba(0,0,0,.36)!important;border-color:rgba(255,204,116,.18)!important}.vehicle-meta.compact small{font-size:9px!important}.vehicle-meta.compact b{font-size:12px!important}
.drive-btn{width:78%;display:block!important;margin:0 auto!important;padding:9px 12px!important;border-radius:4px!important;background:linear-gradient(180deg,rgba(48,31,6,.95),rgba(3,11,14,.95))!important;border:1px solid #b87913!important;color:#ffc970!important;font-weight:900!important;letter-spacing:.8px}
.garage-city-grid{margin-top:15px}.garage-city-card{background:rgba(1,9,13,.84)!important;border-color:rgba(255,173,55,.36)!important}
@media(max-width:1300px){.vehicle-grid{grid-template-columns:repeat(3,minmax(230px,1fr))!important}.garage-summary-panel{grid-template-columns:repeat(3,1fr);}.buy-vehicle-btn{grid-column:1/-1;text-align:center}.aaa-topbar{grid-template-columns:repeat(3,1fr)}}
@media(max-width:900px){.app-shell{grid-template-columns:1fr!important}.sidebar{position:relative!important;height:auto!important}.aaa-topbar{height:auto;grid-template-columns:1fr 1fr!important;padding:12px!important}.vehicle-grid{grid-template-columns:1fr!important}.garage-command{display:block}.garage-summary-panel{grid-template-columns:1fr}.garage-tabs{overflow:auto}.garage-command h1{font-size:42px!important}}


/* =========================================================
   SPRINT 1 - AAA CORE LAYOUT FOUNDATION
   Keeps gameplay intact; replaces visual shell only.
   ========================================================= */
:root{
  --aaa-bg:#03080b;
  --aaa-bg2:#07131a;
  --aaa-panel:rgba(4,12,16,.88);
  --aaa-panel2:rgba(11,22,28,.78);
  --aaa-line:rgba(218,157,55,.34);
  --aaa-line-strong:rgba(255,202,102,.60);
  --aaa-gold:#d99a2b;
  --aaa-gold2:#f1c16f;
  --aaa-brass:#8d5a16;
  --aaa-text:#f3ead7;
  --aaa-muted:#b7a78d;
  --aaa-red:#8d1f18;
}
html,body{margin:0!important;padding:0!important;min-height:100%!important;overflow-x:hidden!important;background:var(--aaa-bg)!important;color:var(--aaa-text)!important;}
body{
  font-family:Inter,Segoe UI,Arial,sans-serif!important;
  background:
    radial-gradient(circle at 78% 6%,rgba(217,154,43,.20),transparent 24%),
    radial-gradient(circle at 20% 0%,rgba(57,100,109,.22),transparent 26%),
    linear-gradient(135deg,#03080b 0%,#07131a 45%,#130e09 100%)!important;
}
body:before{content:"";position:fixed;inset:0;pointer-events:none;z-index:-1;background:linear-gradient(90deg,rgba(0,0,0,.44),rgba(0,0,0,.06) 48%,rgba(0,0,0,.42)),repeating-linear-gradient(0deg,rgba(255,255,255,.018) 0 1px,transparent 1px 4px)!important;}
.app-shell{display:grid!important;grid-template-columns:286px minmax(0,1fr)!important;gap:0!important;align-items:stretch!important;min-height:100vh!important;background:transparent!important;}
.sidebar{position:relative!important;height:auto!important;min-height:100vh!important;max-height:none!important;overflow:visible!important;padding:0!important;background:linear-gradient(180deg,rgba(1,10,14,.98),rgba(5,15,19,.98) 52%,rgba(23,14,6,.98))!important;border-right:1px solid var(--aaa-line)!important;box-shadow:16px 0 55px rgba(0,0,0,.45)!important;}
.aaa-brand{height:128px!important;margin:0!important;padding:22px 18px!important;border-bottom:1px solid var(--aaa-line)!important;display:flex!important;align-items:center!important;justify-content:flex-start!important;gap:14px!important;background:radial-gradient(circle at 30% 15%,rgba(217,154,43,.16),transparent 42%)!important;}
.brand-mark{width:54px!important;height:54px!important;border-radius:16px!important;border:1px solid var(--aaa-line-strong)!important;background:linear-gradient(145deg,rgba(217,154,43,.24),rgba(2,8,12,.66))!important;display:grid!important;place-items:center!important;color:var(--aaa-gold2)!important;font-size:28px!important;box-shadow:0 0 28px rgba(217,154,43,.18)!important;}
.brand-title{color:var(--aaa-gold2)!important;font-family:Georgia,serif!important;font-size:29px!important;line-height:.94!important;letter-spacing:2.4px!important;text-shadow:0 0 25px rgba(217,154,43,.28)!important;}
.aaa-player{margin:16px!important;padding:16px!important;border:1px solid var(--aaa-line)!important;border-radius:18px!important;background:linear-gradient(145deg,rgba(255,255,255,.055),rgba(217,154,43,.055)),radial-gradient(circle at 80% 0%,rgba(217,154,43,.14),transparent 40%)!important;box-shadow:0 16px 40px rgba(0,0,0,.28)!important;}
.avatar-frame{width:82px!important;height:82px!important;margin:0 auto 12px!important;border:1px solid var(--aaa-line-strong)!important;border-radius:22px!important;background:radial-gradient(circle,#22333b,#060b0d 68%)!important;display:grid!important;place-items:center!important;box-shadow:0 0 25px rgba(217,154,43,.18)!important;}
.avatar-face{font-size:36px!important;color:var(--aaa-gold2)!important;}
.player-name{text-align:center!important;color:#fff!important;font-size:17px!important;font-weight:900!important;letter-spacing:.8px!important;margin-bottom:8px!important;}
.player-line{font-size:12px!important;color:var(--aaa-muted)!important;margin:5px 0!important;display:flex!important;justify-content:space-between!important;gap:10px!important;}
.exp-row{display:grid!important;grid-template-columns:auto 1fr auto!important;gap:8px!important;align-items:center!important;margin-top:12px!important;color:var(--aaa-muted)!important;font-size:11px!important;font-weight:900!important;letter-spacing:1px!important;}
.exp-track{height:8px!important;background:rgba(0,0,0,.52)!important;border:1px solid rgba(255,202,102,.22)!important;border-radius:999px!important;overflow:hidden!important;box-shadow:inset 0 0 12px #000!important;}
.exp-track i{display:block!important;height:100%!important;background:linear-gradient(90deg,#8d5a16,#d99a2b,#ffe0a0)!important;box-shadow:0 0 15px rgba(217,154,43,.65)!important;border-radius:999px!important;}
.grouped-nav{padding:0 12px 20px!important;display:block!important;}
.menu-section{margin:0 0 12px!important;padding:0 0 10px!important;border-bottom:1px solid rgba(218,157,55,.14)!important;}
.menu-header{display:flex!important;justify-content:space-between!important;align-items:center!important;color:var(--aaa-gold2)!important;font-size:11px!important;font-weight:950!important;letter-spacing:1.6px!important;text-transform:uppercase!important;margin:0!important;padding:8px 8px 6px!important;opacity:.96!important;}
.menu-header:after{content:""!important;}
.nav a{margin:3px 0!important;padding:10px 12px!important;border-radius:11px!important;border:1px solid transparent!important;background:transparent!important;color:var(--aaa-muted)!important;text-decoration:none!important;font-size:13px!important;font-weight:850!important;letter-spacing:.15px!important;display:flex!important;align-items:center!important;justify-content:space-between!important;transition:.18s ease!important;}
.nav a:hover{transform:translateX(3px)!important;background:rgba(255,255,255,.045)!important;color:#fff!important;border-color:rgba(218,157,55,.18)!important;}
.nav a.active{transform:none!important;background:linear-gradient(90deg,rgba(217,154,43,.92),rgba(141,90,22,.80))!important;color:#071015!important;border-color:rgba(255,226,150,.75)!important;box-shadow:0 0 22px rgba(217,154,43,.25)!important;}
.badge,.notification i{min-width:20px!important;height:20px!important;border-radius:999px!important;background:var(--aaa-red)!important;color:#fff!important;display:inline-grid!important;place-items:center!important;font-size:11px!important;border:1px solid rgba(255,255,255,.18)!important;}
.content-wrap{padding:0!important;margin:0!important;min-width:0!important;min-height:100vh!important;background:linear-gradient(90deg,rgba(2,8,12,.78),rgba(2,8,12,.30))!important;}
.aaa-topbar{height:76px!important;margin:0!important;border-radius:0!important;border:0!important;border-bottom:1px solid var(--aaa-line)!important;background:linear-gradient(180deg,rgba(1,10,14,.97),rgba(3,12,16,.91))!important;display:grid!important;grid-template-columns:repeat(6,minmax(112px,1fr)) 130px!important;gap:0!important;padding:0 22px!important;align-items:center!important;box-shadow:0 14px 42px rgba(0,0,0,.32)!important;}
.top-stat{height:100%!important;display:grid!important;grid-template-columns:auto 1fr!important;grid-template-rows:1fr 1fr!important;column-gap:9px!important;align-items:center!important;padding:12px 15px!important;border-right:1px solid rgba(218,157,55,.13)!important;}
.top-stat span{grid-row:1/3!important;color:var(--aaa-gold2)!important;font-size:23px!important;filter:drop-shadow(0 0 10px rgba(217,154,43,.26))!important;}
.top-stat small{align-self:end!important;color:var(--aaa-muted)!important;font-size:10px!important;font-weight:900!important;letter-spacing:1.1px!important;text-transform:uppercase!important;}
.top-stat b{align-self:start!important;color:#fff!important;font-size:14px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;}
.top-icons{display:flex!important;gap:9px!important;justify-content:flex-end!important;align-items:center!important;}

.notification{position:relative!important;width:42px!important;height:42px!important;border:1px solid var(--aaa-line)!important;border-radius:13px!important;display:grid!important;place-items:center!important;background:rgba(255,255,255,.035)!important;color:var(--aaa-gold2)!important;}
.notification i{position:absolute!important;right:-7px!important;top:-7px!important;font-style:normal!important;}
.aaa-hero{margin:24px 26px 0!important;min-height:230px!important;border:1px solid var(--aaa-line)!important;border-radius:24px!important;padding:32px!important;display:grid!important;grid-template-columns:minmax(0,1fr) 310px!important;gap:22px!important;align-items:end!important;overflow:hidden!important;position:relative!important;background:linear-gradient(110deg,rgba(3,9,12,.94),rgba(7,18,23,.66) 50%,rgba(217,154,43,.20)),radial-gradient(circle at 76% 24%,rgba(217,154,43,.25),transparent 28%),linear-gradient(135deg,#08151b,#1b140c)!important;box-shadow:0 22px 70px rgba(0,0,0,.35)!important;}
.aaa-hero:before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(0,0,0,.50),transparent 58%),repeating-linear-gradient(115deg,rgba(255,255,255,.035) 0 1px,transparent 1px 22px);pointer-events:none!important;}
.aaa-hero>*{position:relative;z-index:1;}
.hero-kicker{color:var(--aaa-gold2)!important;font-size:12px!important;font-weight:950!important;letter-spacing:2.2px!important;text-transform:uppercase!important;margin-bottom:8px!important;}
.aaa-hero h1{margin:0!important;color:#fff!important;font-family:Georgia,serif!important;font-size:58px!important;line-height:.95!important;letter-spacing:2px!important;text-shadow:0 5px 28px #000!important;}
.aaa-hero p{margin:14px 0 0!important;max-width:620px!important;color:var(--aaa-muted)!important;font-size:16px!important;}
.hero-status{display:grid!important;grid-template-columns:1fr!important;gap:10px!important;}
.hero-status div{padding:13px 15px!important;border:1px solid rgba(255,202,102,.23)!important;border-radius:16px!important;background:rgba(0,0,0,.27)!important;backdrop-filter:blur(3px)!important;}
.hero-status small{display:block!important;color:var(--aaa-muted)!important;font-size:10px!important;font-weight:900!important;letter-spacing:1.2px!important;text-transform:uppercase!important;margin-bottom:4px!important;}
.hero-status b{color:var(--aaa-gold2)!important;font-size:15px!important;}
.box.aaa-page{margin:24px 26px 34px!important;padding:24px!important;border:1px solid var(--aaa-line)!important;border-radius:24px!important;background:linear-gradient(145deg,rgba(3,11,15,.86),rgba(11,19,22,.76))!important;box-shadow:0 22px 70px rgba(0,0,0,.28)!important;overflow-x:auto!important;}
.card,.panel,.stat-card,.garage-city-card,.aaa-vehicle-card,.message-card{background:linear-gradient(145deg,rgba(5,14,18,.88),rgba(19,16,10,.76))!important;border:1px solid rgba(218,157,55,.27)!important;border-radius:18px!important;box-shadow:0 16px 48px rgba(0,0,0,.28)!important;}
.btn,button.btn{background:linear-gradient(180deg,#d99a2b,#81500a)!important;color:#120d05!important;border:1px solid #f1c16f!important;border-radius:12px!important;font-weight:950!important;letter-spacing:.4px!important;box-shadow:0 0 20px rgba(217,154,43,.18)!important;}
.btn:hover,button.btn:hover{filter:brightness(1.10)!important;transform:translateY(-1px)!important;}
.input,input,select,textarea{background:rgba(0,0,0,.35)!important;border:1px solid rgba(218,157,55,.30)!important;color:#fff!important;border-radius:12px!important;}
table{background:rgba(0,0,0,.22)!important;border-radius:16px!important;overflow:hidden!important;} th{background:rgba(217,154,43,.14)!important;color:var(--aaa-gold2)!important;} td,th{border-color:rgba(218,157,55,.15)!important;}
.msg{margin:18px 26px 0!important;background:rgba(80,18,16,.80)!important;border:1px solid rgba(255,103,91,.35)!important;border-left:5px solid #d64b3e!important;border-radius:14px!important;color:#ffd3cc!important;}
.stats{grid-template-columns:repeat(auto-fit,minmax(175px,1fr))!important;gap:14px!important;}
.stat-card small{color:var(--aaa-muted)!important;font-weight:900!important;letter-spacing:1.1px!important}.stat-card b{color:var(--aaa-gold2)!important;font-size:24px!important;}
.page-garage .aaa-hero{background:linear-gradient(110deg,rgba(3,9,12,.95),rgba(7,18,23,.54),rgba(217,154,43,.20)),radial-gradient(circle at 76% 22%,rgba(217,154,43,.28),transparent 30%),linear-gradient(135deg,#07131a,#241508)!important;}
.page-crime .aaa-hero,.page-heists .aaa-hero,.page-jail .aaa-hero{background:linear-gradient(110deg,rgba(3,9,12,.95),rgba(24,8,7,.58),rgba(217,60,43,.14)),radial-gradient(circle at 78% 24%,rgba(217,154,43,.20),transparent 30%),linear-gradient(135deg,#07131a,#240a08)!important;}
.page-market .aaa-hero,.page-cargo .aaa-hero,.page-warehouse .aaa-hero{background:linear-gradient(110deg,rgba(3,9,12,.95),rgba(9,30,36,.58),rgba(217,154,43,.17)),radial-gradient(circle at 78% 24%,rgba(84,169,186,.22),transparent 30%),linear-gradient(135deg,#07131a,#0d242a)!important;}
.page-casino .aaa-hero,.page-bank .aaa-hero,.page-licenses .aaa-hero{background:linear-gradient(110deg,rgba(3,9,12,.95),rgba(38,20,8,.58),rgba(217,154,43,.22)),radial-gradient(circle at 78% 24%,rgba(217,154,43,.29),transparent 30%),linear-gradient(135deg,#07131a,#2b1807)!important;}
.page-family .aaa-hero,.page-territories .aaa-hero,.page-influence .aaa-hero,.page-ranking .aaa-hero{background:linear-gradient(110deg,rgba(3,9,12,.95),rgba(11,23,25,.58),rgba(217,154,43,.18)),radial-gradient(circle at 78% 24%,rgba(217,154,43,.25),transparent 30%),linear-gradient(135deg,#07131a,#171207)!important;}
@media(max-width:1200px){.aaa-topbar{grid-template-columns:repeat(3,1fr)!important;height:auto!important;padding:8px 12px!important}.top-stat{min-height:58px!important}.aaa-hero{grid-template-columns:1fr!important}.hero-status{grid-template-columns:repeat(3,1fr)!important}.aaa-hero h1{font-size:46px!important}}
@media(max-width:820px){.app-shell{grid-template-columns:1fr!important}.sidebar{min-height:auto!important}.aaa-topbar{grid-template-columns:1fr 1fr!important}.aaa-hero{margin:16px!important;padding:22px!important}.box.aaa-page{margin:16px!important;padding:16px!important}.hero-status{grid-template-columns:1fr!important}.aaa-hero h1{font-size:38px!important}.grouped-nav{display:grid!important;grid-template-columns:1fr!important}}



/* === Sprint 3: Dashboard Command Center === */
.s3-dashboard{display:flex;flex-direction:column;gap:20px;}
.s3-hero{position:relative;overflow:hidden;min-height:255px;border:1px solid rgba(217,154,43,.48);border-radius:26px;background:
    radial-gradient(circle at 82% 18%,rgba(217,154,43,.28),transparent 26%),
    radial-gradient(circle at 22% 0%,rgba(255,204,116,.16),transparent 24%),
    linear-gradient(135deg,rgba(2,10,14,.96),rgba(10,19,22,.82) 54%,rgba(55,31,8,.80));
    box-shadow:0 28px 90px rgba(0,0,0,.45);padding:30px;display:grid;grid-template-columns:minmax(0,1.25fr) minmax(280px,.75fr);gap:22px;align-items:end;}
.s3-hero:before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(0,0,0,.18),transparent 45%,rgba(0,0,0,.30)),repeating-linear-gradient(90deg,rgba(255,255,255,.025) 0 1px,transparent 1px 72px);pointer-events:none;}
.s3-kicker{position:relative;z-index:1;color:var(--aaa-gold2,#ffcc74);font-weight:900;letter-spacing:3.5px;text-transform:uppercase;font-size:12px;margin-bottom:8px;}
.s3-hero h1{position:relative;z-index:1;margin:0;color:#fff0c8;font-size:58px;line-height:.92;letter-spacing:5px;text-shadow:0 8px 38px rgba(0,0,0,.75);font-family:Georgia,'Times New Roman',serif;}
.s3-hero p{position:relative;z-index:1;color:#c8b696;max-width:720px;font-size:16px;line-height:1.65;margin:18px 0 0;}
.s3-hero-side{position:relative;z-index:1;background:linear-gradient(145deg,rgba(0,0,0,.35),rgba(217,154,43,.08));border:1px solid rgba(217,154,43,.34);border-radius:22px;padding:18px;display:grid;gap:6px;}
.s3-status-line{display:flex;justify-content:space-between;gap:6px;border-bottom:1px solid rgba(217,154,43,.16);padding-bottom:10px;color:#bba989;}
.s3-status-line:last-child{border-bottom:0;padding-bottom:0}.s3-status-line b{color:#ffe2a4;text-align:right;}
.s3-stat-grid{display:grid;grid-template-columns:repeat(6,minmax(145px,1fr));gap:14px;}
.s3-stat{position:relative;overflow:hidden;border:1px solid rgba(217,154,43,.30);border-radius:20px;padding:16px;background:linear-gradient(145deg,rgba(4,13,17,.90),rgba(32,22,12,.82));box-shadow:0 16px 42px rgba(0,0,0,.28);min-height:118px;}
.s3-stat:before{content:"";position:absolute;right:-35px;top:-42px;width:115px;height:115px;border-radius:50%;background:rgba(217,154,43,.10);}
.s3-stat .icon{font-size:22px;margin-bottom:10px}.s3-stat small{display:block;color:#a99677;text-transform:uppercase;letter-spacing:1.4px;font-size:11px;font-weight:800}.s3-stat b{display:block;margin-top:7px;color:#ffe0a0;font-size:22px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.s3-layout{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(320px,.55fr);gap:18px;align-items:start;}
.s3-panel{background:linear-gradient(145deg,rgba(4,13,17,.92),rgba(20,16,10,.86));border:1px solid rgba(217,154,43,.28);border-radius:22px;padding:20px;box-shadow:0 18px 55px rgba(0,0,0,.34);}
.s3-panel h2{margin:0 0 15px;color:#ffd68c;letter-spacing:2px;text-transform:uppercase;font-size:17px;}
.s3-operations{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:14px;}
.s3-op{border:1px solid rgba(217,154,43,.20);border-radius:18px;background:rgba(0,0,0,.24);padding:15px;min-height:126px;transition:.18s ease;}
.s3-op:hover{transform:translateY(-2px);border-color:rgba(255,204,116,.58);background:rgba(217,154,43,.08);}
.s3-op .top{display:flex;justify-content:space-between;gap:6px;align-items:center;margin-bottom:10px}.s3-op .top span{font-size:24px}.s3-op .top b{color:#ffe1a6;font-size:19px}.s3-op small{color:#a99677;text-transform:uppercase;letter-spacing:1.2px;font-weight:800}.s3-op p{margin:8px 0 0;color:#c8b696;line-height:1.45;}
.s3-feed-list{display:grid;gap:10px}.s3-feed-item{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:start;border:1px solid rgba(217,154,43,.16);border-radius:15px;padding:11px;background:rgba(0,0,0,.24)}.s3-feed-icon{width:34px;height:34px;border-radius:12px;display:grid;place-items:center;background:rgba(217,154,43,.12);border:1px solid rgba(217,154,43,.22)}.s3-feed-item b{color:#ffe1a6}.s3-feed-item p{margin:3px 0 0;color:#bcae96}.s3-feed-age{font-size:11px;color:#8f806d;white-space:nowrap;}
.s3-action-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.s3-action{display:block;text-decoration:none;border:1px solid rgba(217,154,43,.26);background:linear-gradient(135deg,rgba(105,55,7,.72),rgba(4,12,15,.76));border-radius:16px;padding:14px;color:#fff0d0;font-weight:900;letter-spacing:.8px}.s3-action:hover{border-color:#ffd07d;box-shadow:0 0 24px rgba(217,154,43,.18);transform:translateY(-1px)}
.s3-leader-row{display:grid;grid-template-columns:32px 1fr auto;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid rgba(217,154,43,.14)}.s3-leader-row:last-child{border-bottom:0}.s3-rank{width:28px;height:28px;border-radius:999px;background:rgba(217,154,43,.14);border:1px solid rgba(217,154,43,.30);display:grid;place-items:center;color:#ffd68c;font-weight:900}.s3-leader-row b{color:#fff0d0}.s3-leader-row small{display:block;color:#9e907a;margin-top:2px}.s3-leader-value{color:#ffd68c;font-weight:900;text-align:right;}
.s3-two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.s3-empty{color:#9e907a;border:1px dashed rgba(217,154,43,.22);border-radius:16px;padding:18px;text-align:center;background:rgba(0,0,0,.16)}
@media(max-width:1500px){.s3-stat-grid{grid-template-columns:repeat(3,minmax(145px,1fr));}.s3-operations{grid-template-columns:repeat(2,minmax(180px,1fr));}}
@media(max-width:1050px){.s3-hero,.s3-layout,.s3-two{grid-template-columns:1fr}.s3-hero h1{font-size:44px}.s3-stat-grid{grid-template-columns:repeat(2,minmax(145px,1fr));}.s3-operations{grid-template-columns:1fr}.s3-action-grid{grid-template-columns:1fr}}
@media(max-width:620px){.s3-stat-grid{grid-template-columns:1fr}.s3-hero{padding:22px}.s3-hero h1{font-size:36px;letter-spacing:3px}.s3-feed-item{grid-template-columns:auto 1fr}.s3-feed-age{grid-column:2}}
</style>
</head>
<body class="page-{{ page or 'login' }}">

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
        <div class="brand aaa-brand">
            <div class="brand-mark">♜</div>
            <div class="brand-title">PEAKY<br>BLINDERS</div>
        </div>
        <div class="sidebar-player aaa-player">
            {% set current_avatar = avatar_info(user) %}
            <a class="avatar-picker-form" href="/settings" title="Change profile">
                <div class="avatar-frame avatar-button avatar-image-frame">
                    <img class="avatar-img" src="{{ current_avatar.image }}" alt="{{ current_avatar.label }}">
                </div>
            </a>
            <div class="player-name">{{ user.username }}</div>
            <div class="player-line">📍 <span class="city">{% if is_user_traveling(user) %}TRAVELLING{% else %}{{ user.location }}{% endif %}</span></div>
            <div class="player-line">👑 <span class="gold">{{ user.rank }}</span></div>
            <div class="exp-row"><span>EXP</span><div class="exp-track"><i style="width:{{ exp_percent(user) }}%"></i></div><b>{{ exp_percent(user) }}%</b></div>
        </div>
        <div class="nav grouped-nav">
            <div class="menu-section">
                <div class="menu-header">🏠 {{ t("overview") }}</div>
                <a href="/dashboard" class="{% if page == 'dashboard' %}active{% endif %}">{{ t("dashboard") }}</a>
                <a href="/messages" class="{% if page == 'messages' %}active{% endif %}">{{ t("messages") }}{% set unread = unread_message_count(user) %}{% if unread > 0 %}<span class="badge">{{ unread }}</span>{% endif %}</a>
                <a href="/friends" class="{% if page == 'friends' %}active{% endif %}">{{ t("friends") }}</a>
                <a href="/ranking" class="{% if page == 'ranking' %}active{% endif %}">{{ t("rankings") }}</a>
            </div>
            <div class="menu-section">
                <div class="menu-header">📦 {{ t("logistics") }}</div>
                <a href="/market" class="{% if page == 'market' %}active{% endif %}">{{ t("smuggling") }}</a>
                <a href="/cargo" class="{% if page == 'cargo' %}active{% endif %}">{{ t("cargo") }}</a>
                <a href="/traveling" class="{% if page == 'traveling' %}active{% endif %}">{{ t("traveling") }}</a>
                <a href="/warehouse" class="{% if page == 'warehouse' %}active{% endif %}">{{ t("warehouse") }}</a>
            </div>
            <div class="menu-section">
                <div class="menu-header">🔫 {{ t("crime_group") }}</div>
                <a href="/" class="{% if page == 'crime' %}active{% endif %}">{{ t("crimes") }}</a>
                <a href="/heists" class="{% if page == 'heists' %}active{% endif %}">{{ t("heists") }}</a>
                <a href="/protection" class="{% if page == 'protection' %}active{% endif %}">{{ t("protection") }}</a>
                <a href="/bullets" class="{% if page == 'bullets' %}active{% endif %}">{{ t("weapons") }}</a>
            </div>
            <div class="menu-section">
                <div class="menu-header">🚗 {{ t("empire") }}</div>
                <a href="/garage" class="{% if page == 'garage' %}active{% endif %}">{{ t("garage") }}</a>
                <a href="/assets" class="{% if page == 'assets' %}active{% endif %}">{{ t("businesses") }}</a>
                <a href="/properties" class="{% if page == 'properties' %}active{% endif %}">{{ t("properties") }}</a>
                <a href="/casino" class="{% if page == 'casino' %}active{% endif %}">{{ t("casinos") }}</a>
                <a href="/licenses" class="{% if page == 'licenses' %}active{% endif %}">{{ t("licenses") }}</a>
                <a href="/influence" class="{% if page == 'influence' %}active{% endif %}">{{ t("influence") }}</a>
            </div>
            <div class="menu-section">
                <div class="menu-header">👪 {{ t("family") }}</div>
                <a href="/family" class="{% if page == 'family' %}active{% endif %}">{{ t("family") }}</a>
                <a href="/territories" class="{% if page == 'territories' %}active{% endif %}">{{ t("territories") }}</a>
            </div>
            <div class="menu-section">
                <div class="menu-header">👤 {{ t("account") }}</div>
                <a href="/bank" class="{% if page == 'bank' %}active{% endif %}">{{ t("bank") }}</a>
                <a href="/jail" class="{% if page == 'jail' %}active{% endif %}">{{ t("jail") }}</a>
                <a href="/logout">{{ t("logout") }}</a>
            </div>
        </div>
    </aside>
    <main class="content-wrap">
        <div class="topbar aaa-topbar">
            <div class="top-stat"><span>💸</span><small>{{ t("cash") }}</small><b>${{ moneyfmt(user.money) }}</b></div>
            <div class="top-stat"><span>🍾</span><small>{{ t("gin") }}</small><b>{{ warehouse_quantity(user, 'gin') }} L</b></div>
            <div class="top-stat"><span>⚔️</span><small>{{ t("power") }}</small><b>{{ moneyfmt(power_score(user)) }}</b></div>
            <div class="top-stat"><span>🔫</span><small>{{ t("bullets") }}</small><b>{{ moneyfmt(user.bullets) }}</b></div>
            <div class="top-stat"><span>👪</span><small>{{ t("family") }}</small><b>{% if user.family %}{{ user.family.name }}{% else %}{{ t("solo") }}{% endif %}</b></div>
            <div class="top-stat"><span>⏱</span><small>{{ t("server_time") }}</small><b id="server-clock">--:--:--</b></div>
            <div class="top-icons"><span class="notification">✉<i>{{ unread_message_count(user) }}</i></span><span class="notification">🔔<i>{{ family_territory_count(user.family) if user.family else 0 }}</i></span>
                <form class="language-picker" action="/set_language" method="post">
                    <label for="language">{{ t("language") }}</label>
                    <select id="language" class="language-select" name="language" onchange="this.form.submit()">
                        {% for code, info in languages.items() %}
                            <option value="{{ code }}" {% if code == current_language %}selected{% endif %}>{{ info.flag }} {{ code|upper }}</option>
                        {% endfor %}
                    </select>
                    <input type="hidden" name="next" value="{{ request.path }}">
                </form>
                <a class="profile-settings-btn" href="/settings" title="{{ t('profile_settings') }}">🎩</a>
            </div>
        </div>
        {% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
        <section class="aaa-hero page-hero-{{ page }}">
            <div class="hero-copy">
                <div class="hero-kicker">{{ t("hero_kicker") }}</div>
                <h1>{{ page_title }}</h1>
                <p>{{ t("hero_text") }}</p>
            </div>
            <div class="hero-status">
                <div><small>{{ t("location") }}</small><b>{% if is_user_traveling(user) %}{{ t("travelling") }}{% else %}{{ user.location }}{% endif %}</b></div>
                <div><small>{{ t("rank") }}</small><b>{{ user.rank }}</b></div>
                <div><small>{{ t("exp") }}</small><b>{{ exp_percent(user) }}%</b></div>
            </div>
        </section>
    <div class="box aaa-page">

    {% if page == "messages" %}
        <h2>📬 {{ t("messages") }}</h2>
        <p class="muted">{{ t("message_center_text") }}</p>

        <div class="card">
            <h3>✍️ {{ t("compose_message") }}</h3>
            <form action="/send_player_message" method="post">
                <label>{{ t("recipient") }}</label><br>
                <input class="input" name="recipient" list="player-list" placeholder="Username" value="{{ prefill_recipient or '' }}" required>
                <datalist id="player-list">
                    {% for player in message_recipients %}
                        <option value="{{ player.username }}">
                    {% endfor %}
                </datalist>
                <label>{{ t("subject") }}</label><br>
                <input class="input" name="subject" maxlength="120" value="{{ prefill_subject or '' }}" required>
                <label>{{ t("message") }}</label><br>
                <textarea class="input" name="body" rows="5" maxlength="2000" required></textarea>
                <button class="btn">{{ t("send_message") }}</button>
            </form>
        </div>

        <div class="category-tabs">
            <a href="/messages">{{ t("inbox") }}</a>
            <a href="/messages?category=player">✉️ {{ t("player_messages") }}</a>
            <a href="#sent-messages">✅ {{ t("sent_messages") }}</a>
            <a href="/messages?category=cargo">📦 Cargo</a>
            <a href="/messages?category=travel">✈️ Travel</a>
            <a href="/messages?category=crime">🚨 Crime</a>
            <a href="/messages?category=security">🛡️ Security</a>
            <a href="/messages?category=casino">🎰 Casino</a>
            <a href="/messages?category=territory">⚔️ Territory</a>
            <a href="/messages?category=system">⚙️ System</a>
        </div>

        <h3>{{ t("inbox") }}</h3>
        {% if messages %}
        <div class="message-list">
            {% for message in messages %}
            <div class="message-card {% if not message.is_read %}unread{% endif %}">
                <div class="message-icon">{{ message_category_icon(message.category) }}</div>
                <div>
                    <div class="message-title">{{ message.title }}</div>
                    <div class="message-meta">{{ message.category|title }} · {{ message_age(message) }}{% if not message.is_read %} · <span class="gold">{{ t("unread") }}</span>{% endif %}</div>
                    {% if message.is_read %}
                        <div class="message-body">{{ message.body }}</div>
                    {% else %}
                        <div class="message-body muted">🔒 {{ t("message_hidden_until_open") }}</div>
                    {% endif %}
                </div>
                <div>
                    <form action="/message_action" method="post">
                        <input type="hidden" name="message_id" value="{{ message.id }}">
                        {% if not message.is_read %}<button class="btn" name="action" value="open">{{ t("open_message") }}</button>{% endif %}
                        <button class="btn btn-delete" name="action" value="delete">🗑 {{ t("delete") }}</button>
                    </form>
                    {% if message.category == "player" and message.sender %}
                        <a class="btn" style="margin-top:8px;display:inline-block" href="/messages?to={{ message.sender.username }}&subject=Re:%20{{ message.title|urlencode }}">↩ {{ t("reply") }}</a>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
            <div class="card"><h3>{{ t("no_messages") }}</h3><p class="muted">{{ t("inbox_empty") }}</p></div>
        {% endif %}

        <h3 id="sent-messages">✅ {{ t("sent_messages") }}</h3>
        {% if sent_messages %}
            <div class="message-list">
                {% for message in sent_messages %}
                <div class="message-card">
                    <div class="message-icon">✅</div>
                    <div>
                        <div class="message-title">{{ message.title }}</div>
                        <div class="message-meta">
                            {{ t("sent_to") }}: <b class="gold">{{ message.user.username if message.user else "Unknown" }}</b>
                            · {{ message_age(message) }}
                            · {% if message.is_read %}
                                <span class="good">{{ t("opened") }}</span>
                              {% else %}
                                <span class="red">{{ t("not_opened") }}</span>
                              {% endif %}
                        </div>
                        <div class="message-body">{{ message.body }}</div>
                    </div>
                    <div>
                        <span class="{% if message.is_read %}good{% else %}red{% endif %}">
                            {% if message.is_read %}✅ {{ t("opened") }}{% else %}⌛ {{ t("not_opened") }}{% endif %}
                        </span>
                        <form action="/message_action" method="post" style="margin-top:8px">
                            <input type="hidden" name="message_id" value="{{ message.id }}">
                            <button class="btn btn-delete" name="action" value="delete">🗑 {{ t("delete") }}</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            </div>
        {% else %}
            <div class="card"><h3>{{ t("no_messages") }}</h3><p class="muted">{{ t("inbox_empty") }}</p></div>
        {% endif %}
    {% endif %}

    {% if page == "dashboard" %}
        <div class="s3-dashboard">
            <section class="s3-hero">
                <div>
                    <div class="s3-kicker">Empire Command Center</div>
                    <h1>THE SHELBY<br>COMPANY</h1>
                    <p>Welkom terug, <b class="gold">{{ user.username }}</b>. Beheer cashflow, goederen, voertuigen, familie-invloed en territoriumcontrole vanuit één premium command center.</p>
                    <div class="quick-actions">
                        <a class="btn" href="/">⚡ Commit Crime</a>
                        <a class="btn" href="/market">🍾 Smuggling</a>
                        <a class="btn" href="/garage">🚗 Garage</a>
                        <a class="btn" href="/family">👪 {{ t("family") }} HQ</a>
                        <a class="btn" href="/casino">🃏 Casino</a>
                    </div>
                </div>
                <div class="s3-hero-side">
                    <div class="s3-status-line"><span>Current City</span><b>{{ user.location }}</b></div>
                    <div class="s3-status-line"><span>Rank</span><b>{{ user.rank }}</b></div>
                    <div class="s3-status-line"><span>Family</span><b>{% if user.family %}{{ user.family.name }}{% else %}Solo Operator{% endif %}</b></div>
                    <div class="s3-status-line"><span>Influence</span><b>{{ influence_count(user) }}/4</b></div>
                    <div class="s3-status-line"><span>Unread Messages</span><b>{{ unread_message_count(user) }}</b></div>
                </div>
            </section>

            <section class="s3-stat-grid">
                <div class="s3-stat"><div class="icon">💵</div><small>Cash on Hand</small><b>${{ moneyfmt(user.money) }}</b></div>
                <div class="s3-stat"><div class="icon">🏦</div><small>Bank Balance</small><b>${{ moneyfmt(user.bank) }}</b></div>
                <div class="s3-stat"><div class="icon">⚜️</div><small>Power Score</small><b>{{ moneyfmt(power_score(user)) }}</b></div>
                <div class="s3-stat"><div class="icon">👑</div><small>Rank</small><b>{{ user.rank }}</b></div>
                <div class="s3-stat"><div class="icon">🏴</div><small>Territories</small><b>{{ family_territory_count(user.family) if user.family else 0 }}</b></div>
                <div class="s3-stat"><div class="icon">👪</div><small>Family Members</small><b>{{ family_member_count(user.family) if user.family else 0 }}</b></div>
            </section>

            <div class="s3-layout">
                <main class="s3-panel">
                    <h2>Empire Operations</h2>
                    <div class="s3-operations">
                        <a class="s3-op" href="/assets"><div class="top"><span>🏭</span><b>{{ total_distilleries(user) }}</b></div><small>Businesses</small><p>Distilleries producing gin across your cities.</p></a>
                        <a class="s3-op" href="/warehouse"><div class="top"><span>📦</span><b>{{ warehouse_used(user) }}/{{ warehouse_capacity(user) }}</b></div><small>Warehouse</small><p>Stock capacity, contraband and ready goods.</p></a>
                        <a class="s3-op" href="/garage"><div class="top"><span>🚗</span><b>{{ total_vehicles(user) }}</b></div><small>Garage</small><p>Vehicles, transport power and street presence.</p></a>
                        <a class="s3-op" href="/properties"><div class="top"><span>🏛</span><b>${{ moneyfmt(property_income_per_hour(user)) }}/h</b></div><small>Properties</small><p>Passive income ready: ${{ moneyfmt(property_collectable_income(user)) }}.</p></a>
                        <a class="s3-op" href="/casino"><div class="top"><span>🃏</span><b>{{ user_casinos(user)|length }}</b></div><small>Casinos</small><p>Vault value: ${{ moneyfmt(casino_vault_total(user)) }}.</p></a>
                        <a class="s3-op" href="/influence"><div class="top"><span>🏛️</span><b>{{ influence_count(user) }}/4</b></div><small>Influence</small><p>Police, judge, mayor and customs control.</p></a>
                    </div>
                </main>

                <aside class="s3-panel">
                    <h2>Quick Actions</h2>
                    <div class="s3-action-grid">
                        <a class="s3-action" href="/">⚡ Street Crimes</a>
                        <a class="s3-action" href="/heists">💼 Heists</a>
                        <a class="s3-action" href="/market">🍾 Market</a>
                        <a class="s3-action" href="/cargo">📦 Cargo</a>
                        <a class="s3-action" href="/territories">⚔️ Territories</a>
                        <a class="s3-action" href="/bank">🏦 Bank</a>
                    </div>
                </aside>
            </div>

            <div class="s3-two">
                <section class="s3-panel">
                    <h2>Live Activity Feed</h2>
                    <div class="s3-feed-list">
                        {% set recent_messages = message_rows(user, 'all')[:6] %}
                        {% if recent_messages %}
                            {% for message in recent_messages %}
                                <div class="s3-feed-item">
                                    <div class="s3-feed-icon">{{ message_category_icon(message.category) }}</div>
                                    <div><b>{{ message.title }}</b><p>{{ message.body[:95] }}{% if message.body|length > 95 %}...{% endif %}</p></div>
                                    <div class="s3-feed-age">{{ message_age(message) }}</div>
                                </div>
                            {% endfor %}
                        {% else %}
                            <div class="s3-empty">No recent messages yet.</div>
                        {% endif %}
                    </div>
                </section>

                <section class="s3-panel">
                    <h2>Active Cargo</h2>
                    <div class="s3-feed-list">
                        {% set shipments = active_shipments(user) %}
                        {% if shipments %}
                            {% for shipment in shipments[:6] %}
                                <div class="s3-feed-item">
                                    <div class="s3-feed-icon">📦</div>
                                    <div><b>{{ shipment.origin }} → {{ shipment.destination }}</b><p>{{ shipment.quantity }}x {{ shipment.item_key }} · ETA {{ format_duration((shipment.arrives_at - now_time)|int if shipment.arrives_at > now_time else 0) }}</p></div>
                                    <div class="s3-feed-age">${{ moneyfmt(shipment_value(shipment)) }}</div>
                                </div>
                            {% endfor %}
                        {% else %}
                            <div class="s3-empty">No active cargo shipments.</div>
                        {% endif %}
                    </div>
                </section>
            </div>

            <div class="s3-layout">
                <section class="s3-panel">
                    <h2>Richest Players</h2>
                    {% if top_richest %}
                        {% for player in top_richest %}
                            <div class="s3-leader-row"><div class="s3-rank">{{ loop.index }}</div><div><b>{{ player.username }}</b><small>{{ player.rank }} · {{ player.location }}</small></div><div class="s3-leader-value">${{ moneyfmt(player.money + player.bank) }}</div></div>
                        {% endfor %}
                    {% else %}<div class="s3-empty">No ranking data.</div>{% endif %}
                </section>
                <section class="s3-panel">
                    <h2>Strongest Players</h2>
                    {% if top_power %}
                        {% for row in top_power %}
                            <div class="s3-leader-row"><div class="s3-rank">{{ loop.index }}</div><div><b>{{ row.user.username }}</b><small>{{ row.user.rank }} · {{ row.user.location }}</small></div><div class="s3-leader-value">{{ moneyfmt(row.power) }}</div></div>
                        {% endfor %}
                    {% else %}<div class="s3-empty">No power data.</div>{% endif %}
                </section>
            </div>
        </div>
    {% endif %}

    {% if page == "crime" %}
        <div class="s4-ops-wrap">
            <section class="s4-hero">
                <div class="s4-hero-grid">
                    <div>
                        <div class="s4-eyebrow">Operations Center</div>
                        <h1>STREET CRIMES</h1>
                        <p>Run quick operations across {{ user.location }}. Your rank adds <b class="gold">+{{ rank_bonus(user, 'crime_chance') }}%</b> success and <b class="gold">+{{ rank_bonus(user, 'crime_income') }}%</b> income. Local vehicles can add extra edge, but failed jobs can attract police attention.</p>
                    </div>
                    {% set crime_left = (cooldown - (now_time - user.last_crime))|int %}
                    {% set crime_wait = crime_left if crime_left > 0 else 0 %}
                    <div class="s4-cooldown">
                        <small>Crime Cooldown</small>
                        {% if crime_wait > 0 %}<b>{{ format_duration(crime_wait) }}</b><div class="s4-bar"><span style="width:{{ ((cooldown-crime_wait) / cooldown * 100)|int }}%"></span></div>{% else %}<b>Ready</b><div class="s4-bar"><span style="width:100%"></span></div>{% endif %}
                    </div>
                </div>
            </section>

            <div class="s4-stats">
                <div class="s4-stat"><small>Cash</small><b>${{ moneyfmt(user.money) }}</b></div>
                <div class="s4-stat"><small>Power</small><b>{{ moneyfmt(power_score(user)) }}</b></div>
                <div class="s4-stat"><small>Rank</small><b>{{ user.rank }}</b></div>
                <div class="s4-stat"><small>Location</small><b>{{ user.location }}</b></div>
            </div>

            <div class="s4-section-head"><h2>Available Operations</h2><span>Risk / Reward</span></div>
            <div class="s4-grid">
                {% set crime_cards = [
                    {'key':'pickpocket','icon':'🕴️','title':'Pickpocket Run','risk':'Low','risk_class':'risk-low','desc':'Fast street work with low exposure. Good for early cash and safe EXP.', 'reward':'$30 - $100','exp':'2 - 6 EXP','success':85 + rank_bonus(user, 'crime_chance'), 'police':'5%'},
                    {'key':'robbery','icon':'🏪','title':'Store Robbery','risk':'Medium','risk_class':'risk-medium','desc':'Hit a shop, move fast, and disappear into the Birmingham fog.', 'reward':'$100 - $350','exp':'8 - 18 EXP','success':65 + rank_bonus(user, 'crime_chance'), 'police':'12%'},
                    {'key':'truck','icon':'🚚','title':'Bank Transport','risk':'High','risk_class':'risk-high','desc':'Intercept guarded money transport. Bigger payout, bigger police heat.', 'reward':'$400 - $1,000','exp':'20 - 45 EXP','success':40 + rank_bonus(user, 'crime_chance'), 'police':'25%'}
                ] %}
                {% for op in crime_cards %}
                <article class="s4-operation-card {% if crime_wait > 0 %}s4-disabled{% endif %}">
                    <div class="s4-card-top">
                        <div style="display:flex;gap:6px;align-items:start"><div class="s4-icon">{{ op.icon }}</div><div class="s4-title"><h3>{{ op.title }}</h3><p>{{ op.desc }}</p></div></div>
                        <span class="s4-risk {{ op.risk_class }}">{{ op.risk }} Risk</span>
                    </div>
                    <div class="s4-card-body">
                        <div class="s4-metrics">
                            <div class="s4-metric"><small>Reward</small><b>{{ op.reward }}</b></div>
                            <div class="s4-metric"><small>{{ t("exp") }}</small><b>{{ op.exp }}</b></div>
                            <div class="s4-metric"><small>Success</small><b>{{ [op.success, 95]|min }}%</b><div class="s4-success-ring"><span style="width:{{ [op.success,95]|min }}%"></span></div></div>
                            <div class="s4-metric"><small>Police Risk</small><b>{{ op.police }}</b></div>
                        </div>
                        <form action="/crime_action" method="post">
                            <small class="muted">Vehicle from {{ user.location }}</small>
                            <select class="input s4-select" name="vehicle_key">
                                <option value="">No vehicle</option>
                                {% for item in local_vehicles %}<option value="{{ item.vehicle.key }}">{{ item.vehicle.year }} {{ item.vehicle.name }} (+{{ item.vehicle.bonus }}%) x{{ item.quantity }}</option>{% endfor %}
                            </select>
                            <button class="btn s4-action-btn" name="crime" value="{{ op.key }}" {% if crime_wait > 0 %}disabled{% endif %}>Start Operation</button>
                        </form>
                    </div>
                </article>
                {% endfor %}
            </div>

            <div class="s4-section-head"><h2>Weapon Theft</h2><span>Black Market / Armories</span></div>
            <div class="s4-grid two">
                <article class="s4-operation-card {% if crime_wait > 0 %}s4-disabled{% endif %}">
                    <div class="s4-card-top">
                        <div style="display:flex;gap:6px;align-items:start">
                            <div class="s4-icon">🔫</div>
                            <div class="s4-title">
                                <h3>Steal Weapons</h3>
                                <p>Raid a weapon stash. You can find ammunition, common weapons, or rarely elite weapons.</p>
                            </div>
                        </div>
                        <span class="s4-risk risk-high">High Risk</span>
                    </div>
                    <div class="s4-metrics">
                        <div class="s4-metric"><small>Potential</small><b>Bullets / Weapon</b></div>
                        <div class="s4-metric"><small>Arrest Risk</small><b>{{ [weapon_theft_arrest_risk - lookout_arrest_reduction(user), 5]|max }}%</b></div>
                    </div>
                    <form action="/crime_action" method="post">
                        <button class="btn s4-action-btn" name="crime" value="weapon_theft" {% if crime_wait > 0 %}disabled{% endif %}>Raid Weapon Stash</button>
                    </form>
                </article>
            </div>

            <div class="s4-section-head"><h2>Vehicle Theft</h2><span>Garages / Streets</span></div>
            <div class="s4-grid two">
                <article class="s4-operation-card {% if crime_wait > 0 %}s4-disabled{% endif %}">
                    <div class="s4-card-top"><div style="display:flex;gap:6px;align-items:start"><div class="s4-icon">🚗</div><div class="s4-title"><h3>Street Vehicle Theft</h3><p>Search streets and parking garages. Most attempts find parts or nothing; luxury vehicles are rare.</p></div></div><span class="s4-risk risk-medium">Medium Risk</span></div>
                    <div class="s4-metrics"><div class="s4-metric"><small>Potential</small><b>Parts / Vehicle</b></div><div class="s4-metric"><small>Arrest Risk</small><b>{{ [18 - lookout_arrest_reduction(user), 3]|max }}%</b></div></div>
                    <form action="/crime_action" method="post"><button class="btn s4-action-btn" name="crime" value="street_vehicle_theft" {% if crime_wait > 0 %}disabled{% endif %}>Search Parking Garages</button></form>
                </article>
                <article class="s4-operation-card {% if crime_wait > 0 %}s4-disabled{% endif %}">
                    <div class="s4-card-top"><div style="display:flex;gap:6px;align-items:start"><div class="s4-icon">🎯</div><div class="s4-title"><h3>Steal From Player</h3><p>Automatically targets a local active player with stealable vehicles in {{ user.location }}.</p></div></div><span class="s4-risk risk-high">High Risk</span></div>
                    <div class="s4-metrics"><div class="s4-metric"><small>Target City</small><b>{{ user.location }}</b></div><div class="s4-metric"><small>Security</small><b>Guards / Safehouses</b></div></div>
                    <form action="/crime_action" method="post"><button class="btn s4-action-btn" name="crime" value="player_vehicle_theft" {% if crime_wait > 0 %}disabled{% endif %}>Search Local Garages</button></form>
                    <p class="s4-note">Victims with bodyguards, safehouses and lookouts are harder to rob.</p>
                </article>
            </div>

            <div class="s4-footer-grid">
                <section class="s4-briefing"><h3>Operation Rules</h3><ul><li>Every crime triggers the shared {{ cooldown }} second cooldown.</li><li>Vehicle bonuses improve your operation success chance.</li><li>Failed crimes may cost money, jail time, or vehicle exposure.</li></ul></section>
                <section class="s4-briefing"><h3>Next Moves</h3><div class="s4-route-buttons"><a href="/heists"><span>Plan a major heist</span><b>→</b></a><a href="/garage"><span>Improve your vehicle bonus</span><b>→</b></a><a href="/protection"><span>Buy protection</span><b>→</b></a></div></section>
            </div>
        </div>
    {% endif %}

    {% if page == "bank" %}
        <div class="s3-dashboard s-bank-page">
            <section class="s3-hero s-bank-hero">
                <div>
                    <span class="s3-kicker">Shelby Financial Office</span>
                    <h1>Bank & Credit</h1>
                    <p>Beheer je contant geld, banksaldo, rente en leningen op basis van je rang.</p>
                </div>
                <div class="s3-hero-stats">
                    <div class="s3-stat"><div class="icon">💵</div><small>Cash in kas</small><b>${{ moneyfmt(user.money) }}</b></div>
                    <div class="s3-stat"><div class="icon">🏦</div><small>Op de bank</small><b>${{ moneyfmt(user.bank) }}</b></div>
                    <div class="s3-stat"><div class="icon">💰</div><small>Totaal vermogen</small><b>${{ moneyfmt(bank_total_worth(user)) }}</b></div>
                </div>
            </section>

            <div class="s3-grid-3">
                <article class="s3-panel">
                    <h3>Vermogen overzicht</h3>
                    <div class="s3-mini-list">
                        <div><span>Cash in kas</span><b>${{ moneyfmt(user.money) }}</b></div>
                        <div><span>Bank saldo</span><b>${{ moneyfmt(user.bank) }}</b></div>
                        <div><span>Openstaande lening</span><b class="red">-${{ moneyfmt(user.bank_loan or 0) }}</b></div>
                        <div><span>Netto vermogen</span><b class="gold">${{ moneyfmt(bank_total_worth(user)) }}</b></div>
                    </div>
                    <form action="/bank_action" method="post" class="s-bank-form">
                        <input class="input" type="number" name="amount" min="1" placeholder="Bedrag" required>
                        <div class="s-bank-actions">
                            <button class="btn" name="action" value="deposit">Deposit</button>
                            <button class="btn" name="action" value="withdraw">Withdraw</button>
                        </div>
                    </form>
                </article>

                <article class="s3-panel">
                    <h3>Bank rente</h3>
                    <div class="s3-mini-list">
                        <div><span>Rente percentage</span><b>{{ bank_interest_percent(user) }}% per uur</b></div>
                        <div><span>Beschikbaar nu</span><b class="gold">${{ moneyfmt(bank_interest_ready(user)) }}</b></div>
                        <div><span>Volgende rente</span><b>{% if bank_interest_remaining(user) > 0 %}{{ format_duration(bank_interest_remaining(user)) }}{% else %}Nu beschikbaar{% endif %}</b></div>
                    </div>
                    <form action="/bank_action" method="post">
                        <button class="btn" name="action" value="collect_interest" {% if bank_interest_ready(user) <= 0 %}disabled{% endif %}>Rente innen</button>
                    </form>
                    <p class="s4-note">Rente wordt berekend over je vermogen op de bank, niet over contant geld.</p>
                </article>

                <article class="s3-panel">
                    <h3>Bank lening</h3>
                    <div class="s3-mini-list">
                        <div><span>Jouw rang</span><b>{{ user.rank }}</b></div>
                        <div><span>Maximale lening</span><b>${{ moneyfmt(bank_loan_limit(user)) }}</b></div>
                        <div><span>Nog beschikbaar</span><b class="gold">${{ moneyfmt(bank_available_credit(user)) }}</b></div>
                        <div><span>Rente op lening</span><b>{{ bank_loan_interest_percent(user) }}%</b></div>
                    </div>
                    <form action="/bank_action" method="post" class="s-bank-form">
                        <input class="input" type="number" name="amount" min="1" placeholder="Bedrag" required>
                        <div class="s-bank-actions">
                            <button class="btn" name="action" value="borrow" {% if bank_available_credit(user) <= 0 %}disabled{% endif %}>Lenen</button>
                            <button class="btn" name="action" value="repay" {% if (user.bank_loan or 0) <= 0 %}disabled{% endif %}>Terugbetalen</button>
                        </div>
                    </form>
                    <p class="s4-note">Bij lenen wordt de rente direct aan je schuld toegevoegd. Terugbetalen gebeurt uit je cash in kas.</p>
                </article>
            </div>
        </div>
    {% endif %}

    {% if page == "market" %}
        <h2>🍾 Smuggling Market <span class="gold">• 📍 {{ user.location }}</span></h2>
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

        <hr><h2>📈 Global Smuggling Prices</h2>
        <p class="muted">Prices update every hour. You can view every city from anywhere, so you can plan routes before travelling.</p>
        <table>
            <tr>
                <th>City</th>
                {% for key, data in contraband_by_key.items() %}<th>{{ data.label }}</th>{% endfor %}
            </tr>
            {% for row in market_board %}
            <tr>
                <td class="gold">{{ row.city }}</td>
                {% for price in row.prices %}
                <td>
                    <b>${{ price.price }}</b>
                    {% if price.change > 0 %}<span class="good">▲ +${{ price.change }}</span>{% elif price.change < 0 %}<span class="red">▼ -${{ 0 - price.change }}</span>{% else %}<span class="muted">■ $0</span>{% endif %}
                </td>
                {% endfor %}
            </tr>
            {% endfor %}
        </table>

        <hr><h2>📦 Stock Shipments</h2>
        <p>Send goods to another city without travelling. Economy cargo takes about 1 hour. Paying more unlocks faster cargo. Self-smuggling requires a paid ticket and you choose exactly how much cargo you carry.</p>
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

        <hr><h2>🚂 Self-Smuggling Travel</h2>
        <p>Self-smuggling now uses the same travel times as the Traveling page. Choose a destination, transport method, cargo type and amount. Your selected vehicle travels with you and becomes visible in the destination garage.</p>
        {% if is_user_traveling(user) %}
            <div class="card">
                <h3>⏳ Currently Travelling</h3>
                <p>You are travelling to <b class="gold">{{ user.travel_destination }}</b> by <b>{{ user.travel_mode }}</b>.</p>
                <p>Arrival in: <b class="gold">{{ format_duration(travel_remaining(user)) }}</b></p>
                {% if user.travel_smuggle_quantity and user.travel_smuggle_item_key %}
                    <p>Carried cargo: <b class="gold">{{ user.travel_smuggle_quantity }}x {{ contraband_by_key[user.travel_smuggle_item_key].label }}</b></p>
                {% endif %}
            </div>
        {% else %}
        <div class="grid">
            {% for city in cities %}
            {% if city != user.location %}
            <div class="card">
                <h3>🚂 Travel to {{ city }}{% if is_international_city(city) %} 🌍{% endif %}</h3>
                <form action="/travel_action" method="post">
                    <input type="hidden" name="destination" value="{{ city }}">
                    Transport:<br>
                    <select class="input" name="mode">
                        {% for option in travel_option_rows(user, city) %}
                            <option value="{{ option.key }}">{{ option.label }} · {{ format_duration(option.seconds) }} · ${{ option.cost }}</option>
                        {% endfor %}
                    </select>
                    Cargo to carry:<br>
                    <select class="input" name="item_key">
                        <option value="">No cargo - travel clean</option>
                        {% for item in contraband %}
                            <option value="{{ item.key }}">{{ item.label }} - owned {{ item.quantity }} - local price ${{ item.price }} - risk +{{ item.risk }}%</option>
                        {% endfor %}
                    </select>
                    Amount to smuggle on this trip:<br>
                    <input class="input" type="number" name="smuggle_amount" min="0" value="0">
                    <button class="btn">Start Self-Smuggling Trip</button>
                </form>
            </div>
            {% endif %}
            {% endfor %}
        </div>
        <div class="card" style="margin-top:15px;">
            <h3>⚠️ Customs Rule</h3>
            <p>If customs catches you, only the selected trip cargo is confiscated. The rest of your warehouse stays safe.</p>
            <p class="gold">Example: own 1,000 gin, carry 100 gin, get caught → lose 100 gin only.</p>
        </div>
        {% endif %}
    {% endif %}


    {% if page == "traveling" %}
        <h2>✈️ Traveling</h2>
        <p>Travel to another city without smuggling cargo. Choose between walking, public routes, normal flights, or your own vehicles from the local garage.</p>

        {% if is_user_traveling(user) %}
            <div class="panel">
                <h2>🧭 Journey in Progress</h2>
                <p>Destination: <b class="gold">{{ user.travel_destination }}</b></p>
                <p>Transport: <b class="gold">{{ user.travel_mode }}</b></p>
                <p>Time remaining: <b class="gold">{{ format_duration(travel_remaining(user)) }}</b></p>
                <p class="muted">When the timer reaches zero, your location updates automatically after refreshing or opening any page.</p>
            </div>
        {% else %}
            <div class="dashboard-hero">
                <div class="panel">
                    <h2>📍 Current City</h2>
                    <p class="gold" style="font-size:30px;margin:0;">{{ user.location }}</p>
                    <p>Clean travel only. For smuggling cargo, use the Smuggling page.</p>
                </div>
                <div class="panel">
                    <h2>⚡ Speed Guide</h2>
                    <p>On foot: <b class="gold">3h</b></p>
                    <p>Fastest oldtimer: <b class="gold">5m</b></p>
                    <p>Private Jet: <b class="gold">2m</b></p>
                </div>
            </div>

            <form action="/travel_start" method="post">
                <div class="grid">
                    <div class="card">
                        <h3>🌍 Destination</h3>
                        <select class="input" name="destination">
                            {% for city in cities %}
                                <option value="{{ city }}" {% if city == user.location %}disabled{% endif %}>{{ city }}{% if is_international_city(city) %} 🌍{% endif %}</option>
                            {% endfor %}
                        </select>
                        <p class="muted">After choosing a destination, select one of the transport options below.</p>
                    </div>
                    <div class="card">
                        <h3>🎩 Garage Advantage</h3>
                        <p>Your owned vehicles in <b class="gold">{{ user.location }}</b> unlock faster travel options.</p>
                        <p>Buy better vehicles in the Garage. The new <b class="gold">Private Jet</b> is the fastest option.</p>
                    </div>
                </div>

                <hr>
                <h2>Choose Transport</h2>
                <div class="vehicle-grid">
                    {% for option in travel_options %}
                    <label class="vehicle-card" style="cursor:pointer;">
                        <div class="vehicle-image" style="--vehicle-tone: {{ option.vehicle.tone if option.vehicle else '#333' }}; {% if option.vehicle and option.vehicle.image %}background-image: linear-gradient(rgba(0,0,0,.08),rgba(0,0,0,.72)), url('{{ option.vehicle.image }}');{% endif %}">
                            <div class="vehicle-silhouette">
                                <div class="year">{{ format_duration(option.seconds) }}</div>
                                <div class="icon">{{ option.vehicle.icon if option.vehicle else 'TRAVEL' }}</div>
                            </div>
                        </div>
                        <div class="vehicle-body">
                            <h3>{{ option.label }}</h3>
                            <p>{{ option.description }}</p>
                            <div class="vehicle-meta">
                                <div><small>Duration</small><b>{{ format_duration(option.seconds) }}</b></div>
                                <div><small>Cost</small><b>${{ option.cost }}</b></div>
                            </div>
                            <input type="radio" name="mode" value="{{ option.key }}" {% if loop.first %}checked{% endif %}> Select
                        </div>
                    </label>
                    {% endfor %}
                </div>
                <br>
                <button class="btn">Start Clean Travel</button>
            </form>
        {% endif %}
    {% endif %}


    {% if page == "cargo" %}
        <div class="cargo-hero">
            <div class="cargo-command">
                <h2>📦 Cargo Center</h2>
                <p>Manage all shipments from one command center. Send warehouse stock to another city, track ETA, collect arrived cargo, and watch customs risk before moving valuable goods.</p>
                <div class="quick-actions"><a class="btn" href="/market">🍾 Smuggling Market</a><a class="btn" href="/warehouse">🏚 Warehouse</a><a class="btn" href="/traveling">✈️ Traveling</a></div>
            </div>
            <div class="cargo-kpis">
                <div class="stat-card"><small>Active Shipments</small><b class="gold">{{ cargo_stats.active }}</b></div>
                <div class="stat-card"><small>Arrived Cargo</small><b class="good">{{ cargo_stats.arrived }}</b></div>
                <div class="stat-card"><small>Cargo Value</small><b class="blue">${{ cargo_stats.value }}</b></div>
                <div class="stat-card"><small>Seized Shipments</small><b class="red">{{ cargo_stats.seized }}</b></div>
            </div>
        </div>

        <div class="panel cargo-send-panel">
            <h2>🚢 Send Cargo</h2>
            <p class="muted">Current city: <b class="gold">{{ user.location }}</b>. Faster transport costs more. International routes have higher customs risk.</p>
            <form action="/shipment_action" method="post">
                <input type="hidden" name="return_to" value="cargo">
                <input type="hidden" name="action" value="send">
                <div class="cargo-form-grid">
                    <div>Goods:<br><select class="input" name="item_key">{% for item in contraband %}<option value="{{ item.key }}">{{ item.label }} — owned {{ item.quantity }}</option>{% endfor %}</select></div>
                    <div>Amount:<br><input class="input" type="number" name="amount" min="1" value="1"></div>
                    <div>Destination:<br><select class="input" name="destination">{% for city in cities %}<option value="{{ city }}" {% if city == user.location %}disabled{% endif %}>{{ city }}{% if is_international_city(city) %} 🌍{% endif %}</option>{% endfor %}</select></div>
                    <div>Transport:<br><select class="input" name="speed">{% for key, speed in shipment_speeds.items() %}<option value="{{ key }}">{{ speed.label }} — {{ format_duration(speed.seconds) }}</option>{% endfor %}</select></div>
                    <div><button class="btn" style="width:100%;">Send Cargo</button></div>
                </div>
            </form>
        </div>

        <hr><h2>🚢 Active & Recent Shipments</h2>
        <div class="cargo-board">
            {% for shipment in shipments %}
            <div class="cargo-card">
                <div class="cargo-route">{{ shipment.origin }} → {{ shipment.destination }}</div>
                <span class="cargo-status {% if shipment.status == 'arrived' %}status-arrived{% elif shipment.status == 'seized' %}status-seized{% else %}status-transit{% endif %}">
                    {% if shipment.status == 'arrived' %}Arrived{% elif shipment.status == 'seized' %}Seized{% else %}In Transit{% endif %}
                </span>
                <div class="cargo-meta">
                    <div><small>Goods</small><b>{{ shipment.quantity }}x {{ shipment.label }}</b></div>
                    <div><small>Value at destination</small><b class="good">${{ shipment.value }}</b></div>
                    <div><small>ETA</small><b>{% if shipment.remaining > 0 %}{{ format_duration(shipment.remaining) }}{% elif shipment.status == 'arrived' %}Ready{% else %}-{% endif %}</b></div>
                    <div><small>Collect city</small><b>{{ shipment.destination }}</b></div>
                </div>
                <div class="cargo-progress"><span style="width:{{ shipment.progress }}%;"></span></div>
                {% if shipment.can_collect %}
                    <form action="/shipment_action" method="post">
                        <input type="hidden" name="return_to" value="cargo">
                        <input type="hidden" name="shipment_id" value="{{ shipment.id }}">
                        <button class="btn" name="action" value="collect">Collect Cargo</button>
                    </form>
                {% elif shipment.status == 'arrived' %}
                    <p class="red">Travel to {{ shipment.destination }} to collect this cargo.</p>
                {% elif shipment.status == 'seized' %}
                    <p class="red">Customs seized this shipment.</p>
                {% else %}
                    <p class="muted">Shipment is still moving through the Shelby routes.</p>
                {% endif %}
            </div>
            {% endfor %}
            {% if shipments|length == 0 %}<div class="card"><h3>No shipments yet</h3><p class="muted">Send cargo from your warehouse to start building your international smuggling empire.</p></div>{% endif %}
        </div>
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
        <div class="s5-wrap">
            <section class="s5-hero">
                <div class="s5-eyebrow">Family Headquarters</div>
                <h1>{% if user.family %}{{ user.family.name }}{% else %}THE FAMILY{% endif %}</h1>
                <p>Build a crew, control money, coordinate members and grow into a real city-wide criminal organization.</p>
            </section>

            {% if user.family %}
                <div class="s5-stat-grid">
                    <div class="s5-stat"><small>Your Role</small><b>{{ user.family_role }}</b></div>
                    <div class="s5-stat"><small>Members</small><b>{{ family_member_count(user.family) }}</b></div>
                    <div class="s5-stat"><small>Family Power</small><b>{{ moneyfmt(family_power(user.family)) }}</b></div>
                    <div class="s5-stat"><small>Controlled Cities</small><b>{{ family_territory_count(user.family) }}</b></div>
                </div>

                <div class="s5-command-grid">
                    <section class="s5-panel s5-treasury">
                        <h2>Family Treasury</h2>
                        <div class="s5-money">${{ moneyfmt(user.family.bank) }}</div>
                        <p>Deposits strengthen the family and help finance territory wars. Only Boss and Underboss can withdraw.</p>
                        <form action="/family_action" method="post" class="s5-form-row">
                            <input class="input" type="number" name="amount" min="1" required placeholder="Amount">
                            <button class="btn" name="action" value="deposit">Deposit</button>
                            {% if user.family_role in ["Boss", "Underboss"] %}<button class="btn" name="action" value="withdraw">Withdraw</button>{% endif %}
                        </form>
                    </section>
                    <section class="s5-panel">
                        <h2>Family Bonuses</h2>
                        <div class="s5-bonus-list">
                            <div class="s5-bonus"><small>Crime Income</small><b>+{{ family_bonus(user, 'crime_income') }}%</b></div>
                            <div class="s5-bonus"><small>Smuggling</small><b>+{{ family_bonus(user, 'smuggling') }}%</b></div>
                            <div class="s5-bonus"><small>Protection</small><b>+{{ family_bonus(user, 'protection') }}%</b></div>
                        </div>
                        <p style="margin-top:14px">Bonuses grow with the size of the organization and stay capped for balance.</p>
                        <form action="/family_action" method="post"><button class="btn" name="action" value="leave">Leave Family</button></form>
                    </section>
                </div>

                <section class="s5-panel">
                    <h2>Family Roster</h2>
                    <div class="s5-member-grid">
                        {% for member in family_members %}
                        <article class="s5-member">
                            <div class="s5-avatar">{{ member.username[:1]|upper }}</div>
                            <h3>{{ member.username }}</h3>
                            <span class="s5-role">{{ member.family_role }}</span>
                            <dl>
                                <dt>Rank</dt><dd>{{ member.rank }}</dd>
                                <dt>Power</dt><dd>{{ moneyfmt(power_score(member)) }}</dd>
                                <dt>Location</dt><dd>{{ member.location }}</dd>
                                <dt>Wealth</dt><dd>${{ moneyfmt(member.money + member.bank) }}</dd>
                            </dl>
                        </article>
                        {% endfor %}
                    </div>
                </section>
            {% else %}
                <div class="s5-command-grid">
                    <section class="s5-panel">
                        <h2>Create Family</h2>
                        <p>Cost: <b class="good">$50,000</b>. You become the Boss and start building a crew around your empire.</p>
                        <form action="/family_action" method="post">
                            <input class="input" name="family_name" required maxlength="80" placeholder="Family name">
                            <button class="btn" name="action" value="create">Create Family</button>
                        </form>
                    </section>
                    <section class="s5-panel">
                        <h2>Join Family</h2>
                        <p>Enter the exact family name to join as an Associate.</p>
                        <form action="/family_action" method="post">
                            <input class="input" name="family_name" required maxlength="80" placeholder="Family name">
                            <button class="btn" name="action" value="join">Join Family</button>
                        </form>
                    </section>
                </div>
            {% endif %}

            <section class="s5-panel">
                <h2>Family Rankings</h2>
                <table class="s5-rank-table">
                    <tr><th>#</th><th>Family</th><th>Boss</th><th>Members</th><th>Bank</th><th>Power</th></tr>
                    {% for fam in families %}
                    <tr><td>{{ loop.index }}</td><td>{{ fam.name }}</td><td>{{ fam.boss.username if fam.boss else 'Unknown' }}</td><td>{{ family_member_count(fam) }}</td><td class="good">${{ moneyfmt(fam.bank) }}</td><td class="gold">{{ moneyfmt(family_power(fam)) }}</td></tr>
                    {% endfor %}
                    {% if families|length == 0 %}<tr><td colspan="6" style="color:#777;">No families created yet.</td></tr>{% endif %}
                </table>
            </section>
        </div>
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
                <hr style="border-color:rgba(214,168,95,.18);margin:16px 0;">
                <h3>🤝 Sell to Local Buyer</h3>
                <p>Local buyer price: <b class="good">${{ local_buyer_gin_price(user) }}</b> per gin. This is always 30% below the current city's smuggling price of <b class="gold">${{ local_smuggling_gin_price(user) }}</b>.</p>
                <form action="/local_gin_buyer_action" method="post">
                    Amount:<br><input class="input" type="number" name="amount" min="1" max="{{ business_ready_gin(current_business) }}" placeholder="Ready gin amount">
                    <button class="btn">Sell Local Gin</button>
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
        {% set local_owned_count = owned_vehicles_in_city(user)|length %}
        <section class="garage-stage">
            <div class="garage-command sprint2-command">
                <div class="garage-title-stack">
                    <span class="eyebrow">SHELBY MOTOR WORKS</span>
                    <h1>GARAGE</h1>
                    <p>Your vehicles, from street carts to prestige motors and private aircraft.</p>
                </div>
                <div class="garage-summary-panel sprint2-summary">
                    <div class="s2-kpi"><small>TOTAL VEHICLES</small><b>{{ total_vehicles(user) }}</b><span>Empire fleet</span></div>
                    <div class="s2-kpi"><small>TOTAL VALUE</small><b>${{ moneyfmt(empire_value(user)) }}</b><span>Assets & vehicles</span></div>
                    <div class="s2-kpi"><small>LOCAL GARAGE</small><b>{{ local_owned_count }} / 20</b><span>{{ user.location }}</span></div>
                    <a class="btn buy-vehicle-btn" href="#vehicle-showroom">BUY NEW VEHICLE</a>
                </div>
            </div>

            <div class="garage-tabs sprint2-tabs">
                <a class="active">ALL VEHICLES</a>
                <a>STARTER</a>
                <a>MIDDLE CLASS</a>
                <a>ELITE</a>
                <a>LEGENDARY</a>
                <a>AIRCRAFT</a>
            </div>

            <div id="vehicle-showroom" class="sprint2-showroom">
            {% for group in vehicle_categories %}
                <div class="vehicle-section sprint2-section">
                    <div class="section-heading-row">
                        <h2 class="vehicle-section-title">{{ group.name }}</h2>
                        <span>{{ group.vehicles|length }} available</span>
                    </div>
                    <div class="vehicle-grid sprint2-vehicle-grid">
                        {% for vehicle in group.vehicles %}
                        {% set owned_here = vehicle_quantity(user, user.location, vehicle.key) %}
                        <div class="vehicle-card aaa-vehicle-card sprint2-vehicle-card {% if owned_here > 0 %}is-owned{% endif %}">
                            <div class="vehicle-image sprint2-vehicle-image" style="--vehicle-tone: {{ vehicle.tone }}; {% if vehicle.image %}background-image: linear-gradient(180deg,rgba(0,0,0,.02),rgba(0,0,0,.08) 42%,rgba(0,0,0,.78)), url('{{ vehicle.image }}');{% endif %}">
                                <div class="vehicle-year-badge">{{ vehicle.year }}</div>
                                {% if owned_here > 0 %}<div class="owned-ribbon">OWNED x{{ owned_here }}</div>{% endif %}
                                <div class="vehicle-silhouette sprint2-nameplate">
                                    <div class="icon">{{ vehicle.name }}</div>
                                    <div class="year">{{ vehicle.category }}</div>
                                </div>
                            </div>
                            <div class="vehicle-body sprint2-vehicle-body">
                                <div class="vehicle-specs sprint2-specs">
                                    <span>TOP SPEED<br><b>{{ 90 + vehicle.bonus * 3 }} km/h</b></span>
                                    <span>FUEL<br><b>{% if vehicle.key == 'private_jet' %}Jet Fuel{% else %}{{ 18 - (vehicle.bonus // 8) }} L / 100km{% endif %}</b></span>
                                    <span>BONUS<br><b>+{{ vehicle.bonus }}</b></span>
                                </div>
                                <div class="vehicle-meta compact sprint2-meta">
                                    <div><small>PRICE</small><b class="good">${{ moneyfmt(vehicle.price) }}</b></div>
                                    <div><small>SELL VALUE</small><b class="{% if vehicle.key in exclusive_profit_vehicles %}gold{% else %}muted{% endif %}">${{ moneyfmt(vehicle_sell_price(vehicle)) }}</b></div>
                                    <div><small>LOCAL STOCK</small><b>{{ owned_here }}</b></div>
                                </div>
                                {% if vehicle.key in exclusive_profit_vehicles %}
                                    <p class="gold">Exclusive vehicle: can be resold for profit.</p>
                                {% else %}
                                    <p class="muted">Normal resale: sells below purchase value.</p>
                                {% endif %}
                                <form action="/garage_action" method="post">
                                    <input type="hidden" name="vehicle_key" value="{{ vehicle.key }}">
                                    <button class="btn drive-btn sprint2-buy-btn" name="action" value="buy">PURCHASE</button>
                                    {% if owned_here > 0 %}
                                        <button class="btn" name="action" value="sell">SELL 1 FOR ${{ moneyfmt(vehicle_sell_price(vehicle)) }}</button>
                                    {% endif %}
                                </form>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            {% endfor %}
            </div>
        </section>

        <h2 class="vehicle-section-title city-title">CITY GARAGES</h2>
        <div class="garage-city-grid sprint2-city-grid">
            {% for citydata in garages %}
            <div class="garage-city-card">
                <h3>🚗 {{ citydata.city }} Garage</h3>
                <p>{% if citydata.city == user.location %}<span class="good">You are here</span>{% else %}<span class="muted">Travel here to buy locally</span>{% endif %}</p>
                <p>Total vehicles: <b class="gold">{{ citydata.total }}</b></p>
                <p>Total value: <b class="good">${{ moneyfmt(garage_city_value(citydata)) }}</b></p>
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


    {% if page == "settings" %}
        {% set current_avatar = avatar_info(user) %}
        {% set owned_keys = owned_avatar_keys(user) %}
        <section class="settings-profile-hero">
            <div class="settings-current-avatar">
                <img src="{{ current_avatar.image }}" alt="{{ current_avatar.label }}">
            </div>
            <div>
                <span class="eyebrow">{{ t("player_profile") }}</span>
                <h1>{{ t("profile_settings") }}</h1>
                <p>{{ t("choose_character_text") }}</p>
                <p>{{ t("current_portrait") }}: <b class="gold">{{ current_avatar.label }}</b></p>
                <p>{{ t("profile_stars") }}: <b class="gold">{{ avatar_star_text(user) }}</b></p>
            </div>
        </section>

        <h2>🎩 {{ t("portrait_market") }}</h2>
        <div class="avatar-grid">
            {% for key, avatar in player_avatars.items() %}
            <div class="avatar-choice {% if key == current_avatar.key %}is-selected{% endif %}">
                <img src="{{ avatar.image }}" alt="{{ avatar.label }}">
                <div class="avatar-label">{{ avatar.label }}</div>
                <div class="avatar-price">
                    <b class="gold">{{ "★" * avatar.stars }}{{ "☆" * (5 - avatar.stars) }}</b><br>
                    <span>{% if avatar.price == 0 %}{{ t("free") }}{% else %}${{ moneyfmt(avatar.price) }}{% endif %}</span>
                </div>
                <form action="/avatar_action" method="post">
                    <input type="hidden" name="avatar_key" value="{{ key }}">
                    {% if key in owned_keys %}
                        <button class="btn" name="action" value="use">{% if key == current_avatar.key %}{{ t("selected") }}{% else %}{{ t("use_portrait") }}{% endif %}</button>
                    {% elif avatar.price == 0 %}
                        <button class="btn" name="action" value="buy">{{ t("unlock_free") }}</button>
                    {% else %}
                        <button class="btn" name="action" value="buy">{{ t("buy_portrait") }}</button>
                    {% endif %}
                </form>
            </div>
            {% endfor %}
        </div>
    {% endif %}

    {% if page == "bullets" %}
        <h2>🔫 Weapons Market</h2>
        <p>Your rank gives +{{ rank_bonus(user, 'attack') }}% attack power. Your weapon collection adds extra power to your empire.</p>

        <div class="s3-stat-grid">
            <div class="s3-stat"><div class="icon">🔫</div><small>Bullets</small><b>{{ moneyfmt(user.bullets) }}</b></div>
            <div class="s3-stat"><div class="icon">⚔️</div><small>Weapon Power</small><b>{{ moneyfmt(total_weapon_power(user)) }}</b></div>
            <div class="s3-stat"><div class="icon">🎖</div><small>Rank Attack Bonus</small><b>+{{ rank_bonus(user, 'attack') }}%</b></div>
        </div>

        <div class="card">
            <h3>Buy Ammunition</h3>
            <form action="/bullet_action" method="post">
                <button class="btn" name="action" value="buy_bullet">Buy 10 bullets - $200</button>
            </form>
        </div>

        <h2>Available Weapons</h2>
        <div class="s4-grid">
            {% for weapon in weapon_inventory_rows(user) %}
            <article class="s4-operation-card">
                <div class="s4-card-top">
                    <div style="display:flex;gap:6px;align-items:start">
                        <div class="s4-icon">🔫</div>
                        <div class="s4-title">
                            <h3>{{ weapon.name }}</h3>
                            <p>{{ weapon.rarity }} weapon. Owned: <b class="gold">{{ weapon.quantity }}</b></p>
                        </div>
                    </div>
                    <span class="s4-risk risk-medium">+{{ weapon.attack }} Power</span>
                </div>
                <div class="s4-card-body">
                    <div class="s4-metrics">
                        <div class="s4-metric"><small>Price</small><b>${{ moneyfmt(weapon.price) }}</b></div>
                        <div class="s4-metric"><small>Owned</small><b>{{ weapon.quantity }}</b></div>
                        <div class="s4-metric"><small>Total Power</small><b>{{ moneyfmt(weapon.total_attack) }}</b></div>
                    </div>
                    <form action="/bullet_action" method="post">
                        <input type="hidden" name="weapon_key" value="{{ weapon.key }}">
                        <button class="btn s4-action-btn" name="action" value="buy_weapon">Buy Weapon</button>
                    </form>
                </div>
            </article>
            {% endfor %}
        </div>

        <p class="muted">You can also steal weapons from the Crimes page with the Weapon Theft operation.</p>

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
        <div class="s4-ops-wrap">
            <section class="s4-hero">
                <div class="s4-hero-grid">
                    <div>
                        <div class="s4-eyebrow">Crew Briefing</div>
                        <h1>SHELBY HEISTS</h1>
                        <p>Coordinate bigger jobs for serious cash and reputation. Heists consume bullets, require organizational power, and can send you to jail if the crew fails.</p>
                    </div>
                    <div class="s4-cooldown">
                        <small>Heist Cooldown</small>
                        {% if heist_wait > 0 %}<b>{{ format_duration(heist_wait) }}</b><div class="s4-bar"><span style="width:{{ ((heist_cooldown-heist_wait) / heist_cooldown * 100)|int }}%"></span></div>{% else %}<b>Ready</b><div class="s4-bar"><span style="width:100%"></span></div>{% endif %}
                    </div>
                </div>
            </section>
            <div class="s4-stats">
                <div class="s4-stat"><small>Power</small><b>{{ moneyfmt(power_score(user)) }}</b></div>
                <div class="s4-stat"><small>Bullets</small><b>{{ moneyfmt(user.bullets) }}</b></div>
                <div class="s4-stat"><small>Completed</small><b>{{ user.heists_successful }}</b></div>
                <div class="s4-stat"><small>Rank</small><b>{{ user.rank }}</b></div>
            </div>

            <div class="s4-section-head"><h2>Major Operations</h2><span>Briefing Cards</span></div>
            <div class="s4-grid">
                {% for plan in heist_plans %}
                {% set risk_class = 'risk-low' if plan.success_chance >= 65 else ('risk-medium' if plan.success_chance >= 48 else 'risk-high') %}
                {% set difficulty = 'Low' if plan.success_chance >= 65 else ('Medium' if plan.success_chance >= 48 else 'High') %}
                <article class="s4-operation-card {% if heist_wait > 0 or not plan.ready %}s4-disabled{% endif %}">
                    <div class="s4-card-top">
                        <div style="display:flex;gap:6px;align-items:start"><div class="s4-icon">{% if plan.key == 'bookmaker' %}📒{% elif plan.key == 'train' %}🚂{% else %}🚔{% endif %}</div><div class="s4-title"><h3>{{ plan.name }}</h3><p>{% if plan.key == 'bookmaker' %}Shake down bookmakers and collect street debt.{% elif plan.key == 'train' %}Hit a payroll convoy before it reaches the depot.{% else %}Raid a police armory for a high-pressure score.{% endif %}</p></div></div>
                        <span class="s4-risk {{ risk_class }}">{{ difficulty }} Difficulty</span>
                    </div>
                    <div class="s4-card-body">
                        <div class="s4-metrics">
                            <div class="s4-metric"><small>Required Power</small><b>{{ moneyfmt(plan.min_power) }}</b></div>
                            <div class="s4-metric"><small>Bullets</small><b>{{ plan.bullets }}</b></div>
                            <div class="s4-metric"><small>Reward</small><b>${{ moneyfmt(plan.cash_min) }} - ${{ moneyfmt(plan.cash_max) }}</b></div>
                            <div class="s4-metric"><small>{{ t("exp") }}</small><b>{{ plan.exp }}</b></div>
                            <div class="s4-metric"><small>Success</small><b>{{ plan.success_chance }}%</b><div class="s4-success-ring"><span style="width:{{ plan.success_chance }}%"></span></div></div>
                            <div class="s4-metric"><small>Jail Risk</small><b>{{ plan.jail }}s</b></div>
                        </div>
                        {% if not plan.ready %}<div class="s4-warning">Not enough power or bullets yet. Build your crew before executing this plan.</div>{% endif %}
                        <form action="/heist_action" method="post" class="s4-card-actions" style="margin-top:12px">
                            <input type="hidden" name="heist_key" value="{{ plan.key }}">
                            <button class="btn s4-action-btn" {% if heist_wait > 0 or not plan.ready %}disabled{% endif %}>Execute Heist</button>
                        </form>
                    </div>
                </article>
                {% endfor %}
            </div>
            <div class="s4-footer-grid">
                <section class="s4-briefing"><h3>Crew Briefing</h3><ul><li>Heists use bullets immediately when started.</li><li>Power, rank, family and vehicle bonuses can improve odds.</li><li>Failure can cost cash and send you to jail.</li></ul></section>
                <section class="s4-briefing"><h3>Prepare The Crew</h3><div class="s4-route-buttons"><a href="/bullets"><span>Buy weapons</span><b>→</b></a><a href="/garage"><span>Increase vehicle edge</span><b>→</b></a><a href="/family"><span>Build family strength</span><b>→</b></a></div></section>
            </div>
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

        <div class="card">
            <h3>🗝️ Free a Prisoner</h3>
            <p>Break another player out of jail. A successful rescue gives you EXP and can improve your rank progress.</p>
            <p>Cost: <b class="gold">${{ moneyfmt(jail_break_cost) }}</b> cash + <b class="gold">{{ jail_break_bullets }}</b> bullets</p>
            <p>Success chance: <b class="gold">{{ jail_break_success_chance }}%</b></p>
            <p>Reward on success: <b class="gold">+{{ jail_break_exp_reward }} EXP</b></p>
            <p>Risk on failure: <b class="red">{{ jail_break_fail_jail_chance }}%</b> chance that you get jailed.</p>

            {% if remaining|default(0) > 0 %}
                <p class="red">You cannot free another prisoner while you are in jail.</p>
            {% elif jailed_players %}
                <form action="/free_prisoner" method="post">
                    <select class="input" name="target_id" required>
                        {% for prisoner in jailed_players %}
                            <option value="{{ prisoner.id }}">{{ prisoner.username }} - {{ prisoner.jail_remaining }}s remaining</option>
                        {% endfor %}
                    </select>
                    <button class="btn">Start Jail Break</button>
                </form>
            {% else %}
                <p class="muted">There are no other prisoners to free right now.</p>
            {% endif %}
        </div>

        <p>Total arrests: <b>{{ user.arrests }}</b></p>
    {% endif %}

    {% if page == "territories" %}
        <div class="s5-wrap">
            <section class="s5-hero">
                <div class="s5-eyebrow">Territory Command</div>
                <h1>WAR ROOM</h1>
                <p>Control cities, collect taxes and fight rival families for strategic bonuses across the criminal map.</p>
            </section>

            <div class="s5-war-room">
                <div class="s5-war"><small>Attack Cost</small><b>${{ moneyfmt(territory_war_cost) }}</b></div>
                <div class="s5-war"><small>Bullets Required</small><b>{{ moneyfmt(territory_war_bullets) }}</b></div>
                <div class="s5-war"><small>Minimum Members</small><b>{{ territory_min_members }}</b></div>
                <div class="s5-war"><small>Protection Window</small><b>{{ format_duration(territory_protection_time) }}</b></div>
            </div>

            {% if user.family %}
                <div class="s5-command-grid">
                    <section class="s5-panel">
                        <h2>{{ user.family.name }} Empire</h2>
                        <div class="s5-stat-grid" style="grid-template-columns:repeat(3,1fr)">
                            <div class="s5-stat"><small>Controlled Cities</small><b>{{ family_territory_count(user.family) }}</b></div>
                            <div class="s5-stat"><small>Tax Income</small><b>${{ moneyfmt(family_territory_tax_per_hour(user.family)) }}/hr</b></div>
                            <div class="s5-stat"><small>Family Bank</small><b>${{ moneyfmt(user.family.bank) }}</b></div>
                        </div>
                    </section>
                    <section class="s5-panel">
                        <h2>Collect Taxes</h2>
                        <p>Taxes go directly into the family treasury. Only Boss and Underboss can collect them.</p>
                        <form action="/territory_action" method="post"><button class="btn" name="action" value="collect_tax">Collect Territory Taxes</button></form>
                    </section>
                </div>
            {% else %}
                <section class="s5-panel"><p class="red">You need to join or create a family before using territory wars.</p><a class="btn" href="/family">Open Family HQ</a></section>
            {% endif %}

            <section class="s5-panel">
                <h2>City Control Map</h2>
                <div class="s5-territory-grid">
                    {% for territory in territories %}
                    <article class="s5-territory">
                        <div class="top">
                            <h3>{{ territory.city }}</h3>
                            {% if territory.family_id and user.family and territory.family_id == user.family_id %}<span class="s5-status owned">Your Family</span>{% elif territory.family %}<span class="s5-status enemy">Rival Control</span>{% else %}<span class="s5-status state">State Controlled</span>{% endif %}
                        </div>
                        <div class="body">
                            <div class="s5-line"><span>Controller</span><b>{% if territory.family %}{{ territory.family.name }}{% else %}The State{% endif %}</b></div>
                            <div class="s5-line"><span>Hourly Tax</span><b class="good">${{ moneyfmt(territory_tax_data[territory.city].tax_per_hour) }}</b></div>
                            <div class="s5-line"><span>Bonus</span><b>{{ territory_tax_data[territory.city].bonus }}</b></div>
                            <div class="s5-line"><span>Status</span><b>{% if territory.protected_until and territory.protected_until > now_time %}<span class="s5-status protected">Protected {{ format_duration((territory.protected_until - now_time)|int) }}</span>{% else %}<span class="s5-status owned">Open</span>{% endif %}</b></div>
                            {% if user.family and (not territory.family_id or territory.family_id != user.family_id) %}
                            <form action="/territory_action" method="post" style="margin-top:14px">
                                <input type="hidden" name="city" value="{{ territory.city }}">
                                <button class="btn" name="action" value="attack">Declare War</button>
                            </form>
                            {% else %}
                                <p style="color:#8f8170;margin:14px 0 0">No hostile action available.</p>
                            {% endif %}
                        </div>
                    </article>
                    {% endfor %}
                </div>
            </section>
        </div>
    {% endif %}


    {% if page == "friends" %}
        <h2>👥 {{ t("friends") }}</h2>
        <p class="muted">{{ t("friends") }} are your personal network. They stay separate from Family.</p>

        <div class="card">
            <h3>🔎 {{ t("find_friends") }}</h3>
            <form action="/friends" method="get" style="display:grid;grid-template-columns:1fr auto;gap:10px;align-items:end">
                <div>
                    <label>{{ t("search_players") }}</label><br>
                    <input class="input" name="q" value="{{ friend_query or '' }}" placeholder="Username">
                </div>
                <button class="btn">{{ t("search_friends") }}</button>
            </form>

            {% if friend_query %}
                {% if friend_search_results %}
                    <div class="message-list" style="margin-top:14px">
                        {% for player in friend_search_results %}
                            {% set fstatus = friendship_status(user, player) %}
                            <div class="message-card">
                                <div class="message-icon">👤</div>
                                <div>
                                    <div class="message-title">{{ player.username }}</div>
                                    <div class="message-meta">
                                        {{ player.rank }} · {{ player.location }} · {{ avatar_star_text(player) }}
                                        · {% if is_online(player) %}<span class="good">🟢 {{ t("online") }}</span>{% else %}<span class="red">⚫ {{ t("offline") }}</span>{% endif %}
                                    </div>
                                </div>
                                <div>
                                    {% if fstatus == "none" %}
                                        <form action="/friend_action" method="post">
                                            <input type="hidden" name="target_id" value="{{ player.id }}">
                                            <button class="btn" name="action" value="add">👥 {{ t("add_friend") }}</button>
                                        </form>
                                    {% elif fstatus == "sent" %}
                                        <span class="gold">⏳ {{ t("friend_request_sent") }}</span>
                                    {% elif fstatus == "incoming" %}
                                        <form action="/friend_action" method="post">
                                            <input type="hidden" name="target_id" value="{{ player.id }}">
                                            <button class="btn" name="action" value="accept">✅ {{ t("accept") }}</button>
                                            <button class="btn" name="action" value="decline">✖ {{ t("decline") }}</button>
                                        </form>
                                    {% else %}
                                        <span class="good">✅ {{ t("already_friends") }}</span>
                                    {% endif %}
                                </div>
                            </div>
                        {% endfor %}
                    </div>
                {% else %}
                    <p class="muted" style="margin-top:12px">{{ t("no_players_found") }}</p>
                {% endif %}
            {% endif %}
        </div>

        <div class="card">
            <h3>📥 {{ t("incoming_requests") }}</h3>
            {% if incoming_requests %}
                <div class="message-list">
                    {% for link in incoming_requests %}
                    <div class="message-card">
                        <div class="message-icon">👥</div>
                        <div>
                            <div class="message-title">{{ link.user.username }}</div>
                            <div class="message-meta">
                                {{ link.user.rank }} · {{ link.user.location }} · {{ avatar_star_text(link.user) }}
                                · {% if is_online(link.user) %}<span class="good">🟢 {{ t("online") }}</span>{% else %}<span class="red">⚫ {{ t("offline") }}</span>{% endif %}
                            </div>
                        </div>
                        <div>
                            <form action="/friend_action" method="post">
                                <input type="hidden" name="target_id" value="{{ link.user_id }}">
                                <button class="btn" name="action" value="accept">✅ {{ t("accept") }}</button>
                                <button class="btn" name="action" value="decline">✖ {{ t("decline") }}</button>
                            </form>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            {% else %}
                <p class="muted">{{ t("no_friend_requests") }}</p>
            {% endif %}
        </div>

        <div class="card">
            <h3>👥 {{ t("my_friends") }}</h3>
            {% if friend_links %}
                <div class="message-list">
                    {% for link in friend_links %}
                    {% set friend = friend_user_from_link(user, link) %}
                    {% if friend %}
                    <div class="message-card">
                        <div class="message-icon">{% if is_online(friend) %}🟢{% else %}⚫{% endif %}</div>
                        <div>
                            <div class="message-title">{{ friend.username }}</div>
                            <div class="message-meta">
                                {{ friend.rank }} · {{ friend.location }} · {{ avatar_star_text(friend) }}
                                · {% if is_online(friend) %}<span class="good">{{ t("online") }}</span>{% else %}<span class="red">{{ t("offline") }}</span>{% endif %}
                            </div>
                            <div class="message-body">
                                <b>{{ t("power") }}:</b> {{ power_score(friend) }}
                                · <b>{{ t("family") }}:</b> {% if friend.family %}{{ friend.family.name }}{% else %}{{ t("solo") }}{% endif %}
                            </div>
                        </div>
                        <div>
                            <a class="btn" href="/messages?to={{ friend.username }}">✉ {{ t("send_message") }}</a>
                            <form action="/friend_action" method="post" style="margin-top:8px">
                                <input type="hidden" name="target_id" value="{{ friend.id }}">
                                <button class="btn" name="action" value="remove">🗑 {{ t("remove_friend") }}</button>
                            </form>
                        </div>
                    </div>
                    {% endif %}
                    {% endfor %}
                </div>
            {% else %}
                <p class="muted">{{ t("no_friends") }}</p>
            {% endif %}
        </div>
    {% endif %}

    {% if page == "ranking" %}
        <h2>🏆 {{ t("rankings") }}</h2>
        <p>{{ t("rankings_sorted") }}</p>

        <div class="ranking-player-panel">
            <h3>🎯 Your Ranking Position</h3>
            <div class="ranking-player-grid">
                <div class="ranking-player-stat">
                    <small>Your Rank Number</small>
                    <b>#{{ current_player_rank }}</b>
                </div>
                <div class="ranking-player-stat">
                    <small>Current Rank</small>
                    <b>{{ user.rank }}</b>
                </div>
                <div class="ranking-player-stat">
                    <small>Performance Score</small>
                    <b>{{ moneyfmt(current_rank_info.score) }}</b>
                </div>
                <div class="ranking-player-stat">
                    <small>Next Rank</small>
                    <b>{% if current_rank_info.next %}{{ current_rank_info.next[1] }}{% else %}Maximum Rank{% endif %}</b>
                </div>
            </div>
            <div class="rank-progress-track">
                <span style="width:{{ current_rank_percent }}%"></span>
            </div>
            <div class="rank-next-note">
                {% if current_rank_info.next %}
                    Needed for next rank: <b class="gold">{{ moneyfmt(current_rank_info.next[0]) }}</b> score.
                    Remaining: <b class="gold">{{ moneyfmt(current_rank_info.remaining) }}</b>.
                {% else %}
                    You have reached the highest rank.
                {% endif %}
            </div>
        </div>

        <div class="ranking-search-card">
            <form class="ranking-search-form" action="/ranking" method="get">
                <div>
                    <label>Search player</label><br>
                    <input class="input" name="q" value="{{ search_query or '' }}" placeholder="Username">
                </div>
                <button class="btn">Search</button>
            </form>

            {% if search_query and searched_player %}
                {% set s_avatar = avatar_info(searched_player) %}
                <div class="ranking-search-result">
                    <div class="ranking-search-rank">#{{ searched_rank }}</div>
                    <div>
                        <h3 style="margin:0 0 8px">{{ searched_player.username }}</h3>
                        <div class="ranking-search-meta">
                            <span><b>Rank:</b> {{ searched_player.rank }}</span>
                            <span><b>Profile:</b> {{ avatar_star_text(searched_player) }}</span>
                            <span><b>City:</b> {{ searched_player.location }}</span>
                            <span><b>Family:</b> {% if searched_player.family %}{{ searched_player.family.name }}{% else %}{{ t("solo") }}{% endif %}</span>
                            <span><b>Status:</b> {% if is_online(searched_player) %}<span class="good">Online</span>{% else %}<span class="red">Offline</span>{% endif %}</span>
                            <span><b>EXP:</b> {{ moneyfmt(searched_player.exp) }}</span>
                            <span><b>Power:</b> {{ moneyfmt(power_score(searched_player)) }}</span>
                            <span><b>Wealth:</b> ${{ moneyfmt(searched_player.money + searched_player.bank) }}</span>
                        </div>
                        {% if searched_player.id != user.id %}
                            {% set fstatus = friendship_status(user, searched_player) %}
                            <div style="margin-top:12px;display:flex;gap:10px;flex-wrap:wrap">
                                {% if fstatus == "none" %}
                                    <form action="/friend_action" method="post">
                                        <input type="hidden" name="target_id" value="{{ searched_player.id }}">
                                        <button class="btn" name="action" value="add">👥 {{ t("add_friend") }}</button>
                                    </form>
                                {% elif fstatus == "sent" %}
                                    <span class="gold">⏳ {{ t("friend_request_sent") }}</span>
                                {% elif fstatus == "incoming" %}
                                    <form action="/friend_action" method="post">
                                        <input type="hidden" name="target_id" value="{{ searched_player.id }}">
                                        <button class="btn" name="action" value="accept">✅ {{ t("accept") }}</button>
                                        <button class="btn" name="action" value="decline">✖ {{ t("decline") }}</button>
                                    </form>
                                {% else %}
                                    <span class="good">✅ {{ t("already_friends") }}</span>
                                {% endif %}
                                <a class="btn" href="/messages?to={{ searched_player.username }}">✉ {{ t("send_message") }}</a>
                            </div>
                        {% endif %}
                    </div>
                </div>
            {% elif search_query %}
                <div class="ranking-search-result">
                    <div class="ranking-search-rank">?</div>
                    <div>
                        <h3 style="margin:0">No player found</h3>
                        <p class="muted">No username matched "{{ search_query }}".</p>
                    </div>
                </div>
            {% endif %}
        </div>

        <table>
            <tr><th>#</th><th>{{ t("name") }}</th><th>{{ t("profile") }}</th><th>{{ t("status") }}</th><th>{{ t("rank") }}</th><th>{{ t("city") }}</th><th>{{ t("exp") }}</th><th>{{ t("power") }}</th><th>{{ t("wealth") }}</th></tr>
            {% for u in users %}
            {% set u_avatar = avatar_info(u) %}
            <tr class="{% if loop.index <= 10 %}ranking-top10{% endif %} {% if loop.index <= 3 %}ranking-top3{% endif %}">
                <td>
                    <span class="{% if loop.index <= 10 %}ranking-place-badge{% endif %}">
                        {% if loop.index == 1 %}🥇{% elif loop.index == 2 %}🥈{% elif loop.index == 3 %}🥉{% else %}#{{ loop.index }}{% endif %}
                    </span>
                </td>
                <td>
                    {{ u.username }}
                    {% if loop.index <= 10 %}<span class="ranking-title-crown">★ TOP 10</span>{% endif %}
                </td>
                <td>
                    <span class="ranking-avatar"><img src="{{ u_avatar.image }}" alt="{{ u_avatar.label }}"></span>
                    <span class="gold">{{ avatar_star_text(u) }}</span>
                </td>
                <td>{% if u.is_dead %}<span class="red">💀 {{ t("dead") }}</span>{% else %}<span class="good">🟢 {{ t("active") }}</span>{% endif %}</td>
                <td>{{ u.rank }}</td><td>{{ u.location }}</td><td>{{ moneyfmt(u.exp) }}</td>
                <td class="gold">{{ moneyfmt(power_score(u)) }}</td><td class="good">${{ moneyfmt(u.money + u.bank) }}</td>
            </tr>
            {% endfor %}
        </table>

        <div class="rank-overview-card">
            <h2>📜 Rank Overview</h2>
            <p class="muted">These are the available ranks in the game. Ranks are based on total performance score, not only raw EXP.</p>
            <div class="rank-overview-grid">
                {% for rank_row in rank_overview_rows() %}
                    <div class="rank-overview-row {% if loop.last %}top-rank{% endif %}">
                        <b>{{ rank_row.name }}</b>
                        <span>{% if rank_row.score == 0 %}Starter rank{% else %}{{ moneyfmt(rank_row.score) }} score{% endif %}</span>
                    </div>
                {% endfor %}
            </div>
        </div>

    {% endif %}

    </div>
    </main>
</div>
{% endif %}
<script>
function updateServerClock(){
  const el=document.getElementById('server-clock');
  if(!el) return;
  const d=new Date();
  el.textContent=d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
}
updateServerClock();
setInterval(updateServerClock,1000);
</script>
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




LANGUAGES = {
    "en": {"flag": "🇬🇧", "name": "English"},
    "us": {"flag": "🇺🇸", "name": "American"},
    "nl": {"flag": "🇳🇱", "name": "Nederlands"},
    "de": {"flag": "🇩🇪", "name": "Deutsch"},
    "fr": {"flag": "🇫🇷", "name": "Français"},
    "es": {"flag": "🇪🇸", "name": "Español"},
}

TRANSLATIONS = {
    "en": {"overview":"Overview","dashboard":"Dashboard","messages":"Messages","rankings":"Rankings","logistics":"Logistics","smuggling":"Smuggling","cargo":"Cargo","traveling":"Traveling","warehouse":"Warehouse","crime_group":"Crime","crimes":"Crimes","heists":"Heists","protection":"Protection","weapons":"Weapons","empire":"Empire","garage":"Garage","businesses":"Businesses","properties":"Properties","casinos":"Casinos","licenses":"Licenses","influence":"Influence","family":"Family","territories":"Territories","account":"Account","bank":"Bank","jail":"Jail","logout":"Logout","cash":"Cash","gin":"Gin","power":"Power","bullets":"Bullets","server_time":"Server Time","location":"Location","rank":"Rank","exp":"EXP","travelling":"Travelling","solo":"Solo","hero_kicker":"Shelby Company Operations","hero_text":"Manage your empire with power, reputation and precision.","language":"Language"},
    "us": {"overview":"Overview","dashboard":"Dashboard","messages":"Messages","rankings":"Rankings","logistics":"Logistics","smuggling":"Bootlegging","cargo":"Cargo","traveling":"Travel","warehouse":"Warehouse","crime_group":"Crime","crimes":"Crimes","heists":"Heists","protection":"Protection","weapons":"Weapons","empire":"Empire","garage":"Garage","businesses":"Businesses","properties":"Properties","casinos":"Casinos","licenses":"Licenses","influence":"Influence","family":"Family","territories":"Territories","account":"Account","bank":"Bank","jail":"Jail","logout":"Logout","cash":"Cash","gin":"Liquor","power":"Power","bullets":"Ammo","server_time":"Server Time","location":"Location","rank":"Rank","exp":"XP","travelling":"Traveling","solo":"Solo","hero_kicker":"Shelby Company Operations","hero_text":"Run your empire with cash, muscle and reputation.","language":"Language"},
    "nl": {"overview":"Overzicht","dashboard":"Dashboard","messages":"Berichten","rankings":"Ranglijsten","logistics":"Logistiek","smuggling":"Smokkel","cargo":"Vracht","traveling":"Reizen","warehouse":"Magazijn","crime_group":"Misdaad","crimes":"Crimes","heists":"Overvallen","protection":"Bescherming","weapons":"Wapens","empire":"Imperium","garage":"Garage","businesses":"Bedrijven","properties":"Vastgoed","casinos":"Casino's","licenses":"Licenties","influence":"Invloed","family":"Familie","territories":"Gebieden","account":"Account","bank":"Bank","jail":"Gevangenis","logout":"Uitloggen","cash":"Kas","gin":"Gin","power":"Macht","bullets":"Kogels","server_time":"Servertijd","location":"Locatie","rank":"Rang","exp":"EXP","travelling":"Onderweg","solo":"Solo","hero_kicker":"Shelby Company Operaties","hero_text":"Beheer je imperium met macht, reputatie en precisie.","language":"Taal"},
    "de": {"overview":"Übersicht","dashboard":"Dashboard","messages":"Nachrichten","rankings":"Ranglisten","logistics":"Logistik","smuggling":"Schmuggel","cargo":"Fracht","traveling":"Reisen","warehouse":"Lagerhaus","crime_group":"Verbrechen","crimes":"Verbrechen","heists":"Raubzüge","protection":"Schutz","weapons":"Waffen","empire":"Imperium","garage":"Garage","businesses":"Geschäfte","properties":"Immobilien","casinos":"Casinos","licenses":"Lizenzen","influence":"Einfluss","family":"Familie","territories":"Gebiete","account":"Konto","bank":"Bank","jail":"Gefängnis","logout":"Abmelden","cash":"Bargeld","gin":"Gin","power":"Macht","bullets":"Kugeln","server_time":"Serverzeit","location":"Ort","rank":"Rang","exp":"EP","travelling":"Unterwegs","solo":"Solo","hero_kicker":"Shelby Company Operationen","hero_text":"Verwalte dein Imperium mit Macht, Ruf und Präzision.","language":"Sprache"},
    "fr": {"overview":"Vue d'ensemble","dashboard":"Tableau de bord","messages":"Messages","rankings":"Classements","logistics":"Logistique","smuggling":"Contrebande","cargo":"Cargaison","traveling":"Voyage","warehouse":"Entrepôt","crime_group":"Crime","crimes":"Crimes","heists":"Braquages","protection":"Protection","weapons":"Armes","empire":"Empire","garage":"Garage","businesses":"Affaires","properties":"Propriétés","casinos":"Casinos","licenses":"Licences","influence":"Influence","family":"Famille","territories":"Territoires","account":"Compte","bank":"Banque","jail":"Prison","logout":"Déconnexion","cash":"Espèces","gin":"Gin","power":"Puissance","bullets":"Balles","server_time":"Heure serveur","location":"Lieu","rank":"Rang","exp":"EXP","travelling":"En voyage","solo":"Solo","hero_kicker":"Opérations Shelby Company","hero_text":"Gérez votre empire avec puissance, réputation et précision.","language":"Langue"},
    "es": {"overview":"Resumen","dashboard":"Panel","messages":"Mensajes","rankings":"Clasificaciones","logistics":"Logística","smuggling":"Contrabando","cargo":"Carga","traveling":"Viajes","warehouse":"Almacén","crime_group":"Crimen","crimes":"Crímenes","heists":"Atracos","protection":"Protección","weapons":"Armas","empire":"Imperio","garage":"Garaje","businesses":"Negocios","properties":"Propiedades","casinos":"Casinos","licenses":"Licencias","influence":"Influencia","family":"Familia","territories":"Territorios","account":"Cuenta","bank":"Banco","jail":"Cárcel","logout":"Salir","cash":"Efectivo","gin":"Ginebra","power":"Poder","bullets":"Balas","server_time":"Hora del servidor","location":"Ubicación","rank":"Rango","exp":"EXP","travelling":"Viajando","solo":"Solo","hero_kicker":"Operaciones Shelby Company","hero_text":"Administra tu imperio con poder, reputación y precisión.","language":"Idioma"},
}

EXTRA_TRANSLATIONS = {
    "en": {
        "settings": "Settings",
        "profile_settings": "Profile Settings",
        "player_profile": "Player Profile",
        "portrait_market": "Portrait Market",
        "choose_character_text": "Buy prestige portraits and choose the character that represents your gang.",
        "current_portrait": "Current portrait",
        "profile_stars": "Profile stars",
        "selected": "Selected",
        "use_portrait": "Use portrait",
        "buy_portrait": "Buy portrait",
        "unlock_free": "Unlock free",
        "free": "FREE",
        "profile": "Profile",
        "name": "Name",
        "status": "Status",
        "city": "City",
        "wealth": "Wealth",
        "active": "Active",
        "dead": "Dead",
        "rankings_sorted": "Rankings are sorted by Power first, then Wealth.",
        "not_enough_cash_avatar": "Not enough cash.",
        "avatar_costs": "costs",
        "avatar_unlocked": "Unlocked",
        "avatar_set_profile": "and set it as your profile portrait.",
        "avatar_must_buy": "You must buy this portrait before you can use it.",
    },
    "us": {
        "settings": "Settings",
        "profile_settings": "Profile Settings",
        "player_profile": "Player Profile",
        "portrait_market": "Portrait Market",
        "choose_character_text": "Buy prestige portraits and pick the character that represents your crew.",
        "current_portrait": "Current portrait",
        "profile_stars": "Profile stars",
        "selected": "Selected",
        "use_portrait": "Use portrait",
        "buy_portrait": "Buy portrait",
        "unlock_free": "Unlock free",
        "free": "FREE",
        "profile": "Profile",
        "name": "Name",
        "status": "Status",
        "city": "City",
        "wealth": "Wealth",
        "active": "Active",
        "dead": "Dead",
        "rankings_sorted": "Rankings are sorted by Power first, then Wealth.",
        "not_enough_cash_avatar": "Not enough cash.",
        "avatar_costs": "costs",
        "avatar_unlocked": "Unlocked",
        "avatar_set_profile": "and set it as your profile portrait.",
        "avatar_must_buy": "You must buy this portrait before you can use it.",
    },
    "nl": {
        "settings": "Instellingen",
        "profile_settings": "Profielinstellingen",
        "player_profile": "Spelersprofiel",
        "portrait_market": "Portretmarkt",
        "choose_character_text": "Koop prestigieuze portretten en kies het personage dat jouw bende vertegenwoordigt.",
        "current_portrait": "Huidig portret",
        "profile_stars": "Profielsterren",
        "selected": "Geselecteerd",
        "use_portrait": "Portret gebruiken",
        "buy_portrait": "Portret kopen",
        "unlock_free": "Gratis ontgrendelen",
        "free": "GRATIS",
        "profile": "Profiel",
        "name": "Naam",
        "status": "Status",
        "city": "Stad",
        "wealth": "Vermogen",
        "active": "Actief",
        "dead": "Dood",
        "rankings_sorted": "Ranglijsten worden eerst gesorteerd op Macht en daarna op Vermogen.",
        "not_enough_cash_avatar": "Niet genoeg contant geld.",
        "avatar_costs": "kost",
        "avatar_unlocked": "Ontgrendeld",
        "avatar_set_profile": "en ingesteld als jouw profielportret.",
        "avatar_must_buy": "Je moet dit portret eerst kopen voordat je het kunt gebruiken.",
    },
    "de": {
        "settings": "Einstellungen",
        "profile_settings": "Profileinstellungen",
        "player_profile": "Spielerprofil",
        "portrait_market": "Porträtmarkt",
        "choose_character_text": "Kaufe Prestige-Porträts und wähle den Charakter, der deine Bande repräsentiert.",
        "current_portrait": "Aktuelles Porträt",
        "profile_stars": "Profilsterne",
        "selected": "Ausgewählt",
        "use_portrait": "Porträt verwenden",
        "buy_portrait": "Porträt kaufen",
        "unlock_free": "Kostenlos freischalten",
        "free": "KOSTENLOS",
        "profile": "Profil",
        "name": "Name",
        "status": "Status",
        "city": "Stadt",
        "wealth": "Vermögen",
        "active": "Aktiv",
        "dead": "Tot",
        "rankings_sorted": "Ranglisten werden zuerst nach Macht und danach nach Vermögen sortiert.",
        "not_enough_cash_avatar": "Nicht genug Bargeld.",
        "avatar_costs": "kostet",
        "avatar_unlocked": "Freigeschaltet",
        "avatar_set_profile": "und als dein Profilporträt eingestellt.",
        "avatar_must_buy": "Du musst dieses Porträt kaufen, bevor du es verwenden kannst.",
    },
    "fr": {
        "settings": "Paramètres",
        "profile_settings": "Paramètres du profil",
        "player_profile": "Profil du joueur",
        "portrait_market": "Marché des portraits",
        "choose_character_text": "Achetez des portraits de prestige et choisissez le personnage qui représente votre gang.",
        "current_portrait": "Portrait actuel",
        "profile_stars": "Étoiles du profil",
        "selected": "Sélectionné",
        "use_portrait": "Utiliser le portrait",
        "buy_portrait": "Acheter le portrait",
        "unlock_free": "Débloquer gratuitement",
        "free": "GRATUIT",
        "profile": "Profil",
        "name": "Nom",
        "status": "Statut",
        "city": "Ville",
        "wealth": "Richesse",
        "active": "Actif",
        "dead": "Mort",
        "rankings_sorted": "Les classements sont triés par Puissance puis par Richesse.",
        "not_enough_cash_avatar": "Pas assez d'argent.",
        "avatar_costs": "coûte",
        "avatar_unlocked": "Débloqué",
        "avatar_set_profile": "et défini comme portrait de profil.",
        "avatar_must_buy": "Vous devez acheter ce portrait avant de pouvoir l'utiliser.",
    },
    "es": {
        "settings": "Ajustes",
        "profile_settings": "Ajustes de perfil",
        "player_profile": "Perfil del jugador",
        "portrait_market": "Mercado de retratos",
        "choose_character_text": "Compra retratos de prestigio y elige el personaje que representa a tu banda.",
        "current_portrait": "Retrato actual",
        "profile_stars": "Estrellas del perfil",
        "selected": "Seleccionado",
        "use_portrait": "Usar retrato",
        "buy_portrait": "Comprar retrato",
        "unlock_free": "Desbloquear gratis",
        "free": "GRATIS",
        "profile": "Perfil",
        "name": "Nombre",
        "status": "Estado",
        "city": "Ciudad",
        "wealth": "Riqueza",
        "active": "Activo",
        "dead": "Muerto",
        "rankings_sorted": "Las clasificaciones se ordenan primero por Poder y luego por Riqueza.",
        "not_enough_cash_avatar": "No tienes suficiente efectivo.",
        "avatar_costs": "cuesta",
        "avatar_unlocked": "Desbloqueado",
        "avatar_set_profile": "y establecido como tu retrato de perfil.",
        "avatar_must_buy": "Debes comprar este retrato antes de poder usarlo.",
    },
}
for lang_code, rows in EXTRA_TRANSLATIONS.items():
    TRANSLATIONS.setdefault(lang_code, {}).update(rows)


PLAYER_MESSAGE_TRANSLATIONS = {'en': {'compose_message': 'Compose Message', 'send_message': 'Send Message', 'recipient': 'Recipient', 'subject': 'Subject', 'message': 'Message', 'player_messages': 'Player messages', 'message_center_text': 'All empire alerts and player messages in one place.', 'all': 'All', 'inbox_empty': 'Your inbox is empty.', 'no_messages': 'No messages', 'unread': 'Unread', 'mark_read': 'Mark Read', 'delete': 'Delete', 'message_sent': 'Message sent.', 'recipient_not_found': 'Recipient not found.', 'cannot_message_self': 'You cannot send a message to yourself.', 'subject_body_required': 'Subject and message are required.'}, 'us': {'compose_message': 'Compose Message', 'send_message': 'Send Message', 'recipient': 'Recipient', 'subject': 'Subject', 'message': 'Message', 'player_messages': 'Player mail', 'message_center_text': 'All empire alerts and player mail in one place.', 'all': 'All', 'inbox_empty': 'Your inbox is empty.', 'no_messages': 'No messages', 'unread': 'Unread', 'mark_read': 'Mark Read', 'delete': 'Delete', 'message_sent': 'Message sent.', 'recipient_not_found': 'Recipient not found.', 'cannot_message_self': 'You cannot send a message to yourself.', 'subject_body_required': 'Subject and message are required.'}, 'nl': {'compose_message': 'Bericht opstellen', 'send_message': 'Bericht versturen', 'recipient': 'Ontvanger', 'subject': 'Onderwerp', 'message': 'Bericht', 'player_messages': 'Spelersberichten', 'message_center_text': 'Alle empire-meldingen en spelersberichten op één plek.', 'all': 'Alles', 'inbox_empty': 'Je inbox is leeg.', 'no_messages': 'Geen berichten', 'unread': 'Ongelezen', 'mark_read': 'Markeer gelezen', 'delete': 'Verwijderen', 'message_sent': 'Bericht verstuurd.', 'recipient_not_found': 'Ontvanger niet gevonden.', 'cannot_message_self': 'Je kunt jezelf geen bericht sturen.', 'subject_body_required': 'Onderwerp en bericht zijn verplicht.'}, 'de': {'compose_message': 'Nachricht verfassen', 'send_message': 'Nachricht senden', 'recipient': 'Empfänger', 'subject': 'Betreff', 'message': 'Nachricht', 'player_messages': 'Spielernachrichten', 'message_center_text': 'Alle Imperiums-Meldungen und Spielernachrichten an einem Ort.', 'all': 'Alle', 'inbox_empty': 'Dein Posteingang ist leer.', 'no_messages': 'Keine Nachrichten', 'unread': 'Ungelesen', 'mark_read': 'Als gelesen markieren', 'delete': 'Löschen', 'message_sent': 'Nachricht gesendet.', 'recipient_not_found': 'Empfänger nicht gefunden.', 'cannot_message_self': 'Du kannst dir selbst keine Nachricht senden.', 'subject_body_required': 'Betreff und Nachricht sind erforderlich.'}, 'fr': {'compose_message': 'Rédiger un message', 'send_message': 'Envoyer le message', 'recipient': 'Destinataire', 'subject': 'Sujet', 'message': 'Message', 'player_messages': 'Messages des joueurs', 'message_center_text': "Toutes les alertes d'empire et messages des joueurs au même endroit.", 'all': 'Tous', 'inbox_empty': 'Votre boîte de réception est vide.', 'no_messages': 'Aucun message', 'unread': 'Non lu', 'mark_read': 'Marquer comme lu', 'delete': 'Supprimer', 'message_sent': 'Message envoyé.', 'recipient_not_found': 'Destinataire introuvable.', 'cannot_message_self': 'Vous ne pouvez pas vous envoyer un message.', 'subject_body_required': 'Le sujet et le message sont obligatoires.'}, 'es': {'compose_message': 'Redactar mensaje', 'send_message': 'Enviar mensaje', 'recipient': 'Destinatario', 'subject': 'Asunto', 'message': 'Mensaje', 'player_messages': 'Mensajes de jugadores', 'message_center_text': 'Todas las alertas del imperio y mensajes de jugadores en un solo lugar.', 'all': 'Todos', 'inbox_empty': 'Tu bandeja de entrada está vacía.', 'no_messages': 'Sin mensajes', 'unread': 'No leído', 'mark_read': 'Marcar como leído', 'delete': 'Eliminar', 'message_sent': 'Mensaje enviado.', 'recipient_not_found': 'Destinatario no encontrado.', 'cannot_message_self': 'No puedes enviarte un mensaje a ti mismo.', 'subject_body_required': 'El asunto y el mensaje son obligatorios.'}}
for lang_code, rows in PLAYER_MESSAGE_TRANSLATIONS.items():
    TRANSLATIONS.setdefault(lang_code, {}).update(rows)


PLAYER_MESSAGE_READ_TRANSLATIONS = {
    "en": {"sent_messages":"Sent messages","inbox":"Inbox","opened":"Opened","not_opened":"Not opened yet","opened_by":"Opened by","sent_to":"Sent to","read_receipt":"Read receipt"},
    "us": {"sent_messages":"Sent mail","inbox":"Inbox","opened":"Opened","not_opened":"Not opened yet","opened_by":"Opened by","sent_to":"Sent to","read_receipt":"Read receipt"},
    "nl": {"sent_messages":"Verzonden berichten","inbox":"Inbox","opened":"Geopend","not_opened":"Nog niet geopend","opened_by":"Geopend door","sent_to":"Verzonden naar","read_receipt":"Leesbevestiging"},
    "de": {"sent_messages":"Gesendete Nachrichten","inbox":"Posteingang","opened":"Geöffnet","not_opened":"Noch nicht geöffnet","opened_by":"Geöffnet von","sent_to":"Gesendet an","read_receipt":"Lesebestätigung"},
    "fr": {"sent_messages":"Messages envoyés","inbox":"Boîte de réception","opened":"Ouvert","not_opened":"Pas encore ouvert","opened_by":"Ouvert par","sent_to":"Envoyé à","read_receipt":"Accusé de lecture"},
    "es": {"sent_messages":"Mensajes enviados","inbox":"Bandeja de entrada","opened":"Abierto","not_opened":"Aún no abierto","opened_by":"Abierto por","sent_to":"Enviado a","read_receipt":"Confirmación de lectura"},
}
for lang_code, rows in PLAYER_MESSAGE_READ_TRANSLATIONS.items():
    TRANSLATIONS.setdefault(lang_code, {}).update(rows)


PLAYER_MESSAGE_OPEN_TRANSLATIONS = {
    "en": {"open_message":"Open Message","message_hidden_until_open":"Message content is hidden until you open it.","message_opened":"Message opened."},
    "us": {"open_message":"Open Message","message_hidden_until_open":"Message content is hidden until you open it.","message_opened":"Message opened."},
    "nl": {"open_message":"Bericht openen","message_hidden_until_open":"De inhoud is verborgen totdat je het bericht opent.","message_opened":"Bericht geopend."},
    "de": {"open_message":"Nachricht öffnen","message_hidden_until_open":"Der Inhalt ist verborgen, bis du die Nachricht öffnest.","message_opened":"Nachricht geöffnet."},
    "fr": {"open_message":"Ouvrir le message","message_hidden_until_open":"Le contenu est masqué jusqu'à l'ouverture du message.","message_opened":"Message ouvert."},
    "es": {"open_message":"Abrir mensaje","message_hidden_until_open":"El contenido está oculto hasta que abras el mensaje.","message_opened":"Mensaje abierto."},
}
for lang_code, rows in PLAYER_MESSAGE_OPEN_TRANSLATIONS.items():
    TRANSLATIONS.setdefault(lang_code, {}).update(rows)


FRIENDS_TRANSLATIONS = {
    "en": {"friends":"Friends","add_friend":"Add Friend","friend_request_sent":"Friend request sent","already_friends":"Friends","incoming_requests":"Incoming Requests","my_friends":"My Friends","accept":"Accept","decline":"Decline","remove_friend":"Remove Friend","no_friend_requests":"No pending friend requests.","no_friends":"No friends yet.","friend_added":"Friend request sent.","friend_accepted":"Friend request accepted.","friend_declined":"Friend request declined.","friend_removed":"Friend removed.","friend_request_exists":"Friend request already exists.","send_message":"Send Message"},
    "us": {"friends":"Friends","add_friend":"Add Friend","friend_request_sent":"Friend request sent","already_friends":"Friends","incoming_requests":"Incoming Requests","my_friends":"My Friends","accept":"Accept","decline":"Decline","remove_friend":"Remove Friend","no_friend_requests":"No pending friend requests.","no_friends":"No friends yet.","friend_added":"Friend request sent.","friend_accepted":"Friend request accepted.","friend_declined":"Friend request declined.","friend_removed":"Friend removed.","friend_request_exists":"Friend request already exists.","send_message":"Send Message"},
    "nl": {"friends":"Vrienden","add_friend":"Vriend toevoegen","friend_request_sent":"Vriendschapsverzoek verzonden","already_friends":"Vrienden","incoming_requests":"Binnenkomende verzoeken","my_friends":"Mijn vrienden","accept":"Accepteren","decline":"Weigeren","remove_friend":"Vriend verwijderen","no_friend_requests":"Geen openstaande vriendschapsverzoeken.","no_friends":"Nog geen vrienden.","friend_added":"Vriendschapsverzoek verzonden.","friend_accepted":"Vriendschapsverzoek geaccepteerd.","friend_declined":"Vriendschapsverzoek geweigerd.","friend_removed":"Vriend verwijderd.","friend_request_exists":"Vriendschapsverzoek bestaat al.","send_message":"Bericht sturen"},
    "de": {"friends":"Freunde","add_friend":"Freund hinzufügen","friend_request_sent":"Freundschaftsanfrage gesendet","already_friends":"Freunde","incoming_requests":"Eingehende Anfragen","my_friends":"Meine Freunde","accept":"Akzeptieren","decline":"Ablehnen","remove_friend":"Freund entfernen","no_friend_requests":"Keine ausstehenden Freundschaftsanfragen.","no_friends":"Noch keine Freunde.","friend_added":"Freundschaftsanfrage gesendet.","friend_accepted":"Freundschaftsanfrage angenommen.","friend_declined":"Freundschaftsanfrage abgelehnt.","friend_removed":"Freund entfernt.","friend_request_exists":"Freundschaftsanfrage existiert bereits.","send_message":"Nachricht senden"},
    "fr": {"friends":"Amis","add_friend":"Ajouter un ami","friend_request_sent":"Demande d'ami envoyée","already_friends":"Amis","incoming_requests":"Demandes reçues","my_friends":"Mes amis","accept":"Accepter","decline":"Refuser","remove_friend":"Retirer l'ami","no_friend_requests":"Aucune demande d'ami en attente.","no_friends":"Aucun ami pour le moment.","friend_added":"Demande d'ami envoyée.","friend_accepted":"Demande d'ami acceptée.","friend_declined":"Demande d'ami refusée.","friend_removed":"Ami retiré.","friend_request_exists":"La demande d'ami existe déjà.","send_message":"Envoyer un message"},
    "es": {"friends":"Amigos","add_friend":"Añadir amigo","friend_request_sent":"Solicitud de amistad enviada","already_friends":"Amigos","incoming_requests":"Solicitudes recibidas","my_friends":"Mis amigos","accept":"Aceptar","decline":"Rechazar","remove_friend":"Eliminar amigo","no_friend_requests":"No hay solicitudes de amistad pendientes.","no_friends":"Aún no tienes amigos.","friend_added":"Solicitud de amistad enviada.","friend_accepted":"Solicitud de amistad aceptada.","friend_declined":"Solicitud de amistad rechazada.","friend_removed":"Amigo eliminado.","friend_request_exists":"La solicitud de amistad ya existe.","send_message":"Enviar mensaje"},
}
for lang_code, rows in FRIENDS_TRANSLATIONS.items():
    TRANSLATIONS.setdefault(lang_code, {}).update(rows)


FRIENDS_ONLINE_SEARCH_TRANSLATIONS = {
    "en": {"online":"Online","offline":"Offline","find_friends":"Find Friends","search_friends":"Search friends","search_players":"Search players","no_players_found":"No players found.","online_status":"Online status"},
    "us": {"online":"Online","offline":"Offline","find_friends":"Find Friends","search_friends":"Search friends","search_players":"Search players","no_players_found":"No players found.","online_status":"Online status"},
    "nl": {"online":"Online","offline":"Offline","find_friends":"Vrienden zoeken","search_friends":"Vrienden zoeken","search_players":"Spelers zoeken","no_players_found":"Geen spelers gevonden.","online_status":"Online status"},
    "de": {"online":"Online","offline":"Offline","find_friends":"Freunde finden","search_friends":"Freunde suchen","search_players":"Spieler suchen","no_players_found":"Keine Spieler gefunden.","online_status":"Online-Status"},
    "fr": {"online":"En ligne","offline":"Hors ligne","find_friends":"Trouver des amis","search_friends":"Rechercher des amis","search_players":"Rechercher des joueurs","no_players_found":"Aucun joueur trouvé.","online_status":"Statut en ligne"},
    "es": {"online":"En línea","offline":"Desconectado","find_friends":"Buscar amigos","search_friends":"Buscar amigos","search_players":"Buscar jugadores","no_players_found":"No se encontraron jugadores.","online_status":"Estado en línea"},
}
for lang_code, rows in FRIENDS_ONLINE_SEARCH_TRANSLATIONS.items():
    TRANSLATIONS.setdefault(lang_code, {}).update(rows)


MESSAGE_REPLY_TRANSLATIONS = {
    "en": {"reply":"Reply"},
    "us": {"reply":"Reply"},
    "nl": {"reply":"Reageren"},
    "de": {"reply":"Antworten"},
    "fr": {"reply":"Répondre"},
    "es": {"reply":"Responder"},
}
for lang_code, rows in MESSAGE_REPLY_TRANSLATIONS.items():
    TRANSLATIONS.setdefault(lang_code, {}).update(rows)

PAGE_TITLE_KEYS = {"dashboard":"dashboard","messages":"messages","crime":"crimes","bank":"bank","market":"smuggling","traveling":"traveling","cargo":"cargo","warehouse":"warehouse","assets":"businesses","properties":"properties","garage":"garage","casino":"casinos","licenses":"licenses","influence":"influence","family":"family","territories":"territories","bullets":"weapons","protection":"protection","heists":"heists","jail":"jail","ranking":"rankings","settings":"settings","friends":"friends"}
PAGE_ICONS = {"dashboard":"🏠","messages":"📬","crime":"⚡","bank":"🏦","market":"🍾","traveling":"✈️","cargo":"📦","warehouse":"🏚","assets":"🏭","properties":"🏛","garage":"🚗","casino":"🃏","licenses":"🎫","influence":"🏛","family":"👪","territories":"⚔️","bullets":"🔫","protection":"🛡️","heists":"💼","jail":"🚔","ranking":"🏆","settings":"⚙️","friends":"👥"}
def current_language():
    lang = session.get("language", "en")
    return lang if lang in LANGUAGES else "en"
def tr(key):
    lang = current_language()
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))
def translated_page_title(page):
    key = PAGE_TITLE_KEYS.get(page)
    icon = PAGE_ICONS.get(page, "")
    label = tr(key) if key else PAGE_TITLES.get(page, "Peaky Empire")
    return f"{icon} {label}".strip()

def moneyfmt(value):
    try:
        return "{:,}".format(int(safe_number(value)))
    except Exception:
        return str(value)

def exp_percent(user):
    try:
        exp = int(safe_number(getattr(user, "exp", 0)))
        ordered = sorted(RANKS, key=lambda x: x[0])
        current_floor = 0
        next_needed = None
        for needed, rank_name in ordered:
            if exp >= needed:
                current_floor = needed
            elif next_needed is None:
                next_needed = needed
                break
        if next_needed is None:
            return 100
        span = max(1, next_needed - current_floor)
        return max(0, min(100, int(((exp - current_floor) / span) * 100)))
    except Exception:
        return 0

def render_page(user, page, **kwargs):
    return render_template_string(
        HTML_UI,
        game_name=GAME_NAME,
        user=user,
        page=page,
        page_title=translated_page_title(page),
        languages=LANGUAGES,
        current_language=current_language(),
        t=tr,
        request=request,
        player_avatars=PLAYER_AVATARS,
        avatar_info=avatar_info,
        owned_avatar_keys=owned_avatar_keys,
        owns_avatar=owns_avatar,
        avatar_stars=avatar_stars,
        avatar_star_text=avatar_star_text,
        avatar_prestige_value=avatar_prestige_value,
        power_score=power_score,
        rank_progress_score=rank_progress_score,
        next_rank_info=next_rank_info,
        rank_overview_rows=rank_overview_rows,
        weapon_inventory_rows=weapon_inventory_rows,
        total_weapon_power=total_weapon_power,
        weapon_types=WEAPON_TYPES,
        rank_progress_percent=rank_progress_percent,
        rank_bonus=rank_bonus,
        bribe_cost=bribe_cost,
        bribe_chance=bribe_chance,
        total_distilleries=total_distilleries,
        business_ready_gin=business_ready_gin,
        business_collectable_gin=business_collectable_gin,
        local_smuggling_gin_price=local_smuggling_gin_price,
        local_buyer_gin_price=local_buyer_gin_price,
        total_ready_gin=total_ready_gin,
        warehouse_free_space=warehouse_free_space,
        total_vehicles=total_vehicles,
        vehicle_bonus=vehicle_bonus,
        vehicle_quantity=vehicle_quantity,
        vehicle_categories_for_showroom=vehicle_categories_for_showroom,
        garage_city_value=garage_city_value,
        vehicle_theft_options=vehicle_theft_options(),
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
        warehouse_quantity=warehouse_quantity,
        warehouse_capacity=warehouse_capacity,
        warehouse_level_info=warehouse_level_info,
        travel_cost_to=travel_cost_to,
        travel_option_rows=travel_option_rows,
        travel_remaining=travel_remaining,
        format_duration=format_duration,
        is_user_traveling=is_user_traveling,
        is_international_city=is_international_city,
        contraband_by_key=CONTRABAND,
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
        shipment_value=shipment_value,
        unread_message_count=unread_message_count,
        message_category_icon=message_category_icon,
        message_age=message_age,
        message_rows=message_rows,
        friendship_status=friendship_status,
        friend_user_from_link=friend_user_from_link,
        is_online=is_online,
        online_status_text=online_status_text,
        sent_message_rows=sent_message_rows,
        message_read_status=message_read_status,
        casino_vault_total=casino_vault_total,
        dynamic_market_price=dynamic_market_price,
        market_price_change=market_price_change,
        market_price_trend=market_price_trend,
        price_trend_symbol=price_trend_symbol,
        bank_interest_percent=bank_interest_percent,
        bank_interest_remaining=bank_interest_remaining,
        bank_interest_ready=bank_interest_ready,
        bank_loan_limit=bank_loan_limit,
        bank_loan_interest_percent=bank_loan_interest_percent,
        bank_available_credit=bank_available_credit,
        bank_total_worth=bank_total_worth,
        now_time=time.time(),
        moneyfmt=moneyfmt,
        exp_percent=exp_percent,
        **kwargs,
    )


@app.route("/set_language", methods=["POST"])
def set_language():
    lang = request.form.get("language", "en")
    if lang in LANGUAGES:
        session["language"] = lang
    target = request.form.get("next") or request.referrer or url_for("dashboard")
    if not str(target).startswith("/"):
        target = url_for("dashboard")
    return redirect(target)


@app.route("/avatar_action", methods=["POST"])
def avatar_action():
    user, error = login_required()
    if error:
        return error

    avatar_key = request.form.get("avatar_key", "straat_jongen")
    action = request.form.get("action", "use")

    if avatar_key not in PLAYER_AVATARS:
        avatar_key = "straat_jongen"

    avatar = PLAYER_AVATARS[avatar_key]
    owned = owned_avatar_keys(user)

    if action == "buy" and avatar_key not in owned:
        price = int(avatar.get("price", 0))
        if int(safe_number(user.money)) < price:
            return redirect(url_for("settings", msg=f"{tr('not_enough_cash_avatar')} {avatar['label']} {tr('avatar_costs')} ${moneyfmt(price)}."))
        user.money = int(safe_number(user.money)) - price
        owned.add(avatar_key)
        set_owned_avatar_keys(user, owned)
        user.avatar_key = avatar_key
        db.session.commit()
        return redirect(url_for("settings", msg=f"{tr('avatar_unlocked')} {avatar['label']} {tr('avatar_set_profile')}"))

    if avatar_key not in owned:
        return redirect(url_for("settings", msg=tr("avatar_must_buy")))

    user.avatar_key = avatar_key
    set_owned_avatar_keys(user, owned)
    db.session.commit()

    target = request.form.get("next") or request.referrer or url_for("settings")
    if not str(target).startswith("/"):
        target = url_for("settings")
    return redirect(target)


@app.route("/settings")
def settings():
    user, error = login_required()
    if error:
        return error
    return render_page(user, "settings", msg=request.args.get("msg"))


@app.route("/dashboard")
def dashboard():
    user, redirect_response = login_required()
    if redirect_response:
        return redirect_response

    alive_users = User.query.filter_by(is_dead=False).all()
    top_richest = sorted(alive_users, key=lambda p: int(safe_number(p.money)) + int(safe_number(p.bank)), reverse=True)[:5]
    top_power = [
        {"user": player, "power": power_score(player)}
        for player in sorted(alive_users, key=lambda p: power_score(p), reverse=True)[:5]
    ]

    return render_page(
        user,
        "dashboard",
        top_richest=top_richest,
        top_power=top_power,
        msg=request.args.get("msg"),
    )


@app.route("/messages")
def messages():
    user, error = login_required()
    if error:
        return error
    category = request.args.get("category", "all")
    prefill_recipient = request.args.get("to", "").strip()
    prefill_subject = request.args.get("subject", "").strip()
    recipients = User.query.filter(User.id != user.id, User.is_dead == False).order_by(User.username.asc()).limit(200).all()
    return render_page(
        user,
        "messages",
        messages=message_rows(user, category),
        sent_messages=sent_message_rows(user),
        message_recipients=recipients,
        prefill_recipient=prefill_recipient,
        prefill_subject=prefill_subject,
        msg=request.args.get("msg"),
    )


@app.route("/send_player_message", methods=["POST"])
def send_player_message():
    user, error = login_required()
    if error:
        return error

    recipient_name = request.form.get("recipient", "").strip()
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "").strip()

    if not subject or not body:
        return redirect(url_for("messages", msg=tr("subject_body_required")))

    target = User.query.filter(User.username.ilike(recipient_name)).first()
    if not target or target.is_dead:
        return redirect(url_for("messages", msg=tr("recipient_not_found")))

    if target.id == user.id:
        return redirect(url_for("messages", msg=tr("cannot_message_self")))

    title = f"From {user.username}: {subject[:90]}"
    clean_body = body[:2000]
    create_message(
        target.id,
        "player",
        title,
        clean_body,
        commit=True,
        sender_id=user.id,
    )

    return redirect(url_for("messages", category="player", msg=tr("message_sent")))


@app.route("/message_action", methods=["POST"])
def message_action():
    user, error = login_required()
    if error:
        return error
    message_id = safe_int(request.form.get("message_id"))
    action = request.form.get("action")
    message = Message.query.filter_by(id=message_id, user_id=user.id).first()
    if not message:
        message = Message.query.filter_by(id=message_id, sender_id=user.id, category="player").first()
    if not message:
        return redirect(url_for("messages", msg="Message not found."))
    if action in ["open", "read"]:
        message.is_read = True
        if safe_number(getattr(message, "read_at", 0)) <= 0:
            message.read_at = time.time()
        db.session.commit()
        return redirect(url_for("messages", msg=tr("message_opened")))
    if action == "delete":
        db.session.delete(message)
        db.session.commit()
        return redirect(url_for("messages", msg=tr("delete")))
    return redirect(url_for("messages", msg="Invalid message action."))


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
        theft_vehicle_options=vehicle_theft_options(),
        weapon_theft_arrest_risk=WEAPON_THEFT_ARREST_RISK,
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
    now = time.time()
    jailed_players = User.query.filter(
        User.jail_until > now,
        User.id != user.id,
        User.is_dead == False
    ).order_by(User.username.asc()).all()
    for prisoner in jailed_players:
        prisoner.jail_remaining = jail_remaining(prisoner)
    return render_page(
        user,
        "jail",
        remaining=remaining,
        bribe_wait=bribe_wait,
        jailed_players=jailed_players,
        jail_break_cost=JAIL_BREAK_COST,
        jail_break_bullets=JAIL_BREAK_BULLETS,
        jail_break_success_chance=JAIL_BREAK_SUCCESS_CHANCE,
        jail_break_exp_reward=JAIL_BREAK_EXP_REWARD,
        jail_break_fail_jail_chance=JAIL_BREAK_FAIL_JAIL_CHANCE,
        msg=request.args.get("msg"),
    )


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


@app.route("/free_prisoner", methods=["POST"])
def free_prisoner():
    user, error = login_required()
    if error:
        return error

    if jail_remaining(user) > 0:
        return redirect(url_for("jail", msg="You cannot free another prisoner while you are in jail."))

    target_id = safe_int(request.form.get("target_id"))
    target = User.query.get(target_id)

    if not target or target.is_dead:
        return redirect(url_for("jail", msg="That prisoner could not be found."))

    if target.id == user.id:
        return redirect(url_for("jail", msg="You cannot free yourself with a jail break. Use the corrupt officer option."))

    if jail_remaining(target) <= 0:
        target.jail_until = 0.0
        db.session.commit()
        return redirect(url_for("jail", msg=f"{target.username} is already free."))

    if safe_number(user.money) < JAIL_BREAK_COST:
        return redirect(url_for("jail", msg=f"You need ${JAIL_BREAK_COST} cash to prepare a jail break."))

    if safe_number(user.bullets) < JAIL_BREAK_BULLETS:
        return redirect(url_for("jail", msg=f"You need {JAIL_BREAK_BULLETS} bullets to prepare a jail break."))

    user.money = safe_number(user.money) - JAIL_BREAK_COST
    user.bullets = safe_number(user.bullets) - JAIL_BREAK_BULLETS

    if random.randint(1, 100) <= JAIL_BREAK_SUCCESS_CHANCE:
        target.jail_until = 0.0
        target.bribe_available_at = 0.0
        user.exp = safe_number(user.exp) + JAIL_BREAK_EXP_REWARD
        user.update_rank()

        create_message(
            target.id,
            "security",
            "Jail Break",
            f"{user.username} broke you out of prison. You are free again.",
            commit=False,
        )
        create_message(
            user.id,
            "security",
            "Jail Break Successful",
            f"You freed {target.username} from prison and gained {JAIL_BREAK_EXP_REWARD} EXP.",
            commit=False,
        )

        db.session.commit()
        return redirect(url_for("jail", msg=f"✅ You freed {target.username} and gained {JAIL_BREAK_EXP_REWARD} EXP. Rank progress improved."))

    punishment = ""
    if random.randint(1, 100) <= JAIL_BREAK_FAIL_JAIL_CHANCE:
        user.jail_until = max(safe_number(user.jail_until), time.time() + JAIL_BREAK_FAIL_JAIL_TIME)
        user.arrests = int(safe_number(user.arrests)) + 1
        punishment = f" You were caught and jailed for {JAIL_BREAK_FAIL_JAIL_TIME} seconds."

    create_message(
        user.id,
        "security",
        "Jail Break Failed",
        f"Your attempt to free {target.username} failed.{punishment}",
        commit=False,
    )

    db.session.commit()
    return redirect(url_for("jail", msg=f"❌ Jail break failed. You lost ${JAIL_BREAK_COST} and {JAIL_BREAK_BULLETS} bullets.{punishment}"))


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

    if crime_key == "weapon_theft":
        user.last_crime = now
        arrest_chance = max(5, WEAPON_THEFT_ARREST_RISK - lookout_arrest_reduction(user))
        if random.randint(1, 100) <= arrest_chance:
            jail_time = random.randint(120, 360)
            fine = reduce_loss_by_protection(user, int(max(250, safe_number(user.money) * 0.10)))
            user.money = max(0, safe_number(user.money) - fine)
            user.jail_until = time.time() + int(jail_time * influence_jail_multiplier(user))
            user.arrests = safe_number(user.arrests) + 1
            db.session.commit()
            return redirect(url_for("jail", msg=f"🚔 You were caught during a weapon raid. Fine: ${fine}. Jail time: {int(jail_time * influence_jail_multiplier(user))} seconds."))

        weapon_key, weapon = random_stolen_weapon()
        if weapon:
            add_weapon(user, weapon_key, 1)
            bullets_found = random.randint(5, 25)
            exp = random.randint(15, 40)
            user.bullets = int(safe_number(user.bullets)) + bullets_found
            user.exp += exp
            msg = f"🔫 Weapon raid successful. You stole a {weapon['name']} and found {bullets_found} bullets. +{exp} EXP."
        else:
            bullets_found = random.randint(3, 15)
            exp = random.randint(3, 10)
            user.bullets = int(safe_number(user.bullets)) + bullets_found
            user.exp += exp
            msg = f"You found an ammunition crate with {bullets_found} bullets. +{exp} EXP."

        user.update_rank()
        db.session.commit()
        return redirect(url_for("index", msg=msg))

    if crime_key == "street_vehicle_theft":
        user.last_crime = now
        arrest_chance = max(3, 18 - lookout_arrest_reduction(user))
        if random.randint(1, 100) <= arrest_chance:
            jail_time = random.randint(90, 240)
            fine = reduce_loss_by_protection(user, int(max(100, safe_number(user.money) * 0.08)))
            user.money = max(0, safe_number(user.money) - fine)
            user.jail_until = time.time() + int(jail_time * influence_jail_multiplier(user))
            user.arrests = safe_number(user.arrests) + 1
            db.session.commit()
            return redirect(url_for("jail", msg=f"🚔 You were caught during a vehicle theft. Fine: ${fine}. Jail time: {int(jail_time * influence_jail_multiplier(user))} seconds."))

        vehicle = street_theft_vehicle_roll()
        if vehicle:
            add_vehicle_to_city(user, user.location, vehicle["key"], 1)
            exp = random.randint(12, 30)
            user.exp += exp
            msg = f"🚗 Street theft successful. You stole a {vehicle['year']} {vehicle['name']} and stored it in {user.location}. +{exp} EXP."
        else:
            roll = random.randint(1, 100)
            if roll <= 20:
                cash = random.randint(80, 350)
                user.money += cash
                user.exp += 3
                msg = f"You found stolen parts and sold them for ${cash}."
            elif roll <= 30:
                cash = random.randint(350, 1200)
                user.money += cash
                user.exp += 6
                msg = f"You stripped a vehicle for valuable parts and earned ${cash}."
            else:
                user.exp += 1
                msg = "You searched the parking garages but found nothing worth stealing."
        user.update_rank()
        db.session.commit()
        return redirect(url_for("index", msg=msg))

    if crime_key == "player_vehicle_theft":
        target, target_row, vehicle = random_player_vehicle_theft_target(user)
        if not target or not target_row or not vehicle:
            return redirect(url_for("index", msg=f"No stealable player vehicles were found in {user.location}."))

        target_vehicle_key = target_row.vehicle_key
        user.last_crime = now
        chance = player_vehicle_theft_chance(user, target, target_vehicle_key)
        caught_chance = max(8, 28 - rank_bonus(user, "crime_chance") // 2)
        if random.randint(1, 100) <= chance:
            remove_vehicle_from_city(target, user.location, target_vehicle_key, 1)
            add_vehicle_to_city(user, user.location, target_vehicle_key, 1)
            exp = random.randint(25, 70)
            user.exp += exp
            create_message(
                target.id,
                "crime",
                "Vehicle Stolen",
                f"{user.username} stole your {vehicle['year']} {vehicle['name']} from your {user.location} garage.",
                commit=False,
            )
            msg = f"🚗 You stole {target.username}'s {vehicle['year']} {vehicle['name']} from {user.location}. +{exp} EXP."
        else:
            create_message(
                target.id,
                "crime",
                "Attempted Vehicle Theft",
                f"{user.username} attempted to steal your {vehicle['year']} {vehicle['name']} in {user.location}, but failed.",
                commit=False,
            )
            if random.randint(1, 100) <= caught_chance:
                jail_time = int(random.randint(120, 360) * influence_jail_multiplier(user))
                fine = reduce_loss_by_protection(user, int(max(250, vehicle['price'] * 0.03)))
                user.money = max(0, safe_number(user.money) - fine)
                user.jail_until = time.time() + jail_time
                user.arrests = safe_number(user.arrests) + 1
                db.session.commit()
                return redirect(url_for("jail", msg=f"🚔 Player vehicle theft failed and you were caught. Fine: ${fine}. Jail time: {jail_time} seconds."))
            msg = f"Vehicle theft failed. {target.username}'s security and luck protected the {vehicle['name']}."
        user.update_rank()
        db.session.commit()
        return redirect(url_for("index", msg=msg))

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
    action = request.form.get("action")
    amount = safe_int(request.form.get("amount"))

    if action == "collect_interest":
        interest = bank_interest_ready(user)
        if interest <= 0:
            remaining = bank_interest_remaining(user)
            if safe_number(user.bank) <= 0:
                return redirect(url_for("bank", msg="Je hebt geen geld op de bank om rente over te ontvangen."))
            return redirect(url_for("bank", msg=f"Rente is nog niet beschikbaar. Wacht {format_duration(remaining)}."))
        user.bank = int(safe_number(user.bank)) + interest
        user.last_bank_interest = time.time()
        db.session.commit()
        return redirect(url_for("bank", msg=f"Rente ontvangen: ${interest}."))

    if amount <= 0:
        return redirect(url_for("bank", msg="Invalid amount."))

    if action == "deposit":
        if user.money < amount:
            return redirect(url_for("bank", msg="Niet genoeg cash in kas."))
        user.money -= amount
        user.bank += amount
        msg = f"${amount} op de bank gezet."
    elif action == "withdraw":
        if user.bank < amount:
            return redirect(url_for("bank", msg="Niet genoeg geld op de bank."))
        user.bank -= amount
        user.money += amount
        msg = f"${amount} opgenomen uit de bank."
    elif action == "borrow":
        available = bank_available_credit(user)
        if amount > available:
            return redirect(url_for("bank", msg=f"Je kunt maximaal nog ${available} lenen met je huidige rang."))
        interest_fee = int(amount * bank_loan_interest_rate(user))
        total_debt = amount + interest_fee
        user.money = int(safe_number(user.money)) + amount
        user.bank_loan = int(safe_number(getattr(user, "bank_loan", 0))) + total_debt
        msg = f"Lening goedgekeurd: ${amount}. Rente toegevoegd aan schuld: ${interest_fee}."
    elif action == "repay":
        current_debt = int(safe_number(getattr(user, "bank_loan", 0)))
        if current_debt <= 0:
            return redirect(url_for("bank", msg="Je hebt geen openstaande lening."))
        pay_amount = min(amount, current_debt)
        if user.money < pay_amount:
            return redirect(url_for("bank", msg="Niet genoeg cash om af te lossen."))
        user.money -= pay_amount
        user.bank_loan = max(0, current_debt - pay_amount)
        msg = f"${pay_amount} afgelost. Resterende schuld: ${user.bank_loan}."
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
        market_board=market_price_board(),
        msg=request.args.get("msg"),
    )


@app.route("/cargo")
def cargo():
    user, error = login_required()
    if error:
        return error
    return render_page(
        user,
        "cargo",
        contraband=warehouse_overview(user),
        cities=CITIES,
        shipment_speeds=shipment_speed_options(),
        shipments=shipment_overview(user),
        cargo_stats=cargo_center_stats(user),
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
    price = int(dynamic_market_price(user.location, item_key))
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

    target_endpoint = shipment_redirect_target()
    action = request.form.get("action")

    if action == "send":
        item_key = request.form.get("item_key", "gin")
        item_data = CONTRABAND.get(item_key)
        destination = request.form.get("destination")
        amount = safe_int(request.form.get("amount"))
        if not item_data or destination not in MARKET_PRICES or destination == user.location:
            return redirect(url_for(target_endpoint, msg="Invalid shipment route."))
        if amount <= 0:
            return redirect(url_for(target_endpoint, msg="Invalid shipment amount."))

        row = warehouse_item(user, item_key)
        owned = int(safe_number(row.quantity))
        if amount > owned:
            return redirect(url_for(target_endpoint, msg="You do not own that much stock to send."))

        speed = request.form.get("speed", "economy")
        if speed not in SHIPMENT_SPEEDS:
            speed = "economy"
        cost = shipment_cost(destination, amount, speed)
        if safe_number(user.money) < cost:
            return redirect(url_for(target_endpoint, msg=f"Not enough cash. {shipment_speed_label(speed)} costs ${cost}."))

        risk = shipment_customs_risk(user, destination, item_key)
        row.quantity = owned - amount
        user.money = int(safe_number(user.money)) - cost

        if random.randint(1, 100) <= risk:
            fine = reduce_loss_by_protection(user, int(cost * 2))
            user.money = max(0, int(safe_number(user.money)) - fine)
            shipment = Shipment(user_id=user.id, item_key=item_key, quantity=amount, origin=user.location, destination=destination, arrives_at=time.time(), status="seized")
            db.session.add(shipment)
            create_message(user.id, "cargo", "Cargo Seized", f"Customs seized your shipment of {amount} {item_data['label']} from {user.location} to {destination}. You paid ${cost} transport and ${fine} fine.", commit=False)
            db.session.commit()
            return redirect(url_for(target_endpoint, msg=f"🚔 Customs seized your shipment of {amount} {item_data['label']}. You paid ${cost} transport and ${fine} fine."))

        seconds = shipment_seconds_for_speed(speed)
        shipment = Shipment(user_id=user.id, item_key=item_key, quantity=amount, origin=user.location, destination=destination, arrives_at=time.time() + seconds, status="in_transit")
        db.session.add(shipment)
        create_message(user.id, "cargo", "Cargo Sent", f"You sent {amount} {item_data['label']} from {user.location} to {destination} with {shipment_speed_label(speed)}. ETA: {format_duration(seconds)}. Cost: ${cost}.", commit=False)
        db.session.commit()
        route_type = "international" if is_international_city(destination) else "domestic"
        return redirect(url_for(target_endpoint, msg=f"📦 Sent {amount} {item_data['label']} to {destination} with {shipment_speed_label(speed)}. {route_type.title()} shipment arrives in {format_duration(seconds)}. Cost: ${cost}."))

    if action == "collect":
        shipment_id = safe_int(request.form.get("shipment_id"))
        shipment = Shipment.query.filter_by(id=shipment_id, user_id=user.id).first()
        if not shipment:
            return redirect(url_for(target_endpoint, msg="Shipment not found."))
        process_arrived_shipments(user)
        if shipment.status != "arrived":
            return redirect(url_for(target_endpoint, msg="Shipment has not arrived yet."))
        if shipment.destination != user.location:
            return redirect(url_for(target_endpoint, msg=f"Travel to {shipment.destination} to collect this shipment."))
        amount = int(safe_number(shipment.quantity))
        if warehouse_free_space(user) < amount:
            return redirect(url_for(target_endpoint, msg="Not enough warehouse space to collect this shipment."))
        row = warehouse_item(user, shipment.item_key)
        row.quantity = int(safe_number(row.quantity)) + amount
        label = CONTRABAND.get(shipment.item_key, {"label": shipment.item_key})["label"]
        db.session.delete(shipment)
        create_message(user.id, "cargo", "Cargo Collected", f"You collected {amount} {label} in {user.location}.", commit=False)
        db.session.commit()
        return redirect(url_for(target_endpoint, msg=f"✅ Collected {amount} {label} from the shipment."))

    return redirect(url_for(target_endpoint, msg="Invalid shipment action."))


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



@app.route("/traveling")
def traveling():
    user, error = login_required()
    if error:
        return error
    complete_timed_travel(user)
    db.session.commit()
    return render_page(
        user,
        "traveling",
        cities=CITIES,
        travel_options=travel_option_rows(user),
        msg=request.args.get("msg"),
    )


@app.route("/travel_start", methods=["POST"])
def travel_start():
    user, error = login_required()
    if error:
        return error
    if is_user_traveling(user):
        return redirect(url_for("traveling", msg="You are already travelling."))
    destination = request.form.get("destination")
    mode_key = request.form.get("mode", "walk")
    if destination not in CITIES:
        return redirect(url_for("traveling", msg="Invalid destination."))
    if destination == user.location:
        return redirect(url_for("traveling", msg="You are already in that city."))
    option = travel_option_by_key(user, destination, mode_key)
    if not option:
        return redirect(url_for("traveling", msg="Invalid or unavailable transport option."))
    cost = int(option["cost"])
    if safe_number(user.money) < cost:
        return redirect(url_for("traveling", msg=f"Not enough cash. {option['label']} costs ${cost}."))
    user.money = int(safe_number(user.money)) - cost
    user.travel_destination = destination
    user.travel_arrives_at = time.time() + int(option["seconds"])
    user.travel_mode = option["label"]
    user.travel_origin = user.location
    user.travel_vehicle_key = mode_key.split(":", 1)[1] if mode_key.startswith("vehicle:") else None
    db.session.commit()
    return redirect(url_for("traveling", msg=f"Journey started to {destination} with {option['label']}. Arrival in {format_duration(option['seconds'])}."))


@app.route("/travel_action", methods=["POST"])
def travel_action():
    user, error = login_required()
    if error:
        return error
    if is_user_traveling(user):
        return redirect(url_for("market", msg="You are already travelling."))

    destination = request.form.get("destination")
    mode_key = request.form.get("mode", "public")
    if destination not in CITIES:
        return redirect(url_for("market", msg="Invalid destination."))
    if destination == user.location:
        return redirect(url_for("market", msg="You are already there."))

    option = travel_option_by_key(user, destination, mode_key)
    if not option:
        return redirect(url_for("market", msg="Invalid or unavailable transport option."))

    item_key = request.form.get("item_key", "").strip()
    smuggle_amount = max(0, safe_int(request.form.get("smuggle_amount")))
    carried_item = None
    carried_label = "cargo"

    if smuggle_amount > 0:
        if item_key not in CONTRABAND:
            return redirect(url_for("market", msg="Choose valid cargo to smuggle, or set amount to 0 for clean travel."))
        carried_item = warehouse_item(user, item_key)
        carried_label = CONTRABAND[item_key]["label"]
        if int(safe_number(carried_item.quantity)) < smuggle_amount:
            return redirect(url_for("market", msg=f"You do not have enough {carried_label} in your warehouse to carry {smuggle_amount}."))

    cost = int(option["cost"])
    if safe_number(user.money) < cost:
        return redirect(url_for("market", msg=f"Not enough cash for {option['label']}. Cost: ${cost}."))

    # Pay travel cost before the trip attempt.
    user.money = int(safe_number(user.money)) - cost

    if smuggle_amount > 0 and carried_item:
        item_risk = int(CONTRABAND[item_key].get("risk", 0))
        route_risk = 10 if is_international_city(destination) else 3
        # Faster/more private transport is safer than public routes, but never risk-free.
        transport_safety = 0
        if mode_key == "walk":
            transport_safety = -2
        elif mode_key == "public":
            transport_safety = 0
        elif mode_key == "flight":
            transport_safety = 2
        elif mode_key.startswith("vehicle:"):
            vehicle_key = mode_key.split(":", 1)[1]
            vehicle = VEHICLE_BY_KEY.get(vehicle_key, {})
            transport_safety = min(7, int(vehicle.get("bonus", 0)) // 8)
        risk = max(1, route_risk + item_risk - influence_arrest_reduction(user) - transport_safety)
        if random.randint(1, 100) <= risk:
            carried_item.quantity = max(0, int(safe_number(carried_item.quantity)) - smuggle_amount)
            local_price = int(dynamic_market_price(user.location, item_key))
            fine = reduce_loss_by_protection(user, max(100, int(smuggle_amount * max(local_price, 1) * 0.35)))
            user.money = max(0, int(safe_number(user.money)) - fine)
            jail_time = int((90 if is_international_city(destination) else 45) * influence_jail_multiplier(user))
            user.jail_until = time.time() + jail_time
            user.bribe_available_at = time.time() + int(jail_time * BRIBE_WAIT_RATIO)
            user.arrests = int(safe_number(user.arrests)) + 1
            db.session.commit()
            return redirect(url_for("jail", msg=f"🚔 Customs caught you before departure carrying {smuggle_amount}x {carried_label}. That cargo was confiscated. Travel cost: ${cost}. Fine: ${fine}. Jail time: {jail_time} seconds."))

        # Cargo is carried during timed travel. It is returned to the warehouse when the player arrives.
        carried_item.quantity = max(0, int(safe_number(carried_item.quantity)) - smuggle_amount)
        user.travel_smuggle_item_key = item_key
        user.travel_smuggle_quantity = smuggle_amount
    else:
        user.travel_smuggle_item_key = None
        user.travel_smuggle_quantity = 0

    user.travel_destination = destination
    user.travel_arrives_at = time.time() + int(option["seconds"])
    user.travel_mode = option["label"]
    user.travel_origin = user.location
    user.travel_vehicle_key = mode_key.split(":", 1)[1] if mode_key.startswith("vehicle:") else None
    db.session.commit()

    if smuggle_amount > 0:
        return redirect(url_for("market", msg=f"Self-smuggling trip started to {destination} with {option['label']}. Carrying {smuggle_amount}x {carried_label}. Arrival in {format_duration(option['seconds'])}."))
    return redirect(url_for("market", msg=f"Clean travel started to {destination} with {option['label']}. Arrival in {format_duration(option['seconds'])}."))

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


@app.route("/local_gin_buyer_action", methods=["POST"])
def local_gin_buyer_action():
    user, error = login_required()
    if error:
        return error
    business = business_for_current_city(user)
    update_business_production(business)
    ready = int(safe_number(getattr(business, "pending_gin", 0)))
    amount = safe_int(request.form.get("amount"))
    if int(safe_number(business.distilleries)) <= 0:
        return redirect(url_for("assets", msg=f"You do not own any distilleries in {user.location}."))
    if ready <= 0:
        db.session.commit()
        return redirect(url_for("assets", msg=f"No gin ready to sell in {user.location} yet."))
    if amount <= 0:
        return redirect(url_for("assets", msg="Enter a valid gin amount to sell."))
    if amount > ready:
        return redirect(url_for("assets", msg=f"Only {ready} gin is ready in {user.location}."))
    price_each = local_buyer_gin_price(user)
    total = amount * price_each
    business.pending_gin = ready - amount
    user.money = int(safe_number(user.money)) + total
    db.session.commit()
    return redirect(url_for("assets", msg=f"You sold {amount} local gin to a buyer in {user.location} for ${total} (${price_each} each, 30% below smuggling price)."))


@app.route("/garage")
def garage():
    user, error = login_required()
    if error:
        return error
    return render_page(
        user,
        "garage",
        vehicles=OLDTIMER_VEHICLES,
        vehicle_categories=vehicle_categories_for_showroom(OLDTIMER_VEHICLES),
        garages=garage_overview(user),
        vehicle_sell_price=vehicle_sell_price,
        exclusive_profit_vehicles=EXCLUSIVE_PROFIT_VEHICLES,
        msg=request.args.get("msg"),
    )


@app.route("/garage_action", methods=["POST"])
def garage_action():
    user, error = login_required()
    if error:
        return error

    action = request.form.get("action", "buy")
    vehicle_key = request.form.get("vehicle_key")
    vehicle = VEHICLE_BY_KEY.get(vehicle_key)
    if not vehicle:
        return redirect(url_for("garage", msg="Invalid vehicle."))

    ensure_city_vehicles(user)
    row = CityVehicle.query.filter_by(user_id=user.id, city=user.location, vehicle_key=vehicle_key).first()
    if not row:
        row = CityVehicle(user_id=user.id, city=user.location, vehicle_key=vehicle_key, quantity=0)
        db.session.add(row)

    if action == "sell":
        if int(safe_number(row.quantity)) <= 0:
            return redirect(url_for("garage", msg=f"You do not own a {vehicle['name']} in {user.location}."))

        sell_price = vehicle_sell_price(vehicle)
        row.quantity = int(safe_number(row.quantity)) - 1
        user.cars = max(0, int(safe_number(user.cars)) - 1)
        user.money = int(safe_number(user.money)) + sell_price
        db.session.commit()

        if vehicle_key in EXCLUSIVE_PROFIT_VEHICLES:
            return redirect(url_for("garage", msg=f"Exclusive sale: you sold a {vehicle['year']} {vehicle['name']} for ${sell_price} and made a profit."))
        return redirect(url_for("garage", msg=f"You sold a {vehicle['year']} {vehicle['name']} for ${sell_price}. Normal vehicles sell below purchase value."))

    price = int(vehicle["price"])
    if safe_number(user.money) < price:
        return redirect(url_for("garage", msg="Not enough cash."))

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
    elif action == "buy_weapon":
        weapon_key = request.form.get("weapon_key", "")
        weapon = WEAPON_TYPES.get(weapon_key)
        if not weapon:
            return redirect(url_for("bullets", msg="Invalid weapon."))
        price = int(weapon["price"])
        if safe_number(user.money) < price:
            return redirect(url_for("bullets", msg="Not enough cash."))
        user.money = int(safe_number(user.money)) - price
        add_weapon(user, weapon_key, 1)
        msg = f"You bought a {weapon['name']}."
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
        return redirect(url_for("heists", msg=f"✅ OPERATION SUCCESSFUL: {plan['name']} earned ${cash} and {plan['exp']} EXP."))

    fine = reduce_loss_by_protection(user, max(250, plan["cash_min"] // 3))
    user.money = max(0, int(safe_number(user.money)) - fine)
    user.arrests = int(safe_number(user.arrests)) + 1
    user.jail_until = time.time() + int(plan["jail"])
    user.bribe_available_at = time.time() + int(plan["jail"] * BRIBE_WAIT_RATIO)
    db.session.commit()
    return redirect(url_for("jail", msg=f"❌ OPERATION FAILED: You lost ${fine} and were jailed for {plan['jail']} seconds."))


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
        territory_protection_time=TERRITORY_PROTECTION_TIME,
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



@app.route("/friends")
def friends():
    user, error = login_required()
    if error:
        return error

    friend_query = request.args.get("q", "").strip()
    return render_page(
        user,
        "friends",
        incoming_requests=incoming_friend_requests(user),
        friend_links=my_friend_links(user),
        friend_query=friend_query,
        friend_search_results=friend_search_results(user, friend_query),
        msg=request.args.get("msg"),
    )


@app.route("/friend_action", methods=["POST"])
def friend_action():
    user, error = login_required()
    if error:
        return error

    target_id = safe_int(request.form.get("target_id"))
    action = request.form.get("action")
    target = User.query.get(target_id)

    if not target or target.is_dead:
        return redirect(url_for("friends", msg=tr("recipient_not_found")))

    if target.id == user.id:
        return redirect(url_for("friends", msg="You cannot add yourself."))

    link = friendship_between(user.id, target.id)

    if action == "add":
        if link:
            return redirect(url_for("ranking", q=target.username, msg=tr("friend_request_exists")))
        link = Friend(user_id=user.id, friend_id=target.id, accepted=False, created_at=time.time())
        db.session.add(link)
        create_message(target.id, "player", "Friend Request", f"{user.username} sent you a friend request.", commit=False, sender_id=user.id)
        db.session.commit()
        return redirect(url_for("ranking", q=target.username, msg=tr("friend_added")))

    if action == "accept":
        if link and link.friend_id == user.id and not link.accepted:
            link.accepted = True
            create_message(link.user_id, "player", "Friend Request Accepted", f"{user.username} accepted your friend request.", commit=False, sender_id=user.id)
            db.session.commit()
            return redirect(url_for("friends", msg=tr("friend_accepted")))
        return redirect(url_for("friends", msg=tr("friend_request_exists")))

    if action == "decline":
        if link and link.friend_id == user.id and not link.accepted:
            db.session.delete(link)
            db.session.commit()
            return redirect(url_for("friends", msg=tr("friend_declined")))
        return redirect(url_for("friends", msg=tr("friend_request_exists")))

    if action == "remove":
        if link and link.accepted:
            db.session.delete(link)
            db.session.commit()
            return redirect(url_for("friends", msg=tr("friend_removed")))
        return redirect(url_for("friends", msg=tr("friend_request_exists")))

    return redirect(url_for("friends", msg="Invalid friend action."))


@app.route("/ranking")
def ranking():
    user, error = login_required()
    if error:
        return error

    all_users = User.query.all()
    for u in all_users:
        u.update_rank()
    db.session.commit()

    ranked_users = sorted(all_users, key=lambda u: (power_score(u), int(safe_number(u.money)) + int(safe_number(u.bank))), reverse=True)
    users = ranked_users[:100]

    search_query = request.args.get("q", "").strip()
    searched_player = None
    searched_rank = None

    if search_query:
        for index, ranked_user in enumerate(ranked_users, start=1):
            if ranked_user.username.lower() == search_query.lower():
                searched_player = ranked_user
                searched_rank = index
                break

        if not searched_player:
            for index, ranked_user in enumerate(ranked_users, start=1):
                if search_query.lower() in ranked_user.username.lower():
                    searched_player = ranked_user
                    searched_rank = index
                    break

    current_player_rank = None
    for index, ranked_user in enumerate(ranked_users, start=1):
        if ranked_user.id == user.id:
            current_player_rank = index
            break

    return render_page(
        user,
        "ranking",
        users=users,
        search_query=search_query,
        searched_player=searched_player,
        searched_rank=searched_rank,
        current_player_rank=current_player_rank,
        current_rank_info=next_rank_info(user),
        current_rank_percent=rank_progress_percent(user),
        total_ranked_players=len(ranked_users),
        msg=request.args.get("msg"),
    )


with app.app_context():
    os.makedirs(app.instance_path, exist_ok=True)
    db.create_all()
    migrate_database()
    ensure_city_casinos()
    ensure_city_territories()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
