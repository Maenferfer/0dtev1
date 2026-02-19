import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
import pytz
import requests

# Configuración de página para móvil
st.set_page_config(page_title="SPY 0DTE Maestro", page_icon="📈")

def get_delta_strike(price, iv, delta, option_type='call'):
    """Calcula el strike aproximado basado en el delta deseado."""
    t = 0.7 / 365 
    sigma = iv / 100
    if sigma <= 0 or np.isnan(sigma): sigma = 0.15 # Valor por defecto si falla la IV
    
    z = norm.ppf(delta if option_type == 'call' else 1 - abs(delta))
    if option_type == 'call':
        return price * np.exp(z * sigma * np.sqrt(t))
    else:
        return price * np.exp(-z * sigma * np.sqrt(t))

st.title("🚀 SPY 0DTE Maestro")

# Entrada de Saldo
saldo = st.number_input("Introduce tu saldo actual (€):", value=28630.0, step=100.0)

if st.button('Ejecutar Análisis 2026'):
    tz_ny = pytz.timezone('America/New_York')
    tz_es = pytz.timezone('Europe/Madrid')
    now_ny = datetime.now(tz_ny)
    now_es = datetime.now(tz_es)
    
    st.write(f"📍 **España:** {now_es.strftime('%H:%M')} | 🗽 **NY:** {now_ny.strftime('%H:%M')}")
    
    tickers = ["SPY", "^VIX1D", "^VIX", "^VVIX", "^SKEW", "^TRIN"]
    
    with st.spinner('Conectando con Yahoo Finance...'):
        try:
            # SOLUCIÓN AL BLOQUEO: Sesión con User-Agent de navegador real
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            })

            data = yf.download(
                tickers=tickers, 
                period="2d", 
                interval="1m", 
                progress=False,
                session=session
            )
            
            if data.empty:
                st.error("No se recibieron datos. Es posible que el mercado esté cerrado o la API esté limitada.")
                st.stop()

            # Extraer precios de cierre (Close) manejando el MultiIndex de columnas
            # Usamos .xs para obtener una columna limpia para cada ticker
            df_close = data['Close']

            def get_last(ticker):
                val = df_close[ticker].dropna()
                return float(val.iloc[-1]) if not val.empty else None

            lp = get_last('SPY')
            vix1d = get_last('^VIX1D')
            vix = get_last('^VIX')
            vvix = get_last('^VVIX')
            skew = get_last('^SKEW')
            trin = get_last('^TRIN') or 1.0
            
            # Obtener el Open de SPY de hoy (primer registro de la última sesión)
            spy_data = df_close['SPY'].dropna()
            op = float(spy_data.iloc[0]) if not spy_data.empty else lp

            if lp is None or vix1d is None:
                st.error("Error: Faltan datos críticos de SPY o VIX1D.")
                st.stop()

            # Cálculo de Riesgo y Bias
            vix_ratio = vix1d / vix if vix else 1
            risk_score = 0
            if vix_ratio > 1.10: risk_score += 40
            if vvix > 115: risk_score += 30
            if skew > 145: risk_score += 15
            if abs(lp - op) / op > 0.008: risk_score += 15 

            bias = "NEUTRAL"
            if lp > op * 1.004 and trin < 0.85: bias = "ALCISTA"
            elif lp < op * 0.996 and trin > 1.15: bias = "BAJISTA"

            # Configuración de Estrategia
            wing_width = 5 if vix1d > 18 else 2
            target_profit = saldo * 0.005
            riesgo_max = saldo * 0.02
            num_contratos = int(riesgo_max / (wing_width * 100))

            # Definición de Niveles Operativos
            if risk_score >= 75 and bias != "NEUTRAL":
                combo = f"VERTICAL DEBIT SPREAD ({bias})"
                s_c = round(get_delta_strike(lp, vix1d, 0.70, 'call' if bias == 'ALCISTA' else 'put'))
                s_p = 0 
            elif risk_score >= 75:
                combo = "🚫 NO OPERAR"
                s_c, s_p = 0, 0
            elif bias != "NEUTRAL":
                combo = f"VERTICAL CREDIT SPREAD ({bias})"
                s_ref = round(min(lp*0.99, get_delta_strike(lp, vix1d, 0.10, 'put'))) if bias == 'ALCISTA' else round(max(lp*1.01, get_delta_strike(lp, vix1d, 0.10, 'call')))
                s_c, s_p = (0, s_ref) if bias == "ALCISTA" else (s_ref, 0)
            else:
                combo = "IRON CONDOR NEUTRAL"
                s_c = round(max(lp * 1.01, get_delta_strike(lp, vix1d, 0.10, 'call')))
                s_p = round(min(lp * 0.99, get_delta_strike(lp, vix1d, 0.10, 'put')))

            # Interfaz de resultados
            st.divider()
            st.metric("PRECIO SPY", f"{lp:.2f}", f"{((lp-op)/op)*100:.2f}%")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Risk Score", f"{risk_score}/100")
            c2.metric("Bias", bias)
            c3.metric("VIX1D", f"{vix1d:.2f}")

            st.subheader(f"🎯 Estrategia: {combo}")
            
            if s_c != 0 or s_p != 0:
                st.info(f"**Lotes sugeridos:** {max(1, num_contratos)} | **Objetivo:** +{target_profit:.2f}€")
                if "DEBIT" in combo:
                    # Lógica para Debit Spreads
                    st.success(f"✅ COMPRAR: {s_c} | VENDER: {s_c+2 if bias=='ALCISTA' else s_c-2}")
                else:
                    # Lógica para Credit Spreads / Iron Condor
                    if s_c != 0: st.warning(f"CALL: Sell {s_c} / Buy {s_c + wing_width}")
                    if s_p != 0: st.warning(f"PUT: Sell {s_p} / Buy {s_p - wing_width}")
            else:
                st.error("Condiciones de mercado no aptas para operar (Riesgo muy alto).")

        except Exception as e:
            st.error(f"Se produjo un error: {str(e)}")
            st.info("Sugerencia: Asegúrate de que el mercado esté abierto (15:30 - 22:00 hora España).")
