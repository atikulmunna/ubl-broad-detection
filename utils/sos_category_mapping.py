"""
SOS Category Mapping - Maps 243 AI class names to product categories
"""

from typing import Optional

SOS_CATEGORY_MAPPING = {
    # Fabric (24 classes)
    "chaka_powder": "fabric",
    "fast_wash_powder": "fabric",
    "ghari_powder": "fabric",
    "jet_detergent_power": "fabric",
    "keya_detergent_powder": "fabric",
    "keya_laundry_sope": "fabric",
    "max_wash_powder": "fabric",
    "orix_detergent_power": "fabric",
    "rin_nm_std_liquid": "fabric",
    "rin_powder_500g": "fabric",
    "rin_powder_antibacterial": "fabric",
    "surf_excel_matic_1l": "fabric",
    "surf_excel_matic_500ml": "fabric",
    "surf_excel_powder": "fabric",
    "surf_excel_powder_qw": "fabric",
    "tibet_570_sope": "fabric",
    "tibet_ball_sope": "fabric",
    "tibet_bar": "fabric",
    "tibet_powder": "fabric",
    "uniwash_powder": "fabric",
    "wheel_da_hard_soap": "fabric",
    "wheel_powder_500gm": "fabric",
    "xtra_powder": "fabric",

    # Hair Care (61 classes)
    "clear_ahf": "hair_care",
    "clear_cac": "hair_care",
    "clear_csm_large": "hair_care",
    "clear_csm_small": "hair_care",
    "clear_hal": "hair_care",
    "clinic_plus_snl": "hair_care",
    "dove_bar": "hair_care",
    "dove_cond": "hair_care",
    "dove_drt_hairmask": "hair_care",
    "dove_hfr_large": "hair_care",
    "dove_hfr_small": "hair_care",
    "dove_hg": "hair_care",
    "dove_irp_large": "hair_care",
    "dove_irp_small": "hair_care",
    "dove_mask_25": "hair_care",
    "dove_no": "hair_care",
    "dove_nr_lotion": "hair_care",
    "dove_oxg": "hair_care",
    "dove_shampoo_br": "hair_care",
    "dove_shampoo_ed": "hair_care",
    "dove_shampoo_hg": "hair_care",
    "dove_shampoo_muslim": "hair_care",
    "gl_aryuvedic_crm": "hair_care",
    "head_shoulders_men_shampoo": "hair_care",
    "himalaya_shampoo_ahf": "hair_care",
    "lily_shampoo": "hair_care",
    "livon_hair_serum": "hair_care",
    "meril_conditioner": "hair_care",
    "meril_shampoo": "hair_care",
    "pantene_hairfall_shampoo": "hair_care",
    "parachute_naturale_shampoo": "hair_care",
    "revive_hairfall_shampoo": "hair_care",
    "select_plus_men_shampoo": "hair_care",
    "sesa_shampoo": "hair_care",
    "streax_hair_serum": "hair_care",
    "sunsilk_black_large": "hair_care",
    "sunsilk_black_small": "hair_care",
    "sunsilk_fresh": "hair_care",
    "sunsilk_healthy_growth": "hair_care",
    "sunsilk_hfs": "hair_care",
    "sunsilk_hfs_cond": "hair_care",
    "sunsilk_hijab_antibr": "hair_care",
    "sunsilk_hijab_antidan": "hair_care",
    "sunsilk_hijab_refresh": "hair_care",
    "sunsilk_onion": "hair_care",
    "sunsilk_perfect_straight": "hair_care",
    "sunsilk_serum_25": "hair_care",
    "sunsilk_shampoo_black_pouch": "hair_care",
    "sunsilk_tl_large": "hair_care",
    "sunsilk_tl_small": "hair_care",
    "sunsilk_volume": "hair_care",
    "treseme_sampoo_bond_plex": "hair_care",
    "tresemme_cr": "hair_care",
    "tresemme_hfd": "hair_care",
    "tresemme_ks_large": "hair_care",
    "tresemme_ks_small": "hair_care",
    "tresemme_ks_white": "hair_care",
    "tresemme_mask_25": "hair_care",
    "tresemme_nr": "hair_care",
    "tresemme_nr_cond": "hair_care",
    "tresemme_serum_25": "hair_care",

    # Home And Hygiene (12 classes)
    "dettol_ad_liquid": "home_and_hygiene",
    "domex_lime": "home_and_hygiene",
    "domex_ocean": "home_and_hygiene",
    "harpic_toilet_cleaner": "home_and_hygiene",
    "power_toilet_cleaner": "home_and_hygiene",
    "sunbit_dishwashing_bar": "home_and_hygiene",
    "swift_toilet_cleaner": "home_and_hygiene",
    "tylox_toilet_cleaner": "home_and_hygiene",
    "vim_bar": "home_and_hygiene",
    "vim_liquid": "home_and_hygiene",
    "vim_pouch": "home_and_hygiene",
    "vim_powder": "home_and_hygiene",

    # Mini Meals (2 classes)
    "knorr_soup_corn": "mini_meals",
    "knorr_soup_thai": "mini_meals",

    # Nutrition (14 classes)
    "boost_std": "nutrition",
    "glucomax_bib": "nutrition",
    "horlicks_choco": "nutrition",
    "horlicks_junior": "nutrition",
    "horlicks_junior_s1": "nutrition",
    "horlicks_lite": "nutrition",
    "horlicks_mother": "nutrition",
    "horlicks_std": "nutrition",
    "horlicks_women": "nutrition",
    "maltova_bib": "nutrition",
    "maltova_std": "nutrition",
    "pran_glucoses_d": "nutrition",
    "simple_booster_serum": "nutrition",
    "vita_malt": "nutrition",

    # Oral Care (20 classes)
    "am_pm_toothpaste": "oral_care",
    "brushup_toothpaste": "oral_care",
    "closeup_ef": "oral_care",
    "closeup_lemon_salt": "oral_care",
    "closeup_mf": "oral_care",
    "closeup_redhot": "oral_care",
    "colgate_active": "oral_care",
    "cute_toothpaste": "oral_care",
    "dabur_red_toothpaste": "oral_care",
    "magic_tooth_powder": "oral_care",
    "mediplus_toothpaste": "oral_care",
    "meril_baby_toothpaste": "oral_care",
    "pepsodent_advanced_salt": "oral_care",
    "pepsodent_germicheck": "oral_care",
    "pepsodent_kids_orange": "oral_care",
    "pepsodent_kids_strawberry": "oral_care",
    "pepsodent_powder": "oral_care",
    "pepsodent_sensitive_expert": "oral_care",
    "sensodyne_fm_toothpaste": "oral_care",
    "whiteplus_toothpaste": "oral_care",

    # Skin Care (73 classes)
    "acnes_facewash": "skin_care",
    "boro_plus_lotion": "skin_care",
    "dove_bm_fw": "skin_care",
    "dr_rasel_serum": "skin_care",
    "fh_men_crm": "skin_care",
    "fiera_cream": "skin_care",
    "garnier_facewash": "skin_care",
    "garnier_men_facewash": "skin_care",
    "garnier_serum": "skin_care",
    "gh_men": "skin_care",
    "gh_men_fw": "skin_care",
    "gl_face_serum": "skin_care",
    "gl_foundation_crm": "skin_care",
    "gl_insta_glow_fw": "skin_care",
    "gl_lotion": "skin_care",
    "gl_mltvit_crm": "skin_care",
    "gl_sunscrn_crm": "skin_care",
    "gl_winter": "skin_care",
    "himalaya_cream": "skin_care",
    "himalaya_facewash": "skin_care",
    "himalaya_men_fw": "skin_care",
    "lakme_lemon_fw": "skin_care",
    "lakme_prad_crm": "skin_care",
    "lakme_strwaberry_fw": "skin_care",
    "lata_herbal_cream": "skin_care",
    "lily_facewash": "skin_care",
    "lotus_sunscreen": "skin_care",
    "meril_lotion": "skin_care",
    "meril_petroleum_jelly": "skin_care",
    "nivea_cream": "skin_care",
    "nivea_lotion": "skin_care",
    "nivea_men_facewash": "skin_care",
    "osufi_serum": "skin_care",
    "oxy_facewash": "skin_care",
    "parachute_lotion": "skin_care",
    "parachute_petroleum_jelly": "skin_care",
    "ponds_bright_beauty_crm": "skin_care",
    "ponds_bright_beauty_fw": "skin_care",
    "ponds_bright_miracle_fw": "skin_care",
    "ponds_daily_fw": "skin_care",
    "ponds_day_crm": "skin_care",
    "ponds_detan_fw": "skin_care",
    "ponds_facial_scrub": "skin_care",
    "ponds_hydra_gel": "skin_care",
    "ponds_light_moist": "skin_care",
    "ponds_lotion": "skin_care",
    "ponds_men_oil_control_fw": "skin_care",
    "ponds_men_pollout_fw": "skin_care",
    "ponds_milk_crm": "skin_care",
    "ponds_night_crm": "skin_care",
    "ponds_oil_control_fw": "skin_care",
    "ponds_sunscreen_crm": "skin_care",
    "ponds_vanish": "skin_care",
    "revive_lotion": "skin_care",
    "revive_sunscreen": "skin_care",
    "secret_toneup_sunscreen": "skin_care",
    "silica_cream": "skin_care",
    "simple_facial_toner": "skin_care",
    "simple_moist_fw": "skin_care",
    "simple_moisturiser": "skin_care",
    "simple_refreshing_fw": "skin_care",
    "tibet_cream": "skin_care",
    "tibet_petroleum_jelly": "skin_care",
    "vaseline_aloe": "skin_care",
    "vaseline_gluta_flawless": "skin_care",
    "vaseline_gluta_rad": "skin_care",
    "vaseline_hw": "skin_care",
    "vaseline_lotion_aloe": "skin_care",
    "vaseline_lotion_mqd": "skin_care",
    "vaseline_petroleum_jelly_aloe": "skin_care",
    "vaseline_petroleum_jelly_cocoa": "skin_care",
    "vaseline_petroleum_jelly_pure": "skin_care",
    "vaseline_tm": "skin_care",

    # Skin Cleansing (37 classes)
    "aci_neem_bar": "skin_cleansing",
    "acne_aid_bar": "skin_cleansing",
    "bactrol_soap": "skin_cleansing",
    "cosco_bar": "skin_cleansing",
    "dettol_soap": "skin_cleansing",
    "dove_bar_pink": "skin_cleansing",
    "fiama_gel_bar": "skin_cleansing",
    "himalaya_bar_turmeric": "skin_cleansing",
    "jasmine_bar": "skin_cleansing",
    "leona_bar": "skin_cleansing",
    "lifebuoy_bar_care": "skin_cleansing",
    "lifebuoy_bar_cfresh": "skin_cleansing",
    "lifebuoy_bar_lemon": "skin_cleansing",
    "lifebuoy_bar_total": "skin_cleansing",
    "lifebuoy_pouch": "skin_cleansing",
    "lifebuoy_pump": "skin_cleansing",
    "lily_beauty_soap": "skin_cleansing",
    "lily_body_wash": "skin_cleansing",
    "lux_bar_bright_glow": "skin_cleansing",
    "lux_bar_flawless": "skin_cleansing",
    "lux_bar_fresh": "skin_cleansing",
    "lux_bar_fresh_glow": "skin_cleansing",
    "lux_bar_soft_touch": "skin_cleansing",
    "lux_bar_velvet_touch": "skin_cleansing",
    "lux_blk_orchd": "skin_cleansing",
    "lux_brightening_vitamin": "skin_cleansing",
    "lux_freeasia_scnt": "skin_cleansing",
    "lux_french_rose": "skin_cleansing",
    "meril_milk_bar": "skin_cleansing",
    "nivea_body_wash": "skin_cleansing",
    "no1_bar": "skin_cleansing",
    "pears_bar": "skin_cleansing",
    "sandalina_bar": "skin_cleansing",
    "savlon_hand_wash": "skin_cleansing",
    "savlon_soap": "skin_cleansing",
    "septex_bar": "skin_cleansing",
    "xing_dw_bar": "skin_cleansing",
    "keya_lemon_bar": "skin_cleansing",

}


# Display names for categories (UI-friendly)
CATEGORY_DISPLAY_NAMES = {
    'skin_care': 'Skin Care',
    'hair_care': 'Hair Care',
    'oral_care': 'Oral Care',
    'nutrition': 'Nutrition',
    'fabric': 'Fabric',
    'skin_cleansing': 'Skin Cleansing',
    'mini_meals': 'Mini Meals',
    'home_and_hygiene': 'Home and Hygiene',
    'all': 'All Categories'
}


# Valid category identifiers
VALID_CATEGORIES = {
    'skin_care',
    'hair_care',
    'oral_care',
    'nutrition',
    'fabric',
    'skin_cleansing',
    'mini_meals',
    'home_and_hygiene',
    'all'
}


def get_sos_category(class_name: str) -> Optional[str]:
    """
    Get the category for a given AI detection class name.

    Args:
        class_name: AI detection class name (e.g., 'sunsilk_black_small')

    Returns:
        Category identifier (e.g., 'hair_care') or None if not found
    """
    return SOS_CATEGORY_MAPPING.get(class_name)


def get_category_display_name(category_id: str) -> str:
    """
    Get the display name for a category identifier.

    Args:
        category_id: Category identifier (e.g., 'hair_care')

    Returns:
        Display name (e.g., 'Hair Care')
    """
    return CATEGORY_DISPLAY_NAMES.get(category_id, category_id.replace('_', ' ').title())


def is_valid_category(category: str) -> bool:
    """
    Check if a category identifier is valid.

    Args:
        category: Category identifier to validate

    Returns:
        True if valid, False otherwise
    """
    return category in VALID_CATEGORIES


def get_all_categories() -> list:
    """
    Get list of all available category identifiers (excluding 'all').

    Returns:
        List of category identifiers
    """
    return sorted([cat for cat in VALID_CATEGORIES if cat != 'all'])
