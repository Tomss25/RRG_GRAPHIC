"""
RRG Analyzer — Implementazione fedele del file Excel RRG_S_P500_Sectors_JdK.xlsx
=================================================================================
Pipeline matematica identica al foglio JdK_Calcoli:

  RS_raw(t)    = Settore(t) / Benchmark(t)
  EMA12(seed)  = SMA(RS_raw, 12 barre)           [row 13 in Excel]
  EMA12(t)     = EMA12(t-1) + k12*(RS_raw(t) - EMA12(t-1)),  k12 = 2/13
  EMA26(seed)  = SMA(EMA12, 26 barre)            [row 38 in Excel]
  RS_s(t)      = EMA26(t-1) + k26*(EMA12(t) - EMA26(t-1)),  k26 = 2/27
  RS-Ratio(t)  = 100 * RS_s(t) / AVERAGE(RS_s[anchor : t])  [row 89 = anchor+52]
                 anchor = primo valore valido di RS_s (row 38 in Excel)
                 finestra espansa: start fisso, end avanza
  RS-Mom(t)    = 100 * RS-Ratio(t) / AVERAGE(RS-Ratio[t-13 : t])  rolling 14 barre

Versione alternativa (RS_Calcoli + Momentum):
  RS-Ratio_z   = 100 + 10*(RS_s - mu52) / sigma52    z-score rolling 52 barre
  RS-Mom_z     = 100 + 10*(d - mu10) / sigma10        z-score rolling 10 barre su d
"""

import io
import math
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title="RRG Analyzer — JdK Method",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────
# CSS
# ─────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Mono:wght@300;400;500&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background: #F0F4FA; }

.rrg-header {
    background: linear-gradient(135deg, #0F2A56 60%, #1A3A72);
    border: 1px solid rgba(255,255,255,0.12);
    padding: 28px 36px 24px;
    border-radius: 18px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(15,42,86,0.18);
}
.rrg-header::before {
    content: '';
    position: absolute;
    top: -60px; right: -60px;
    width: 260px; height: 260px;
    background: radial-gradient(circle, rgba(147,197,253,0.12) 0%, transparent 70%);
    border-radius: 50%;
}
.rrg-header-tag {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    color: #93C5FD;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 8px;
}
.rrg-header h1 {
    font-family: 'Syne', sans-serif;
    font-size: 28px;
    font-weight: 800;
    color: #FFFFFF;
    margin: 0 0 6px;
    letter-spacing: -0.6px;
}
.rrg-header p {
    color: rgba(186,214,254,0.6);
    font-size: 12px;
    margin: 0;
    font-weight: 300;
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.04em;
}

.metrics-row {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin-bottom: 24px;
}
.metric-card {
    background: #FFFFFF;
    border: 1px solid #DBEAFE;
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: 0 1px 6px rgba(15,42,86,0.07);
}
.metric-card .mc-label {
    font-family: 'DM Mono', monospace;
    font-size: 9px;
    color: #6B8CC4;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin-bottom: 8px;
}
.metric-card .mc-value {
    font-family: 'Syne', sans-serif;
    font-size: 24px;
    font-weight: 700;
    color: #0F2A56;
    line-height: 1;
}
.metric-card .mc-sub {
    font-size: 10px;
    color: #8AAAD4;
    margin-top: 4px;
    font-family: 'DM Mono', monospace;
}

.section-label {
    font-family: 'DM Mono', monospace;
    font-size: 9px;
    color: #3B82F6;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid #DBEAFE;
}

.formula-box {
    background: #F8FAFF;
    border: 1px solid #DBEAFE;
    border-left: 3px solid #3B82F6;
    border-radius: 10px;
    padding: 16px 18px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: #334E7A;
    line-height: 1.9;
}
.formula-box b { color: #0F2A56; }

.q-badge {
    display: inline-block;
    padding: 3px 9px;
    border-radius: 20px;
    font-size: 10px;
    font-family: 'DM Mono', monospace;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.q-leading   { background: rgba(16,185,129,0.10); color: #059669; border: 1px solid rgba(16,185,129,0.25); }
.q-weakening { background: rgba(217,119,6,0.10);  color: #B45309; border: 1px solid rgba(217,119,6,0.25); }
.q-lagging   { background: rgba(220,38,38,0.10);  color: #DC2626; border: 1px solid rgba(220,38,38,0.25); }
.q-improving { background: rgba(37,99,235,0.10);  color: #1D4ED8; border: 1px solid rgba(37,99,235,0.25); }

table { width: 100%; border-collapse: collapse; font-size: 12px; background: transparent; }
th {
    font-family: 'DM Mono', monospace;
    font-size: 9px;
    color: #6B8CC4;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid #DBEAFE;
    background: #F0F6FF;
}
td {
    padding: 9px 14px;
    color: #1E3A5F;
    border-bottom: 1px solid #EEF4FF;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
}
tr:hover td { background: #EFF6FF; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════
#  MATEMATICA — IDENTICA AL FILE EXCEL
# ═══════════════════════════════════════════════════════

def ema_sma_seed(series: pd.Series, period: int) -> pd.Series:
    """
    EMA con seme SMA — identica a Excel JdK_Calcoli:
      Row seed   = AVERAGE(prime [period] osservazioni valide)
                   [AT13]=AVERAGE(B2:B13)  per EMA12
                   [BE38]=AVERAGE(AT13:AT38)  per EMA26
      Row seed+1 = prev + k*(curr-prev),  k = 2/(period+1)
                   [AT14]=AT13+(2/13)*(B14-AT13)
    """
    k = 2.0 / (period + 1)
    arr = series.values.astype(float)
    out = np.full(len(arr), np.nan)

    valid_pos = np.where(~np.isnan(arr))[0]
    if len(valid_pos) < period:
        return pd.Series(out, index=series.index)

    seed_pos = valid_pos[period - 1]
    out[seed_pos] = np.nanmean(arr[valid_pos[:period]])

    for i in range(seed_pos + 1, len(arr)):
        if np.isnan(arr[i]):
            out[i] = np.nan
        else:
            out[i] = arr[i] * k + out[i - 1] * (1 - k)

    return pd.Series(out, index=series.index)


def compute_jdk_method(
    df: pd.DataFrame,
    benchmark_col: str,
    sector_cols: list,
    ema_short: int = 12,
    ema_long: int = 26,
    ratio_window: int = 52,
    momentum_window: int = 14,
) -> dict:
    """
    Pipeline esatta del foglio JdK_Calcoli del file Excel.

    RS-RATIO (Excel formula, riga 89+):
      [F89] = IF(E89="","", 100*E89/AVERAGE(E38:E89))
      [F90] = IF(E90="","", 100*E90/AVERAGE(E39:E90))
      L'anchor E38 = primo valore valido di RS_s.
      La finestra si espande di 1 ad ogni riga.
      Prima barra valida = quando ci sono >= ratio_window barre di RS_s.

    RS-MOMENTUM (Excel formula, riga 102+):
      [G102] = IF(F102="","", 100*F102/AVERAGE(F89:F102))
      Rolling fissa di momentum_window barre sul RS-Ratio.
    """
    results = {}

    for col in sector_cols:
        # STEP 1: RS_raw = Settore / Benchmark
        rs_raw = (df[col] / df[benchmark_col]).replace([np.inf, -np.inf], np.nan)

        # STEP 2: EMA12(RS_raw)
        ema12 = ema_sma_seed(rs_raw, ema_short)

        # STEP 3: EMA26(EMA12) = RS_s
        rs_s = ema_sma_seed(ema12, ema_long)

        # STEP 4: RS-Ratio con finestra espansa (anchor fisso)
        rs_s_arr = rs_s.values.astype(float)
        ratio_arr = np.full(len(rs_s_arr), np.nan)

        valid_rs_pos = np.where(~np.isnan(rs_s_arr))[0]
        if len(valid_rs_pos) >= ratio_window:
            anchor_pos = valid_rs_pos[0]  # row 38 in Excel

            for i in range(anchor_pos, len(rs_s_arr)):
                if np.isnan(rs_s_arr[i]):
                    continue
                # window = RS_s[anchor_pos : i+1]
                window = rs_s_arr[anchor_pos: i + 1]
                window_valid = window[~np.isnan(window)]
                if len(window_valid) < ratio_window:
                    continue
                mean_val = np.mean(window_valid)
                if mean_val != 0:
                    ratio_arr[i] = 100.0 * rs_s_arr[i] / mean_val

        rs_ratio = pd.Series(ratio_arr, index=df.index)

        # STEP 5: RS-Momentum rolling fissa momentum_window barre
        ratio_vals = rs_ratio.values.astype(float)
        mom_arr = np.full(len(ratio_vals), np.nan)

        for i in range(len(ratio_vals)):
            if np.isnan(ratio_vals[i]):
                continue
            start = i - momentum_window + 1
            if start < 0:
                continue
            window = ratio_vals[start: i + 1]
            window_valid = window[~np.isnan(window)]
            if len(window_valid) < momentum_window:
                continue
            mean_val = np.mean(window_valid)
            if mean_val != 0:
                mom_arr[i] = 100.0 * ratio_vals[i] / mean_val

        rs_momentum = pd.Series(mom_arr, index=df.index)

        results[col] = {
            "rs_raw":      rs_raw,
            "ema12":       ema12,
            "rs_s":        rs_s,
            "rs_ratio":    rs_ratio,
            "rs_momentum": rs_momentum,
        }

    return results


def compute_zscore_method(
    df: pd.DataFrame,
    benchmark_col: str,
    sector_cols: list,
    ema_short: int = 12,
    ema_long: int = 26,
    zscore_window: int = 52,
    momentum_window: int = 10,
) -> dict:
    """
    Pipeline esatta dei fogli RS_Calcoli + Momentum (versione z-score).

    RS-RATIO (Excel RS_Calcoli, col AI, riga 89+):
      M89 = AVERAGE(BP38:BP89)    rolling 52 barre
      X89 = STDEVP(BP38:BP89)     deviazione standard popolazione ddof=0
      [AI89] = IF(X89=0,"", 100+10*(BP89-M89)/X89)

    d(RS-Ratio) (Momentum sheet, col B, riga 90+):
      [B90] = RS_Calcoli!AI90 - RS_Calcoli!AI89

    RS-MOMENTUM (Momentum sheet, col AI, riga 90+):
      mu  = AVERAGE(B81:B90)   rolling 10 barre
      sig = STDEVP(B81:B90)    ddof=0
      [AI90] = 100+10*(B90-mu)/sig
    """
    results = {}
    for col in sector_cols:
        rs_raw = (df[col] / df[benchmark_col]).replace([np.inf, -np.inf], np.nan)
        ema12  = ema_sma_seed(rs_raw, ema_short)
        rs_s   = ema_sma_seed(ema12, ema_long)

        roll_mean = rs_s.rolling(zscore_window, min_periods=zscore_window).mean()
        roll_std  = rs_s.rolling(zscore_window, min_periods=zscore_window).std(ddof=0)
        rs_ratio  = 100.0 + 10.0 * (rs_s - roll_mean) / roll_std.replace(0, np.nan)

        d_ratio = rs_ratio.diff()
        m_mean  = d_ratio.rolling(momentum_window, min_periods=momentum_window).mean()
        m_std   = d_ratio.rolling(momentum_window, min_periods=momentum_window).std(ddof=0)
        rs_mom  = 100.0 + 10.0 * (d_ratio - m_mean) / m_std.replace(0, np.nan)

        results[col] = {
            "rs_raw":      rs_raw,
            "ema12":       ema12,
            "rs_s":        rs_s,
            "rs_ratio":    rs_ratio,
            "rs_momentum": rs_mom,
        }
    return results


def get_quadrant(x: float, y: float) -> str:
    if x >= 100 and y >= 100: return "leading"
    if x >= 100 and y <  100: return "weakening"
    if x <  100 and y <  100: return "lagging"
    return "improving"


# ═══════════════════════════════════════════════════════
#  FILE PARSING
# ═══════════════════════════════════════════════════════

def _read_csv_autodetect(raw: bytes) -> pd.DataFrame:
    sample = raw[:4096].decode("utf-8", errors="replace")
    first_line = sample.split("\n")[0]
    sep_counts = {";": first_line.count(";"), ",": first_line.count(","), "\t": first_line.count("\t")}
    sep = max(sep_counts, key=sep_counts.get)
    decimal = "," if sep == ";" else "."
    df = pd.read_csv(io.BytesIO(raw), sep=sep, decimal=decimal)
    if df.shape[1] <= 1:
        alt = "." if decimal == "," else ","
        df = pd.read_csv(io.BytesIO(raw), sep=sep, decimal=alt)
    return df


def parse_file(uploaded) -> pd.DataFrame:
    raw  = uploaded.read()
    name = uploaded.name.lower()

    if name.endswith(".csv"):
        df = _read_csv_autodetect(raw)
    elif name.endswith((".xlsx", ".xls")):
        xls = pd.ExcelFile(io.BytesIO(raw))
        sheet = "Input_Prezzi" if "Input_Prezzi" in xls.sheet_names else xls.sheet_names[0]
        df = pd.read_excel(io.BytesIO(raw), sheet_name=sheet)
    else:
        raise ValueError("Formato non supportato. Carica un file .xlsx o .csv")

    if df.empty:
        raise ValueError("Il file e' vuoto.")

    date_col = None
    for col in df.columns:
        if any(k in str(col).lower() for k in ("date", "data", "time", "periodo", "settimana")):
            date_col = col
            break
    if date_col is None:
        date_col = df.columns[0]

    parsed = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
    if parsed.isna().all():
        parsed = pd.to_datetime(df[date_col], format="mixed", dayfirst=True, errors="coerce")
    if parsed.isna().all():
        raise ValueError(f"Impossibile interpretare '{date_col}' come colonna date.")

    df[date_col] = parsed
    df = df.dropna(subset=[date_col]).set_index(date_col)
    df.index = pd.DatetimeIndex(df.index)
    df = df.sort_index()

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = (df[col].astype(str).str.strip()
                       .str.replace(".", "", regex=False)
                       .str.replace(",", ".", regex=False))
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(how="all")
    df = df[df.index.notna()]

    if df.empty:
        raise ValueError("Nessun dato numerico valido trovato dopo la pulizia.")
    return df


def resample_prices(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """
    Resample preservando la data REALE dell ultima osservazione nel bucket.
    Pandas allinea l indice alla fine del bucket (W-FRI = venerdi SUCCESSIVO),
    causando date future (es. 20/03 invece di 08/03).
    Fix: rimappa ogni bucket con l ultima data originale effettivamente presente.
    """
    freq_map = {"Daily": None, "Weekly": "W-FRI", "Monthly": "ME"}
    rule = freq_map.get(freq)
    if not rule:
        return df

    df_resampled = df.resample(rule).last().dropna(how="all")

    # Per ogni bucket pandas, trova l ultima data REALE del dataframe originale
    real_last_dates = pd.Series(df.index, index=df.index).resample(rule).last()
    df_resampled.index = pd.DatetimeIndex([
        real_last_dates[bl] if bl in real_last_dates.index else bl
        for bl in df_resampled.index
    ])
    return df_resampled


# ═══════════════════════════════════════════════════════
#  PLOTLY — RRG CHART
# ═══════════════════════════════════════════════════════

SECTOR_COLORS = [
    "#3B82F6", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6",
    "#06B6D4", "#F97316", "#84CC16", "#EC4899", "#14B8A6",
    "#6366F1", "#FB923C", "#A3E635", "#E879F9", "#38BDF8",
]

QUADRANT_STYLE = {
    "leading":   {"color": "#059669", "bg": "rgba(16,185,129,0.07)",  "label": "LEADING"},
    "weakening": {"color": "#B45309", "bg": "rgba(217,119,6,0.07)",   "label": "WEAKENING"},
    "lagging":   {"color": "#DC2626", "bg": "rgba(220,38,38,0.07)",   "label": "LAGGING"},
    "improving": {"color": "#1D4ED8", "bg": "rgba(37,99,235,0.07)",   "label": "IMPROVING"},
}


def _sf(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def build_rrg_figure(
    results: dict,
    show_trails: bool = True,
    trail_length: int = 8,
    show_vectors: bool = True,
    dark_mode: bool = True,
) -> go.Figure:
    fig = go.Figure()

    all_x, all_y = [], []
    for v in results.values():
        all_x += [float(x) for x in v["rs_ratio"].dropna().values]
        all_y += [float(y) for y in v["rs_momentum"].dropna().values]

    if not all_x:
        return fig

    rx = max(all_x) - min(all_x)
    ry = max(all_y) - min(all_y)
    padx = max(2.5, rx * 0.12)
    pady = max(2.5, ry * 0.12)
    xmin, xmax = min(all_x) - padx, max(all_x) + padx
    ymin, ymax = min(all_y) - pady, max(all_y) + pady

    bg_paper = "#F0F4FA" if not dark_mode else "#0D1F3C"
    bg_plot  = "#F8FAFF" if not dark_mode else "#0F2444"
    cross_c  = "rgba(15,42,86,0.13)" if not dark_mode else "rgba(147,197,253,0.18)"
    tick_c   = "#7A9CC4" if not dark_mode else "#5B82B8"
    axis_c   = "#2C4F85" if not dark_mode else "#7BAEE8"

    quads = [
        ("leading",   100,  xmax, 100,  ymax,  xmax - padx * 0.25, ymax - pady * 0.35),
        ("weakening", 100,  xmax, ymin, 100,   xmax - padx * 0.25, ymin + pady * 0.35),
        ("lagging",   xmin, 100,  ymin, 100,   xmin + padx * 0.25, ymin + pady * 0.35),
        ("improving", xmin, 100,  100,  ymax,  xmin + padx * 0.25, ymax - pady * 0.35),
    ]
    for qname, x0, x1, y0, y1, lx, ly in quads:
        qs = QUADRANT_STYLE[qname]
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=qs["bg"], line_width=0, layer="below")
        fig.add_annotation(x=lx, y=ly, text=qs["label"],
                           font=dict(size=9, color=qs["color"], family="DM Mono"),
                           showarrow=False, opacity=0.45)

    for shape_kw in [
        dict(x0=100, x1=100, y0=ymin, y1=ymax),
        dict(x0=xmin, x1=xmax, y0=100, y1=100),
    ]:
        fig.add_shape(type="line", **shape_kw,
                      line=dict(color=cross_c, width=1.5, dash="dot"))

    for i, (name, v) in enumerate(results.items()):
        color = SECTOR_COLORS[i % len(SECTOR_COLORS)]
        ratio = v["rs_ratio"]
        mom   = v["rs_momentum"]

        valid = ratio.notna() & mom.notna()
        if not valid.any():
            continue

        last_idx = valid[::-1].idxmax()
        rx_val   = float(ratio[last_idx])
        ry_val   = float(mom[last_idx])
        qd       = get_quadrant(rx_val, ry_val)
        qcolor   = QUADRANT_STYLE[qd]["color"]

        if show_trails:
            valid_idx = valid[valid].index.tolist()
            pos       = valid_idx.index(last_idx)
            start_pos = max(0, pos - trail_length)
            trail_idx = valid_idx[start_pos: pos + 1]

            xs = [float(ratio[t]) for t in trail_idx]
            ys = [float(mom[t])   for t in trail_idx]
            n  = len(xs)

            for j in range(n - 1):
                alpha = 0.07 + 0.50 * (j / max(n - 2, 1))
                r_hex = int(qcolor[1:3], 16)
                g_hex = int(qcolor[3:5], 16)
                b_hex = int(qcolor[5:7], 16)
                rgba  = f"rgba({r_hex},{g_hex},{b_hex},{alpha:.2f})"
                sz    = 2.5 + 2.0 * (j / max(n - 2, 1))
                fig.add_trace(go.Scatter(
                    x=[xs[j], xs[j + 1]], y=[ys[j], ys[j + 1]],
                    mode="lines+markers",
                    line=dict(color=rgba, width=1.8),
                    marker=dict(size=[sz, 0], color=rgba),
                    hoverinfo="skip",
                    showlegend=False,
                    name=f"_t_{name}_{j}",
                ))

            if show_vectors and n >= 2:
                fig.add_annotation(
                    x=xs[-1], y=ys[-1], ax=xs[-2], ay=ys[-2],
                    xref="x", yref="y", axref="x", ayref="y",
                    showarrow=True, arrowhead=2,
                    arrowsize=1.2, arrowwidth=2.0,
                    arrowcolor=qcolor,
                )

        hover_lines = [
            f"<b>{name}</b>",
            f"RS-Ratio:    {rx_val:.4f}",
            f"RS-Momentum: {ry_val:.4f}",
            f"Quadrante:   {qd.capitalize()}",
            f"Data:        {last_idx.strftime('%d/%m/%Y')}",
        ]

        fig.add_trace(go.Scatter(
            x=[rx_val], y=[ry_val],
            mode="markers+text",
            name=name,
            marker=dict(
                size=16,
                color=qcolor,
                line=dict(color="#FFFFFF", width=2.5),
            ),
            text=[f"<b>{name}</b>"],
            textposition="top right",
            textfont=dict(size=11, color=qcolor, family="DM Sans"),
            hovertemplate="<br>".join(hover_lines) + "<extra></extra>",
            legendgroup=name,
        ))

    fig.update_layout(
        paper_bgcolor=bg_paper,
        plot_bgcolor=bg_plot,
        font=dict(family="DM Sans", color=axis_c),
        margin=dict(l=58, r=32, t=44, b=58),
        xaxis=dict(
            title=dict(text="RS-Ratio  ->  Forza Relativa",
                       font=dict(size=11, color=axis_c)),
            gridcolor="rgba(15,42,86,0.07)" if not dark_mode else "rgba(180,200,240,0.07)",
            tickfont=dict(family="DM Mono", size=9, color=tick_c),
            zeroline=False,
            range=[_sf(xmin), _sf(xmax)],
        ),
        yaxis=dict(
            title=dict(text="RS-Momentum  ^  Velocita",
                       font=dict(size=11, color=axis_c)),
            gridcolor="rgba(15,42,86,0.07)" if not dark_mode else "rgba(180,200,240,0.07)",
            tickfont=dict(family="DM Mono", size=9, color=tick_c),
            zeroline=False,
            range=[_sf(ymin), _sf(ymax)],
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.01,
            xanchor="left", x=0,
            font=dict(size=10, family="DM Sans"),
            bgcolor="rgba(240,244,250,0.92)" if not dark_mode else "rgba(13,31,60,0.85)",
            bordercolor="#DBEAFE" if not dark_mode else "rgba(255,255,255,0.07)",
            borderwidth=1,
        ),
        hoverlabel=dict(
            bgcolor="#0F2A56" if not dark_mode else "#0D1F3C",
            font=dict(color="#DBEAFE", family="DM Mono", size=11),
            bordercolor="rgba(59,130,246,0.5)",
        ),
        height=660,
    )
    return fig


def build_results_table(results: dict) -> pd.DataFrame:
    rows = []
    for name, v in results.items():
        ratio = v["rs_ratio"].dropna()
        mom   = v["rs_momentum"].dropna()
        if ratio.empty or mom.empty:
            continue
        rx = float(ratio.iloc[-1])
        ry = float(mom.iloc[-1])
        qd = get_quadrant(rx, ry)
        d_ratio = ratio.iloc[-1] - ratio.iloc[-2] if len(ratio) >= 2 else np.nan
        d_mom   = mom.iloc[-1]   - mom.iloc[-2]   if len(mom)   >= 2 else np.nan
        rows.append({
            "Settore":     name,
            "RS-Ratio":    round(rx, 3),
            "D Ratio":     f"{d_ratio:+.3f}" if not np.isnan(d_ratio) else "-",
            "RS-Momentum": round(ry, 3),
            "D Momentum":  f"{d_mom:+.3f}" if not np.isnan(d_mom) else "-",
            "Quadrante":   qd.capitalize(),
            "Data":        ratio.index[-1].strftime("%d/%m/%Y"),
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════
#  INTERFACCIA STREAMLIT
# ═══════════════════════════════════════════════════════

st.markdown("""
<div class="rrg-header">
  <div class="rrg-header-tag">Relative Rotation Graph - Julius de Kempenaer Methodology</div>
  <h1>RRG Analyzer</h1>
  <p>EMA12 - EMA26 - RS_s | RS-Ratio = 100*RS_s/Media(RS_s) | RS-Momentum = 100*Ratio/Media14(Ratio)</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ──
with st.sidebar:
    st.markdown("### Parametri")
    st.markdown("---")

    method = st.selectbox(
        "Metodo di calcolo",
        ["JdK Originale (JdK_Calcoli)", "Z-Score Statistico (RS_Calcoli)"],
        help="JdK: 100*RS_s/Media (foglio JdK_Calcoli)\nZ-Score: 100+10*(x-mu)/sigma (RS_Calcoli+Momentum)",
    )

    st.markdown("**EMA Smoothing**")
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        ema_short = st.number_input("EMA breve", min_value=3, max_value=30, value=12, step=1)
    with col_e2:
        ema_long = st.number_input("EMA lungo", min_value=5, max_value=60, value=26, step=1)

    st.markdown("**Finestre normalizzazione**")
    ratio_win = st.slider("Finestra RS-Ratio (default 52)", 10, 120, 52)
    mom_win   = st.slider("Finestra RS-Momentum (default 14)", 3, 40, 14)

    if "Z-Score" in method:
        st.markdown("**Z-Score specifico**")
        zscore_win = st.slider("z-score RS-Ratio", 10, 120, 52)
        mom_zscore = st.slider("z-score Momentum", 3, 40, 10)
    else:
        zscore_win = 52
        mom_zscore = 10

    st.markdown("---")
    st.markdown("**Visualizzazione**")
    dark_mode    = st.toggle("Tema scuro", value=False)
    show_trails  = st.toggle("Scie storiche", value=True)
    trail_len    = st.slider("Lunghezza scia", 2, 24, 8)
    show_vectors = st.toggle("Vettori direzionali", value=True)

    st.markdown("---")
    st.markdown("**Frequenza dati**")
    freq = st.selectbox("Resample", ["Weekly", "Daily", "Monthly"], index=0)

    st.markdown("---")
    jdk_active = "JdK" in method
    st.markdown(f"""
    <div style="font-size:10px; color:#8AAAD4; font-family:monospace; line-height:2.0;">
    {"JdK_Calcoli ATTIVO" if jdk_active else "RS_Calcoli ATTIVO"}<br>
    RS_raw = Settore / Benchmark<br>
    EMA{ema_short} seed=SMA{ema_short}<br>
    EMA{ema_long}(EMA{ema_short}) = RS_s<br>
    {"RS-Ratio = 100*RS_s/Media(RS_s)" if jdk_active else "RS-Ratio = 100+10*zscore52"}<br>
    {"RS-Mom = 100*Ratio/Media14(Ratio)" if jdk_active else "RS-Mom = 100+10*zscore10(d)"}
    </div>
    """, unsafe_allow_html=True)


# ── Upload ──
col_up, col_info = st.columns([3, 2])

with col_up:
    st.markdown('<div class="section-label">01 - CARICAMENTO DATI</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Carica il tuo file",
        type=["xlsx", "xls", "csv"],
        help="Excel: legge foglio 'Input_Prezzi'. CSV: rileva auto sep e decimali.",
        label_visibility="collapsed",
    )

with col_info:
    st.markdown('<div class="section-label">STRUTTURA ATTESA</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="formula-box">
    <b>Col A</b>  Date settimanali<br>
    <b>Col B</b>  Benchmark (S&P 500 PR)<br>
    <b>Col C+</b> Settori GICS<br><br>
    <b>Excel</b>  foglio Input_Prezzi<br>
    <b>CSV</b>    rileva auto ; , tab
    </div>
    """, unsafe_allow_html=True)


if uploaded is None:
    st.markdown("""
    <div style="text-align:center; padding:100px 0; color:rgba(140,160,200,0.25);">
      <div style="font-size:56px; margin-bottom:18px; opacity:0.4;">&#9672;</div>
      <div style="font-family:monospace; font-size:11px; letter-spacing:0.15em;">
        CARICA UN FILE EXCEL O CSV PER INIZIARE
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()


try:
    df_raw = parse_file(uploaded)
except Exception as e:
    st.error(f"Errore nel parsing: {e}")
    st.stop()


all_cols = list(df_raw.columns)
if len(all_cols) < 2:
    st.error("Il file deve avere almeno 2 colonne (benchmark + 1 settore).")
    st.stop()

st.markdown('<div class="section-label">02 - SELEZIONE COLONNE</div>', unsafe_allow_html=True)
c1, c2 = st.columns([1, 3])
with c1:
    benchmark_col = st.selectbox("Benchmark", all_cols, index=0)
with c2:
    default_sectors = [c for c in all_cols if c != benchmark_col]
    sector_cols = st.multiselect("Settori", default_sectors, default=default_sectors)

if not sector_cols:
    st.warning("Seleziona almeno un settore.")
    st.stop()

df = resample_prices(df_raw, freq)

idx_valid = df.index[df.index.notna()]
if len(idx_valid) == 0:
    st.error("Nessuna data valida trovata.")
    st.stop()

date_min = idx_valid.min().to_pydatetime().date()
date_max = idx_valid.max().to_pydatetime().date()

st.markdown('<div class="section-label">03 - INTERVALLO TEMPORALE</div>', unsafe_allow_html=True)
d1, d2 = st.columns(2)
with d1:
    start_date = st.date_input("Dal", value=date_min, min_value=date_min, max_value=date_max)
with d2:
    end_date = st.date_input("Al", value=date_max, min_value=date_min, max_value=date_max)

df = df.loc[pd.Timestamp(start_date): pd.Timestamp(end_date)]
if df.empty:
    st.warning("Nessun dato nell'intervallo selezionato.")
    st.stop()


try:
    if "JdK" in method:
        results = compute_jdk_method(
            df, benchmark_col, sector_cols,
            ema_short=ema_short,
            ema_long=ema_long,
            ratio_window=ratio_win,
            momentum_window=mom_win,
        )
    else:
        results = compute_zscore_method(
            df, benchmark_col, sector_cols,
            ema_short=ema_short,
            ema_long=ema_long,
            zscore_window=zscore_win,
            momentum_window=mom_zscore,
        )
except Exception as e:
    st.error(f"Errore nel calcolo: {e}")
    st.stop()


df_tbl      = build_results_table(results)
n_bars      = len(df)
n_leading   = len(df_tbl[df_tbl["Quadrante"] == "Leading"])
n_improving = len(df_tbl[df_tbl["Quadrante"] == "Improving"])
n_weakening = len(df_tbl[df_tbl["Quadrante"] == "Weakening"])
n_lagging   = len(df_tbl[df_tbl["Quadrante"] == "Lagging"])
valid_count = len(df_tbl)
warmup_rows = ema_short + ema_long + ratio_win + mom_win
usable_rows = max(0, n_bars - warmup_rows)

st.markdown(f"""
<div class="metrics-row">
  <div class="metric-card">
    <div class="mc-label">Barre totali</div>
    <div class="mc-value">{n_bars}</div>
    <div class="mc-sub">{freq} · {start_date}</div>
  </div>
  <div class="metric-card">
    <div class="mc-label">Warm-up consumato</div>
    <div class="mc-value" style="color:#2563EB">{warmup_rows}</div>
    <div class="mc-sub">utili: {usable_rows} barre</div>
  </div>
  <div class="metric-card">
    <div class="mc-label">Settori validi</div>
    <div class="mc-value">{valid_count}</div>
    <div class="mc-sub">su {len(sector_cols)} selezionati</div>
  </div>
  <div class="metric-card">
    <div class="mc-label">Leading + Improving</div>
    <div class="mc-value" style="color:#059669">{n_leading + n_improving}</div>
    <div class="mc-sub">L:{n_leading} · I:{n_improving}</div>
  </div>
  <div class="metric-card">
    <div class="mc-label">Lagging + Weakening</div>
    <div class="mc-value" style="color:#DC2626">{n_lagging + n_weakening}</div>
    <div class="mc-sub">Lag:{n_lagging} · W:{n_weakening}</div>
  </div>
</div>
""", unsafe_allow_html=True)


st.markdown('<div class="section-label">04 - RELATIVE ROTATION GRAPH</div>', unsafe_allow_html=True)

fig = build_rrg_figure(
    results,
    show_trails=show_trails,
    trail_length=trail_len,
    show_vectors=show_vectors,
    dark_mode=dark_mode,
)
st.plotly_chart(fig, use_container_width=True)


st.markdown('<div class="section-label">05 - TABELLA RISULTATI (ultima data)</div>', unsafe_allow_html=True)

def _badge(q):
    cl = q.lower()
    return f'<span class="q-badge q-{cl}">{q}</span>'

df_display = df_tbl.copy()
df_display["Quadrante"] = df_display["Quadrante"].apply(_badge)
df_display = df_display.sort_values("RS-Ratio", ascending=False).reset_index(drop=True)
st.markdown(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)


st.markdown("---")
st.markdown('<div class="section-label">06 - DATI INTERMEDI E DEBUG</div>', unsafe_allow_html=True)

with st.expander("Serie storiche complete per settore"):
    tab_ratio, tab_mom, tab_rs, tab_ema12, tab_raw = st.tabs([
        "RS-Ratio", "RS-Momentum", "RS_s (EMA26)", "EMA12", "RS_raw"
    ])
    with tab_ratio:
        st.caption("RS-Ratio = 100 * RS_s(t) / AVERAGE(RS_s[anchor:t])")
        st.dataframe(pd.DataFrame({n: v["rs_ratio"] for n, v in results.items()}).dropna(how="all").round(4), use_container_width=True)
    with tab_mom:
        st.caption("RS-Momentum = 100 * RS-Ratio(t) / AVERAGE(RS-Ratio[t-13:t])")
        st.dataframe(pd.DataFrame({n: v["rs_momentum"] for n, v in results.items()}).dropna(how="all").round(4), use_container_width=True)
    with tab_rs:
        st.caption("RS_s = EMA26(EMA12(RS_raw))")
        st.dataframe(pd.DataFrame({n: v["rs_s"] for n, v in results.items()}).dropna(how="all").round(6), use_container_width=True)
    with tab_ema12:
        st.caption("EMA12(RS_raw) — k = 2/13")
        st.dataframe(pd.DataFrame({n: v["ema12"] for n, v in results.items()}).dropna(how="all").round(6), use_container_width=True)
    with tab_raw:
        st.caption("RS_raw = Settore / Benchmark")
        st.dataframe(pd.DataFrame({n: v["rs_raw"] for n, v in results.items()}).dropna(how="all").round(6), use_container_width=True)


with st.expander("Analisi warm-up e disponibilita dati"):
    st.markdown(f"""
    <div class="formula-box">
    <b>TIMELINE WARM-UP (identica al file Excel)</b><br><br>
    Row 2        Prima RS_raw disponibile<br>
    Row {1+ema_short:3d}      Seme EMA{ema_short} = SMA delle prime {ema_short} osservazioni<br>
    Row {1+ema_short+1:3d}      EMA{ema_short} propaga   k={2/(ema_short+1):.4f}<br>
    Row {1+ema_short+ema_long:3d}      Seme EMA{ema_long} = SMA delle prime {ema_long} osservazioni di EMA{ema_short}<br>
    Row {1+ema_short+ema_long+1:3d}      RS_s propaga   k={2/(ema_long+1):.4f}<br>
    Row {1+ema_short+ema_long+ratio_win:3d}      PRIMO RS-RATIO valido (finestra minima {ratio_win} barre di RS_s)<br>
    Row {1+ema_short+ema_long+ratio_win+mom_win:3d}      PRIMO RS-MOMENTUM valido (finestra {mom_win} barre di RS-Ratio)<br><br>
    Barre totali: {n_bars}  |  Warm-up: {warmup_rows} ({ema_short}+{ema_long}+{ratio_win}+{mom_win})  |  Utili: {usable_rows}
    </div>
    """, unsafe_allow_html=True)

    warmup_data = []
    for name, v in results.items():
        warmup_data.append({
            "Settore": name,
            "RS_raw": int(v["rs_raw"].notna().sum()),
            "EMA12":  int(v["ema12"].notna().sum()),
            "RS_s":   int(v["rs_s"].notna().sum()),
            "RS-Ratio": int(v["rs_ratio"].notna().sum()),
            "RS-Momentum": int(v["rs_momentum"].notna().sum()),
        })
    st.dataframe(pd.DataFrame(warmup_data), use_container_width=True, hide_index=True)


with st.expander("Riferimento formule matematiche complete"):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("""
        <div class="formula-box">
        <b>PIPELINE JdK_Calcoli (metodo principale)</b><br><br>

        <b>STEP 1 - RS_raw</b><br>
        RS_raw(t) = Settore(t) / Benchmark(t)<br>
        Excel: =IFERROR(C2/B2,"")<br><br>

        <b>STEP 2 - EMA12  k=2/13=0.1538</b><br>
        seme: AVERAGE(B2:B13)  riga 13<br>
        prop: C13+(2/13)*(B14-C13)<br><br>

        <b>STEP 3 - EMA26(EMA12) = RS_s  k=2/27=0.0741</b><br>
        seme: AVERAGE(C13:C38)  riga 38<br>
        prop: D38+(2/27)*(C39-D38)<br><br>

        <b>STEP 4 - RS-Ratio finestra espansa</b><br>
        [F89]=100*E89/AVERAGE(E38:E89)<br>
        [F90]=100*E90/AVERAGE(E39:E90)<br>
        Anchor=primo RS_s valido (riga 38)<br>
        Finestra cresce +1 ogni riga<br>
        Attivo dopo min 52 barre di RS_s<br><br>

        <b>STEP 5 - RS-Momentum rolling 14</b><br>
        [G102]=100*F102/AVERAGE(F89:F102)<br>
        Rolling fissa 14 barre su RS-Ratio<br><br>

        <b>QUADRANTI</b><br>
        Leading:   X&gt;=100 AND Y&gt;=100<br>
        Weakening: X&gt;=100 AND Y&lt;100<br>
        Lagging:   X&lt;100 AND Y&lt;100<br>
        Improving: X&lt;100 AND Y&gt;=100
        </div>
        """, unsafe_allow_html=True)

    with col_b:
        st.markdown("""
        <div class="formula-box">
        <b>PIPELINE RS_Calcoli+Momentum (z-score)</b><br><br>

        <b>STEP 1-3</b> identici alla pipeline JdK<br><br>

        <b>STEP 4z - RS-Ratio z-score</b><br>
        M = AVERAGE(RS_s, rolling 52)  [col M]<br>
        S = STDEVP(RS_s, rolling 52)   [col X]  ddof=0<br>
        RS-Ratio = 100+10*(RS_s-M)/S   [col AI]<br>
        Excel: =IF(X89=0,"",100+10*(BP89-M89)/X89)<br><br>

        <b>STEP 5z - d(RS-Ratio)</b><br>
        d(t) = RS-Ratio(t) - RS-Ratio(t-1)<br>
        Excel: =IF(OR(AI90="",AI89=""),"",AI90-AI89)<br><br>

        <b>STEP 6z - RS-Momentum z-score</b><br>
        mu  = AVERAGE(d, rolling 10)   [col M]<br>
        sig = STDEVP(d, rolling 10)    [col X]  ddof=0<br>
        RS-Mom = 100+10*(d-mu)/sig<br>
        Excel: =IF(COUNT(B81:B90)&lt;2,"",<br>
               100+10*(B90-AVERAGE(B81:B90))/STDEVP(B81:B90))<br><br>

        <b>NOTA: STDEVP vs STDEV</b><br>
        Excel usa STDEVP (ddof=0, pop.) non STDEV<br>
        Istruzione foglio: "Questo file usa STDEVP<br>
        per compatibilita con Excel meno recente"
        </div>
        """, unsafe_allow_html=True)


with st.expander("JdK_RRG snapshot (replica foglio Excel)"):
    st.caption("Ultima riga valida per ciascun settore — replica del foglio JdK_RRG con INDEX/LOOKUP.")
    snap_rows = []
    for name, v in results.items():
        ratio = v["rs_ratio"].dropna()
        mom   = v["rs_momentum"].dropna()
        if ratio.empty or mom.empty:
            continue
        rx = float(ratio.iloc[-1])
        ry = float(mom.iloc[-1])
        snap_rows.append({
            "Sector":     name,
            "RS-Ratio X": round(rx, 4),
            "RS-Mom Y":   round(ry, 4),
            "X_line":     100,
            "Y_line":     100,
            "Quadrante":  get_quadrant(rx, ry).capitalize(),
            "Data":       ratio.index[-1].strftime("%d/%m/%Y"),
        })
    if snap_rows:
        st.dataframe(pd.DataFrame(snap_rows), use_container_width=True, hide_index=True)
