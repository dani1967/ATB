# Analizzatore Performance Bici 
Un'applicazione desktop stand-alone leggera e intuitiva sviluppata in Python con interfaccia grafica (GUI) per l'analisi avanzata di tracce ciclistiche in formato `.gpx` e `.fit`. 

Il programma elabora i dati altimetrici e planimetrici isolando i singoli tratti tramite criteri geometrici puri, calcola le performance medie (pendenza, VAM, potenza, frequenza cardiaca) e identifica automaticamente il **GPM (Gran Premio della Montagna / Culmine altimetrico)** geolocalizzandolo in tempo reale sulla cartografia.

---

## 🚀 Caratteristiche Principali

- **Parser Multicanale:** Supporto nativo per file GPX e FIT (inclusa la decodifica dei record di posizione geometrica compressi dai ciclocomputer).
- **Segmentazione Intelligente:** Suddivisione dinamica del percorso in tratti omogenei tramite l'algoritmo *Douglas-Peucker* basato sui cambi di pendenza reali e impostabili dall'utente.
- **Profilo Altimetrico Dinamico:** Grafico interattivo generato con Matplotlib e colorato secondo pendenze standardizzate:
  - 🟢 Discesa (`<0%`)
  - 🟡 Falsopiano (`0-3%`)
  - 🟠 Salita (`3-7%`)
  - 🔴 Dura (`7-11%`)
  - 🟤 Muri (`>11%`)
- **Rilevamento e Geolocalizzazione GPM:** Individuazione automatica del picco massimo dell'uscita con marcatore visivo (`^`) sul grafico e marker dedicato (`⛰️ CULMINE`) sulla mappa.
- **Integrazione Cartografica:** Visualizzazione della traccia e dei punti di controllo su mappa interattiva integrata basata su OpenStreetMap (`tkintermapview`).
- **Fault-Tolerance di Rete:** Gestione dei timeout (3 secondi) e gestione dello stato di isolamento. Se il server OpenStreetMap non risponde in tempo, la località viene contrassegnata in tabella con la sigla compatta **(TR)**; in caso di assenza totale di connessione, viene mostrato il tag **Offline**.
- **Interfaccia Asincrona:** Barra di stato inferiore che traccia l'avanzamento dei calcoli e i cicli di interrogazione ai server OSM senza mai congelare la finestra di Windows/Linux.

---

## 🛠️ Logica di Funzionamento ed Algoritmi

1. **Interpolazione e Filtraggio:** I dati grezzi di altitudine vengono puliti e stabilizzati utilizzando un filtro *Savitzky-Golay* (`savgol_filter`) per rimuovere i micro-errori del GPS o del sensore barometrico senza appiattire le cime delle salite.
2. **Douglas-Peucker (Riduzione Traccia):** L'algoritmo riduce la complessità altimetrica della traccia spezzandola solo dove la variazione di pendenza supera la "Sensibilità" (es. 15 metri di dislivello cumulato) inserita dall'utente.
3. **Reverse Geocoding:** Per ogni tratto distribuito, il programma estrae le coordinate di inizio e fine e interroga i server di OpenStreetMap tramite la libreria `geopy` per assegnare i nomi reali dei comuni o delle frazioni attraversate.

---

## 📦 Requisiti di Sistema

Per eseguire il programma da codice sorgente, è necessario **Python 3.8 o superiore** e l'installazione delle seguenti librerie esterne:

```bash
pip install numpy pandas scipy matplotlib geopy tkintermapview gpxpy fitparse
