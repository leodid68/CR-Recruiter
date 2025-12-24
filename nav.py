import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Titre de l'application
st.title("📈 Analyse Financière avec Yahoo Finance")
st.write("Récupération et analyse de données boursières en temps réel.")

# Sélection de l'actif
ticker = st.text_input("Entrez le symbole boursier (ex: AAPL, MSFT, BTC-USD)", "AAPL")
period = st.selectbox("Période", ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"])

# Récupération des données
@st.cache_data
def get_data(ticker, period):
    data = yf.download(ticker, period=period, progress=False)
    return data

data = get_data(ticker, period)

# Affichage des données brutes
st.write("### Données brutes")
st.write(data.tail())

# Graphique du cours (corrigé)
st.write("### Graphique du cours")
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=data.index,
    open=data['Open'],
    high=data['High'],
    low=data['Low'],
    close=data['Close'],
    name='Cours'
))
fig.update_layout(
    title=f"Cours de {ticker}",
    yaxis_title="Prix (USD)",
    xaxis_rangeslider_visible=True,  # Ajout du zoom
    template="plotly_dark",  # Thème sombre pour plus de lisibilité
    height=600  # Hauteur fixe pour éviter les problèmes de mise en page
)
st.plotly_chart(fig, use_container_width=True)

# Indicateurs techniques (corrigés)
st.write("### Indicateurs Techniques")
tab1, tab2, tab3 = st.tabs(["RSI", "MACD", "Bollinger Bands"])

# RSI (corrigé)
with tab1:
    rsi_period = st.slider("Période RSI", 5, 30, 14)
    delta = data['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(rsi_period).mean()
    avg_loss = loss.rolling(rsi_period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    fig_rsi = go.Figure()
    fig_rsi.add_trace(go.Scatter(x=data.index, y=rsi, name="RSI", line=dict(color='blue')))
    fig_rsi.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Surachat")
    fig_rsi.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Survente")
    fig_rsi.update_layout(
        title=f"RSI ({rsi_period} périodes)",
        yaxis_title="RSI",
        template="plotly_dark",
        height=400
    )
    st.plotly_chart(fig_rsi, use_container_width=True)

# MACD (corrigé)
with tab2:
    fast_period = st.slider("Période rapide (MACD)", 5, 30, 12)
    slow_period = st.slider("Période lente (MACD)", 10, 50, 26)
    signal_period = st.slider("Période signal (MACD)", 5, 30, 9)
    exp1 = data['Close'].ewm(span=fast_period, adjust=False).mean()
    exp2 = data['Close'].ewm(span=slow_period, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    fig_macd = go.Figure()
    fig_macd.add_trace(go.Scatter(x=data.index, y=macd, name="MACD", line=dict(color='blue')))
    fig_macd.add_trace(go.Scatter(x=data.index, y=signal, name="Signal", line=dict(color='red')))
    fig_macd.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Niveau zéro")
    fig_macd.update_layout(
        title=f"MACD ({fast_period}, {slow_period}, {signal_period})",
        yaxis_title="MACD",
        template="plotly_dark",
        height=400
    )
    st.plotly_chart(fig_macd, use_container_width=True)

# Bollinger Bands (corrigé)
with tab3:
    bb_period = st.slider("Période Bollinger Bands", 5, 50, 20)
    std_dev = st.slider("Écart-type", 1, 3, 2)
    sma = data['Close'].rolling(bb_period).mean()
    std = data['Close'].rolling(bb_period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    fig_bb = go.Figure()
    fig_bb.add_trace(go.Scatter(x=data.index, y=data['Close'], name="Cours", line=dict(color='white')))
    fig_bb.add_trace(go.Scatter(x=data.index, y=upper_band, name="Bande supérieure", line=dict(color='red', dash='dash')))
    fig_bb.add_trace(go.Scatter(x=data.index, y=lower_band, name="Bande inférieure", line=dict(color='green', dash='dash')))
    fig_bb.add_trace(go.Scatter(x=data.index, y=sma, name="Moyenne mobile", line=dict(color='yellow')))
    fig_bb.update_layout(
        title=f"Bollinger Bands ({bb_period}, {std_dev}σ)",
        yaxis_title="Prix (USD)",
        template="plotly_dark",
        height=400
    )
    st.plotly_chart(fig_bb, use_container_width=True)

# Informations supplémentaires
st.write("### Informations sur l'actif")
info = yf.Ticker(ticker).info
st.write(f"**Nom :** {info.get('longName', 'N/A')}")
st.write(f"**Secteur :** {info.get('sector', 'N/A')}")
st.write(f"**Pays :** {info.get('country', 'N/A')}")
st.write(f"**Capitalisation :** {info.get('marketCap', 'N/A'):,.2f} USD")