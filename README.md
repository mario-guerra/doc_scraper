# Documentation Scraper

A Python script that scrapes documentation pages and converts them to markdown format for AI processing.

## Features

- 🔗 **Smart Link Extraction**: Follows content links while ignoring header/footer navigation
- 🎯 **Content Focused**: Automatically identifies and extracts main content areas
- 📝 **Clean Markdown**: Converts HTML to well-formatted markdown
- 🖼️ **Image Downloads**: Automatically downloads and embeds images locally
- 🔒 **Security Conscious**: Follows OWASP recommendations with input validation
- ⏱️ **Respectful Scraping**: Built-in delays between requests
- 🎨 **Customizable**: Configurable selectors and output options
- ⚡ **JavaScript Support**: Handles dynamic content with Selenium (scrape_docs_dynamic.py)
- 🏢 **Confluence Cloud Support**: Auto-detects Atlassian Confluence URLs and uses the REST API for fast, reliable extraction

## Installation

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

Or install manually:

```bash
pip install requests beautifulsoup4 html2text lxml selenium
```

2. For JavaScript support (Selenium), you'll also need Chrome/Chromium browser installed.

## Usage

### Two Versions Available

1. **`scrape_docs.py`** - Fast, static HTML scraping (no JavaScript)
2. **`scrape_docs_dynamic.py`** - Handles JavaScript-rendered content (uses Selenium)

### Basic Usage

**For static HTML sites:**
```bash
python scrape_docs.py https://docs.example.com/guide
```

**For JavaScript-heavy sites (like Microsoft Learn):**
```bash
python scrape_docs_dynamic.py https://learn.microsoft.com/collections/xyz
```

This will:
1. Load the page at the given URL
2. Find all content links (excluding header/footer links)
3. Scrape each linked page
4. Download all images and save them in `scraped_docs/images/`
5. Save each page as a markdown file in `scraped_docs/` with local image references

### Advanced Options

**Custom output directory:**
```bash
python scrape_docs_dynamic.py https://docs.example.com/guide --output-dir my_docs
```

**Add custom exclude selectors:**
```bash
python scrape_docs_dynamic.py https://docs.example.com/guide \
  --exclude-selector ".sidebar" \
  --exclude-selector "#toc"
```

**Adjust delay between requests (be respectful!):**
```bash
python scrape_docs_dynamic.py https://docs.example.com/guide --delay 2.0
```

**Disable JavaScript support (faster):**
```bash
python scrape_docs_dynamic.py https://docs.example.com/guide --no-selenium
```

**Show browser window (for debugging):**
```bash
python scrape_docs_dynamic.py https://docs.example.com/guide --no-headless
```

**Disable image downloads (faster, smaller output):**
```bash
python scrape_docs_dynamic.py https://docs.example.com/guide --no-images
```

### Command Line Options

```
positional arguments:
  url                   The base URL to start scraping from

optional arguments:
  -h, --help            Show help message
  -o, --output-dir DIR  Directory to save markdown files (default: scraped_docs)
  -e, --exclude-selector CSS
                        CSS selector for elements to exclude (can be used multiple times)
  -d, --delay SECONDS   Delay between requests in seconds (default: 1.0)
```

### Confluence Cloud

Both scrapers **auto-detect** Confluence Cloud URLs (`*.atlassian.net/wiki/...`) and switch to the Confluence REST API automatically. This is faster and more reliable than scraping the rendered React UI.

**Scrape a Confluence space from a Table of Contents page:**
```bash
python scrape_docs.py https://mysite.atlassian.net/wiki/spaces/DOC/pages/123456/Table+of+Contents \
  --cookie-file cookies.txt \
  --output-dir my_docs
```

**Scrape a single Confluence page:**
```bash
python scrape_docs_dynamic.py https://mysite.atlassian.net/wiki/spaces/DOC/pages/123456/My+Page \
  --cookie-file cookies.txt \
  --single-page
```

The Confluence API support:
- Extracts page content via the REST API (`/wiki/rest/api/content/`)
- Follows internal page links (`ac:link` / `ri:page` references)
- Downloads image attachments from Confluence pages
- Converts Confluence storage-format HTML to clean markdown
- Works with both `scrape_docs.py` and `scrape_docs_dynamic.py`

> **Note:** Confluence Cloud requires authentication. Export your browser cookies to a `cookies.txt` file — see the [Cookie Authentication Guide](COOKIE_AUTHENTICATION_GUIDE.md) for details.

## How It Works

1. **Fetch Base Page**: Loads the starting URL
2. **Extract Links**: Finds all links in the main content area (excluding header/footer/nav)
3. **Filter Links**: Only includes links from the same domain
4. **Scrape Pages**: For each link:
   - Fetches the page
   - Removes header/footer/navigation elements
   - Extracts main content area
   - Converts HTML to markdown
   - Saves with metadata header
5. **Respectful Delays**: Waits between requests to avoid overwhelming servers

## Output Format

Each scraped page is saved as a markdown file with:

- **Filename**: Generated from the URL path (e.g., `/docs/api/auth` → `docs_api_auth.md`)
- **Metadata Header**: Includes source URL and page title
- **Clean Content**: Main content converted to markdown

Example output file:

```markdown
# Source: https://docs.example.com/guide/authentication
# Title: Authentication Guide

---

## Authentication

This guide explains how to authenticate...

![Diagram](images/a1b2c3d4e5f6.png)
```

### Image Handling

**Automatic Image Downloads (Default):**
- All images are automatically downloaded to `scraped_docs/images/`
- Image filenames are generated using MD5 hashes for uniqueness
- Markdown references are updated to point to local files
- Supports: JPG, PNG, GIF, SVG, WebP, BMP
- Data URLs (base64 images) are preserved as-is

**Directory Structure:**
```
scraped_docs/
├── images/
│   ├── a1b2c3d4e5f6.png
│   ├── b2c3d4e5f6g7.jpg
│   └── ...
├── page1.md
├── page2.md
└── ...
```

**Disable Image Downloads:**
```bash
python scrape_docs_dynamic.py <url> --no-images
```

## Default Excluded Elements

By default, the script excludes these CSS selectors:
- `header`
- `footer`
- `nav`
- `.header`
- `.footer`
- `.navigation`

You can add more with the `--exclude-selector` option.

## Tips for Best Results

1. **Start with an index page**: Use a documentation index or table of contents as your starting URL
2. **Check robots.txt**: Ensure you're allowed to scrape the site
3. **Adjust delays**: For large sites, increase the delay to be more respectful
4. **Test first**: Try with a small section before scraping entire documentation
5. **Custom selectors**: If the default exclusions don't work well, add site-specific selectors

## Examples

**Scrape Python docs:**
```bash
python scrape_docs.py https://docs.python.org/3/tutorial/index.html \
  --output-dir python_docs \
  --delay 1.5
```

**Scrape with custom exclusions:**
```bash
python scrape_docs.py https://docs.example.com \
  --exclude-selector ".advertisement" \
  --exclude-selector ".related-links" \
  --exclude-selector "#comments"
```

## Security Features

Following OWASP Top 10 recommendations:

- ✅ Input validation on URLs
- ✅ Timeout on requests (30 seconds)
- ✅ Sanitized filenames (no path traversal)
- ✅ Same-domain restriction (no external link following)
- ✅ User-agent header set
- ✅ No execution of downloaded content

## Troubleshooting

**"Required packages not installed" error:**
```bash
pip install -r requirements.txt
```

**No content extracted / "Found 0 content links":**
- **The page uses JavaScript**: Use `scrape_docs_dynamic.py` instead of `scrape_docs.py`
- Try adding custom exclude selectors for the specific site
- All links might be in header/footer (adjust `--exclude-selector`)
- For collection pages (like Microsoft Learn), you may need to scrape individual article URLs directly

**Selenium/WebDriver errors:**
- Make sure Chrome/Chromium is installed
- Try: `pip install --upgrade selenium`
- On macOS: `brew install chromedriver` (if using Homebrew)

**Rate limiting / blocked:**
- Increase the delay with `--delay`
- Check if the site allows scraping in robots.txt
- Some sites may block automated access

## Use Cases

Perfect for:
- 📚 Creating local copies of documentation for offline use
- 🤖 Preparing documentation for AI/LLM processing
- 📖 Converting web docs to markdown for version control
- 🔍 Building searchable documentation archives

## License

Free to use and modify for your documentation needs.

