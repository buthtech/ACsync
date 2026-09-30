import csv
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="ACsync | Smart AC Coordination", page_icon="❄️",
                   layout="wide", initial_sidebar_state="expanded")

# ---------- Style (theme-neutral: works in light and dark mode) ----------
st.markdown("""
<style>
.block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px;}
.hero-title {font-size: 2.4rem; font-weight: 750; letter-spacing: -0.03em;}
.hero-sub {font-size: 1.05rem; opacity: .7; max-width: 850px; line-height: 1.6; margin-bottom: .8rem;}
.kpi {border: 1px solid rgba(128,128,128,.25); border-radius: 14px; padding: 1.1rem 1.2rem;
      min-height: 125px; background: rgba(128,128,128,.04);}
.kpi-label {font-size: .82rem; opacity: .65; margin-bottom: .4rem;}
.kpi-value {font-size: 1.7rem; font-weight: 700; letter-spacing: -0.02em;}
.kpi-desc {font-size: .78rem; opacity: .6; margin-top: .3rem;}
.kpi.good .kpi-value {color: #2ea043;}
.step {border: 1px solid rgba(128,128,128,.22); border-radius: 12px; padding: 1rem 1.1rem; height: 100%;}
.step b {font-size: 1.05rem;}
.status {display: inline-block; padding: .3rem .75rem; border-radius: 999px; font-size: .78rem;
         font-weight: 600; background: rgba(46,160,67,.12); color: #2ea043;}
.footer {text-align: center; opacity: .45; font-size: .78rem; padding-top: 2rem;}
</style>
""", unsafe_allow_html=True)

# ---------- Data loading ----------
RESULTS_FILE, PRED_FILE = "results.json", "dashboard_predictions.csv"
REQUIRED = ["household", "room", "timestamp_10min", "indoor_temp", "outdoor_temp", "predicted_temp"]


@st.cache_data
def load_results(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@st.cache_data
def load_predictions(path):
    df = pd.read_csv(path)
    df["timestamp_10min"] = pd.to_datetime(df["timestamp_10min"], errors="coerce")
    df["household"] = df["household"].astype(str)  # IDs may contain Arabic/text
    df["room"] = df["room"].astype(str)
    return df.dropna(subset=["timestamp_10min"])


missing_files = [f for f in (RESULTS_FILE, PRED_FILE) if not Path(f).exists()]
if missing_files:
    st.error(f"Missing file(s): {', '.join(missing_files)}. Put them next to app.py, "
             "or run `python make_sample_data.py` to generate test data.")
    st.stop()

results, df = load_results(RESULTS_FILE), load_predictions(PRED_FILE)

absent = [c for c in REQUIRED if c not in df.columns]
if absent:
    st.error("The prediction file is missing columns: " + ", ".join(absent))
    st.stop()


def g(section, key, default=None):
    """Safe lookup into results.json so a missing key never crashes the page."""
    return results.get(section, {}).get(key, default)


def fmt(value, spec=".2f", unit=""):
    return "n/a" if value is None else f"{value:{spec}}{unit}"


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("## ❄️ ACsync")
    st.caption("Predictive coordination for residential air-conditioning.")
    st.divider()

    pairs = df[["household", "room"]].drop_duplicates().sort_values(["household", "room"])
    labels = (pairs["household"] + " / " + pairs["room"]).tolist()
    label = st.selectbox("Room", labels, help="Household and room to inspect.")
    hh, room = pairs.iloc[labels.index(label)]

    room_df = df[(df["household"] == hh) & (df["room"] == room)].sort_values("timestamp_10min")
    days = sorted(room_df["timestamp_10min"].dt.date.unique())

    picked = st.date_input("Date", value=days[0], min_value=days[0], max_value=days[-1])
    selected_date = picked[0] if isinstance(picked, (tuple, list)) and picked else picked
    if not isinstance(selected_date, date):
        selected_date = days[0]

    comfort = st.slider("Comfort band (°C)", 18.0, 30.0, (23.0, 26.0), 0.5,
                        help="Shaded on the forecast chart.")
    show_outdoor = st.toggle("Show outdoor temperature", value=True)

    st.divider()
    st.caption(f"Demo period: {g('demo_period', 'start', '?')} → {g('demo_period', 'end', '?')}")
    st.caption(f"{g('demo_period', 'rooms', '?')} rooms · {g('demo_period', 'timestamps', '?')} timestamps")
    st.caption(f"Forecast horizon: {g('model', 'forecast_horizon_minutes', '?')} min")

day_df = room_df[room_df["timestamp_10min"].dt.date == selected_date].copy()
period_label = f"{g('demo_period', 'days', 7)}-day"

# ---------- Header + KPIs ----------
st.markdown('<div class="hero-title">❄️ ACsync</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Forecasts indoor temperature and staggers compressors '
            'to reduce simultaneous demand.</div>', unsafe_allow_html=True)
st.markdown('<span class="status">● Simulation ready</span>', unsafe_allow_html=True)
st.write("")

with st.expander("👋 New here? Quick guide", expanded=False):
    st.markdown(
        "**ACsync predicts room temperature 20 minutes ahead and staggers AC compressors "
        "so they don't all start at once.**\n\n"
        "- **Forecast:** pick a room and day in the sidebar to see how well the prediction matches reality.\n"
        "- **Try it yourself:** enter your own number of ACs and see your estimated savings.\n"
        "- **Feedback:** tell us what worked and what didn't.")


def kpi(col, label_, value, desc, good=True):
    col.markdown(f'<div class="kpi {"good" if good else ""}"><div class="kpi-label">{label_}</div>'
                 f'<div class="kpi-value">{value}</div><div class="kpi-desc">{desc}</div></div>',
                 unsafe_allow_html=True)


k1, k2, k3, k4 = st.columns(4)
kpi(k1, "Peak power reduction", fmt(g("power", "peak_reduction_percent"), ".1f", "%"),
    f"{fmt(g('power', 'traditional_peak_kw'), '.1f')} → {fmt(g('power', 'acsync_peak_kw'), '.1f')} kW")
kpi(k2, "Energy reduction", fmt(g("energy", "energy_reduction_percent"), ".1f", "%"),
    f"{fmt(g('energy', 'traditional_kwh'))} → {fmt(g('energy', 'acsync_kwh'))} kWh")
kpi(k3, "Energy saved", fmt(g("energy", "energy_saved_kwh"), ".2f", " kWh"),
    f"Across the {period_label} demonstration")
kpi(k4, "Estimated saving", fmt(g("cost", "estimated_saving_sar"), ".2f", " SAR"),
    "Electricity cost")

st.write("")
tab_fc, tab_try, tab_fleet, tab_impact, tab_model, tab_fb = st.tabs(
    ["🌡️ Forecast", "🧮 Try it yourself", "📊 Accuracy (all rooms)", "⚡ Energy & power",
     "🤖 Model & method", "💬 Feedback"])

# ---------- Forecast tab ----------
with tab_fc:
    st.subheader(f"{hh} · {room}")
    st.caption(str(selected_date))

    if day_df.empty:
        st.info("No measurements for this date. Pick another date in the sidebar.")
    else:
        t = day_df["timestamp_10min"]
        err = day_df["predicted_temp"] - day_df["indoor_temp"]
        mae, rmse, bias = err.abs().mean(), (err ** 2).mean() ** 0.5, err.mean()

        fig = go.Figure()
        fig.add_hrect(y0=comfort[0], y1=comfort[1], fillcolor="rgba(46,160,67,.10)",
                      line_width=0, annotation_text="Comfort band", annotation_position="top left")
        fig.add_trace(go.Scatter(x=t, y=day_df["indoor_temp"], name="Actual indoor", line=dict(width=3)))
        fig.add_trace(go.Scatter(x=t, y=day_df["predicted_temp"], name="Predicted indoor",
                                 line=dict(width=2, dash="dash")))
        if show_outdoor:
            fig.add_trace(go.Scatter(x=t, y=day_df["outdoor_temp"], name="Outdoor",
                                     line=dict(width=1.5), opacity=.55))
        fig.update_layout(height=500, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                          yaxis_title="Temperature (°C)",
                          legend=dict(orientation="h", y=1.04, x=0))
        st.plotly_chart(fig, use_container_width=True)

        m = st.columns(5)
        m[0].metric("Avg. indoor", f"{day_df['indoor_temp'].mean():.2f} °C")
        m[1].metric("Avg. predicted", f"{day_df['predicted_temp'].mean():.2f} °C")
        m[2].metric("Avg. outdoor", f"{day_df['outdoor_temp'].mean():.2f} °C")
        m[3].metric("MAE", f"{mae:.2f} °C", help="Mean absolute error for this room and day.")
        m[4].metric("Bias", f"{bias:+.2f} °C", help="Positive = model over-predicts.")
        st.caption(f"RMSE for this day: {rmse:.3f} °C")

        in_band = day_df["indoor_temp"].between(*comfort).mean() * 100
        quality = "very close" if mae < 0.3 else "close" if mae < 0.6 else "loose"
        st.info(f"**In plain words:** on this day the forecast was {quality} to reality "
                f"(off by {mae:.2f} °C on average), and the room stayed inside your "
                f"{comfort[0]:g}–{comfort[1]:g} °C comfort band {in_band:.0f}% of the time.")

        st.markdown("#### Prediction error")
        ef = go.Figure(go.Scatter(x=t, y=err, mode="lines", name="Error", line=dict(width=2)))
        ef.add_hline(y=0, line_dash="dot")
        ef.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
                         yaxis_title="Predicted − actual (°C)")
        st.plotly_chart(ef, use_container_width=True)

        st.download_button("Download this day (CSV)", day_df.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"acsync_{hh}_{room}_{selected_date}.csv", mime="text/csv")

# ---------- Fleet accuracy tab ----------
with tab_fleet:
    st.subheader("Forecast accuracy across rooms")
    all_err = df.assign(abs_err=(df["predicted_temp"] - df["indoor_temp"]).abs(),
                        sq_err=(df["predicted_temp"] - df["indoor_temp"]) ** 2)
    per_room = (all_err.groupby(["household", "room"])
                .agg(MAE=("abs_err", "mean"), RMSE=("sq_err", lambda s: s.mean() ** 0.5),
                     Samples=("abs_err", "size")).reset_index())
    per_room["RMSE"] = per_room["RMSE"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Overall MAE", f"{all_err['abs_err'].mean():.3f} °C")
    c2.metric("Overall RMSE", f"{all_err['sq_err'].mean() ** 0.5:.3f} °C")
    c3.metric("Rooms", len(per_room))

    worst = per_room.sort_values("MAE", ascending=False)
    bar = go.Figure(go.Bar(x=(worst["household"] + " / " + worst["room"]), y=worst["MAE"]))
    bar.update_layout(height=380, yaxis_title="MAE (°C)", margin=dict(l=10, r=10, t=30, b=10),
                      title="Rooms ranked by error (worst first)")
    st.plotly_chart(bar, use_container_width=True)
    st.dataframe(worst.round(3), use_container_width=True, hide_index=True)

# ---------- Impact tab ----------
with tab_impact:
    st.subheader("Conventional operation vs ACsync")

    def compare_bar(title, y, unit, fmt_spec):
        f = go.Figure(go.Bar(x=["Traditional", "ACsync"], y=y,
                             text=[f"{v:{fmt_spec}} {unit}" for v in y], textposition="auto"))
        f.update_layout(title=title, height=380, yaxis_title=unit, showlegend=False,
                        margin=dict(l=10, r=10, t=60, b=10))
        return f

    a, b = st.columns(2)
    tp, ap = g("power", "traditional_peak_kw"), g("power", "acsync_peak_kw")
    te, ae = g("energy", "traditional_kwh"), g("energy", "acsync_kwh")
    if None not in (tp, ap):
        a.plotly_chart(compare_bar("Peak power demand", [tp, ap], "kW", ".1f"), use_container_width=True)
    if None not in (te, ae):
        b.plotly_chart(compare_bar(f"{period_label} energy", [te, ae], "kWh", ".2f"), use_container_width=True)

    st.markdown("#### Electricity cost")
    c = st.columns(3)
    c[0].metric("Traditional", fmt(g("cost", "traditional_cost_sar"), ".2f", " SAR"))
    c[1].metric("ACsync", fmt(g("cost", "acsync_cost_sar"), ".2f", " SAR"))
    c[2].metric("Saving", fmt(g("cost", "estimated_saving_sar"), ".2f", " SAR"))

# ---------- Try it yourself ----------
with tab_try:
    st.subheader("Estimate savings for your own building")
    st.caption("A simplified estimate: it applies the energy reduction measured in the demo "
               "to the numbers you enter. It is not a guarantee.")
    a, b = st.columns(2)
    n_ac = a.number_input("Number of ACs", 1, 200, 6)
    p_ac = a.number_input("Power per AC (kW)", 0.5, 10.0,
                          float(g("power", "power_per_ac_kw", 1.5) or 1.5), 0.1)
    limit = a.number_input("Max ACs allowed to run at once", 1, int(n_ac), min(2, int(n_ac)))
    hours = b.slider("Hours of AC use per day", 1, 24, 10)
    duty = b.slider("Share of time the compressor is running (%)", 10, 100, 50)
    rate = b.number_input("Electricity rate (SAR/kWh)", 0.01, 2.0,
                          float(g("cost", "electricity_rate_sar_per_kwh", 0.2) or 0.2), 0.01)

    pct = g("energy", "energy_reduction_percent", 0) or 0
    trad_peak, ac_peak = n_ac * p_ac, min(n_ac, limit) * p_ac
    trad_kwh = n_ac * p_ac * hours * duty / 100 * 30
    saved_kwh = trad_kwh * pct / 100
    r = st.columns(4)
    r[0].metric("Peak without ACsync", f"{trad_peak:.1f} kW")
    r[1].metric("Peak with ACsync", f"{ac_peak:.1f} kW", f"-{(1 - ac_peak / trad_peak) * 100:.0f}%",
                delta_color="inverse")
    r[2].metric("Energy saved / month", f"{saved_kwh:.0f} kWh")
    r[3].metric("Cost saved / month", f"{saved_kwh * rate:.1f} SAR")
    f = go.Figure(go.Bar(x=["Without ACsync", "With ACsync"], y=[trad_kwh, trad_kwh - saved_kwh],
                         text=[f"{trad_kwh:.0f} kWh", f"{trad_kwh - saved_kwh:.0f} kWh"],
                         textposition="auto"))
    f.update_layout(title="Estimated monthly energy", height=340, showlegend=False,
                    yaxis_title="kWh", margin=dict(l=10, r=10, t=60, b=10))
    st.plotly_chart(f, use_container_width=True)

# ---------- Feedback ----------
FEEDBACK_FILE = "feedback.csv"
with tab_fb:
    st.subheader("Tell us what you think")
    with st.form("feedback", clear_on_submit=True):
        role = st.selectbox("I am a...", ["Homeowner / tenant", "Building manager",
                                          "Energy professional", "Judge / reviewer", "Other"])
        rating = st.slider("How useful is this dashboard? (1 = not, 5 = very)", 1, 5, 4)
        would_use = st.radio("Would you use ACsync in your own home or building?",
                             ["Yes", "Maybe", "No"], horizontal=True)
        comment = st.text_area("Anything confusing or missing?", max_chars=1000)
        if st.form_submit_button("Send feedback"):
            new_file = not Path(FEEDBACK_FILE).exists()
            with open(FEEDBACK_FILE, "a", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                if new_file:
                    w.writerow(["time", "role", "rating", "would_use", "comment"])
                w.writerow([datetime.now().isoformat(timespec="seconds"), role, rating,
                            would_use, comment])
            st.success("Thank you! Your feedback was saved.")

    if Path(FEEDBACK_FILE).exists():
        fb = pd.read_csv(FEEDBACK_FILE)
        st.caption(f"{len(fb)} response(s) so far · average rating {fb['rating'].mean():.1f}/5")
        with st.expander("Organizer view"):
            st.dataframe(fb, use_container_width=True, hide_index=True)
            st.download_button("Download feedback (CSV)", fb.to_csv(index=False).encode("utf-8-sig"),
                               file_name="acsync_feedback.csv", mime="text/csv")

# ---------- Model tab ----------
with tab_model:
    st.subheader("How ACsync works")
    horizon = g("model", "forecast_horizon_minutes", 20)
    steps = [("1. Observe", "Collect indoor and outdoor temperature, time and AC operating data."),
             ("2. Predict", f"{g('model', 'type', 'A model')} forecasts indoor temperature {horizon} minutes ahead."),
             ("3. Coordinate", "Compressors are staggered to limit simultaneous demand."),
             ("4. Reduce", "Lower peak power, energy use and electricity cost.")]
    for col, (title, text) in zip(st.columns(4), steps):
        col.markdown(f'<div class="step"><b>{title}</b><p>{text}</p></div>', unsafe_allow_html=True)

    st.divider()
    l, r = st.columns(2)
    with l:
        st.markdown("#### Prediction model")
        st.write(f"**Model:** {g('model', 'type', 'n/a')}")
        st.write(f"**Forecast horizon:** {horizon} minutes")
        st.write(f"**System RMSE:** {fmt(g('model', 'prediction_rmse_c'), '.4f', ' °C')}")
    with r:
        st.markdown("#### Simulation assumptions")
        st.write(f"**Power per AC:** {g('power', 'power_per_ac_kw', 'n/a')} kW")
        st.write(f"**Electricity rate:** {g('cost', 'electricity_rate_sar_per_kwh', 'n/a')} SAR/kWh")
        st.write(f"**Max coordinated ACs:** {g('power', 'max_coordinated_acs', 2)}")

    with st.expander("Methodology"):
        st.markdown(
            "1. **Data preparation:** real AC and weather data aligned to 10-minute timestamps.\n"
            f"2. **Forecasting:** Random Forest regression predicts temperature {horizon} minutes ahead.\n"
            "3. **Coordination:** predictions decide which compressors run, capping simultaneous ones.\n"
            "4. **Simulation:** traditional operation vs ACsync over the same period.\n"
            "5. **Impact:** peak power, energy and cost computed from the simulation.")

st.markdown('<div class="footer">ACsync · Predictive Air-Conditioning Coordination · '
            'Hackathon Demonstration</div>', unsafe_allow_html=True)