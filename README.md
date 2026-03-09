# RRG Analyzer — JdK Methodology

Implementazione fedele del modello Excel `RRG_S_P500_Sectors_JdK.xlsx`.

## Pipeline matematica (JdK_Calcoli)

| Step | Formula | Excel row |
|------|---------|-----------|
| RS_raw | `Settore / Benchmark` | 2+ |
| EMA12 seed | `AVERAGE(B2:B13)` | 13 |
| EMA12 prop | `prev + (2/13)*(curr - prev)` | 14+ |
| EMA26 seed | `AVERAGE(C13:C38)` | 38 |
| RS_s prop | `prev + (2/27)*(ema12 - prev)` | 39+ |
| RS-Ratio | `100 * RS_s(t) / AVERAGE(RS_s[38:t])` | 89+ |
| RS-Momentum | `100 * Ratio(t) / AVERAGE(Ratio[t-13:t])` | 102+ |

## Deploy su Streamlit Cloud

```bash
git init && git add . && git commit -m "Initial"
git remote add origin https://github.com/USERNAME/rrg-analyzer.git
git push -u origin main
# share.streamlit.io → New app → app.py
```

## Formato input

- **Excel**: carica il file con foglio `Input_Prezzi` (col A=date, B=benchmark, C+=settori)
- **CSV**: rilevamento automatico separatore `;`,`,` e decimali `,`,`.`
