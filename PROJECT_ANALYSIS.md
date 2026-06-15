# Project Analysis: Billboard Info Extraction Pipeline

## Purpose

This project extracts business information from storefront/signboard images and exports structured results to Excel.

Target business fields:

- `image_name`
- `shop_name`
- `address`
- `phone_number`
- `website_links`
- `open_hours`

## Current Architecture

The repository already has most of the expected `src/` module structure:

```text
.
├── main.py
├── requirements.txt
├── data/
└── src/
    ├── __init__.py
    ├── models.py
    ├── ocr.py
    ├── extractor.py
    ├── search.py
    ├── enricher.py
    ├── exporter.py
    └── pipeline.py
```

### Entry Point

`main.py:6` calls:

```python
run_pipeline(data_dir=Path("data"), output_path=Path("output/results.xlsx"))
```

There is currently no CLI argument parsing. Configuration is mostly through environment variables.

### Module Responsibilities

| Module | Current responsibility |
|---|---|
| `src/ocr.py` | Lists image files and runs PaddleOCR. Handles some PaddleOCR output shapes and HEIF/HEIC fallback via `pillow-heif`. |
| `src/extractor.py` | Sends OCR text to Ollama with `format="json"` and parses JSON responses. Also extracts missing fields from search results. |
| `src/search.py` | Performs a single DuckDuckGo text search using a simple query. |
| `src/enricher.py` | Detects missing fields, calls search, asks Ollama to fill missing fields, and merges results. |
| `src/exporter.py` | Converts all `ShopInfo` objects into one DataFrame and writes Excel at the end. |
| `src/pipeline.py` | Orchestrates OCR, extraction, enrichment, and final Excel export. |
| `src/models.py` | Defines `SearchResult` and `ShopInfo` Pydantic models. |

## Module Dependency Graph

```text
main.py
  └── src.pipeline.run_pipeline()
        ├── src.ocr.OCRReader.extract_text()
        │     └── PaddleOCR
        ├── src.extractor.OllamaExtractor.extract_from_ocr()
        │     ├── ollama.chat()
        │     └── src.models.ShopInfo
        ├── src.search.DuckDuckGoSearcher.search()
        │     ├── duckduckgo_search.DDGS
        │     └── src.models.SearchResult
        ├── src.enricher.ShopInfoEnricher.enrich_if_needed()
        │     ├── src.search.DuckDuckGoSearcher
        │     ├── src.extractor.OllamaExtractor.extract_missing_from_search()
        │     └── src.models.ShopInfo
        └── src.exporter.export_to_excel()
              ├── pandas
              └── src.models.ShopInfo
```

## Current Data Flow

```text
data/*.jpg/png/...
  ↓
OCRReader.extract_text(image_path)
  ↓
OCR text
  ↓
OllamaExtractor.extract_from_ocr(ocr_text, source_image)
  ↓
ShopInfo with extracted fields
  ↓
ShopInfoEnricher.enrich_if_needed(ShopInfo)
  ↓
DuckDuckGoSearcher.search(shop_name, address)
  ↓
OllamaExtractor.extract_missing_from_search(...)
  ↓
Merged ShopInfo
  ↓
records.append(ShopInfo)
  ↓
export_to_excel(records, output/results.xlsx)
```

## Existing Strengths

1. **Module split exists**  
   The project is already divided into OCR, extraction, search, enrichment, export, pipeline, and models.

2. **Pydantic models are present**  
   `src/models.py` uses Pydantic `BaseModel`, field normalization, and a helper for missing enrichment fields.

3. **Structured logging is used**  
   Each module has a module logger, and the pipeline configures basic logging.

4. **OCR output parsing is tolerant**  
   `src/ocr.py:_extract_text_lines()` handles nested dictionaries, tuples, and lists from different PaddleOCR result shapes.

5. **LLM JSON parsing has recovery behavior**  
   `src/extractor.py` attempts normal JSON parsing, fenced JSON extraction, first JSON object extraction, and one repair pass.

6. **Search failures do not crash the whole pipeline**  
   `src/search.py` catches DuckDuckGo exceptions and logs them.

7. **Runtime cache paths are configured**  
   `src/pipeline.py:_configure_runtime_paths()` sets Paddle cache and temp directories under `output/`.

## Existing Weaknesses

### 1. Search Quality

Current search is too simple:

- `src/search.py:17` builds one query: `shop_name + address`.
- It does not generate targeted queries for:
  - official website
  - Facebook page
  - Google Maps
  - opening hours
  - phone number
- It does not prefer official sources.
- It returns only the first `max_results` raw results.
- It does not rank or filter results before passing them to the LLM.

The enrichment prompt in `src/extractor.py:40` also lacks explicit instructions for official-source priority and source ranking.

### 2. Reliability and Memory Usage

`src/pipeline.py:50` stores every result in memory:

```python
records: list[ShopInfo] = []
```

`src/pipeline.py:63` only exports after all images are processed:

```python
export_to_excel(records, output_path)
```

This is not scalable to tens of thousands of images and is not crash-safe.

### 3. No Resume Support

There is no check for existing per-image JSON artifacts. If the process crashes, all completed but unexported work is lost.

Required behavior is missing:

```text
if output/json/<image>.json exists:
    skip processing
unless --force is specified
```

### 4. No Debug Artifacts per Image

The current implementation writes only `output/results.xlsx`. It does not save per-image JSON files containing:

- OCR text
- extracted fields
- search query
- search results
- enrichment results
- final merged result

This makes debugging failed or low-quality extractions difficult.

### 5. Validation Is Incomplete

Current validation only normalizes empty strings and website link lists in `src/models.py`.

Missing validation:

- Vietnamese phone number validation
- URL validation
- malformed address rejection
- open-hour pattern validation/normalization

Examples of expected open hours:

- `07:00-18:00`
- `08:00 - 22:00`

### 6. Export Contract Mismatch

The requested Excel field is `image_name`, but `src/models.py:63` exports `source_image`.

### 7. Configuration Mismatch

`src/extractor.py:18` defaults to model `"qwen3"`, while `src/pipeline.py:34` defaults to environment variable `OLLAMA_MODEL` with fallback `"qwen3:4b"`.

### 8. Exception Handling Is Too Broad

`src/pipeline.py:60` catches all exceptions and logs them, but failed records are not persisted. This makes it hard to distinguish:

- OCR failure
- LLM failure
- search failure
- enrichment failure
- export failure

### 9. No Tests

There are no visible unit tests for:

- validators
- search query generation/ranking
- JSON persistence
- resume behavior
- CSV append
- Excel conversion

## Technical Debt

1. **End-to-end export coupling**  
   Excel export depends on holding all records in memory.

2. **No persistence abstraction**  
   JSON saving, CSV append, and final Excel conversion should be separated from pipeline orchestration.

3. **Search and enrichment are tightly coupled to raw result formatting**  
   Search quality improvements require changes in both search and enrichment.

4. **Validation is embedded only in normalization**  
   Business rules should be explicit, testable, and preferably separated from model normalization.

5. **No CLI layer**  
   `main.py` hardcodes data and output paths. Adding `--force`, output directory, model, OCR language, and search count requires CLI support.

6. **Generated/runtime files are mixed with source files**  
   `output/` currently contains cache, temp files, and final artifacts. The refactor should make output structure explicit.

## Bugs and Risks

1. **Data loss on crash**  
   Because results are only exported at the end, a crash loses all in-memory records.

2. **No resume means repeated expensive work**  
   OCR and Ollama calls will be repeated even for images already processed.

3. **Poor enrichment recall**  
   One generic query is unlikely to find Facebook pages, official websites, or opening hours.

4. **Invalid data can be exported**  
   Phone numbers, URLs, addresses, and open hours are not validated against business rules.

5. **Excel may be overwritten only after full run**  
   Existing `output/results.xlsx` is not safely updated until all images complete.

6. **Search failures are silent in final output**  
   Search exceptions are logged but not represented in per-image artifacts.

7. **Model defaults are inconsistent**  
   Extractor and pipeline defaults can diverge.

## Recommended Improvements

### Architecture

Add explicit persistence and validation modules:

```text
src/
├── models.py
├── ocr.py
├── extractor.py
├── search.py
├── enricher.py
├── exporter.py
├── pipeline.py
├── validation.py
└── persistence.py
```

Recommended responsibilities:

- `validation.py`: field validators for phone, URL, address, and open hours.
- `persistence.py`: per-image JSON writing, CSV append, resume checks, final Excel conversion.
- `exporter.py`: CSV-to-Excel conversion and export row formatting.
- `pipeline.py`: orchestration only.

### Data Flow After Refactor

```text
image path
  ↓
resume check: output/json/<image>.json exists?
  ↓ yes
load existing result and append CSV row
  ↓ no
OCR
  ↓
Extract
  ↓
Validate
  ↓
Missing fields?
  ↓ yes
Generate targeted search queries
  ↓
Search DuckDuckGo
  ↓
Rank official sources
  ↓
Enrich with Ollama
  ↓
Validate final fields
  ↓
Save per-image JSON
  ↓
Append CSV row
  ↓
next image

After all images:
  ↓
Convert CSV → Excel
```

### Search Improvements

Generate multiple queries using both shop name and address:

- exact business query
- business + address
- business + city/province if detectable
- business + Facebook
- business + official website
- business + opening hours
- business + Google Maps

Rank results by source priority:

1. Official website
2. Official Facebook page
3. Google Maps
4. Other reputable directories
5. General snippets

Pass ranked results and source-priority instructions to the enrichment prompt.

### Resume and Crash Safety

Use stable filenames:

```text
output/json/<image_stem>.json
```

Behavior:

- Without `--force`: skip existing JSON files.
- With `--force`: overwrite existing JSON files.
- Save JSON immediately after processing each image.
- Append CSV immediately after JSON save.
- Convert CSV to Excel after the full run.

### Validation Rules

Recommended rules:

- Phone:
  - Accept Vietnamese mobile and landline patterns.
  - Normalize spaces, dots, parentheses, and country code.
- Website:
  - Require valid URL scheme and domain.
  - Normalize `http://`/`https://`.
  - Reject JavaScript/data URLs.
- Address:
  - Reject very short values.
  - Reject values that look like phone numbers, URLs, or pure OCR noise.
  - Prefer values containing Vietnamese address signals when present.
- Open hours:
  - Accept `HH:MM-HH:MM`.
  - Accept `HH:MM - HH:MM`.
  - Normalize spacing around dashes.

## Refactor Plan

1. Add `src/validation.py`.
2. Add `src/persistence.py`.
3. Update `src/models.py` for export/debug serialization and validation integration.
4. Improve `src/search.py` with query generation and source ranking.
5. Improve `src/extractor.py` prompts for higher-quality enrichment.
6. Update `src/enricher.py` to use ranked search results and preserve search/enrichment artifacts.
7. Update `src/exporter.py` to append CSV rows and convert CSV to Excel.
8. Refactor `src/pipeline.py` to stream processing, resume, save JSON, append CSV, and avoid storing all records.
9. Update `main.py` with CLI arguments.
10. Add tests for validation, persistence/resume, search query generation/ranking, and export helpers.

## Verification Plan

Run these checks after implementation:

```bash
python -m compileall src main.py
```

Run the pipeline on the small sample dataset:

```bash
python main.py --force
```

Verify:

- `output/json/*.json` files are created.
- Each JSON contains OCR, extracted fields, search query/results, enrichment results, and final result.
- Rerunning without `--force` skips existing images.
- Rerunning with `--force` reprocesses images.
- `output/results.csv` appends rows immediately.
- `output/results.xlsx` is generated from CSV at the end.
- Phone, URL, address, and open-hour validation rejects obviously invalid values.
