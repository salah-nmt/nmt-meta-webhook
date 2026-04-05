import os
import logging
import requests
from datetime import datetime
from flask import Flask, request, jsonify
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
        badge = "<span style=\"background:" + k + ";color:#fff;padding:2px 8px;border-radius:8px\">" + l["tier"] + "</span>"
        rows += ("<tr><td>" + l["tijdstip"] + "</td><td><b>" + l["naam"] + "</b></td>"
                 + "<td>" + l["telefoon"] + "</td><td>" + l["postcode"] + "</td>"
                 + "<td>" + str(l["score"]) + "</td><td>" + badge + "</td>"
                 + "<td>" + l["whatsapp"][:60] + "</td></tr>")
    return ("<!DOCTYPE html><html><head><meta charset=\"UTF-8\"><title>NMT</title>"
            "<style>body{font-family:Arial;background:#0f1923;color:#fff;padding:20px}"
            "h1{color:#f97316}table{width:100%;border-collapse:collapse}"
            "th{background:#1a2744;padding:10px;text-align:left;border-bottom:2px solid #f97316}"
            "td{padding:8px;border-bottom:1px solid #1a2744}"
            "a.btn{background:#f97316;color:#fff;padding:8px 16px;border-radius:8px;text-decoration:none;font-weight:bold;margin-right:8px}"
            "</style></head><body>"
            "<h1>NMT Group</h1>"
            "<p><a class=\"btn\" href=\"/dashboard\">&#128202; Dashboard</a>"
            "<a class=\"btn\" href=\"/ads\">&#127912; Ad Engine</a></p>"
            "<p style=\"color:#888\">Leads: " + str(len(LEADS)) + " | HOT: " + str(hot) + " | WARM: " + str(warm) + " | COLD: " + str(cold) + "</p>"
            "<table><tr><th>Tijd</th><th>Naam</th><th>Tel</th><th>Postcode</th><th>Score</th><th>Tier</th><th>WhatsApp</th></tr>"
            + rows + "</table></body></html>")


@app.route("/ads")
def ads_engine():
    return ADS_HTML


@app.route("/health")
def health():
    return jsonify({"ok": True, "leads": len(LEADS)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)


ADS_HTML = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NMT Ad Creative Engine</title>
<style>
:root{--bg:#0f1923;--card:#1a2744;--card2:#162035;--orange:#f97316;--orange2:#ea6c0a;--text:#fff;--muted:#94a3b8;--border:#1e3a5f;--green:#22c55e;--red:#ef4444;--yellow:#facc15}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--text);font-family:'Segoe UI',Arial,sans-serif;min-height:100vh}
nav{background:var(--card);border-bottom:2px solid var(--orange);display:flex;align-items:center;padding:0 16px;height:56px;gap:4px;position:sticky;top:0;z-index:100;flex-wrap:wrap}
.nav-logo{font-size:1.1em;font-weight:800;color:var(--orange);margin-right:16px}.nav-btn{background:none;border:none;color:var(--muted);padding:7px 12px;border-radius:8px;cursor:pointer;font-size:0.85em;transition:all 0.2s}
.nav-btn:hover,.nav-btn.active{background:var(--orange);color:#fff}.nav-spacer{flex:1}
.api-badge{font-size:0.72em;padding:4px 10px;border-radius:20px;cursor:pointer}
.api-ok{background:#14532d;color:var(--green)}.api-missing{background:#7f1d1d;color:var(--red)}
.page{display:none;padding:20px;max-width:1400px;margin:0 auto}.page.active{display:block}
.card{background:var(--card);border-radius:12px;padding:18px;border:1px solid var(--border);margin-bottom:12px}
h1{font-size:1.5em;color:var(--orange);margin-bottom:4px}h2{font-size:1.1em;margin-bottom:10px}h3{font-size:0.95em;margin-bottom:6px;color:var(--orange)}
.sub{color:var(--muted);font-size:0.88em;margin-bottom:16px}
label{display:block;font-size:0.82em;color:var(--muted);margin-bottom:5px;margin-top:12px}
input,select,textarea{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:9px 12px;font-size:0.9em;outline:none;transition:border 0.2s;font-family:inherit}
input:focus,select:focus,textarea:focus{border-color:var(--orange)}textarea{resize:vertical}select option{background:var(--card)}
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 18px;border-radius:8px;border:none;cursor:pointer;font-size:0.9em;font-weight:600;transition:all 0.2s}
.btn-primary{background:var(--orange);color:#fff}.btn-primary:hover{background:var(--orange2)}.btn-primary:disabled{opacity:0.5;cursor:not-allowed}
.btn-ghost{background:var(--card2);color:var(--text);border:1px solid var(--border)}.btn-ghost:hover{border-color:var(--orange);color:var(--orange)}
.btn-danger{background:#7f1d1d;color:#fca5a5}.btn-sm{padding:5px 10px;font-size:0.78em}.btn-green{background:#14532d;color:var(--green)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.variants-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px;margin-top:16px}
.ad-card{background:var(--card2);border-radius:12px;overflow:hidden;border:2px solid var(--border);transition:border 0.2s}.ad-card:hover{border-color:var(--orange)}
.ad-preview{background:linear-gradient(135deg,#0f1923 0%,#1a2744 100%);aspect-ratio:4/5;display:flex;flex-direction:column;justify-content:space-between;padding:16px;position:relative}
.ad-badge{background:var(--orange);color:#fff;font-size:0.6em;font-weight:800;padding:3px 8px;border-radius:20px;position:absolute;top:10px;right:10px}
.ad-service-tag{background:rgba(249,115,22,0.15);color:var(--orange);font-size:0.65em;padding:2px 6px;border-radius:6px;border:1px solid rgba(249,115,22,0.3);width:fit-content;margin-bottom:6px}
.ad-headline{font-size:0.95em;font-weight:800;line-height:1.3;color:#fff}
.ad-subtext{font-size:0.68em;color:var(--muted);margin-top:6px;line-height:1.4}
.ad-social-proof{font-size:0.63em;color:var(--green);background:rgba(34,197,94,0.1);padding:3px 6px;border-radius:6px;margin-top:6px}
.ad-fomo{font-size:0.63em;color:var(--yellow);background:rgba(250,204,21,0.1);padding:3px 6px;border-radius:6px;margin-top:3px}
.ad-cta-preview{background:var(--orange);color:#fff;text-align:center;padding:8px;font-weight:800;font-size:0.75em;border-radius:8px;margin-top:10px}
.ad-footer{font-size:0.6em;color:var(--muted);text-align:center;margin-top:6px}
.ad-meta{padding:10px}.ad-variant-label{font-size:0.72em;color:var(--muted);margin-bottom:5px}
.ad-actions{display:flex;gap:5px;flex-wrap:wrap}
.quality-score{font-size:2.5em;font-weight:900}.score-ok{color:var(--green)}.score-warn{color:var(--yellow)}.score-bad{color:var(--red)}
.issue-item{display:flex;align-items:flex-start;gap:8px;padding:8px;background:var(--bg);border-radius:8px;margin-bottom:6px}
.issue-text{font-size:0.85em}.issue-fix{font-size:0.75em;color:var(--orange);margin-top:2px}
.vault-item{background:var(--card2);border-radius:10px;padding:12px;border:1px solid var(--border);margin-bottom:8px}
.vault-tags{display:flex;gap:5px;flex-wrap:wrap;margin-top:6px}
.tag{font-size:0.68em;padding:2px 7px;border-radius:12px;background:rgba(249,115,22,0.15);color:var(--orange);border:1px solid rgba(249,115,22,0.3)}
.asset-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin-top:12px}
.asset-item{background:var(--card2);border-radius:10px;overflow:hidden;border:2px solid var(--border);cursor:pointer;transition:border 0.2s}.asset-item:hover{border-color:var(--orange)}
.asset-thumb{width:100%;height:90px;display:flex;align-items:center;justify-content:center;font-size:2em;background:var(--bg)}
.asset-name{padding:6px;font-size:0.73em;color:var(--muted);overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.asset-type{font-size:0.62em;color:var(--orange);padding:0 6px 6px}
.spinner{display:inline-block;width:18px;height:18px;border:3px solid rgba(249,115,22,0.3);border-top-color:var(--orange);border-radius:50%;animation:spin 0.8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-msg{color:var(--muted);font-size:0.88em;display:flex;align-items:center;gap:8px;padding:16px}
.alert{padding:10px 14px;border-radius:8px;font-size:0.88em;margin-bottom:14px}
.alert-orange{background:rgba(249,115,22,0.1);border:1px solid rgba(249,115,22,0.3);color:#fed7aa}
.alert-red{background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);color:#fca5a5}
.alert-green{background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);color:#86efac}
.divider{height:1px;background:var(--border);margin:16px 0}
.flex{display:flex;align-items:center;gap:8px}.ml-auto{margin-left:auto}.gap{margin-top:12px}
.ratio-badge{background:#1e3a5f;color:#93c5fd;font-size:0.72em;padding:3px 7px;border-radius:6px;font-weight:700}
pre{white-space:pre-wrap;font-family:inherit}
@media(max-width:768px){.grid2{grid-template-columns:1fr}.variants-grid{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<nav>
  <div class="nav-logo">&#127919; NMT Ads</div>
  <button class="nav-btn active" onclick="showPage('generator',this)">&#10024; Generator</button>
  <button class="nav-btn" onclick="showPage('checker',this)">&#128269; Checker</button>
  <button class="nav-btn" onclick="showPage('vault',this)">&#127942; Winning Ads</button>
  <button class="nav-btn" onclick="showPage('assets',this)">&#128444;&#65039; Assets</button>
  <button class="nav-btn" onclick="showPage('settings',this)">&#9881;&#65039; Instellingen</button>
  <div class="nav-spacer"></div>
  <span id="api-badge" class="api-badge api-missing" onclick="showPage('settings',document.querySelectorAll('.nav-btn')[4])">&#9888;&#65039; API Key vereist</span>
</nav>

<div id="page-generator" class="page active">
  <h1>&#10024; Ad Creative Generator</h1>
  <p class="sub">Claude genereert 4-5 unieke varianten &middot; Altijd 1080x1350 &middot; Meta Ads geoptimaliseerd &middot; Winning ad formule</p>
  <div id="no-api-banner" class="alert alert-red" style="display:none">&#9888;&#65039; Geen Anthropic API key. Ga naar <strong>&#9881;&#65039; Instellingen</strong> en voer je key in om Claude te activeren.</div>
  <div class="grid2">
    <div class="card">
      <h2>&#127919; Concept Instellen</h2>
      <label>Service</label>
      <select id="gen-service"><option>Warmtepomp</option><option>Airco</option><option>Ketelonderhoud</option><option>Ramen &amp; Deuren</option><option>Platdak</option></select>
      <label>Concept / Kernboodschap</label>
      <textarea id="gen-concept" rows="3" placeholder="bv. Bespaar tot 1500 euro per jaar op energiefactuur met warmtepomp inclusief premie-aanvraag"></textarea>
      <label>Doelgroep</label>
      <input id="gen-target" value="Huiseigenaren provincie Antwerpen, 30-65 jaar"/>
      <label>Aanbod / USP</label>
      <textarea id="gen-usp" rows="2" placeholder="bv. Gratis offerte, installatie binnen 2 weken, 2000 euro premie mogelijk"></textarea>
      <label>Extra instructies (optioneel)</label>
      <textarea id="gen-extra" rows="2" placeholder="bv. Meer urgentie, focus op prijs, voeg seizoensreferentie toe..."></textarea>
      <div class="gap"></div>
      <div class="flex"><span class="ratio-badge">&#128208; 1080x1350</span><span class="ratio-badge">&#127463;&#127466; Vlaams NL</span><span class="ratio-badge">&#128241; Meta Ads</span></div>
      <div class="gap"></div>
      <button class="btn btn-primary" id="gen-btn" onclick="generateAds()" style="width:100%">&#10024; Genereer 4-5 Varianten</button>
    </div>
    <div class="card">
      <h2>&#127942; Winning Formule</h2>
      <p style="font-size:0.83em;color:var(--muted);line-height:1.9">
        <strong>1. &#127907; Hook</strong> &mdash; Pakkend, specifiek getal of vraag<br>
        <strong>2. &#128172; Body</strong> &mdash; Probleem &rarr; Oplossing &rarr; Bewijs<br>
        <strong>3. &#11088; Social proof</strong> &mdash; 9/10 klanten TrustLocal<br>
        <strong>4. &#9889; FOMO</strong> &mdash; OP=OP / beperkte plaatsen<br>
        <strong>5. &#128222; CTA</strong> &mdash; Gratis offerte, bel nu<br>
        <strong>6. &#9989; Garantie</strong> &mdash; Geen verplichtingen<br><br>
        <strong>5 Varianten per concept:</strong><br>
        A &mdash; Prijs &amp; Besparing &middot; B &mdash; Urgentie/FOMO<br>
        C &mdash; Social Proof &middot; D &mdash; Pijn/Probleem &middot; E &mdash; Premie
      </p>
    </div>
  </div>
  <div id="gen-loading" style="display:none"><div class="loading-msg"><div class="spinner"></div>Claude genereert 5 unieke ad varianten...</div></div>
  <div id="variants-output" style="display:none;margin-top:20px">
    <div class="flex">
      <h2>&#128203; Gegenereerde Varianten</h2>
      <div class="flex ml-auto">
        <button class="btn btn-ghost btn-sm" onclick="copyAllVariants()">&#128203; Alles kopi&euml;ren</button>
        <button class="btn btn-green btn-sm" onclick="saveToVault()">&#127942; Bewaar in Vault</button>
      </div>
    </div>
    <div id="variants-grid" class="variants-grid"></div>
  </div>
</div>

<div id="page-checker" class="page">
  <h1>&#128269; Ad Quality Checker</h1>
  <p class="sub">Claude analyseert spelling, CTA, social proof, dubbele elementen &mdash; en geeft automatisch een gecorrigeerde versie</p>
  <div class="grid2">
    <div class="card">
      <h2>&#128221; Ad tekst invoeren</h2>
      <label>Plak volledige ad tekst</label>
      <textarea id="checker-input" rows="12" placeholder="Plak hier je volledige ad tekst (headline + body + CTA + social proof)..."></textarea>
      <label>Service context</label>
      <select id="checker-service"><option>Warmtepomp</option><option>Airco</option><option>Ketelonderhoud</option><option>Ramen &amp; Deuren</option><option>Platdak</option></select>
      <div class="gap"></div>
      <button class="btn btn-primary" onclick="runChecker()" style="width:100%">&#128269; Analyseer &amp; Fix automatisch</button>
    </div>
    <div id="checker-results" class="card" style="display:none">
      <div class="flex"><h2>&#128202; Analyse Resultaat</h2><div id="checker-score" class="quality-score ml-auto"></div></div>
      <div id="checker-issues"></div>
      <div class="divider"></div>
      <h3>&#9989; Auto-fix Versie</h3>
      <div id="checker-fixed" style="background:var(--bg);border-radius:8px;padding:12px;font-size:0.85em;line-height:1.7;white-space:pre-wrap;max-height:280px;overflow-y:auto"></div>
      <div class="gap"></div>
      <button class="btn btn-primary btn-sm" onclick="copyFixed()">&#128203; Kopieer gecorrigeerde versie</button>
    </div>
    <div id="checker-loading" style="display:none" class="card"><div class="loading-msg"><div class="spinner"></div>Claude analyseert je ad...</div></div>
  </div>
</div>

<div id="page-vault" class="page">
  <h1>&#127942; Winning Ads Vault</h1>
  <p class="sub">Bewaar best presterende ads &mdash; Claude leert hiervan en verbetert elke nieuwe generatie</p>
  <button class="btn btn-primary" onclick="toggleVaultForm()" style="margin-bottom:12px">&#10133; Winning Ad Toevoegen</button>
  <div id="add-vault-form" class="card" style="display:none;margin-bottom:14px">
    <h2>&#10133; Winning Ad Toevoegen</h2>
    <div class="grid2">
      <div>
        <label>Naam / Titel</label><input id="vault-name" placeholder="bv. Warmtepomp FOMO Juni 2025"/>
        <label>Service</label>
        <select id="vault-service"><option>Warmtepomp</option><option>Airco</option><option>Ketelonderhoud</option><option>Ramen &amp; Deuren</option><option>Platdak</option></select>
        <label>Resultaten</label><input id="vault-results" placeholder="bv. CTR 4.2%, CPL 8.50 euro, 45 leads in 1 week"/>
        <label>Wat maakte het winnend?</label>
        <textarea id="vault-why" rows="3" placeholder="bv. Sterke prijs hook, OP=OP urgentie werkte goed, emoji trok aandacht..."></textarea>
      </div>
      <div>
        <label>Volledige Ad Tekst</label>
        <textarea id="vault-text" rows="8" placeholder="Plak hier de volledige ad tekst die goed presteerde..."></textarea>
        <label>Tags (komma-gescheiden)</label>
        <input id="vault-tags" placeholder="urgentie, prijs, warmtepomp, fomo"/>
      </div>
    </div>
    <div class="gap"></div>
    <div class="flex">
      <button class="btn btn-primary" onclick="saveVaultItem()">&#128190; Bewaren</button>
      <button class="btn btn-ghost" onclick="toggleVaultForm()">Annuleren</button>
    </div>
  </div>
  <div id="vault-list"></div>
</div>

<div id="page-assets" class="page">
  <h1>&#128444;&#65039; Asset Bibliotheek</h1>
  <p class="sub">Bewaar logo's, afbeeldingen en referenties voor je ad creatives</p>
  <div class="card" style="margin-bottom:14px">
    <h2>&#128228; Asset Toevoegen</h2>
    <div class="grid2">
      <div>
        <label>Naam</label><input id="asset-name" placeholder="bv. NMT Logo Oranje"/>
        <label>Type</label>
        <select id="asset-type"><option value="logo">Logo</option><option value="background">Achtergrond</option><option value="product">Product foto</option><option value="reference">Referentie ad</option><option value="other">Overige</option></select>
        <label>URL of beschrijving</label><input id="asset-url" placeholder="https://... of beschrijving van de afbeelding"/>
      </div>
      <div>
        <label>Notities</label><textarea id="asset-notes" rows="4" placeholder="Gebruik, kleurcode, wanneer inzetten..."></textarea>
        <div class="gap"></div>
        <button class="btn btn-primary" onclick="saveAsset()">&#128190; Opslaan</button>
      </div>
    </div>
  </div>
  <h2>&#128193; Opgeslagen Assets</h2>
  <div id="asset-grid" class="asset-grid"></div>
</div>

<div id="page-settings" class="page">
  <h1>&#9881;&#65039; Instellingen</h1>
  <p class="sub">Voer je Anthropic API key in om Claude te activeren &mdash; daarna werkt alles automatisch</p>
  <div class="alert alert-orange">
    &#128273; <strong>Jouw actie vereist:</strong> Voer hieronder je Anthropic API key in.
    Haal hem op via <a href="https://console.anthropic.com" target="_blank" style="color:var(--orange);font-weight:bold">console.anthropic.com</a> &rarr; API Keys &rarr; Create Key (begint met sk-ant-api03-...)
  </div>
  <div class="grid2">
    <div class="card">
      <h2>&#128273; Anthropic API Key</h2>
      <label>Claude API Key <span style="color:var(--red)">*</span></label>
      <input id="api-key-input" type="password" placeholder="sk-ant-api03-..."/>
      <p style="font-size:0.78em;color:var(--muted);margin-top:6px">Wordt veilig opgeslagen in je browser. Gaat nergens naartoe.</p>
      <div class="gap"></div>
      <button class="btn btn-primary" onclick="saveApiKey()">&#128190; Opslaan &amp; Claude Activeren</button>
      <div id="api-status" style="margin-top:8px"></div>
    </div>
    <div class="card">
      <h2>&#128279; Gekoppelde Services</h2>
      <p style="font-size:0.83em;color:var(--muted);line-height:2">
        &#9989; <strong>Railway</strong> &mdash; web-production-79958.up.railway.app<br>
        &#9989; <strong>Meta Webhook</strong> &mdash; Leads ontvangen &amp; scoren<br>
        &#9989; <strong>OpenAI GPT-4o-mini</strong> &mdash; WhatsApp templates<br>
        &#128273; <strong>Claude Sonnet</strong> &mdash; Ad generatie (key vereist)<br><br>
        <a href="/dashboard" style="color:var(--orange)">&rarr; Lead Dashboard</a> &nbsp;
        <a href="/health" style="color:var(--orange)">&rarr; Health Check</a>
      </p>
    </div>
  </div>
  <div class="gap"></div>
  <div class="card">
    <h2>&#128221; Standaard Teksten</h2>
    <div class="grid2">
      <div>
        <label>Social Proof tekst</label>
        <textarea id="default-social-proof" rows="3">9/10 klanten bevelen ons aan op TrustLocal &#11088;&#11088;&#11088;&#11088;&#11088;
&#9989; Meer dan 500 tevreden klanten in de regio Antwerpen</textarea>
        <label>FOMO/Urgentie</label>
        <textarea id="default-fomo" rows="3">&#9889; OP=OP &mdash; Nog beperkte plaatsen beschikbaar deze maand!
&#128293; Boek nu en ontvang gratis installatieinspectie (t.w.v. 150 euro)</textarea>
      </div>
      <div>
        <label>Standaard CTA's</label>
        <textarea id="default-ctas" rows="3">&#128073; Vraag gratis en vrijblijvende offerte aan
&#128222; Bel nu &mdash; Wij helpen u direct!
&#128172; Stuur een bericht via WhatsApp</textarea>
        <label>Garantie tekst</label>
        <textarea id="default-guarantee" rows="2">&#9989; 100% gratis offerte &middot; Geen verplichtingen &middot; Binnen 24u reactie</textarea>
      </div>
    </div>
    <div class="gap"></div>
    <button class="btn btn-primary" onclick="saveDefaults()">&#128190; Standaarden Opslaan</button>
  </div>
  <div class="gap"></div>
  <div class="card">
    <h2>&#129302; Extra Claude Instructies</h2>
    <label>Aanvullende instructies voor de ad generator</label>
    <textarea id="system-prompt-extra" rows="4" placeholder="bv. Gebruik altijd u. Vermeld altijd provincie Antwerpen. Verwijs naar overheidssubsidies..."></textarea>
    <div class="gap"></div>
    <button class="btn btn-ghost" onclick="saveSystemPrompt()">&#128190; Opslaan</button>
  </div>
</div>

<script>
var S={apiKey:localStorage.getItem('nmt_k')||'',variants:[],vault:JSON.parse(localStorage.getItem('nmt_v')||'[]'),assets:JSON.parse(localStorage.getItem('nmt_a')||'[]'),defaults:JSON.parse(localStorage.getItem('nmt_d')||'{}')
,sysExtra:localStorage.getItem('nmt_se')||'',lastSvc:''};

function showPage(n,b){document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active')});document.querySelectorAll('.nav-btn').forEach(function(x){x.classList.remove('active')});document.getElementById('page-'+n).classList.add('active');if(b)b.classList.add('active');checkKey();}

function checkKey(){var b=document.getElementById('api-badge'),bn=document.getElementById('no-api-banner');if(S.apiKey&&S.apiKey.startsWith('sk-ant')){b.className='api-badge api-ok';b.textContent='\u2705 Claude actief';if(bn)bn.style.display='none';}else{b.className='api-badge api-missing';b.textContent='\u26a0\ufe0f API Key vereist';if(bn)bn.style.display='block';}}

async function claude(sys,usr,mt){if(!S.apiKey||!S.apiKey.startsWith('sk-ant'))throw new Error('Geen API key. Ga naar \u2699\ufe0f Instellingen.');var r=await fetch('https://api.anthropic.com/v1/messages',{method:'POST',headers:{'Content-Type':'application/json','x-api-key':S.apiKey,'anthropic-version':'2023-06-01'},body:JSON.stringify({model:'claude-sonnet-4-20250514',max_tokens:mt||4096,messages:[{role:'user',content:usr}],system:sys})});if(!r.ok){var e=await r.json();throw new Error((e.error&&e.error.message)||'API fout '+r.status);}var d=await r.json();return d.content[0].text;}

function vaultCtx(){if(!S.vault.length)return'';return'\n\nWINNING ADS (leer hiervan):\n'+S.vault.slice(0,3).map(function(v,i){return'Ad '+(i+1)+' ('+v.service+', resultaten: '+(v.results||'goed')+'): '+v.text.substring(0,200)+'... Werkte omdat: '+(v.why||'nvt')}).join('\n');}

async function generateAds(){var svc=document.getElementById('gen-service').value,con=document.getElementById('gen-concept').value,tgt=document.getElementById('gen-target').value,usp=document.getElementById('gen-usp').value,ext=document.getElementById('gen-extra').value;if(!con.trim()){alert('Vul een concept in!');return;}var sp=S.defaults.socialProof||'9/10 klanten bevelen ons aan op TrustLocal \u2b50\u2b50\u2b50\u2b50\u2b50',fm=S.defaults.fomo||'\u26a1 OP=OP \u2014 Nog beperkte plaatsen beschikbaar!',gu=S.defaults.guarantee||'\u2705 100% gratis offerte \u00b7 Geen verplichtingen';var sys='Je bent expert Facebook/Instagram advertentietekst schrijver voor NMT Group, Belgisch renovatiebedrijf Antwerpen.\nBRAND: NMT Group (MAGINVEST BV) | Service: '+svc+' | Regio: provincie Antwerpen | Taal: Vlaams Nederlands (u/uw)\nFORMAT: ALTIJD 1080x1350 pixels portrait\nVERPLICHT IN ELKE VARIANT:\n- Social proof: "'+sp+'"\n- FOMO: "'+fm+'"\n- Garantie: "'+gu+'"\nFORMULE: Hook (getal/vraag/pijnpunt) \u2192 Probleem\u2192Oplossing\u2192Bewijs \u2192 Social proof \u2192 FOMO \u2192 CTA\n5 VARIANTEN: A=Prijs/Besparing B=Urgentie/FOMO C=Social Proof D=Pijn/Probleem E=Premie/Voordeel\n'+(S.sysExtra?'EXTRA INSTRUCTIES: '+S.sysExtra:'')+vaultCtx()+'\nOUTPUT: Geef EXACT een JSON array met 5 objecten, NIETS anders:\n[{"variant":"A","type":"Prijs/Besparing","headline":"...","subtext":"...","socialProof":"...","fomo":"...","cta":"...","guarantee":"...","fullText":"complete ad tekst"}]';var usr='SERVICE: '+svc+'\nCONCEPT: '+con+'\nDOELGROEP: '+tgt+'\nUSP: '+(usp||'Gratis offerte, snelle installatie')+'\nEXTRA: '+(ext||'geen')+'\n\nGeef ALLEEN de JSON array terug.';document.getElementById('gen-btn').disabled=true;document.getElementById('gen-loading').style.display='block';document.getElementById('variants-output').style.display='none';try{var raw=await claude(sys,usr,4096);var m=raw.match(/\[[\s\S]*\]/);if(!m)throw new Error('Geen geldige JSON ontvangen');var vars=JSON.parse(m[0]);S.variants=vars;S.lastSvc=svc;renderVars(vars,svc);document.getElementById('variants-output').style.display='block';}catch(e){alert('Fout: '+e.message);}finally{document.getElementById('gen-btn').disabled=false;document.getElementById('gen-loading').style.display='none';}}

function renderVars(vars,svc){var c={A:'#22c55e',B:'#f97316',C:'#3b82f6',D:'#a855f7',E:'#ec4899'};document.getElementById('variants-grid').innerHTML=vars.map(function(v,i){return'<div class="ad-card"><div class="ad-preview"><div class="ad-badge" style="background:'+(c[v.variant]||'#f97316')+'">'+ v.variant+'</div><div><div class="ad-service-tag">\U0001f3e0 '+svc+'</div><div class="ad-headline">'+(v.headline||'')+'</div><div class="ad-subtext">'+(v.subtext||'').substring(0,100)+'...</div><div class="ad-social-proof">\u2b50 '+(v.socialProof||'').substring(0,55)+'</div><div class="ad-fomo">\u26a1 '+(v.fomo||'').substring(0,50)+'</div><div class="ad-cta-preview">\U0001f449 '+(v.cta||'Gratis offerte')+'</div><div class="ad-footer">\U0001f4d0 1080x1350 \u00b7 NMT Group</div></div></div><div class="ad-meta"><div class="ad-variant-label">'+(v.type||'Variant '+v.variant)+'</div><div class="ad-actions"><button class="btn btn-ghost btn-sm" onclick="copyV('+i+')">\U0001f4cb Kopieer</button><button class="btn btn-ghost btn-sm" onclick="checkV('+i+')">\U0001f50d Check</button><button class="btn btn-ghost btn-sm" onclick="expandV('+i+')">\U0001f441\ufe0f Volledig</button></div></div></div>';}).join('');}

function copyV(i){var v=S.variants[i];navigator.clipboard.writeText(v.fullText||v.headline+'\n\n'+v.subtext);alert('Variant '+v.variant+' gekopieerd!');}

function expandV(i){var v=S.variants[i],t=v.fullText||v.headline+'\n\n'+v.subtext+'\n\n'+v.socialProof+'\n'+v.fomo+'\n\n'+v.cta+'\n\n'+v.guarantee;var el=document.createElement('div');el.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:1000;display:flex;align-items:center;justify-content:center;padding:16px';el.innerHTML='<div style="background:var(--card);border-radius:14px;padding:20px;max-width:560px;width:100%;max-height:80vh;overflow-y:auto"><div class="flex"><h2>Variant '+v.variant+' \u2014 '+v.type+'</h2><button onclick="this.closest(\'[style]\').remove()" style="margin-left:auto;background:none;border:none;color:var(--muted);font-size:1.5em;cursor:pointer">\u00d7</button></div><pre style="margin-top:12px;background:var(--bg);padding:14px;border-radius:8px;font-size:0.85em;line-height:1.7">'+t+'</pre><div style="margin-top:10px;display:flex;gap:6px"><button class="btn btn-primary btn-sm" onclick="navigator.clipboard.writeText(this.closest(\'[style]\').querySelector(\'pre\').textContent);alert(\'Gekopieerd!\')">\U0001f4cb Kopieer</button><button class="btn btn-ghost btn-sm" onclick="this.closest(\'[style]\').remove()">Sluiten</button></div></div>';document.body.appendChild(el);}

function checkV(i){document.getElementById('checker-input').value=S.variants[i].fullText||S.variants[i].headline;showPage('checker',document.querySelectorAll('.nav-btn')[1]);}

function copyAllVariants(){navigator.clipboard.writeText(S.variants.map(function(v){return'=== VARIANT '+v.variant+' \u2014 '+v.type+' ===\n'+(v.fullText||v.headline+'\n'+v.subtext)}).join('\n\n'+'\u2500'.repeat(40)+'\n\n'));alert('Alle varianten gekopieerd!');}

function saveToVault(){if(!S.variants.length)return;var v=S.variants[0];S.vault.unshift({id:Date.now(),name:S.lastSvc+' - Auto '+new Date().toLocaleDateString('nl-BE'),service:S.lastSvc,text:v.fullText||v.headline+'\n'+v.subtext,results:'',why:'Auto-opgeslagen vanuit generator',tags:['auto',S.lastSvc.toLowerCase()],date:new Date().toISOString()});localStorage.setItem('nmt_v',JSON.stringify(S.vault));renderVault();alert('Opgeslagen in Vault!');}

async function runChecker(){var txt=document.getElementById('checker-input').value.trim(),svc=document.getElementById('checker-service').value;if(!txt){alert('Voer ad tekst in!');return;}document.getElementById('checker-results').style.display='none';document.getElementById('checker-loading').style.display='block';var sys='Je bent kwaliteitscontroleur voor Vlaamse Facebook/Instagram advertenties voor NMT Group.\nAnalyseer op: spelfouten (Vlaams NL), zwakke/ontbrekende CTA, ontbrekende social proof, ontbrekende FOMO/urgentie, inconsistenties, dubbele elementen, stijlproblemen.\nGeef EXACT dit JSON (niets anders):\n{"score":85,"issues":[{"type":"error","icon":"\u274c","text":"beschrijving","fix":"hoe te fixen"}],"fixedVersion":"volledig gecorrigeerde ad tekst"}\nScore 0-100. Wees specifiek. Geef altijd een gecorrigeerde versie.';try{var raw=await claude(sys,'Analyseer deze '+svc+' ad:\n\n'+txt,2048);var m=raw.match(/\{[\s\S]*\}/);if(!m)throw new Error('Ongeldig antwoord');var res=JSON.parse(m[0]);var se=document.getElementById('checker-score');se.textContent=res.score+'/100';se.className='quality-score '+(res.score>=80?'score-ok':res.score>=60?'score-warn':'score-bad');document.getElementById('checker-issues').innerHTML=(res.issues||[]).map(function(x){return'<div class="issue-item"><div>'+x.icon+'</div><div><div class="issue-text">'+x.text+'</div>'+(x.fix?'<div class="issue-fix">\U0001f4a1 Fix: '+x.fix+'</div>':'')+'</div></div>'}).join('')||'<div style="color:var(--green);padding:8px">\u2705 Geen problemen gevonden!</div>';document.getElementById('checker-fixed').textContent=res.fixedVersion||txt;window._fx=res.fixedVersion;document.getElementById('checker-results').style.display='block';}catch(e){alert('Fout: '+e.message);}finally{document.getElementById('checker-loading').style.display='none';}}

function copyFixed(){navigator.clipboard.writeText(window._fx||document.getElementById('checker-fixed').textContent);alert('Gecorrigeerde versie gekopieerd!');}

function toggleVaultForm(){var f=document.getElementById('add-vault-form');f.style.display=f.style.display==='none'?'block':'none';}

function saveVaultItem(){S.vault.unshift({id:Date.now(),name:document.getElementById('vault-name').value||'Winning Ad',service:document.getElementById('vault-service').value,results:document.getElementById('vault-results').value,why:document.getElementById('vault-why').value,text:document.getElementById('vault-text').value,tags:document.getElementById('vault-tags').value.split(',').map(function(t){return t.trim()}).filter(Boolean),date:new Date().toISOString()});localStorage.setItem('nmt_v',JSON.stringify(S.vault));renderVault();toggleVaultForm();['vault-name','vault-results','vault-why','vault-text','vault-tags'].forEach(function(id){document.getElementById(id).value=''});}

function renderVault(){var l=document.getElementById('vault-list');if(!l)return;if(!S.vault.length){l.innerHTML='<div style="color:var(--muted);text-align:center;padding:30px">Nog geen winning ads. Voeg je best presterende ads toe!</div>';return;}l.innerHTML=S.vault.map(function(v,i){return'<div class="vault-item"><div class="flex"><div><strong>'+v.name+'</strong><span style="margin-left:8px;font-size:0.72em;color:var(--muted)">'+v.service+' \u00b7 '+new Date(v.date).toLocaleDateString('nl-BE')+'</span></div><div class="flex ml-auto"><button class="btn btn-ghost btn-sm" onclick="document.getElementById(\'checker-input\').value=S.vault['+i+'].text;showPage(\'checker\',document.querySelectorAll(\'.nav-btn\')[1])">\U0001f50d</button><button class="btn btn-danger btn-sm" onclick="if(confirm(\'Verwijderen?\'))S.vault.splice('+i+',1),localStorage.setItem(\'nmt_v\',JSON.stringify(S.vault)),renderVault()">\U0001f5d1\ufe0f</button></div></div>'+(v.results?'<div style="margin-top:5px;font-size:0.8em;color:var(--green)">\U0001f4ca '+v.results+'</div>':'')+( v.why?'<div style="margin-top:3px;font-size:0.8em;color:var(--muted)">\U0001f4a1 '+v.why+'</div>':'')+'<div class="vault-tags">'+(v.tags||[]).map(function(t){return'<span class="tag">'+t+'</span>'}).join('')+'</div></div>';}).join('');}

function saveAsset(){S.assets.unshift({id:Date.now(),name:document.getElementById('asset-name').value||'Asset',type:document.getElementById('asset-type').value,url:document.getElementById('asset-url').value,notes:document.getElementById('asset-notes').value,date:new Date().toISOString()});localStorage.setItem('nmt_a',JSON.stringify(S.assets));renderAssets();['asset-name','asset-url','asset-notes'].forEach(function(id){document.getElementById(id).value=''});}

function renderAssets(){var g=document.getElementById('asset-grid');if(!g)return;var ic={logo:'\U0001f3f7\ufe0f',background:'\U0001f5bc\ufe0f',product:'\U0001f4e6',reference:'\U0001f3c6',other:'\U0001f4ce'};if(!S.assets.length){g.innerHTML='<div style="color:var(--muted);padding:16px;grid-column:1/-1">Nog geen assets opgeslagen.</div>';return;}g.innerHTML=S.assets.map(function(a,i){return'<div class="asset-item"><div class="asset-thumb">'+(ic[a.type]||'\U0001f4ce')+'</div><div class="asset-name">'+a.name+'</div><div class="asset-type">'+a.type+' <span onclick="if(confirm(\'Verwijderen?\'))S.assets.splice('+i+',1),localStorage.setItem(\'nmt_a\',JSON.stringify(S.assets)),renderAssets()" style="color:var(--red);cursor:pointer">\U0001f5d1\ufe0f</span></div></div>';}).join('');}

function saveApiKey(){var k=document.getElementById('api-key-input').value.trim();if(!k.startsWith('sk-ant')){document.getElementById('api-status').innerHTML='<div class="alert alert-red">\u26a0\ufe0f Ongeldige key. Moet beginnen met sk-ant...</div>';return;}S.apiKey=k;localStorage.setItem('nmt_k',k);document.getElementById('api-status').innerHTML='<div class="alert alert-green">\u2705 Claude Sonnet geactiveerd! Je kunt nu ads genereren.</div>';checkKey();}

function saveDefaults(){S.defaults={socialProof:document.getElementById('default-social-proof').value,fomo:document.getElementById('default-fomo').value,ctas:document.getElementById('default-ctas').value,guarantee:document.getElementById('default-guarantee').value};localStorage.setItem('nmt_d',JSON.stringify(S.defaults));alert('Standaarden opgeslagen!');}

function saveSystemPrompt(){S.sysExtra=document.getElementById('system-prompt-extra').value;localStorage.setItem('nmt_se',S.sysExtra);alert('Claude instructies opgeslagen!');}

(function init(){checkKey();renderVault();renderAssets();var d=S.defaults;if(d.socialProof)document.getElementById('default-social-proof').value=d.socialProof;if(d.fomo)document.getElementById('default-fomo').value=d.fomo;if(d.ctas)document.getElementById('default-ctas').value=d.ctas;if(d.guarantee)document.getElementById('default-guarantee').value=d.guarantee;var se=localStorage.getItem('nmt_se');if(se)document.getElementById('system-prompt-extra').value=se;if(S.apiKey)document.getElementById('api-key-input').value=S.apiKey;})();
</script>
</body>
</html>"""
