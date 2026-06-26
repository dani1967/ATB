# -*- coding: utf-8 -*-
"""
Analizzatore Tracce Bici V0.0.26 - Menu Dinamico Mappe, Threading, Velocità, Classificazione Pendenze Avanzata
------------------------------------------------------------------------------------------------------------------------
Copyright (C) 2026 Daniele Drago <dandrago@altevista.org>
------------------------------------------------------------------------------------------------------------------------
"""

import os
import math
import time
import json
import threading
import queue
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

# Integrazione Grafica Matplotlib in Tkinter
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Patch

# Geolocalizzazione e Mappe
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import tkintermapview

# Interfaccia Grafica
import tkinter as tk
from tkinter import filedialog, simpledialog, ttk, messagebox

# Variabili di stato globali
cache_localita = {}
file_cache_corrente = ""
epsilon_archiviato = 15
dati_esportazione_tratti = []
fig_da_esportare = None
nome_file_originale = ""
df_globale_analizzato = None  # Conserva i dati per il ricalcolo dinamico delle zone
geoloc_online_var = None      # Controllo attivazione rete immediata
combo_mappa = None            # Riferimento globale per il menu di selezione mappa

# Coda per la comunicazione tra Thread di Background e GUI di Tkinter
coda_geoloc = queue.Queue()

# Componenti GUI per l'input delle zone
ent_ftp = None
ent_fcmax = None
tree_tratti_global = None  # Riferimento globale per l'aggiornamento asincrono
punti_sospesi_bg = []      # Coordinate estratte nell'ultimo parsing per recupero tardivo

# ==========================================
# FUNZIONE AUSILIARIA PER AGGIORNARE LA GUI
# ==========================================
def aggiorna_stato(testo):
    status_var.set(testo)
    root.update_idletasks()

def formatta_timedelta(seconds):
    if pd.isna(seconds) or seconds < 0: return "N/D"
    tot_sec = int(round(seconds))
    ore = tot_sec // 3600
    minuti = (tot_sec % 3600) // 60
    sec = tot_sec % 60
    if ore > 0: return f"{ore}h {minuti:02d}m {sec:02d}s"
    return f"{minuti}m {sec:02d}s"

# ==========================================
# 1. FUNZIONI DI LETTURA DATI
# ==========================================

def read_gpx_file(file_path):
    import gpxpy
    with open(file_path, 'r') as gpx_file:
        gpx = gpxpy.parse(gpx_file)
    data = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                data.append({
                    'time': point.time, 'lat': point.latitude, 'lon': point.longitude,
                    'ele': point.elevation, 'lap': 0, 'distance_fit': np.nan
                })
    df = pd.DataFrame(data)
    if df['time'].notna().any():
        df['time'] = pd.to_datetime(df['time'], utc=True)
    df['power'] = np.nan; df['heart_rate'] = np.nan; df['cadence'] = np.nan
    return df

def read_fit_file(file_path):
    from fitparse import FitFile
    fitfile = FitFile(file_path)
    records = []
    
    aggiorna_stato("Lettura file FIT in corso... Scansione record...")
    
    for message in fitfile.get_messages():
        if message.name == 'record':
            fields = message.get_values()
            
            lat = fields.get('position_latitude') or fields.get('position_lat') or fields.get('latitude') or fields.get('lat')
            lon = fields.get('position_longitude') or fields.get('position_long') or fields.get('longitude') or fields.get('lon')
            
            lat_deg, lon_deg = np.nan, np.nan
            if lat is not None and lon is not None:
                try:
                    l_val = float(lat)
                    o_val = float(lon)
                    if abs(l_val) > 180.0 or abs(o_val) > 180.0:
                        lat_deg = l_val * (180.0 / 2**31)
                        lon_deg = o_val * (180.0 / 2**31)
                    else:
                        lat_deg = l_val
                        lon_deg = o_val
                    if lon_deg > 180.0:
                        lon_deg -= 360.0
                except (ValueError, TypeError):
                    pass
            
            ele = fields.get('enhanced_altitude') or fields.get('altitude') or fields.get('elevation') or fields.get('ele')
            dist = fields.get('distance') or fields.get('total_distance') or fields.get('dist')
            cad = fields.get('cadence') or fields.get('cad') or fields.get('cadenza')
            pwr = fields.get('power') or fields.get('watts') or fields.get('potenza')
            hr = fields.get('heart_rate') or fields.get('bpm') or fields.get('heartrate') or fields.get('frequenza_cardiaca')
            timestamp = fields.get('timestamp') or fields.get('time')
            
            if timestamp is not None or ele is not None or lat_deg is not np.nan:
                records.append({
                    'time': timestamp, 'lat': lat_deg, 'lon': lon_deg, 'ele': ele,
                    'distance_fit': dist, 'cadence': cad, 'power': pwr, 'heart_rate': hr
                })
                
    df = pd.DataFrame(records)
    if not df.empty and 'lat' in df.columns:
        valid_coords = df['lat'].notna().sum()
        aggiorna_stato(f"File FIT letto. Record totali: {len(df)} | Coordinate valide: {valid_coords}")
        time.sleep(0.3)
    return df

# ==========================================
# 2. CALCOLI GEOMETRICI E GESTIONE CACHE
# ==========================================

def haversine_distance(lat1, lon1, lat2, lon2):
    if pd.isna(lat1) or pd.isna(lon1) or lat2 is None or lon2 is None: return 0.0
    if pd.isna(lat2) or pd.isna(lon2): return 0.0
    if lat1 == 0.0 or lon1 == 0.0 or lat2 == 0.0 or lon2 == 0.0: return 0.0
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    return R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

def carica_cache_locale(path_file_originale):
    global cache_localita, file_cache_corrente, epsilon_archiviato
    file_cache_corrente = path_file_originale + ".geonames"
    cache_localita = {}
    epsilon_archiviato = 15
    if os.path.exists(file_cache_corrente):
        try:
            with open(file_cache_corrente, 'r', encoding='utf-8') as f:
                cache_localita = json.load(f)
            if "_meta_epsilon" in cache_localita:
                epsilon_archiviato = int(cache_localita["_meta_epsilon"])
            aggiorna_stato("Cache geografica locale caricata.")
        except Exception:
            cache_localita = {}

def salva_cache_locale(epsilon_usato):
    global cache_localita, file_cache_corrente
    if file_cache_corrente:
        try:
            cache_localita["_meta_epsilon"] = epsilon_usato
            with open(file_cache_corrente, 'w', encoding='utf-8') as f:
                json.dump(cache_localita, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

def get_location_name_sync(lat, lon):
    global cache_localita
    if pd.isna(lat) or pd.isna(lon) or lat == 0.0 or lon == 0.0 or abs(lat) > 90.0 or abs(lon) > 180.0: 
        return "Punto Traccia"
        
    chiave = f"{lat:.4f}_{lon:.4f}"
    if chiave in cache_localita:
        return cache_localita[chiave]
            
    geolocator = Nominatim(user_agent="analizzatore_tracce_bici_v0026")
    try:
        location = geolocator.reverse((lat, lon), timeout=3)
        if location and 'address' in location.raw:
            addr = location.raw['address']
            loc = (addr.get('hamlet') or addr.get('isolated_dwelling') or 
                   addr.get('village') or addr.get('suburb') or 
                   addr.get('town') or addr.get('city'))
            if not loc and 'road' in addr:
                loc = addr.get('road')
            if not loc:
                loc = "Località"
                
            prov = addr.get('county') or addr.get('state')
            prov_str = prov[:2].upper() if prov else ""
            risultato = f"{loc} ({prov_str})" if prov_str else loc
            cache_localita[chiave] = risultato
            return risultato
    except (GeocoderTimedOut, GeocoderServiceError):
        return f"[TO] {lat:.3f},{lon:.3f}"
    except Exception:
        return f"[ERR] {lat:.3f},{lon:.3f}"
        
    return f"{lat:.3f},{lon:.3f}"

def process_track_data(df):
    if df.empty: return df
    aggiorna_stato("Filtraggio e interpolazione geometrica dei dati...")
    
    if 'lat' in df.columns and 'lon' in df.columns:
        df.loc[df['lat'] == 0.0, 'lat'] = np.nan
        df.loc[df['lon'] == 0.0, 'lon'] = np.nan

    for col in ['lat', 'lon', 'ele', 'power', 'heart_rate', 'cadence', 'distance_fit']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').replace([np.inf, -np.inf], np.nan)
            
    df['lat'] = df['lat'].interpolate(method='linear').ffill().bfill()
    df['lon'] = df['lon'].interpolate(method='linear').ffill().bfill()
    df['ele'] = df['ele'].interpolate(method='linear').ffill().bfill().fillna(0.0)

    distances = [0.0]
    lat_col, lon_col = df['lat'].values, df['lon'].values
    for i in range(1, len(df)):
        distances.append(haversine_distance(lat_col[i - 1], lon_col[i - 1], lat_col[i], lon_col[i]))
    df['delta_dist'] = distances
    df['cum_dist_haversine'] = df['delta_dist'].cumsum()

    if 'distance_fit' in df.columns and df['distance_fit'].notna().any() and (df['cum_dist_haversine'].max() < 10.0 or df['lat'].isna().all()):
        df['distance_fit'] = df['distance_fit'].interpolate().ffill().bfill().fillna(0.0)
        df['cum_dist'] = df['distance_fit']
    else:
        df['cum_dist'] = df['cum_dist_haversine']

    # Calcolo della velocità istantanea pre-filtraggio (km/h)
    if 'time' in df.columns and df['time'].notna().sum() > 2:
        df['delta_t_raw'] = pd.to_datetime(df['time']).diff().dt.total_seconds().fillna(1.0)
        df['speed_kmh'] = np.where(df['delta_t_raw'] > 0.1, (df['delta_dist'] / 1000.0) / (df['delta_t_raw'] / 3600.0), 0.0)
        df['speed_kmh'] = df['speed_kmh'].clip(0.0, 95.0)
    else:
        df['speed_kmh'] = np.nan

    filtered = []
    if len(df) > 0:
        filtered.append(df.iloc[0])
        last_dist = df['cum_dist'].iloc[0]
        for idx in range(1, len(df)):
            if (df['cum_dist'].iloc[idx] - last_dist) >= 0.5:
                filtered.append(df.iloc[idx])
                last_dist = df['cum_dist'].iloc[idx]
        if df.index[-1] != filtered[-1].name: filtered.append(df.iloc[-1])
        df = pd.DataFrame(filtered).reset_index(drop=True)

    df['delta_dist'] = df['cum_dist'].diff().fillna(0.0)
    df['ele_filtered'] = savgol_filter(df['ele'], window_length=15, polyorder=2) if len(df) > 15 else df['ele']
    df['delta_ele'] = df['ele_filtered'].diff().fillna(0.0)
    df['slope'] = np.where(df['delta_dist'] > 0.1, (df['delta_ele'] / df['delta_dist']) * 100, 0.0).clip(-35.0, 35.0)
    
    # Ri-smooth della velocità sui punti campionati uniformi
    if 'speed_kmh' in df.columns and df['speed_kmh'].notna().any():
        df['speed_kmh'] = df['speed_kmh'].interpolate().ffill().bfill()
        if len(df) > 15:
            df['speed_kmh'] = savgol_filter(df['speed_kmh'], window_length=15, polyorder=1).clip(0.0, 95.0)
    return df

def get_slope_color(slope):
    if slope < 0: return '#34a853'       # Discesa
    elif slope < 3: return '#fbbc05'     # Falsopiano
    elif slope < 6: return '#ff9900'     # Salita Leggera (3-6%)
    elif slope < 9: return '#dd4b39'     # Salita Sostenuta (6-9%)
    elif slope < 12: return '#b30000'    # Salita Dura (9-12%)
    else: return '#4a0000'               # Muri (>12%)

def douglas_peucker(points, epsilon):
    if len(points) < 3: return [0, len(points) - 1]
    stack = [(0, len(points) - 1)]
    global_indices = {0, len(points) - 1}
    while stack:
        start, end = stack.pop()
        if end - start < 2: continue
        start_pt, end_pt = points[start], points[end]
        max_dist, index = 0.0, start
        ax, ay = start_pt[0], start_pt[1]
        bx, by = end_pt[0], end_pt[1]
        ab_x, ab_y = bx - ax, by - ay
        ab_len_sq = ab_x**2 + ab_y**2
        for i in range(start + 1, end):
            points_i = points[i]
            px, py = points_i[0], points_i[1]
            if ab_len_sq == 0:
                dist = math.sqrt((px - ax)**2 + (py - ay)**2)
            else:
                t = max(0, min(1, ((px - ax) * ab_x + (py - ay) * ab_y) / ab_len_sq))
                dist = math.sqrt((px - (ax + t * ab_x))**2 + (py - (ay + t * ab_y))**2)
            if dist > max_dist: index, max_dist = i, dist
        if max_dist > epsilon:
            global_indices.add(index)
            stack.append((start, index))
            stack.append((index, end))
    return sorted(list(global_indices))

def esporta_report():
    global dati_esportazione_tratti, fig_da_esportare, nome_file_originale
    if not dati_esportazione_tratti: return
    try:
        base_path = os.path.splitext(nome_file_originale)[0]
        csv_path = base_path + "_report_tratti.csv"
        png_path = base_path + "_profilo.png"
        
        df_csv = pd.DataFrame(dati_esportazione_tratti, columns=[
            'ID Tratto', 'Percorso Geografico', 'Lunghezza', 'Dislivello Netto', 'Pendenza Media', 'VAM Media', 'Potenza Media', 'FC Media'
        ])
        df_csv.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=';')
        
        if fig_da_esportare:
            fig_da_esportare.savefig(png_path, dpi=200, bbox_inches='tight')
            
        messagebox.showinfo("Esportazione", f"File scaricati con successo:\n1. {os.path.basename(csv_path)}\n2. {os.path.basename(png_path)}")
    except Exception as e:
        messagebox.showerror("Errore Esportazione", str(e))

# ==========================================
# 3. INTERFACCIA DINAMICA DELLE ZONE INTENSITÀ
# ==========================================
def renderizza_zone_intensita(event=None):
    global df_globale_analizzato, ent_ftp, ent_fcmax
    if df_globale_analizzato is None or df_globale_analizzato.empty: return

    for widget in tab_zone.winfo_children():
        if isinstance(widget, ttk.Frame) and widget == frame_inputs_zone: pass
        else: widget.destroy()

    try:
        ftp = float(ent_ftp.get())
        fc_max = float(ent_fcmax.get())
    except ValueError:
        lbl_err = ttk.Label(tab_zone, text="Inserire parametri FTP e FC Max validi nel pannello in alto.", font=("Helvetica", 11, "bold"), foreground="red")
        lbl_err.pack(pady=40)
        return

    df = df_globale_analizzato.copy()
    if 'time' in df.columns and df['time'].notna().sum() > 2:
        df['delta_t'] = pd.to_datetime(df['time']).diff().dt.total_seconds().fillna(1.0).clip(lower=0.0, upper=10.0)
    else:
        df['delta_t'] = 1.0

    tot_tempo_valido = df['delta_t'].sum()
    if tot_tempo_valido <= 0: tot_tempo_valido = 1.0

    has_power = 'power' in df.columns and df['power'].notna().any()
    has_hr = 'heart_rate' in df.columns and df['heart_rate'].notna().any()

    num_plots = (1 if has_power else 0) + (1 if has_hr else 0)
    if num_plots == 0:
        lbl_no = ttk.Label(tab_zone, text="La traccia corrente non contiene campionamenti di Potenza o FC.", font=("Helvetica", 11))
        lbl_no.pack(pady=40)
        return

    fig, axes = plt.subplots(num_plots, 1, figsize=(11, 3.1 * num_plots))
    if num_plots == 1: axes = [axes]
    plot_idx = 0

    if has_power:
        zone_pwr_defs = [
            ("Z1 - Recupero Attivo (<55%)", 0, 0.55 * ftp, "#dcdcdc"),
            ("Z2 - Endurance (55-75%)", 0.55 * ftp, 0.75 * ftp, "#34a853"),
            ("Z3 - Tempo (75-90%)", 0.75 * ftp, 0.90 * ftp, "#fbbc05"),
            ("Z4 - Soglia Lattacida (90-105%)", 0.90 * ftp, 1.05 * ftp, "#ff6d01"),
            ("Z5 - Vo2Max (105-120%)", 1.05 * ftp, 1.20 * ftp, "#ea4335"),
            ("Z6 - Capacità Anaerobica (>120%)", 1.20 * ftp, 9999 * ftp, "#4a0000")
        ]
        nomi_p, secondi_p, colori_p = [], [], []
        for nome, low, high, col in zone_pwr_defs:
            sec_in_zone = df[(df['power'] >= low) & (df['power'] < high)]['delta_t'].sum()
            nomi_p.append(nome)
            secondi_p.append(sec_in_zone)
            colori_p.append(col)
            
        pct_p = [(s / tot_tempo_valido) * 100 for s in secondi_p]
        ax = axes[plot_idx]
        bars = ax.barh(nomi_p, pct_p, color=colori_p, edgecolor='grey', height=0.55)
        ax.set_xlabel('% del Tempo Totale Attivo')
        ax.set_title(f"Distribuzione Carico Potenza (Soglia FTP: {int(ftp)} W)", fontsize=10, fontweight='bold', loc='left')
        ax.set_xlim(0, max(pct_p) + 12 if max(pct_p) > 0 else 100)
        ax.grid(True, axis='x', linestyle=':', alpha=0.5)
        
        for bar, sec in zip(bars, secondi_p):
            width = bar.get_width()
            if sec > 0:
                ax.text(width + 1, bar.get_y() + bar.get_height()/2, f"{formatta_timedelta(sec)} ({width:.1f}%)", 
                        va='center', ha='left', fontsize=8, fontweight='bold')
        plot_idx += 1

    if has_hr:
        zone_hr_defs = [
            ("Z1 - Rigenerante (<60%)", 0, 0.60 * fc_max, "#dcdcdc"),
            ("Z2 - Fondo Lungo (60-70%)", 0.60 * fc_max, 0.70 * fc_max, "#34a853"),
            ("Z3 - Fondo Medio (70-80%)", 0.70 * fc_max, 0.80 * fc_max, "#fbbc05"),
            ("Z4 - Soglia Anaerobica (80-90%)", 0.80 * fc_max, 0.90 * fc_max, "#ff6d01"),
            ("Z5 - Massimale (>90%)", 0.90 * fc_max, 999 * fc_max, "#ea4335")
        ]
        nomi_h, secondi_h, colori_h = [], [], []
        for nome, low, high, col in zone_hr_defs:
            sec_in_zone = df[(df['heart_rate'] >= low) & (df['heart_rate'] < high)]['delta_t'].sum()
            nomi_h.append(nome)
            secondi_h.append(sec_in_zone)
            colori_h.append(col)
            
        pct_h = [(s / tot_tempo_valido) * 100 for s in secondi_h]
        ax = axes[plot_idx]
        bars = ax.barh(nomi_h, pct_h, color=colori_h, edgecolor='grey', height=0.55)
        ax.set_xlabel('% del Tempo Totale Attivo')
        ax.set_title(f"Distribuzione Carico Frequenza Cardiaca (FC Max: {int(fc_max)} bpm)", fontsize=10, fontweight='bold', loc='left')
        ax.set_xlim(0, max(pct_h) + 12 if max(pct_h) > 0 else 100)
        ax.grid(True, axis='x', linestyle=':', alpha=0.5)
        
        for bar, sec in zip(bars, secondi_h):
            width = bar.get_width()
            if sec > 0:
                ax.text(width + 1, bar.get_y() + bar.get_height()/2, f"{formatta_timedelta(sec)} ({width:.1f}%)", 
                        va='center', ha='left', fontsize=8, fontweight='bold')

    fig.tight_layout()
    canvas_zone = FigureCanvasTkAgg(fig, master=tab_zone)
    canvas_zone.draw()
    canvas_zone.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

# ==========================================
# 4. ENGINE ASINCRONO DI GEOLOCALIZZAZIONE
# ==========================================

def thread_geolocalizzazione(punti_da_geoloc, epsilon_da_salvare):
    for idx_tratto, lat_s, lon_s, lat_e, lon_e in punti_da_geoloc:
        ch_s = f"{lat_s:.4f}_{lon_s:.4f}"
        ch_e = f"{lat_e:.4f}_{lon_e:.4f}"
        
        n_inizio = cache_localita.get(ch_s) or get_location_name_sync(lat_s, lon_s)
        if ch_s not in cache_localita: time.sleep(0.5)
        
        n_fine = cache_localita.get(ch_e) or get_location_name_sync(lat_e, lon_e)
        if ch_e not in cache_localita: time.sleep(0.5)
        
        nuovo_itinerario = f"{n_inizio} ➔ {n_fine}"
        coda_geoloc.put(("TRATTO_PRONTO", idx_tratto, nuovo_itinerario))
        
    coda_geoloc.put(("FINITO", epsilon_da_salvare, ""))

def controlla_coda_eventi():
    global dati_esportazione_tratti, tree_tratti_global
    try:
        while True:
            tipo_msg, parametro1, parametro2 = coda_geoloc.get_nowait()
            
            if tipo_msg == "TRATTO_PRONTO":
                idx_tratto = parametro1
                nuovo_testo = parametro2
                
                if tree_tratti_global and tree_tratti_global.winfo_exists():
                    for item in tree_tratti_global.get_children():
                        valori = list(tree_tratti_global.item(item, 'values'))
                        if valori[0] == f"Tratto {idx_tratto + 1}":
                            valori[1] = nuovo_testo
                            tree_tratti_global.item(item, values=valori)
                            break
                            
                if idx_tratto < len(dati_esportazione_tratti):
                    lista_tratto = list(dati_esportazione_tratti[idx_tratto])
                    lista_tratto[1] = nuovo_testo
                    dati_esportazione_tratti[idx_tratto] = tuple(lista_tratto)
                    
            elif tipo_msg == "FINITO":
                epsilon_salva = parametro1
                salva_cache_locale(epsilon_salva)
                aggiorna_stato("Geolocalizzazione in background ultimata. Cache salvata.")
                return
                
            coda_geoloc.task_done()
    except queue.Empty:
        pass
    root.after(200, controlla_coda_eventi)

def forza_recupero_nomi_manuale():
    global punti_sospesi_bg, epsilon_archiviato
    if not punti_sospesi_bg:
        messagebox.showinfo("Info", "Tutti i tratti correnti sono già localizzati o non ci sono tracce caricate.")
        return
    
    aggiorna_stato(f"Richiesta manuale avviata. Ricerca online per {len(punti_sospesi_bg)} punti in corso...")
    worker = threading.Thread(target=thread_geolocalizzazione, args=(punti_sospesi_bg, epsilon_archiviato), daemon=True)
    worker.start()

def cambia_provider_mappa(event=None):
    global combo_mappa
    scelta = combo_mappa.get()
    map_widget_corrente = None
    for widget in tab_mappa.winfo_children():
        if isinstance(widget, tkintermapview.TkinterMapView):
            map_widget_corrente = widget
            break
            
    if map_widget_corrente:
        if scelta == "OpenTopoMap (Topografica/Isoipse)":
            map_widget_corrente.set_tile_server("https://a.tile.opentopomap.org/{z}/{x}/{y}.png", max_zoom=17)
        elif scelta == "OpenStreetMap (Standard)":
            map_widget_corrente.set_tile_server("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", max_zoom=19)
        elif scelta == "Waymarked Trails (Ciclistica)":
            map_widget_corrente.set_tile_server("https://tile.waymarkedtrails.org/cycling/{z}/{x}/{y}.png", max_zoom=19)
        elif scelta == "USGS Topo (Mappa Geologica US)":
            map_widget_corrente.set_tile_server("https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}", max_zoom=16)

# ==========================================
# 5. ELABORAZIONE TRACCIATO E INTERFACCIA
# ==========================================

def seleziona_e_analizza():
    global fig_da_esportare, nome_file_originale, dati_esportazione_tratti, epsilon_archiviato, df_globale_analizzato, tree_tratti_global, geoloc_online_var, punti_sospesi_bg, combo_mappa
    file_path = filedialog.askopenfilename(
        parent=root, title="Seleziona la traccia GPS/FIT",
        filetypes=[("File validi", "*.gpx *.fit"), ("Tutti i file", "*.*")]
    )
    if not file_path: return
    nome_file_originale = file_path
        
    carica_cache_locale(file_path)
    punti_sospesi_bg = []
    
    epsilon_user = simpledialog.askinteger("Sensibilità", "Tolleranza cambio pendenza (metri dislivello):", 
                                           parent=root, initialvalue=epsilon_archiviato, minvalue=3)
    EPSILON = epsilon_user if epsilon_user is not None else epsilon_archiviato
    epsilon_archiviato = EPSILON
    
    titolo_user = simpledialog.askstring("Titolo", "Titolo del tracciato:", parent=root, initialvalue=os.path.basename(file_path))
    titolo_definitivo = titolo_user if (titolo_user and titolo_user.strip()) else os.path.basename(file_path)
    
    if file_path.lower().endswith('.gpx'): df_raw = read_gpx_file(file_path)
    else: df_raw = read_fit_file(file_path)
    
    if df_raw is None or df_raw.empty: 
        aggiorna_stato("Errore: Il file selezionato non contiene dati validi.")
        return
    
    df = process_track_data(df_raw)
    df_globale_analizzato = df
    
    idx_gpm = df['ele_filtered'].idxmax()
    quota_max = df['ele_filtered'].iloc[idx_gpm]
    dist_gpm = df['cum_dist'].iloc[idx_gpm]
    lat_gpm = df['lat'].iloc[idx_gpm]
    lon_gpm = df['lon'].iloc[idx_gpm]
    
    # Nome provvisorio del GPM
    ch_gpm = f"{lat_gpm:.4f}_{lon_gpm:.4f}"
    nome_gpm_iniziale = cache_localita.get(ch_gpm) or f"Vetta ({lat_gpm:.3f}, {lon_gpm:.3f})"

    aggiorna_stato("Calcolo divisione tratti (Douglas-Peucker)...")
    pts = list(zip(df['cum_dist'].values, df['ele_filtered'].values))
    split_indices = sorted(list(set(douglas_peucker(pts, EPSILON))))
    NUM_SEGMENTS = len(split_indices) - 1
    
    # Pulizia dei vecchi tab grafici
    for tab in [tab_profilo, tab_tabella, tab_mappa, tab_stats]:
        for widget in tab.winfo_children(): widget.destroy()
    for widget in tab_zone.winfo_children():
        if widget != frame_inputs_zone: widget.destroy()
        
    # Rigenerazione barra dei comandi manuali interni del Tab Tabella
    frame_tabella_top = ttk.Frame(tab_tabella, padding=5)
    frame_tabella_top.pack(side=tk.TOP, fill=tk.X)
    btn_forza_nomi = ttk.Button(frame_tabella_top, text="🔄 Recupera Nomi Online Adesso (In Background)", command=forza_recupero_nomi_manuale)
    btn_forza_nomi.pack(side=tk.LEFT, padx=5)
    
    df_map_clean = df[df['lat'].notna() & (df['lat'] != 0.0) & (df['lat'].abs() <= 90.0)]
    map_coordinates = list(zip(df_map_clean['lat'].values, df_map_clean['lon'].values))
    
    map_widget = tkintermapview.TkinterMapView(tab_mappa, corner_radius=0)
    map_widget.pack(fill=tk.BOTH, expand=True)
    
    # IMPOSTAZIONE TILE SERVER DINAMICA BASATA SUL MENU DI SCELTA
    scelta_attuale = combo_mappa.get()
    if scelta_attuale == "OpenTopoMap (Topografica/Isoipse)":
        map_widget.set_tile_server("https://a.tile.opentopomap.org/{z}/{x}/{y}.png", max_zoom=17)
    elif scelta_attuale == "OpenStreetMap (Standard)":
        map_widget.set_tile_server("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", max_zoom=19)
    elif scelta_attuale == "Waymarked Trails (Ciclistica)":
        map_widget.set_tile_server("https://tile.waymarkedtrails.org/cycling/{z}/{x}/{y}.png", max_zoom=19)
    elif scelta_attuale == "USGS Topo (Mappa Geologica US)":
        map_widget.set_tile_server("https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}", max_zoom=16)
    
    if map_coordinates:
        map_widget.set_path(map_coordinates, color="#1a1a1a", width=3)
    
    fig, ax_plot = plt.subplots(figsize=(11, 4.8))
    fig_da_esportare = fig
    min_ele = df['ele_filtered'].min() - 30
    
    has_power = 'power' in df.columns and df['power'].notna().any()
    has_hr = 'heart_rate' in df.columns and df['heart_rate'].notna().any()
    has_time = 'time' in df.columns and df['time'].notna().any()
    has_speed = 'speed_kmh' in df.columns and df['speed_kmh'].notna().any()

    table_rows = []
    vams_list = []
    
    for i in range(NUM_SEGMENTS):
        s_idx, e_idx = split_indices[i], split_indices[i+1]
        seg_data = df.iloc[s_idx:e_idx + 1]
        
        seg_dist = seg_data['cum_dist'].iloc[-1] - seg_data['cum_dist'].iloc[0]
        seg_ele_change = seg_data['ele_filtered'].iloc[-1] - seg_data['ele_filtered'].iloc[0]
        seg_ascent = seg_data['delta_ele'].clip(lower=0).sum()
        avg_slope = (seg_ele_change / seg_dist * 100) if seg_dist > 5 else 0.0
        color = get_slope_color(avg_slope)
        
        ax_plot.plot(seg_data['cum_dist'], seg_data['ele_filtered'], color='#202124', linewidth=1)
        ax_plot.fill_between(seg_data['cum_dist'], seg_data['ele_filtered'], min_ele, color=color, alpha=0.75)
        
        x_c = (seg_data['cum_dist'].iloc[0] + seg_data['cum_dist'].iloc[-1]) / 2
        y_c = seg_data['ele_filtered'].iloc[len(seg_data) // 2]
        ax_plot.text(x_c, y_c + 5, str(i+1), color='black', fontsize=8, fontweight='bold', ha='center',
                     bbox=dict(boxstyle='circle,pad=0.15', facecolor='white', edgecolor='#5f6368', alpha=0.8))
        
        lat_start, lon_start = 0.0, 0.0
        for idx in range(s_idx, min(e_idx + 1, len(df))):
            if pd.notna(df['lat'].iloc[idx]) and df['lat'].iloc[idx] != 0.0:
                lat_start, lon_start = float(df['lat'].iloc[idx]), float(df['lon'].iloc[idx])
                break
        lat_end, lon_end = 0.0, 0.0
        for idx in range(e_idx, max(s_idx - 1, -1), -1):
            if pd.notna(df['lat'].iloc[idx]) and df['lat'].iloc[idx] != 0.0:
                lat_end, lon_end = float(df['lat'].iloc[idx]), float(df['lon'].iloc[idx])
                break

        ch_s, ch_e = f"{lat_start:.4f}_{lon_start:.4f}", f"{lat_end:.4f}_{lon_end:.4f}"
        
        if ch_s in cache_localita and ch_e in cache_localita:
            testo_itinerario = f"{cache_localita[ch_s]} ➔ {cache_localita[ch_e]}"
        else:
            if geoloc_online_var.get():
                testo_itinerario = f"{lat_start:.3f},{lon_start:.3f} ➔ {lat_end:.3f},{lon_end:.3f} (Ricerca...)"
                punti_sospesi_bg.append((i, lat_start, lon_start, lat_end, lon_end))
            else:
                n_s = cache_localita.get(ch_s) or f"[OFF] {lat_start:.3f},{lon_start:.3f}"
                n_e = cache_localita.get(ch_e) or f"[OFF] {lat_end:.3f},{lon_end:.3f}"
                testo_itinerario = f"{n_s} ➔ {n_e}"
                punti_sospesi_bg.append((i, lat_start, lon_start, lat_end, lon_end))
        
        if i == 0 and lat_start != 0.0:
            map_widget.set_marker(lat_start, lon_start, text="PARTENZA")
        if lat_end != 0.0:
            map_widget.set_marker(lat_end, lon_end, text=f"Tratto {i+1}")
        
        vam_val = 0
        vam_str = "0 m/h"
        if has_time and seg_ascent > 0.5 and len(seg_data['time'].dropna()) >= 2:
            dur = (seg_data['time'].dropna().iloc[-1] - seg_data['time'].dropna().iloc[0]).total_seconds() / 3600.0
            if dur > 0: 
                vam_val = int(round(seg_ascent / dur))
                vam_str = f"{vam_val} m/h"
        vams_list.append(vam_val if vam_val > 0 else np.nan)
            
        pwr = f"{round(seg_data['power'].mean())} W" if has_power and seg_data['power'].notna().any() else "N/D"
        hr = f"{round(seg_data['heart_rate'].mean())} bpm" if has_hr and seg_data['heart_rate'].notna().any() else "N/D"
        
        table_rows.append((f"Tratto {i+1}", testo_itinerario, f"{seg_dist/1000:.2f} km", 
                           f"{'+' if seg_ele_change>=0 else ''}{seg_ele_change:.1f} m", f"{avg_slope:.1f} %", vam_str, pwr, hr))

    dati_esportazione_tratti = table_rows

    # Costruzione del Bilancio Globale
    tot_dist_km = (df['cum_dist'].iloc[-1] - df['cum_dist'].iloc[0]) / 1000.0
    tot_ascent = df['delta_ele'].clip(lower=0).sum()
    tot_tempo_str = "N/D"
    vam_globale = 0
    if has_time and len(df['time'].dropna()) >= 2:
        sec_totali = (df['time'].dropna().iloc[-1] - df['time'].dropna().iloc[0]).total_seconds()
        tot_tempo_str = formatta_timedelta(sec_totali)
        if sec_totali > 0 and tot_ascent > 0:
            vam_globale = int(round(tot_ascent / (sec_totali / 3600.0)))

    valid_speeds = df['speed_kmh'].dropna() if has_speed else pd.Series()
    valid_powers = df['power'].dropna() if has_power else pd.Series()
    valid_hrs = df['heart_rate'].dropna() if has_hr else pd.Series()
    valid_vams = pd.Series(vams_list).dropna()

    frame_card = ttk.LabelFrame(tab_stats, text=" BILANCIO GLOBALE DELL'USCITA ", padding=15)
    frame_card.pack(fill=tk.X, padx=15, pady=15)
    ttk.Label(frame_card, text=f"Distanza Totale: {tot_dist_km:.2f} km", font=('Helvetica', 11, 'bold')).grid(row=0, column=0, padx=20, pady=5, sticky='w')
    ttk.Label(frame_card, text=f"Dislivello Complessivo: +{tot_ascent:.1f} m", font=('Helvetica', 11, 'bold')).grid(row=0, column=1, padx=20, pady=5, sticky='w')
    ttk.Label(frame_card, text=f"Tempo Totale: {tot_tempo_str}", font=('Helvetica', 11, 'bold')).grid(row=0, column=2, padx=20, pady=5, sticky='w')
    ttk.Label(frame_card, text=f"Punto Culminante (GPM): {nome_gpm_iniziale} ({quota_max:.1f} m)", font=('Helvetica', 10, 'italic')).grid(row=1, column=0, columnspan=3, padx=20, pady=10, sticky='w')

    frame_grid = ttk.LabelFrame(tab_stats, text=" ANALISI STATISTICA DESCRITTIVA DELLE METRICHE ", padding=10)
    frame_grid.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
    
    grid_cols = ('stat', 'velocita', 'vam', 'potenza', 'fc')
    tree_stats = ttk.Treeview(frame_grid, columns=grid_cols, show='headings', height=4)
    tree_stats.heading('stat', text='Metrica')
    tree_stats.heading('velocita', text='Velocità (km/h)')
    tree_stats.heading('vam', text='VAM (m/h)')
    tree_stats.heading('potenza', text='Potenza (W)')
    tree_stats.heading('fc', text='Frequenza Card. (bpm)')
    for c in grid_cols: tree_stats.column(c, width=150, anchor='center')
        
    tree_stats.insert('', tk.END, values=("MEDIA", f"{valid_speeds.mean():.1f} km/h" if has_speed else "N/D", f"{vam_globale} m/h", f"{round(valid_powers.mean()) if has_power else 'N/D'}", f"{round(valid_hrs.mean()) if has_hr else 'N/D'}"))
    tree_stats.insert('', tk.END, values=("MEDIANA", f"{valid_speeds.median():.1f} km/h" if has_speed else "N/D", f"{int(round(valid_vams.median())) if not valid_vams.empty else 'N/D'}", f"{round(valid_powers.median()) if has_power else 'N/D'}", f"{round(valid_hrs.median()) if has_hr else 'N/D'}"))
    tree_stats.insert('', tk.END, values=("MASSIMO", f"{valid_speeds.max():.1f} km/h" if has_speed else "N/D", f"{int(valid_vams.max()) if not valid_vams.empty else 'N/D'}", f"{round(valid_powers.max()) if has_power else 'N/D'}", f"{round(valid_hrs.max()) if has_hr else 'N/D'}"))
    tree_stats.insert('', tk.END, values=("MINIMO", f"{valid_speeds.min():.1f} km/h" if has_speed else "N/D", f"{int(valid_vams.min()) if not valid_vams.empty else 'N/D'}", f"{round(valid_powers.min()) if has_power else 'N/D'}", f"{round(valid_hrs.min()) if has_hr else 'N/D'}"))
    tree_stats.pack(fill=tk.BOTH, expand=True)

    lbl_t = ttk.Label(tab_zone, text="Apri questo tab per calcolare i grafici di ripartizione fisiologica del carico.", font=("Helvetica", 10), foreground="#5f6368")
    lbl_t.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    # Disegno del Profilo Altimetrico
    ax_plot.axvline(x=dist_gpm, color='#b22222', linestyle=':', alpha=0.8, linewidth=1.5)
    ax_plot.plot(dist_gpm, quota_max, marker='^', color='#b22222', markersize=7)
    ax_plot.text(dist_gpm, quota_max + 12, f"GPM\n({quota_max:.1f} m)", color='#b22222', fontsize=8, fontweight='bold', ha='center',
                 bbox=dict(boxstyle='round,pad=0.2', facecolor='#fff5f5', edgecolor='#b22222', alpha=0.9))
                 
    if lat_gpm != 0.0:
        map_widget.set_marker(lat_gpm, lon_gpm, text=f"⛰️ CULMINE ({quota_max:.0f}m)")

    if not df_map_clean.empty:
        map_widget.set_position(float(df_map_clean['lat'].mean()), float(df_map_clean['lon'].mean()))
        map_widget.set_zoom(12)

    ax_plot.set_title(f"Profilo Altimetrico: {titolo_definitivo}", fontsize=11, fontweight='bold', loc='left')
    ax_plot.grid(True, linestyle='--', alpha=0.4)
    ax_plot.set_xlim(df['cum_dist'].min(), df['cum_dist'].max())
    ax_plot.set_ylim(bottom=min_ele)
    
    # LEGENDA AGGIORNATA
    legend_el = [
        Patch(facecolor='#34a853', alpha=0.75, label='Discesa (<0%)'), 
        Patch(facecolor='#fbbc05', alpha=0.75, label='Falsopiano (0-3%)'),
        Patch(facecolor='#ff9900', alpha=0.75, label='Salita Leggera (3-6%)'), 
        Patch(facecolor='#dd4b39', alpha=0.75, label='Salita Sostenuta (6-9%)'),
        Patch(facecolor='#b30000', alpha=0.75, label='Salita Dura (9-12%)'), 
        Patch(facecolor='#4a0000', alpha=0.75, label='Muri (>12%)')
    ]
    ax_plot.legend(handles=legend_el, loc='upper left', fontsize=8)
    
    canvas = FigureCanvasTkAgg(fig, master=tab_profilo)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # Costruzione Tabella Tratti
    cols = ('id', 'itinerario', 'lunghezza', 'dislivello', 'pendenza', 'vam', 'potenza', 'fc')
    tree_tratti_global = ttk.Treeview(tab_tabella, columns=cols, show='headings')
    tree_tratti_global.heading('id', text='ID Tratto')
    tree_tratti_global.heading('itinerario', text='Percorso Geografico')
    tree_tratti_global.heading('lunghezza', text='Lunghezza'); tree_tratti_global.heading('dislivello', text='Dislivello Netto')
    tree_tratti_global.heading('pendenza', text='Pendenza Media'); tree_tratti_global.heading('vam', text='VAM Media')
    tree_tratti_global.heading('potenza', text='Potenza Media'); tree_tratti_global.heading('fc', text='FC Media')
    
    tree_tratti_global.column('id', width=70, anchor='center'); tree_tratti_global.column('itinerario', width=420, anchor='w')
    for c in cols[2:]: tree_tratti_global.column(c, width=105, anchor='center')
    
    tree_tratti_global.tag_configure('pari', background='#f8f9fa')
    for idx, row in enumerate(table_rows):
        tag = 'pari' if idx % 2 == 0 else ''
        tree_tratti_global.insert('', tk.END, values=row, tags=(tag,))
        
    scrollbar = ttk.Scrollbar(tab_tabella, orient=tk.VERTICAL, command=tree_tratti_global.yview)
    tree_tratti_global.configure(yscroll=scrollbar.set)
    tree_tratti_global.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    notebook.select(tab_profilo)
    btn_export.config(state=tk.NORMAL)
    
    notebook.bind("<<NotebookTabChanged>>", lambda e: renderizza_zone_intensita(None) if notebook.index("current") == 3 else None)
    
    if geoloc_online_var.get() and punti_sospesi_bg:
        aggiorna_stato(f"Dati caricati. Ricerca asincrona in background avviata per {len(punti_sospesi_bg)} punti...")
        worker = threading.Thread(target=thread_geolocalizzazione, args=(punti_sospesi_bg, EPSILON), daemon=True)
        worker.start()
    else:
        salva_cache_locale(EPSILON)
        aggiorna_stato("Analisi completata. Localizzazione istantanea (da cache o offline).")

def esci_programma():
    aggiorna_stato("Chiusura componenti...")
    try:
        for widget in tab_mappa.winfo_children():
            if isinstance(widget, tkintermapview.TkinterMapView): widget.destroy()
    except Exception: pass
    root.quit()
    root.destroy()

# ==========================================
# 6. COSTRUZIONE INTERFACCIA PRINCIPALE
# ==========================================
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Analizzatore Performance Bici V0.0.26")
    root.geometry("1280x800")
    root.minsize(900, 550)
    
    geoloc_online_var = tk.BooleanVar(value=True)
    
    style = ttk.Style()
    style.theme_use('clam')
    
    top_bar = ttk.Frame(root, padding="10")
    top_bar.pack(side=tk.TOP, fill=tk.X)
    
    btn_carica = ttk.Button(top_bar, text="Seleziona File e Avvia Analisi Traccia", command=seleziona_e_analizza)
    btn_carica.pack(side=tk.LEFT, padx=5)
    
    chk_geoloc = ttk.Checkbutton(top_bar, text="Geolocalizzazione Online all'avvio", variable=geoloc_online_var)
    chk_geoloc.pack(side=tk.LEFT, padx=15)
    
    # AGGIUNTA MENU DI SCELTA PROVIDER MAPPA NELLA BARRA SUPERIORE
    ttk.Label(top_bar, text="Tipo Mappa:", font=("Helvetica", 9, "bold")).pack(side=tk.LEFT, padx=(10, 2))
    
    mappe_disponibili = [
        "OpenTopoMap (Topografica/Isoipse)",
        "OpenStreetMap (Standard)",
        "Waymarked Trails (Ciclistica)",
        "USGS Topo (Mappa Geologica US)"
    ]
    combo_mappa = ttk.Combobox(top_bar, values=mappe_disponibili, state="readonly", width=30)
    combo_mappa.set("OpenTopoMap (Topografica/Isoipse)") # Valore di default
    combo_mappa.pack(side=tk.LEFT, padx=5)
    combo_mappa.bind("<<ComboboxSelected>>", cambia_provider_mappa)
    
    btn_export = ttk.Button(top_bar, text="Scarica Report (CSV + PNG)", command=esporta_report, state=tk.DISABLED)
    btn_export.pack(side=tk.LEFT, padx=5)
    
    btn_esci = ttk.Button(top_bar, text="Chiudi Applicazione", command=esci_programma)
    btn_esci.pack(side=tk.LEFT, padx=5)
    
    lbl_info = ttk.Label(top_bar, text="Pendenze: Sostenuta (6-9%) integrata", font=("Helvetica", 9, "italic"), foreground="#4a0000")
    lbl_info.pack(side=tk.LEFT, padx=20)
    
    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    tab_profilo = ttk.Frame(notebook)
    tab_tabella = ttk.Frame(notebook)
    tab_stats = ttk.Frame(notebook)
    tab_zone = ttk.Frame(notebook)
    tab_mappa = ttk.Frame(notebook)
    
    notebook.add(tab_profilo, text="  Profilo Altimetrico  ")
    notebook.add(tab_tabella, text="  Tabella Tratti  ")
    notebook.add(tab_stats, text="  Statistiche  ")
    notebook.add(tab_zone, text="  Zone Intensità  ")
    notebook.add(tab_mappa, text="  Mappa Percorso  ")
    
    frame_tabella_top = ttk.Frame(tab_tabella, padding=5)
    frame_tabella_top.pack(side=tk.TOP, fill=tk.X)
    btn_forza_nomi = ttk.Button(frame_tabella_top, text="🔄 Recupera Nomi Online Adesso (In Background)", command=forza_recupero_nomi_manuale)
    btn_forza_nomi.pack(side=tk.LEFT, padx=5)
    
    frame_inputs_zone = ttk.Frame(tab_zone, padding=8, relief=tk.RIDGE)
    frame_inputs_zone.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
    
    ttk.Label(frame_inputs_zone, text="Soglia FTP (Watt):", font=('Helvetica', 9, 'bold')).pack(side=tk.LEFT, padx=(10, 5))
    ent_ftp = ttk.Entry(frame_inputs_zone, width=8)
    ent_ftp.insert(0, "250")
    ent_ftp.pack(side=tk.LEFT, padx=5)
    
    ttk.Label(frame_inputs_zone, text="FC Max (bpm):", font=('Helvetica', 9, 'bold')).pack(side=tk.LEFT, padx=(20, 5))
    ent_fcmax = ttk.Entry(frame_inputs_zone, width=8)
    ent_fcmax.insert(0, "185")
    ent_fcmax.pack(side=tk.LEFT, padx=5)
    
    btn_aggiorna_zone = ttk.Button(frame_inputs_zone, text="Ricalcola e Aggiorna Grafici Zone", command=lambda: renderizza_zone_intensita(None))
    btn_aggiorna_zone.pack(side=tk.LEFT, padx=25)
    
    notebook.bind("<<NotebookTabChanged>>", lambda e: renderizza_zone_intensita(None) if notebook.index("current") == 3 else None)
    
    for tab, txt in [(tab_profilo, "Grafico Altimetrico"), (tab_tabella, "Tabella Dati Performance"), (tab_stats, "Riepilogo e Mediane"), (tab_mappa, "Mappa GPS OpenStreetMap")]:
        lbl = ttk.Label(tab, text=f"Nessun dato caricato. Premi il pulsante in alto per generare il {txt}.", font=("Helvetica", 10), foreground="#5f6368")
        lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
    status_var = tk.StringVar()
    status_var.set("Pronto. Seleziona un file per iniziare.")
    
    status_bar = ttk.Frame(root, relief=tk.SUNKEN, padding=(5, 2))
    status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    status_label = ttk.Label(status_bar, textvariable=status_var, font=("Helvetica", 9), foreground="#3c4043")
    status_label.pack(side=tk.LEFT)
    
    root.after(200, controlla_coda_eventi)
    root.protocol("WM_DELETE_WINDOW", esci_programma)
    root.mainloop()