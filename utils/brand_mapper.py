"""
Brand Mapper for SOS
Extracts brand names from product class names for brand-level aggregation
"""

from typing import Optional

# Brand extraction patterns (prefix-based matching)
# Ordered by specificity (longer prefixes first to avoid mismatches)
BRAND_PATTERNS = {
    # === UBL BRANDS ===
    # Skin Care
    'gl_': 'Glow & Lovely',
    'gh_': 'Glow & Handsome',
    'ponds_': "Pond's",
    'vaseline_': 'Vaseline',
    'dove_nr_lotion': 'Dove',  # Specific skin care product

    # Hair Care
    'clinic_plus_': 'Clinic Plus',
    'sunsilk_': 'Sunsilk',
    'clear_': 'Clear',
    'tresemme_': 'Tresemme',
    'treseme_': 'Tresemme',  # Alternative spelling
    'dove_': 'Dove',  # General Dove pattern (after specific dove_nr_lotion)

    # Nutrition
    'horlicks_': 'Horlicks',
    'maltova_': 'Maltova',
    'boost_': 'Boost',
    'glucomax_': 'Glucomax',

    # Oral Care
    'pepsodent_': 'Pepsodent',
    'closeup_': 'Closeup',

    # Skin Cleansing
    'lux_': 'Lux',
    'lifebuoy_': 'Lifebuoy',

    # Home & Hygiene
    'vim_': 'Vim',
    'domex_': 'Domex',

    # Fabric
    'surf_': 'Surf Excel',
    'wheel_': 'Wheel',
    'rin_': 'Rin',

    # Mini Meals
    'knorr_': 'Knorr',

    # === COMPETITOR BRANDS ===
    # Hair Care Competitors
    'head_shoulders_': 'Head & Shoulders',
    'pantene_': 'Pantene',
    'select_plus_': 'Select Plus',
    'parachute_': 'Parachute',
    'himalaya_': 'Himalaya',
    'garnier_': 'Garnier',
    'revive_': 'Revive',
    'livon_': 'Livon',
    'sesa_': 'Sesa',
    'streax_': 'Streax',
    'lily_': 'Lily',
    'meril_': 'Meril',

    # Oral Care Competitors
    'colgate_': 'Colgate',
    'sensodyne_': 'Sensodyne',
    'dabur_': 'Dabur',
    'mediplus_': 'Mediplus',
    'whiteplus_': 'Whiteplus',
    'brushup_': 'Brushup',
    'am_pm_': 'AM PM',
    'cute_': 'Cute',
    'magic_': 'Magic',

    # Skin Care Competitors
    'dr_rasel_': 'Dr Rasel',
    'osufi_': 'Osufi',
    'boro_plus_': 'Boro Plus',
    'fh_': 'Fair & Handsome',
    'lakme_': 'Lakme',
    'lotus_': 'Lotus',
    'simple_': 'Simple',
    'secret_': 'Secret',
    'nivea_': 'Nivea',
    'fiera_': 'Fiera',
    'lata_': 'Lata',

    # Skin Cleansing Competitors
    'acne_aid_': 'Acne Aid',
    'acnes_': 'Acnes',
    'jasmine_': 'Jasmine',
    'pears_': 'Pears',
    'savlon_': 'Savlon',
    'septex_': 'Septex',
    'bactrol_': 'Bactrol',
    'aci_': 'ACI',
    'cosco_': 'Cosco',
    'sandalina_': 'Sandalina',
    'leona_': 'Leona',
    'tibet_': 'Tibet',
    'fiama_': 'Fiama',
    'xing_': 'Xing',
    'no1_': 'No1',
    'oxy_': 'Oxy',
    'silica_': 'Silica',

    # Home & Hygiene Competitors
    'harpic_': 'Harpic',
    'dettol_': 'Dettol',
    'tylox_': 'Tylox',
    'power_': 'Power',
    'swift_': 'Swift',
    'sunbit_': 'Sunbit',

    # Fabric Competitors
    'jet_': 'Jet',
    'orix_': 'Orix',
    'ghari_': 'Ghari',
    'fast_': 'Fast',
    'chaka_': 'Chaka',
    'keya_': 'Keya',
    'max_': 'Max',
    'xtra_': 'Xtra',
    'uniwash_': 'Uniwash',

    # Nutrition Competitors
    'pran_': 'Pran',
    'vita_': 'Vita',
}

# UBL (Unilever Bangladesh Limited) brands
UBL_BRANDS = {
    'Glow & Lovely', 'Glow & Handsome', "Pond's", 'Vaseline', 'Dove',
    'Sunsilk', 'Clear', 'Tresemme', 'Clinic Plus',
    'Horlicks', 'Maltova', 'Boost', 'Glucomax',
    'Pepsodent', 'Closeup',
    'Lux', 'Lifebuoy',
    'Vim', 'Domex',
    'Surf Excel', 'Wheel', 'Rin',
    'Knorr',
}


def extract_brand_from_product(product_name: str) -> str:
    """
    Extract brand name from AI detection class name.

    Args:
        product_name: AI class name (e.g., "sunsilk_black_small", "gl_mltvit_crm")

    Returns:
        Brand name (e.g., "Sunsilk", "Glow & Lovely") or "N/A" if not found

    Examples:
        >>> extract_brand_from_product("sunsilk_black_small")
        'Sunsilk'
        >>> extract_brand_from_product("gl_mltvit_crm")
        'Glow & Lovely'
        >>> extract_brand_from_product("unknown_product")
        'N/A'
    """
    if not product_name:
        return "N/A"

    product_lower = product_name.lower()

    # Check exact matches first (for specific patterns like dove_nr_lotion)
    if product_lower in BRAND_PATTERNS:
        return BRAND_PATTERNS[product_lower]

    # Check prefix patterns (most specific first - already ordered in BRAND_PATTERNS)
    for pattern, brand in BRAND_PATTERNS.items():
        if product_lower.startswith(pattern):
            return brand

    # No match found - competitor or unknown product
    return "N/A"


def get_company_name(brand_name: str) -> str:
    """
    Get company name for a brand.

    Args:
        brand_name: Brand name (e.g., "Sunsilk", "Parachute", "N/A")

    Returns:
        Company name: "Unilever Bangladesh Limited" for UBL brands, "Competitor" for others
    """
    if brand_name == "N/A":
        return "Competitor"

    # Check if brand is UBL
    if brand_name in UBL_BRANDS:
        return "Unilever Bangladesh Limited"

    # All other mapped brands are competitors
    return "Competitor"


def is_ubl_brand(brand_name: str) -> bool:
    """Check if brand is a UBL brand (not competitor)"""
    return brand_name in UBL_BRANDS
