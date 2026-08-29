import json
import uuid
import datetime
import logging
from typing import Any, Dict, Optional
from agent.tools.base import BaseTool

logger = logging.getLogger(__name__)

try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    logger.warning("google-cloud-firestore SDK not installed. Falling back to mock DB.")


class DBManagerTool(BaseTool):
    name = "db_manager"
    description = "Queries, updates, and persists agent state, records, and task metrics to central storage (Firestore)."

    def __init__(self):
        self.db = None
        self.mock_db = {}
        if FIRESTORE_AVAILABLE:
            try:
                # Initializes with default credentials (Cloud Run injects these automatically)
                self.db = firestore.Client()
                logger.info("Successfully connected to Google Cloud Firestore.")
            except Exception as e:
                logger.error(f"Failed to initialize Firestore Client: {e}. Falling back to in-memory mock dict.")

    def run(
        self,
        action: str = "upsert",
        collection: str = "task_records",
        data: Optional[Dict[str, Any]] = None,
        query_filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        data_to_store = data or {"status": "ACTIVE", "processed_by": "TaskmasterAgent"}

        if not self.db:
            # Fallback mock mode (useful for local dev without credentials)
            return self._mock_run(action, collection, data_to_store)

        try:
            col_ref = self.db.collection(collection)

            if action in ("upsert", "write", "create"):
                # Firestore will auto-generate an ID if we use add()
                # But it's easier to create a document ref to get the ID
                doc_ref = col_ref.document()
                # Firestore natively handles nested dicts/types, no need to json.dumps
                doc_ref.set({
                    "data": data_to_store,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                return {
                    "action": action,
                    "collection": collection,
                    "record_id": doc_ref.id,
                    "stored_data": data_to_store,
                    "status": "SUCCESS"
                }
            
            elif action in ("query", "read"):
                # Just fetch all documents in the collection up to 10 limits for safety
                query = col_ref.limit(10)
                docs = query.stream()
                
                records = []
                for doc in docs:
                    doc_dict = doc.to_dict()
                    records.append({
                        "id": doc.id,
                        "data": doc_dict.get("data", {}),
                        "timestamp": str(doc_dict.get("timestamp"))
                    })
                    
                return {
                    "action": action,
                    "collection": collection,
                    "result_count": len(records),
                    "records": records
                }

            return {"action": action, "status": "COMPLETED", "details": "Default operation executed"}
            
        except Exception as e:
            return {
                "status": "FAILED",
                "error": f"Firestore Operation Failed: {str(e)}"
            }
            
    def _mock_run(self, action: str, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if action in ("upsert", "write", "create"):
            record_id = str(uuid.uuid4())
            if collection not in self.mock_db:
                self.mock_db[collection] = []
            
            self.mock_db[collection].append({
                "id": record_id,
                "data": data,
                "timestamp": str(datetime.datetime.now())
            })
            
            return {
                "action": action,
                "collection": collection,
                "record_id": record_id,
                "stored_data": data,
                "status": "SUCCESS"
            }
        elif action in ("query", "read"):
            records = self.mock_db.get(collection, [])
            return {
                "action": action,
                "collection": collection,
                "result_count": len(records),
                "records": records[:10]
            }
            
        return {"action": action, "status": "COMPLETED", "details": "Default mock operation executed"}
