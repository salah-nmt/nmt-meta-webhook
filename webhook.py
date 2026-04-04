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
