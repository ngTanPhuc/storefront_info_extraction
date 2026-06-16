# Storefront Information Extraction

This project reads photos of storefronts and creates a spreadsheet with the business information found in each photo.

## What the project does

For each image, the project:

1. Looks for the main/primary business in the photo.
2. Reads visible information from that business sign or storefront.
3. If important details are missing, it searches the web for extra information.
4. Saves a detailed result file for each image.
5. Creates a final Excel spreadsheet and CSV file.

The final spreadsheet contains these columns:

| Column | Meaning |
|---|---|
| `image_name` | Name of the input image |
| `shop_name` | Business/shop name |
| `address` | Address found from the image or web search |
| `phone_number` | Phone number found from the image or web search |
| `website_links` | Website/Facebook links found |
| `open_hours` | Opening hours found |

Important: this is an automated helper, not a perfect manual check. Please review the final Excel file before using the information.

## What you need

You need:

- Python installed on your computer
- Ollama installed and running locally
- A vision-language model downloaded in Ollama
- Internet connection for web-search enrichment
- A folder of storefront images

Supported image types:

- `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, `.tiff`, `.webp`
- `.heic` and `.heif` images are converted automatically to PNG before processing

The project currently uses `gemma4:latest` as the default Ollama model. You can also use another vision model, I recommend `qwen3vl:32b` for the best accuracy (but this will also require strong PC).

## Folder structure

```text
storefront_info_extraction/
├── data/                         # Put your input storefront images here
├── output/                       # Results are saved here
│   ├── json/                     # Detailed result for each image
│   ├── *.csv                     # Spreadsheet data in CSV format
│   └── *.xlsx                    # Final Excel file
├── scripts/                      # Helper scripts
├── src/                          # Program code
├── main.py                       # Main program file
└── requirements.txt              # Python packages needed by the project
```

For normal use, you mostly need to care about:

- `data/` — where your input images go
- `output/` — where results are saved
- `main.py` — the file you run

## Install this project

First, in your terminal, clone this project from GitHub:

```bash
git clone https://github.com/ngTanPhuc/storefront_info_extraction.git
cd storefront_info_extraction
```

Then create a Python environment:

```bash
python -m venv .venv
```

Activate the environment.

On macOS/Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate
```

Install the Python packages:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `python` does not work, try `python3` instead.

## Install and start Ollama

Install Ollama from:

https://ollama.com

Then install the default model:

```bash
ollama pull gemma4:latest
```

Or install another vision model, for example:

```bash
ollama pull qwen3vl:32b
```

Start Ollama if it is not already running. On most computers, Ollama runs automatically in the background after installation.

## Prepare your images

Put your storefront images in the `data/` folder.

Example:

```text
data/
├── shop_001.jpg
├── shop_002.png
└── shop_003.heic
```

You can also keep your images somewhere else and tell the program where to find them when you run it.

## Run the project

Run the program:

```bash
python main.py
```

By default, it reads images from:

```text
data/
```

and writes the final Excel file to:

```text
output/results.xlsx
```

It also creates:

```text
output/results.csv
output/json/
```

## Run with a custom input folder and output file

If your images are in another folder, use `--data-dir`.

If you want a different output file, use `--output-path`.

Example:

```bash
python main.py --data-dir my_images --output-path output/my_results.xlsx
```

## Use a different Ollama model

The default model is `gemma4:latest`.

To use a different model, set `OLLAMA_MODEL` before running the program.

Example with `qwen3vl:32b`:

```bash
OLLAMA_MODEL=qwen3vl:32b python main.py --output-path output/qwen3vl-32b/results.xlsx
```

On Windows PowerShell:

```powershell
$env:OLLAMA_MODEL="qwen3vl:32b"
python main.py --output-path output/qwen3vl-32b/results.xlsx
```

Make sure you already downloaded the model:

```bash
ollama pull qwen3vl:32b
```

## Re-run images

The project saves detailed JSON results for each image. If you run the program again without `--force`, it skips images that already have a result. This makes re-runs faster.

To reprocess all images from the beginning, use:

```bash
python main.py --force
```

Use `--force` when:

- You changed the model
- You changed the program
- You want to update old results
- Some previous results look wrong

## Test HEIC/HEIF image conversion

If you want to test one `.heic` or `.heif` image, run:

```bash
python scripts/test_vlm_image_preparation.py path/to/image.heic
```

The converted PNG will be saved under:

```text
output/converted_images/
```

## Where to find results

After the program finishes, open the final Excel file from the `output/` folder.

Example:

```text
output/qwen3vl-32b/results.xlsx
```

The matching CSV file is in the same folder:

```text
output/qwen3vl-32b/results.csv
```

Detailed per-image results are saved as JSON files:

```text
output/qwen3vl-32b/json/
```

## Common problems

### Ollama model not found

Run:

```bash
ollama pull gemma4:latest
```

Or install the model you are using, for example:

```bash
ollama pull qwen3vl:32b
```

### Ollama connection error

Make sure Ollama is installed and running.

You can usually test it with:

```bash
ollama list
```

### No images were processed

Check that your images are inside the folder you passed to `--data-dir`, or inside the default `data/` folder.

Also make sure the file extensions are supported.

### Web search does not add missing information

The project uses DuckDuckGo search when fields are missing. If the web search cannot find reliable information, the field may stay empty.

### Results look wrong

Try these steps:

1. Check the original image quality.
2. Make sure the main business sign is clear.
3. Try a stronger vision model, such as `qwen3vl:32b`.
4. Re-run with `--force`.

Example:

```bash
OLLAMA_MODEL=qwen3vl:32b python main.py --output-path output/qwen3vl-32b/results.xlsx --force
```

## Simple workflow

1. Put images in `data/`.
2. Install Python packages.
3. Install Ollama and download the model.
4. Run:

   ```bash
   python main.py
   ```

5. Open the Excel file in `output/`.
6. Review the results before using them.
