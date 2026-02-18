import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
import pytz

# Configuración de página para móvil
st.set_page_config(page_title="SPY 0DTE Maestro", page_icon="📈")

def get_delta_strike(price, iv, delta, option_type='call'):
    t = 0.7 / 365 
    sigma = iv / 100
    z = norm.ppf(delta if option_type == 'call' else 1 - abs(delta))
    return price * np.exp(z * sigma * np.sqrt(t)) if option_type == 'call' else price * np.exp(-z * sigma * np.sqrt(t))

st.title("🚀 SPY 0DTE Maestro")

# Entrada de Saldo en la barra lateral o principal
saldo = st.number_input("Introduce tu saldo actual (€):", value=28630.0, step=100.0)

if st.button('Ejecutar Análisis 16:15'):
    tz_ny = pytz.timezone('America/New_York')
    tz_es = pytz.timezone('Europe/Madrid')
    now_ny = datetime.now(tz_ny)
    now_es = datetime.now(tz_es)
    
    st.write(f"📍 **España:** {now_es.strftime('%H:%M')} | 🗽 **NY:** {now_ny.strftime('%H:%M')}")
    
    tickers = ["SPY", "^VIX1D", "^VIX", "^VVIX", "^SKEW", "^TRIN"]
    
    with st.spinner('Descargando datos de mercado...'):
        try:
            data = yf.download(tickers, period="2d", interval="1m", progress=False)
            
            lp = float(data['Close']['SPY'].dropna().iloc[-1])   
            op = float(data['Open']['SPY'].dropna().iloc[0]) 
            vix1d = float(data['Close']['^VIX1D'].dropna().iloc[-1])
            vix = float(data['Close']['^VIX'].dropna().iloc[-1])
            vvix = float(data['Close']['^VVIX'].dropna().iloc[-1])
            skew = float(data['Close']['^SKEW'].dropna().iloc[-1])
            
            try:
                trin = float(data['Close']['^TRIN'].dropna().iloc[-1])
            except:
                trin = 1.0

            vix_ratio = vix1d / vix
            risk_score = 0
            if vix_ratio > 1.10: risk_score += 40
            if vvix > 115: risk_score += 30
            if skew > 145: risk_score += 15
            if abs(lp - op) / op > 0.008: risk_score += 15 

            bias = "NEUTRAL"
            if lp > op * 1.004 and trin < 0.85: bias = "ALCISTA"
            elif lp < op * 0.996 and trin > 1.15: bias = "BAJISTA"

            # Lógica de Estrategia
            wing_width = 5 if vix1d > 18 else 2
            target_profit = saldo * 0.005
            riesgo_max = saldo * 0.02
            num_contratos = int(riesgo_max / (wing_width * 100))

            # Definición de Combo
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
                s_ref = round(min(lp*0.99, get_delta_strike(lp,vix1d,-0.10,'put'))) if bias == 'ALCISTA' else round(max(lp*1.01, get_delta_strike(lp,vix1d,0.10,'call')))
                s_c, s_p = (0, s_ref) if bias == "ALCISTA" else (s_ref, 0)
            else:
                combo = "IRON CONDOR NEUTRAL"
                s_c = round(max(lp * 1.01, get_delta_strike(lp, vix1d, 0.10, 'call')))
                s_p = round(min(lp * 0.99, get_delta_strike(lp, vix1d, -0.10, 'put')))

            # Visualización en la App
            st.metric("PRECIO SPY", f"{lp:.2f}", f"{((lp-op)/op)*100:.2f}%")
            
            col1, col2 = st.columns(2)
            col1.metric("Risk Score", f"{risk_score}/100")
            col2.metric("Bias", bias)

            st.subheader(f"🎯 Estrategia: {combo}")
            
            if s_c != 0 or s_p != 0:
                st.info(f"**Lotes sugeridos:** {max(1, num_contratos)} | **Objetivo:** +{target_profit:.2f}€")
                if "DEBIT" in combo:
                    st.write(f"✅ **Compra:** {s_c if s_c!=0 else s_p} | **Venta:** {round(s_c+2 if bias=='ALCISTA' else s_p-2)}")
                else:
                    if s_c != 0: st.success(f"CALL: Sell {s_c} / Buy {s_c + wing_width}")
                    if s_p != 0: st.success(f"PUT: Sell {s_p} / Buy {s_p - wing_width}")
            else:
                st.error("Día de alto riesgo. Mejor no operar.")

        except Exception as e:
            st.error(f"Error: {e}. El mercado podría estar cerrado.")

