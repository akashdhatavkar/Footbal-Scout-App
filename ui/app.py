"""Streamlit frontend for the Football Stats App.

Run locally:
    streamlit run ui/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pipeline import Pipeline  # noqa: E402

st.set_page_config(page_title="Football Stats App", layout="wide")


@st.cache_resource
def get_pipeline() -> Pipeline:
    return Pipeline()


def fmt_value(value) -> str:
    if value is None:
        return "—"
    return f"€{value / 1_000_000:,.1f}m"


def main() -> None:
    st.title("⚽ Football Stats App")
    st.caption(
        "Search any player to view their statistical profile, current market value "
        "and the top-5 most similar players worldwide."
    )

    pipeline = get_pipeline()
    corpus = pipeline.corpus

    with st.sidebar:
        st.header("Corpus")
        st.metric("Players indexed", len(corpus))
        k = st.slider("Similar players to show", 1, 10, 5)
        enrich = st.toggle("Live market-value enrichment (Transfermarkt)", value=False)

    query = st.text_input("Player name", placeholder="e.g. Martin Ødegaard")
    if not query:
        st.info("Enter a player name to begin.")
        return

    try:
        result = pipeline.get_similar(query, k=k, enrich_market_value=enrich)
    except LookupError:
        st.error(f"Player not found in corpus: **{query}**")
        st.write("Try one of:", ", ".join(p.name for p in corpus[:12]), "…")
        return

    player = result["player"]
    match_type = result["match_type"]
    confidence = result["confidence"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Name", player["name"])
    col2.metric("Club", player["club"])
    col3.metric("League", player["league"])
    col4.metric("Market value", fmt_value(player["market_value_eur"]))
    st.caption(
        f"Position: {player['position']} · Age: {player['age']} · "
        f"Match: {match_type} ({confidence:.0f}%)"
    )

    st.subheader("Top similar players (weighted)")
    rows = []
    for s in result["similar_players"]:
        p = s["player"]
        rows.append(
            {
                "#": s["rank"],
                "Player": p["name"],
                "Club": p["club"],
                "League": p["league"],
                "Position": p["position"],
                "Age": p["age"],
                "Market value": fmt_value(p["market_value_eur"]),
                "Cosine": f"{s['cosine_similarity']:.3f}",
                "League ×": f"{s['league_multiplier']:.2f}",
                "Exp ×": f"{s['experience_multiplier']:.2f}",
                "Final score": f"{s['final_score']:.4f}",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    with st.expander("Full statistical profile (per 90)"):
        st.json(player["features"])


if __name__ == "__main__":
    main()
