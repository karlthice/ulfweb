#!/usr/bin/env python3
"""
Graph RAG Icelandic Benchmark — HRÍ Keppnisreglur

Uploads the Icelandic cycling competition rules (Keppnisreglur HRÍ) PDF
to collection 4 and evaluates retrieval accuracy against 10 Q&A pairs
in Icelandic, testing multilingual Graph RAG performance.

Usage:
    python3 tests/test_graphrag_hri.py [--skip-upload] [--base-url URL]
"""

import argparse
import json
import re
import sys
import time

import httpx
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ── Configuration ──────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "http://localhost:8000"
COLLECTION_ID = 4
POLL_INTERVAL = 3
QUERY_TOP_K = 10

PDF_PATH = "/home/karlth/Downloads/Keppnisreglur-HRI-2020-6juli.pdf"

# ── Benchmark Q&A pairs ────────────────────────────────────────────────────

BENCHMARK = [
    {
        "question": "Hvað stendur skammstöfunin HRÍ fyrir?",
        "expected": "Skammstöfunin stendur fyrir Hjólreiðasamband Íslands.",
        "keywords": ["Hjólreiðasamband", "Íslands"],
    },
    {
        "question": "Er leyfilegt að keppa án hjálms á mótum HRÍ?",
        "expected": "Nei, það er hjálmaskylda í öllum keppnum á keppnisdagskrá HRÍ.",
        "keywords": ["hjálmaskylda", "öllum keppnum"],
    },
    {
        "question": "Hversu hátt gjald þarf keppnishaldari að greiða HRÍ fyrir hvern skráðan keppanda á íslandsmóti?",
        "expected": "Fyrir hvern keppanda tekur HRÍ gjald að fjárhæð 1.000 krónur.",
        "keywords": ["1.000", "krónur", "keppanda"],
    },
    {
        "question": "Hvaða aðila nefnir reglugerðin að keppnishaldari gæti þurft að fá leyfi hjá til að halda keppni?",
        "expected": "Keppnishaldari þarf að afla leyfa frá veghaldara, lögreglu og sveitarfélagi ef við á.",
        "keywords": ["veghaldara", "lögreglu", "sveitarfélagi"],
    },
    {
        "question": "Hver er fresturinn til að skila inn kæru eftir að atvik á sér stað í keppni?",
        "expected": "Kærufresturinn rennur út 30 mínútum eftir að viðkomandi keppandi kemur í mark.",
        "keywords": ["30 mínútum", "mark", "kæru"],
    },
    {
        "question": "Má ríkjandi Íslandsmeistari klæðast Íslandsmeistaratreyjunni sinni þegar hann keppir á Íslandsmóti?",
        "expected": "Nei, það má ekki keppa í Íslandsmeistaratreyju á íslandsmóti því þar er verið að keppa um sjálfan titilinn.",
        "keywords": ["Íslandsmeistaratreyju", "íslandsmóti", "titilinn"],
    },
    {
        "question": "Hvaða skilyrði þarf erlendur ríkisborgari að uppfylla til að fá þátttökurétt á Íslandsmóti?",
        "expected": (
            "Erlendur ríkisborgari verður að hafa átt lögheimili á Íslandi í þrjú ár. "
            "Að auki verður viðkomandi að vera fullgildur meðlimur í félagi innan ÍSÍ."
        ),
        "keywords": ["lögheimili", "þrjú ár", "ÍSÍ", "meðlimur"],
    },
    {
        "question": "Hvaða fjögur atriði verða að koma fram í skriflegri kæru vegna meints brots á keppnisreglum?",
        "expected": (
            "Það verður að koma fram hvaða regla er talin brotin. Einnig þarf að "
            "tilgreina hvar og hvenær brotið átti sér stað. Þá þarf að koma fram "
            "hverjir urðu uppvísir að brotinu. Að lokum þarf að fylgja nákvæm "
            "lýsing á brotinu."
        ),
        "keywords": ["regla", "hvar", "hvenær", "uppvísir", "lýsing"],
    },
    {
        "question": "Hvernig er skorið úr um sigurvegara ef tveir keppendur eru jafnir að stigum þegar öllum mótum í stigakeppni er lokið?",
        "expected": (
            "Sá aðili telst sigurvegari sem oftar hefur lent í fyrsta sæti. Ef þeir "
            "eru enn jafnir gildir hvor hefur oftar verið í öðru sæti, og svo framvegis. "
            "Ef enn er jafnt þá verður sá Stigameistari sem var ofar í síðustu keppni ársins."
        ),
        "keywords": ["fyrsta sæti", "öðru sæti", "síðustu keppni"],
    },
    {
        "question": "Hvaða brot á auglýsingareglum geta leitt til þess að keppanda, félagi eða liði sé meinuð þátttaka í keppni?",
        "expected": (
            "Brot geta falist í því að auglýsa eða tengja sig við vörumerki sem "
            "tengjast tóbaki, áfengi, klámi eða öðrum vörum sem gætu skaðað ímynd "
            "HRÍ eða hjólreiða á Íslandi. Ef þessi regla er brotin getur það leitt "
            "til þess að keppanda, félagi eða liði sé meinuð þátttaka."
        ),
        "keywords": ["tóbaki", "áfengi", "klámi", "ímynd", "meinuð þátttaka"],
    },
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def upload_pdf(client: httpx.Client, base_url: str, pdf_path: str) -> dict:
    filename = pdf_path.rsplit("/", 1)[-1]
    with open(pdf_path, "rb") as f:
        resp = client.post(
            f"{base_url}/api/v1/documents/collections/{COLLECTION_ID}/documents",
            files={"file": (filename, f, "application/pdf")},
        )
    resp.raise_for_status()
    return resp.json()


def poll_status(client: httpx.Client, base_url: str, doc_id: int) -> str:
    while True:
        resp = client.get(f"{base_url}/api/v1/documents/documents/{doc_id}/status")
        resp.raise_for_status()
        data = resp.json()
        status = data["status"]
        if status == "ready":
            print(f"  Document ready — {data.get('page_count', '?')} pages processed")
            return status
        if status == "error":
            print(f"  ERROR: {data.get('error_message', 'unknown')}")
            return status
        print(f"  Status: {status} …", end="\r")
        time.sleep(POLL_INTERVAL)


def query_collection(client: httpx.Client, base_url: str, question: str) -> str:
    chunks = []
    with client.stream(
        "POST",
        f"{base_url}/api/v1/documents/collections/{COLLECTION_ID}/query",
        json={"question": question, "top_k": QUERY_TOP_K},
        timeout=300.0,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: "):]
            try:
                msg = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "content":
                chunks.append(msg.get("content", ""))
            elif msg.get("type") == "error":
                print(f"    Stream error: {msg.get('content')}")
                break
            elif msg.get("type") == "done":
                break
    return "".join(chunks)


def score_keywords(answer: str, keywords: list[str]) -> float:
    answer_lower = strip_think_blocks(answer).lower()
    found = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return found / len(keywords) if keywords else 0.0


def score_embedding(model: SentenceTransformer, expected: str, actual: str) -> float:
    actual = strip_think_blocks(actual)
    if not actual.strip():
        return 0.0
    embeddings = model.encode([expected, actual], convert_to_numpy=True)
    sim = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    return float(max(0.0, sim))


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Graph RAG HRÍ Icelandic Benchmark")
    parser.add_argument("--skip-upload", action="store_true",
                        help="Skip PDF upload (assume already processed)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"Server base URL (default: {DEFAULT_BASE_URL})")
    args = parser.parse_args()

    base_url = args.base_url
    client = httpx.Client(timeout=300.0)

    # ── Phase 1: Upload ────────────────────────────────────────────────────
    if not args.skip_upload:
        print("=" * 70)
        print("PHASE 1: Upload Keppnisreglur HRÍ PDF")
        print("=" * 70)
        t0 = time.time()
        doc = upload_pdf(client, base_url, PDF_PATH)
        doc_id = doc["id"]
        print(f"  Uploaded document ID: {doc_id}")
        status = poll_status(client, base_url, doc_id)
        upload_time = time.time() - t0
        print(f"  Processing time: {upload_time:.1f}s")
        if status != "ready":
            print("  Upload failed — aborting.")
            sys.exit(1)
    else:
        print("(Skipping upload — assuming PDF already processed)")
        upload_time = 0

    # ── Phase 2: Query ─────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("PHASE 2: Query 10 Icelandic questions")
    print("=" * 70)

    answers = []
    query_times = []
    for i, item in enumerate(BENCHMARK, 1):
        q = item["question"]
        print(f"\n  Q{i}: {q[:80]}{'…' if len(q) > 80 else ''}")
        t0 = time.time()
        answer = query_collection(client, base_url, q)
        elapsed = time.time() - t0
        query_times.append(elapsed)
        answers.append(answer)
        clean = strip_think_blocks(answer)
        preview = clean[:200].replace("\n", " ")
        if len(clean) > 200:
            preview += " …"
        print(f"  A{i} ({elapsed:.1f}s): {preview}")

    # ── Phase 3: Evaluate ──────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("PHASE 3: Evaluate accuracy")
    print("=" * 70)

    print("\n  Loading embedding model for similarity scoring …")
    model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")

    kw_scores = []
    emb_scores = []
    combined_scores = []

    for i, (item, answer) in enumerate(zip(BENCHMARK, answers), 1):
        kw = score_keywords(answer, item["keywords"])
        emb = score_embedding(model, item["expected"], answer)
        combo = 0.5 * kw + 0.5 * emb
        kw_scores.append(kw)
        emb_scores.append(emb)
        combined_scores.append(combo)

    # ── Report ─────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("BENCHMARK RESULTS — HRÍ Keppnisreglur (Icelandic)")
    print("=" * 70)
    if upload_time:
        print(f"  PDF processing time: {upload_time:.1f}s")
    print()

    hdr = f"  {'#':>2}  {'Keywords':>8}  {'Embed':>6}  {'Combined':>8}  {'Time':>6}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for i in range(len(BENCHMARK)):
        print(
            f"  {i+1:>2}  {kw_scores[i]:>7.0%}  {emb_scores[i]:>6.0%}  "
            f"{combined_scores[i]:>7.0%}  {query_times[i]:>5.1f}s"
        )

    print("  " + "-" * (len(hdr) - 2))

    avg_kw = np.mean(kw_scores)
    avg_emb = np.mean(emb_scores)
    avg_combo = np.mean(combined_scores)
    avg_time = np.mean(query_times)

    print(
        f"  {'Avg':>2}  {avg_kw:>7.0%}  {avg_emb:>6.0%}  "
        f"{avg_combo:>7.0%}  {avg_time:>5.1f}s"
    )

    print()
    target = 0.70
    if avg_combo >= target:
        print(f"  PASS: Average combined score {avg_combo:.0%} >= {target:.0%} target")
    else:
        print(f"  BELOW TARGET: Average combined score {avg_combo:.0%} < {target:.0%} target")

    # ── Detailed answers ───────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("DETAILED ANSWERS")
    print("=" * 70)
    for i, (item, answer) in enumerate(zip(BENCHMARK, answers), 1):
        clean = strip_think_blocks(answer)
        kw_count = sum(1 for kw in item["keywords"] if kw.lower() in clean.lower())
        print(f"\n  Q{i}: {item['question']}")
        print(f"  Keywords matched: {score_keywords(answer, item['keywords']):.0%} "
              f"({kw_count}/{len(item['keywords'])})")
        missed = [kw for kw in item["keywords"] if kw.lower() not in clean.lower()]
        if missed:
            print(f"  Missed keywords: {missed}")
        print(f"  Answer:\n    {clean[:600]}")
        if len(clean) > 600:
            print("    …")

    print()
    return 0 if avg_combo >= target else 1


if __name__ == "__main__":
    sys.exit(main())
