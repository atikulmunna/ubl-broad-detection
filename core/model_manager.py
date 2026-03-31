"""
Model Manager Module

Manages shared YOLO models across multiple workers with persistent CUDA streams.
All workers share the same model instances to save memory.
"""

import os
import logging
import threading
from typing import Dict, Optional, Any

import torch
from ultralytics import YOLO

from config.loader import MODEL_PATHS, MODELS_CONFIG, PER_WORKER_MODELS, NUM_WORKERS

logger = logging.getLogger(__name__)

# Backward compatibility: Allow environment variable override
NUM_INFERENCE_WORKERS = int(os.getenv('NUM_INFERENCE_WORKERS', str(NUM_WORKERS)))


class MultiStreamModelManager:
    """
    Manages YOLO models across multiple workers with two strategies:
    
    Strategy 1 (per_worker_models=False): Shared models with CUDA streams
    - Shared models: All workers use same YOLO instances (memory efficient)
    - Per-worker persistent CUDA streams for parallelism
    - Lock-free inference for maximum GPU utilization
    - 4x less VRAM usage
    
    Strategy 2 (per_worker_models=True): Per-worker model instances (YOLO-recommended)
    - Each worker gets separate YOLO model instances
    - Thread-safe by design (no shared state)
    - Higher VRAM usage (4x models loaded)
    - Guaranteed thread safety
    """

    def __init__(self, num_workers: int = NUM_INFERENCE_WORKERS, per_worker_models: bool = PER_WORKER_MODELS):
        self.num_workers = num_workers
        self.per_worker_models = per_worker_models
        
        # Strategy 1: Shared models
        self.models: Dict[str, YOLO] = {}

        # Strategy 2: Per-worker models {worker_id: {model_name: YOLO}}
        self.worker_models: Dict[int, Dict[str, YOLO]] = {}

        # Per-model inference locks (thread safety for shared models)
        self._model_locks: Dict[str, threading.Lock] = {}

        # Device detection: MPS (Apple Silicon) > CUDA (NVIDIA) > CPU

        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"

        # Per-worker CUDA streams (persistent for better performance, CUDA only)
        self.worker_streams: Dict[int, Any] = {}

        # Only use locks for model loading, not for inference
        self._loading_lock = threading.Lock()

        logger.info(f"Initializing MultiStreamModelManager on {self.device}")
        logger.info(f"Workers: {num_workers}")
        logger.info(f"Strategy: {'Per-worker models' if per_worker_models else 'Shared models with CUDA streams'}")

        if per_worker_models:
            # Strategy 2: Load separate models for each worker (YOLO-recommended)
            logger.info(f"Loading {len(MODEL_PATHS)} models × {num_workers} workers = {len(MODEL_PATHS) * num_workers} model instances")
            for worker_id in range(num_workers):
                self._load_worker_models(worker_id)
        else:
            # Strategy 1: Load shared models once (memory efficient)
            logger.info(f"Loading {len(MODEL_PATHS)} shared models (CUDA stream parallelism)")
            self._load_models()
            self._create_worker_streams()

    def _load_models(self):
        """Load all models once and share across workers"""
        # Only lock during loading, not inference
        with self._loading_lock:
            for model_name, model_path in MODEL_PATHS.items():
                try:
                    if os.path.exists(model_path):
                        logger.info(f"Loading {model_name} model from {model_path}")
                        model = YOLO(model_path)
                        model.to(self.device)
                        self.models[model_name] = model
                        self._model_locks[model_name] = threading.Lock()
                        logger.info(f"Loaded {model_name} model successfully")
                    else:
                        logger.warning(f"Model file not found: {model_path}")
                except Exception as e:
                    logger.error(f"Error loading {model_name} model: {e}")
    
    def _load_worker_models(self, worker_id: int):
        """Load separate model instances for a specific worker (Strategy 2)"""
        with self._loading_lock:
            self.worker_models[worker_id] = {}
            logger.info(f"Loading models for Worker {worker_id}")
            
            for model_name, model_path in MODEL_PATHS.items():
                try:
                    if os.path.exists(model_path):
                        logger.debug(f"Worker {worker_id}: Loading {model_name} from {model_path}")
                        model = YOLO(model_path)
                        model.to(self.device)
                        self.worker_models[worker_id][model_name] = model
                    else:
                        logger.warning(f"Worker {worker_id}: Model file not found: {model_path}")
                except Exception as e:
                    logger.error(f"Worker {worker_id}: Failed to load {model_name}: {e}")

    def _create_worker_streams(self):
        """Create persistent CUDA streams for each worker"""
        if self.device == "cuda":
            logger.info(f"Creating {self.num_workers} persistent CUDA streams")
            for worker_id in range(self.num_workers):
                self.worker_streams[worker_id] = torch.cuda.Stream()
                logger.debug(f"Worker {worker_id}: Stream created")
        else:
            logger.info("CPU mode - no CUDA streams needed")

    def get_model(self, model_name: str, worker_id: int = 0) -> Optional[YOLO]:
        """Get model instance (shared or worker-specific based on strategy)"""
        if self.per_worker_models:
            # Strategy 2: Return worker's own model instance
            if worker_id not in self.worker_models:
                logger.warning(f"Worker {worker_id} models not loaded, loading now...")
                self._load_worker_models(worker_id)
            return self.worker_models.get(worker_id, {}).get(model_name)
        else:
            # Strategy 1: Return shared model
            return self.models.get(model_name)

    def predict(self, model_name: str, source, worker_id: int = 0, **kwargs):
        """
        Run prediction using selected strategy (shared model + CUDA stream OR per-worker model).

        Args:
            model_name: Name of the model to use
            source: Image source (path, PIL, numpy array)
            worker_id: Worker ID for model/stream selection (0 to num_workers-1)
            **kwargs: Additional arguments for model.predict()

        Returns:
            Model prediction results
        """
        model = self.get_model(model_name, worker_id=worker_id)
        if model is None:
            raise ValueError(f"Model {model_name} not loaded for worker {worker_id}")

        if self.per_worker_models:
            # Strategy 2: Per-worker models (thread-safe by design, no streams needed)
            results = model.predict(source, **kwargs)
        else:
            # Strategy 1: Shared model — per-model lock for thread safety
            lock = self._model_locks.get(model_name)
            if lock:
                with lock:
                    if self.device == "cuda" and worker_id in self.worker_streams:
                        with torch.cuda.stream(self.worker_streams[worker_id]):
                            results = model.predict(source, **kwargs)
                    else:
                        results = model.predict(source, **kwargs)
            else:
                results = model.predict(source, **kwargs)

        return results


# Global model manager singleton
model_manager = MultiStreamModelManager()
