# 🔄 RRG Analyzer

**Relative Rotation Graph** — implementazione della metodologia **JdK (Julius de Kempenaer)** per l'analisi della rotazione settoriale.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

---

## 📊 Cosa fa

Genera un **Relative Rotation Graph (RRG)** interattivo a partire da qualsiasi paniere di titoli/settori con un benchmark di riferimento.

### Pipeline di calcolo (metodologia JdK)

```
Prezzi grezzi
    ↓
RS_raw = Prezzo_settore / Prezzo_benchmark
    ↓
EMA₁₂(RS_raw)  →  EMA₂₆(EMA₁₂) = RS_smoothed
    ↓
Z-score rolling 52 periodi × 10 + 100  →  RS-Ratio   (asse X)
    ↓
Δ(RS-Ratio)  →  Z-score rolling 14 periodi × 10 + 100  →  RS-Momentum  (asse Y)
```

### I 4 quadranti

| Quadrante | RS-Ratio | RS-Momentum | Interpretazione |
|-----------|----------|-------------|-----------------|
| 🟢 **Leading**   | > 100 | > 100 | Sovraperformance con momentum positivo |
| 🟡 **Weakening** | > 100 | < 100 | Sovraperformance in rallentamento |
| 🔴 **Lagging**   | < 100 | < 100 | Sottoperformance con momentum negativo |
| 🔵 **Improving** | < 100 | > 100 | Sottoperformance in recupero |

---

## 🚀 Deploy su Streamlit Cloud

1. **Fork** questo repository su GitHub
2. Vai su [share.streamlit.io](https://share.streamlit.io)
3. Clicca **"New app"** → seleziona il tuo fork
4. **Main file path**: `app.py`
5. Clicca **Deploy**

---

## 💻 Esecuzione locale

```bash
# Clona il repo
git clone https://github.com/TUO_USERNAME/rrg-analyzer.git
cd rrg-analyzer

# Installa dipendenze
pip install -r requirements.txt

# Avvia
streamlit run app.py
```

L'app sarà disponibile su `http://localhost:8501`

---

## 📁 Formato file

Il file (XLSX o CSV) deve avere:
- **Prima colonna**: Date (qualsiasi formato riconoscibile)
- **Seconda colonna**: Benchmark (es. S&P 500)
- **Colonne successive**: Prezzi di chiusura dei titoli/settori

Esempio:

| Date       | SP500    | Tech     | Finance  | Energy   |
|------------|----------|----------|----------|----------|
| 2022-01-07 | 4677.03  | 1234.56  | 567.89   | 234.56   |
| 2022-01-14 | 4662.85  | 1198.44  | 554.21   | 241.33   |

Frequenze supportate: **daily**, **weekly**, **monthly** (con resampling automatico).

---

## ⚙️ Parametri configurabili

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| EMA Corta | 12 | Periodi prima EMA (su RS_raw) |
| EMA Lunga | 26 | Periodi seconda EMA (su EMA₁₂) |
| Z-score Window | 52 | Finestra rolling per normalizzazione RS-Ratio |
| Momentum Window | 14 | Finestra rolling per RS-Momentum |

---

## 🛠 Stack tecnico

- **Python 3.10+**
- **Streamlit** — interfaccia web
- **Plotly** — grafico RRG interattivo
- **Pandas / NumPy** — calcoli numerici
- **OpenPyXL** — lettura file Excel

---

## 📄 Licenza

MIT License — libero utilizzo, modifica e distribuzione.
