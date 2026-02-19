import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
import pytz

# Configuración de página
st.set_page_config(page_title="SPY 0DTE Maestro", page_icon="📈")

def get_delta_strike(price, iv, delta, option_type='call'):
    t = 0.7 / 365 
    sigma = iv / 100
    z = norm.ppf(delta if option_type == 'call' else 1 - abs(delta))
    # Evitar errores si sigma es 0 o nan
    if np.isnan(sigma) or sigma == 0: sigma = 0.15 
    return price * np.exp(z * sigma * np.sqrt(t)) if option_type == 'call' else price * np.exp(-z * sigma * np.sqrt(t))

st.title("🚀 SPY 0DTE Maestro")

saldo = st.number_input("Introduce tu saldo actual (€):", value=28630.0, step=100.0)

if st.button('Ejecutar Análisis'):
    tz_ny = pytz.timezone('America/New_York')
    tz_es = pytz.timezone('Europe/Madrid')
    now_ny = datetime.now(tz_ny)
    now_es = datetime.now(tz_es)
    
    st.write(f"📍 **España:** {now_es.strftime('%H:%M')} | 🗽 **NY:** {now_ny.strftime('%H:%M')}")
    
    tickers = ["SPY", "^VIX1D", "^VIX", "^VVIX", "^SKEW", "^TRIN"]
    
    with st.spinner('Descargando datos de mercado...'):
        try:
            # Descargamos los datos
            data = yf.download(tickers, period="2d", interval="1m", progress=False)
            
            if data.empty:
                st.error("No se recibieron datos de Yahoo Finance.")
                st.stop()

            # --- CORRECCIÓN DE ACCESO A DATOS ---
            # Usamos loc y flatten para evitar errores de MultiIndex
            close_prices = data['Close']
            
            def get_last_valid(ticker):
                series = close_prices[ticker].dropna()
                if series.empty: return 0.0
                return float(series.iloc[-1])

            lp = get_last_valid('SPY')
            # Para el Open, buscamos el primer dato disponible del día actual
            op = float(close_prices['SPY'].dropna().iloc[0]) 
            
            vix1d = get_last_valid('^VIX1D')
            vix = get_last_valid('^VIX')
            vvix = get_last_valid('^VVIX')
            skew = get_last_valid('^SKEW')
            trin = get_last_valid('^TRIN') or 1.0

            # Validar que tengamos datos mínimos para operar
            if lp == 0 or vix == 0:
                st.error("Faltan datos críticos (SPY o VIX).")
                st.stop()

            # Lógica de Riesgo
            vix_ratio = vix1d / vix if vix != 0 else 1
            risk_score = 0
            if vix_ratio > 1.10: risk_score += 40
            if vvix > 115: risk_score += 30
            if skew > 145: risk_score += 15
            if abs(lp - op) / op > 0.008: risk_score += 15 

            bias = "NEUTRAL"
            if lp > op * 1.004 and trin < 0.85: bias = "ALCISTA"
            elif lp < op * 0.996 and trin > 1.15: bias = "BAJISTA"

            # Estrategia
            wing_width = 5 if vix1d > 18 else 2
            target_profit = saldo * 0.005
            riesgo_max = saldo * 0.02
            num_contratos = int(riesgo_max / (wing_width * 100))

            if risk_score >= 75 and bias != "NEUTRAL":
                combo = f"VERTICAL DEBIT SPREAD ({bias})"
                s_long = get_delta_strike(lp, vix1d, 0.70, 'call' if bias == 'ALCISTA' else 'put')
                s_short = get_delta_strike(lp, vix1d, 0.50, 'call' if bias == 'ALCISTA' else 'put')
                s_c, s_p = round(s_long), round(s_short)
            elif risk_score >= 75:
                combo = "🚫 NO OPERAR"
                s_c, s_p = 0, 0
            elif bias != "NEUTRAL":
                combo = f"VERTICAL CREDIT SPREAD ({bias})"
                if bias == 'ALCISTA':
                    s_ref = round(min(lp*0.99, get_delta_strike(lp, vix1d, 0.10, 'put')))
                    s_c, s_p = 0, s_ref
                else:
                    s_ref = round(max(lp*1.01, get_delta_strike(lp, vix1d, 0.10, 'call')))
                    s_c, s_p = s_ref, 0
            else:
                combo = "IRON CONDOR NEUTRAL"
                s_c = round(max(lp * 1.01, get_delta_strike(lp, vix1d, 0.10, 'call')))
                s_p = round(min(lp * 0.99, get_delta_strike(lp, vix1d, 0.10, 'put')))

            # Visualización
            st.metric("PRECIO SPY", f"{lp:.2f}", f"{((lp-op)/op)*100:.2f}%")
            
            col1, col2 = st.columns(2)
            col1.metric("Risk Score", f"{risk_score}/100")
            col2.metric("Bias", bias)

            st.subheader(f"🎯 Estrategia: {combo}")
            
            if combo != "🚫 NO OPERAR":
                st.info(f"**Lotes sugeridos:** {max(1, num_contratos)} | **Objetivo:** +{target_profit:.2f}€")
                if "DEBIT" in combo:
                    # Corrección de visualización para Debit Spreads
                    venta = s_c + 2 if bias == 'ALCISTA' else s_c - 2
                    st.write(f"✅ **Compra (Long):** {s_c} | **Venta (Short):** {venta}")
                else:
                    if s_c != 0: st.success(f"CALL SPREAD: Sell {s_c} / Buy {s_c + wing_width}")
                    if s_p != 0: st.success(f"PUT SPREAD: Sell {s_p} / Buy {s_p - wing_width}")
            else:
                st.error("Día de alto riesgo o condiciones extremas. Mejor no operar.")

        except Exception as e:
            st.error(f"Error de ejecución: {e}")
            st.info("Nota: Yahoo Finance puede fallar si el mercado está cerrado o no hay liquidez en los índices de volatilidad.")
