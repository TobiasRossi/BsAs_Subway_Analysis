import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Buenos Aires Subte — Frequency Analysis",
    page_icon="🚇",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_css(path):
    with open(path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)


load_css('style.css')

# ── Constants ──────────────────────────────────────────────────────────────────
LINE_COLORS = {
    'A': '#38BDF8',
    'B': '#F87171',
    'C': '#818CF8',
    'D': '#34D399',
    'E': '#C084FC',
    'H': '#FBBF24',
    'Premetro': '#94A3B8',
}

LINE_COLS    = ['line_A', 'line_B', 'line_C', 'line_D', 'line_E', 'line_H', 'premetro']
LINE_LABELS  = ['A', 'B', 'C', 'D', 'E', 'H', 'Premetro']
LABEL_TO_COL = dict(zip(LINE_LABELS, LINE_COLS))


def hex_to_rgba(hex_color, alpha=0.2):
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


def base_layout(**overrides):
    layout = dict(
        paper_bgcolor='#0f0f0f',
        plot_bgcolor='#0f0f0f',
        font=dict(family='IBM Plex Mono', color='#888', size=11),
        margin=dict(l=50, r=20, t=40, b=40),
        xaxis=dict(gridcolor='#1e1e1e', linecolor='#2a2a2a', tickcolor='#444'),
        yaxis=dict(gridcolor='#1e1e1e', linecolor='#2a2a2a', tickcolor='#444'),
    )
    layout.update(overrides)
    return layout


# ── Data ───────────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    raw = pd.read_excel('Subway_Frequency.xlsx')

    df = raw.copy()
    df['date'] = pd.to_datetime(df['mes_anio'], errors='coerce').dt.to_period('M').dt.to_timestamp()
    df = df[df['date'] < '2026-01-01'].copy()

    def parse_time_to_seconds(value):
        if pd.isna(value):
            return np.nan
        try:
            parts = str(value).strip().split(':')
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
        except (ValueError, AttributeError):
            return np.nan

    freq_cols = [
        'servicio_frecuencia_a', 'servicio_frecuencia_b', 'servicio_frecuencia_c',
        'servicio_frecuencia_d', 'servicio_frecuencia_e', 'servicio_frecuencia_h',
        'servicio_frecuencia_premetro',
    ]
    rename = {
        'servicio_frecuencia_a':        'line_A',
        'servicio_frecuencia_b':        'line_B',
        'servicio_frecuencia_c':        'line_C',
        'servicio_frecuencia_d':        'line_D',
        'servicio_frecuencia_e':        'line_E',
        'servicio_frecuencia_h':        'line_H',
        'servicio_frecuencia_premetro': 'premetro',
    }

    for col in freq_cols:
        df[col] = df[col].apply(parse_time_to_seconds)

    df = df.rename(columns=rename)
    df['year']  = df['date'].dt.year
    df['month'] = df['date'].dt.month

    # Impute line D Jan-Feb 2024
    q1_median = df[(df['year'] == 2024) & df['month'].between(3, 6)]['line_D'].median()
    df['line_D'] = df['line_D'].fillna(q1_median)

    # Cap outliers above 30 min (1800s), then convert to minutes
    df[LINE_COLS] = df[LINE_COLS].where(df[LINE_COLS] <= 1800) / 60

    return df[['date', 'year', 'month'] + LINE_COLS]


df = load_data()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.caption('LINES')
    selected_labels = st.multiselect(
        label='Lines',
        options=LINE_LABELS,
        default=LINE_LABELS,
        label_visibility='collapsed',
    )

    st.caption('DATE RANGE')
    min_date = df['date'].min().to_pydatetime()
    max_date = df['date'].max().to_pydatetime()
    date_range = st.slider(
        label='Date range',
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
        format='MMM YYYY',
        label_visibility='collapsed',
    )

    st.caption('ABOUT')
    st.caption('Source: Buenos Aires Data  \nUpdated monthly (1-month lag)  \nValues in minutes between trains')

# ── Filter ─────────────────────────────────────────────────────────────────────
if not selected_labels:
    st.warning('Select at least one line.')
    st.stop()

selected_cols = [LABEL_TO_COL[l] for l in selected_labels]
mask = (df['date'] >= pd.Timestamp(date_range[0])) & (df['date'] <= pd.Timestamp(date_range[1]))
dff  = df[mask].copy()

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="dash-title">🚇 Buenos Aires Subte — Service Frequency</div>'
    '<div class="dash-subtitle">Monthly average headway per line · 2019–2025</div>',
    unsafe_allow_html=True,
)
st.divider()

# ── KPI row ────────────────────────────────────────────────────────────────────
st.caption('SUMMARY — SELECTED PERIOD')
kpi_cols = st.columns(len(selected_labels))
for i, (label, col) in enumerate(zip(selected_labels, selected_cols)):
    series = dff[col].dropna()
    if series.empty:
        continue
    with kpi_cols[i]:
        st.metric(
            label=f'Line {label}',
            value=f'{series.mean():.1f} min',
            delta=f'peak {series.max():.1f} min',
            delta_color='inverse',
        )

st.divider()

# ── Time series ────────────────────────────────────────────────────────────────
st.caption('TIME SERIES — HEADWAY BY LINE')

fig_ts = go.Figure()
for label, col in zip(selected_labels, selected_cols):
    series = dff[['date', col]].dropna()
    fig_ts.add_trace(go.Scatter(
        x=series['date'],
        y=series[col],
        name=f'Line {label}',
        line=dict(color=LINE_COLORS[label], width=2),
        mode='lines',
        hovertemplate=f'<b>Line {label}</b><br>%{{x|%b %Y}}<br>%{{y:.1f}} min<extra></extra>',
    ))

fig_ts.add_vrect(
    x0='2020-03-20', x1='2020-12-31',
    fillcolor='rgba(255,60,60,0.07)',
    layer='below', line_width=0,
    annotation_text='COVID peak',
    annotation_position='top left',
    annotation=dict(font=dict(size=10, color='#555', family='IBM Plex Mono')),
)

fig_ts.update_layout(base_layout(
    height=360,
    hovermode='x unified',
    yaxis_title='Minutes between trains',
    xaxis_title=None,
    legend=dict(
        orientation='h', yanchor='bottom', y=1.02,
        xanchor='left', x=0,
        font=dict(size=11),
        bgcolor='rgba(0,0,0,0)',
    ),
))

st.plotly_chart(fig_ts, use_container_width=True)

st.divider()

# ── Line comparison ────────────────────────────────────────────────────────────
st.caption('LINE COMPARISON — DISTRIBUTION')
col_left, col_right = st.columns(2)

with col_left:
    fig_box = go.Figure()
    for label, col in zip(selected_labels, selected_cols):
        fig_box.add_trace(go.Box(
            y=dff[col].dropna(),
            name=f'Line {label}',
            marker_color=LINE_COLORS[label],
            line_color=LINE_COLORS[label],
            fillcolor=hex_to_rgba(LINE_COLORS[label], 0.35),
            boxmean=True,
            hovertemplate=f'<b>Line {label}</b><br>%{{y:.1f}} min<extra></extra>',
        ))
    fig_box.update_layout(base_layout(
        height=320,
        showlegend=False,
        yaxis_title='Minutes between trains',
        xaxis_title=None,
        title=dict(text='Distribution per line', font=dict(size=12, color='#666')),
    ))
    st.plotly_chart(fig_box, use_container_width=True)

with col_right:
    avgs = [dff[col].mean() for col in selected_cols]
    fig_bar = go.Figure(go.Bar(
        x=[f'Line {l}' for l in selected_labels],
        y=avgs,
        marker_color=[LINE_COLORS[l] for l in selected_labels],
        marker_line_color='#0f0f0f',
        marker_line_width=1,
        text=[f'{v:.1f}m' for v in avgs],
        textposition='outside',
        textfont=dict(size=11, family='IBM Plex Mono', color='#aaa'),
        hovertemplate='<b>%{x}</b><br>%{y:.2f} min avg<extra></extra>',
    ))
    fig_bar.update_layout(base_layout(
        height=320,
        showlegend=False,
        yaxis_title='Avg. minutes between trains',
        xaxis_title=None,
        title=dict(text='Average headway per line', font=dict(size=12, color='#666')),
    ))
    st.plotly_chart(fig_bar, use_container_width=True)
