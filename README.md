# DiseaseNet

A bioinformatics web application that maps human diseases to their associated genes, receptors, ligands, and drug compounds — pulling live data from KEGG, UniProt, and PubChem.

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-green)
![SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey)

---

## Overview

DiseaseNet lets you type any human disease name and get back a detailed table of genes involved in that disease's pathways, with protein annotations, receptor/ligand classification, associated drug compounds, and links to 3D protein structures.

Developed as part of the **Databases and Web Design** course in the MSc Bioinformatics for Health Sciences programme at **Universitat Pompeu Fabra (UPF) / Universitat de Barcelona**, 2025–2027.

**Authors**: Austin Gilbride · Brigita Medelyte · Revanth Naidu

---

## Features

- Fuzzy disease name search with autocomplete and "Did you mean?" suggestions
- Browse the full KEGG disease catalogue (~3000 diseases) via a searchable modal
- Real-time progress bar as gene data is fetched (Server-Sent Events)
- Results table: gene symbol, protein name, functional role, receptor/ligand status, drug compounds, PDB structure links
- Export results to CSV
- User accounts (sign up / log in) with per-user search history
- Recent searches shown on the home page (last 3)

---

## Quick Start

### Prerequisites

- Python 3.9 or higher
- pip

### Install

```bash
pip install -r requirements.txt
```

### Run (development)

```bash
python app.py
```

On Windows you can also double-click `run.bat`.

Open your browser at: `http://127.0.0.1:5000`

### Run (production)

```bash
gunicorn -c gunicorn.conf.py wsgi:app
```

---

## Usage

1. Type a disease name in the search bar (e.g. `Breast cancer`, `Type 2 diabetes`)
2. Pick a suggestion from autocomplete, or hit **Search**
3. Watch the real-time progress as gene data loads
4. Explore the results table — hover a row to see full text, click PDB IDs to open structures
5. Click **Export CSV** to download the data
6. Sign up / log in to save your search history

---

## Project Structure

```
diseasenet/
├── app.py                  # Flask routes and server logic
├── backend.py              # Data-fetching pipeline (KEGG → UniProt → PubChem)
├── wsgi.py                 # Gunicorn WSGI entry point
├── gunicorn.conf.py        # Gunicorn configuration
├── run.bat                 # Windows dev launcher
├── requirements.txt        # Python dependencies
├── db/
│   ├── __init__.py         # SQLAlchemy db instance
│   └── models.py           # User and UserSearch ORM models
├── instance/
│   └── diseasenet.db       # Main SQLite database (users table)
├── templates/
│   ├── index.html          # Main single-page UI
│   └── auth.html           # Login / Sign-up page
├── static/
│   └── images/             # Logo, background
├── uploads/                # Temp files (gitignored)
└── outputs/                # Generated CSV exports (gitignored)
```

---

## Data Sources

| Source | What we use it for |
|--------|--------------------|
| **KEGG** | Disease → pathway associations; gene IDs in each pathway (via KGML) |
| **UniProt** | Protein name, functional description, receptor/ligand keywords, PDB IDs |
| **PubChem** | Gene → compound bioactivity data; drug compound names |

---

## Output Table Columns

| Column | Description |
|--------|-------------|
| Gene | HGNC gene symbol |
| Protein Name | Full protein name from UniProt |
| Functional Role | Biological function from UniProt (expandable) |
| Receptor / Ligand | Classification from UniProt keywords |
| Drug Compounds | Bioactive compounds from PubChem |
| PDB IDs | Clickable links to RCSB Protein Data Bank |

---

## How It Works

### 1. Disease Search and Fuzzy Matching

The user types a disease name. As they type, the frontend calls `/suggest` which uses **rapidfuzz** (`WRatio` scorer) to match the input against the full KEGG disease list cached in memory. If the exact search returns no KEGG match, a "Did you mean?" page is shown with the top scored candidates.

The user can also click **Browse Diseases** to open a modal with the full list of ~3000 KEGG diseases, filterable by typing.

### 2. Real-Time Streaming (SSE)

When the user submits a search, the browser opens a **Server-Sent Events** connection to `/stream`. The Flask backend launches a background thread that runs the full pipeline and pushes two types of events back to the browser:

- `progress` — `{ current, total, gene }` — updates the progress bar
- `result` — the complete JSON table data (or an error)

This avoids HTTP timeouts and lets the user see progress in real time.

### 3. KEGG Pathway Lookup

The backend calls:
1. `http://rest.kegg.jp/find/disease/<name>` — find the KEGG disease ID
2. `http://rest.kegg.jp/link/pathway/<disease_id>` — get all pathways linked to this disease, filtered to human (`hsa`) pathways
3. `http://rest.kegg.jp/get/<pathway_id>/kgml` — fetch the KGML (XML) for each pathway

### 4. Gene Extraction and Deduplication

KGML is parsed with `xml.etree.ElementTree`. Gene nodes are extracted by their `name` attribute (e.g. `hsa:1956`), resolved to HGNC symbols via KEGG gene lookup.

Deduplication happens at two levels:
- **Intra-pathway**: a `seen` set inside `parse_kgml()` prevents duplicate entries within a single pathway.
- **Inter-pathway**: a `seen_symbols` set in `build_gene_receptor_ligand_table()` ensures each gene symbol appears only once across all pathways.

### 5. Parallel Gene Annotation

For each unique gene symbol, three external APIs are queried in parallel using `ThreadPoolExecutor` (5 workers):

- **UniProt**: `https://rest.uniprot.org/uniprotkb/search?query=gene:<symbol>+AND+organism_id:9606` — returns protein name, function, keywords (receptor/ligand), and PDB cross-references
- **PubChem Gene lookup**: `https://pubchem.ncbi.nlm.nih.gov/rest/pug/gene/symbol/<symbol>/aids/JSON` — returns assay IDs linked to the gene
- **PubChem Compound names**: resolves assay IDs to compound names via the PUG REST API

Results from all three are merged into one row per gene.

### 6. User Accounts and History

Passwords are hashed with **bcrypt**. The main `diseasenet.db` stores the `users` table. Each user also gets their own SQLite file at `instance/users/<username>.db` containing a `user_search` table — this keeps search histories isolated per user without polluting the main database.

The `/history` endpoint reads the user's own DB and returns the last 50 searches.

### 7. CSV Export

The frontend POSTs the current table data (as JSON) to `/export_csv`. The backend writes it to a CSV file in `outputs/` and returns it as a file download.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Home page |
| GET | `/stream?disease_name=...&disease_id=...` | SSE stream: progress + results |
| POST | `/process` | Non-streaming search (JSON) |
| POST | `/suggest` | Fuzzy disease name suggestions |
| GET | `/diseases` | Full KEGG disease list (cached in memory) |
| GET | `/diseases/clear` | Clear the in-memory disease list cache |
| GET | `/diseases/debug` | Debug KEGG connectivity |
| GET | `/recent_searches` | Last 3 searches (session-global) |
| GET | `/history` | Current user's search history (requires login) |
| POST | `/export_csv` | Download results as CSV |
| GET/POST | `/login` | Login |
| GET/POST | `/signup` | Sign up |
| GET | `/logout` | Logout |

---

## Dependencies

```
flask==3.0.0
flask-sqlalchemy==3.1.1
requests==2.31.0
bcrypt==4.1.2
rapidfuzz==3.9.7
gunicorn==21.2.0
```

---

## Notes

- All external APIs (KEGG, UniProt, PubChem) are free and require no authentication.
- Search time is typically 15–60 seconds depending on the number of pathways and genes.
- SQLite is used for simplicity; switching to MySQL/PostgreSQL requires only changing the `SQLALCHEMY_DATABASE_URI` in `app.py`.
- The production server must use Gunicorn with `gthread` workers (not the default `sync` worker) to support SSE streaming.
