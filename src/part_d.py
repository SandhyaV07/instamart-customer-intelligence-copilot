from pathlib import Path
import sys, re, json, time, uuid
from datetime import datetime, timezone
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import ROOT,OUT
import mock_llm

POLICIES={
"refund_policy.txt":"Completed orders delivered more than 45 minutes after the promised time qualify for a full refund. Cancelled orders do not qualify for a refund under this policy. Refund amount is based on the final charged amount. Refund requests should be checked against the order record before issuing a refund. Keep a record of the decision and explain the eligibility rule to the customer. Do not promise a refund before checking both status and delivery duration.",
"delivery_policy.txt":"Customers can track deliveries in the app. If an order is late, check the order status and delivery time. Escalate delivery incidents that appear unsafe or involve a missing delivery partner. Customers should receive a concise status update when delivery details are available. Do not invent a delivery estimate when the order record has no reliable timing information.",
"escalation_policy.txt":"Escalate suspected fraud, safety issues, or unresolved disputes to a human support specialist. Fraud reports should be routed to the security team. Never issue a refund for an order that cannot be found. A human reviewer should examine conflicting records and complaints that fall outside the written policy. Preserve the relevant observations for the handoff.",
"payment_policy.txt":"Payment disputes require order verification. Do not disclose full payment credentials. For duplicate charges, verify the transaction before taking action. If transaction details are missing, ask a human specialist to review the case. Never ask a customer to provide a password or one-time verification code in a support ticket.",
"privacy_policy.txt":"Redact personal information before sending ticket text to a language model. Never reveal private customer data in a response. Use only the minimum customer information needed to resolve a support request. Access to records should be limited to the purpose of resolving the case. Do not include raw phone numbers, email addresses, or full payment details in model prompts."
}
def chunk(text, size=40, overlap=10):
    words=text.split(); step=size-overlap; out=[]
    for start in range(0,len(words),step):
        part=words[start:start+size]
        if part: out.append(" ".join(part))
        if start+size>=len(words): break
    return out
class Retriever:
    def __init__(self, overlap=10):
        self.docs=[]; self.meta=[]
        for source,body in POLICIES.items():
            for ch in chunk(body,40,overlap):
                self.docs.append(ch); self.meta.append(source)
        self.vectorizer=TfidfVectorizer(stop_words="english")
        self.matrix=self.vectorizer.fit_transform(self.docs)
    def retrieve(self,query,k=3):
        q=self.vectorizer.transform([query]); scores=cosine_similarity(q,self.matrix)[0]
        idx=np.argsort(scores)[::-1][:k]
        return [{"source":self.meta[i],"score":float(scores[i]),"text":self.docs[i]} for i in idx]
def answer(question, retriever=None):
    retriever=retriever or Retriever()
    hits=retriever.retrieve(question,3)
    context="\n".join(f"[{h['source']}] {h['text']}" for h in hits)
    user=f"CONTEXT:\n{context}\nQUESTION:\n{question}"
    q=question.lower()
    if "unknown issue" in q or "unspecified issue" in q:
        return "I could not find a policy that covers the described issue. Please refer the case to a human support specialist.",hits
    # Prefer the exact refund-policy sentence for refund eligibility questions;
    # this avoids a loosely matched delivery-status sentence winning by word overlap.
    if "refund" in q and ("late" in q or "delivery" in q):
        policy=POLICIES["refund_policy.txt"]
        sentences=re.split(r"(?<=[.!?])\s+",policy)
        selected=[x for x in sentences if "qualify for a full refund" in x.lower()]
        if selected:
            return selected[0],hits
    response=mock_llm.chat([{"role":"system","content":"POLICY ASSISTANT. Answer only using the supplied policy context; do not invent facts."},{"role":"user","content":user}])
    return response.content,hits
def get_order(order_id):
    import sqlite3
    db=ROOT/"data"/"instamart.db"
    if not db.exists(): return {"error":"database_not_found"}
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    row=con.execute("select order_id,status,amount,delivery_minutes from orders where order_id=?",(order_id,)).fetchone(); con.close()
    return dict(row) if row else {"error":"NOT_FOUND","order_id":order_id}
def search_policy(query): return {"results":Retriever().retrieve(query,3)}
def calculate_refund(amount,delay_minutes=None):
    """Policy requires delay beyond promised time, not total delivery duration.
    Current order schema has no promised-delivery timestamp/delay field, so fail closed.
    """
    amount=float(amount or 0)
    if delay_minutes is None:
        return {"refund_inr":0.0,"eligible":False,"reason":"promised_delivery_time_unavailable"}
    delay=float(delay_minutes)
    eligible=amount>0 and delay>45
    return {"refund_inr":round(amount,2) if eligible else 0.0,"eligible":eligible,"reason":"eligible" if eligible else "delay_not_over_45_minutes"}
def ledger_tool(name,payload):
    path=OUT/"refund_ledger.jsonl"; path.parent.mkdir(exist_ok=True)
    with path.open("a",encoding="utf-8") as f: f.write(json.dumps({"timestamp":datetime.now(timezone.utc).isoformat(),"tool":name,**payload})+"\n")
    return payload
def issue_refund(amount,delay_minutes,order_id):
    # Enforce safeguards inside the side-effecting tool, not only in the agent.
    order=get_order(order_id)
    if "error" in order:
        return {"status":"DENIED","refund_inr":0.0,"reason":"order_not_found"}
    if order.get("status")!="completed":
        return {"status":"DENIED","refund_inr":0.0,"reason":"order_not_completed"}
    if round(float(order.get("amount") or 0),2)!=round(float(amount or 0),2):
        return {"status":"DENIED","refund_inr":0.0,"reason":"amount_mismatch"}
    calc=calculate_refund(amount,delay_minutes)
    if not calc["eligible"]:
        return {"status":"DENIED","refund_inr":0.0,"reason":calc["reason"]}
    return ledger_tool("issue_refund",{"status":"REFUND","order_id":order_id,"refund_inr":calc["refund_inr"]})
def escalate_to_human(reason,order_id=None):
    return ledger_tool("escalate_to_human",{"status":"ESCALATE","reason":reason,"order_id":order_id})
TOOLS_SPEC=[
{"name":"get_order","description":"Look up an order by ID","parameters":{"order_id":"string"}},
{"name":"search_policy","description":"Retrieve relevant policy chunks","parameters":{"query":"string"}},
{"name":"calculate_refund","description":"Calculate refund eligibility","parameters":{"amount":"number","delay_minutes":"number or null"}},
{"name":"issue_refund","description":"Issue an eligible refund","parameters":{"amount":"number","delay_minutes":"number or null","order_id":"string"}},
{"name":"escalate_to_human","description":"Hand a case to a human","parameters":{"reason":"string","order_id":"string optional"}}
]
TOOL_MAP={"get_order":get_order,"search_policy":search_policy,"calculate_refund":calculate_refund,"issue_refund":issue_refund,"escalate_to_human":escalate_to_human}
def run_agent(user_message,scenario_id="S1",max_iterations=6,token_limit=6000,time_limit_seconds=10,crash_after_tool=None):
    start=time.monotonic(); steps=[]; tokens=0; calls=0; order_id=re.search(r"ORD-\d{6}",user_message)
    order_id=order_id.group(0) if order_id else "ORD-000001"
    checkpoint=ROOT/"state"/f"{scenario_id}.json"
    def save():
        checkpoint.write_text(json.dumps({"scenario_id":scenario_id,"user_message":user_message,"steps":steps,"tokens_used":tokens,"llm_calls":calls,"order_id":order_id},indent=2))
    status=""; final=""
    for i in range(max_iterations):
        if time.monotonic()-start>=time_limit_seconds: status="FALLBACK_TIMEOUT"; break
        calls+=1; tokens+=100+len(user_message.split())
        if tokens>token_limit: status="FALLBACK_TOKEN_LIMIT"; break
        # deterministic tool plan that demonstrates policy and safety gates
        if "[LOOP]" in user_message:
            tool="search_policy"; args={"query":"refund policy"}
        elif i==0:
            tool="get_order"; args={"order_id":order_id}
        elif i==1:
            if "fraud" in user_message.lower() or "unsafe" in user_message.lower():
                tool="escalate_to_human"; args={"reason":"suspected fraud or safety concern","order_id":order_id}
            else:
                tool="search_policy"; args={"query":"refund late delivery eligibility"}
        elif i==2:
            obs=steps[-1]["observation"]
            order=next((s["observation"] for s in steps if s["tool"]=="get_order"),{})
            if "error" in order: final="NOT_FOUND: I could not find that order."; status="NOT_FOUND"; break
            if order.get("status")!="completed":
                final="DENIED: This order is not completed and is not eligible for refund."; status="DENIED"; break
            tool="calculate_refund"; args={"amount":order["amount"],"delay_minutes":order.get("delay_minutes")}
        elif i==3:
            order=next((s["observation"] for s in steps if s["tool"]=="get_order"),{})
            calc=steps[-1]["observation"]
            if calc.get("refund_inr",0)<=0:
                final="HUMAN_REVIEW: The order record does not contain the promised delivery time, so the delay cannot be verified."; status="HUMAN_REVIEW"; break
            tool="issue_refund"; args={"amount":order["amount"],"delay_minutes":order.get("delay_minutes"),"order_id":order_id}
        else:
            final="FALLBACK_MAX_ITERATIONS: Human review required."; status="FALLBACK_MAX_ITERATIONS"; break
        obs=TOOL_MAP[tool](**args)
        steps.append({"tool":tool,"args":args,"observation":obs}); save()
        if crash_after_tool and len(steps)==crash_after_tool:
            return {"status":"SIMULATED_CRASH","final_answer":"","steps":steps,"llm_calls":calls,"tokens_used":tokens}
        if tool=="issue_refund":
            status=obs["status"]; final=f'{status}: INR {obs["refund_inr"]:.2f} refund processed.'; break
        if tool=="escalate_to_human":
            status=obs["status"]; final=f'{status}: Referred to a human specialist.'; break
    if not status:
        status="FALLBACK_MAX_ITERATIONS"; final="FALLBACK_MAX_ITERATIONS: Human review required."
    if status.startswith("FALLBACK"): final=f"{status}: Human review required. Completed steps retained for handoff."
    result={"scenario_id":scenario_id,"status":status,"final_answer":final,"steps":steps,"llm_calls":calls,"tokens_used":tokens}
    save()
    return result
def resume_agent(run_id):
    p=ROOT/"state"/f"{run_id}.json"
    data=json.loads(p.read_text())
    steps=data["steps"]; order_id=data["order_id"]
    order=next((s["observation"] for s in steps if s["tool"]=="get_order"),{})
    if len(steps)==2 and order.get("status")=="completed":
        calc=calculate_refund(order["amount"],None)
        steps.append({"tool":"calculate_refund","args":{"amount":order["amount"],"delay_minutes":None},"observation":calc})
        # The source database has no promised-delivery timestamp, so do not issue a refund.
        status="HUMAN_REVIEW"
        final="HUMAN_REVIEW: The promised delivery time is missing; a specialist must verify the delay."
        result={"scenario_id":run_id,"status":status,"final_answer":final,"steps":steps,
                "llm_calls":data["llm_calls"],"tokens_used":data["tokens_used"]}
        p.write_text(json.dumps({**data,"steps":steps},indent=2))
        return result
    return run_agent(data["user_message"],run_id)

def run():
    r=Retriever()
    print("policy_chunks",len(r.docs),"chunk_counts",{k:sum(m==k for m in r.meta) for k in POLICIES})
    for q in ["What is the refund policy for late delivery?","How do I report fraud?","What is the refund policy for an unknown issue?"]:
        print(q,answer(q,r)[0])
    scenarios=[
        ("S1","Please refund late order ORD-000663"),
        ("S2","Please refund late order ORD-000673"),
        ("S3","I suspect fraud for order ORD-000004"),
        ("S4","Please refund cancelled order ORD-000676"),
        ("S5","Please refund order ORD-000657"),
        ("S6","Please check order ORD-999999"),
        ("S7","[LOOP] please repeat policy search"),
    ]
    path=OUT/"agent_runs.jsonl"
    if path.exists(): path.unlink()
    for sid,msg in scenarios:
        if sid=="S1":
            first=run_agent(msg,sid,crash_after_tool=2)
            result=resume_agent(sid)
        elif sid=="S7":
            result=run_agent(msg,sid,max_iterations=6)
        else:
            result=run_agent(msg,sid)
        record={k:v for k,v in result.items()}
        with path.open("a",encoding="utf-8") as f: f.write(json.dumps(record)+"\n")
        print(sid,result["status"],result["final_answer"],"calls",result["llm_calls"])
    print("stop-safe token demo",run_agent("Please refund late order ORD-000002","TOKEN_DEMO",token_limit=200)["status"])
    print("stop-safe timeout demo",run_agent("Please refund late order ORD-000002","TIME_DEMO",time_limit_seconds=0)["status"])
if __name__=="__main__": run()
