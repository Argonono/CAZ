# CareAtZero

**Free & low-cost care. Know where to go.**

CareAtZero helps people who don't have health insurance find **free or low-cost** doctors, dentists, eye care and mental-health help near them.

Try it: **https://careatzero.streamlit.app**

Made by Arjun Manne for the 2026 Congressional App Challenge.

---

## What it does

1. **Pick what you need:** Medical, Dental, Vision or Mental health.
2. **Tell it where you are:** it can find you, or you type a ZIP code.
3. **See places near you,** best match first, with:
   - the cost: **Free**, **Sliding scale** (you pay less if you earn less) or **Ask the clinic**
   - how far away it is
   - what to bring and how to get in
   - buttons to **call**, **get directions**, **add to calendar** or **save the info**
4. **See free pop-up clinics:** big free events (dental, eye exams, check-ups) that happen for a day or two.

It does not ask for your name or health problems, and it does not save anything about you.

## Where the information comes from

The app gets fresh information from official public lists:

| Source | What it gives us |
|---|---|
| HRSA (U.S. government) | Community health centers (sliding scale) |
| NC Department of Health | Free clinics, dental clinics, health departments |
| SAMHSA FindTreatment.gov (U.S. government) | Mental-health and addiction help |
| Remote Area Medical | Free pop-up clinics |
| U.S. Census Bureau | Where each ZIP code is on the map |

**Our rules:**
- A place is called **Free** only if its source says it is free.
- Every result shows **where the information came from** and **when it was checked**.
- If a source is down, the app says so. It never makes up information.

## How it works (the short version)

1. The app **downloads** the lists above and **remembers** them for 6 hours, so searches are fast.
2. It **keeps** places that offer the care you picked and are close to you.
3. It gives each place a **score out of 100**, using cost, how soon you can go, distance and more.
4. It **shows** the best matches first, and explains why each one matched.

If a list can't be downloaded, the app uses the last copy it has, or a saved copy in `data/snapshots/`, and labels it with its date.

See the picture: [`docs/architecture.png`](docs/architecture.png)

## Run it on your computer

You need **Python 3.11 or newer**.

```
pip install -r requirements.txt
python -m streamlit run app.py
```

Then open http://localhost:8501 in your browser.

**Check the data sources** (and refresh the saved copies):

```
python tools/check_live_sources.py
```

**Run the tests:**

```
pip install pytest
python -m pytest -q
```

## What's inside

| Folder or file | What it is |
|---|---|
| `app.py` | Home screen |
| `pages/` | Find, Details, Help and About screens |
| `live/` | Downloads the official lists, and remembers them |
| `scoring/` | The score out of 100 |
| `utils/` | Location, dates and time zones, looks, calendar file |
| `components/` | Finds your location in the browser |
| `database/`, `data/` | A small built-in backup list, and saved copies |
| `docs/` | The "install on your phone" page and the architecture picture |
| `tests/` | Automatic checks that the app works |
| `tools/` | Script that checks the data sources |

## Tools I used

- **Python**: the programming language
- **Streamlit**: turns Python into a website and phone app
- **Folium / OpenStreetMap**: the map
- **SQLite**: the small built-in backup list
- **pytest**: automatic tests
- **GitHub** and **Streamlit Community Cloud**: to store the code and put the app online
- **GitHub Pages**: the "install on your phone" page

**AI tools:** I used AI coding assistant Anthropic's Claude to help with parts of this project: the phone-style screen design, connecting the live data sources, finding and fixing bugs, and writing tests. I planned the app, made the design decisions, and tested everything myself.

## Safety

CareAtZero is **not** medical advice.
**In an emergency, call 911.** For a mental-health crisis, **call or text 988.**
