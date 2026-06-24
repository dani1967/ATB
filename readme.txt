---

### 2. File: `README.txt` (Formato Testo Semplice)

```text
=========================================================================
ANALIZZATORE PERFORMANCE BICI (V8.6) - NOTE OPERATIVE DI INSTALLAZIONE
=========================================================================
Copyright (C) 2026 Daniele Drago <dandrago@altevista.org>
Riferimento Script: datibici.0.0.11.py
-------------------------------------------------------------------------

1. REQUISITI DI SISTEMA
------------------------
Il programma richiede l'installazione di Python 3.8 (o superiore) e dei 
seguenti pacchetti esterni necessari per il calcolo matematico, l'analisi 
dei file cartografici e il disegno dell'interfaccia grafica:

numpy, pandas, scipy, matplotlib, geopy, tkintermapview, gpxpy, fitparse


2. PROCEDURA DI INSTALLAZIONE ED ESECUZIONE
-------------------------------------------

A) SU WINDOWS:
   1. Aprire il prompt dei comandi (cmd) nella cartella dello script.
   2. Installare le librerie necessarie digitando il comando:
      pip install numpy pandas scipy matplotlib geopy tkintermapview gpxpy fitparse
   
   3. Avviare l'applicazione con il comando:
      python datibici.0.0.11.py

   *NOTA - COMPILAZIONE (.EXE):
   Se si desidera creare un pacchetto autonomo senza dover installare Python 
   su altri PC, installare pyinstaller ("pip install pyinstaller") e lanciare:
   pyinstaller --noconsole --onefile datibici.0.0.11.py
   Il file finale sarà generato dentro la sottocartella "dist".

B) SU LINUX (Ubuntu / Debian / Linux Mint):
   1. Aprire il terminale e installare l'estensione grafica tkinter di sistema
      (spesso assente di default su Linux) e l'installatore pip:
      sudo apt update
      sudo apt install python3-tk python3-pip -y

   2. Installare le librerie Python digitando:
      pip3 install numpy pandas scipy matplotlib geopy tkintermapview gpxpy fitparse

   3. Eseguire l'applicazione:
      python3 datibici.0.0.11.py

   *NOTA - COMPILAZIONE BINARIO LINUX:
   La compilazione può essere fatta tramite PyInstaller anche su Linux usando:
   pyinstaller --noconsole --onefile datibici.0.0.11.py


3. LOGICA DI FUNZIONAMENTO E PARAMETRI UTENTE
----------------------------------------------
- Filtro Altimetrico: Applica un filtro Savitzky-Golay (polyorder=2) per 
  stabilizzare i dati barometrici o GPS riducendo il rumore di fondo.
- Parametro Sensibilita': Definisce la tolleranza in metri di dislivello 
  per l'algoritmo Douglas-Peucker. Valori bassi (5-10 mt) mostrano i micro-cambi 
  di pendenza collinari; valori alti (15-20 mt) isolano i grandi passi montani.
- Rilevamento GPM: Calcola automaticamente il culmine altimetrico assoluto 
  della traccia, applicando un marcatore sul profilo grafico e un marker 
  cartografico ("⛰️ CULMINE") sulla mappa stradale.
- Tolleranza di rete (TR): Gestione automatica del Geocoding su OpenStreetMap. 
  In caso di latenza o problemi temporanei dei server di rete (timeout), per 
  preservare la larghezza e la pulizia visiva delle colonne della tabella, 
  la località viene contrassegnata con l'identificativo breve "(TR)".
- Chiusura Sicura: Il software gestisce in modo sicuro l'evento di distruzione 
  della GUI (sia da pulsante che da "X" del sistema operativo), disattivando 
  preventivamente i thread asincroni delle immagini tile di tkintermapview per 
  evitare crash del gestore "after" nel terminale.

-------------------------------------------------------------------------
Fine documento.
