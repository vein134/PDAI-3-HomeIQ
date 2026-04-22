GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap');

:root {
    --navy:      #0a0e1a;
    --navy-2:    #111827;
    --navy-3:    #1a2235;
    --navy-4:    #243048;
    --gold:      #c9a84c;
    --gold-light:#e8c97a;
    --gold-dim:  #7a6030;
    --cream:     #f5f0e8;
    --white:     #ffffff;
    --muted:     #8899aa;
}

.stApp, [data-testid="stAppViewContainer"] {
    background: var(--navy) !important;
    font-family: 'DM Sans', sans-serif !important;
}
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
.stDeployButton { display: none !important; }
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
section[data-testid="stSidebarCollapsedControl"] { display: none !important; }

.stMarkdown, .stText, p, li, span, label, div {
    color: var(--cream) !important;
    font-family: 'DM Sans', sans-serif !important;
}
h1, h2, h3, h4 {
    font-family: 'Playfair Display', serif !important;
    color: var(--white) !important;
}

[data-testid="stDataFrame"] { background: var(--navy-3) !important; }
[data-testid="stDataFrame"] td,
[data-testid="stDataFrame"] th {
    color: #ffffff !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 13px !important;
}
[data-testid="stDataFrame"] thead th {
    background: var(--navy-4) !important;
    color: var(--gold) !important;
    font-size: 11px !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
[data-testid="stMetric"] {
    background: var(--navy-3) !important;
    border: 1px solid var(--navy-4) !important;
    border-radius: 12px !important;
    padding: 20px !important;
}
[data-testid="stMetricLabel"] {
    color: var(--muted) !important;
    font-size: 11px !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
[data-testid="stMetricValue"] {
    color: var(--white) !important;
    font-family: 'Playfair Display', serif !important;
    font-size: 28px !important;
}
[data-testid="stTabs"] [role="tablist"] {
    background: var(--navy-2) !important;
    border-bottom: 1px solid var(--navy-4) !important;
    gap: 4px;
    padding: 4px 8px 0;
}
[data-testid="stTabs"] [role="tab"] {
    background: transparent !important;
    color: var(--muted) !important;
    border: none !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 13px !important;
    font-weight: 500;
    padding: 10px 18px !important;
    border-radius: 8px 8px 0 0 !important;
    transition: all 0.2s;
}
[data-testid="stTabs"] [role="tab"]:hover { color: var(--gold-light) !important; background: var(--navy-3) !important; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    background: var(--navy-3) !important;
    color: var(--gold) !important;
    border-bottom: 2px solid var(--gold) !important;
}
[data-testid="stTabContent"] {
    background: var(--navy-2) !important;
    border: 1px solid var(--navy-4) !important;
    border-top: none !important;
    border-radius: 0 0 12px 12px !important;
    padding: 24px !important;
}
[data-testid="stTabContent"] p,
[data-testid="stTabContent"] span,
[data-testid="stTabContent"] div {
    color: var(--cream) !important;
}
.stButton > button {
    background: linear-gradient(135deg, var(--gold), var(--gold-dim)) !important;
    color: var(--navy) !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 10px 24px !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 20px rgba(201,168,76,0.35) !important;
}
.stDownloadButton > button {
    background: var(--navy-3) !important;
    color: var(--gold) !important;
    border: 1px solid var(--gold-dim) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
[data-testid="stAlert"] {
    background: var(--navy-3) !important;
    border-radius: 10px !important;
    border-left-width: 3px !important;
}
[data-testid="stExpander"] {
    background: var(--navy-3) !important;
    border: 1px solid var(--navy-4) !important;
    border-radius: 10px !important;
}
hr { border-color: var(--navy-4) !important; margin: 24px 0 !important; }
[data-testid="stChatMessage"] {
    background: var(--navy-3) !important;
    border: 1px solid var(--navy-4) !important;
    border-radius: 12px !important;
}
[data-testid="stChatInput"] textarea {
    background: var(--navy-3) !important;
    border: 1px solid var(--navy-4) !important;
    color: var(--white) !important;
    border-radius: 10px !important;
}
.stTextArea textarea {
    background: #1a2640 !important;
    border: 1px solid #2a3550 !important;
    color: #f5f0e8 !important;
    border-radius: 8px !important;
    font-size: 14px !important;
}
.stNumberInput input,
.stTextInput input,
.stSelectbox > div > div,
.stMultiSelect > div > div,
.stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div,
input[type="number"],
input[type="text"] {
    background: #1a2640 !important;
    border: 1px solid #2a3550 !important;
    color: #ffffff !important;
    border-radius: 8px !important;
    font-size: 14px !important;
}
.stNumberInput label,
.stTextInput label,
.stSelectbox label,
.stMultiSelect label,
.stSlider label,
.stTextArea label {
    color: #b0c0d0 !important;
    font-size: 12px !important;
}
.stSlider [data-testid="stTickBarMin"],
.stSlider [data-testid="stTickBarMax"],
.stSlider span,
.stSlider div[data-testid="stThumbValue"] {
    color: #f5f0e8 !important;
}
[data-baseweb="select"] span,
[data-baseweb="tag"] span { color: #ffffff !important; }
[data-baseweb="tag"] {
    background: #243048 !important;
    border: 1px solid #c9a84c44 !important;
    color: #f5f0e8 !important;
}
div[data-baseweb="popover"],
div[data-baseweb="select"] ul,
div[data-baseweb="menu"] {
    background: #1a2640 !important;
    border: 1px solid #2a3550 !important;
    border-radius: 8px !important;
}
div[data-baseweb="menu"] li,
div[data-baseweb="option"] {
    background: #1a2640 !important;
    color: #f5f0e8 !important;
}
div[data-baseweb="option"]:hover,
div[data-baseweb="option"][aria-selected="true"] {
    background: #243048 !important;
    color: #c9a84c !important;
}
input::placeholder, textarea::placeholder { color: #8899aa !important; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--navy-2); }
::-webkit-scrollbar-thumb { background: var(--navy-4); border-radius: 3px; }
.stCaption, [data-testid="stCaptionContainer"] p {
    color: #aabbcc !important; font-size: 13px !important;
}
table { width: 100%; border-collapse: collapse; }
table td, table th {
    color: var(--white) !important; background: var(--navy-3) !important;
    border: 1px solid var(--navy-4) !important; padding: 8px 12px !important; font-size: 13px !important;
}
table thead th {
    background: var(--navy-4) !important; color: var(--gold) !important;
    font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.06em;
}
</style>
"""

PLOT_THEME = dict(
    paper_bgcolor="#111827", plot_bgcolor="#1a2235",
    font=dict(color="#f5f0e8", family="DM Sans"),
    xaxis=dict(gridcolor="#243048", linecolor="#243048"),
    yaxis=dict(gridcolor="#243048", linecolor="#243048"),
    legend=dict(
        bgcolor="rgba(26,34,53,0.9)",
        bordercolor="#2a3550",
        borderwidth=1,
        font=dict(color="#f5f0e8", size=12),
    ),
)

C = dict(
    gold="#c9a84c", green="#2dd4a0", red="#f87171", blue="#60a5fa",
    muted="#8899aa", purple="#a78bfa", orange="#fb923c", cyan="#22d3ee",
)

REGION_COLORS = {
    "London": "#c9a84c", "South East": "#60a5fa", "South West": "#2dd4a0",
    "East of England": "#818cf8", "East Midlands": "#a78bfa", "West Midlands": "#fb923c",
    "Yorkshire": "#22d3ee", "North West": "#f87171", "North East": "#f472b6",
    "Wales": "#34d399", "Scotland": "#fbbf24", "Northern Ireland": "#fb7185",
}


def hex_to_rgba(hex_color, alpha=0.13):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
