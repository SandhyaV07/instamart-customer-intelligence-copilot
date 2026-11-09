"""Offline deterministic mock LLM used for the capstone. No network calls."""
import json, re
from dataclasses import dataclass, field

_calls = 0
_successes = 0
@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    @property
    def total_tokens(self): return self.prompt_tokens + self.completion_tokens
@dataclass
class Response:
    content: str = ""
    tool_calls: list = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

def reset():
    global _calls, _successes
    _calls = 0; _successes = 0

def _tokens(s): return max(1, len(str(s).split()))

def chat(messages, tools=None, temperature=0):
    global _calls, _successes
    _calls += 1
    joined = "\n".join(str(m.get("content","")) for m in messages)
    # Periodic transient failures mimic an unreliable local service.
    if _calls % 9 == 0:
        raise RuntimeError("transient mock service error")
    _successes += 1
    prompt_tokens = _tokens(joined)
    if "POLICY ASSISTANT" in joined:
        context = re.search(r"CONTEXT:\n(.*?)\nQUESTION:\n(.*)", joined, re.S)
        answer = "I could not find a supported answer in the supplied policy context."
        if context:
            ctx, q = context.group(1), context.group(2).lower()
            sentences = re.split(r"(?<=[.!?])\s+", ctx)
            scored = sorted(sentences, key=lambda s: sum(w in s.lower() for w in re.findall(r"\w+", q)), reverse=True)
            if scored and any(w in scored[0].lower() for w in re.findall(r"\w+", q)):
                answer = scored[0].strip()
        content = answer
    elif "CLASSIFY" in joined:
        text = messages[-1].get("content","").lower()
        if "EXAMPLES:" in joined:
            order = ["fraud","technical","billing","delivery"]
        else:
            order = ["billing","fraud","technical","delivery"]
        kws = {
            "billing":["charged","refund","payment","billing","invoice","double"],
            "delivery":["late","delivery","arrived","missing","order not"],
            "technical":["app","crash","login","error","checkout","screen"],
            "fraud":["fraud","not recognize","unauthorized","suspicious","stolen"]
        }
        scores={c:sum(k in text for k in kws[c]) for c in order}
        category=max(order,key=lambda c:scores[c])
        if _successes % 13 == 0:
            content=f"I believe the category is {category} because the message suggests it."
        elif _successes % 17 == 0:
            content=json.dumps({"category":"shipping","reason":"Invalid category from simulated model."})
        else:
            content=json.dumps({"category":category,"reason":"Matched message cues."})
    elif "AGENT" in joined:
        # Tool-using agent responses are deliberately lightweight; scripts may also run deterministic plans.
        content="I need a human agent to review this request."
    else:
        content="I could not find a supported answer in the supplied context."
    return Response(content=content, usage=Usage(prompt_tokens=prompt_tokens, completion_tokens=_tokens(content)))
