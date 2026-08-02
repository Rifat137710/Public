# Stock Market Prediction with Sentiment Analysis

**Course:** EEE 402 — Artificial Intelligence and Machine Learning Laboratory (January 2025)
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** G2 | **Group:** 02
**Full report:** [`EEE402_Project_Report_Group_02.pdf`](EEE402_Project_Report_Group_02.pdf)

---

## What this project does

- **Predicts Google's daily closing price from two very different signals at once** — historical
  price data and the public mood in financial news headlines — testing whether a model that reads
  the news beats one that only reads the ticker.
- **Built the pipeline end to end:** raw headlines → per-day sentiment score → merged with OHLC
  prices and technical indicators → windowed sequence model → next-day closing price.
- **Recovered a malformed dataset before anything else could run.** The Kaggle news file packs
  multiple headlines and dates onto single lines, so it was parsed line-by-line with regular
  expressions to rebuild date–headline pairs, then stripped of byte-string artefacts (`b'...'`,
  `\n`, `\r`). Scores were averaged per day so one sentiment value aligns with one trading row.
- **Engineered ten technical indicators** on top of raw prices — MA7, MA20, EMA, MACD with signal
  line, 20-day standard deviation, upper/lower Bollinger Bands, RSI-14, SMA-14 and log momentum —
  supplying trend, momentum and volatility context, with windowed framing to stop the RNNs
  overfitting.
- **Benchmarked properly rather than reporting one number.** LSTM and GRU were each trained across
  **four feature configurations**, with and without windowing, and compared against Random Forest,
  Linear Regression, XGBoost and a plain ANN, using manual hyperparameter search over units,
  batch size, learning rate and epochs, plus early stopping.
- **Result — GRU won at R² = 0.9515** (MAE 0.0769, MSE 0.0102) on all extracted features. Its
  simpler two-gate design trains faster on fewer parameters and generalises better at this dataset
  size, where stock data carries short-to-mid-term trends rather than long-range dependencies.
- **Result — sentiment measurably helped.** Adding the sentiment feature lifted the windowed LSTM
  from **R² 0.6984 → 0.8894** — the clearest single piece of evidence that news mood carries real
  predictive signal here.
- **Result — sequence models beat everything else outright.** Linear Regression, Random Forest,
  XGBoost and the ANN treat each day as independent, so they cannot learn momentum and produce
  flat or over-smoothed predictions that miss real market movement.
- **Result — the honest limitation.** No perfectly correlated dataset pair existed: prices are
  Google-specific while the sentiment corpus covers tech-sector news broadly, and **both end in
  2016**, so the trained model is not usable for present-day forecasting.

## Pipeline

1. **Data collection** — News headlines from the Kaggle *stocknews* / `RedditNews.csv` dataset
   (2008–2016); matching Google price history pulled with the `yfinance` library over the exact
   same period.
2. **Text cleaning** — The raw news file is malformed (multiple headlines and dates per line), so
   it is parsed line-by-line with regular expressions to recover date–headline pairs, then
   stripped of byte-string artefacts (`b'...'`, `\n`, `\r`).
3. **Sentiment scoring** — Each headline is scored for polarity (−1 to +1). Scores are averaged
   per day so that one sentiment value aligns with one trading row.
4. **Feature engineering** — Technical indicators added on top of OHLC prices: MA7, MA20, EMA,
   MACD (+ signal line), 20-day standard deviation, upper/lower Bollinger Bands, RSI-14, SMA-14,
   and log momentum. These supply trend, momentum, and volatility context, and the windowed
   framing prevents the RNNs from overfitting.
5. **Modelling** — LSTM and GRU trained in four feature configurations (primary only; primary +
   sentiment; additional indicators; all features), with Random Forest, Linear Regression,
   XGBoost, and a plain ANN as baselines.
6. **Tuning** — Manual hyperparameter search over units, batch size, learning rate, and epochs,
   with early stopping as a callback.

> **Note on the sentiment tool:** the report describes both **VADER** (rule-based, NLTK) and
> **TextBlob** — VADER is presented in the design chapter, while the implementation and design
> justification sections state TextBlob was used for the final polarity scores.

## Results

Evaluated with MAE, MSE, and R² on held-out data (values shown as *without windowing & with windowing*):

| Feature set | LSTM (R²) | GRU (R²) |
| --- | --- | --- |
| Primary features only | 0.6598 & 0.6984 | 0.9432 & 0.8166 |
| Primary + sentiment score | 0.6283 & 0.8894 | 0.8905 & 0.8126 |
| Additional (technical) features | 0.8124 & 0.7441 | — |
| **All extracted features** | 0.8926 & 0.8300 | **0.9515** (MAE 0.0769, MSE 0.0102) |

**Takeaways:**

- **GRU was the best model overall** (R² ≈ 0.95). Its simpler two-gate design trains faster,
  needs fewer parameters, and generalises better on a dataset of this size — stock data carries
  short-to-mid-term trends more than long-range dependencies.
- **Adding sentiment helped**, most visibly for the windowed LSTM (R² 0.63 → 0.89).
- **Sequence models clearly beat the rest.** Linear Regression, Random Forest, XGBoost, and the
  ANN treat every day as independent, so they cannot learn momentum and produce flat or
  over-smoothed predictions.

## Main limitation

No perfectly correlated dataset pair existed. The price data is company-specific (Google), while
the sentiment corpus covers technology-sector news broadly — and both end in 2016, so the trained
model is not directly usable for present-day forecasting.

## Future work

Real-time news and social feeds; contextual sentiment models (BERT, RoBERTa) that handle sarcasm;
hybrid LSTM + GRU + CNN architectures; attention mechanisms over time steps; volume and
macroeconomic features; and deployment as a web or mobile app for live predictions.

## Team

Md. Rifat Rahman (2006137) · Md. Shihab Sheikh (2006176) · Orjun Kumar Paul (2006186) ·
Jain Uddin Ahmad (2006187) · Mushfikur Rahman Navin (2006190) · A. M. Mostain Ahmed Sayami (2006193)

**Course instructors:** Dr. Mohammad Ariful Haque (Professor), Akif Hamid (Part-Time Lecturer)
