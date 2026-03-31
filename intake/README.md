Client SDK Contract (What Researchers Must Do)
Minimum Required Code:
import uuid
from datetime import datetime
import requests

# 1. Initialize run

run_id = str(uuid.uuid4())
agent_name = "my-agent"
project_id = "my-experiment"

# 2. Execute step & send span

start = datetime.utcnow()
result = my_llm.generate("What is RAG?")
end = datetime.utcnow()

requests.post("http://localhost:8000/v1/spans", json={
"span_id": str(uuid.uuid4()),
"run_id": run_id,
"agent_name": agent_name,
"project_id": project_id,
"span_type": "llm_call",
"name": "Initial reasoning",
"started_at": start.isoformat(),
"completed_at": end.isoformat(),
"is_final": False, # ← Required!

    # Optional LLM metrics
    "model_id": "gpt-4",
    "tokens_input": 100,
    "tokens_output": 200

})

# 3. Last span must set is_final=True

requests.post("http://localhost:8000/v1/spans", json={
"span_id": str(uuid.uuid4()),
"run_id": run_id,
"agent_name": agent_name,
"project_id": project_id,
"span_type": "custom",
"name": "Run complete",
"started_at": datetime.utcnow().isoformat(),
"completed_at": datetime.utcnow().isoformat(),
"is_final": True # ← Triggers finalization!
})
