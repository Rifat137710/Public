# Stock Market Prediction with Sentiment Analysis

**Course:** EEE 402 — Artificial Intelligence and Machine Learning Laboratory (January 2025)
**Institution:** Department of EEE, Bangladesh University of Engineering and Technology (BUET)
**Section:** G2 | **Group:** 02
**Full report:** [`EEE402_Project_Report_Group_02.pdf`](EEE402_Project_Report_Group_02.pdf)
**Code:** https://github.com/navin2006190/Stock_market_prediction_with_sentiment_analysis

---

## What this project does

Predicts the daily **closing price of Google (GOOG) stock** by combining two very different
signals: historical price data and the **public mood in financial news headlines**. The premise
is that markets move on sentiment as much as on numbers, so a model that reads the news should
beat one that only reads the ticker.

The pipeline in one line:

> raw news headlines → sentiment score per day → merged with price data + technical indicators →
> sequence model (LSTM / GRU) → next-day closing price

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
