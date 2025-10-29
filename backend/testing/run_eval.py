import json, re, statistics
from openai import OpenAI

MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = open("testing/llm1_system_v1_1.md", "r", encoding="utf-8").read()

client = OpenAI()  # setzt OPENAI_API_KEY aus der Umgebung

A = dict(temperature=0.1, top_p=0.9, seed=42, max_output_tokens=1000)
B = dict(temperature=0.3, top_p=0.9, seed=42, max_output_tokens=1000)

def call_llm(params, chat_history, human_input):
    dev = SYSTEM_PROMPT.replace("{{chat_history}}", chat_history)\
                       .replace("{{human_input}}", human_input)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "developer", "content": dev}],
        **params
    )
    return resp.choices[0].message.content

# ---- Checks (leicht erweiterbar) ----
RE_STATUS = re.compile(r"status:\s*(schätzung|bestätigt)\b", re.I)
RE_ITEM   = re.compile(r"- name=.+?, menge=\d+(\.\d+)?, einheit=(kg|L|m²|m|Stück|Platte)")
FORBIDDEN = re.compile(r"\b(Eimer|Sack|Gebinde|VE)\b", re.I)

def eval_case(output, expect):
    score = 0
    notes = []

    m = RE_STATUS.search(output or "")
    status = (m.group(1).lower() if m else None)

    # Mode-Mapping
    if expect["mode"] == "guard":
        if "Es liegen noch keine Angebotsdaten vor." in output:
            score += 1
        else:
            notes.append("guard text fehlt")
    elif expect["mode"] == "schaetzung":
        if status == "schätzung": score += 1
        else: notes.append("status != schätzung")
        # Pflicht-Überschriften
        for h in ["**Projektbeschreibung**", "**Leistungsdaten**", "**Materialbedarf**"]:
            if h in output: score += 0.5
            else: notes.append(f"Header fehlt: {h}")
        # Material-Zeilen vorhanden
        if RE_ITEM.search(output): score += 1
        else: notes.append("kein Material-Item erkannt")
    elif expect["mode"] == "bestaetigt":
        if status == "bestätigt": score += 1
        else: notes.append("status != bestätigt")

    # Muss-Strings
    for must in expect.get("must_include", []):
        if must in output: score += 0.25
        else: notes.append(f"must_include fehlt: {must}")

    # Verbote (Gebinde etc.)
    if FORBIDDEN.search(output):
        notes.append("verbotene Begriffe gefunden (Gebinde/VE)")
    else:
        score += 0.5

    return score, notes

def run_variant(params, cases):
    results = []
    for c in cases:
        out = call_llm(params, c["chat_history"], c["human_input"])
        score, notes = eval_case(out, c["expect"])
        results.append({"name": c["name"], "score": score, "notes": notes, "output": out})
    return results

if __name__ == "__main__":
    cases = json.load(open("eval_cases.json", "r", encoding="utf-8"))

    resA = run_variant(A, cases)
    resB = run_variant(B, cases)

    def summarize(res, label):
        scores = [r["score"] for r in res]
        print(f"\n=== {label} ===")
        print(f"Mean score: {statistics.mean(scores):.2f} | Min: {min(scores):.2f} | Max: {max(scores):.2f}")
        for r in res:
            print(f"- {r['name']}: {r['score']:.2f}  {'; '.join(r['notes']) if r['notes'] else 'OK'}")
        return scores

    sA = summarize(resA, "Variant A (temp=0.1)")
    sB = summarize(resB, "Variant B (temp=0.3)")

    delta = statistics.mean(sA) - statistics.mean(sB)
    print(f"\nΔ(A-B) = {delta:.2f}  → {'A besser' if delta>0 else 'B besser' if delta<0 else 'gleich'}")
