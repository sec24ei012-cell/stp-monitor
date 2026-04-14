"""
components/charts.py
--------------------
All Plotly chart builders for the STP monitoring dashboard.
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

from utils.alerts import THRESHOLDS

# ── Colour palette ────────────────────────────────────────────────────────────
COLOURS = {
    "turbidity": "#1D9E75",   # teal
    "tds":       "#378ADD",   # blue
    "level":     "#BA7517",   # amber
    "flow":      "#D4537E",   # pink
}

UNITS = {
    "turbidity": "NTU",
    "tds":       "ppm",
    "level":     "%",
    "flow":      "L/min",
}

LABELS = {
    "turbidity": "Turbidity",
    "tds":       "TDS",
    "level":     "Tank Level",
    "flow":      "Flow Rate",
}


def _anomaly_mask(series: pd.Series, warn: float, crit: float) -> pd.Series:
    """Return True where value exceeds warning threshold."""
    return series >= warn


def build_timeseries_chart(df: pd.DataFrame,
                           selected_params: list[str],
                           show_anomalies: bool = True) -> go.Figure:
    """
    24-hour interactive rolling time-series chart.
    Supports zoom, hover, parameter toggling, and anomaly highlighting.
    """
    if df.empty or not selected_params:
        fig = go.Figure()
        fig.update_layout(
            title="No data yet – waiting for sensor readings…",
            template="plotly_white",
        )
        return fig

    rows = len(selected_params)
    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=[f"{LABELS[p]} ({UNITS[p]})" for p in selected_params],
    )

    for idx, param in enumerate(selected_params, start=1):
        if param not in df.columns:
            continue

        y      = df[param]
        x      = df["timestamp"]
        colour = COLOURS[param]
        warn_lvl, crit_lvl = THRESHOLDS.get(param, (None, None))

        # Main trace
        fig.add_trace(
            go.Scatter(
                x=x, y=y,
                mode="lines",
                name=LABELS[param],
                line=dict(color=colour, width=1.5),
                hovertemplate=(
                    f"<b>{LABELS[param]}</b>: %{{y:.1f}} {UNITS[param]}<br>"
                    "%{x|%H:%M:%S}<extra></extra>"
                ),
                legendgroup=param,
            ),
            row=idx, col=1,
        )

        # Warning band
        if warn_lvl is not None:
            fig.add_hline(
                y=warn_lvl, line_dash="dash",
                line_color="#BA7517", line_width=1,
                annotation_text="warn", annotation_position="right",
                row=idx, col=1,
            )

        # Critical band
        if crit_lvl is not None:
            fig.add_hline(
                y=crit_lvl, line_dash="dot",
                line_color="#E24B4A", line_width=1,
                annotation_text="crit", annotation_position="right",
                row=idx, col=1,
            )

        # Anomaly markers
        if show_anomalies and warn_lvl is not None:
            mask = _anomaly_mask(y, warn_lvl, crit_lvl)
            if mask.any():
                fig.add_trace(
                    go.Scatter(
                        x=x[mask], y=y[mask],
                        mode="markers",
                        name=f"{LABELS[param]} anomaly",
                        marker=dict(
                            color="#E24B4A",
                            size=6,
                            symbol="circle-open",
                            line=dict(width=1.5),
                        ),
                        hovertemplate=(
                            f"<b>ANOMALY</b> {LABELS[param]}: %{{y:.1f}} {UNITS[param]}<br>"
                            "%{x|%H:%M:%S}<extra></extra>"
                        ),
                        legendgroup=param,
                        showlegend=False,
                    ),
                    row=idx, col=1,
                )

    fig.update_layout(
        height=180 * rows + 60,
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        margin=dict(l=60, r=60, t=40, b=40),
        font=dict(family="IBM Plex Mono, monospace", size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
    )
    for i in range(1, rows + 1):
        fig.update_yaxes(
            showgrid=True, gridcolor="rgba(0,0,0,0.06)", row=i, col=1
        )

    return fig


def build_gauge_chart(value: float, param: str,
                      min_val: float = 0.0) -> go.Figure:
    """Compact gauge indicator for a single parameter."""
    warn_lvl, crit_lvl = THRESHOLDS.get(param, (value * 2, value * 3))
    max_val = crit_lvl * 1.3

    if value < warn_lvl:
        bar_color = "#1D9E75"   # green
    elif value < crit_lvl:
        bar_color = "#BA7517"   # amber
    else:
        bar_color = "#E24B4A"   # red

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number=dict(
            suffix=f" {UNITS.get(param, '')}",
            font=dict(size=20, family="IBM Plex Mono, monospace"),
        ),
        gauge=dict(
            axis=dict(range=[min_val, max_val], tickfont=dict(size=10)),
            bar=dict(color=bar_color, thickness=0.6),
            steps=[
                dict(range=[min_val, warn_lvl], color="#E1F5EE"),
                dict(range=[warn_lvl, crit_lvl], color="#FAEEDA"),
                dict(range=[crit_lvl, max_val],  color="#FCEBEB"),
            ],
            threshold=dict(
                line=dict(color="#E24B4A", width=2),
                thickness=0.8, value=crit_lvl,
            ),
        ),
        title=dict(text=LABELS.get(param, param),
                   font=dict(size=13, family="IBM Plex Mono, monospace")),
    ))
    fig.update_layout(
        height=200,
        margin=dict(l=20, r=20, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def build_correlation_heatmap(df: pd.DataFrame) -> go.Figure:
    """Pearson correlation matrix of all sensor parameters."""
    params = ["turbidity", "tds", "level", "flow"]
    avail  = [p for p in params if p in df.columns]
    if len(avail) < 2:
        return go.Figure()

    corr = df[avail].corr()
    labels = [LABELS[p] for p in avail]

    fig = go.Figure(go.Heatmap(
        z=corr.values,
        x=labels, y=labels,
        colorscale="RdBu",
        zmid=0,
        text=np.round(corr.values, 2),
        texttemplate="%{text}",
        hovertemplate="%{x} vs %{y}: %{z:.2f}<extra></extra>",
    ))
    fig.update_layout(
        title="Parameter correlation (last 24 h)",
        height=320,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Mono, monospace", size=11),
    )
    return fig
