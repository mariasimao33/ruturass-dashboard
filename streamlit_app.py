import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import streamlit as st

LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/9/9c/CGD_Logo_2017.png"

st.set_page_config(
    page_title="Ruturas Dashboard",
    page_icon=LOGO_URL,
    layout="wide",
)

# -------------------------------------------------------------------------
# Legenda das métricas (REMOVIDO: Indisponíveis 1ª Linha)
# -------------------------------------------------------------------------
LEGEND_MD = """
**Legenda das métricas**

- **Ruturas**: máquina **sem numerário** ou com **saldo < 500€**  
- **Indisponíveis**: **inoperacional** (fora de serviço)  
"""

# Linha do topo com logo e título
c_logo, c_title = st.columns([0.12, 2.55])
with c_logo:
    st.image(LOGO_URL, width=72)

# -------------------------------------------------------------------------
# Autenticação por username/password usando Streamlit Secrets
# -------------------------------------------------------------------------
# Espera-se que no Secrets (Cloud) exista:
# [auth]
# username = "..."
# password = "..."

AUTH_USER = st.secrets["auth"].get("username", "")
AUTH_PASS = st.secrets["auth"].get("password", "")

# Inicializa estado de sessão
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None


def do_login(user, pwd):
    if user == AUTH_USER and pwd == AUTH_PASS:
        st.session_state.auth_ok = True
        st.session_state.auth_user = user
        return True
    return False


def do_logout():
    st.session_state.auth_ok = False
    st.session_state.auth_user = None


# UI de login (aparece se ainda não autenticado)
if not st.session_state.auth_ok:
    st.title("Ruturas Dashboard – Login")
    with st.form("login_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            user_input = st.text_input("Utilizador", autocomplete="username")
        with col2:
            pass_input = st.text_input("Palavra‑passe", type="password", autocomplete="current-password")
        ok = st.form_submit_button("Entrar")
    if ok:
        if do_login(user_input, pass_input):
            st.success("Autenticado com sucesso. A carregar…")
            st.rerun()  # recarrega a app já autenticada
        else:
            st.error("Credenciais inválidas. Tenta novamente.")
    st.stop()  # bloqueia o resto da app para não autenticados
else:
    # Barra de topo com info + botão sair
    topc1, topc2 = st.columns([0.8, 0.2])
    with topc1:
        st.caption(f"✅ Sessão iniciada como **{st.session_state.auth_user}**")
    with topc2:
        if st.button("Terminar sessão", use_container_width=True):
            do_logout()
            st.rerun()

# -------------------------------------------------------------------------
# Título (sem dot/legenda no topo)
# -------------------------------------------------------------------------
with c_title:
    st.markdown("<h1 style='margin-bottom:0;'>Ruturas Dashboard</h1>", unsafe_allow_html=True)

st.write("Carrega um ficheiro CSV")

# -------------------------------------------------------------------------
# Helpers / Constantes
# -------------------------------------------------------------------------
def base_name(colname: str) -> str:
    """Remove sufixos pandas .1, .2 e devolve lowercase trim."""
    return str(colname).strip().split(".", 1)[0].lower()


def normalize_text_pt(s: str) -> str:
    """Remove acentos PT para matching robusto."""
    repl = str.maketrans("áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ", "aaaaeeiooouucAAAAEEIOOOUUC")
    return str(s).translate(repl).strip().lower()


def base_norm(colname: str) -> str:
    return normalize_text_pt(base_name(colname))


# >>> ALTERAÇÃO: Só manter Ruturas + Indisponiveis (IGNORA Indisponíveis 1ª Linha)
METRICS = ["Ruturas", "Indisponiveis"]

# >>> ALTERAÇÃO: apenas as colunas esperadas destas 2 métricas
EXPECTED_BASENORMS = [
    "ruturas vtm", "indisponiveis vtm",
    "ruturas atm", "indisponiveis atm",
]

DISPLAY_FONTE = {
    "GERAL": "Geral",
    "Agências": "Agências",
    "Esegur": "Fornecedores",  # display name pedido
}

# -------------------------------------------------------------------------
# Leitura e normalização segundo o novo layout (Agências + Esegur + Just/Registos)
# -------------------------------------------------------------------------
def read_uploaded_csv_v2(file):
    """
    Novo CSV:
      - Bloco principal começa em "Data"
      - Bloco Justificações começa em "Resposta" (novo) ou "Data" (antigo)
      - Bloco Eventos começa em "Evento" (novo) ou "Data" (antigo)
    header=1 para ler a segunda linha como nomes de coluna.
    """
    # tentar UTF-8 -> fallback Latin-1
    try:
        df = pd.read_csv(file, sep=";", header=1, engine="python")
    except UnicodeDecodeError:
        file.seek(0)
        df = pd.read_csv(file, sep=";", header=1, engine="python", encoding="latin-1")

    df.columns = [str(c).strip() for c in df.columns]
    cols = df.columns.tolist()

    # ---------------------- localizar separadores ----------------------
    bases_norm = [normalize_text_pt(base_name(c)) for c in cols]

    def find_next(pos0, names_set):
        for i in range(pos0 + 1, len(bases_norm)):
            if bases_norm[i] in names_set:
                return i
        return None

    # 1) início do bloco principal (tem de existir)
    try:
        start_main = bases_norm.index("data")
    except ValueError:
        raise ValueError("Estrutura inesperada: não encontrei a 1ª coluna 'Data' (bloco principal).")

    # 2) início do bloco justificações
    start_j = find_next(start_main, {"data", "resposta"})

    # 3) início do bloco eventos
    start_e = None
    if start_j is not None:
        start_e = find_next(start_j, {"data", "evento"})

    # ---------------------- BLOCO PRINCIPAL (Agências + Esegur) ----------------------
    end_main = start_j if start_j is not None else len(cols)
    df_mainblk = df.iloc[:, start_main:end_main].copy()

    # A primeira coluna deve ser 'Data'. Normalizar datas.
    data_col = df_mainblk.columns[0]
    df_mainblk.rename(columns={data_col: "Data"}, inplace=True)
    df_mainblk["Data"] = pd.to_datetime(df_mainblk["Data"], errors="coerce").dt.normalize()
    df_mainblk = df_mainblk.dropna(subset=["Data"]).reset_index(drop=True)

    # Mapear colunas duplicadas: 1ª ocorrência -> Agências; 2ª -> Esegur
    occ_map = {bn: [] for bn in EXPECTED_BASENORMS}
    for c in df_mainblk.columns[1:]:
        bn = base_norm(c)
        if bn in occ_map:
            occ_map[bn].append(c)

    def colmeta_from_basename(bn: str):
        # "ruturas vtm" -> ("VTM","Ruturas")
        parts = bn.split()
        metrica = parts[0].capitalize()  # Ruturas / Indisponiveis
        canal = parts[-1].upper()        # VTM / ATM
        return canal, metrica

    map_agencias = {}
    map_esegur = {}
    for bn, col_list in occ_map.items():
        canal, metrica = colmeta_from_basename(bn)
        if len(col_list) >= 1:
            map_agencias[col_list[0]] = (canal, metrica)
        if len(col_list) >= 2:
            map_esegur[col_list[1]] = (canal, metrica)

    def melt_fonte(df_blk: pd.DataFrame, map_cols: dict, fonte_label: str) -> pd.DataFrame:
        if not map_cols:
            return pd.DataFrame(columns=["Data", "Fonte", "Canal", "Metrica", "Valor"])
        keep = ["Data"] + list(map_cols.keys())
        dfx = df_blk[keep].copy()
        dfl = dfx.melt(id_vars=["Data"], var_name="Col", value_name="Valor")
        dfl["Fonte"] = fonte_label
        dfl[["Canal", "Metrica"]] = dfl["Col"].apply(lambda c: pd.Series(map_cols[c]))
        dfl.drop(columns=["Col"], inplace=True)
        dfl["Valor"] = pd.to_numeric(dfl["Valor"], errors="coerce").fillna(0)
        return dfl[["Data", "Fonte", "Canal", "Metrica", "Valor"]]

    df_ag = melt_fonte(df_mainblk, map_agencias, "Agências")
    df_es = melt_fonte(df_mainblk, map_esegur, "Esegur")

    # Se Esegur não existir no CSV para alguma métrica, criar zeros (mesmas datas/categorias)
    if df_es.empty and not df_ag.empty:
        uniq = df_ag[["Data", "Canal", "Metrica"]].drop_duplicates()
        uniq["Fonte"] = "Esegur"
        uniq["Valor"] = 0
        df_es = uniq[["Data", "Fonte", "Canal", "Metrica", "Valor"]].copy()

    df_daily = pd.concat([df_ag, df_es], ignore_index=True)

    # Garantir que só ficam métricas desejadas
    df_daily = df_daily[df_daily["Metrica"].isin(METRICS)].copy()

    # Adicionar linha "GERAL" (ATM+VTM) por Fonte e Métrica
    df_geral = (
        df_daily.groupby(["Data", "Fonte", "Metrica"], as_index=False)["Valor"].sum()
        .assign(Canal="GERAL")
        .loc[:, ["Data", "Fonte", "Canal", "Metrica", "Valor"]]
    )
    df_daily = pd.concat([df_daily, df_geral], ignore_index=True)

    # ---------------------- BLOCO JUSTIFICAÇÕES (matriz diária) ----------------------
    df_just, just_has_date = None, False
    try:
        if start_j is None:
            raise ValueError("Sem bloco de justificações (não encontrei 'Resposta'/'Data' após o bloco principal).")

        end_j = start_e if start_e is not None else len(cols)
        df_right = df.iloc[:, start_j:end_j].copy()
        df_right.columns = [str(c).strip() for c in df_right.columns]

        # aceitar "Data" OU "Resposta" como coluna de datas
        date_col = None
        for c in df_right.columns:
            b = normalize_text_pt(base_name(c))
            if b in ("data", "resposta"):
                date_col = c
                break

        if date_col:
            df_right.rename(columns={date_col: "Data"}, inplace=True)
            df_right["Data"] = pd.to_datetime(df_right["Data"], errors="coerce").dt.normalize()
            df_right = df_right.dropna(subset=["Data"])
            for c in [c for c in df_right.columns if c != "Data"]:
                df_right[c] = pd.to_numeric(df_right[c], errors="coerce").fillna(0)
            df_just = df_right.copy()
            just_has_date = True
        else:
            for c in df_right.columns:
                df_right[c] = pd.to_numeric(df_right[c], errors="coerce").fillna(0)
            df_just = df_right.copy()
            just_has_date = False
    except Exception:
        df_just, just_has_date = None, False

    # ---------------------- BLOCO EVENTOS DETALHADOS ----------------------
    df_events = None
    if start_e is not None:
        df_events_blk = df.iloc[:, start_e:].copy()

        rename_map = {}
        for c in df_events_blk.columns:
            n = normalize_text_pt(c)
            # aceitar "Data" OU "Evento" como coluna de datas
            if n in ("data", "evento"):
                rename_map[c] = "Data"
            elif n.startswith("hora"):
                rename_map[c] = "Hora_" + c.split()[1] if len(c.split()) > 1 else "Hora"
            elif "duracao" in n:
                rename_map[c] = "Duracao_" + str(len(rename_map))
            elif n in ("agencia/empresa", "agencia/ empresa", "agenciaempresa", "agencia_empresa"):
                rename_map[c] = "AgenciaEmpresa"
            elif n.startswith("maquina"):
                rename_map[c] = "Maquina"
            elif n.startswith("justific"):
                rename_map[c] = "Justificacao"

        dfe = df_events_blk.rename(columns=rename_map)
        keep = [c for c in ["Data", "AgenciaEmpresa", "Maquina", "Justificacao"] if c in dfe.columns]
        if keep:
            dfe = dfe[keep].copy()
            if "Data" in dfe.columns:
                dfe["Data"] = pd.to_datetime(dfe["Data"], errors="coerce").dt.normalize()

            if "AgenciaEmpresa" in dfe.columns:
                dfe["Fonte"] = np.where(
                    dfe["AgenciaEmpresa"].fillna("").str.strip().str.lower() == "esegur",
                    "Esegur",
                    "Agências",
                )
            df_events = dfe.dropna(how="all")
        else:
            df_events = None

    return df_daily, df_just, just_has_date, df_events
# -------------------------------------------------------------------------
# Upload + cache em disco
# -------------------------------------------------------------------------
import os, io, hashlib, pickle
from datetime import datetime

PERSIST_DIR = ".streamlit_cache"
os.makedirs(PERSIST_DIR, exist_ok=True)

STATE_META = os.path.join(PERSIST_DIR, "meta.pkl")
STATE_DAILY = os.path.join(PERSIST_DIR, "daily.pkl")
STATE_JUST = os.path.join(PERSIST_DIR, "just.pkl")
STATE_EVENTS = os.path.join(PERSIST_DIR, "events.pkl")


def save_cache(df_daily, df_just, just_has_date, df_events, file_hash):
    meta = dict(
        saved_at=datetime.utcnow().isoformat() + "Z",
        file_hash=file_hash,
    )
    with open(STATE_META, "wb") as f:
        pickle.dump(meta, f)
    with open(STATE_DAILY, "wb") as f:
        pickle.dump(df_daily, f)
    with open(STATE_JUST, "wb") as f:
        pickle.dump(df_just, f)
    with open(STATE_EVENTS, "wb") as f:
        pickle.dump(df_events, f)


def load_cache():
    if not os.path.exists(STATE_META):
        return None
    try:
        with open(STATE_META, "rb") as f:
            meta = pickle.load(f)
        with open(STATE_DAILY, "rb") as f:
            df_daily = pickle.load(f)
        with open(STATE_JUST, "rb") as f:
            df_just = pickle.load(f)
        with open(STATE_EVENTS, "rb") as f:
            df_events = pickle.load(f)
        return dict(
            meta=meta,
            df_daily=df_daily,
            df_just=df_just,
            df_events=df_events,
        )
    except Exception:
        return None


def hash_bytes(b):
    return hashlib.sha256(b).hexdigest()


@st.cache_data
def parse_csv_cached(raw):
    return read_uploaded_csv_v2(io.BytesIO(raw))


file = st.file_uploader("Carrega o ficheiro CSV", type=["csv"], help="Mantém-se após refresh")

cache = None

if file is not None:
    raw = file.read()
    h = hash_bytes(raw)

    # Se o ficheiro mudou → reprocessar
    try:
        df_daily, df_just, just_has_date, df_events = parse_csv_cached(raw)
        save_cache(df_daily, df_just, just_has_date, df_events, h)
        st.success("Dados carregados.")
    except Exception as e:
        st.error(f"Erro ao ler o CSV: {e}")
        st.stop()

else:
    # Sem upload → tentar cache disco
    cache = load_cache()
    if cache is None:
        st.info("Aguarda upload de ficheiro…")
        st.stop()
    df_daily = cache["df_daily"]
    df_just = cache["df_just"]
    df_events = cache["df_events"]
    st.caption(f"A usar dados guardados em disco ({cache['meta']['saved_at']}).")

# Se chegaste aqui → df_daily está garantido
if df_daily is None or df_daily.empty:
    st.error("Cache ou ficheiro inválido. Carrega novo ficheiro.")
    st.stop()

last_date = df_daily["Data"].max()

# -------------------------------------------------------------------------
# Utilitários de KPIs
# -------------------------------------------------------------------------
def ma7_from_series(s: pd.Series) -> float:
    """Média móvel de 7 (excluindo o dia de referência; já deve ser filtrado)."""
    return float(s.tail(7).mean()) if not s.empty else float("nan")


def today_and_ma7(df_daily: pd.DataFrame, fonte_tab: str, canal: str, metrica: str, ref_date: pd.Timestamp):
    """
    Devolve (valor_hoje, m7) para a combinação pedida.
    fonte_tab: "GERAL" (soma das fontes) | "Agências" | "Esegur"
    canal: "ATM" | "VTM" | "GERAL"
    metrica: "Ruturas" | "Indisponiveis"
    """
    if fonte_tab == "GERAL":
        # soma das fontes
        df_today = df_daily[
            (df_daily["Data"] == ref_date)
            & (df_daily["Canal"] == canal)
            & (df_daily["Metrica"] == metrica)
        ]
        v_hoje = float(df_today.groupby("Data")["Valor"].sum().sum())

        df_hist = df_daily[
            (df_daily["Data"] < ref_date)
            & (df_daily["Canal"] == canal)
            & (df_daily["Metrica"] == metrica)
        ]
        s_hist = df_hist.groupby("Data")["Valor"].sum().sort_index()
        m7 = ma7_from_series(s_hist)
    else:
        df_today = df_daily[
            (df_daily["Data"] == ref_date)
            & (df_daily["Fonte"] == fonte_tab)
            & (df_daily["Canal"] == canal)
            & (df_daily["Metrica"] == metrica)
        ]
        v_hoje = float(df_today["Valor"].sum())

        df_hist = (
            df_daily[
                (df_daily["Data"] < ref_date)
                & (df_daily["Fonte"] == fonte_tab)
                & (df_daily["Canal"] == canal)
                & (df_daily["Metrica"] == metrica)
            ]
            .sort_values("Data")
        )
        m7 = ma7_from_series(df_hist["Valor"])
    return v_hoje, m7


def render_main_kpi(metrica: str, v_geral: float, m7_geral: float):
    """Mostra KPI principal (GERAL) com delta vs M7 (inverse)."""
    delta = None if pd.isna(m7_geral) else f"{'+' if (v_geral - m7_geral) >= 0 else ''}{int(round(v_geral - m7_geral))}"
    st.metric(metrica, int(v_geral), delta=delta, delta_color="inverse" if delta else "off")


# -------------------------------------------------------------------------
# KPIs — Destaque GERAL (soma ATM+VTM) + legenda dentro da secção
# -------------------------------------------------------------------------
h1, h2 = st.columns([0.92, 0.08])

with h1:
    st.header(f"Indicadores — {last_date.date().isoformat()}")

with h2:
    if hasattr(st, "popover"):
        with st.popover("ℹ️", help="Legenda das métricas"):
            st.markdown(LEGEND_MD)
    else:
        with st.expander("ℹ️ Legenda", expanded=False):
            st.markdown(LEGEND_MD)

tab_geral, tab_ag, tab_for = st.tabs([DISPLAY_FONTE["GERAL"], DISPLAY_FONTE["Agências"], DISPLAY_FONTE["Esegur"]])

# Em cada tab: mostrar KPIs da soma (Canal="GERAL") como destaque
for tab, fonte_tab in zip([tab_geral, tab_ag, tab_for], ["GERAL", "Agências", "Esegur"]):
    with tab:
        if fonte_tab == "GERAL":
            sub_today = df_daily[(df_daily["Data"] == last_date) & (df_daily["Canal"] == "GERAL")]
        else:
            sub_today = df_daily[
                (df_daily["Data"] == last_date)
                & (df_daily["Fonte"] == fonte_tab)
                & (df_daily["Canal"] == "GERAL")
            ]
        if sub_today.empty:
            st.info(f"Sem dados para {DISPLAY_FONTE[fonte_tab]} no dia {last_date.date().isoformat()}.")
            continue

        # >>> ALTERAÇÃO: KPIs principais só com 2 métricas
        cols = st.columns(2)
        for metrica, cc in zip(METRICS, cols):
            v_geral, m7_geral = today_and_ma7(df_daily, fonte_tab, "GERAL", metrica, last_date)
            with cc:
                render_main_kpi(metrica, v_geral, m7_geral)

        # Detalhe estético por canal (ATM/VTM) num expander
        with st.expander("Detalhe por canal (ATM / VTM)"):
            c1, c2 = st.columns(2)
            for metrica, cont in zip(METRICS, [c1, c2]):
                v_atm, m7_atm = today_and_ma7(df_daily, fonte_tab, "ATM", metrica, last_date)
                v_vtm, m7_vtm = today_and_ma7(df_daily, fonte_tab, "VTM", metrica, last_date)
                with cont:
                    st.caption(f"**{metrica}**")
                    d_atm = None if pd.isna(m7_atm) else f"{'+' if (v_atm - m7_atm) >= 0 else ''}{int(round(v_atm - m7_atm))}"
                    d_vtm = None if pd.isna(m7_vtm) else f"{'+' if (v_vtm - m7_vtm) >= 0 else ''}{int(round(v_vtm - m7_vtm))}"
                    st.metric("ATM", int(v_atm), delta=d_atm, delta_color="inverse" if d_atm else "off")
                    st.metric("VTM", int(v_vtm), delta=d_vtm, delta_color="inverse" if d_vtm else "off")
        st.markdown("---")

# -------------------------------------------------------------------------
# Evolução diária — escolher Fonte (Geral/Agências/Fornecedores) e Métrica,
# mostrar três linhas: ATM, VTM e GERAL (soma)
# -------------------------------------------------------------------------
st.header("Evolução diária")
fonte_sel_label = st.radio(
    "Fonte",
    [DISPLAY_FONTE["GERAL"], DISPLAY_FONTE["Agências"], DISPLAY_FONTE["Esegur"]],
    horizontal=True,
    index=0,
)

# map back to internal labels
label_to_internal = {v: k for k, v in DISPLAY_FONTE.items()}
fonte_sel = label_to_internal[fonte_sel_label]

# >>> ALTERAÇÃO: selectbox só com 2 métricas
met_sel = st.selectbox("Métrica", METRICS, index=0)

if fonte_sel == "GERAL":
    # Somar fontes para ATM/VTM e manter GERAL (soma final)
    base = df_daily[
        (df_daily["Metrica"] == met_sel) & (df_daily["Canal"].isin(["ATM", "VTM", "GERAL"]))
    ].copy()

    # ATM/VTM: somar por data e canal; GERAL já existe como soma por fonte (vamos somar também por data)
    df_atm_vtm = (
        base[base["Canal"].isin(["ATM", "VTM"])]
        .groupby(["Data", "Canal"], as_index=False)["Valor"]
        .sum()
    )
    df_all = (
        base[base["Canal"] == "GERAL"]
        .groupby(["Data"], as_index=False)["Valor"]
        .sum()
        .assign(Canal="GERAL")
    )
    df_chart = pd.concat([df_atm_vtm, df_all], ignore_index=True)
else:
    df_chart = (
        df_daily[
            (df_daily["Fonte"] == fonte_sel)
            & (df_daily["Metrica"] == met_sel)
            & (df_daily["Canal"].isin(["ATM", "VTM", "GERAL"]))
        ]
        .groupby(["Data", "Canal"], as_index=False)["Valor"]
        .sum()
    )

if df_chart.empty:
    st.info("Sem dados para o filtro escolhido.")
else:
    chart = (
        alt.Chart(df_chart)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("Data:T", title="Data", axis=alt.Axis(format="%Y-%m-%d")),
            y=alt.Y("Valor:Q", title="Valor"),
            color=alt.Color("Canal:N", title=None, scale=alt.Scale(scheme="tableau10")),
            tooltip=[
                alt.Tooltip("Data:T", title="Data", format="%Y-%m-%d"),
                alt.Tooltip("Canal:N", title="Canal"),
                alt.Tooltip("Valor:Q", title=met_sel, format=".0f"),
            ],
        )
        .properties(height=340)
    )
    st.altair_chart(chart, use_container_width=True)

# -------------------------------------------------------------------------
# JUSTIFICAÇÕES — Matriz diária (geral) + Gráfico (Agências) via registos
# -------------------------------------------------------------------------
st.header("Justificações")

# 1) Matriz diária (geral)
if df_just is None or df_just.empty:
    st.info("Sem dados de justificações (matriz diária).")
else:
    sem_col_candidates = [c for c in df_just.columns if normalize_text_pt(c).startswith("sem justific")]
    sem_col = sem_col_candidates[0] if sem_col_candidates else None

    # Top 2 do último dia (exclui 'Sem justificação')
    st.subheader("Top 2 — último dia (geral)")
    if "Data" in df_just.columns:
        last_date_just = df_just["Data"].max()
        df_last = df_just[df_just["Data"] == last_date_just].copy()
        cand_cols = [c for c in df_last.columns if c != "Data" and c != sem_col]
        if df_last.empty or not cand_cols:
            st.info("Sem dados de justificações para o último dia.")
        else:
            s_vals = df_last[cand_cols].iloc[0].astype(float)
            top2 = s_vals.sort_values(ascending=False).head(2)
            colA, colB = st.columns(2)
            with colA:
                st.metric(top2.index[0], int(top2.iloc[0]))
            with colB:
                if len(top2) > 1:
                    st.metric(top2.index[1], int(top2.iloc[1]))
            with st.expander("Ver todas as categorias (último dia)"):
                st.dataframe(
                    s_vals.sort_values(ascending=False)
                    .reset_index()
                    .rename(columns={"index": "Categoria", 0: "Valor"}),
                    use_container_width=True,
                    hide_index=True,
                )

    # Acumulado por período (exclui 'Sem justificação')
    st.subheader("Acumulado por período (geral)")
    periodo = st.selectbox("Período", ["1 semana", "Mês", "Ano", "1-3 Anos"], index=1, key="per_just")
    days_map = {"1 semana": 7, "Mês": 30, "Ano": 365, "1-3 Anos": 365 * 3}
    dias = days_map[periodo]
    if "Data" in df_just.columns:
        end_date = df_just["Data"].max().normalize()
        start_date = end_date - pd.Timedelta(days=dias - 1)
        dfj_win = df_just[(df_just["Data"] >= start_date) & (df_just["Data"] <= end_date)].copy()
        st.caption(f"Período: {start_date.date().isoformat()} a {end_date.date().isoformat()} ({periodo})")
    else:
        dfj_win = df_just.copy()
        st.caption("Período não disponível")

    cols_sum = [c for c in dfj_win.columns if c != "Data" and c != sem_col]
    total_just = dfj_win[cols_sum].sum().sort_values(ascending=False)
    st.bar_chart(total_just)

# 2) Gráfico — Justificações só das Agências (registos detalhados) — remover Esegur e tabelas
st.subheader("Justificações — Agências (registos detalhados)")
if (df_events is None) or df_events.empty or ("Justificacao" not in df_events.columns):
    st.info("Sem registos detalhados para calcular este gráfico.")
else:
    col1, col2 = st.columns(2)
    with col1:
        periodo_ev = st.selectbox("Período", ["Tudo", "1 semana", "Mês", "Ano", "1-3 Anos"], index=2, key="per_ev_ag_only")
    with col2:
        excluir_sem = st.checkbox("Excluir 'Sem justificação'", value=True, key="excluir_sem_ag_only")

    def filtro_periodo(df, periodo_label: str):
        days_map2 = {"1 semana": 7, "Mês": 30, "Ano": 365, "1-3 Anos": 365 * 3, "Tudo": None}
        dias2 = days_map2[periodo_label]
        if (dias2 is None) or ("Data" not in df.columns) or (df["Data"].dropna().empty):
            return df
        end_d = df["Data"].max().normalize()
        start_d = end_d - pd.Timedelta(days=dias2 - 1)
        return df[(df["Data"] >= start_d) & (df["Data"] <= end_d)].copy()

    ev = df_events.copy()
    # Filtrar apenas Agências
    ev = ev[ev["Fonte"] == "Agências"]

    # Aplicar janela temporal
    ev = filtro_periodo(ev, periodo_ev)

    # Correção robusta para "Sem justificação"
    if excluir_sem and "Justificacao" in ev.columns:
        ev = ev[~ev["Justificacao"].fillna("").astype(str).apply(normalize_text_pt).eq("sem justificacao")]

    if ev.empty:
        st.info("Sem registos para os filtros.")
    else:
        top_by_ag = (
            ev.groupby(["Justificacao"], dropna=False)
            .size()
            .rename("Ocorrencias")
            .reset_index()
            .sort_values("Ocorrencias", ascending=False)
            .head(10)
        )
        chart_ag = (
            alt.Chart(top_by_ag)
            .mark_bar(color="#4C78A8")
            .encode(
                x=alt.X("Ocorrencias:Q", title="Ocorrências"),
                y=alt.Y("Justificacao:N", title=None, sort="-x"),
                tooltip=["Justificacao:N", alt.Tooltip("Ocorrencias:Q", title="Ocorrências")],
            )
            .properties(height=280)
        )
        st.altair_chart(chart_ag, use_container_width=True)

# -------------------------------------------------------------------------
# Top 5 piores agências (nº de ocorrências) — exclui Fornecedores (Esegur)
# -------------------------------------------------------------------------
st.header("Top 5 piores agências (nº de ocorrências)")

if (df_events is None) or df_events.empty or ("AgenciaEmpresa" not in df_events.columns):
    st.info("Sem registos detalhados com 'AgenciaEmpresa'.")
else:
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        periodo_top = st.selectbox("Período", ["Tudo", "1 semana", "Mês", "Ano", "1-3 Anos"], index=2, key="periodo_top")
    with col_t2:
        just_opts2 = ["Todas"] + sorted([j for j in df_events["Justificacao"].dropna().unique()]) if "Justificacao" in df_events.columns else ["Todas"]
        just_sel2 = st.selectbox("Justificação", just_opts2, index=0, key="just_top")

    def filtro_periodo_top(df, periodo_label: str):
        days_map = {"1 semana": 7, "Mês": 30, "Ano": 365, "1-3 Anos": 365 * 3, "Tudo": None}
        dias = days_map[periodo_label]
        if dias is None or "Data" not in df.columns or df["Data"].dropna().empty:
            return df
        end_date = df["Data"].max().normalize()
        start_date = end_date - pd.Timedelta(days=dias - 1)
        return df[(df["Data"] >= start_date) & (df["Data"] <= end_date)].copy()

    top_df = df_events.copy()
    # Excluir Fornecedores (Esegur)
    top_df = top_df[top_df["Fonte"] == "Agências"]
    top_df = filtro_periodo_top(top_df, periodo_top)
    if just_sel2 != "Todas" and "Justificacao" in top_df.columns:
        top_df = top_df[top_df["Justificacao"] == just_sel2]

    if top_df.empty:
        st.info("Sem dados para o filtro selecionado.")
    else:
        topN = (
            top_df.dropna(subset=["AgenciaEmpresa"])
            .groupby("AgenciaEmpresa", dropna=False)
            .size()
            .sort_values(ascending=False)
            .head(5)
            .rename("Ocorrencias")
            .reset_index()
        )

        chart_top = (
            alt.Chart(topN)
            .mark_bar(color="#E76F51")
            .encode(
                x=alt.X("Ocorrencias:Q", title="Ocorrências"),
                y=alt.Y("AgenciaEmpresa:N", title="Agência", sort="-x"),
                tooltip=["AgenciaEmpresa:N", alt.Tooltip("Ocorrencias:Q", title="Ocorrências")],
            )
            .properties(height=240)
        )
        labels = (
            alt.Chart(topN)
            .mark_text(align="left", dx=4, color="#333")
            .encode(x="Ocorrencias:Q", y=alt.Y("AgenciaEmpresa:N", sort="-x"), text="Ocorrencias:Q")
        )
        st.altair_chart((chart_top + labels), use_container_width=True)
        with st.expander("Ver tabela"):
            st.dataframe(topN, use_container_width=True, hide_index=True)

# -------------------------------------------------------------------------
# Recomendações (bullet points) — só para 2 métricas
# -------------------------------------------------------------------------
st.header("Recomendações acionáveis")


def _series_agg(df, canal, metrica, fonte=None):
    """Devolve série diária agregada para (fonte opcional) x canal x métrica."""
    base = df[(df["Canal"] == canal) & (df["Metrica"] == metrica)].copy()
    if fonte and fonte != "GERAL":
        base = base[base["Fonte"] == fonte]

    # Agregar por dia (soma de fontes quando 'GERAL')
    s = base.groupby("Data")["Valor"].sum().sort_index()
    return s


def _wow_value(s: pd.Series, ref_date: pd.Timestamp):
    """Valor exatamente 7 dias antes, se existir."""
    prev = ref_date - pd.Timedelta(days=7)
    return float(s.get(prev, np.nan))


def _zscore(s: pd.Series, ref_date: pd.Timestamp, window=28):
    """Z‑Score do último dia vs média/DP dos últimos 'window' dias (excluindo hoje)."""
    if s.empty or ref_date not in s.index:
        return np.nan
    shist = s[s.index < ref_date].tail(window)
    if len(shist) < max(7, window // 2):
        return np.nan
    mu, sd = float(shist.mean()), float(shist.std(ddof=0))
    if sd == 0:
        return np.nan
    return (float(s.loc[ref_date]) - mu) / sd


def _slope7(s: pd.Series, ref_date: pd.Timestamp):
    """Inclinação (diferença média diária) últimos 7 dias anteriores a ref_date."""
    shist = s[(s.index < ref_date)].tail(7)
    if len(shist) < 3:
        return np.nan
    x = np.arange(len(shist))
    y = shist.values.astype(float)
    xbar, ybar = x.mean(), y.mean()
    num = ((x - xbar) * (y - ybar)).sum()
    den = ((x - xbar) ** 2).sum()
    if den == 0:
        return np.nan
    slope = num / den
    return float(slope)


def _fmt_delta(abs_delta, pct_delta):
    sign = "+" if abs_delta >= 0 else ""
    if np.isnan(pct_delta):
        return f"{sign}{int(round(abs_delta))}"
    return f"{sign}{int(round(abs_delta))} ({sign}{int(round(pct_delta))}%)"


def _severity(today, m7, z):
    """Classifica severidade (🔴/🟠/🟡/🟢) com base em Z e desvios vs MA7."""
    if any(pd.isna(x) for x in [today, m7]):
        return "🟡"
    if (not pd.isna(z)) and (z >= 2.0):
        return "🔴"
    if today >= m7 * 1.25 and (today - m7) >= 5:
        return "🔴"
    if today >= m7 * 1.10 and (today - m7) >= 3:
        return "🟠"
    if today < m7 * 0.90:
        return "🟢"
    return "🟡"


def _norm_pt(s: str) -> str:
    return normalize_text_pt(s)


def _playbook_para_justificacao(just_txt: str):
    """
    Traduz justificações em ações concretas (regras por palavras‑chave PT normalizadas).
    """
    j = _norm_pt(str(just_txt))
    actions = []
    if any(k in j for k in ["numerar", "numerario", "dinheiro", "cash"]):
        actions += ["reforçar abastecimentos (ajustar frequência Esegur)", "calibrar níveis alvo por agência (perfil de procura)"]
    if any(k in j for k in ["consumiv", "papel", "rolo", "toner"]):
        actions += ["enviar kit consumíveis para agências top‑ocorrência", "checklist diária de stock na abertura"]
    if any(k in j for k in ["comunic", "rede", "ligacao", "vpn", "router", "lan", "wan"]):
        actions += ["abrir ticket com IT para verificação link/latência", "failover 4G temporário onde disponível"]
    if any(k in j for k in ["manuten", "prevent", "tecnico", "hardware", "lec", "leitor", "dispens"]):
        actions += ["agendar manutenção preventiva", "prioridade SLA 4h nos equipamentos reincidentes"]
    if any(k in j for k in ["software", "versao", "update", "patch"]):
        actions += ["validar versão/patch e janela de atualização", "rollback/patch hotfix se aplicável"]
    if any(k in j for k in ["energia", "eletric", "eletricidade", "ups"]):
        actions += ["verificar UPS e estabilidade de energia", "coordenação local para horários críticos"]
    if any(k in j for k in ["sem justific", "nao identific"]):
        actions += ["sanear registos: reforçar preenchimento de causa", "auditar 10 amostras para descobrir causa real"]
    if not actions:
        actions = ["diagnóstico local com checklist padrão", "validar logs e fotos do incidente"]

    seen, dedup = set(), []
    for a in actions:
        if a not in seen:
            seen.add(a)
            dedup.append(a)
    return dedup


def _top_agencias_e_playbook(df_events, end_date, days=30, max_ag=5):
    """Top agências por ocorrências (últimos N dias) + ações por justificações dominantes."""
    out = []
    if (df_events is None) or df_events.empty or ("AgenciaEmpresa" not in df_events.columns):
        return out
    ev = df_events.copy()
    if "Data" in ev.columns and not ev["Data"].dropna().empty:
        start = end_date - pd.Timedelta(days=days - 1)
        ev = ev[(ev["Data"] >= start) & (ev["Data"] <= end_date)]
    ev = ev[ev["Fonte"] == "Agências"]
    if ev.empty:
        return out
    by_ag = ev.dropna(subset=["AgenciaEmpresa"]).groupby("AgenciaEmpresa").size().rename("Ocorrencias").sort_values(ascending=False)
    total = int(by_ag.sum()) if len(by_ag) else 0
    by_ag = by_ag.head(max_ag)
    for ag, n in by_ag.items():
        share = 0 if total == 0 else int(round(100 * n / total))
        topj = []
        if "Justificacao" in ev.columns:
            topj = (
                ev[ev["AgenciaEmpresa"] == ag]
                .groupby("Justificacao", dropna=False)
                .size()
                .sort_values(ascending=False)
                .head(2)
                .index.tolist()
            )
        actions = []
        for j in topj:
            actions.extend(_playbook_para_justificacao(j))
        out.append({"agencia": ag, "ocorr": int(n), "share": share, "justs": topj, "acoes": actions[:3]})
    return out


try:
    if df_daily.empty:
        st.info("Sem dados para gerar recomendações.")
        st.stop()

    ref = last_date

    # 1) Painel de Risco por Fonte x Métrica (GERAL = soma ATM+VTM)
    blocos = []
    for fonte in ["GERAL", "Agências", "Esegur"]:
        for metrica in METRICS:
            s_geral = _series_agg(df_daily, "GERAL", metrica, fonte=(None if fonte == "GERAL" else fonte))
            today = float(s_geral.get(ref, np.nan))
            m7 = float(s_geral[s_geral.index < ref].tail(7).mean()) if not s_geral.empty else np.nan
            prev7 = _wow_value(s_geral, ref)
            z = _zscore(s_geral, ref, window=28)
            slope = _slope7(s_geral, ref)
            abs_d = np.nan if pd.isna(m7) else (today - m7)
            pct_d = np.nan if pd.isna(m7) or m7 == 0 else (today / m7 - 1) * 100
            sev = _severity(today, m7, z)
            blocos.append(
                {
                    "fonte": fonte,
                    "metrica": metrica,
                    "today": today,
                    "m7": m7,
                    "wow": prev7,
                    "z": z,
                    "slope7": slope,
                    "abs_d": abs_d,
                    "pct_d": pct_d,
                    "sev": sev,
                }
            )

    # 2) Contribuição por Canal no dia de referência
    contrib = []
    for fonte in ["GERAL", "Agências", "Esegur"]:
        for metrica in METRICS:
            for canal in ["ATM", "VTM"]:
                s = _series_agg(df_daily, canal, metrica, fonte=(None if fonte == "GERAL" else fonte))
                val = float(s.get(ref, 0.0))
                contrib.append({"fonte": fonte, "metrica": metrica, "canal": canal, "valor": val})
    contrib_df = pd.DataFrame(contrib)

    top_contrib = {}
    if not contrib_df.empty:
        for (f, m), sub in contrib_df.groupby(["fonte", "metrica"]):
            sub = sub.sort_values("valor", ascending=False)
            if not sub.empty:
                top_contrib[(f, m)] = (sub.iloc[0]["canal"], float(sub.iloc[0]["valor"]))

    # 3) Top agências e playbooks (últimos 30 dias, só Agências)
    top_ag_play = _top_agencias_e_playbook(df_events, end_date=ref, days=30, max_ag=5)

    # ---------------------------
    # Render — Decisões imediatas
    # ---------------------------
    st.subheader("Decisões imediatas (24–48h)")
    bullets = []
    for b in blocos:
        if b["sev"] == "🔴":
            canal_dom, val_dom = top_contrib.get((b["fonte"], b["metrica"]), ("—", 0))
            wow = b["wow"]
            wow_txt = "n/d" if pd.isna(wow) else f"{int(wow)}"
            delta_txt = _fmt_delta(b["abs_d"], b["pct_d"])
            bullets.append(
                f"{b['sev']} **{DISPLAY_FONTE.get(b['fonte'], b['fonte'])} — {b['metrica']}** "
                f"no topo: **{int(b['today'])}** vs M7 **{int(round(b['m7']))}** ({delta_txt}), Z={b['z']:.2f}, WoW={wow_txt}. "
                f"**Atacar {canal_dom}** (contribui {int(val_dom)} hoje)."
            )
    if bullets:
        st.markdown("\n".join(f"- {x}" for x in bullets))
    else:
        st.info("Sem alertas 🔴. Mesmo assim, verifique as ações da semana para mitigação preventiva.")

    # ---------------------------
    # Render — Ações da semana
    # ---------------------------
    st.subheader("Ações da semana")
    bullets = []

    if (df_events is not None) and ("Justificacao" in (df_events.columns if df_events is not None else [])):
        ev_ag = df_events.copy()
        if "Data" in ev_ag.columns and not ev_ag["Data"].dropna().empty:
            win_start = ref - pd.Timedelta(days=30)
            ev_ag = ev_ag[(ev_ag["Data"] >= win_start) & (ev_ag["Data"] <= ref)]
        ev_ag = ev_ag[ev_ag["Fonte"] == "Agências"]
        topj = []
        if not ev_ag.empty:
            topj = ev_ag.groupby("Justificacao", dropna=False).size().sort_values(ascending=False).head(3).index.tolist()

        for j in topj:
            acts = _playbook_para_justificacao(j)[:3]
            if acts:
                bullets.append(f"🟠 **Justificação dominante** _{j}_ → " + "; ".join(acts))

    if top_ag_play:
        for item in top_ag_play[:3]:
            jtxt = ", ".join([f"_{j}_" for j in item["justs"]]) if item["justs"] else "sem justificação dominante"
            bullets.append(
                f"🟠 **Roteirizar visita** à agência **{item['agencia']}** "
                f"({item['ocorr']} ocorrências; {item['share']}% das top) — causas: {jtxt}. "
                f"Ações: {', '.join(item['acoes'])}."
            )

    flag_esegur = any(b["fonte"] == "Esegur" and b["sev"] in ["🔴", "🟠"] for b in blocos)
    if flag_esegur:
        doms = [(b["metrica"],) + top_contrib.get(("Esegur", b["metrica"]), ("—", 0)) for b in blocos if b["fonte"] == "Esegur"]
        doms = sorted(doms, key=lambda x: x[2], reverse=True)
        if doms:
            m, c, v = doms[0]
            bullets.append(
                f"🟠 **Esegur**: renegociar/ajustar **frequência e janelas** no canal **{c}** (maior contribuição em {m}, {int(v)} hoje). "
                "Implementar teste A/B em 3 locais com aumento de frequência por 2 semanas."
            )

    if bullets:
        st.markdown("\n".join(f"- {x}" for x in bullets))
    else:
        st.info("Sem ações semanais específicas derivadas dos dados do último mês.")

    # ---------------------------
    # Render — Prevenção (30 dias)
    # ---------------------------
    st.subheader("Prevenção (30 dias)")
    bullets = []

    trend_warnings = [b for b in blocos if (not pd.isna(b["slope7"])) and (b["slope7"] > 0.5) and (b["sev"] in ["🟡", "🟠"])]
    for tw in trend_warnings[:4]:
        bullets.append(
            f"🟡 **Tendência de subida** em {DISPLAY_FONTE.get(tw['fonte'], tw['fonte'])} — {tw['metrica']}: "
            f"+{tw['slope7']:.1f}/dia (últimos 7 dias). "
            "Agendar auditoria de processos e revisão de SLAs antes de virar 🔴."
        )

    if df_just is not None and not df_just.empty:
        sem_cols = [c for c in df_just.columns if _norm_pt(c).startswith("sem justific")]
        if sem_cols:
            if "Data" in df_just.columns:
                end_d = df_just["Data"].max().normalize()
                start_d = end_d - pd.Timedelta(days=29)
                win = df_just[(df_just["Data"] >= start_d) & (df_just["Data"] <= end_d)]
            else:
                win = df_just.copy()

            sem_total = float(win[sem_cols[0]].sum()) if sem_cols[0] in win.columns else 0.0
            all_cols = [c for c in win.columns if c != "Data"]
            base_total = float(win[all_cols].sum().sum()) if all_cols else 0.0
            if base_total > 0 and sem_total / base_total >= 0.10:
                pct = int(round(100 * sem_total / base_total))
                bullets.append(
                    f"🟡 **Qualidade de dados**: 'Sem justificação' = {pct}% dos registos (30 dias). "
                    "Treinar preenchimento de causa e tornar campo obrigatório para fechar ticket."
                )

    if top_ag_play:
        total_top = sum(a["ocorr"] for a in top_ag_play)
        ev_ag_all = df_events[(df_events["Fonte"] == "Agências")] if (df_events is not None) and ("Fonte" in df_events.columns) else None
        if ev_ag_all is not None and not ev_ag_all.empty:
            if "Data" in ev_ag_all.columns and not ev_ag_all["Data"].dropna().empty:
                start = ref - pd.Timedelta(days=30)
                ev_ag_all = ev_ag_all[(ev_ag_all["Data"] >= start) & (ev_ag_all["Data"] <= ref)]
            total_all = int(ev_ag_all.shape[0])
            if total_all > 0:
                share_top = int(round(100 * total_top / total_all))
                if share_top >= 40:
                    bullets.append(
                        f"🟡 **Ataque Pareto**: Top 5 agências concentram {share_top}% das ocorrências (30 dias). "
                        "Implementar *war‑room* quinzenal até queda de 30%."
                    )

    if bullets:
        st.markdown("\n".join(f"- {x}" for x in bullets))
    else:
        st.caption("Sem alertas de prevenção no horizonte de 30 dias.")

    # ---------------------------
    # Extra — Tabela de Prioridades (score de risco)
    # ---------------------------
    with st.expander("Tabela de prioridades (score de risco)"):
        pri = []
        for b in blocos:
            score = 0
            if not pd.isna(b["z"]):
                score += min(3, max(0, int(b["z"])))
            if not pd.isna(b["pct_d"]):
                score += (2 if b["pct_d"] >= 25 else 1 if b["pct_d"] >= 10 else 0)
            if not pd.isna(b["slope7"]) and b["slope7"] > 0.5:
                score += 1
            sev_rank = {"🔴": 3, "🟠": 2, "🟡": 1, "🟢": 0}.get(b["sev"], 1)
            score += sev_rank

            pri.append(
                {
                    "Fonte": DISPLAY_FONTE.get(b["fonte"], b["fonte"]),
                    "Métrica": b["metrica"],
                    "Hoje": int(b["today"]) if not pd.isna(b["today"]) else None,
                    "M7": int(round(b["m7"])) if not pd.isna(b["m7"]) else None,
                    "Δ vs M7": int(round(b["abs_d"])) if not pd.isna(b["abs_d"]) else None,
                    "% vs M7": f"{int(round(b['pct_d']))}%" if not pd.isna(b["pct_d"]) else None,
                    "Z(28d)": f"{b['z']:.2f}" if not pd.isna(b["z"]) else "n/d",
                    "Slope7": f"{b['slope7']:.1f}" if not pd.isna(b["slope7"]) else "n/d",
                    "Severidade": b["sev"],
                    "Score": score,
                }
            )
        if pri:
            st.dataframe(pd.DataFrame(pri).sort_values("Score", ascending=False), use_container_width=True, hide_index=True)

except Exception as e:
    st.info(f"Não foi possível gerar recomendações avançadas ({e}).")

# -------------------------------------------------------------------------
# Downloads
# -------------------------------------------------------------------------
st.header("Download dos dados")

# Tabela diária normalizada (Fonte x Canal x Métrica) — já vem sem Indisponíveis 1ª Linha
csv_daily = (
    df_daily.sort_values(["Data", "Fonte", "Canal", "Metrica"])
    .to_csv(index=False, sep=";")
    .encode("utf-8-sig")
)
st.download_button(
    "Baixar CSV (diário — Fonte/Canal/Métrica)",
    csv_daily,
    file_name="ruturas_diario_fonte_canal.csv",
    mime="text/csv",
)

# Justificações (matriz diária)
if (df_just is not None) and (not df_just.empty):
    csv_just = df_just.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Baixar CSV (justificações — matriz)",
        csv_just,
        file_name="ruturas_justificacoes_matriz.csv",
        mime="text/csv",
    )

# Registos detalhados normalizados
if (df_events is not None) and (not df_events.empty):
    csv_ev = df_events.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Baixar CSV (registos detalhados)",
        csv_ev,
        file_name="ruturas_registos_detalhados.csv",
        mime="text/csv",
    )
