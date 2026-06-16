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

The project uses a modular `src/` layout. The OCR stage has been removed from the active pipeline and replaced with a VLM-first Ollama extractor using `qwen2.5vl:3b`.

```text
.
├── main.py
├── PROJECT_ANALYSIS.md
├── requirements.txt
├── data/
└── src/
    ├── __init__.py
    ├── models.py
    ├── image_utils.py
    ├── extractor.py
    ├── search.py
    ├── enricher.py
    ├── exporter.py
    ├── pipeline.py
    ├── persistence.py
    └── images.py
```


### Entry Point

`main.py` defines CLI argument parsing.

Current CLI:

```bash
python main.py
python main.py --force
python main.py --data-dir data --output-path output/results.xlsx
```

Important arguments:

- `--data-dir`: image input directory.
- `--output-path`: final Excel output path.
- `--force`: reprocess images even if `output/json/<image>.json` already exists.

### Module Responsibilities

| Module | Current responsibility |
|---|---|
| `src/images.py` | Lists supported image files from the data directory. |
| `src/image_utils.py` | Prepares images for Ollama VLM calls. Supported formats pass through; HEIF/HEIC images are converted to cached PNG files under `output/converted_images/`. |
| `src/extractor.py` | Sends prepared images directly to Ollama using `qwen2.5vl:3b`, requests JSON-only business extraction, parses/repairs JSON, and keeps the raw VLM response. |
| `src/search.py` | Performs DuckDuckGo text search for enrichment and stores the last query used. |
| `src/enricher.py` | Detects missing fields, calls DuckDuckGo, asks Ollama to fill missing fields from search results, merges results, and records search/enrichment debug metadata. |
| `src/exporter.py` | Builds export rows, appends rows to CSV, writes legacy in-memory Excel export, and converts CSV to Excel. |
| `src/persistence.py` | Per-image JSON persistence, failure records, CSV append, and CSV rebuild from JSON. |
| `src/pipeline.py` | Orchestrates VLM image extraction, resume checks, JSON saving, CSV append, CSV rebuild, and final Excel conversion. |
| `src/models.py` | Defines `SearchResult` and `ShopInfo` Pydantic models, including `raw_response`, search queries, and enrichment results. |

## Module Dependency Graph

```text
main.py
  └── src.pipeline.run_pipeline()
        ├── src.images.list_images()
        ├── src.image_utils.prepare_image_for_vlm()
        ├── src.extractor.OllamaExtractor.extract_from_image()
        │     ├── ollama.chat()
        │     └── src.models.ShopInfo
        ├── src.search.DuckDuckGoSearcher.search()
        │     ├── duckduckgo_search.DDGS
        │     └── src.models.SearchResult
        ├── src.enricher.ShopInfoEnricher.enrich_if_needed()
        │     ├── src.search.DuckDuckGoSearcher
        │     ├── src.extractor.OllamaExtractor.extract_missing_from_search()
        │     └── src.models.ShopInfo
        ├── src.persistence.PersistenceManager
        │     ├── src.exporter.shop_info_to_export_row()
        │     └── json/csv file writes
        └── src.exporter.convert_csv_to_excel()
              ├── pandas
              └── output/results.csv
```

## Current Data Flow

```text
data/*.jpg/png/...
  ↓
for each image:
  resume check: output/json/<image>.json exists?
  ↓ yes
  skip image unless --force
  ↓ no
  prepare image for VLM
      ↓ supported: use original
      ↓ HEIF/HEIC: convert/cache PNG under output/converted_images/
  ↓
  VLM extraction with Ollama qwen2.5vl:3b
  ↓
  Validate/parse JSON
  ↓
  Enrich missing fields if needed
      ↓
      DuckDuckGo search
      ↓
      Ollama extraction from search results
  ↓
  Save per-image JSON immediately
  ↓
  Append CSV row immediately
  ↓
next image

After all images:
  ↓
Rebuild output/results.csv from output/json/*.json
  ↓
Convert output/results.csv → output/results.xlsx
```

The pipeline no longer stores all `ShopInfo` objects in memory. It returns a lightweight `PipelineSummary`.

## VLM Extraction Details

### Model

Default model:

```text
qwen2.5vl:3b
```

The pipeline allows overriding with:

```bash
OLLAMA_MODEL=another-model python main.py
```

### Image Preparation

`src/image_utils.py` prepares images before they are sent to Ollama.

Supported VLM image formats pass through unchanged:

- `.png`
- `.jpg`
- `.jpeg`
- `.webp`

HEIF/HEIC images are converted to PNG:

- `.heif`
- `.heic`

Converted PNG files are saved under:

```text
output/converted_images/
```

Behavior:

- If the image is already supported and is not HEIF/HEIC by file signature, `prepare_image_for_vlm()` returns the original path.
- If the image is HEIF/HEIC by extension or HEIF file signature, it converts to PNG using Pillow and `pillow-heif`.
- If the PNG already exists and is non-empty, it reuses the cached PNG.
- If conversion fails, it raises `ImagePreparationError`.
- The pipeline catches preparation failures, logs them, saves a failure JSON record, skips that image, and continues.

The extractor validates the prepared image before sending it to Ollama:

```python
image_for_model = prepare_image_for_vlm(image_path)
validate_prepared_image(image_for_model)
```

### Ollama Call Style

The active extractor uses the official Python Ollama package:

```python
from ollama import chat

response = chat(
    model=self.model,
    messages=[user_content],
    format="json",
    options={"temperature": 0},
)
```

For image extraction, the user message includes:

```python
user_content["images"] = [str(image_path)]
```

### VLM Prompt

`src/extractor.py` defines `VLM_EXTRACTION_PROMPT`. It instructs the model to:

- Extract business information from the storefront image.
- Return JSON only.
- Use the required schema:
  - `shop_name`: null
  - `address`: null
  - `phone_number`: null
  - `website_links`: []
  - `open_hours`: null
- Do not hallucinate.
- Use null for missing scalar fields and [] for missing website links.
- Extract all visible phone numbers.
- Extract all visible URLs.
- Extract Facebook pages if visible.
- Extract the most complete visible address.
- Extract opening hours only if visible.

## Per-Image JSON Schema

Successful per-image JSON files are saved under:

```text
output/json/<image_stem>.json
```

Required top-level fields:

```json
{
  "image_name": "...",
  "model": "qwen2.5vl:3b",
  "raw_response": "...",
  "parsed_result": {},
  "final_result": {}
}
```

Current success JSON also includes:

- `search_queries`
- `search_results`
- `enrichment_results`
- `export_row`

Failure JSON includes:

- `processing_status`
- `created_at`
- `image_name`
- `source_image`
- `failed_stage`
- `error_type`
- `error_message`
- `traceback`

## Existing Strengths

1. **Modular design**  
   OCR, image listing, extraction, search, enrichment, export, persistence, and pipeline orchestration are separated.

2. **VLM-first extraction**  
   The main pipeline sends images directly to Ollama instead of running PaddleOCR first.

3. **HEIF/HEIC image preparation**  
   The pipeline now converts unsupported HEIF/HEIC images to cached PNG files before sending them to Qwen2.5VL.

4. **Pydantic models are present**  
   `src/models.py` uses Pydantic `BaseModel`, field normalization, and helper methods for business/export fields.

4. **Structured logging is used**  
   Each module has a module logger, and the pipeline configures basic logging.

5. **LLM JSON parsing has recovery behavior**  
   `src/extractor.py` attempts normal JSON parsing, fenced JSON extraction, first JSON object extraction, and one repair pass.

6. **Search failures do not crash the whole pipeline**  
   `src/search.py` catches DuckDuckGo exceptions and logs them.

7. **Reliability is improved**  
   The pipeline saves per-image JSON immediately, appends CSV rows immediately, skips existing JSON files unless `--force` is passed, and converts CSV to Excel at the end.

8. **Debug artifacts are supported**  
   Successful per-image JSON files include raw VLM response, parsed result, final result, search queries/results, enrichment results, and export row.

9. **Failed per-image records are persisted**  
   Failure JSON records the failed stage, error type, message, and traceback.

## Current Weaknesses

### 1. Obsolete OCR File Removed

The obsolete OCR module has been deleted. The active pipeline no longer imports or uses OCR, and source-level OCR references are gone.

### 2. Old Output Artifacts Still Contain OCR Data

Existing files under `output/json/` and `output/.paddlex_cache/` were created by the previous OCR pipeline. They may still contain `ocr_text` and PaddleOCR cache data.

Recommended cleanup:

- Run `python main.py --force` to overwrite `output/json/*.json` with VLM results.
- Optionally delete `output/.paddlex_cache/` after confirming it is no longer needed.

### 3. Search Quality Still Needs Work

Current search remains simple:

- `src/search.py` builds one query: `shop_name + address`.
- It does not generate targeted queries for:
  - official website
  - Facebook page
  - Google Maps
  - opening hours
  - phone number
- It does not prefer official sources.
- It returns only the first `max_results` raw results.
- It does not rank or filter results before passing them to the LLM.

The enrichment prompt now says "web search results" and prefers official sources, but the search module itself still needs query generation and ranking.

### 4. Resume Support

Resume support is implemented.

Current behavior:

- JSON path is derived from image stem at `src/persistence.py`.
- Pipeline skips existing JSON files unless `--force` is passed.
- `main.py` exposes `--force`.

Current resume flow:

```text
if output/json/<image>.json exists and --force is false:
    skip VLM/search
else:
    process image
    save output/json/<image>.json
    append output/results.csv
```

Skipped records are included in the final CSV because the pipeline rebuilds CSV from all JSON files.

Remaining resume risks:

- If an existing JSON file is corrupted, the current pipeline will still skip it rather than repairing it.
- If two different images have the same stem but different extensions, the current filename strategy could collide.
- Resume does not currently load the existing JSON result into memory for immediate CSV append; it relies on the final CSV rebuild.

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

### 6. Export Contract

The Excel export uses the requested fields:

```python
[
    "image_name",
    "shop_name",
    "address",
    "phone_number",
    "website_links",
    "open_hours",
]
```

`src/models.py` builds the export row from `Path(self.source_image).name`.

### 7. Exception Handling

Per-image exceptions are caught and persisted as failure JSON.

Current behavior:

- `src/pipeline.py` catches exceptions per image.
- `src/persistence.py` saves failure JSON with stage and traceback.
- The pipeline continues to the next image.

Remaining concern:

- Export-time failures outside the per-image loop can still stop the final CSV/Excel conversion.

### 8. No Tests

There are no visible unit tests for:

- VLM extractor prompt/call construction
- JSON parsing/repair
- JSON persistence
- resume behavior
- CSV append
- CSV rebuild
- Excel conversion
- validators, once added
- search query generation/ranking, once improved

## Technical Debt

1. **Persistence and export are separated but coupled enough for CSV rebuild**  
   `src/persistence.py` imports `src.exporter.shop_info_to_export_row()` and `EXPORT_COLUMNS`.

2. **Search and enrichment are tightly coupled to raw result formatting**  
   Search quality improvements still require changes in both search and enrichment.

3. **Validation is embedded only in normalization**  
   Business rules should be explicit, testable, and preferably separated into `src/validation.py`.

4. **CLI is minimal**  
   The CLI supports data directory, output path, and `--force`, but not model, max search results, or other runtime options.

5. **Generated/runtime files are mixed with source files**  
   `output/` contains cache, temp files, JSON, CSV, and Excel artifacts. The structure is clearer now but still not isolated from the repository root.

6. **No test infrastructure**  
   The project has no test runner, fixtures, or mocked VLM/search tests.

## Bugs and Risks

1. **Potential duplicate CSV rows during interrupted runs**  
   CSV append happens immediately, but duplicates are corrected only when the final CSV rebuild runs.

2. **Corrupted JSON can block resume**  
   Existing JSON files are treated as completed records. Corrupted JSON is not detected before skip.

3. **Filename collision risk**  
   JSON filenames use image stem. Two images with the same stem but different extensions could collide.

4. **Poor enrichment recall remains**  
   One generic DuckDuckGo query is unlikely to find Facebook pages, official websites, or opening hours.

5. **Invalid data can be exported**  
   Phone numbers, URLs, addresses, and open hours are not validated against business rules.

6. **Search failures are debug-visible but not semantically classified**  
   Search exceptions are logged and no-result enrichment is recorded, but there is no structured search error field yet.

7. **Old OCR artifacts may confuse inspection**  
   Existing `output/json/*.json` and `output/.paddlex_cache/` files are from the old pipeline and may still contain OCR text.

## Recommended Improvements

### Architecture

Current architecture after the VLM migration:

```text
src/
├── models.py
├── images.py
├── extractor.py
├── search.py
├── enricher.py
├── exporter.py
├── pipeline.py
└── persistence.py
```

Recommended next modules:

```text
src/validation.py
```

Recommended responsibilities:

- `validation.py`: field validators for phone, URL, address, and open hours.
- `persistence.py`: per-image JSON writing, failure records, CSV append, CSV rebuild from JSON.
- `exporter.py`: CSV-to-Excel conversion and export row formatting.
- `pipeline.py`: orchestration only.

### Data Flow After VLM Migration

```text
image path
  ↓
resume check: output/json/<image>.json exists?
  ↓ yes
skip unless --force
  ↓ no
VLM extraction with Ollama qwen2.5vl:3b
  ↓
Parse/validate JSON
  ↓
Missing fields?
  ↓ yes
Search DuckDuckGo
  ↓
Enrich with Ollama
  ↓
Save per-image JSON
  ↓
Append CSV row
  ↓
next image

After all images:
  ↓
Rebuild CSV from JSON
  ↓
Convert CSV → Excel
```

Validation is still missing from this flow.

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

Current behavior:

- JSON path: `output/json/<image_stem>.json`
- Without `--force`: skip existing JSON files.
- With `--force`: overwrite existing JSON files.
- Save JSON immediately after processing each image.
- Append CSV immediately after JSON save.
- Rebuild CSV from JSON at the end.
- Convert CSV to Excel after the full run.

Recommended hardening:

- Validate JSON before skipping.
- Use collision-resistant filenames, for example stem plus short hash.
- Keep a small processing manifest if CSV deduplication before final rebuild is required.
- Clean old OCR JSON/cache artifacts after migration.

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

## Migration Summary

Completed:

1. Added `src/images.py` for image listing.
2. Replaced `src/extractor.py` with a VLM-first Ollama extractor.
3. Added `src/image_utils.py` for HEIF/HEIC-to-PNG preparation and caching.
4. Updated extractor to use `from ollama import chat`.
4. Set default model to `qwen2.5vl:3b`.
5. Added reusable VLM prompt constant.
6. Updated `ShopInfo` to store `raw_response` instead of `ocr_text`.
7. Updated `src/persistence.py` to save VLM JSON with `image_name`, `model`, `raw_response`, `parsed_result`, and `final_result`.
8. Updated `src/pipeline.py` to prepare images and call `extract_from_image()` instead of OCR.
9. Removed PaddleOCR/PaddlePaddle from `requirements.txt` and added Pillow/pillow-heif for image preparation.
10. Added `scripts/test_vlm_image_preparation.py`.
11. Preserved resume, CSV append, CSV rebuild, and Excel export behavior.

Remaining:

1. Optionally clean old OCR output artifacts.
2. Add `src/validation.py`.
3. Improve DuckDuckGo search query generation and source ranking.
4. Add tests for VLM extraction, persistence/resume, and export helpers.

## Verification Plan

Run:

```bash
python3 -m compileall src main.py
```

Verify active source files:

```bash
grep -RInE "paddle|OCR|ocr|ocr_text|OCRReader" src main.py requirements.txt --exclude=ocr.py
```

Expected: no output from active source files.

Run the image-preparation test script on one HEIF/HEIC image:

```bash
.venv/bin/python scripts/test_vlm_image_preparation.py path/to/image.heic
```

Run a forced sample if Ollama is available:

```bash
python3 main.py --force
```

Verify:

- `src/pipeline.py` no longer imports or initializes OCR.
- `src/extractor.py` prepares images with `prepare_image_for_vlm()` before calling `ollama.chat`.
- HEIF/HEIC images are converted to `output/converted_images/*.png`.
- `src/extractor.py` sends `images=[str(image_for_model)]` to Ollama.
- Default model is `qwen2.5vl:3b`.
- JSON files contain `image_name`, `model`, `raw_response`, `parsed_result`, and `final_result`.
- Resume skips existing `output/json/<image>.json` unless `--force`.
- Excel export still contains only the required six business columns.
- Old OCR JSON/cache artifacts are either overwritten by `--force` or cleaned separately.
