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
💻 Istruzioni di Installazione ed Esecuzione
🪟 Su Windows
Opzione 1: Esecuzione standard con Python
Scaricare o copiare il file datibici.0.0.11.py in una cartella locale.

Aprire il Prompt dei comandi (cmd) o PowerShell in quella cartella.

Installare le dipendenze lanciando:

DOS
pip install numpy pandas scipy matplotlib geopy tkintermapview gpxpy fitparse
Avviare l'applicazione:

DOS
python datibici.0.0.11.py
Opzione 2: Creazione di un Eseguibile indipendente (.exe)
Per distribuire il programma su PC che non hanno Python installato, è possibile generare un file .exe stand-alone usando PyInstaller:

Installare il pacchetto di compilazione: pip install pyinstaller

Generare l'eseguibile monolitico senza console testuale di sfondo:

DOS
pyinstaller --noconsole --onefile datibici.0.0.11.py
Al termine del processo, l'applicazione finale compilata si troverà all'interno della cartella dist/datibici.0.0.11.exe.

🐧 Su Linux (Ubuntu / Debian / Fedora)
Le distribuzioni Linux spesso distribuiscono Python senza il modulo grafico tkinter di default. È fondamentale installarlo tramite il gestore pacchetti di sistema prima di procedere.

Opzione 1: Esecuzione da terminale
Aprire il terminale e installare le dipendenze di sistema e Python:

Bash
# Per distribuzioni basate su Debian/Ubuntu/Mint:
sudo apt update
sudo apt install python3-tk python3-pip -y

# Per distribuzioni basate su Fedora/RHEL:
sudo dnf install python3-tkinter python3-pip -y
Installare i moduli Python richiesti:

Bash
pip3 install numpy pandas scipy matplotlib geopy tkintermapview gpxpy fitparse
Avviare l'interfaccia grafica:

Bash
python3 datibici.0.0.11.py
Opzione 2: Compilazione in Binario Nativo Linux
Installare PyInstaller: pip3 install pyinstaller

Compilare lo script:

Bash
pyinstaller --noconsole --onefile datibici.0.0.11.py
Il file binario compilato nativo per Linux sarà disponibile nella cartella dist/.

🎯 Guida all'Utilizzo del Software
Caricamento File: Cliccare sul pulsante "Seleziona File e Avvia Analisi Traccia" e scegliere un file .gpx o .fit.

Impostazione Sensibilità: Verrà mostrato un pop-up che richiede la tolleranza in metri di dislivello (Default: 15).

Inserimento Titolo: Fornire un titolo personalizzato per l'uscita (verrà stampato nell'intestazione del grafico).

Navigazione Tab:

Profilo Altimetrico: Mostra l'andamento altimetrico colorato per pendenza e il cartello del GPM.

Tabella Tratti: Mostra la griglia ordinata dei segmenti con la VAM, i Watt medi e la FC media.

Mappa Percorso: Visualizza la mappa stradale interattiva con la traccia e i marker geografici del culmine.

Chiusura Pulita: Utilizzare il pulsante dedicato "Chiudi Applicazione" o la classica X della finestra. Il codice intercetta l'uscita distruggendo preventivamente i widget cartografici per prevenire eccezioni asincrone (after script di tkintermapview) in console.

📄 Licenza e Note Legali
Copyright (C) 2026 Daniele Drago

Sito Web di riferimento: dandrago@altevista.org

Codice rilasciato per scopi scientifici, di studio geologico-geomorfologico e di analisi atletica personale.
