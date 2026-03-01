#!/usr/bin/env python3
"""
Graph RAG Chess Rules Benchmark

Uploads LawsOfChess.pdf to collection 2, queries 10 chess-rules questions
of increasing difficulty, and scores retrieval accuracy via keyword matching
and embedding cosine similarity.

Usage:
    python3 tests/test_graphrag_chess.py [--skip-upload] [--base-url URL]
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

BASE_URL = "http://localhost:8000"
COLLECTION_ID = 2
PDF_PATH = "/home/karlth/Downloads/LawsOfChess.pdf"
POLL_INTERVAL = 3  # seconds between status polls
QUERY_TOP_K = 10

# ── Benchmark Q&A pairs (increasing difficulty) ────────────────────────────

BENCHMARK = [
    # 1 – Easy: basic board facts
    {
        "question": "How many squares are on a chessboard and how is it structured?",
        "expected": (
            "The chessboard is an 8 x 8 grid of 64 equal squares, "
            "alternately light (white) and dark (black). "
            "The vertical columns are called files, the horizontal rows are called ranks, "
            "and straight lines of same-colour squares are called diagonals."
        ),
        "keywords": ["64", "8", "files", "ranks", "diagonals", "light", "dark"],
    },
    # 2 – Easy: piece movement
    {
        "question": "How does the bishop move in chess?",
        "expected": (
            "The bishop may move to any square along a diagonal on which it stands. "
            "It cannot move over intervening pieces."
        ),
        "keywords": ["diagonal", "cannot", "intervening"],
    },
    # 3 – Easy: objective of the game
    {
        "question": "What is the objective of a chess game?",
        "expected": (
            "The objective is to place the opponent's king under attack (in check) "
            "in such a way that the opponent has no legal move. The player who achieves "
            "this goal is said to have checkmated the opponent's king and wins the game."
        ),
        "keywords": ["checkmate", "king", "attack", "no legal move", "won"],
    },
    # 4 – Medium: special pawn move
    {
        "question": "What is en passant in chess?",
        "expected": (
            "En passant is a special pawn capture. A pawn attacking a square crossed by "
            "an opponent's pawn which has advanced two squares in one move from its "
            "original square may capture this opponent's pawn as though the latter had "
            "been moved only one square. This capture is only legal on the move "
            "immediately following this advance."
        ),
        "keywords": ["en passant", "pawn", "two squares", "one square", "only legal", "following"],
    },
    # 5 – Medium: castling conditions
    {
        "question": "Under what conditions is castling permanently lost?",
        "expected": (
            "The right to castle is permanently lost if the king has already moved, "
            "or with a rook that has already moved. Castling is also temporarily "
            "prevented if the king's square, the square it must cross, or the square "
            "it is to occupy is attacked, or if there is any piece between the king "
            "and the rook."
        ),
        "keywords": ["king", "moved", "rook", "moved", "attacked", "piece between"],
    },
    # 6 – Medium: stalemate
    {
        "question": "What is stalemate in chess?",
        "expected": (
            "Stalemate occurs when the player to move has no legal move and his king "
            "is not in check. The game is drawn. This immediately ends the game, "
            "provided that the move producing the stalemate position was legal."
        ),
        "keywords": ["stalemate", "no legal move", "not in check", "drawn"],
    },
    # 7 – Medium: promotion
    {
        "question": "What happens when a pawn reaches the last rank? What pieces can it become?",
        "expected": (
            "When a pawn reaches the rank furthest from its starting position it must "
            "be exchanged as part of the same move for a new queen, rook, bishop or "
            "knight of the same colour. The player's choice is not restricted to "
            "pieces that have been captured previously. This is called promotion and "
            "the effect of the new piece is immediate."
        ),
        "keywords": ["promotion", "queen", "rook", "bishop", "knight", "same colour",
                      "not restricted", "immediate"],
    },
    # 8 – Hard: fifty-move rule
    {
        "question": "Explain the 50-move draw rule in chess.",
        "expected": (
            "The game may be drawn if each player has made at least the last 50 "
            "consecutive moves without the movement of any pawn and without any "
            "capture. The player having the move writes his move on his scoresheet "
            "and declares to the arbiter his intention to make this move which shall "
            "result in the last 50 moves having been made by each player without "
            "pawn movement or capture."
        ),
        "keywords": ["50", "consecutive", "pawn", "capture", "drawn", "scoresheet", "arbiter"],
    },
    # 9 – Hard: arbiter penalties
    {
        "question": "What penalties can an arbiter apply according to the FIDE Laws of Chess?",
        "expected": (
            "The arbiter can apply one or more of the following penalties: (a) warning, "
            "(b) increasing the remaining time of the opponent, (c) reducing the "
            "remaining time of the offending player, (d) declaring the game to be lost, "
            "(e) reducing the points scored in the game by the offending party, "
            "(f) increasing the points scored in the game by the opponent to the "
            "maximum available for that game, (g) expulsion from the event."
        ),
        "keywords": ["warning", "increasing", "time", "opponent", "reducing", "time",
                      "declaring", "lost", "points", "expulsion"],
    },
    # 10 – Hard: quickplay finish
    {
        "question": "What is a quickplay finish and when can a player claim a draw during one?",
        "expected": (
            "A quickplay finish is the phase of a game when all remaining moves must "
            "be made in a limited time. If the player having the move has less than "
            "two minutes left on his clock, he may claim a draw before his flag falls. "
            "He shall summon the arbiter and may stop the clocks. If the arbiter agrees "
            "the opponent is making no effort to win by normal means, or that it is not "
            "possible to win by normal means, then he shall declare the game drawn."
        ),
        "keywords": ["quickplay finish", "remaining moves", "limited time",
                      "two minutes", "claim a draw", "flag", "arbiter", "normal means"],
    },
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def upload_pdf(client: httpx.Client, base_url: str, pdf_path: str) -> dict:
    """Upload a PDF to collection and return document metadata."""
    with open(pdf_path, "rb") as f:
        resp = client.post(
            f"{base_url}/api/v1/documents/collections/{COLLECTION_ID}/documents",
            files={"file": ("LawsOfChess.pdf", f, "application/pdf")},
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
            print(f"  Document ready — {data.get('page_count', '?')} pages processed")
            return status
        if status == "error":
            print(f"  ERROR: {data.get('error_message', 'unknown')}")
            return status
        print(f"  Status: {status} …")
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


def strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


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
    parser = argparse.ArgumentParser(description="Graph RAG Chess Rules Benchmark")
    parser.add_argument("--skip-upload", action="store_true",
                        help="Skip PDF upload (assume already processed)")
    parser.add_argument("--base-url", default=BASE_URL,
                        help=f"Server base URL (default: {BASE_URL})")
    args = parser.parse_args()

    base_url = args.base_url

    client = httpx.Client(timeout=300.0)

    # ── Phase 1: Upload ────────────────────────────────────────────────────
    if not args.skip_upload:
        print("=" * 70)
        print("PHASE 1: Upload LawsOfChess.pdf")
        print("=" * 70)
        t0 = time.time()
        doc = upload_pdf(client, base_url, PDF_PATH)
        doc_id = doc["id"]
        print(f"  Uploaded document ID: {doc_id}")
        status = poll_status(client, base_url, doc_id)
        upload_time = time.time() - t0
        print(f"  Total processing time: {upload_time:.1f}s")
        if status != "ready":
            print("  Upload failed — aborting.")
            sys.exit(1)
    else:
        print("(Skipping upload — assuming PDF already processed in collection)")
        upload_time = 0

    # ── Phase 2: Query ─────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("PHASE 2: Query 10 chess-rules questions")
    print("=" * 70)

    answers = []
    query_times = []
    for i, item in enumerate(BENCHMARK, 1):
        q = item["question"]
        print(f"\n  Q{i}: {q}")
        t0 = time.time()
        answer = query_collection(client, base_url, q)
        elapsed = time.time() - t0
        query_times.append(elapsed)
        answers.append(answer)
        # Show truncated answer
        preview = answer[:200].replace("\n", " ")
        if len(answer) > 200:
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
    print("BENCHMARK RESULTS")
    print("=" * 70)
    if upload_time:
        print(f"  PDF processing time: {upload_time:.1f}s")
    print()

    hdr = f"  {'#':>2}  {'Keywords':>8}  {'Embedding':>9}  {'Combined':>8}  {'Time':>6}  Question"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for i, item in enumerate(BENCHMARK):
        q_short = item["question"][:48]
        if len(item["question"]) > 48:
            q_short += "…"
        print(
            f"  {i+1:>2}  {kw_scores[i]:>7.0%}  {emb_scores[i]:>9.0%}  "
            f"{combined_scores[i]:>7.0%}  {query_times[i]:>5.1f}s  {q_short}"
        )

    print("  " + "-" * (len(hdr) - 2))

    avg_kw = np.mean(kw_scores)
    avg_emb = np.mean(emb_scores)
    avg_combo = np.mean(combined_scores)
    avg_time = np.mean(query_times)

    print(
        f"  {'Avg':>2}  {avg_kw:>7.0%}  {avg_emb:>9.0%}  "
        f"{avg_combo:>7.0%}  {avg_time:>5.1f}s"
    )

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
        print(f"\n  Q{i}: {item['question']}")
        print(f"  Keywords matched: {score_keywords(answer, item['keywords']):.0%} "
              f"({sum(1 for kw in item['keywords'] if kw.lower() in clean.lower())}"
              f"/{len(item['keywords'])})")
        # Show which keywords were missed
        missed = [kw for kw in item["keywords"] if kw.lower() not in clean.lower()]
        if missed:
            print(f"  Missed keywords: {missed}")
        print(f"  Answer:\n    {clean[:500]}")
        if len(clean) > 500:
            print("    …")

    print()
    return 0 if avg_combo >= target else 1


if __name__ == "__main__":
    sys.exit(main())
