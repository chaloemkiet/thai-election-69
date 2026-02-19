# =========================================================
# IMPORTS & CONFIG
# =========================================================
import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import json

st.set_page_config(
    page_title="Election 69 Dashboard",
    page_icon="🗳️",
    layout="wide"
)

# =========================================================
# UTILITIES
# =========================================================
def fetch_local_json(path: str) -> dict:
    """Load JSON from local snapshot file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_name(name: str) -> str:
    """Remove Thai prefixes from names."""
    prefixes = ["นาย", "นางสาว", "นาง"]
    for prefix in prefixes:
        if name.startswith(prefix):
            return name.replace(prefix, "", 1).strip()
    return name.strip()


# =========================================================
# LOAD DATA (FROM SNAPSHOT FILES)
# =========================================================
@st.cache_data
def load_data():

    # ---------- Load raw JSON ----------
    province_json = fetch_local_json("data/info_province.json")
    constituency_json = fetch_local_json("data/info_constituency.json")
    party_json = fetch_local_json("data/info_party_overview.json")
    mp_candidate_json = fetch_local_json("data/info_mp_candidate.json")
    party_candidate_json = fetch_local_json("data/info_party_candidate.json")
    stats_cons_json = fetch_local_json("data/stats_cons.json")
    stats_party_json = fetch_local_json("data/stats_party.json")

    # ---------- Dimension Tables ----------
    df_province = pd.json_normalize(province_json["province"])
    df_constituency = pd.json_normalize(constituency_json)
    df_party = pd.json_normalize(party_json)
    df_mp_candidate = pd.json_normalize(mp_candidate_json)

    # ---------- Constituency Summary ----------
    summary_rows = []

    for province in stats_cons_json["result_province"]:
        for cons in province["constituencies"]:
            summary_rows.append({
                "cons_id": cons.get("cons_id"),
                "turn_out": cons.get("turn_out"),
                "valid_votes": cons.get("valid_votes"),
                "invalid_votes": cons.get("invalid_votes"),
                "blank_votes": cons.get("blank_votes"),
                "party_list_turn_out": cons.get("party_list_turn_out"),
                "party_list_valid_votes": cons.get("party_list_valid_votes"),
                "party_list_invalid_votes": cons.get("party_list_invalid_votes"),
                "party_list_blank_votes": cons.get("party_list_blank_votes"),
                "counted_vote_stations": cons.get("counted_vote_stations"),
                "percent_count": cons.get("percent_count"),
            })

    df_cons_summary = pd.DataFrame(summary_rows)

    # ---------- Candidate Votes ----------
    candidate_rows = []

    for province in stats_cons_json["result_province"]:
        for cons in province["constituencies"]:
            for candidate in cons.get("candidates", []):
                candidate_rows.append({
                    "cons_id": cons.get("cons_id"),
                    "mp_app_id": candidate.get("mp_app_id"),
                    "mp_app_vote": candidate.get("mp_app_vote"),
                    "mp_app_vote_percent": candidate.get("mp_app_vote_percent"),
                    "mp_app_rank": candidate.get("mp_app_rank"),
                    "party_id": candidate.get("party_id"),
                })

    df_cons_candidate = pd.DataFrame(candidate_rows)

    return (
        df_province,
        df_constituency,
        df_party,
        df_mp_candidate,
        df_cons_summary,
        df_cons_candidate,
    )


# =========================================================
# DATA PREPARATION
# =========================================================
(
    df_province,
    df_constituency,
    df_party,
    df_mp_candidate,
    df_cons_summary,
    df_cons_candidate,
) = load_data()


# ---------- Join candidate name ----------
df_cons_candidate = df_cons_candidate.merge(
    df_mp_candidate[["mp_app_id", "mp_app_name"]],
    on="mp_app_id",
    how="left"
)

# ---------- Join party name ----------
df_cons_candidate = df_cons_candidate.merge(
    df_party[["party_id", "party_name"]],
    on="party_id",
    how="left"
)

# ---------- Calculate Margin ----------
df_top2 = df_cons_candidate[df_cons_candidate["mp_app_rank"] <= 2]

margin_df = (
    df_top2.sort_values(["cons_id", "mp_app_rank"])
    .groupby("cons_id")
    .apply(lambda x: x.iloc[0]["mp_app_vote_percent"] - x.iloc[1]["mp_app_vote_percent"])
    .reset_index(name="margin_percent")
)

df_cons_summary = df_cons_summary.merge(margin_df, on="cons_id", how="left")

# ---------- Calculate ENP ----------
def calculate_enp(group):
    shares = group["mp_app_vote_percent"] / 100
    return 1 / np.sum(shares**2)

enp_df = (
    df_cons_candidate.groupby("cons_id")
    .apply(calculate_enp)
    .reset_index(name="ENP")
)

df_cons_summary = df_cons_summary.merge(enp_df, on="cons_id", how="left")

# ---------- Join Zone + Province ----------
df_cons_summary = df_cons_summary.merge(
    df_constituency[["cons_id", "prov_id", "zone"]],
    on="cons_id",
    how="left"
)

df_cons_summary = df_cons_summary.merge(
    df_province[["prov_id", "province"]],
    on="prov_id",
    how="left"
)


# =========================================================
# DASHBOARD UI
# =========================================================
st.title("🗳 Election 69 – Analytical Dashboard")

# ---------- KPI ----------
col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Districts", df_cons_summary["cons_id"].nunique())
col2.metric("Total Voters", f"{df_cons_summary['turn_out'].sum():,.0f}")
col3.metric("Average Margin", f"{df_cons_summary['margin_percent'].mean():.2f}%")
col4.metric("Average ENP", f"{df_cons_summary['ENP'].mean():.2f}")

st.divider()

# =========================================================
# AVG MARGIN BY PROVINCE
# =========================================================
province_margin = (
    df_cons_summary.groupby("province")
    .agg(avg_margin=("margin_percent", "mean"))
    .reset_index()
    .sort_values("avg_margin")
)

st.subheader("📊 Average Margin by Province")

fig_margin = px.bar(
    province_margin,
    x="avg_margin",
    y="province",
    orientation="h",
    color="avg_margin",
    color_continuous_scale="RdYlGn_r",
)

fig_margin.update_layout(
    xaxis_title="Average Margin (%)",
    yaxis_title="Province",
    height=1200
)

st.plotly_chart(fig_margin, use_container_width=True)

st.divider()

# =========================================================
# ENP vs MARGIN SCATTER (INTERACTIVE)
# =========================================================
st.subheader("🧠 Fragmentation (ENP) vs Margin")

plot_df = df_cons_summary.dropna(subset=["ENP", "margin_percent"]).copy()

if "selected_province" not in st.session_state:
    st.session_state.selected_province = None

if st.session_state.selected_province:
    plot_df["color_group"] = np.where(
        plot_df["province"] == st.session_state.selected_province,
        "Selected Province",
        "Other Provinces"
    )

    fig = px.scatter(
        plot_df,
        x="ENP",
        y="margin_percent",
        color="color_group",
        color_discrete_map={
            "Selected Province": "red",
            "Other Provinces": "lightgray"
        },
        hover_data=["cons_id", "province", "zone"],
    )
else:
    fig = px.scatter(
        plot_df,
        x="ENP",
        y="margin_percent",
        color="margin_percent",
        color_continuous_scale="RdYlGn_r",
        hover_data=["cons_id", "province", "zone"],
    )

fig.update_layout(
    height=600,
    clickmode="event+select",
    dragmode="select"
)

event = st.plotly_chart(
    fig,
    use_container_width=True,
    key="scatter_native",
    on_select="rerun"
)

if event and "selection" in event:
    indices = event["selection"]["point_indices"]
    if indices:
        idx = indices[0]
        st.session_state.selected_province = plot_df.iloc[idx]["province"]
        st.rerun()

if st.session_state.selected_province:
    if st.button("Reset Highlight"):
        st.session_state.selected_province = None
        st.rerun()

st.markdown("""
### 📌 How to interpret ENP vs Margin

- 🔼 ENP สูง + 🔽 Margin ต่ำ → หลายพรรคแข่งกันสูสี  
- 🔽 ENP ต่ำ + 🔼 Margin สูง → เขตฐานเสียงแข็ง  
- 🔼 ENP สูง + 🔼 Margin สูง → หลายพรรคลงแข่ง แต่มีพรรคเด่น  
- 🔽 ENP ต่ำ + 🔽 Margin ต่ำ → แข่งหลัก ๆ 2 พรรค สูสี
""")

