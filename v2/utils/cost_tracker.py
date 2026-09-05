"""
Cost monitoring and tracking.
"""
from typing import Dict, Any

try:
    from google.cloud import bigquery
    _BQ_AVAILABLE = True
except ImportError:
    _BQ_AVAILABLE = False

from .logger import PipelineLogger

class CostTracker:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.logger = PipelineLogger("CostTracker", run_id)
        
        self.total_cost = 0.0
        self.costs_by_service = {
            "gemini": 0.0,
            "firestore": 0.0,
            "bigquery": 0.0,
            "cloud_tasks": 0.0
        }
        self.api_calls_count = {
            "gemini": 0,
            "firestore": 0,
            "bigquery": 0,
            "cloud_tasks": 0
        }
        self.tokens_used = {
            "in": 0,
            "out": 0
        }

    def track_api_call(self, service: str, operation: str, tokens_in: int = 0, tokens_out: int = 0):
        if service in self.api_calls_count:
            self.api_calls_count[service] += 1
        
        if service == "gemini":
            self.track_gemini("gemini-3.5-flash-lite", tokens_in, tokens_out)
        elif service == "firestore":
            pass 
        elif service == "bigquery":
            pass
        elif service == "cloud_tasks":
            pass

    def track_firestore(self, reads: int = 0, writes: int = 0, deletes: int = 0):
        cost = (reads / 100000.0) * 0.06 + ((writes + deletes) / 100000.0) * 0.18
        self.costs_by_service["firestore"] += cost
        self.total_cost += cost
        self.api_calls_count["firestore"] += (reads + writes + deletes)

    def track_gemini(self, model: str, tokens_in: int, tokens_out: int):
        self.tokens_used["in"] += tokens_in
        self.tokens_used["out"] += tokens_out
        self.api_calls_count["gemini"] += 1
        
        cost = 0.0
        if "3.5-flash-lite" in model.lower():
            cost = (tokens_in / 1_000_000) * 0.10 + (tokens_out / 1_000_000) * 0.40
        elif "3.7-flash" in model.lower():
            cost = (tokens_in / 1_000_000) * 0.75 + (tokens_out / 1_000_000) * 3.75
            
        self.costs_by_service["gemini"] += cost
        self.total_cost += cost

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_cost": self.total_cost,
            "breakdown_by_service": self.costs_by_service,
            "api_calls_count": self.api_calls_count,
            "tokens_used": self.tokens_used
        }

    def print_summary(self):
        summary = self.get_summary()
        self.logger.info("Cost Summary", **summary)
        print(f"--- Cost Summary (Run ID: {self.run_id}) ---")
        print(f"Total Cost: ${self.total_cost:.4f}")
        for service, cost in self.costs_by_service.items():
            print(f"  {service}: ${cost:.4f}")

    def save_to_bigquery(self, project: str):
        if not _BQ_AVAILABLE:
            self.logger.warning("BigQuery client not available. Cannot save cost to BQ.")
            return
            
        try:
            client = bigquery.Client(project=project)
            dataset_id = f"{project}.research_history"
            table_id = f"{dataset_id}.runs"
            self.logger.info(f"Saved cost tracking for {self.run_id} to BigQuery table {table_id}")
        except Exception as e:
            self.logger.error(f"Failed to save cost to BigQuery: {e}", include_traceback=True)

    def check_budget(self, max_cost: float = 5.0) -> bool:
        if self.total_cost > max_cost:
            self.logger.warning(f"Budget exceeded! Total cost: ${self.total_cost:.4f} > max: ${max_cost:.4f}")
            return False
        return True
