Datibici

**Datibici** è un'applicazione desktop in Python progettata per l'analisi, la segmentazione e la visualizzazione di tracce ciclistiche nei formati **GPX** e **FIT** provenienti dai moderni ciclocomputer. Il programma genera mappe interattive, profili altimetrici e ripartizioni fisiologiche del carico per analizzare nel dettaglio le prestazioni.

---

## Come Funziona il Programma (Logica di Elaborazione)

L'applicazione non si limita a mostrare i dati grezzi, ma esegue un flusso di elaborazione e pulizia del tracciato strutturato in diverse fasi:

### 1. Parsing e Normalizzazione dei Dati
* **File GPX:** Estrae le coordinate geometriche (Latitudine, Longitudine), il tempo UTC e l'elevazione da ogni punto traccia.
* **File FIT:** Decodifica il formato binario nativo dei dispositivi (es. Garmin, Wahoo), recuperando oltre ai dati geografici anche i record dei sensori accoppiati: **Potenza (Watt)**, **Frequenza Cardiaca (bpm)** e **Cadenza (rpm)**.

### 2. Filtraggio Geometrico e Altimetrico
I dati GPS contengono spesso errori di campionamento e "rumore" dovuto alla perdita di segnale. Per ovviare a questo:
* Le coordinate mancanti o errate vengono corrette tramite interpolazione lineare.
* La distanza tra i punti viene calcolata matematicamente tramite la **formula dell'Haversine** (distanza ortodromica sulla sfera terrestre).
* Il profilo altimetrico viene ripulito applicando un **filtro di Savitzky-Golay (savgol_filter)** di secondo ordine. Questo passaggio è fondamentale per eliminare i micro-denti di sega altimetrici, garantendo un calcolo realistico del dislivello e delle pendenze istantanee.

### 3. Segmentazione Automatica dei Tratti (Douglas-Peucker)
La funzionalità chiave del programma è la suddivisione automatica dell'uscita in tratti omogenei di salita, discesa o pianura. 
L'applicazione utilizza l'algoritmo di **Douglas-Peucker**, un sistema di semplificazione delle linee geometriche. Il programma analizza il profilo altimetrico e individua i "punti di flesso" (i cambi di pendenza più significativi) in base alla tolleranza in metri (Epsilon) impostata dall'utente. Ogni segmento risultante viene poi isolato e analizzato singolarmente.

### 4. Geolocalizzazione Asincrona (Caching)
Per ogni tratto individuato, il programma interroga le API di *Nominatim (OpenStreetMap)* in background (threading dedicato per non bloccare l'interfaccia grafica) per recuperare i nomi delle località di inizio e fine segmento. Per ridurre il consumo di dati e velocizzare i caricamenti successivi, i nomi vengono salvati localmente in un file di cache (`.geonames`) associato alla traccia.

### 5. Calcolo Fisiologico delle Zone di Intensità
In base dei valori di **FTP (Functional Threshold Power)** e **FC Max** inseriti dall'utente, il programma analizza secondo per secondo la traccia e categorizza il tempo speso in 6 zone di potenza (da Recupero Attivo a Capacità Anaerobica) e 5 zone cardiache, mostrando i grafici di ripartizione dello stress allenante.

---

## Prerequisiti

Prima di iniziare, assicurati di avere **Python 3.8 (o superiore)** installato sul tuo sistema.

---

## Installazione e Avvio (Codice Sorgente)

Per eseguire l'applicazione partendo dal codice sorgente, clona il repository (o scarica il file `.py`) e segui i passaggi per il tuo sistema operativo per configurare l'ambiente virtuale e installare le dipendenze tramite `pip`.

### Linux (Ubuntu / Linux Mint)
Apri il terminale e digita:
```bash
# 1. Installa il supporto per gli ambienti virtuali e Tkinter (se non presenti)
sudo apt update
sudo apt install python3-venv python3-tk

# 2. Naviga nella cartella del progetto e crea l'ambiente virtuale
cd /percorso/alla/cartella/datibici
python3 -m venv venv

# 3. Attiva l'ambiente virtuale
source venv/bin/activate

# 4. Aggiorna pip e installa i requisiti
pip install --upgrade pip
pip install pandas matplotlib geopy tkintermapview fitparse scipy numpy pillow

# 5. Avvia l'applicazione
python datibici.0.0.27.py
Windows
Apri il Prompt dei Comandi (cmd) o PowerShell e digita:

DOS
:: 1. Naviga nella cartella del progetto
cd C:\percorso\alla\cartella\datibici

:: 2. Crea l'ambiente virtuale
python -m venv venv

:: 3. Attiva l'ambiente virtuale
venv\Scripts\activate

:: 4. Aggiorna pip e installa i requisiti
python -m pip install --upgrade pip
pip install pandas matplotlib geopy tkintermapview fitparse scipy numpy pillow

:: 5. Avvia l'applicazione
python datibici.0.0.27.py
macOS
Apri il terminale e digita:

Bash
# 1. Naviga nella cartella del progetto
cd /percorso/alla/cartella/datibici

# 2. Crea l'ambiente virtuale
python3 -m venv venv

# 3. Attiva l'ambiente virtuale
source venv/bin/activate

# 4. Aggiorna pip e installa i requisiti
pip install --upgrade pip
pip install pandas matplotlib geopy tkintermapview fitparse scipy numpy pillow

# 5. Avvia l'applicazione
python datibici.0.0.27.py
💡 Nota per le sessioni successive: Ogni volta che riapri il terminale per avviare il programma, ricordati di riposizionarti nella cartella ed eseguire solo il comando di attivazione dell'ambiente virtuale (source venv/bin/activate su Linux/Mac o venv\Scripts\activate su Windows) prima di lanciare lo script.

Creare l'Eseguibile Indipendente
Se desideri generare un pacchetto autonomo (un file eseguibile che non richiede la presenza di Python installato sul computer di destinazione), puoi utilizzare PyInstaller. Il comando deve essere lanciato all'interno del proprio ambiente virtuale attivo.

Installa PyInstaller tramite pip:

Bash
pip install pyinstaller
Genera il pacchetto lanciando il seguente comando:

Bash
pyinstaller --onefile --windowed --hidden-import="PIL._tkinter_finder" --name="Datibici" datibici.0.0.27.py
Dettaglio parametri utilizzati:
--onefile: Comprime l'intero programma e le sue dipendenze in un unico file eseguibile autonomo.

--windowed: Nasconde la finestra del terminale/prompt in background (indispensabile per le applicazioni GUI basate su Tkinter).

--hidden-import="PIL._tkinter_finder": Forza PyInstaller a includere il modulo di backend di Pillow necessario per il corretto caricamento delle immagini e delle mappe all'interno di Tkinter, evitando crash all'avvio dell'eseguibile.

--name="Datibici": Imposta il nome personalizzato del file binario finale.

Al termine del processo, l'applicazione compilata sarà disponibile all'interno della cartella dist/.

Funzionalità Principali
Parsing File Multi-Formato: Supporto nativo per file di allenamento e percorsi in formato .gpx e .fit.

Mappe Interattive: Integrazione con tkintermapview per la visualizzazione dinamica della traccia percorsa.

Menu Tipo Mappa: Menu a tendina dedicato per variare istantaneamente il server cartografico (OpenTopoMap con curve di livello, OpenStreetMap Standard, Waymarked Trails ciclistica, USGS Topo).

Profili Altimetrici Colorati: Grafici avanzati relativi a quota e pendenze generati tramite matplotlib, con colorazione dinamica basata sulla pendenza del tratto (Verde per discesa, Giallo/Arancione per falsopiano e salita leggera, Rosso/Amaranto per salite dure e muri).

Statistiche Descrittive: Analisi puntuale di medie, mediane, valori massimi e minimi di Velocità, VAM (Velocità Ascensionale Media), Potenza e Frequenza Cardiaca.

Esportazione Dati: Funzione per scaricare il report tabellare completo dei tratti in formato .csv (separatore ;) e l'immagine del profilo altimetrico in .png.

