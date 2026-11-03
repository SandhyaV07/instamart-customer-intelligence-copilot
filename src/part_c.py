from pathlib import Path
import sys, re, json, time, random
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import ROOT,RAW,OUT
import mock_llm

ALLOWED={"billing","delivery","technical","fraud"}
EMAIL=re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE=re.compile(r"\b[6-9]\d{9}\b")
ORDER=re.compile(r"ORD-\d{6}")
def redact(s):
    s=EMAIL.sub("[EMAIL]",str(s)); s=PHONE.sub("[PHONE]",s); s=ORDER.sub("[ORDER_ID]",s)
    return s
def route(status,category,segment_name):
    if status in {"skipped_empty","flagged_long","flagged_invalid_output","budget_exhausted"}: return "human_review","NORMAL"
    if category=="fraud": return "security_team","HIGH"
    if segment_name=="Premium": return "premium_desk","HIGH"
    return "support_queue","NORMAL"
def classify(frame, few_shot=True, budget=100000, output_name="triage_results.csv"):
    mock_llm.reset()
    results=[]; running_tokens=0; retries=0
    seg_path=OUT/"customer_segments.csv"
    segments=pd.read_csv(seg_path) if seg_path.exists() else pd.DataFrame(columns=["customer_id","segment_name"])
    seg=dict(zip(segments.customer_id,segments.segment_name))
    system="CLASSIFY the ticket. Categories: billing, delivery, technical, fraud. Return JSON only: {\"category\":\"...\",\"reason\":\"...\"}."
    if few_shot: system += "\nEXAMPLES:\nMessage: I suspect fraud. => {\"category\":\"fraud\",\"reason\":\"unauthorized activity\"}\nMessage: app crashes. => {\"category\":\"technical\",\"reason\":\"app failure\"}"
    for _,row in frame.iterrows():
        ticket=str(row["message"] or "")
        red=redact(ticket)
        est=len(red.split())
        base={"ticket_id":row.ticket_id,"customer_id":row.customer_id,"status":"","category":"","segment_name":seg.get(row.customer_id,"Unknown"),"priority":"","route":"","tokens_used":0}
        if not red.strip(): base["status"]="skipped_empty"
        elif est>400: base["status"]="flagged_long"
        else:
            status=None; category=None; tokens=0
            for attempt in range(4):
                if running_tokens>=budget:
                    status="budget_exhausted"; break
                try:
                    response=mock_llm.chat([{"role":"system","content":system},{"role":"user","content":red}])
                    tokens=response.usage.total_tokens; running_tokens+=tokens
                    content=response.choices[0].message.content or ""
                    try:
                        obj=json.loads(content)
                        if obj.get("category") in ALLOWED:
                            category=obj["category"]; status="classified_json"
                        else: status="flagged_invalid_output"
                    except Exception:
                        words=re.findall(r"[a-z]+",content.lower())
                        matches=set(words)&ALLOWED
                        if len(matches)==1:
                            category=matches.pop(); status="classified_keyword"
                        else: status="flagged_invalid_output"
                    break
                except mock_llm.TransientLLMError:
                    retries+=1
                    if attempt<3: time.sleep(.001*(2**attempt)*random.uniform(.9,1.15))
                    else: status="flagged_invalid_output"
                except Exception:
                    status="flagged_invalid_output"
                    break
            base["status"]=status or "flagged_invalid_output"; base["category"]=category or ""
            base["tokens_used"]=tokens
        base["route"],base["priority"]=route(base["status"],base["category"],base["segment_name"])
        results.append(base)
    out=pd.DataFrame(results)
    out.to_csv(OUT/output_name,index=False)
    print(output_name, "status_counts",out.status.value_counts().to_dict(),"tokens",running_tokens,"retries",retries)
    return out
def run():
    tickets=pd.read_csv(RAW/"tickets.csv").rename(columns={"text":"message"}).fillna({"message":""})
    zero=classify(tickets,False,6000,"triage_budget_demo.csv")
    final=classify(tickets,True,100000,"triage_results.csv")
    print("Final rows:",len(final),"PII remaining:",sum(bool(EMAIL.search(redact(x)) or PHONE.search(redact(x)) or ORDER.search(redact(x))) for x in tickets.message))
if __name__=="__main__": run()
