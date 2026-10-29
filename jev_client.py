"""Jev (TypeSafe) karar modeli istemcisi - OpenRouter Decisions API.

Jev metin yazmaz; verilen 'state' (degerlendirilecek icerik) icin tipli sorulara olasilik dondurur:
  noul   -> evet/hayir olasiligi        {"type":"noul","instructions":..,"criteria":{"true":..,"false":..}}
  choice -> etiketlerden biri            {"type":"choice","instructions":..,"criteria":{"etiket": "tarif", ...}}
  score  -> sirali olcek                 {"type":"score","instructions":..,"criteria":["dusuk", ..., "yuksek"]}
Ayni state hakkindaki tum sorular tek istekte gonderilir. Ucret sadece girdi tokenlari (~$0.00002/cagri).
Anahtar: .env -> OPENROUTER_API_KEY. Sonuclar diske onbelleklenir (ayni state+soru tekrar ucretlendirilmez).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
CACHE = Path("work/research/jev_cache")

_spent = 0.0


def spent() -> float:
    """Bu oturumda harcanan toplam dolar (yanittaki usage.cost toplami)."""
    return _spent


def _key() -> str:
    load_dotenv(".env")
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        raise RuntimeError("OPENROUTER_API_KEY .env icinde yok (openrouter.ai > Keys).")
    return k


def decide(state: str | dict | list, questions: dict[str, dict], retries: int = 3) -> dict[str, dict]:
    """questions: {anahtar: soru}. Donus: {anahtar: cevap} (choice -> 'choice' + 'probabilities',
    noul -> 'noul' olasiligi, score -> 'score' + 'probabilities')."""
    global _spent
    body = {"model": MODEL, "state": state, "questions": questions}
    h = hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    cache = CACHE / f"{h}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    for attempt in range(retries):
        r = requests.post(URL, json=body, timeout=60,
                          headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"Jev hata {r.status_code}: {r.text[:500]}")
        data = r.json()
        _spent += float(data.get("usage", {}).get("cost", 0) or 0)
        answers = data["answers"]
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
        return answers
    raise RuntimeError("Jev: tekrar denemeler tukendi")


def choice(label_tarifleri: dict[str, str], instructions: str) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": label_tarifleri}


def noul(instructions: str, true: str, false: str) -> dict:
    return {"type": "noul", "instructions": instructions, "criteria": {"true": true, "false": false}}


def score(instructions: str, levels: list[str]) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": levels}


if __name__ == "__main__":
    # hizli test: python jev_client.py
    ans = decide("What if a needle hit your city at light speed? A single sewing needle, flying at 99.99% "
                 "the speed of light, hits with the energy of 100 Hiroshima bombs.",
                 {"hook": choice({"shock_number": "a surprising number or statistic",
                                  "question": "opens with a question to the viewer",
                                  "danger": "a threat or danger to the viewer"}, "What is the main hook type?")})
    print(json.dumps(ans, indent=2), f"\ncost ${spent():.6f}")
