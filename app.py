import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title="RRG Analyzer",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────
# CUSTOM CSS — light professional navy style
# ─────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

/* Header */
.main-header {
    background: linear-gradient(135deg, #0A1628 0%, #1C3057 100%);
    padding: 24px 32px;
    border-radius: 16px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.main-header h1 {
    color: white;
    font-size: 24px;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.5px;
}
.main-header p {
    color: rgba(255,255,255,0.55);
    font-size: 13px;
    margin: 2px 0 0;
}

/* Metric cards */
.metric-card {
    background: white;
    border: 1.5px solid #E4EAF4;
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 8px;
}
.metric-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #8A9BBE;
    margin-bottom: 4px;
}
.metric-value {
    font-size: 22px;
    font-weight: 700;
    color: #0A1628;
    font-family: 'DM Mono', monospace;
    letter-spacing: -1px;
}

/* Quadrant chips */
.chip {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
}
.chip-leading   { background: rgba(0,135,90,0.1);  color: #00875A; }
.chip-weakening { background: rgba(196,121,0,0.1); color: #C47900; }
.chip-lagging   { background: rgba(196,0,43,0.1);  color: #C4002B; }
.chip-improving { background: rgba(0,98,196,0.1);  color: #0062C4; }

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background: #F5F7FA;
    border-right: 1px solid #E4EAF4;
}
section[data-testid="stSidebar"] .block-container {
    padding-top: 24px;
}

/* Remove default streamlit padding top */
.block-container { padding-top: 1rem; }

/* Divider */
hr { border: none; border-top: 1px solid #E4EAF4; margin: 16px 0; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# RRG ENGINE
# ─────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    k = 2.0 / (period + 1)
    result = [np.nan] * len(series)
    valid = series.dropna()
    if len(valid) < period:
        return pd.Series(result, index=series.index)
    seed_idx = valid.index[period - 1]
    seed_val = valid.iloc[:period].mean()
    idx_pos = series.index.get_loc(seed_idx)
    result[idx_pos] = seed_val
    for i in range(idx_pos + 1, len(series)):
        if pd.isna(series.iloc[i]):
            result[i] = np.nan
        else:
            result[i] = series.iloc[i] * k + result[i - 1] * (1 - k)
    return pd.Series(result, index=series.index)


def compute_rrg(
    df: pd.DataFrame,
    benchmark_col: str,
    sector_cols: list,
    ema_short: int = 12,
    ema_long: int = 26,
    zscore_window: int = 52,
    momentum_window: int = 14,
) -> dict:
    results = {}
    for col in sector_cols:
        rs_raw = df[col] / df[benchmark_col]
        ema1   = ema(rs_raw, ema_short)
        rs_s   = ema(ema1, ema_long)

        roll_mean = rs_s.rolling(zscore_window, min_periods=zscore_window).mean()
        roll_std  = rs_s.rolling(zscore_window, min_periods=zscore_window).std(ddof=0)
        rs_ratio  = 100 + ((rs_s - roll_mean) / roll_std.replace(0, np.nan)) * 10

        d_ratio = rs_ratio.diff()
        m_mean  = d_ratio.rolling(momentum_window, min_periods=momentum_window).mean()
        m_std   = d_ratio.rolling(momentum_window, min_periods=momentum_window).std(ddof=0)
        rs_mom  = 100 + ((d_ratio - m_mean) / m_std.replace(0, np.nan)) * 10

        results[col] = {"rs_ratio": rs_ratio, "rs_momentum": rs_mom}
    return results


def resample_prices(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    freq_map = {"Daily": None, "Weekly": "W-FRI", "Monthly": "ME"}
    rule = freq_map.get(freq)
    if not rule:
        return df
    return df.resample(rule).last().dropna(how="all")


def get_quadrant(x: float, y: float) -> str:
    if x >= 100 and y >= 100: return "leading"
    if x >= 100 and y <  100: return "weakening"
    if x <  100 and y <  100: return "lagging"
    return "improving"


def parse_file(uploaded) -> pd.DataFrame:
    raw = uploaded.read()
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw))
    else:
        df = pd.read_excel(io.BytesIO(raw))

    if df.empty:
        raise ValueError("Il file è vuoto.")

    # Detect date column: prefer named, fall back to first column
    date_col = None
    for col in df.columns:
        if any(k in str(col).lower() for k in ("date", "data", "time", "periodo")):
            date_col = col
            break
    if date_col is None:
        date_col = df.columns[0]

    # Parse dates — try multiple strategies
    parsed = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
    if parsed.isna().all():
        parsed = pd.to_datetime(df[date_col], format="mixed", dayfirst=True, errors="coerce")
    if parsed.isna().all():
        raise ValueError(
            f"Impossibile interpretare la colonna '{date_col}' come date. "
            "Verifica il formato (es. YYYY-MM-DD, DD/MM/YYYY)."
        )

    df[date_col] = parsed
    # Drop rows where date could not be parsed
    n_before = len(df)
    df = df.dropna(subset=[date_col])
    if df.empty:
        raise ValueError("Nessuna riga con data valida trovata nel file.")

    df = df.set_index(date_col)
    df.index = pd.DatetimeIndex(df.index)
    df = df.sort_index()

    # Convert all other columns to numeric, drop fully-empty rows
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(how="all")

    if df.empty:
        raise ValueError("Il file non contiene dati numerici validi dopo la pulizia.")

    # Safety check: ensure index is a proper DatetimeIndex with no NaT
    df = df[df.index.notna()]
    if df.empty:
        raise ValueError("Nessuna data valida trovata dopo la pulizia dell'indice.")

    return df


# ─────────────────────────────────────────
# PLOTLY RRG CHART
# ─────────────────────────────────────────

COLORS = [
    "#1D5FC4", "#E63946", "#2A9D8F", "#F4A261", "#8338EC",
    "#06D6A0", "#D4A017", "#FB8500", "#2D6A4F", "#C77DFF",
    "#0077B6", "#EF233C", "#4CC9F0", "#F72585", "#3A0CA3",
]

QUADRANT_COLORS = {
    "leading":   "#00875A",
    "weakening": "#C47900",
    "lagging":   "#C4002B",
    "improving": "#0062C4",
}


def build_rrg_figure(
    results: dict,
    dates: pd.DatetimeIndex,
    show_trails: bool = False,
    trail_length: int = 8,
) -> go.Figure:
    fig = go.Figure()

    # Collect all valid values to set axis range
    all_x, all_y = [], []
    for v in results.values():
        all_x += list(v["rs_ratio"].dropna())
        all_y += list(v["rs_momentum"].dropna())

    if not all_x:
        return fig

    pad  = max(3, (max(all_x) - min(all_x)) * 0.08)
    padY = max(3, (max(all_y) - min(all_y)) * 0.08)
    xmin = min(all_x) - pad
    xmax = max(all_x) + pad
    ymin = min(all_y) - padY
    ymax = max(all_y) + padY

    # Quadrant background boxes
    quad_boxes = [
        (100, xmax, 100, ymax, "rgba(0,135,90,0.06)",   "LEADING",   100.2, ymax - padY * 0.4),
        (100, xmax, ymin, 100, "rgba(196,121,0,0.06)",  "WEAKENING", 100.2, ymin + padY * 0.4),
        (xmin, 100, ymin, 100, "rgba(196,0,43,0.06)",   "LAGGING",   xmin + pad * 0.3, ymin + padY * 0.4),
        (xmin, 100, 100, ymax, "rgba(0,98,196,0.06)",   "IMPROVING", xmin + pad * 0.3, ymax - padY * 0.4),
    ]
    for x0, x1, y0, y1, color, label, lx, ly in quad_boxes:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=color, line_width=0, layer="below")
        fig.add_annotation(x=lx, y=ly, text=label,
                           font=dict(size=10, color=color.replace("0.06", "0.35"), family="DM Sans"),
                           showarrow=False, xanchor="left")

    # Center crosshair
    fig.add_shape(type="line", x0=100, x1=100, y0=ymin, y1=ymax,
                  line=dict(color="rgba(10,22,40,0.2)", width=1.5, dash="dot"))
    fig.add_shape(type="line", x0=xmin, x1=xmax, y0=100, y1=100,
                  line=dict(color="rgba(10,22,40,0.2)", width=1.5, dash="dot"))

    # Draw each sector
    for i, (name, v) in enumerate(results.items()):
        color   = COLORS[i % len(COLORS)]
        ratio_s = v["rs_ratio"]
        mom_s   = v["rs_momentum"]

        # Last valid point
        valid_both = ratio_s.notna() & mom_s.notna()
        if not valid_both.any():
            continue
        last_idx = valid_both[::-1].idxmax()
        qd     = get_quadrant(ratio_s[last_idx], mom_s[last_idx])
        qcolor = QUADRANT_COLORS[qd]

        if show_trails:
            # Find numeric position of last_idx
            all_valid = valid_both[valid_both].index
            pos       = list(all_valid).index(last_idx)
            start_pos = max(0, pos - trail_length)
            trail_idx = all_valid[start_pos : pos + 1]

            xs = ratio_s[trail_idx].values
            ys = mom_s[trail_idx].values
            ds = [d.strftime("%Y-%m-%d") for d in trail_idx]

            # Gradient trail: split into segments
            n = len(xs)
            for j in range(n - 1):
                alpha = 0.12 + 0.7 * (j / max(n - 2, 1))
                rgba  = f"rgba({int(qcolor[1:3],16)},{int(qcolor[3:5],16)},{int(qcolor[5:7],16)},{alpha:.2f})"
                fig.add_trace(go.Scatter(
                    x=[xs[j], xs[j+1]], y=[ys[j], ys[j+1]],
                    mode="lines+markers",
                    line=dict(color=rgba, width=2),
                    marker=dict(size=[3 if j > 0 else 4, 0], color=rgba),
                    hoverinfo="skip",
                    showlegend=False,
                    name=f"{name}_t{j}",
                ))

        # Main dot
        fig.add_trace(go.Scatter(
            x=[ratio_s[last_idx]],
            y=[mom_s[last_idx]],
            mode="markers+text",
            name=name,
            marker=dict(
                size=14,
                color=qcolor,
                line=dict(color="white", width=2.5),
                symbol="circle",
            ),
            text=[name],
            textposition="top right",
            textfont=dict(size=11, color=qcolor, family="DM Sans"),
            hovertemplate=(
                f"<b>{name}</b><br>"
                f"RS-Ratio:    %{{x:.2f}}<br>"
                f"RS-Momentum: %{{y:.2f}}<br>"
                f"Quadrante:   {qd.capitalize()}<br>"
                f"Data:        {last_idx.strftime('%Y-%m-%d')}"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="#F8FAFD",
        font=dict(family="DM Sans", color="#0A1628"),
        margin=dict(l=60, r=40, t=40, b=60),
        xaxis=dict(
            title="RS-Ratio  →  (Forza Relativa)",
            titlefont=dict(size=11, color="#4A5A7A"),
            gridcolor="rgba(10,22,40,0.06)",
            tickfont=dict(family="DM Mono", size=10, color="#8A9BBE"),
            zeroline=False,
            range=[xmin, xmax],
        ),
        yaxis=dict(
            title="RS-Momentum  ↑  (Velocità)",
            titlefont=dict(size=11, color="#4A5A7A"),
            gridcolor="rgba(10,22,40,0.06)",
            tickfont=dict(family="DM Mono", size=10, color="#8A9BBE"),
            zeroline=False,
            range=[ymin, ymax],
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.01,
            xanchor="left", x=0,
            font=dict(size=11),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="#E4EAF4",
            borderwidth=1,
        ),
        hoverlabel=dict(
            bgcolor="#0A1628",
            font_color="white",
            font_family="DM Mono",
            font_size=12,
            bordercolor="#0A1628",
        ),
        height=620,
    )
    return fig


# ─────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────

# Header
st.markdown("""
<div class="main-header">
  <div style="font-size:36px">🔄</div>
  <div>
    <h1>RRG Analyzer</h1>
    <p>Relative Rotation Graph — Metodologia JdK (Julius de Kempenaer)</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── SIDEBAR ──
with st.sidebar:
    st.markdown("### 📂 Carica Dati")

    uploaded = st.file_uploader(
        "File prezzi storici",
        type=["xlsx", "xls", "csv"],
        help="Prima colonna = Date. Colonne successive = prezzi di chiusura (benchmark + strumenti).",
    )

    df_raw = None
    if uploaded:
        try:
            df_raw = parse_file(uploaded)
            st.success(f"✅ {len(df_raw)} righe · {len(df_raw.columns)} colonne")
        except Exception as e:
            st.error(f"❌ {e}")

    st.markdown("---")
    st.markdown("### ⚙️ Configurazione")

    if df_raw is not None:
        cols = list(df_raw.columns)

        benchmark = st.selectbox("Benchmark (indice di riferimento)", cols, index=0)

        sector_options = [c for c in cols if c != benchmark]
        sectors = st.multiselect(
            "Titoli / Settori",
            options=sector_options,
            default=sector_options,
            help="Seleziona i componenti da analizzare rispetto al benchmark.",
        )

        st.markdown("---")
        st.markdown("### 📅 Timeframe")

        freq = st.selectbox(
            "Frequenza",
            ["Daily", "Weekly", "Monthly"],
            index=1,
            help="Se necessario, i dati vengono ricampionati automaticamente.",
        )

        # Guard against NaT in index
        idx_valid = df_raw.index[df_raw.index.notna()]
        if len(idx_valid) == 0:
            st.error("❌ L'indice temporale non contiene date valide. Ricarica il file.")
            st.stop()
        date_min = idx_valid.min().to_pydatetime().date()
        date_max = idx_valid.max().to_pydatetime().date()

        col1, col2 = st.columns(2)
        with col1:
            range_from = st.date_input("Da", value=date_min, min_value=date_min, max_value=date_max, format="DD/MM/YYYY")
        with col2:
            range_to = st.date_input("A",  value=date_max, min_value=date_min, max_value=date_max, format="DD/MM/YYYY")

        st.markdown("---")
        with st.expander("🔧 Parametri Avanzati"):
            c1, c2 = st.columns(2)
            ema_short       = c1.number_input("EMA Corta",        value=12, min_value=2,  max_value=50)
            ema_long        = c2.number_input("EMA Lunga",        value=26, min_value=5,  max_value=100)
            zscore_window   = c1.number_input("Z-score Window",   value=52, min_value=10, max_value=260)
            momentum_window = c2.number_input("Momentum Window",  value=14, min_value=3,  max_value=52)

        run = st.button("▶ Calcola RRG", type="primary", use_container_width=True)
    else:
        st.info("Carica un file XLSX o CSV per iniziare.")
        run = False
        sectors = []
        benchmark = None

# ── MAIN AREA ──
if df_raw is not None and run and sectors:
    # Apply date filter
    df = df_raw[
        (df_raw.index >= pd.Timestamp(range_from)) &
        (df_raw.index <= pd.Timestamp(range_to))
    ].copy()

    # Resample
    df = resample_prices(df, freq)

    min_rows = ema_short + ema_long + zscore_window + momentum_window
    if len(df) < min_rows:
        st.error(f"❌ Dati insufficienti: {len(df)} periodi disponibili, minimo {min_rows} richiesti. Amplia il range o usa una frequenza più alta.")
        st.stop()

    # Compute
    with st.spinner("Calcolo RRG in corso..."):
        results = compute_rrg(
            df, benchmark, sectors,
            ema_short=ema_short,
            ema_long=ema_long,
            zscore_window=zscore_window,
            momentum_window=momentum_window,
        )

    # Build snapshot
    snapshot = []
    for name, v in results.items():
        valid = v["rs_ratio"].notna() & v["rs_momentum"].notna()
        if not valid.any():
            continue
        last = valid[::-1].idxmax()
        x = float(v["rs_ratio"][last])
        y = float(v["rs_momentum"][last])
        snapshot.append({"name": name, "x": x, "y": y, "quadrant": get_quadrant(x, y)})
    snapshot.sort(key=lambda s: s["x"], reverse=True)

    # ── Store results in session state ──
    st.session_state["results"]  = results
    st.session_state["dates"]    = df.index
    st.session_state["snapshot"] = snapshot
    st.session_state["meta"]     = f"Benchmark: {benchmark} · Freq: {freq} · {len(df)} periodi"

# ── DISPLAY (persists across trail toggle) ──
if "results" in st.session_state:
    results  = st.session_state["results"]
    dates    = st.session_state["dates"]
    snapshot = st.session_state["snapshot"]
    meta     = st.session_state["meta"]

    # Top metric strip
    leading   = sum(1 for s in snapshot if s["quadrant"] == "leading")
    weakening = sum(1 for s in snapshot if s["quadrant"] == "weakening")
    lagging   = sum(1 for s in snapshot if s["quadrant"] == "lagging")
    improving = sum(1 for s in snapshot if s["quadrant"] == "improving")

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f'<div class="metric-card"><div class="metric-label">🟢 Leading</div><div class="metric-value" style="color:#00875A">{leading}</div></div>', unsafe_allow_html=True)
    m2.markdown(f'<div class="metric-card"><div class="metric-label">🟡 Weakening</div><div class="metric-value" style="color:#C47900">{weakening}</div></div>', unsafe_allow_html=True)
    m3.markdown(f'<div class="metric-card"><div class="metric-label">🔴 Lagging</div><div class="metric-value" style="color:#C4002B">{lagging}</div></div>', unsafe_allow_html=True)
    m4.markdown(f'<div class="metric-card"><div class="metric-label">🔵 Improving</div><div class="metric-value" style="color:#0062C4">{improving}</div></div>', unsafe_allow_html=True)

    # Chart + controls
    chart_col, table_col = st.columns([3, 1])

    with chart_col:
        # Trail controls inline above chart
        tc1, tc2, tc3 = st.columns([1, 2, 1])
        with tc1:
            show_trails = st.toggle("🐾 Mostra Code", value=False)
        with tc2:
            trail_length = st.slider(
                "Lunghezza coda (periodi)",
                min_value=2, max_value=min(60, len(dates) - 1),
                value=8,
                disabled=not show_trails,
                label_visibility="collapsed" if not show_trails else "visible",
            )
        with tc3:
            st.caption(f"{'🐾 ' + str(trail_length) + ' periodi' if show_trails else ''}")

        st.caption(f"📊 {meta}")

        fig = build_rrg_figure(results, dates, show_trails=show_trails, trail_length=trail_length)
        st.plotly_chart(fig, use_container_width=True, config={
            "displayModeBar": True,
            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
            "toImageButtonOptions": {"filename": "rrg_chart", "format": "png", "scale": 2},
        })

    with table_col:
        st.markdown("#### 📋 Snapshot")
        st.caption("Ordinato per RS-Ratio ↓")

        QUAD_LABELS = {
            "leading":   "🟢 Leading",
            "weakening": "🟡 Weakening",
            "lagging":   "🔴 Lagging",
            "improving": "🔵 Improving",
        }

        for s in snapshot:
            with st.container():
                st.markdown(f"""
                <div style="background:white;border:1.5px solid #E4EAF4;border-radius:10px;
                            padding:10px 14px;margin-bottom:8px;">
                  <div style="font-weight:600;font-size:13px;color:#0A1628;margin-bottom:4px">{s['name']}</div>
                  <div style="display:flex;gap:12px;align-items:center">
                    <span style="font-family:'DM Mono',monospace;font-size:11px;color:#4A5A7A">
                      X: <b>{s['x']:.2f}</b>
                    </span>
                    <span style="font-family:'DM Mono',monospace;font-size:11px;color:#4A5A7A">
                      Y: <b>{s['y']:.2f}</b>
                    </span>
                  </div>
                  <div style="margin-top:6px">
                    <span class="chip chip-{s['quadrant']}">{QUAD_LABELS[s['quadrant']]}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)

        # CSV export
        st.markdown("---")
        df_export = pd.DataFrame(snapshot)[["name", "x", "y", "quadrant"]]
        df_export.columns = ["Titolo", "RS-Ratio", "RS-Momentum", "Quadrante"]
        csv = df_export.to_csv(index=False).encode("utf-8")
        st.download_button("⬇ Esporta CSV", csv, "rrg_snapshot.csv", "text/csv", use_container_width=True)

elif df_raw is None:
    # Welcome state
    st.markdown("""
    <div style="text-align:center;padding:80px 40px;color:#8A9BBE;">
      <div style="font-size:64px;margin-bottom:16px;opacity:0.4">🔄</div>
      <div style="font-size:18px;font-weight:600;color:#4A5A7A;margin-bottom:8px">
        Nessun grafico da visualizzare
      </div>
      <div style="font-size:13px;max-width:400px;margin:0 auto;line-height:1.6">
        Carica un file <b>XLSX</b> o <b>CSV</b> dalla barra laterale.<br>
        La prima colonna deve contenere le <b>date</b>, le successive i <b>prezzi di chiusura</b>
        del benchmark e dei titoli/settori da analizzare.
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 Formato file atteso"):
        st.markdown("""
| Date       | SP500    | Tech     | Finance  | Energy   |
|------------|----------|----------|----------|----------|
| 2022-01-07 | 4677.03  | 1234.56  | 567.89   | 234.56   |
| 2022-01-14 | 4662.85  | 1198.44  | 554.21   | 241.33   |
| ...        | ...      | ...      | ...      | ...      |

- **Prima colonna**: Date (qualsiasi formato riconoscibile)
- **Seconda colonna**: Benchmark (es. indice S&P 500)
- **Colonne successive**: Prezzi di chiusura dei titoli/settori
- Frequenze supportate: **daily**, **weekly**, **monthly**
        """)
