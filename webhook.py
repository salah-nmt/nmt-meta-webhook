import os, json, logging, requests
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]
META_VERIFY_TOKEN = os.environ["META_VERIFY_TOKEN"]
PORT              = int(os.environ.get("PORT", 5000))
LEADS = []


@app.route("/webhook/meta", methods=["GET"])
def verificatie():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == META_VERIFY_TOKEN):
        return request.args.get("hub.challenge"), 200
    return "Mislukt", 403


@app.route("/webhook/meta", methods=["POST"])
def ontvangen():
    payload = request.get_json(silent=True) or {}
    try:
        entry = payload["entry"][0]["changes"][0]
        if entry["field"] != "leadgen":
            return jsonify({"status": "overgeslagen"}), 200
        val = entry["value"]
        velden = {v["name"]: v["values"][0] for v in val.get("field_data", []) if v.get("values")}
        naam      = velden.get("full_name") or "Onbekend"
        tel       = velden.get("phone_number") or velden.get("phone", "")
        email     = velden.get("email", "")
        postcode  = velden.get("zip_code") or velden.get("postcode", "")
        opmerking = velden.get("opmerking") or velden.get("message", "")
        ad        = val.get("ad_name", "")
        dienst    = detecteer_dienst(val.get("field_data", []), ad)
    except Exception as e:
        log.error(f"Parse: {e}")
        return jsonify({"status": "geen leadgen"}), 200

    score = 0
    try:
        if 2000 <= int(postcode[:4]) <= 2990:
            score += 30
    except Exception:
        pass
    if tel: score += 20
    if email: score += 10
    if opmerking: score += 10
    if any(w in opmerking.lower() for w in ["dringend","kapot","stuk","snel","urgent"]):
        score += 10
    score += 20
    tier = "HOT" if score >= 70 else ("WARM" if score >= 40 else "COLD")
    log.info(f"{naam} | {postcode} | {score} ({tier})")

    template = f"Dag {naam}, bedankt voor uw aanvraag bij NMT Group. Een adviseur neemt vandaag contact op."
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "messages": [
                {"role": "system", "content": "NMT Lead Agent. Geef WhatsApp follow-up NL (3 zinnen) + wanneer bellen."},
                {"role": "user", "content": f"Lead: {naam}, tel:{tel}, pc:{postcode}, dienst:{dienst}, score:{score} {tier}"},
            ], "max_tokens": 200, "temperature": 0.3},
            timeout=20,
        )
        r.raise_for_status()
        template = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.error(f"OpenAI: {e}")

    LEADS.insert(0, {
        "tijdstip": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "naam": naam, "telefoon": tel, "email": email,
        "postcode": postcode, "dienst": dienst,
        "score": score, "tier": tier,
        "opmerking": opmerking, "ad_name": ad,
        "whatsapp_template": template,
    })
    return jsonify({"status": "verwerkt", "lead": naam, "tier": tier}), 200


def detecteer_dienst(field_data, ad_name=""):
    tekst = ad_name.lower() + " " + " ".join(str(v.get("values", [""])[0]).lower() for v in field_data)
    for dienst, kws in {
        "warmtepomp": ["warmtepomp", "heat pump", "wp"],
        "airco": ["airco", "airconditioning", "koeling"],
        "ketelonderhoud": ["ketelonderhoud", "onderhoud"],
        "ramen": ["ramen", "deuren", "raam"],
        "platdak": ["platdak", "dakwerken"],
    }.items():
        if any(kw in tekst for kw in kws):
            return dienst
    return "ketelonderhoud"


@app.route("/dashboard")
def dashboard():
    hot  = sum(1 for l in LEADS if l["tier"] == "HOT")
    warm = sum(1 for l in LEADS if l["tier"] == "WARM")
    cold = sum(1 for l in LEADS if l["tier"] == "COLD")
    rows = ""
    for l in LEADS:
        k = {"HOT": "#ea4335", "WARM": "#fa7b17", "COLD": "#4285f4"}.get(l["tier"], "#888")
        t = str(l.get("whatsapp_template", ""))[:80]
        rows += f"<tr><td>{l['tijdstip']}</td><td><b>{l['naam']}</b></td><td>{l['telefoon']}</td><td>{l['postcode']}</td><td>{l['score']}</td><td style='background:{k};color:#fff;padding:3px 8px;border-radius:10px'>{l['tier']}</td><td>{t}...</td></tr>"
    return ("<!DOCTYPE html><html><head><meta charset='UTF-8'><title>NMT Dashboard</title>"
        "<style>body{font-family:Arial;background:#0f1923;color:#fff;padding:20px}"
        "h1{color:#f97316}table{width:100%;border-collapse:collapse}"
        "th{background:#1a2744;padding:10px;text-align:left;border-bottom:2px solid #f97316}"
        "td{padding:8px;border-bottom:1px solid #1a2744}tr:hover td{background:#1a2744}"
        ".s{display:flex;gap:16px;margin:16px 0}.b{background:#1a2744;padding:16px 24px;border-radius:8px;text-align:center}"
        ".n{font-size:2em;font-weight:bold}.hot{color:#ea4335}.warm{color:#fa7b17}.cold{color:#4285f4}"
        "</style></head><body>"
        f"<h1>NMT Lead Dashboard</h1><p style='color:#888'>{len(LEADS)} leads</p>"
        f"<div class='s'><div class='b'><div class='n hot'>{hot}</div>HOT</div>"
        f"<div class='b'><div class='n warm'>{warm}</div>WARM</div>"
        f"<div class='b'><div class='n cold'>{cold}</div>COLD</div></div>"
        "<table><tr><th>Tijdstip</th><th>Naam</th><th>Telefoon</th><th>Postcode</th>"
        f"<th>Score</th><th>Tier</th><th>WhatsApp</th></tr>{rows}</table></body></html>")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "NMT Meta Webhook", "leads": len(LEADS)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
