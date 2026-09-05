"""
Structured logging for the pipeline.
"""
import json
import time
import traceback
from datetime import datetime
from contextlib import contextmanager

try:
    import google.cloud.logging
    _GCP_LOGGING_AVAILABLE = True
except ImportError:
    _GCP_LOGGING_AVAILABLE = False
    import logging

class PipelineLogger:
    def __init__(self, stage: str, run_id: str = ''):
        self.stage = stage
        self.run_id = run_id
        self._gcp_logger = None
        
        if _GCP_LOGGING_AVAILABLE:
            try:
                client = google.cloud.logging.Client()
                self._gcp_logger = client.logger("oladizz-research")
            except Exception:
                self._gcp_logger = None
        
        if not self._gcp_logger:
            self._local_logger = logging.getLogger("PipelineLogger")
            if not self._local_logger.handlers:
                handler = logging.StreamHandler()
                self._local_logger.addHandler(handler)
            self._local_logger.setLevel(logging.INFO)

    def _log(self, severity: str, message: str, **kwargs):
        entry = {
            "run_id": self.run_id,
            "stage": self.stage,
            "severity": severity,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": kwargs
        }
        
        if self._gcp_logger:
            self._gcp_logger.log_struct(entry, severity=severity)
        else:
            msg = json.dumps(entry)
            if severity in ("ERROR", "CRITICAL"):
                self._local_logger.error(msg)
            elif severity == "WARNING":
                self._local_logger.warning(msg)
            else:
                self._local_logger.info(msg)

    def info(self, message: str, **kwargs):
        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, include_traceback: bool = True, **kwargs):
        if include_traceback:
            kwargs["traceback"] = traceback.format_exc()
        self._log("ERROR", message, **kwargs)

    def metric(self, name: str, value: float, unit: str):
        self._log("INFO", f"Metric: {name}={value}{unit}", metric_name=name, metric_value=value, metric_unit=unit)

    @contextmanager
    def timer(self, name: str):
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            self.metric(name, duration, "seconds")
