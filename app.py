import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import numpy as np

st.set_page_config(
    page_title="Election 69 Full Dashboard",
    page_icon="🗳",
    layout="wide"
)

import streamlit as st
import pandas as pd
import requests
import plotly.express as px


# =========================================================
# CONFIG
# =========================================================
URLS = {
    "info_province": "https://static-ectreport69.ect.go.th/data/data/refs/info_province.json",
    "info_constituency": "https://static-ectreport69.ect.go.th/data/data/refs/info_constituency.json",
    "info_party_overview": "https://static-ectreport69.ect.go.th/data/data/refs/info_party_overview.json",
    "info_mp_candidate": "https://static-ectreport69.ect.go.th/data/data/refs/info_mp_candidate.json",
    "info_party_candidate": "https://static-ectreport69.ect.go.th/data/data/refs/info_party_candidate.json",
    "stats_cons": "https://stats-ectreport69.ect.go.th/data/records/stats_cons.json",
    "stats_party": "https://stats-ectreport69.ect.go.th/data/records/stats_party.json",
}


# =========================================================
# UTILITY FUNCTIONS
# =========================================================
import json

def fetch_local_json(path: str) -> dict:
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
# LOAD DATA (Cached 5 minutes)
# =========================================================
@st.cache_data(ttl=300)
def load_data():

    # -------------------------
    # Fetch Raw JSON
    # -------------------------
    province_json = fetch_json(URLS["info_province"])
    constituency_json = fetch_json(URLS["info_constituency"])
    party_json = fetch_json(URLS["info_party_overview"])
    mp_candidate_json = fetch_json(URLS["info_mp_candidate"])
    party_candidate_json = fetch_json(URLS["info_party_candidate"])
    stats_cons_json = fetch_json(URLS["stats_cons"])
    stats_party_json = fetch_json(URLS["stats_party"])

    # -------------------------
    # Dimension Tables
    # -------------------------
    df_province = pd.json_normalize(province_json["province"])
    df_constituency = pd.json_normalize(constituency_json)
    df_party = pd.json_normalize(party_json)
    df_mp_candidate = pd.json_normalize(mp_candidate_json)

    # -------------------------
    # Party List Candidates
    # -------------------------
    party_rows = []

    for party in party_candidate_json:
        party_no = party["party_no"]

        pm_names = set()
        if "pm_candidates" in party:
            pm_names = {
                clean_name(pm["name"])
                for pm in party["pm_candidates"]
            }

        for candidate in party["party_list_candidates"]:
            original_name = candidate["name"]
            cleaned_name = clean_name(original_name)

            party_rows.append(
                {
                    "party_no": party_no,
                    "list_no": candidate["list_no"],
                    "name": original_name,
                    "image_url": candidate["image_url"],
                    "pm_candidates": cleaned_name in pm_names,
                }
            )

    df_party_candidate = pd.DataFrame(party_rows)

    # -------------------------
    # Stats - Constituency Summary
    # -------------------------
    summary_rows = []

    for province in stats_cons_json["result_province"]:
        for cons in province["constituencies"]:
            summary_rows.append(
                {
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
                }
            )

    df_cons_summary = pd.DataFrame(summary_rows)

    # -------------------------
    # Stats - Candidate Votes
    # -------------------------
    candidate_rows = []

    for province in stats_cons_json["result_province"]:
        for cons in province["constituencies"]:
            cons_id = cons.get("cons_id")

            for candidate in cons.get("candidates", []):
                candidate_rows.append(
                    {
                        "cons_id": cons_id,
                        "mp_app_id": candidate.get("mp_app_id"),
                        "mp_app_vote": candidate.get("mp_app_vote"),
                        "mp_app_vote_percent": candidate.get("mp_app_vote_percent"),
                        "mp_app_rank": candidate.get("mp_app_rank"),
                        "party_id": candidate.get("party_id"),
                    }
                )

    df_cons_candidate = pd.DataFrame(candidate_rows)

    # -------------------------
    # Party Stats
    # -------------------------
    df_stats_cons = pd.json_normalize(stats_cons_json)
    df_stats_party = pd.json_normalize(stats_party_json)

    return (
        df_province,
        df_constituency,
        df_party,
        df_mp_candidate,
        df_party_candidate,
        df_stats_cons,
        df_cons_summary,
        df_cons_candidate,
        df_stats_party,
    )

(
    df_province,
    df_constituency,
    df_party,
    df_mp_candidate,
    df_party_candidate,
    df_stats_cons,
    df_cons_summary,
    df_cons_candidate,
    df_stats_party,
) = load_data()

# =========================================================
# JOIN DIMENSION DATA
# =========================================================

# join ชื่อผู้สมัคร (ใช้ field ตาม df_mp_candidate ที่คุณ normalize มา)
if "name" in df_mp_candidate.columns:
    df_cons_candidate = df_cons_candidate.merge(
        df_mp_candidate[["mp_app_id", "name"]],
        on="mp_app_id",
        how="left"
    )
else:
    # fallback ป้องกัน error ถ้าชื่อ field ต่าง
    name_col = [c for c in df_mp_candidate.columns if "name" in c.lower()][0]
    df_cons_candidate = df_cons_candidate.merge(
        df_mp_candidate[["mp_app_id", name_col]],
        on="mp_app_id",
        how="left"
    )
    df_cons_candidate = df_cons_candidate.rename(columns={name_col: "name"})

# join พรรค
if "party_name" in df_party.columns:
    df_cons_candidate = df_cons_candidate.merge(
        df_party[["party_id", "party_name"]],
        on="party_id",
        how="left"
    )


# =========================================================
# MARGIN ANALYSIS (เขตสูสี / ชนะขาด)
# =========================================================

df_top2 = df_cons_candidate[df_cons_candidate["mp_app_rank"] <= 2]

margin_df = (
    df_top2.sort_values(["cons_id", "mp_app_rank"])
    .groupby("cons_id")
    .apply(
        lambda x: x.iloc[0]["mp_app_vote_percent"]
        - x.iloc[1]["mp_app_vote_percent"]
        if len(x) > 1 else None
    )
    .reset_index(name="margin_percent")
)

df_cons_summary = df_cons_summary.merge(
    margin_df,
    on="cons_id",
    how="left"
)


# =========================================================
# EFFECTIVE NUMBER OF PARTIES (ENP)
# =========================================================

def calculate_enp(group):
    shares = group["mp_app_vote_percent"] / 100
    return 1 / np.sum(shares**2)

enp_df = (
    df_cons_candidate.groupby("cons_id")
    .apply(calculate_enp)
    .reset_index(name="ENP")
)

df_cons_summary = df_cons_summary.merge(
    enp_df,
    on="cons_id",
    how="left"
)

# =========================================================
# JOIN ZONE FROM df_constituency
# =========================================================

# ตรวจว่ามี cons_id ใน df_constituency จริง
if "cons_id" not in df_constituency.columns:
    st.error("df_constituency ไม่มีคอลัมน์ cons_id")
else:
    # ตรวจว่ามี zone จริง
    if "zone" not in df_constituency.columns:
        st.error("df_constituency ไม่มีคอลัมน์ zone")
    else:
        df_cons_summary = df_cons_summary.merge(
            df_constituency[["cons_id", "zone"]],
            on="cons_id",
            how="left"
        )


# =========================================================
# CLOSE RACE / LANDSLIDE TABLES (WITH ZONE)
# =========================================================

close_race = df_cons_summary.sort_values("margin_percent").head(10)
landslide = df_cons_summary.sort_values(
    "margin_percent", ascending=False
).head(10)





# =========================================================
# พรรคที่แพ้เฉือนมากที่สุด
# =========================================================

second_place = df_cons_candidate[df_cons_candidate["mp_app_rank"] == 2]

# หาเขตที่แพ้ไม่เกิน 1%
narrow_loss = second_place[
    second_place["mp_app_vote_percent"] >=
    second_place.groupby("cons_id")["mp_app_vote_percent"].transform("max") - 1
]

if "party_name" in narrow_loss.columns:
    party_narrow_loss = (
        narrow_loss.groupby("party_name")
        .size()
        .reset_index(name="narrow_losses")
        .sort_values("narrow_losses", ascending=False)
    )
else:
    party_narrow_loss = pd.DataFrame()


# =========================================================
# DASHBOARD
# =========================================================

st.title("🗳 Election 69 - Overview")
# st.caption("Built from all 7 ECT APIs")

# KPI
col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Electoral Districts", df_cons_summary["cons_id"].nunique())
col1.caption("จำนวนเขตเลือกตั้งทั้งหมด")
col2.metric("Total Voters", f"{df_cons_summary['turn_out'].sum():,.0f}")
col2.caption("ผู้มาใช้สิทธิเลือกตั้ง")
col3.metric("Margin", f"{df_cons_summary['margin_percent'].mean():.2f}%")
col3.caption("ค่าเฉลี่ยต่อเขตของส่วนต่างคะแนนระหว่างอันดับ 1 และ 2")
col4.metric("Effective Number of Parties", f"{df_cons_summary['ENP'].mean():.2f}")
col4.caption("ค่าเฉลี่ยต่อเขตของจำนวนพรรคที่แข่งขันกันจริง")

st.divider()

# # Close vs Landslide
# col1, col2 = st.columns(2)

# with col1:
#     st.subheader("🔥 Top 10 เขตสูสี")
#     st.dataframe(
#         close_race[["cons_id", "zone", "margin_percent"]],
#         use_container_width=True
#     )

# with col2:
#     st.subheader("🏆 Top 10 เขตชนะขาด")
#     st.dataframe(
#         landslide[["cons_id", "zone", "margin_percent"]],
#         use_container_width=True
#     )

# =========================================================
# AVG MARGIN BY PROVINCE
# =========================================================

# 1) join cons -> province_id
df_cons_summary = df_cons_summary.merge(
    df_constituency[["cons_id", "prov_id"]],
    on="cons_id",
    how="left"
)

# 2) join province_id -> province name
df_cons_summary = df_cons_summary.merge(
    df_province[["prov_id", "province"]],
    on="prov_id",
    how="left"
)

# 3) aggregate ค่าเฉลี่ย margin ต่อจังหวัด
province_margin = (
    df_cons_summary.groupby("province")
    .agg(avg_margin=("margin_percent", "mean"))
    .reset_index()
    .sort_values("avg_margin")
)

# =========================================================
# BAR CHART
# =========================================================

st.subheader("📊 ค่าเฉลี่ยส่วนต่างคะแนนต่อจังหวัด")

fig_province_margin = px.bar(
    province_margin,
    x="avg_margin",
    y="province",
    orientation="h",
    color="avg_margin",
    color_continuous_scale="RdYlGn_r",
)

fig_province_margin.update_layout(
    xaxis_title="ค่าเฉลี่ยส่วนต่างคะแนน (%)",
    yaxis_title="จังหวัด",
    height=1200
)

st.plotly_chart(fig_province_margin, use_container_width=True)

st.divider()

# # Turnout Distribution
# st.subheader("📊 Turnout Distribution")

# fig_turnout = px.histogram(
#     df_cons_summary,
#     x="turn_out",
#     nbins=30,
#     color_discrete_sequence=["#6C5CE7"]
# )

# st.plotly_chart(fig_turnout, use_container_width=True)
# st.markdown("""
# ### 📌 กราฟ Turnout Distribution บอกอะไรได้บ้าง?

# - ดูระดับการมีส่วนร่วมของประชาชนโดยรวม  
# - เห็นความแตกต่างของการออกมาใช้สิทธิระหว่างเขตเลือกตั้ง  
# - ช่วยระบุเขตที่มี turnout สูงหรือต่ำผิดปกติ  

# **ตัวอย่างการตีความ:**

# - 🔼 Turnout สูง → ประชาชนตื่นตัวทางการเมืองสูง หรือการแข่งขันในเขตเข้มข้น  
# - 🔽 Turnout ต่ำ → ความสนใจทางการเมืองต่ำ หรือเขตอาจมีการแข่งขันไม่สูงมาก  
# - 📊 การกระจายกว้าง → ความแตกต่างระหว่างพื้นที่สูง  
# - 📍 การกระจุกตัวแคบ → พฤติกรรมผู้ใช้สิทธิคล้ายกันทั่วประเทศ  
# """)

# st.divider()

# ENP vs Margin
st.subheader("🧠 โครงสร้างการแข่งขัน (ENP vs Margin)")

# เตรียมข้อมูล
plot_df = df_cons_summary.dropna(subset=["ENP", "margin_percent"]).copy()

if "selected_province" not in st.session_state:
    st.session_state.selected_province = None


# ถ้ามีจังหวัดถูกเลือก → highlight
if st.session_state.selected_province:
    plot_df["color_group"] = np.where(
        plot_df["province"] == st.session_state.selected_province,
        "จังหวัดที่เลือก",
        "จังหวัดอื่น"
    )

    fig = px.scatter(
        plot_df,
        x="ENP",
        y="margin_percent",
        color="color_group",
        color_discrete_map={
            "จังหวัดที่เลือก": "red",
            "จังหวัดอื่น": "lightgray",
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
    dragmode="select"   # ต้องเปิด select mode
)

# แสดงกราฟ + รับ selection
event = st.plotly_chart(
    fig,
    use_container_width=True,
    key="scatter_native",
    on_select="rerun"
)

# อ่าน selection
if event and "selection" in event:
    indices = event["selection"]["point_indices"]
    if indices:
        idx = indices[0]
        st.session_state.selected_province = plot_df.iloc[idx]["province"]
        st.rerun()


# ปุ่ม reset
if st.session_state.selected_province:
    if st.button("Reset Highlight"):
        st.session_state.selected_province = None
        st.rerun()

# st.subheader("🧠 โครงสร้างการแข่งขัน (ENP vs Margin)")

# fig_enp = px.scatter(
#     df_cons_summary,
#     x="ENP",
#     y="margin_percent",
#     color="margin_percent",
#     color_continuous_scale="RdYlGn_r",
#     hover_data={
#         "cons_id": True,
#         "province": True,
#         "zone": True,
#         "ENP": ':.2f',
#         "margin_percent": ':.2f',
#     }
# )

# fig_enp.update_layout(
#     xaxis_title="จำนวนพรรคที่มีผลจริง (ENP)",
#     yaxis_title="ส่วนต่างคะแนน (%)",
# )
# st.plotly_chart(fig_enp, use_container_width=True)

st.markdown("""
### 📌 กราฟ Fragmentation (ENP) vs Margin บอกอะไรได้บ้าง?

กราฟนี้ช่วยให้เห็น:

- โครงสร้างการแข่งขันของแต่ละเขต  
- เขตที่มีความหลากหลายทางการเมืองสูง  
- เขตที่เป็นฐานเสียงแข็ง (stronghold) ของพรรคใดพรรคหนึ่ง  
- รูปแบบการแข่งขันของทั้งประเทศในภาพรวม  

**ตัวอย่างการตีความ:**

- 🔼 ENP สูง + 🔽 Margin ต่ำ  
  → หลายพรรคแข่งขันกัน และผลออกมาสูสีมาก  

- 🔽 ENP ต่ำ + 🔼 Margin สูง  
  → พรรคหลักพรรคเดียวครองพื้นที่ ชนะขาด  

- 🔼 ENP สูง + 🔼 Margin สูง  
  → หลายพรรคลงแข่ง แต่มีพรรคหนึ่งโดดเด่นชัด  

- 🔽 ENP ต่ำ + 🔽 Margin ต่ำ  
  → แข่งขันหลัก ๆ ระหว่าง 2 พรรค และสูสี  
""")

st.divider()



