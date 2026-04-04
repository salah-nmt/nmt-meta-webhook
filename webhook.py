import os, json, logging
from datetime import datetime
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]
NMT_WORKFLOW_ID   = os.environ.get("NMT_WORKFLOW_ID", "wf_69ce1e50699481908d2c7867858061cf04a2def3ed9c7474")
META_VERIFY_TOKEN = os.environ["META_VERIFY_TOKEN"]
META_APP_SECRET   = os.environ.get("META_APP_SECRET", "")
PORT              = int(os.environ.get("PORT", 5000))
WERKGEBIED        = set(range(2000, 2991))

DIENST_KEYWORDS = {
    "warmtepomp": ["warmtepomp", "heat pump"],
    "airco": ["airco", "airconditioning"],
    "ketelonderhoud": ["ketelonderhoud", "onderhoud"],
    "installatie": ["installatie", "cv ketel", "boiler"],
    "ramen": ["ramen", "deuren"],
    "platdak": ["platdak", "dakwerken"],
}

def detecteer_dienst(field_data, ad_name=""):
    tekst = ad_name.lower() + " " + " ".join(str(v.get("values",[""])[0]).lower() for v in field_data)
    for dienst, kws in DIENST_KEYWORDS.items():
        if any(kw in tekst for kw in kws): return dienst
    return "ketelonderhoud"

def parseer_lead(payload):
    try:
        val = payload["entry"][0]["changes"][0]["value"]
        velden = {v["name"]: v["values"][0] for v in val.get("field_data",[]) if v.get("values")}
        return {
            "naam": velden.get("full_name") or velden.get("naam","Onbekend"),
            "email": velden.get("email",""),
            "telefoon": velden.get("phone_number") or velden.get("phone",""),
            "postcode": velden.get("zip_code") or velden.get("postcode",""),
            "opmerking": velden.get("opmerking") or velden.get("message",""),
            "dienst": detecteer_dienst(val.get("field_data",[]), val.get("ad_name","")),
            "ad_name": val.get("ad_name",""),
        }
    except Exception as e:
        log.error(f"Parse fout: {e}"); return None

def bereken_score(lead):
    score = 0
    try:
        if int(lead["postcode"].replace(" ","")[:4]) in WERKGEBIED: score += 30
    except: pass
    if lead["telefoon"]: score += 20
    if lead["email"]: score += 10
    if lead["opmerking"]: score += 10
    if lead["dienst"] in ("warmtepomp","ramen"): score += 5
    if any(w in lead["opmerking"].lower() for w in ["dringend","kapot","stuk","snel"]): score += 10
    if lead["dienst"] in ("ketelonderhoud","installatie","airco","warmtepomp"): score += 20
    tier = "HOT" if score>=70 else ("WARM" if score>=40 else "COLD")
    return {"pre_score": score, "tier": tier}

def stuur_naar_workflow(lead, score):
    msg = (f"Nieuwe Meta Lead: {lead['naam']} | Tel: {lead['telefoon']} | Email: {lead['email']} | "
           f"Postcode: {lead['postcode']} | Dienst: {lead['dienst']} | Opmerking: {lead['opmerking'] or 'geen'} | "
           f"Score: {score['pre_score']}/100 - {score['tier']}\n\nGeef volledige scoring analyse en WhatsApp follow-up template.")
    try:
        r = requests.post("https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json", "OpenAI-Beta": "responses=v1"},
            json={"workflow_id": NMT_WORKFLOW_ID, "input": msg, "stream": False}, timeout=30)
        r.raise_for_status()
        log.info(f"Verwerkt: {lead['naam']} - {score['tier']}")
        return True
    except Exception as e:
        log.error(f"Fout: {e}"); return False

@app.route("/webhook/meta", methods=["GET"])
def verificatie():
    if (request.args.get("hub.mode")=="subscribe" and
        request.args.get("hub.verify_token")==META_VERIFY_TOKEN):
        return request.args.get("hub.challenge"), 200
    return "Mislukt", 403

@app.route("/webhook/meta", methods=["POST"])
def ontvangen():
    payload = request.get_json(silent=True)
    if not payload: return jsonify({"error": "Geen payload"}), 400
    lead = parseer_lead(payload)
    if not lead: return jsonify({"error": "Parse fout"}), 422
    score = bereken_score(lead)
    log.info(f"{lead['naam']} | {lead['dienst']} | {score['pre_score']} ({score['tier']})")
    if stuur_naar_workflow(lead, score):
        return jsonify({"status":"verwerkt","lead":lead["naam"],"tier":score["tier"]}), 200
    return jsonify({"status":"fout"}), 502

@app.route("/health")
def health():
    return jsonify({"status":"ok","service":"NMT Meta Webhook"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
