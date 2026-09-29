# CareCost 🏥

> **AI-assisted healthcare cost and care navigation for Indian patients.**  
> Hackathon MVP — estimates are demo data only. Not medical or financial advice.

---

## What it does

| Feature | Details |
|---|---|
| **Cost range** | Estimated procedure cost by city tier and hospital type |
| **Hospital finder** | Nearby hospitals ranked by out-of-pocket cost, with map |
| **Scheme engine** | PM-JAY / Aarogyasri coverage computed per hospital |
| **Insurance** | Cashless coverage on the remaining balance |
| **Quote check** | Validate a hospital quote against the crowd range |
| **Multilingual** | English / Telugu / Hindi UI labels |
| **Voice input** | Web Speech API for the treatment search field |
| **Dark mode** | Persisted in `localStorage` |

---

## Quick start

```bash
# 1. Clone / unzip the project
cd healthcare

# 2. Create a virtual environment (recommended)
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the server
uvicorn app.main:app --reload
```

Open **http://localhost:8000** in your browser.

---

## Run unit tests

```bash
pytest tests/test_engine.py -v
```

Expected output: **12 tests passed** (covering scheme eligibility, coverage caps, and quote validation verdicts).

---

## Project structure

```
healthcare/
├── app/
│   ├── __init__.py
│   ├── main.py        ← FastAPI app + API endpoints
│   ├── estimator.py   ← predict_range() — swap in ML model here
│   ├── schemes.py     ← eligibility rules + quote validator
│   └── geo.py         ← Haversine distance
├── static/
│   ├── index.html     ← Single-page app shell
│   ├── app.js         ← All SPA logic
│   ├── style.css      ← Mobile-first design system
│   └── i18n.json      ← EN / TE / HI translations
├── data/
│   ├── procedures.csv
│   ├── prices.csv
│   ├── schemes.csv
│   └── hospitals.csv
├── tests/
│   └── test_engine.py
├── requirements.txt
└── README.md
```

---

## API reference

### `GET /api/procedures?q=<search>`
Returns a list of procedures. Optional `q` parameter filters by name or keyword.

### `POST /api/estimate`
```json
{
  "procedure_id": "P001",
  "city": "Hyderabad",
  "has_scheme_card": true,
  "insurance_cover_left": 50000,
  "user_lat": 17.38,
  "user_lng": 78.48
}
```
Returns cost range, per-hospital breakdown, best option, and assumptions.

### `POST /api/validate-quote`
```json
{
  "procedure_id": "P001",
  "city": "Hyderabad",
  "quote_amount": 25000
}
```
Returns `verdict` (`below_range` / `fair` / `above_range` / `far_above`) and a plain-language suggestion.

---

## How to replace demo data with real data

All rows with `source = "demo"` are placeholder values.  
To add real data:

### 1. `data/procedures.csv`
Add real procedure names, IDs, and search keywords. Keep the same column schema.

### 2. `data/prices.csv`
Replace or extend rows for actual city tiers and hospital types. Source verified pricing from CGHS rate lists, NHA package rates, or hospital MoUs.

| Column | Notes |
|---|---|
| `city_tier` | 1 = metro, 2 = tier-2, 3 = small town |
| `hospital_type` | `government` / `trust` / `private` / `corporate` |
| `source` | Set to `"real"` to suppress the demo badge |

### 3. `data/schemes.csv`
Update `package_rate` and `max_cover_per_family` from the official NHA / state health authority notifications. Add new schemes by adding rows with a new `scheme_id` and a new `eligibility_rule` string. Then add the rule clause handler in `app/schemes.py → _evaluate_clause()`.

### 4. `data/hospitals.csv`
Replace with real hospital records. Obtain `lat`/`lng` from the hospital's Google Maps listing. Set `nabh=1` only for NABH-accredited facilities. List all applicable `scheme_ids` (comma-separated, no spaces).

### 5. Upgrade the price model
`app/estimator.py → predict_range()` is designed to be swapped out.  
Replace the CSV lookup with a call to a scikit-learn quantile regression model while keeping the same function signature:

```python
def predict_range(prices_df, *, procedure_id, city, hospital_type) -> dict | None:
    # Load your trained model and call model.predict(...)
    return {"low": ..., "mid": ..., "high": ..., "city_tier": ..., "source": "real"}
```

---

## Eligibility rule extensions

Rules in `data/schemes.csv → eligibility_rule` use AND-joined plain-English clauses.  
To add a new clause (e.g. `age_above_60`):

1. Add the clause string to the relevant rows in `schemes.csv`.
2. Add a matching `elif clause == "age_above_60":` branch in `app/schemes.py → _evaluate_clause()`, accepting whatever new input fields you need.
3. Pass the new field from the API endpoint in `app/main.py`.

---

## Disclaimer

> These estimates are based on demo CSV data. They are **not** verified prices, **not** medical advice, and **not** financial advice. Always confirm actual costs with the treating hospital before making any decisions.
