import os, json, logging, requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]
META_VERIFY_TOKEN = os.environ["META_VERIFY_TOKEN"]
PORT              = int(os.environ.get("PORT", 5000))

# In-memory lead opslag (blijft zolang server draait)
LEADS = []

DASHBOARD_HTML = """
<!DOCTYPE html><html lang="nl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NMT Lead Dashboard</title>
<style>
  body{font-family:Arial,sans-serif;background:#0f1923;color:#fff;padding:20px;margin:0}
  h1{color:#f97316;margin-bottom:5px}
  .stats{display:flex;gap:16px;margin:20px 0}
  .stat{background:#1a2744;border-radius:8px;padding:16px 24px;text-align:center}
  .stat .n{font-size:2em;font-weight:bold}
  .hot{color:#ea4335}.warm{color:#fa7b17}.cold{color:#4285f4}
  table{width:100%;border-collapse:collapse;margin-top:16px}
  th{background:#1a2744;padding:10px;text-align:left;font-size:13px;border-bottom:2px solid #f97316}
  td{padding:9px 10px;border-bottom:1px solid #1a2744;font-size:13px}
  tr:hover td{background:#1a2744}
  .badge{padding:3px 10px;border-radius:12px;font-weight:bold;font-size:12px}
  .HOT{background:#ea4335;color:#fff}
  .WARM{background:#fa7b17;color:#fff}
  .COLD{background:#4285f4;color:#fff}
  .template{max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}
  .template:hover{white-space:normal}
</style></head>
<body>
<h1>🔥 NMT Lead Dashboard</h1>
<p style="color:#888">{{ total }} leads — laatste update: {{ now }}</p>
<div class="stats">
  <div class="stat"><div class="n hot">{{ hot }}</div><div>HOT</div></div>
  <div class="stat"><div class="n warm">{{ warm }}</div><div>WARM</div></div>
  <div class="stat"><div class="n cold">{{ cold }}</div><div>COLD</div></div>
</div>
<table>
<thead><tr>
  <th>Tijdstip</th><th>Naam</th><th>Telefoon</th><th>Postcode</th>
  <th>Dienst</th><th>Score</th><th>Tier</th><th>WhatsApp Template</th>
</tr></thead>
<tbody>
{% for l in leads %}
<tr>
  <td>{{ l.tijdstip }}</td>
  <td><strong>{{ l.naam }}</strong></td>
  <td>{{ l.telefoon }}</td>
  <td>{{ l.postcode }}</td>
  <td>{{ l.dienst }}</td>
  <td>{{ l.score }}</td>
  <td><span class="badge {{ l.tier }}">{{ l.tier }}</span></td>
  <td class="template" title="{{ l.whatsapp_template }}">{{ l.whatsapp_template[:80] }}...</td>
</tr>
{% endfor %}
</tbody></table>
</body></html>
"""


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
        naam     = velden.get("full_name") or velden.get("naam", "Onbekend")
        tel      = velden.get("phone_number") or velden.get("phone", "")
        email    = velden.get("email", "")
        postcode = velden.get("zip_code") or velden.get("postcode", "")
        opmerking= velden.get("opmerking") or velden.get("message", "")
        ad       = val.get("ad_name", "")
        dienst   = detecteer_dienst(val.get("field_data", []), ad)
    except Exception as e:
        log.error(f"Parse: {e}")
        return jsonify({"status": "geen leadgen"}), 200

    score = 0
    try:
        if 2000 <= int(postcode[:4]) <= 2990: score += 30
    except Exception: pass
    if tel: score += 20
    if email: score += 10
    if opmerking: score += 10
    if any(w in opmerking.lower() for w in ["dringend","kapot","stuk","snel","urgent"]): score += 10
    score += 20
    tier = "HOT" if score >= 70 else ("WARM" if score >= 40 else "COLD")
    log.info(f"{naam} | {postcode} | {score} ({tier})")

    template = f"Dag {naam}, bedankt voor uw aanvraag bij NMT Group. Een adviseur neemt vandaag contact op."
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model":"gpt-4o-mini","messages":[
                {"role":"system","content":"Je bent NMT Lead Agent. Geef een korte WhatsApp follow-up NL (max 3 zinnen) + wanneer bellen."},
                {"role":"user","content":f"Lead: {naam}, tel:{tel}, pc:{postcode}, dienst:{dienst}, opmerking:{opmerking}, score:{score} {tier}"},
            ],"max_tokens":200,"temperature":0.3},
            timeout=20,
        )
        r.raise_for_status()
        template = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.error(f"OpenAI: {e}")

    lead = {
        "tijdstip": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "naam": naam, "telefoon": tel, "email": email,
        "postcode": postcode, "dienst": dienst,
        "score": score, "tier": tier,
        "opmerking": opmerking, "ad_name": ad,
        "whatsapp_template": template,
    }
    LEADS.insert(0, lead)
    log.info(f"Lead opgeslagen: {naam} {tier}")

    return jsonify({"status": "verwerkt", "lead": naam, "tier": tier}), 200


def detecteer_dienst(field_data, ad_name=""):
    tekst = ad_name.lower() + " " + " ".join(str(v.get("values",[""])[0]).lower() for v in field_data)
    for dienst, kws in {
        "warmtepomp":["warmtepomp","heat pump","wp"],
        "airco":["airco","airconditioning","koeling"],
        "ketelonderhoud":["ketelonderhoud","onderhoud","maintenance"],
        "installatie":["installatie","cv ketel","boiler"],
        "ramen":["ramen","deuren","raam"],
        "platdak":["platdak","dakwerken"],
    }.items():
        if any(kw in tekst for kw in kws): return dienst
    return "ketelonderhoud"


@app.route("/dashboard")
def dashboard():
    hot  = sum(1 for l in LEADS if l["tier"] == "HOT")
    warm = sum(1 for l in LEADS if l["tier"] == "WARM")
    cold = sum(1 for l in LEADS if l["tier"] == "COLD")
    return render_template_string(DASHBOARD_HTML,
        leads=LEADS, total=len(LEADS),
        hot=hot, warm=warm, cold=cold,
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "NMT Meta Webhook", "leads": len(LEADS)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
import os, json, logging, requests
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
META_VERIFY_TOKEN = os.environ["META_VERIFY_TOKEN"]
GOOGLE_SHEET_URL = os.environ.get("GOOGLE_SHEET_URL", "")
PORT = int(os.environ.get("PORT", 5000))


@app.route("/webhook/meta", methods=["GET"])
def verificatie():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == META_VERIFY_TOKEN):
        return request.args.get("hub.challenge"), 200
    return "Mislukt", 403


@app.route("/webhook/meta", methods=["POST"])
def ontvangen():
    payload = request.get_json(silent=True) or {}
    log.info(f"Payload: {json.dumps(payload)[:200]}")
    try:
        entry = payload["entry"][0]["changes"][0]
        if entry["field"] != "leadgen":
            return jsonify({"status": "overgeslagen"}), 200
        val = entry["value"]
        velden = {v["name"]: v["values"][0] for v in val.get("field_data", []) if v.get("values")}
        naam = velden.get("full_name") or velden.get("naam", "Onbekend")
        tel = velden.get("phone_number") or velden.get("phone", "")
        email = velden.get("email", "")
        postcode = velden.get("zip_code") or velden.get("postcode", "")
        opmerking = velden.get("opmerking") or velden.get("message", "")
        ad = val.get("ad_name", "")
        dienst = detecteer_dienst(val.get("field_data", []), ad)
    except Exception as e:
        log.error(f"Parse fout: {e}")
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

    # OpenAI
    whatsapp_template = f"Dag {naam}, bedankt voor uw aanvraag bij NMT Group. Een adviseur neemt vandaag contact op."
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model":"gpt-4o-mini","messages":[
                {"role":"system","content":"Je bent NMT Lead Agent. Geef een korte WhatsApp follow-up NL (max 3 zinnen) + wanneer bellen."},
                {"role":"user","content":f"Lead: {naam}, tel:{tel}, pc:{postcode}, dienst:{dienst}, opmerking:{opmerking}, score:{score} {tier}"},
            ],"max_tokens":200,"temperature":0.3},
            timeout=20,
        )
        resp.raise_for_status()
        whatsapp_template = resp.json()["choices"][0]["message"]["content"]
        log.info(f"AI: {whatsapp_template[:100]}")
    except Exception as e:
        log.error(f"OpenAI fout: {e}")

    # Google Sheet via script URL
    schrijf_naar_sheet(naam, tel, email, postcode, dienst, score, tier, opmerking, ad, whatsapp_template)

    return jsonify({"status": "verwerkt", "lead": naam, "tier": tier}), 200


def schrijf_naar_sheet(naam, tel, email, postcode, dienst, score, tier, opmerking, ad, template):
    if not GOOGLE_SHEET_URL:
        return
    data = {
        "tijdstip": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "naam": naam, "telefoon": tel, "email": email,
        "postcode": postcode, "dienst": dienst,
        "score": score, "tier": tier,
        "opmerking": opmerking, "ad_name": ad,
        "whatsapp_template": template,
    }
    try:
        # Stap 1: GET om redirect URL te achterhalen
        get_resp = requests.get(GOOGLE_SHEET_URL, allow_redirects=True, timeout=10)
        final_url = get_resp.url  # URL na redirect

        # Stap 2: POST direct naar de uiteindelijke URL
        post_resp = requests.post(
            final_url,
            json=data,
            headers={"Content-Type": "application/json"},
            allow_redirects=False,
            timeout=15,
        )
        log.info(f"Sheet GET redirect: {final_url[:80]}")
        log.info(f"Sheet POST status: {post_resp.status_code} | {post_resp.text[:100]}")
    except Exception as e:
        log.error(f"Sheet fout: {e}")


def detecteer_dienst(field_data, ad_name=""):
    tekst = ad_name.lower() + " " + " ".join(str(v.get("values",[""])[0]).lower() for v in field_data)
    for dienst, kws in {
        "warmtepomp":["warmtepomp","heat pump","wp"],
        "airco":["airco","airconditioning","koeling"],
        "ketelonderhoud":["ketelonderhoud","onderhoud","maintenance"],
        "installatie":["installatie","cv ketel","boiler"],
        "ramen":["ramen","deuren","raam"],
        "platdak":["platdak","dakwerken"],
    }.items():
        if any(kw in tekst for kw in kws): return dienst
    return "ketelonderhoud"


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "NMT Meta Webhook"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
import os, json, logging, requests
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
META_VERIFY_TOKEN = os.environ["META_VERIFY_TOKEN"]
GOOGLE_SHEET_URL = os.environ.get("GOOGLE_SHEET_URL", "")
PORT = int(os.environ.get("PORT", 5000))
WERKGEBIED = set(range(2000, 2991))


@app.route("/webhook/meta", methods=["GET"])
def verificatie():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == META_VERIFY_TOKEN):
        return request.args.get("hub.challenge"), 200
    return "Mislukt", 403


@app.route("/webhook/meta", methods=["POST"])
def ontvangen():
    payload = request.get_json(silent=True) or {}
    log.info(f"Payload: {json.dumps(payload)[:200]}")
    try:
        entry = payload["entry"][0]["changes"][0]
        if entry["field"] != "leadgen":
            return jsonify({"status": "overgeslagen"}), 200
        val = entry["value"]
        velden = {v["name"]: v["values"][0] for v in val.get("field_data", []) if v.get("values")}
        naam = velden.get("full_name") or velden.get("naam", "Onbekend")
        tel = velden.get("phone_number") or velden.get("phone", "")
        email = velden.get("email", "")
        postcode = velden.get("zip_code") or velden.get("postcode", "")
        opmerking = velden.get("opmerking") or velden.get("message", "")
        ad = val.get("ad_name", "")
        dienst = detecteer_dienst(val.get("field_data", []), ad)
    except Exception as e:
        log.error(f"Parse fout: {e}")
        return jsonify({"status": "geen leadgen"}), 200

    # Score berekening
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

    # OpenAI analyse
    whatsapp_template = f"Dag {naam}, bedankt voor uw aanvraag bij NMT Group. Een adviseur neemt vandaag contact op."
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Je bent NMT Lead Agent voor NMT Group Hoboken. Warmtepompen, airco, ketels, ramen, dak. Geef een korte WhatsApp follow-up in NL (max 3 zinnen) en zeg wanneer bellen."},
                    {"role": "user", "content": f"Lead: {naam}, tel: {tel}, postcode: {postcode}, dienst: {dienst}, opmerking: {opmerking}, score: {score} {tier}"},
                ],
                "max_tokens": 200,
                "temperature": 0.3,
            },
            timeout=20,
        )
        resp.raise_for_status()
        whatsapp_template = resp.json()["choices"][0]["message"]["content"]
        log.info(f"AI template: {whatsapp_template[:100]}")
    except Exception as e:
        log.error(f"OpenAI fout: {e}")

    # Google Sheet — gebruik form-encoded voor redirect correctheid
    if GOOGLE_SHEET_URL:
        try:
            sheet_data = {
                "tijdstip": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                "naam": naam,
                "telefoon": tel,
                "email": email,
                "postcode": postcode,
                "dienst": dienst,
                "score": score,
                "tier": tier,
                "opmerking": opmerking,
                "ad_name": ad,
                "whatsapp_template": whatsapp_template,
            }
            # Apps Script redirect: stuur als string-encoded JSON in form
            sheet_resp = requests.post(
                GOOGLE_SHEET_URL,
                data=json.dumps(sheet_data),
                headers={"Content-Type": "application/json"},
                allow_redirects=True,
                timeout=15,
            )
            log.info(f"Sheet response: {sheet_resp.status_code} | {sheet_resp.text[:100]}")
        except Exception as e:
            log.error(f"Sheet fout: {e}")

    return jsonify({"status": "verwerkt", "lead": naam, "tier": tier}), 200


def detecteer_dienst(field_data, ad_name=""):
    tekst = ad_name.lower() + " " + " ".join(str(v.get("values",[""])[0]).lower() for v in field_data)
    diensten = {
        "warmtepomp": ["warmtepomp","heat pump","wp"],
        "airco": ["airco","airconditioning","koeling"],
        "ketelonderhoud": ["ketelonderhoud","onderhoud","maintenance"],
        "installatie": ["installatie","cv ketel","boiler"],
        "ramen": ["ramen","deuren","raam"],
        "platdak": ["platdak","dakwerken"],
    }
    for dienst, kws in diensten.items():
        if any(kw in tekst for kw in kws): return dienst
    return "ketelonderhoud"


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "NMT Meta Webhook"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
import os, json, logging, requests
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
META_VERIFY_TOKEN = os.environ["META_VERIFY_TOKEN"]
GOOGLE_SHEET_URL = os.environ.get("GOOGLE_SHEET_URL", "")
PORT = int(os.environ.get("PORT", 5000))
WERKGEBIED = set(range(2000, 2991))


@app.route("/webhook/meta", methods=["GET"])
def verificatie():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == META_VERIFY_TOKEN):
        log.info("Webhook verificatie OK")
        return request.args.get("hub.challenge"), 200
    return "Mislukt", 403


@app.route("/webhook/meta", methods=["POST"])
def ontvangen():
    payload = request.get_json(silent=True) or {}
    log.info(f"Lead ontvangen: {json.dumps(payload)[:200]}")
    try:
        entry = payload["entry"][0]["changes"][0]
        if entry["field"] != "leadgen":
            return jsonify({"status": "overgeslagen"}), 200
        val = entry["value"]
        velden = {v["name"]: v["values"][0] for v in val.get("field_data", []) if v.get("values")}
        naam = velden.get("full_name") or velden.get("naam", "Onbekend")
        tel = velden.get("phone_number") or velden.get("phone", "")
        email = velden.get("email", "")
        postcode = velden.get("zip_code") or velden.get("postcode", "")
        opmerking = velden.get("opmerking") or velden.get("message", "")
        ad = val.get("ad_name", "")
        dienst = detecteer_dienst(val.get("field_data", []), ad)
    except Exception as e:
        log.error(f"Parse fout: {e}")
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

    # OpenAI analyse
    whatsapp_template = ""
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Je bent NMT Lead Agent voor NMT Group Hoboken. Renovatiebedrijf: warmtepompen, airco, ketels, ramen, dak. Geef: 1) HOT/WARM/COLD met uitleg 2) WhatsApp template in NL 3) wanneer bellen. Max 200 woorden."},
                    {"role": "user", "content": f"Lead: {naam}, tel: {tel}, postcode: {postcode}, dienst: {dienst}, opmerking: {opmerking}, pre-score: {score} {tier}"},
                ],
                "max_tokens": 300,
                "temperature": 0.3,
            },
            timeout=25,
        )
        resp.raise_for_status()
        whatsapp_template = resp.json()["choices"][0]["message"]["content"]
        log.info(f"AI:\n{whatsapp_template[:200]}")
    except Exception as e:
        log.error(f"OpenAI fout: {e}")
        whatsapp_template = f"Dag {naam}, bedankt voor uw aanvraag bij NMT Group. Een adviseur neemt vandaag contact op."

    # Google Sheet logging
    if GOOGLE_SHEET_URL:
        try:
            requests.post(GOOGLE_SHEET_URL, json={
                "tijdstip": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                "naam": naam,
                "telefoon": tel,
                "email": email,
                "postcode": postcode,
                "dienst": dienst,
                "score": score,
                "tier": tier,
                "opmerking": opmerking,
                "ad_name": ad,
                "whatsapp_template": whatsapp_template,
            }, timeout=10)
            log.info(f"Lead gelogd in Google Sheet")
        except Exception as e:
            log.error(f"Sheet fout: {e}")

    return jsonify({"status": "verwerkt", "lead": naam, "tier": tier}), 200


def detecteer_dienst(field_data, ad_name=""):
    tekst = ad_name.lower() + " " + " ".join(str(v.get("values",[""])[0]).lower() for v in field_data)
    diensten = {
        "warmtepomp": ["warmtepomp","heat pump","wp"],
        "airco": ["airco","airconditioning","koeling"],
        "ketelonderhoud": ["ketelonderhoud","onderhoud","maintenance"],
        "installatie": ["installatie","cv ketel","boiler"],
        "ramen": ["ramen","deuren","raam"],
        "platdak": ["platdak","dakwerken"],
    }
    for dienst, kws in diensten.items():
        if any(kw in tekst for kw in kws): return dienst
    return "ketelonderhoud"


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "NMT Meta Webhook"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
import os, json, logging, requests
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
META_VERIFY_TOKEN = os.environ["META_VERIFY_TOKEN"]
PORT = int(os.environ.get("PORT", 5000))


@app.route("/webhook/meta", methods=["GET"])
def verificatie():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == META_VERIFY_TOKEN):
        log.info("Webhook verificatie OK")
        return request.args.get("hub.challenge"), 200
    return "Mislukt", 403


@app.route("/webhook/meta", methods=["POST"])
def ontvangen():
    payload = request.get_json(silent=True) or {}
    log.info(f"Lead ontvangen: {json.dumps(payload)[:200]}")
    try:
        entry = payload["entry"][0]["changes"][0]
        if entry["field"] != "leadgen":
            return jsonify({"status": "overgeslagen"}), 200
        val = entry["value"]
        velden = {v["name"]: v["values"][0] for v in val.get("field_data", []) if v.get("values")}
        naam = velden.get("full_name") or velden.get("naam", "Onbekend")
        tel = velden.get("phone_number") or velden.get("phone", "")
        postcode = velden.get("zip_code") or velden.get("postcode", "")
        opmerking = velden.get("opmerking") or velden.get("message", "")
        ad = val.get("ad_name", "")
    except Exception as e:
        log.error(f"Parse fout: {e}")
        return jsonify({"status": "geen leadgen"}), 200

    score = 0
    try:
        if 2000 <= int(postcode[:4]) <= 2990:
            score += 30
    except Exception:
        pass
    if tel: score += 20
    if opmerking: score += 10
    if any(w in opmerking.lower() for w in ["dringend","kapot","stuk","snel","urgent"]):
        score += 10
    score += 20
    tier = "HOT" if score >= 70 else ("WARM" if score >= 40 else "COLD")
    log.info(f"{naam} | {postcode} | {score} ({tier})")

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Je bent NMT Lead Agent voor NMT Group Hoboken. Warmtepompen, airco, ketels, ramen, dak. Geef: 1) HOT/WARM/COLD met uitleg 2) WhatsApp template NL 3) wanneer bellen. Max 200 woorden."},
                    {"role": "user", "content": f"Lead: {naam}, tel: {tel}, postcode: {postcode}, opmerking: {opmerking}, ad: {ad}, pre-score: {score} {tier}"},
                ],
                "max_tokens": 300,
                "temperature": 0.3,
            },
            timeout=25,
        )
        resp.raise_for_status()
        antwoord = resp.json()["choices"][0]["message"]["content"]
        log.info(f"AI:\n{antwoord}")
        return jsonify({"status": "verwerkt", "lead": naam, "tier": tier}), 200
    except Exception as e:
        log.error(f"OpenAI fout: {e}")
        return jsonify({"status": "fout", "error": str(e)}), 502


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "NMT Meta Webhook"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
