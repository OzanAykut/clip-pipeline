"""Transkripti Gemini'ye gonderip klip icin en iyi anlari sectirir."""
from __future__ import annotations

import bisect
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from rich.progress import track

from utils import console

MODEL_NAME = "gemini-2.5-flash-lite"
CHUNK_SECONDS = 600  # ~10 dk parcalar
CHUNK_OVERLAP = 30  # saniye

SYSTEM_PROMPT = """Sen kisa video (TikTok/Shorts) icerik editorusun. Sana uzun bir podcast/yayinin
zaman damgali transkript parcasi verilecek. Gorevin, bu parcadan bagimsiz olarak izlenebilecek,
dikkat cekici klip adaylari bulmak.

KURALLAR:
- Her klip TEK BASINA anlasilir olmali (baglam disaridan bilinmeden anlasilmali).
- Klip bir cumle ORTASINDA baslamamali veya bitmemeli; dogal cumle/dusunce sinirlarinda basla/bitir.
- Ilk 3 saniyede guclu bir "hook" (kanca) olmali: soru, sok edici iddia, merak uyandiran cumle vb.
- start ve end degerleri saniye cinsinden, verilen transkript parcasinin zaman araligi icinde olmali.
- Klipler {min_dur} ile {max_dur} saniye arasinda olmali.
- Ayni parca icindeki klipler birbiriyle CAKISMAMALI.
- score: 1 (zayif) - 10 (viral potansiyeli yuksek) arasinda dogru bir tahmin.
- reason, title, hook alanlarini {title_lang} dilinde yaz (transkriptin dili ile ayni).
- title: kisa, merak uyandiran baslik, max 8 kelime.
- hook: klibin ilk cumlesi/ani neden izleyiciyi durdurur, 1 cumleyle acikla.
- hook_words: transkriptten AYNEN alinmis (yazimini degistirme) 2-4 TEK KELIME (ifade/cumlecik
  DEGIL, her eleman bosluksuz TEK bir kelime olmali, orn. "lost control of" GECERSIZ ama "control"
  GECERLI); klibin en carpici/kanca anindaki (genelde ilk birkac saniyedeki) vurgulanacak kelimeler.
  Bu kelimeler klip icinde ses efektiyle vurgulanacak, o yuzden gercekten transkriptte AYNI YAZIMLA
  gecen tekil kelimeler olmali. Uygun kelime yoksa bos array birak.

SADECE JSON dondur, baska hicbir metin ekleme."""

LANGUAGE_NAMES = {
    "tr": "Turkish",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "ru": "Russian",
    "ar": "Arabic",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
}


class ClipCandidate(BaseModel):
    start: float
    end: float
    title: str
    hook: str
    score: int
    reason: str
    hook_words: list[str] = []


@dataclass
class FlatWord:
    word: str
    start: float
    end: float


@dataclass
class Candidate:
    start: float
    end: float
    title: str
    hook: str
    score: int
    reason: str
    hook_words: list[str] = field(default_factory=list)


def _flatten_words(transcript: dict[str, Any]) -> list[FlatWord]:
    words: list[FlatWord] = []
    for seg in transcript["segments"]:
        for w in seg.get("words", []):
            if w["end"] > w["start"]:
                words.append(FlatWord(w["word"], w["start"], w["end"]))
    words.sort(key=lambda w: w.start)
    return words


def _build_chunks(transcript: dict[str, Any]) -> list[list[dict[str, Any]]]:
    segments = transcript["segments"]
    if not segments:
        return []
    duration = transcript.get("duration") or segments[-1]["end"]
    chunks: list[list[dict[str, Any]]] = []
    chunk_start = 0.0
    while chunk_start < duration:
        chunk_end = chunk_start + CHUNK_SECONDS
        chunk_segs = [s for s in segments if s["start"] < chunk_end and s["end"] > chunk_start - CHUNK_OVERLAP]
        if chunk_segs:
            chunks.append(chunk_segs)
        chunk_start = chunk_end
    return chunks


def _chunk_to_text(chunk_segs: list[dict[str, Any]]) -> str:
    lines = []
    for seg in chunk_segs:
        lines.append(f"[{seg['start']:.2f}-{seg['end']:.2f}] {seg['text']}")
    return "\n".join(lines)


def _extract_retry_delay(exc: Exception) -> float | None:
    """429 hatasinin govdesindeki onerilen 'retryDelay' suresini (saniye) cikarir."""
    match = re.search(r"'retryDelay':\s*'(\d+)s'", str(exc))
    return float(match.group(1)) if match else None


def _call_gemini(client: Any, prompt: str, retries_left: int = 4) -> list[ClipCandidate]:
    from google.genai import types

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[ClipCandidate],
                temperature=0.4,
            ),
        )
        parsed = response.parsed
        if parsed is not None:
            return list(parsed)
        # parsed None ise manuel parse dene
        return [ClipCandidate(**item) for item in json.loads(response.text)]
    except Exception as e:
        is_rate_limit = "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e)
        if retries_left <= 0:
            console.print(f"[red]Gemini cagrisi basarisiz oldu, bu parca atlaniyor: {e}[/red]")
            return []
        if is_rate_limit:
            wait = (_extract_retry_delay(e) or 30.0) + 2.0
            console.print(f"[yellow]Gemini kota siniri, {wait:.0f}sn bekleyip yeniden deneniyor...[/yellow]")
            time.sleep(wait)
            return _call_gemini(client, prompt, retries_left=retries_left - 1)
        console.print(f"[yellow]Gemini yaniti parse edilemedi, yeniden deneniyor... ({e})[/yellow]")
        time.sleep(2)
        return _call_gemini(
            client, prompt + "\n\nSADECE GECERLI JSON DONDUR, markdown kod bloklari kullanma.",
            retries_left=retries_left - 1,
        )


START_PAD = 0.12  # saniye - kelimenin basi kesilmesin diye biraz erken basla
END_PAD = 0.20  # saniye - kelimenin sonu/nefesi kesilmesin diye biraz gec bitir


def _align_to_words(words: list[FlatWord], start: float, end: float) -> tuple[float, float]:
    if not words:
        return start, end
    starts = [w.start for w in words]
    ends = [w.end for w in words]

    i = bisect.bisect_left(starts, start)
    candidates_i = [c for c in (i - 1, i) if 0 <= c < len(words)]
    aligned_start = min(candidates_i, key=lambda c: abs(words[c].start - start))
    aligned_start_val = words[aligned_start].start

    j = bisect.bisect_left(ends, end)
    candidates_j = [c for c in (j - 1, j) if 0 <= c < len(words)]
    aligned_end = min(candidates_j, key=lambda c: abs(words[c].end - end))
    aligned_end_val = words[aligned_end].end

    # faster-whisper'in kelime zaman damgalari bazen tam degil (kelimenin basini/
    # sonunu birkac yuz ms erken kesebiliyor); render'da sesin ortasindan kesilmis
    # gibi durmasini onlemek icin hafif bir pay birakiyoruz.
    aligned_start_val = max(0.0, aligned_start_val - START_PAD)
    aligned_end_val = aligned_end_val + END_PAD

    return aligned_start_val, aligned_end_val


def _resolve_overlaps(candidates: list[Candidate]) -> list[Candidate]:
    """Skora gore azalan sirada greedy secim yapar, cakisanlari eler."""
    accepted: list[Candidate] = []
    for c in sorted(candidates, key=lambda c: c.score, reverse=True):
        overlap = any(not (c.end <= a.start or c.start >= a.end) for a in accepted)
        if not overlap:
            accepted.append(c)
    return accepted


def select_moments(
    transcript: dict[str, Any],
    api_key: str,
    num_clips: int = 10,
    min_dur: int = 25,
    max_dur: int = 60,
) -> list[dict[str, Any]]:
    from google import genai

    client = genai.Client(api_key=api_key)
    words = _flatten_words(transcript)
    chunks = _build_chunks(transcript)
    title_lang = LANGUAGE_NAMES.get(transcript.get("language"), "the transcript's own language")

    if not chunks:
        console.print("[red]Transkriptte segment bulunamadi.[/red]")
        return []

    all_candidates: list[Candidate] = []
    for i, chunk_segs in enumerate(track(chunks, description="Gemini ile aday anlar araniyor...")):
        if i > 0:
            # ucretsiz katmanda dakikada 5 istek siniri var; bunun altinda kalmak icin
            # parcalar arasinda bekle (kota hatasiyla parca atlamak yerine).
            time.sleep(13.0)
        prompt = (
            SYSTEM_PROMPT.format(min_dur=min_dur, max_dur=max_dur, title_lang=title_lang)
            + "\n\nTRANSKRIPT PARCASI:\n"
            + _chunk_to_text(chunk_segs)
        )
        results = _call_gemini(client, prompt)
        for r in results:
            all_candidates.append(
                Candidate(
                    start=r.start, end=r.end, title=r.title, hook=r.hook, score=r.score,
                    reason=r.reason, hook_words=r.hook_words,
                )
            )

    console.print(f"[cyan]{len(all_candidates)} aday bulundu, hizalama ve filtreleme yapiliyor...[/cyan]")

    aligned: list[Candidate] = []
    for c in all_candidates:
        a_start, a_end = _align_to_words(words, c.start, c.end)
        dur = a_end - a_start
        if dur <= 0:
            continue
        if dur > max_dur:
            # max suredeki en yakin kelime sinirina kirp
            cutoff = a_start + max_dur
            k = bisect.bisect_left([w.end for w in words], cutoff)
            if k >= len(words):
                k = len(words) - 1
            if words[k].end > a_start:
                a_end = words[k].end
            dur = a_end - a_start
        if dur < min_dur:
            # Gemini (ozellikle flash-lite) bazen tek cumlelik cok kisa an donduruyor: hook'un basini koru,
            # min sureye ulasana kadar uzat ve ilk cumle sonunda bitir (en fazla max_dur)
            k = bisect.bisect_left([w.end for w in words], a_start + min_dur)
            while k < len(words) - 1 and words[k].end - a_start < max_dur and not words[k].word.strip().endswith((".", "?", "!")):
                k += 1
            if k < len(words):
                a_end = min(words[k].end + END_PAD, a_start + max_dur)
            dur = a_end - a_start
        if dur < min_dur or dur > max_dur:
            continue
        aligned.append(
            Candidate(
                start=a_start, end=a_end, title=c.title, hook=c.hook, score=c.score,
                reason=c.reason, hook_words=c.hook_words,
            )
        )

    non_overlapping = _resolve_overlaps(aligned)
    top = sorted(non_overlapping, key=lambda c: c.score, reverse=True)[:num_clips]
    top_sorted = sorted(top, key=lambda c: c.score, reverse=True)

    return [
        {
            "start": round(c.start, 2),
            "end": round(c.end, 2),
            "duration": round(c.end - c.start, 2),
            "title": c.title,
            "hook": c.hook,
            "score": c.score,
            "reason": c.reason,
            "hook_words": c.hook_words,
        }
        for c in top_sorted
    ]
