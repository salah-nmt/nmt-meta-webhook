import os
import logging
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

OPENAI_KEY = os.environ["OPENAI_API_KEY"]
VERIFY_TOK = os.environ["META_VERIFY_TOKEN"]
PORT = int(os.environ.get("PORT", 5000))

LEADS = []


@app.route("/webhook/meta", methods=["GET"])
def verificatie():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == VERIFY_TOK):
        return request.args.get("hub.challenge"), 200
    return "Mislukt", 403


@app.route("/webhook/meta", methods=["POST"])
def ontvangen():
    payload = request.get_json(silent=True) or {}
    try:
        entry = payload["entry"][0]["changes"][0]
        if entry["field"] != "leadgen":
            return jsonify({"status": "skip"}), 200
        val = entry["value"]
        velden = {v["name"]: v["values"][0] for v in val.get("field_data", []) if v.get("values")}
        naam = velden.get("full_name") or "Onbekend"
        tel = velden.get("phone_number") or velden.get("phone", "")
        postcode = velden.get("zip_code") or velden.get("postcode", "")
        opmerking = velden.get("opmerking") or velden.get("message", "")
        ad = val.get("ad_name", "")
    except Exception as e:
        log.error("Parse: %s", e)
        return jsonify({"status": "fout"}), 200

    score = 20
    try:
        if 2000 <= int(postcode[:4]) <= 2990:
            score += 30
    except Exception:
        pass
    if tel:
        score += 20
    if opmerking:
        score += 10

    tier = "HOT" if score >= 70 else ("WARM" if score >= 40 else "COLD")
    template = "Dag " + naam + ", bedankt voor uw aanvraag bij NMT Group!"

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": "Bearer " + OPENAI_KEY, "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "NMT Lead Agent. WhatsApp NL 3 zinnen."},
                    {"role": "user", "content": naam + " " + tel + " " + postcode + " " + tier},
                ],
                "max_tokens": 150,
                "temperature": 0.3,
            },
            timeout=20,
        )
        r.raise_for_status()
        template = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.error("OpenAI: %s", e)

    LEADS.insert(0, {
        "tijdstip": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "naam": naam, "telefoon": tel, "postcode": postcode,
        "score": score, "tier": tier, "ad": ad, "whatsapp": template,
    })

    return jsonify({"status": "ok", "tier": tier}), 200


@app.route("/dashboard")
def dashboard():
    hot = sum(1 for l in LEADS if l["tier"] == "HOT")
    warm = sum(1 for l in LEADS if l["tier"] == "WARM")
    cold = sum(1 for l in LEADS if l["tier"] == "COLD")
    rows = ""
    for l in LEADS:
        k = {"HOT": "#ea4335", "WARM": "#fa7b17", "COLD": "#4285f4"}.get(l["tier"], "#888")
        badge = '<span style="background:' + k + ';color:#fff;padding:2px 8px;border-radius:8px">' + l["tier"] + '</span>'
        rows += ('<tr><td>' + l["tijdstip"] + '</td><td><b>' + l["naam"] + '</b></td>'
                 + '<td>' + l["telefoon"] + '</td><td>' + l["postcode"] + '</td>'
                 + '<td>' + str(l["score"]) + '</td><td>' + badge + '</td>'
                 + '<td>' + l["whatsapp"][:60] + '</td></tr>')
    return ('<!DOCTYPE html><html><head><meta charset="UTF-8"><title>NMT</title>'
            '<style>body{font-family:Arial;background:#0f1923;color:#fff;padding:20px}'
            'h1{color:#f97316}table{width:100%;border-collapse:collapse}'
            'th{background:#1a2744;padding:10px;text-align:left;border-bottom:2px solid #f97316}'
            'td{padding:8px;border-bottom:1px solid #1a2744}'
            'a.btn{background:#f97316;color:#fff;padding:8px 16px;border-radius:8px;text-decoration:none;font-weight:bold;margin-right:8px}'
            '</style></head><body>'
            '<h1>NMT Group</h1>'
            '<p><a class="btn" href="/dashboard">Dashboard</a><a class="btn" href="/ads">Ad Engine</a></p>'
            '<p style="color:#888">Leads: ' + str(len(LEADS)) + ' | HOT: ' + str(hot) + ' | WARM: ' + str(warm) + ' | COLD: ' + str(cold) + '</p>'
            '<table><tr><th>Tijd</th><th>Naam</th><th>Tel</th><th>Postcode</th><th>Score</th><th>Tier</th><th>WhatsApp</th></tr>'
            + rows + '</table></body></html>')


@app.route("/ads")
def ads_engine():
    return send_from_directory(".", "ads.html")


@app.route("/health")
def health():
    return jsonify({"ok": True, "leads": len(LEADS)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
