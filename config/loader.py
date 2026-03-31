"""
Configuration Loading Module

Loads YAML configuration files and brand norms for the UBL AI system.
Exports all configuration constants needed across modules.
"""

import os
import yaml
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config/config.yaml") -> Dict:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Could not load config: {e}")
        return {}


def _load_brand_norms_main():
    """Load SOS brand norms from flat brand dict keyed by cls class name"""
    try:
        norm_path = os.path.join(os.path.dirname(__file__), "standards", "sos_brand_shelving_norm.yaml")
        with open(norm_path) as f:
            data = yaml.safe_load(f)
            norms = data.get('brands', {})
            logger.info(f"Loaded {len(norms)} brand norms for SOS classification")
            return norms
    except Exception as e:
        logger.warning(f"Could not load brand norms: {e}")
        return {}


def _load_waivers():
    """Load product waivers configuration"""
    try:
        waiver_path = os.path.join(os.path.dirname(__file__), "waivers.yaml")
        if not os.path.exists(waiver_path):
            logger.info("No waivers.yaml found, no products waived")
            return {}
        
        with open(waiver_path) as f:
            data = yaml.safe_load(f)
            if not data or 'waivers' not in data:
                return {}
            
            # Build set of enabled waived products
            waived = set()
            for waiver in data.get('waivers', []):
                product = waiver.get('product')
                enabled = waiver.get('enabled', False)
                if product and enabled:
                    waived.add(product)
            
            logger.info(f"Loaded {len(waived)} active product waivers")
            return {'waived_products': waived}
    except Exception as e:
        logger.warning(f"Could not load waivers: {e}")
        return {}


def _load_qpds_standards():
    """Load QPDS standards configuration"""
    try:
        qpds_path = os.path.join(os.path.dirname(__file__), "standards", "qpds_standards.yaml")
        with open(qpds_path) as f:
            data = yaml.safe_load(f)
            logger.info(f"Loaded QPDS standards with {len(data.get('shelf_types', {}))} shelf types")
            return data
    except Exception as e:
        logger.warning(f"Could not load QPDS standards: {e}")
        return {}


def _load_retail_catalog():
    """Load experimental retail catalog configuration."""
    try:
        catalog_path = os.path.join(os.path.dirname(__file__), "standards", "retail_catalog.yaml")
        with open(catalog_path) as f:
            data = yaml.safe_load(f) or {}
            brands = data.get('brands', {})
            logger.info(f"Loaded retail catalog with {len(brands)} brand entries")
            return data
    except Exception as e:
        logger.warning(f"Could not load retail catalog: {e}")
        return {"brands": {}}


# Load configuration at module import
CONFIG = load_config()

# Worker configuration (config.yaml > environment variable > default 4)
NUM_WORKERS = CONFIG.get('num_workers', int(os.getenv('NUM_INFERENCE_WORKERS', '4')))

# Per-worker models flag (default False for backward compatibility)
PER_WORKER_MODELS = CONFIG.get('per_worker_models', False)

# Model paths
MODEL_DIR = "models"
MODELS_CONFIG = CONFIG.get('models', {})

MODEL_PATHS = {
    'exclusivity': MODELS_CONFIG.get('exclusivity', os.path.join(MODEL_DIR, "EXCLUSIVITY.pt")),
    'sos_det': MODELS_CONFIG.get('sos_det', os.path.join(MODEL_DIR, "SOS-Detection.pt")),
    'sos_cls': MODELS_CONFIG.get('sos_cls', os.path.join(MODEL_DIR, "SOS-Classification.pt")),
    'qpds': MODELS_CONFIG.get('qpds', os.path.join(MODEL_DIR, "QPDS.pt")),
    'qpds_seg': MODELS_CONFIG.get('qpds_seg', os.path.join(MODEL_DIR, "QPDS-seg.pt")),
    'qpds_cls': MODELS_CONFIG.get('qpds_cls', os.path.join(MODEL_DIR, "QPDS-cls.pt")),
    'shelftalker': MODELS_CONFIG.get('shelftalker', os.path.join(MODEL_DIR, "Shelftalker.pt")),
    'sachet': MODELS_CONFIG.get('sachet', os.path.join(MODEL_DIR, "SACHET_YOLO11X.pt")),
    'posm': MODELS_CONFIG.get('posm', os.path.join(MODEL_DIR, "POSM_YOLO11X.pt")),
    'posm_comp': MODELS_CONFIG.get('posm_comp', os.path.join(MODEL_DIR, "POSM_COMP.pt")),
}

# Analysis configs
SHARE_OF_SHELF_CONFIG = CONFIG.get('share_of_shelf', {})
FIXED_SHELF_CONFIG = CONFIG.get('fixed_shelf', {})
SACHET_CONFIG = CONFIG.get('sachet', {})
POSM_CONFIG = CONFIG.get('posm', {})
SOVM_CONFIG = CONFIG.get('sovm', {})
RETAIL_EXPERIMENT_CONFIG = CONFIG.get('retail_experiment', {})

# Load brand norms at module import
BRAND_NORMS = _load_brand_norms_main()

# Load waivers at module import
WAIVERS = _load_waivers()

# Load QPDS standards at module import
QPDS_STANDARDS = _load_qpds_standards()
CONFIG['qpds_standards'] = QPDS_STANDARDS

# Load retail catalog at module import
RETAIL_CATALOG = _load_retail_catalog()
CONFIG['retail_catalog'] = RETAIL_CATALOG

