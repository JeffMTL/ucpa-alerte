#!/usr/bin/env python3
"""
Alerte "place libérée" pour UCPA Sport Station Nantes (cours collectifs Fitness).

- Lit le planning PUBLIC du site (aucune connexion, aucun compte).
- Compare avec la liste de cours surveillés (watch.json).
- Envoie une notification ntfy quand un cours complet a de nouveau au moins 1 place.

Commandes :
  python ucpa_alert.py check            vérifie les cours surveillés (défaut)
  python ucpa_alert.py list --week 1    affiche les cours de la semaine N (0 = en cours)
  python ucpa_alert.py test             envoie une notification de test
  python ucpa_alert.py loop --every 120 vérifie en boucle (pour un PC / Raspberry Pi)

Variable d'environnement : NTFY_TOPIC (nom secret du sujet ntfy).
Uniquement la bibliothèque standard Python (3.9+).
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
HERE = os.path.dirname(os.path.abspath(__file__))
WATCH_FILE = os.path.join(HERE, "watch.json")
STATE_FILE = os.path.join(HERE, "state.json")

PAGE = "https://www.ucpa.com/sport-station/nantes/fitness"
API = "https://www.ucpa.com/sport-station/api/areas-offers/migrated"
PARAMS = {
    "workspace": "alpha_nan",
    "espace": "area_1680850484_13e5a1d0-d511-11ed-93bb-77fd2e78b8a9",
    "period": "months",
    "reservationPeriod": "1",
    "plannerMonthsToIndex": "4",
    "timeframe": "weekly",
    "timezone": "Europe/Paris",
    "codeSiteComptage": "103518861",
    "isInternalSession": "false",
    "time": "0",  # décalage en semaines : 0 = semaine en cours, 1 = suivante...
    "enableCourtProject": "true",
}
MAX_WEEKS = 5  # le site n'ouvre les réservations que ~1 mois à l'avance
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
FR_DAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
ERRORS_BEFORE_ALERT = 6  # ~30 min d'échecs de lecture avant de prévenir


# ---------- utilitaires ----------
def log(*a):
    print(datetime.now(TZ).strftime("%H:%M:%S"), *a, flush=True)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def norm_start(s):
    return s.strip().lower().replace(":", "h")


def parse_dt(date_str, start):
    d, m, y = map(int, date_str.split("/"))
    h, _, mi = norm_start(start).partition("h")
    return datetime(y, m, d, int(h), int(mi or 0), tzinfo=TZ)


def pretty(date_str, start):
    dt = parse_dt(date_str, start)
    return f"{FR_DAYS[dt.weekday()]} {dt:%d/%m} à {norm_start(start)}"


# ---------- lecture du planning ----------
def http_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "fr-FR,fr;q=0.9",
                "Referer": PAGE,
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:  # réseau, 403, JSON invalide...
            last = e
            time.sleep(2 * (i + 1))
    raise last


def fetch_week(offset):
    q = dict(PARAMS, time=str(offset))
    data = http_json(API + "?" + urllib.parse.urlencode(q))
    sessions = []
    for col in data["planner"]["columns"]:
        for it in col.get("items", []):
            sessions.append({
                "id": str(it.get("id")),
                "name": it["name"],
                "date": it["startDate"],      # "02/11/2026"
                "start": it["startTime"],     # "07h30"
                "end": it["endTime"],
                "stock": int(it.get("stock") or 0),
                "label": it.get("stockLabel", ""),
            })
    return sessions


def find(sessions, w):
    for s in sessions:
        if (s["date"] == w["date"] and norm_start(s["start"]) == w["start"]
                and s["name"].casefold() == w["name"].casefold()):
            return s
    return None


# ---------- notification ----------
def send(title, message, priority=4, tags=None):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log("NTFY_TOPIC absent : impossible d'envoyer ->", title, "|", message)
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    payload = {
        "topic": topic, "title": title, "message": message,
        "priority": priority, "tags": tags or [], "click": PAGE,
        "actions": [{"action": "view", "label": "Ouvrir le planning", "url": PAGE}],
    }
    req = urllib.request.Request(
        server, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
        return True
    except Exception as e:
        log("Échec d'envoi ntfy :", e)
        return False


# ---------- commandes ----------
def week_offset(dt, now):
    monday_now = now.date() - timedelta(days=now.weekday())
    monday_dt = dt.date() - timedelta(days=dt.weekday())
    return (monday_dt - monday_now).days // 7


def run_check():
    watches = load_json(WATCH_FILE, [])
    state = load_json(STATE_FILE, {})
    wstate = state.setdefault("watches", {})
    now = datetime.now(TZ)

    by_week, keys_active = {}, set()
    for raw in watches:
        try:
            w = {"name": raw["name"], "date": raw["date"], "start": norm_start(raw["start"])}
            dt = parse_dt(w["date"], w["start"])
        except Exception:
            log("Ligne ignorée (format invalide) :", raw)
            continue
        if dt <= now:
            log("Cours déjà commencé, ignoré :", w["name"], pretty(w["date"], w["start"]))
            continue
        off = week_offset(dt, now)
        if off > MAX_WEEKS:
            log("Trop loin dans le futur, ignoré :", w["name"], pretty(w["date"], w["start"]))
            continue
        w["key"] = f'{w["date"]}|{w["start"]}|{w["name"].casefold()}'
        keys_active.add(w["key"])
        by_week.setdefault(off, []).append(w)

    ok = fail = 0
    for off, ws in sorted(by_week.items()):
        try:
            sessions = fetch_week(off)
            ok += 1
        except Exception as e:
            fail += 1
            log(f"Lecture impossible (semaine +{off}) :", e)
            continue
        for w in ws:
            s = find(sessions, w)
            label = f'{w["name"]} {pretty(w["date"], w["start"])}'
            if s is None:
                log("Cours introuvable dans le planning :", label)
                continue
            st = wstate.setdefault(w["key"], {"notified": False})
            if s["stock"] > 0:
                if st["notified"]:
                    log(label, "->", s["label"], "(déjà notifié)")
                    continue
                time.sleep(3)  # double vérification avant d'alerter
                try:
                    s2 = find(fetch_week(off), w) or s
                except Exception:
                    s2 = s
                if s2["stock"] > 0:
                    msg = f'{w["name"]}, {pretty(w["date"], w["start"])} : {s2["label"]}'
                    if send(f'Place libre : {w["name"]}', msg, tags=["white_check_mark"]):
                        st["notified"] = True
                        log("Notification envoyée :", msg)
            else:
                if st["notified"]:
                    log(label, "est de nouveau complet : alerte réarmée")
                st["notified"] = False
                log(label, "-> complet")

    # état : purge des cours retirés / passés
    for k in list(wstate):
        if k not in keys_active:
            del wstate[k]

    # signalement si le planning devient illisible
    if by_week and ok == 0 and fail > 0:
        state["errors"] = state.get("errors", 0) + 1
        if state["errors"] >= ERRORS_BEFORE_ALERT and not state.get("error_notified"):
            if send("Alerte UCPA : lecture impossible",
                    "Le script n'arrive plus à lire le planning (site modifié ou bloqué ?).",
                    priority=3, tags=["warning"]):
                state["error_notified"] = True
    elif ok > 0:
        state["errors"] = 0
        state["error_notified"] = False

    save_json(STATE_FILE, state)


def run_list(week):
    sessions = fetch_week(week)
    if not sessions:
        print("Aucun cours trouvé pour cette semaine.")
        return
    sessions.sort(key=lambda s: parse_dt(s["date"], s["start"]))
    current = None
    full = []
    for s in sessions:
        if s["date"] != current:
            current = s["date"]
            dt = parse_dt(s["date"], s["start"])
            print(f"\n== {FR_DAYS[dt.weekday()]} {s['date']} ==")
        etat = "COMPLET" if s["stock"] == 0 else s["label"]
        print(f'  {s["start"]}-{s["end"]}  {s["name"]:<24} {etat}')
        if s["stock"] == 0:
            full.append(s)
    if full:
        print("\n--- Cours complets : lignes à copier dans watch.json ---")
        for s in full:
            print(json.dumps({"name": s["name"], "date": s["date"], "start": s["start"]},
                             ensure_ascii=False) + ",")


def main():
    p = argparse.ArgumentParser(description="Alerte places UCPA Nantes")
    p.add_argument("command", nargs="?", default="check",
                   choices=["check", "list", "test", "loop"])
    p.add_argument("--week", type=int, default=0, help="décalage en semaines (list)")
    p.add_argument("--every", type=int, default=120, help="secondes entre 2 vérifications (loop)")
    a = p.parse_args()

    if a.command == "check":
        run_check()
    elif a.command == "list":
        run_list(a.week)
    elif a.command == "test":
        ok = send("Test UCPA", "Si vous lisez ceci, les notifications fonctionnent.",
                  priority=3, tags=["tada"])
        print("Notification de test envoyée." if ok else "Échec : vérifiez NTFY_TOPIC.")
    elif a.command == "loop":
        log(f"Surveillance en boucle toutes les {a.every}s (Ctrl+C pour arrêter)")
        while True:
            try:
                run_check()
            except Exception as e:
                log("Erreur :", e)
            time.sleep(max(30, a.every))


if __name__ == "__main__":
    sys.exit(main())
