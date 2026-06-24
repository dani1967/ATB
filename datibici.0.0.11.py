# -*- coding: utf-8 -*-
"""
Analizzatore Tracce Bici
-------------------------------------------------------------------------
Copyright (C) 2026 Daniele Drago <dandrago@altevista.org>
-------------------------------------------------------------------------
"""

import os
# Forza le librerie di calcolo a usare un solo thread (previene i blocchi nei binari PyInstaller)
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"

import math
import time
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
from tkinter import filedialog, simpledialog, ttk

# ==========================================
# FUNZIONE AUSILIARIA PER AGGIORNARE LA GUI
# ==========================================
def aggiorna_stato(testo):
    """Aggiorna la barra di stato visiva e forza il ridisegno della GUI"""
    status_var.set(testo)
    root.update_idletasks()

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
        time.sleep(0.5)
    return df

# ==========================================
# 2. CALCOLI GEOMETRICI E FILTRAGGIO
# ==========================================

def haversine_distance(lat1, lon1, lat2, lon2):
    if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2): return 0.0
    if lat1 == 0.0 or lon1 == 0.0 or lat2 == 0.0 or lon2 == 0.0: return 0.0
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    return R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

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
    return df

def get_slope_color(slope):
    if slope < 0: return '#34a853'
    elif slope < 3: return '#fbbc05'
    elif slope < 7: return '#ff6d01'
    elif slope < 11: return '#ea4335'
    else: return '#4a0000'

def get_location_name(lat, lon):
    """Recupera il nome località. Restituisce la sigla compatta (TR) in caso di timeout"""
    if pd.isna(lat) or pd.isna(lon) or lat == 0.0 or lon == 0.0 or abs(lat) > 90.0 or abs(lon) > 180.0: 
        return "Punto Traccia"
        
    geolocator = Nominatim(user_agent="analizzatore_tracce_bici_v86")
    try:
        location = geolocator.reverse((lat, lon), timeout=3)
        if location and 'address' in location.raw:
            addr = location.raw['address']
            loc = addr.get('village') or addr.get('town') or addr.get('city') or addr.get('suburb') or addr.get('hamlet') or "Località"
            prov = addr.get('county') or addr.get('state')
            prov_str = prov[:2].upper() if prov else ""
            return f"{loc} ({prov_str})" if prov_str else loc
    except (GeocoderTimedOut, GeocoderServiceError):
        # Sostituita la stringa estesa con la sigla compatta richiesta per preservare la larghezza della tabella
        return f"{lat:.3f}, {lon:.3f} (TR)"
    except Exception:
        return f"{lat:.3f}, {lon:.3f} (Offline)"
        
    return f"{lat:.3f}, {lon:.3f}"

# ==========================================
# 3. ALGORITMO DOUGLAS-PEUCKER
# ==========================================
def douglas_peucker(points, epsilon):
    """Versione Iterativa Fault-Tolerant per prevenire crash su Linux compilato"""
    if len(points) < 3:
        return [0, len(points) - 1]

    stack = [(0, len(points) - 1)]
    global_indices = {0, len(points) - 1}

    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue

        start_pt, end_pt = points[start], points[end]
        max_dist = 0.0
        index = start

        ax, ay = start_pt[0], start_pt[1]
        bx, by = end_pt[0], end_pt[1]
        ab_x, ab_y = bx - ax, by - ay
        ab_len_sq = ab_x ** 2 + ab_y ** 2

        for i in range(start + 1, end):
            px, py = points[i][0], points[i][1]
            if ab_len_sq == 0:
                dist = math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
            else:
                t = max(0, min(1, ((px - ax) * ab_x + (py - ay) * ab_y) / ab_len_sq))
                dist = math.sqrt((px - (ax + t * ab_x)) ** 2 + (py - (ay + t * ab_y)) ** 2)
            if dist > max_dist:
                index, max_dist = i, dist

        if max_dist > epsilon:
            global_indices.add(index)
            stack.append((start, index))
            stack.append((index, end))

    return sorted(list(global_indices))
# ==========================================
# 4. GESTIONE FLUSSO ED ELABORAZIONE
# ==========================================
def seleziona_e_analizza():
    file_path = filedialog.askopenfilename(
        parent=root, title="Seleziona la traccia GPS/FIT",
        filetypes=[("File validi", "*.gpx *.fit"), ("Tutti i file", "*.*")]
    )
    if not file_path: return
        
    epsilon_user = simpledialog.askinteger("Sensibilità", "Tolleranza cambio pendenza (metri dislivello):", parent=root, initialvalue=15, minvalue=3)
    EPSILON = epsilon_user if epsilon_user is not None else 15
    
    titolo_user = simpledialog.askstring("Titolo", "Titolo del tracciato:", parent=root, initialvalue=os.path.basename(file_path))
    titolo_definitivo = titolo_user if (titolo_user and titolo_user.strip()) else os.path.basename(file_path)
    
    if file_path.lower().endswith('.gpx'): df_raw = read_gpx_file(file_path)
    else: df_raw = read_fit_file(file_path)
    
    if df_raw is None or df_raw.empty: 
        aggiorna_stato("Errore: Il file selezionato non contiene dati validi.")
        return
    
    df = process_track_data(df_raw)
    
    # Individuazione e geolocalizzazione GPM
    aggiorna_stato("Identificazione punto di massima quota (GPM)...")
    idx_gpm = df['ele_filtered'].idxmax()
    quota_max = df['ele_filtered'].iloc[idx_gpm]
    dist_gpm = df['cum_dist'].iloc[idx_gpm]
    lat_gpm = df['lat'].iloc[idx_gpm]
    lon_gpm = df['lon'].iloc[idx_gpm]
    
    nome_gpm = "Quota Massima"
    if pd.notna(lat_gpm) and lat_gpm != 0.0:
        nome_gpm = get_location_name(lat_gpm, lon_gpm)
        time.sleep(0.3)

    aggiorna_stato("Esecuzione algoritmo Douglas-Peucker e suddivisione tratti...")
    pts = list(zip(df['cum_dist'].values, df['ele_filtered'].values))
    split_indices = sorted(list(set(douglas_peucker(pts, EPSILON))))
    NUM_SEGMENTS = len(split_indices) - 1
    
    for widget in tab_profilo.winfo_children(): widget.destroy()
    for widget in tab_tabella.winfo_children(): widget.destroy()
    for widget in tab_mappa.winfo_children(): widget.destroy()
    
    df_map_clean = df[df['lat'].notna() & (df['lat'] != 0.0) & (df['lat'].abs() <= 90.0)]
    map_coordinates = list(zip(df_map_clean['lat'].values, df_map_clean['lon'].values))
    
    map_widget = tkintermapview.TkinterMapView(tab_mappa, corner_radius=0)
    map_widget.pack(fill=tk.BOTH, expand=True)
    
    if map_coordinates:
        map_widget.set_path(map_coordinates, color="#202124", width=3)
    
    fig, ax_plot = plt.subplots(figsize=(11, 5))
    min_ele = df['ele_filtered'].min() - 30
    
    has_power = 'power' in df.columns and df['power'].notna().any()
    has_hr = 'heart_rate' in df.columns and df['heart_rate'].notna().any()
    has_time = 'time' in df.columns and df['time'].notna().any()

    table_rows = []
    
    for i in range(NUM_SEGMENTS):
        aggiorna_stato(f"Geolocalizzazione OSM: Tratto {i+1} di {NUM_SEGMENTS}...")
        
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
        
        lat_start, lon_start = np.nan, np.nan
        for idx in range(s_idx, min(e_idx + 1, len(df))):
            if pd.notna(df['lat'].iloc[idx]) and df['lat'].iloc[idx] != 0.0 and abs(df['lat'].iloc[idx]) <= 90.0:
                lat_start = float(df['lat'].iloc[idx])
                lon_start = float(df['lon'].iloc[idx])
                break
                
        lat_end, lon_end = np.nan, np.nan
        for idx in range(e_idx, max(s_idx - 1, -1), -1):
            if pd.notna(df['lat'].iloc[idx]) and df['lat'].iloc[idx] != 0.0 and abs(df['lat'].iloc[idx]) <= 90.0:
                lat_end = float(df['lat'].iloc[idx])
                lon_end = float(df['lon'].iloc[idx])
                break

        n_inizio = get_location_name(lat_start, lon_start)
        time.sleep(0.3)
        n_fine = get_location_name(lat_end, lon_end)
        time.sleep(0.3)
        
        if i == 0 and pd.notna(lat_start):
            map_widget.set_marker(lat_start, lon_start, text="PARTENZA")
        if pd.notna(lat_end):
            map_widget.set_marker(lat_end, lon_end, text=f"Tratto {i+1}")
        
        vam = "0 m/h"
        if has_time and seg_ascent > 0.5 and len(seg_data['time'].dropna()) >= 2:
            dur = (seg_data['time'].dropna().iloc[-1] - seg_data['time'].dropna().iloc[0]).total_seconds() / 3600.0
            if dur > 0: vam = f"{round(seg_ascent / dur)} m/h"
            
        pwr = f"{round(seg_data['power'].mean())} W" if has_power and seg_data['power'].notna().any() else "N/D"
        hr = f"{round(seg_data['heart_rate'].mean())} bpm" if has_hr and seg_data['heart_rate'].notna().any() else "N/D"
        
        table_rows.append((f"Tratto {i+1}", f"{n_inizio} ➔ {n_fine}", f"{seg_dist/1000:.2f} km", 
                           f"{'+' if seg_ele_change>=0 else ''}{seg_ele_change:.1f} m", f"{avg_slope:.1f} %", vam, pwr, hr))

    # Inserimento grafico e mappa del GPM
    ax_plot.axvline(x=dist_gpm, color='#b22222', linestyle=':', alpha=0.8, linewidth=1.5)
    ax_plot.plot(dist_gpm, quota_max, marker='^', color='#b22222', markersize=7)
    testo_gpm = f"GPM: {nome_gpm}\n({quota_max:.1f} m)"
    ax_plot.text(dist_gpm, quota_max + 12, testo_gpm, color='#b22222', fontsize=8, fontweight='bold', ha='center',
                 bbox=dict(boxstyle='round,pad=0.2', facecolor='#fff5f5', edgecolor='#b22222', alpha=0.9))
                 
    if pd.notna(lat_gpm) and lat_gpm != 0.0:
        map_widget.set_marker(lat_gpm, lon_gpm, text=f"⛰️ CULMINE ({quota_max:.0f}m)")

    if not df_map_clean.empty:
        centro_lat = float(df_map_clean['lat'].mean())
        centro_lon = float(df_map_clean['lon'].mean())
        map_widget.set_position(centro_lat, centro_lon)
        map_widget.set_zoom(12)

    ax_plot.set_title(f"Profilo Altimetrico: {titolo_definitivo}", fontsize=11, fontweight='bold')
    ax_plot.grid(True, linestyle='--', alpha=0.4)
    ax_plot.set_xlim(df['cum_dist'].min(), df['cum_dist'].max())
    ax_plot.set_ylim(bottom=min_ele)
    legend_el = [
        Patch(facecolor='#34a853', alpha=0.75, label='Discesa (<0%)'), Patch(facecolor='#fbbc05', alpha=0.75, label='Falsopiano (0-3%)'),
        Patch(facecolor='#ff6d01', alpha=0.75, label='Salita (3-7%)'), Patch(facecolor='#ea4335', alpha=0.75, label='Dura (7-11%)'), Patch(facecolor='#4a0000', alpha=0.75, label='Muri (>11%)')
    ]
    ax_plot.legend(handles=legend_el, loc='upper left', fontsize=8)
    
    canvas = FigureCanvasTkAgg(fig, master=tab_profilo)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # Griglia avanzata Treeview
    cols = ('id', 'itinerario', 'lunghezza', 'dislivello', 'pendenza', 'vam', 'potenza', 'fc')
    tree = ttk.Treeview(tab_tabella, columns=cols, show='headings')
    
    tree.heading('id', text='ID Tratto'); tree.heading('itinerario', text='Percorso Geografico')
    tree.heading('lunghezza', text='Lunghezza'); tree.heading('dislivello', text='Dislivello Netto')
    tree.heading('pendenza', text='Pendenza Media'); tree.heading('vam', text='VAM Media')
    tree.heading('potenza', text='Potenza Media'); tree.heading('fc', text='FC Media')
    
    tree.column('id', width=70, anchor='center'); tree.column('itinerario', width=380, anchor='w')
    for c in cols[2:]: tree.column(c, width=105, anchor='center')
    
    tree.tag_configure('pari', background='#f8f9fa')
    for idx, row in enumerate(table_rows):
        tag = 'pari' if idx % 2 == 0 else ''
        tree.insert('', tk.END, values=row, tags=(tag,))
        
    scrollbar = ttk.Scrollbar(tab_tabella, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscroll=scrollbar.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    notebook.select(tab_profilo)
    aggiorna_stato(f"Analisi completata. Punto più alto: {nome_gpm} a {quota_max:.1f} m.")


def esci_programma():
    """Chiude l'applicazione interrompendo i thread della mappa in modo pulito"""
    global map_widget

    # Aggiorna lo stato visivo
    aggiorna_stato("Chiusura componenti in corso...")

    # Verifica se la mappa esiste nel tab e distruggila per bloccare i thread dopo()
    try:
        for widget in tab_mappa.winfo_children():
            if isinstance(widget, tkintermapview.TkinterMapView):
                widget.destroy()  # Questo interrompe i timer asincroni delle piastrelle
    except Exception:
        pass

    # Ora puoi distruggere la finestra principale in sicurezza
    root.quit()
    root.destroy()

# ==========================================
# 5. COSTRUZIONE INTERFACCIA PRINCIPALE
# ==========================================
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Analizzatore Performance Bici")
    root.geometry("1150x750")
    root.minsize(800, 500)
    
    style = ttk.Style()
    style.theme_use('clam')
    
    # Barra dei comandi superiore
    top_bar = ttk.Frame(root, padding="10")
    top_bar.pack(side=tk.TOP, fill=tk.X)
    
    btn_carica = ttk.Button(top_bar, text="Seleziona File e Avvia Analisi Traccia", command=seleziona_e_analizza)
    btn_carica.pack(side=tk.LEFT, padx=5)
    
    btn_esci = ttk.Button(top_bar, text="Chiudi Applicazione", command=esci_programma)
    btn_esci.pack(side=tk.LEFT, padx=5)
    
    lbl_info = ttk.Label(top_bar, text="Parser FIT Avanzato Multicanale con Fault-Tolerance attivo.", font=("Helvetica", 9, "italic"))
    lbl_info.pack(side=tk.LEFT, padx=20)
    
    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    tab_profilo = ttk.Frame(notebook)
    tab_tabella = ttk.Frame(notebook)
    tab_mappa = ttk.Frame(notebook)
    
    notebook.add(tab_profilo, text="  Profilo Altimetrico  ")
    notebook.add(tab_tabella, text="  Tabella Tratti  ")
    notebook.add(tab_mappa, text="  Mappa Percorso  ")
    
    for tab, txt in [(tab_profilo, "Grafico Altimetrico"), (tab_tabella, "Tabella Dati Performance"), (tab_mappa, "Mappa GPS OpenStreetMap")]:
        lbl = ttk.Label(tab, text=f"Nessun dato caricato. Premi il pulsante in alto per generare il {txt}.", font=("Helvetica", 10), foreground="#5f6368")
        lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
    # Variabile e widget della barra di stato inferiore
    status_var = tk.StringVar()
    status_var.set("Pronto. Seleziona un file GPX o FIT per iniziare.")
    
    status_bar = ttk.Frame(root, relief=tk.SUNKEN, padding=(5, 2))
    status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    status_label = ttk.Label(status_bar, textvariable=status_var, font=("Helvetica", 9), foreground="#3c4043")
    status_label.pack(side=tk.LEFT)

    # Intercetta la chiusura standard della finestra (la X in alto a destra)
    root.protocol("WM_DELETE_WINDOW", esci_programma)

    root.mainloop()
