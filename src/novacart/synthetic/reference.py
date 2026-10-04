"""Domain reference data for the NovaCart synthetic dataset.

The numbers here are deliberately calibrated to look like a mid-sized European
specialist retailer: the mix is fashion/home/electronics heavy, the customer base
is mostly German-speaking with a wider EU tail, and demand concentrates around
Black Friday and Christmas. See docs/data_generation.md for the full rationale.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Country:
    code: str
    name: str
    weight: float
    vat_rate: float
    cities: tuple[str, ...]


@dataclass(frozen=True)
class ChannelProfile:
    name: str
    weight: float
    retention_bias: float
    """Multiplier on latent customer loyalty: referral buyers are the most valuable."""


@dataclass(frozen=True)
class Category:
    name: str
    weight: float
    price_median: float
    price_sigma: float
    gross_margin: float
    subcategories: tuple[str, ...]
    product_nouns: tuple[str, ...]
    month_factors: Mapping[int, float] = field(default_factory=dict)
    popularity_decay: float = 1.1
    """Exponent applied to the product popularity distribution inside the category."""


COUNTRIES: dict[str, Country] = {
    "DE": Country("DE", "Germany", 0.30, 0.19, ("Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt", "Stuttgart")),
    "AT": Country("AT", "Austria", 0.06, 0.20, ("Vienna", "Graz", "Linz", "Salzburg")),
    "NL": Country("NL", "Netherlands", 0.08, 0.21, ("Amsterdam", "Rotterdam", "Utrecht", "Eindhoven")),
    "FR": Country("FR", "France", 0.10, 0.20, ("Paris", "Lyon", "Marseille", "Toulouse", "Lille")),
    "IT": Country("IT", "Italy", 0.07, 0.22, ("Milan", "Rome", "Turin", "Bologna")),
    "ES": Country("ES", "Spain", 0.07, 0.21, ("Madrid", "Barcelona", "Valencia", "Seville")),
    "BE": Country("BE", "Belgium", 0.05, 0.21, ("Brussels", "Antwerp", "Ghent", "Leuven")),
    "PL": Country("PL", "Poland", 0.05, 0.23, ("Warsaw", "Krakow", "Wroclaw", "Gdansk")),
    "IE": Country("IE", "Ireland", 0.04, 0.23, ("Dublin", "Cork", "Galway")),
    "PT": Country("PT", "Portugal", 0.04, 0.23, ("Lisbon", "Porto", "Braga")),
    "FI": Country("FI", "Finland", 0.03, 0.24, ("Helsinki", "Espoo", "Tampere")),
    "SE": Country("SE", "Sweden", 0.03, 0.25, ("Stockholm", "Gothenburg", "Malmo")),
    "DK": Country("DK", "Denmark", 0.03, 0.25, ("Copenhagen", "Aarhus", "Odense")),
    "CZ": Country("CZ", "Czechia", 0.03, 0.21, ("Prague", "Brno", "Ostrava")),
    "SI": Country("SI", "Slovenia", 0.02, 0.22, ("Ljubljana", "Maribor", "Celje")),
}

ACQUISITION_CHANNELS: dict[str, ChannelProfile] = {
    "organic_search": ChannelProfile("organic_search", 0.22, 1.15),
    "paid_search": ChannelProfile("paid_search", 0.18, 0.95),
    "paid_social": ChannelProfile("paid_social", 0.17, 0.90),
    "email": ChannelProfile("email", 0.12, 1.20),
    "referral": ChannelProfile("referral", 0.11, 1.35),
    "direct": ChannelProfile("direct", 0.12, 1.05),
    "affiliate": ChannelProfile("affiliate", 0.05, 0.85),
    "display": ChannelProfile("display", 0.03, 0.80),
}

CATEGORIES: dict[str, Category] = {
    "Electronics": Category(
        name="Electronics",
        weight=0.13,
        price_median=139.00,
        price_sigma=0.50,
        gross_margin=0.28,
        subcategories=("Audio", "Wearables", "Computing Accessories", "Smart Home"),
        product_nouns=(
            "Wireless Earbuds", "Bluetooth Speaker", "Smart Watch", "Fitness Tracker",
            "Power Bank", "USB-C Hub", "Mechanical Keyboard", "Webcam",
            "Noise-Cancelling Headphones", "Tablet Stand",
        ),
        month_factors={11: 1.75, 12: 1.45, 1: 0.85},
        popularity_decay=1.05,
    ),
    "Home & Kitchen": Category(
        name="Home & Kitchen",
        weight=0.17,
        price_median=55.00,
        price_sigma=0.55,
        gross_margin=0.42,
        subcategories=("Cookware", "Small Appliances", "Storage", "Home Comfort"),
        product_nouns=(
            "Espresso Machine", "Air Fryer", "Cast Iron Skillet", "Blender",
            "Vacuum Flask", "Knife Set", "Food Storage Set", "Robot Vacuum",
            "Toaster", "Dinnerware Set",
        ),
        month_factors={11: 1.35, 12: 1.30, 1: 0.90},
        popularity_decay=1.15,
    ),
    "Sports & Outdoors": Category(
        name="Sports & Outdoors",
        weight=0.13,
        price_median=55.00,
        price_sigma=0.50,
        gross_margin=0.45,
        subcategories=("Fitness", "Outdoor", "Cycling", "Water Sports"),
        product_nouns=(
            "Yoga Mat", "Running Shoes", "Resistance Bands", "Cycling Helmet",
            "Insulated Bottle", "Dumbbell Set", "Trekking Poles", "Swim Goggles",
            "Tennis Racket", "Foam Roller",
        ),
        month_factors={1: 1.35, 5: 1.20, 6: 1.30, 7: 1.25, 11: 0.95, 12: 0.90},
        popularity_decay=1.10,
    ),
    "Beauty & Personal Care": Category(
        name="Beauty & Personal Care",
        weight=0.15,
        price_median=22.00,
        price_sigma=0.45,
        gross_margin=0.62,
        subcategories=("Skincare", "Haircare", "Fragrance", "Personal Devices"),
        product_nouns=(
            "Vitamin C Serum", "Moisturiser", "Hair Dryer", "Makeup Brush Set",
            "Sunscreen SPF50", "Face Mask Set", "Body Lotion", "Perfume",
            "Lip Balm Set", "Electric Toothbrush",
        ),
        month_factors={2: 1.10, 6: 1.15, 11: 1.30, 12: 1.35},
        popularity_decay=1.20,
    ),
    "Fashion": Category(
        name="Fashion",
        weight=0.19,
        price_median=42.00,
        price_sigma=0.45,
        gross_margin=0.58,
        subcategories=("Menswear", "Womenswear", "Footwear", "Accessories"),
        product_nouns=(
            "Cotton T-Shirt", "Denim Jacket", "Sneakers", "Wool Scarf",
            "Leather Belt", "Running Socks", "Rain Jacket", "Chino Trousers",
            "Knit Sweater", "Canvas Backpack",
        ),
        month_factors={3: 1.15, 4: 1.20, 9: 1.15, 11: 1.40, 12: 1.25},
        popularity_decay=1.25,
    ),
    "Toys & Games": Category(
        name="Toys & Games",
        weight=0.10,
        price_median=28.00,
        price_sigma=0.42,
        gross_margin=0.47,
        subcategories=("Building Sets", "Board Games", "Outdoor Play", "STEM"),
        product_nouns=(
            "Building Blocks Set", "Board Game", "Puzzle 1000 Pieces", "RC Car",
            "Plush Toy", "Craft Kit", "Action Figure", "Card Game",
            "Science Kit", "Doll House",
        ),
        month_factors={6: 0.90, 7: 0.90, 10: 1.15, 11: 1.90, 12: 2.00},
        popularity_decay=1.05,
    ),
    "Books & Media": Category(
        name="Books & Media",
        weight=0.06,
        price_median=16.00,
        price_sigma=0.35,
        gross_margin=0.38,
        subcategories=("Fiction", "Non-Fiction", "Children", "Games & Puzzles"),
        product_nouns=(
            "Paperback Novel", "Cookbook", "Business Paperback", "Children's Picture Book",
            "Language Course", "Colouring Book", "Travel Guide", "Biography",
            "Notebook Set", "Puzzle Book",
        ),
        month_factors={1: 1.15, 9: 1.30, 12: 1.40},
        popularity_decay=1.30,
    ),
    "Grocery": Category(
        name="Grocery",
        weight=0.07,
        price_median=12.00,
        price_sigma=0.35,
        gross_margin=0.30,
        subcategories=("Coffee & Tea", "Snacks", "Pantry", "Drinks"),
        product_nouns=(
            "Ground Coffee", "Olive Oil", "Dark Chocolate", "Protein Bars",
            "Herbal Tea", "Pasta", "Honey", "Nut Mix",
            "Sparkling Water", "Breakfast Cereals",
        ),
        month_factors={1: 0.95, 11: 1.20, 12: 1.30},
        popularity_decay=1.45,
    ),
}

BRANDS: tuple[str, ...] = (
    "Aurelia", "Northwind Supply", "Kestrel", "Lumen & Co", "Verdant", "Brickford",
    "Solstice", "Marlow", "Pinewood", "Cassia", "Orbit Lab", "Hearthstone Goods",
    "Verity", "Blue Fjord", "Alder & Ash", "Tessera", "Nomad Kits", "Silverleaf",
    "Corvus", "Mirin", "Palladium", "Wildacre", "Fable & Fern", "Nordkap",
)

FIRST_NAMES: tuple[str, ...] = (
    "Anna", "Lukas", "Sophie", "Jonas", "Marie", "Felix", "Laura", "Maximilian",
    "Julia", "David", "Emma", "Leon", "Hannah", "Paul", "Lena", "Elias",
    "Clara", "Niklas", "Nina", "Tobias", "Lea", "Moritz", "Sarah", "Julian",
    "Franziska", "Simon", "Katrin", "Philipp", "Miriam", "Andreas", "Elena", "Martin",
    "Iris", "Stefan", "Amelie", "Rafael", "Greta", "Oliver", "Mia", "Bastian",
    "Nora", "Fabian", "Vera", "Matthias", "Ida", "Sebastian", "Yara", "Thomas",
    "Klara", "Michael", "Rosa", "Daniel", "Sofia", "Jakob", "Chiara", "Christian",
    "Alice", "Patrick", "Marlene", "Vincent",
)

LAST_NAMES: tuple[str, ...] = (
    "Mueller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker",
    "Schulz", "Hoffmann", "Koch", "Bauer", "Richter", "Klein", "Wolf", "Schroeder",
    "Neumann", "Schwarz", "Zimmermann", "Braun", "Krueger", "Hofmann", "Hartmann", "Lange",
    "Schmitt", "Werner", "Schmitz", "Krause", "Meier", "Lehmann", "Schmid", "Schulze",
    "Koehler", "Herrmann", "Koenig", "Walter", "Mayer", "Huber", "Kaiser", "Fuchs",
    "Peters", "Lang", "Scholz", "Moeller", "Weiss", "Jung", "Hahn", "Vogel",
    "Friedrich", "Keller", "Guenther", "Frank", "Berger", "Winkler", "Roth", "Beck",
    "Lorenz", "Baumann", "Franke", "Albrecht",
)

PAYMENT_METHODS: Mapping[str, float] = {
    "card": 0.42,
    "paypal": 0.22,
    "wallet": 0.12,
    "klarna": 0.10,
    "sepa_debit": 0.07,
    "gift_card": 0.04,
    "bank_transfer": 0.03,
}

SALES_CHANNELS: Mapping[str, float] = {
    "web": 0.52,
    "mobile_app": 0.36,
    "marketplace": 0.09,
    "phone": 0.03,
}

ORDER_STATUS_WEIGHTS: Mapping[str, float] = {
    "completed": 0.935,
    "refunded": 0.042,
    "cancelled": 0.023,
}

PAYMENT_STATUS_BY_ORDER_STATUS: Mapping[str, str] = {
    "completed": "captured",
    "refunded": "refunded",
    "cancelled": "voided",
}

CAMPAIGN_CHANNELS: Mapping[str, float] = {
    "email": 0.30,
    "paid_social": 0.22,
    "paid_search": 0.18,
    "display": 0.12,
    "influencer": 0.10,
    "affiliate": 0.08,
}

CAMPAIGN_OBJECTIVES: Mapping[str, float] = {
    "acquisition": 0.30,
    "retention": 0.25,
    "reactivation": 0.20,
    "cross_sell": 0.15,
    "brand": 0.10,
}

CAMPAIGN_AUDIENCES: tuple[str, ...] = (
    "new_customers",
    "high_propensity",
    "loyal_customers",
    "lapsed_customers",
    "broad_reach",
)

CAMPAIGN_NAME_PATTERNS: tuple[str, ...] = (
    "Spring Refresh", "Summer Kickoff", "Back to School", "Autumn Essentials",
    "Black Friday Countdown", "Holiday Gift Guide", "New Year Reset",
    "Loyalty Appreciation", "Win-Back Wave", "Category Spotlight",
)

MONTH_DEMAND_FACTORS: Mapping[int, float] = {
    1: 0.86, 2: 0.89, 3: 0.94, 4: 0.96, 5: 1.00, 6: 1.01,
    7: 0.93, 8: 1.02, 9: 1.05, 10: 1.12, 11: 1.42, 12: 1.30,
}

# Monday .. Sunday
WEEKDAY_FACTORS: tuple[float, ...] = (0.97, 1.00, 1.02, 1.04, 1.06, 0.98, 0.93)

HOUR_OF_DAY_WEIGHTS: tuple[float, ...] = (
    0.20, 0.10, 0.08, 0.06, 0.06, 0.08, 0.15, 0.30, 0.55, 0.80, 1.00, 1.05,
    1.00, 0.95, 0.90, 0.90, 0.95, 1.05, 1.20, 1.30, 1.25, 1.05, 0.70, 0.40,
)

DAY_LEVEL_NOISE_SIGMA = 0.07
DAY_LEVEL_NOISE_AR = 0.55


def _assert_weights_close_to_one(weights: Mapping[str, float], label: str) -> None:
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise AssertionError(f"{label} weights sum to {total!r}, expected 1.0")


def validate_reference_data() -> None:
    """Guard against typos in the probability tables above."""
    _assert_weights_close_to_one({c: p.weight for c, p in COUNTRIES.items()}, "countries")
    _assert_weights_close_to_one({c: p.weight for c, p in ACQUISITION_CHANNELS.items()}, "channels")
    _assert_weights_close_to_one({c: p.weight for c, p in CATEGORIES.items()}, "categories")
    _assert_weights_close_to_one(PAYMENT_METHODS, "payment methods")
    _assert_weights_close_to_one(SALES_CHANNELS, "sales channels")
    _assert_weights_close_to_one(ORDER_STATUS_WEIGHTS, "order statuses")
    _assert_weights_close_to_one(CAMPAIGN_CHANNELS, "campaign channels")
    _assert_weights_close_to_one(CAMPAIGN_OBJECTIVES, "campaign objectives")
    if set(MONTH_DEMAND_FACTORS) != set(range(1, 13)):
        raise AssertionError("MONTH_DEMAND_FACTORS must define all twelve months")
    if any(value <= 0 for value in MONTH_DEMAND_FACTORS.values()):
        raise AssertionError("MONTH_DEMAND_FACTORS must be positive")
    if len(WEEKDAY_FACTORS) != 7:
        raise AssertionError("WEEKDAY_FACTORS must contain seven values")
    if len(HOUR_OF_DAY_WEIGHTS) != 24:
        raise AssertionError("HOUR_OF_DAY_WEIGHTS must contain 24 values")

    for category in CATEGORIES.values():
        if len(category.product_nouns) == 0:
            raise AssertionError(f"category {category.name} has no product nouns")
        for month in category.month_factors:
            if month not in range(1, 13):
                raise AssertionError(f"category {category.name} has an invalid month factor: {month}")
        if not 0.0 < category.gross_margin < 1.0:
            raise AssertionError(f"category {category.name} has an invalid gross margin")

    if len(set(LAST_NAMES)) != len(LAST_NAMES) or len(set(FIRST_NAMES)) != len(FIRST_NAMES):
        raise AssertionError("name pools must not contain duplicates")

