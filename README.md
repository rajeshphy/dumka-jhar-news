# Dumka Brief

Daily English news brief for Dumka and Jharkhand.

The project collects configurable RSS feeds, including Google News searches, Twitter/X-focused queries, and local-news queries. It filters for today's IST-dated items, groups similar headlines, asks Gemini for a two-section summary, and writes a Jekyll Markdown post under `docs/_posts/`.

## Sections

- `Dumka and Nearby`: up to five significant local points
- `Jharkhand`: up to five significant state-level points
- If there are not enough worthwhile stories, a section may show fewer than five points. It never renders more than five.

Local relevance is ranked in three layers:

1. `Primary local`: Dumka and nearby Dumka blocks
2. `Personal local`: Muri, Silli, Sonahatu, and Rahe
3. `Regional local`: Santhal Pargana and nearby districts

## Local Run

Create `.env` locally:

```bash
DUMKA_API_KEY=your_gemini_key_here
# Optional override. The default is gemini-3.1-flash-lite.
GEMINI_MODEL=gemini-3.1-flash-lite
```

Generate:

```bash
./run.sh generate
```

Run without Gemini:

```bash
./run.sh no-ai
```

Preview locally:

```bash
./run.sh serve
```

## Sources

Edit:

```text
config/sources.yml
```

Add a source under `local` or `state`:

```yml
- name: Example Source
  type: rss
  url: "https://example.com/rss.xml"
```

Useful freshness settings:

```yml
require_ist_today: true
max_age_hours: 30
allow_unknown_dates: false
max_groups_per_section: 8
min_group_score: 2
local_keywords: "dumka,दुमका,basukinath,बासुकीनाथ,deoghar,देवघर"
primary_local_keywords: "dumka,दुमका,basukinath,बासुकीनाथ"
personal_local_keywords: "muri,मुरी,silli,सिल्ली,sonahatu,सोनाहातू,rahe,राहे"
regional_local_keywords: "santhal pargana,deoghar,jamtara,godda,pakur,sahibganj"
state_keywords: "jharkhand,झारखंड,ranchi,रांची,jamshedpur,जमशेदपुर"
public_interest_keywords: "accident,हादसा,court,police,weather,government,recruitment"
low_value_keywords: "campus diary,opinion,celebrity,entertainment,promotion"
exclude_keywords: "horoscope,astrology,photo gallery,viral video,recipe"
```

Each source can also have a scoring weight:

```yml
- name: Google News - Dumka
  type: rss
  weight: 3
  url: "https://news.google.com/rss/search?q=Dumka%20Jharkhand%20news%20when%3A1d&hl=en-IN&gl=IN&ceid=IN:en"
```

Before Gemini runs, the script filters old and irrelevant items, removes excluded topics, groups similar headlines, scores each group, and sends only the top `max_groups_per_section` groups per section. URLs are kept locally for source links but are not sent to Gemini.

Twitter/X is currently represented by a Google News RSS source restricted to `x.com` and `twitter.com`. If you get a stable Nitter/RSS bridge later, add it as another `local` source in the same file.

## GitHub Deployment

1. Push this folder as the root of a repo named `dumka-jhar-news`.
2. Add a GitHub Actions repository secret:

```text
DUMKA_API_KEY
```

3. In GitHub Pages settings, set source to `GitHub Actions`.

The site is configured for:

```text
/dumka-jhar-news
```

## Schedule

The workflow runs at:

- 06:00 IST
- 14:00 IST
- 20:00 IST

Each successful run commits the generated post into `docs/_posts/` and deploys GitHub Pages.
