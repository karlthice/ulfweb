#!/usr/bin/env python3
"""
Graph RAG FIA F1 2026 Regulations Benchmark

Uploads three F1 regulation PDFs (Sections A, B, C) to collection 3,
queries 10 regulation questions of increasing difficulty, and scores
retrieval accuracy via keyword matching and embedding cosine similarity.

Usage:
    python3 tests/test_graphrag_f1.py [--skip-upload] [--base-url URL]
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
COLLECTION_ID = 3
POLL_INTERVAL = 3  # seconds between status polls
QUERY_TOP_K = 10

PDF_FILES = [
    "/home/karlth/Downloads/FIA 2026 F1 Regulations - Section A [General Regulatory Provisions] - Iss 01 - 2025-12-10.pdf",
    "/home/karlth/Downloads/FIA 2026 F1 Regulations - Section B [Sporting] - Iss 04 - 2025-12-10.pdf",
    "/home/karlth/Downloads/FIA 2026 F1 Regulations - Section C [Technical] - Iss 15 - 2025-12-10.pdf",
]

# ── Benchmark Q&A pairs (increasing difficulty) ────────────────────────────

BENCHMARK = [
    # Level 1: Easy (Basic Definitions and Facts)
    {
        "question": "What is the deadline for an F1 team to declare the mass of oil contained in each oil tank (except the main tank) before a Total Time Classified Session (TTCS)?",
        "expected": (
            "The mass of oil must be declared to the FIA one hour before the "
            "scheduled start of any TTCS."
        ),
        "keywords": ["one hour", "before", "scheduled start", "TTCS", "declared", "FIA"],
    },
    {
        "question": "What color requirements apply to the external surface of the Energy Store (ES) Main Enclosure?",
        "expected": (
            "At least 70% of the ES Main Enclosure external surface must be orange "
            "colored. Any RAL color code within the range from RAL 2003 to RAL 2011 "
            "may be used, with the specific exception of RAL 2007."
        ),
        "keywords": ["70%", "orange", "RAL 2003", "RAL 2011", "RAL 2007", "exception"],
    },
    {
        "question": "What is the maximum allowed pressure setting for the pressure relief valve fitted to a coolant header tank?",
        "expected": (
            "The pressure relief valve must be set to a maximum of 3.75 barG."
        ),
        "keywords": ["3.75", "barG", "pressure relief valve", "coolant header tank"],
    },
    # Level 2: Medium (Specific Rules and Procedures)
    {
        "question": "Under what conditions might a driver's ability to use Override Mode be disabled during a Qualifying Session (Q) or Sprint Qualifying (SQ)?",
        "expected": (
            "If disabled at any time during any of the three periods of Sprint "
            "Qualifying (SQ1, SQ2, or SQ3) or Qualifying (Q1, Q2, or Q3), it will "
            "remain disabled for the remainder of the relevant period. Furthermore, "
            "if yellow or double yellow flags are shown in a sector, the Race Director "
            "may disable activation in that sector until the flags are withdrawn."
        ),
        "keywords": ["disabled", "remainder", "period", "yellow", "flags",
                      "Race Director", "sector", "withdrawn"],
    },
    {
        "question": "What is the maximum allowed aspect ratio for the external cross-section of a Suspension Fairing, and how is this ratio calculated?",
        "expected": (
            "The aspect ratio must be no greater than 3.5:1. It is calculated as the "
            "ratio of the major axis to the maximum thickness, measured in the "
            "direction normal to the major axis."
        ),
        "keywords": ["3.5", "aspect ratio", "major axis", "maximum thickness", "normal"],
    },
    {
        "question": "If a driver receives a time or drive-through penalty but cannot serve it due to retiring or being unclassified in the Total Time Classified Session (TTCS), what action can the stewards take?",
        "expected": (
            "The stewards may impose a grid place penalty on the driver at their "
            "next Race."
        ),
        "keywords": ["stewards", "grid place penalty", "next Race"],
    },
    # Level 3: Hard (Complex Constraints and Interconnected Rules)
    {
        "question": "What are the specific electrical resistance limits for equipotential bonding paths to the Car Main Ground, and between any two Exposed Conductive Parts of the high voltage system?",
        "expected": (
            "The resistance of potential equalization paths connected to the Car Main "
            "Ground must not exceed 5.0 ohm. The resistance measured between any two "
            "Exposed Conductive Parts of the high voltage system must not exceed 0.1 ohm."
        ),
        "keywords": ["5.0", "0.1", "Car Main Ground", "Exposed Conductive Parts",
                      "high voltage", "resistance"],
    },
    {
        "question": "How is a Gurney defined in terms of its physical dimensions and bonding flange limits on an aerodynamic profile's trailing edge?",
        "expected": (
            "A Gurney must comprise a flat section up to 1mm thick. It includes a "
            "bonding flange on the wing's surface that may extend no more than 20mm "
            "in length and 1mm in thickness. Additionally, no part of the Gurney can "
            "extend beyond a line perpendicular to the surface at the profile's "
            "trailing edge."
        ),
        "keywords": ["1mm", "flat", "bonding flange", "20mm", "perpendicular",
                      "trailing edge"],
    },
    # Level 4: Expert (Highly Specific Materials and Exemptions)
    {
        "question": "What are the maximum permitted material properties (tensile modulus, tensile strength, and density) for carbon fiber composites used outside the Power Unit perimeter?",
        "expected": (
            "A nominal tensile modulus of 550 GPa or less. A nominal tensile strength "
            "of 7100 MPa or less. A density of 1.92 g/cm3 or less."
        ),
        "keywords": ["550", "GPa", "7100", "MPa", "1.92", "density"],
    },
    {
        "question": "What are the five specific design constraints placed on Floor Body Stays to make them exempt from general aerodynamic component regulations?",
        "expected": (
            "Up to three Floor Body Stays are permitted, may only take load in tension, "
            "and must: have a single inboard attachment location between X_F=1775 and "
            "X_R=275; be fixed on its inboard end to the entirely sprung part of the car; "
            "be fixed on its outboard end to Floor Bodywork; have a circular cross-section "
            "with a diameter no more than 5mm except within 25mm of attachment points or "
            "within 10mm of any adjustment mechanism; when viewed from below be fully "
            "obscured with Floor Bodywork in place."
        ),
        "keywords": ["three", "tension", "inboard", "sprung", "outboard",
                      "Floor Bodywork", "circular", "5mm", "25mm", "obscured"],
    },
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def upload_pdf(client: httpx.Client, base_url: str, pdf_path: str) -> dict:
    """Upload a PDF to collection and return document metadata."""
    filename = pdf_path.rsplit("/", 1)[-1]
    with open(pdf_path, "rb") as f:
        resp = client.post(
            f"{base_url}/api/v1/documents/collections/{COLLECTION_ID}/documents",
            files={"file": (filename, f, "application/pdf")},
        )
    resp.raise_for_status()
    return resp.json()


def poll_status(client: httpx.Client, base_url: str, doc_id: int) -> str:
    """Poll document processing status until ready or error."""
    while True:
        resp = client.get(f"{base_url}/api/v1/documents/documents/{doc_id}/status")
        resp.raise_for_status()
        data = resp.json()
        status = data["status"]
        if status == "ready":
            print(f"    Ready — {data.get('page_count', '?')} pages processed")
            return status
        if status == "error":
            print(f"    ERROR: {data.get('error_message', 'unknown')}")
            return status
        print(f"    Status: {status} …", end="\r")
        time.sleep(POLL_INTERVAL)


def query_collection(client: httpx.Client, base_url: str, question: str) -> str:
    """Send a query and collect the full streamed answer."""
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
    """Fraction of expected keywords found (case-insensitive) in answer."""
    answer_lower = strip_think_blocks(answer).lower()
    found = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return found / len(keywords) if keywords else 0.0


def score_embedding(model: SentenceTransformer, expected: str, actual: str) -> float:
    """Cosine similarity between expected and actual answer embeddings."""
    actual = strip_think_blocks(actual)
    if not actual.strip():
        return 0.0
    embeddings = model.encode([expected, actual], convert_to_numpy=True)
    sim = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    return float(max(0.0, sim))  # clamp negatives


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Graph RAG F1 2026 Regulations Benchmark")
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
        print("PHASE 1: Upload F1 2026 Regulation PDFs (Sections A, B, C)")
        print("=" * 70)
        t0 = time.time()

        for pdf_path in PDF_FILES:
            short_name = pdf_path.rsplit("/", 1)[-1][:60]
            print(f"\n  Uploading: {short_name}…")
            doc = upload_pdf(client, base_url, pdf_path)
            doc_id = doc["id"]
            print(f"    Document ID: {doc_id}")
            status = poll_status(client, base_url, doc_id)
            if status != "ready":
                print(f"    Upload failed for {short_name} — aborting.")
                sys.exit(1)

        upload_time = time.time() - t0
        print(f"\n  Total processing time for all 3 PDFs: {upload_time:.1f}s")
    else:
        print("(Skipping upload — assuming PDFs already processed in collection)")
        upload_time = 0

    # ── Phase 2: Query ─────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("PHASE 2: Query 10 F1 regulation questions")
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
    print("BENCHMARK RESULTS — FIA F1 2026 Regulations")
    print("=" * 70)
    if upload_time:
        print(f"  PDF processing time (3 documents): {upload_time:.1f}s")
    print()

    levels = ["Easy", "Easy", "Easy", "Medium", "Medium", "Medium",
              "Hard", "Hard", "Expert", "Expert"]

    hdr = f"  {'#':>2}  {'Level':>7}  {'Keywords':>8}  {'Embed':>6}  {'Combined':>8}  {'Time':>6}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for i in range(len(BENCHMARK)):
        print(
            f"  {i+1:>2}  {levels[i]:>7}  {kw_scores[i]:>7.0%}  {emb_scores[i]:>6.0%}  "
            f"{combined_scores[i]:>7.0%}  {query_times[i]:>5.1f}s"
        )

    print("  " + "-" * (len(hdr) - 2))

    avg_kw = np.mean(kw_scores)
    avg_emb = np.mean(emb_scores)
    avg_combo = np.mean(combined_scores)
    avg_time = np.mean(query_times)

    print(
        f"  {'':>2}  {'Avg':>7}  {avg_kw:>7.0%}  {avg_emb:>6.0%}  "
        f"{avg_combo:>7.0%}  {avg_time:>5.1f}s"
    )

    # Per-level averages
    print()
    for level in ["Easy", "Medium", "Hard", "Expert"]:
        idxs = [i for i, l in enumerate(levels) if l == level]
        if idxs:
            lvl_combo = np.mean([combined_scores[i] for i in idxs])
            lvl_kw = np.mean([kw_scores[i] for i in idxs])
            print(f"  {level:>7} avg: Keywords {lvl_kw:.0%}  Combined {lvl_combo:.0%}")

    print()
    target = 0.70
    if avg_combo >= target:
        print(f"  PASS: Average combined score {avg_combo:.0%} >= {target:.0%} target")
    else:
        print(f"  BELOW TARGET: Average combined score {avg_combo:.0%} < {target:.0%} target")

    # ── Detailed answers (for debugging) ───────────────────────────────────
    print()
    print("=" * 70)
    print("DETAILED ANSWERS")
    print("=" * 70)
    for i, (item, answer) in enumerate(zip(BENCHMARK, answers), 1):
        clean = strip_think_blocks(answer)
        print(f"\n  Q{i} [{levels[i-1]}]: {item['question']}")
        kw_count = sum(1 for kw in item["keywords"] if kw.lower() in clean.lower())
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
