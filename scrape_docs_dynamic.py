#!/usr/bin/env python3
"""
Dynamic Documentation Scraper - Handles JavaScript-rendered pages.

This enhanced version uses Selenium to handle pages that load content dynamically.
Perfect for modern documentation sites like Microsoft Learn that use JavaScript.

Usage:
    python scrape_docs_dynamic.py <url> [--output-dir <dir>] [--exclude-selector <css>]
"""

import argparse
import hashlib
import mimetypes
import os
import re
import sys
import time
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from typing import Set, List, Dict, Tuple, Optional

try:
    import requests
    from bs4 import BeautifulSoup
    import html2text
except ImportError:
    print("Error: Required packages not installed.")
    print("Please install dependencies:")
    print("  pip install requests beautifulsoup4 html2text selenium")
    sys.exit(1)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Warning: Selenium not installed. Dynamic content will not be available.")
    print("Install with: pip install selenium")


class DynamicDocumentationScraper:
    """Scrapes documentation pages with JavaScript support."""
    
    def __init__(
        self,
        base_url: str,
        output_dir: str = "scraped_docs",
        exclude_selectors: List[str] = None,
        delay: float = 2.0,
        use_selenium: bool = True,
        headless: bool = True,
        download_images: bool = True,
        single_page: bool = False,
        cookies: Optional[str] = None,
        cookie_file: Optional[str] = None
    ):
        """
        Initialize the scraper.
        
        Args:
            base_url: The starting URL to scrape
            output_dir: Directory to save markdown files
            exclude_selectors: CSS selectors for elements to exclude
            delay: Delay between requests in seconds
            use_selenium: Use Selenium for JavaScript rendering
            headless: Run browser in headless mode
            download_images: Download and save images locally
            single_page: If True, only scrape the provided URL (don't follow links)
            cookies: Cookie string in format "name1=value1; name2=value2"
            cookie_file: Path to a file containing cookies (Netscape format or cookie string)
        """
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "images"
        self.exclude_selectors = exclude_selectors or [
            'header', 'footer', 'nav', 
            '.header', '.footer', '.navigation',
            '.cookie-banner', '#cookie-banner',
            '.feedback', '.page-actions',
            # Confluence-specific UI elements to exclude
            '.quick-nav', '.sidebar', '.left-sidebar', '.right-sidebar',
            '.navigation', '.navigation-menu', '.space-menu',
            '.page-header', '.page-actions-wrapper', '.page-metadata',
            '.comments-section', '.labels-list', '.page-history',
            '[data-testid="page-header"]', '[data-testid="navigation"]'
        ]
        self.delay = delay
        self.visited_urls: Set[str] = set()
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.headless = headless
        self.driver = None
        self.download_images = download_images
        self.single_page = single_page
        self.downloaded_images: Dict[str, str] = {}  # URL -> local path mapping
        self.cookies = cookies
        self.cookie_file = cookie_file
        
        # Setup requests session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        
        # Load and apply cookies if provided
        self._load_cookies()
        
        # Configure html2text
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = False
        self.html_converter.body_width = 0
        self.html_converter.single_line_break = False
    
    def _load_cookies(self):
        """Load cookies from string or file and apply to session."""
        cookie_dict = {}
        
        if self.cookie_file:
            # Load from file
            try:
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    cookie_dict = self._parse_cookie_string(content)
                    print(f"✓ Loaded cookies from file: {self.cookie_file}")
            except Exception as e:
                print(f"Warning: Could not load cookies from file: {e}")
        
        if self.cookies:
            # Load from string
            parsed = self._parse_cookie_string(self.cookies)
            cookie_dict.update(parsed)
            print(f"✓ Loaded cookies from command line")
        
        # Apply cookies to requests session
        if cookie_dict:
            for name, value in cookie_dict.items():
                self.session.cookies.set(name, value)
    
    def _parse_cookie_string(self, cookie_string: str) -> Dict[str, str]:
        """
        Parse cookie string in various formats.
        
        Supports:
        - "name1=value1; name2=value2"
        - Netscape format (from browser exports)
        - JSON format
        """
        cookie_dict = {}
        
        if not cookie_string:
            return cookie_dict
        
        # Try parsing as simple cookie string
        try:
            # Remove any leading/trailing whitespace
            cookie_string = cookie_string.strip()
            
            # Check if it's Netscape format (starts with #)
            if cookie_string.startswith('#'):
                # Parse Netscape format
                for line in cookie_string.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            # Netscape format: domain, flag, path, secure, expiration, name, value
                            name = parts[5]
                            value = parts[6]
                            cookie_dict[name] = value
            elif '\t' in cookie_string:
                # Tab-separated format (name, value, ...) - common in browser extensions
                for line in cookie_string.split('\n'):
                    line = line.strip()
                    if line:
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            # First two columns are name and value
                            name = parts[0].strip()
                            value = parts[1].strip()
                            if name and value:
                                cookie_dict[name] = value
            else:
                # Parse simple cookie string format
                for item in cookie_string.split(';'):
                    item = item.strip()
                    if '=' in item:
                        name, value = item.split('=', 1)
                        cookie_dict[name.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: Error parsing cookies: {e}")
        
        return cookie_dict
    
    def _apply_selenium_cookies(self, url: str):
        """Apply cookies to Selenium browser."""
        if not self.driver or not self.session.cookies:
            return
        
        try:
            # Parse domain from URL
            parsed = urlparse(url)
            domain = parsed.netloc
            
            # Add cookies to browser
            for cookie in self.session.cookies:
                try:
                    # Selenium cookie format
                    self.driver.add_cookie({
                        'name': cookie.name,
                        'value': cookie.value,
                        'domain': domain
                    })
                except Exception as e:
                    print(f"    Warning: Could not add cookie {cookie.name}: {e}")
        except Exception as e:
            print(f"Warning: Error applying cookies to browser: {e}")
        
    def setup_selenium(self):
        """Initialize Selenium WebDriver."""
        if not self.use_selenium:
            return False
            
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            print("✓ Selenium WebDriver initialized (JavaScript support enabled)")
            return True
        except WebDriverException as e:
            print(f"Warning: Could not initialize Selenium: {e}")
            print("Falling back to static HTML scraping...")
            self.use_selenium = False
            return False
    
    def cleanup_selenium(self):
        """Close Selenium WebDriver."""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def fetch_page_selenium(self, url: str, wait_time: int = 10) -> BeautifulSoup:
        """Fetch and parse a page using Selenium (handles JavaScript)."""
        try:
            # First load the page to set domain
            self.driver.get(url)
            
            # Apply cookies if we haven't already (first page load)
            if self.session.cookies and not hasattr(self, '_cookies_applied'):
                self._apply_selenium_cookies(url)
                self._cookies_applied = True
                # Reload page with cookies
                self.driver.get(url)
            
            # Wait for page to load - look for common content indicators
            try:
                WebDriverWait(self.driver, wait_time).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                print(f"    Page DOM loaded")
                
                # Wait for Confluence content to load (it loads asynchronously)
                try:
                    # Check if this is a Confluence page
                    is_confluence = self.driver.execute_script(
                        'return window.location.hostname.includes("atlassian.net") || document.querySelector("body").classList.contains("confluence") || document.querySelector(".wiki-content, #wiki-content") !== null'
                    )
                    
                    if is_confluence:
                        print(f"    Detected Confluence page, waiting for content to load...")
                        # Wait for content with longer timeout
                        max_wait = 20
                        start_time = time.time()
                        content_found = False
                        
                        while time.time() - start_time < max_wait:
                            # Check for content
                            has_content = self.driver.execute_script("""
                                const content = document.querySelector('.wiki-content, #wiki-content, .wiki-content-view, [data-testid="page-content"], .confluence-content, .wiki-body');
                                return content && content.innerText.trim().length > 100;
                            """)
                            
                            if has_content:
                                print(f"    ✓ Content loaded after {int(time.time() - start_time)} seconds")
                                content_found = True
                                break
                            
                            time.sleep(0.5)
                        
                        if not content_found:
                            print(f"    ⚠️  Content not found after {max_wait} seconds, proceeding anyway")
                        
                        # Additional wait for any remaining dynamic content
                        time.sleep(2)
                    else:
                        print(f"    Not a Confluence page, standard wait")
                        time.sleep(2)
                        
                except Exception as e:
                    print(f"    Warning during content wait: {e}")
                    # If JavaScript fails, just wait a bit longer
                    time.sleep(3)
            except TimeoutException:
                print(f"  Warning: Page load timeout for {url}")
            
            # Get the rendered HTML
            page_source = self.driver.page_source
            return BeautifulSoup(page_source, 'html.parser')
            
        except WebDriverException as e:
            print(f"  Error fetching {url} with Selenium: {e}")
            return None
    
    def fetch_page_static(self, url: str) -> BeautifulSoup:
        """Fetch and parse a page using requests (static HTML only)."""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            print(f"  Error fetching {url}: {e}")
            return None
    
    def fetch_page(self, url: str) -> BeautifulSoup:
        """Fetch page using appropriate method."""
        if self.use_selenium and self.driver:
            return self.fetch_page_selenium(url)
        else:
            return self.fetch_page_static(url)
    
    def extract_content_links(self, soup: BeautifulSoup, page_url: str) -> List[str]:
        """Extract content links, excluding header/footer links."""
        # Create a copy to work with
        soup_copy = BeautifulSoup(str(soup), 'html.parser')
        
        # Remove excluded elements
        for selector in self.exclude_selectors:
            for element in soup_copy.select(selector):
                element.decompose()
        
        # Find all remaining links
        links = []
        base_domain = urlparse(self.base_url).netloc
        
        for link in soup_copy.find_all('a', href=True):
            href = link['href']
            
            # Skip anchor links and javascript
            if href.startswith('#') or href.startswith('javascript:'):
                continue
            
            absolute_url = urljoin(page_url, href)
            parsed = urlparse(absolute_url)
            
            # Only include links from the same domain
            if parsed.netloc == base_domain:
                # Remove fragments and query parameters
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if clean_url not in links and clean_url != page_url:
                    links.append(clean_url)
        
        return links
    
    def download_image(self, image_url: str, page_url: str) -> Tuple[bool, str]:
        """
        Download an image and return local path.
        
        Args:
            image_url: URL of the image to download
            page_url: URL of the page containing the image (for relative URLs)
            
        Returns:
            Tuple of (success, local_path)
        """
        # Check if already downloaded
        if image_url in self.downloaded_images:
            return True, self.downloaded_images[image_url]
        
        try:
            # Resolve relative URLs
            absolute_url = urljoin(page_url, image_url)
            
            # Validate URL
            parsed = urlparse(absolute_url)
            if not parsed.scheme or not parsed.netloc:
                return False, image_url
            
            # Download image
            response = self.session.get(absolute_url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Determine file extension
            content_type = response.headers.get('content-type', '').split(';')[0].strip()
            ext = mimetypes.guess_extension(content_type)
            
            # If no extension from content-type, try from URL
            if not ext:
                url_path = unquote(parsed.path)
                if '.' in url_path:
                    ext = '.' + url_path.split('.')[-1].lower()
                    # Validate extension
                    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp']:
                        ext = '.jpg'  # Default
                else:
                    ext = '.jpg'
            
            # Create unique filename using hash
            url_hash = hashlib.md5(absolute_url.encode()).hexdigest()[:12]
            filename = f"{url_hash}{ext}"
            
            # Ensure images directory exists
            self.images_dir.mkdir(parents=True, exist_ok=True)
            
            # Save image
            image_path = self.images_dir / filename
            with open(image_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Store relative path for markdown
            relative_path = f"images/{filename}"
            self.downloaded_images[image_url] = relative_path
            
            return True, relative_path
            
        except Exception as e:
            print(f"    Warning: Failed to download image {image_url}: {e}")
            return False, image_url
    
    def process_images_in_content(self, soup: BeautifulSoup, page_url: str) -> BeautifulSoup:
        """
        Download images and update their src attributes to local paths.
        
        Args:
            soup: BeautifulSoup object with content
            page_url: URL of the page (for resolving relative image URLs)
            
        Returns:
            Modified BeautifulSoup object with local image paths
        """
        if not self.download_images:
            return soup
        
        # Find all images
        images = soup.find_all('img')
        
        if images:
            print(f"    Found {len(images)} images to download...")
        
        for img in images:
            src = img.get('src')
            if not src:
                continue
            
            # Skip data URLs
            if src.startswith('data:'):
                continue
            
            # Download image
            success, local_path = self.download_image(src, page_url)
            
            if success and local_path != src:
                # Update src to local path
                img['src'] = local_path
                
                # Also update srcset if present
                if img.get('srcset'):
                    # For simplicity, remove srcset and use single src
                    del img['srcset']
        
        return soup
    
    def extract_main_content(self, soup: BeautifulSoup, page_url: str = None) -> BeautifulSoup:
        """Extract main content area."""
        content_soup = BeautifulSoup(str(soup), 'html.parser')
        
        # Remove unwanted elements
        for selector in self.exclude_selectors:
            for element in content_soup.select(selector):
                element.decompose()
        
        # Try to find main content area - expanded Confluence selectors
        main_content = None
        for selector in [
            # Modern Confluence selectors (try these first)
            '[data-testid="page-content"]', '[data-testid="content"]',
            '.wiki-content', '#wiki-content', '.wiki-content-view',
            '.wiki-body', '.confluence-content', '.page-content',
            '.wiki-page', 'div[data-testid="page-body"]',
            # Standard selectors
            'main', 'article', '[role="main"]',
            '.content', '.main-content', '.documentation',
            '#content', '#main-content', '#main'
        ]:
            main_content = content_soup.select_one(selector)
            if main_content:
                print(f"    Found content with selector: {selector}")
                break
        
        # If no main content found, try to find any div with substantial text
        if not main_content:
            print(f"    No content found with standard selectors, searching for content-rich divs...")
            # Find all divs and check which has the most text (likely main content)
            all_divs = content_soup.find_all('div')
            best_div = None
            best_length = 0
            
            for div in all_divs:
                text = div.get_text(strip=True)
                # Skip if it's too short or looks like navigation/UI
                if len(text) > best_length and len(text) > 200:
                    # Check if it doesn't have too many links (likely nav)
                    link_count = len(div.find_all('a'))
                    text_length = len(text)
                    if link_count < text_length / 50:  # Not too link-heavy
                        best_div = div
                        best_length = len(text)
            
            if best_div:
                print(f"    Found content-rich div with {best_length} characters")
                main_content = best_div
            else:
                # Last resort: use body
                main_content = content_soup.find('body')
                if main_content:
                    print(f"    Using body as fallback")
        
        result = main_content if main_content else content_soup
        
        # Final check - if still minimal content, try extracting from body more aggressively
        if result:
            result_text = result.get_text() if hasattr(result, 'get_text') else str(result)
            if len(result_text.strip()) < 100:
                print(f"    ⚠️  Still minimal content ({len(result_text.strip())} chars), trying body extraction...")
                body = content_soup.find('body')
                if body:
                    # Remove all the UI elements we know about
                    for exclude in ['nav', 'header', 'footer', 'script', 'style', 
                                   '.navigation', '.sidebar', '.quick-nav', 
                                   '[data-testid="navigation"]', '[data-testid="header"]']:
                        for elem in body.select(exclude):
                            elem.decompose()
                    body_text = body.get_text(strip=True)
                    if len(body_text) > len(result_text.strip()):
                        print(f"    Using cleaned body content ({len(body_text)} chars)")
                        result = body
        
        # Process images if page_url provided
        if page_url and self.download_images:
            result = self.process_images_in_content(result, page_url)
        
        return result
    
    def html_to_markdown(self, html_content) -> str:
        """Convert HTML to markdown."""
        html_str = str(html_content)
        markdown = self.html_converter.handle(html_str)
        
        # Clean up excessive newlines
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        return markdown.strip()
    
    def sanitize_filename(self, url: str) -> str:
        """Create a safe filename from URL."""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        if not path or path == '':
            filename = 'index'
        else:
            filename = path.replace('/', '_')
            filename = re.sub(r'\.(html?|php|aspx?)$', '', filename)
        
        filename = re.sub(r'[^\w\-_]', '_', filename)
        
        if len(filename) > 200:
            filename = filename[:200]
        
        return f"{filename}.md"
    
    def save_markdown(self, url: str, markdown_content: str, title: str = None):
        """Save markdown to file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = self.sanitize_filename(url)
        filepath = self.output_dir / filename
        
        # Add metadata
        metadata = f"# Source: {url}\n"
        if title:
            metadata += f"# Title: {title}\n"
        metadata += f"\n---\n\n"
        
        full_content = metadata + markdown_content
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        print(f"  ✓ Saved: {filename}")
    
    def scrape_page(self, url: str) -> bool:
        """Scrape a single page."""
        if url in self.visited_urls:
            return False
        
        print(f"Scraping: {url}")
        self.visited_urls.add(url)
        
        soup = self.fetch_page(url)
        if not soup:
            print("  ✗ Failed to fetch page")
            return False
        
        # Extract title
        title = soup.find('title')
        title_text = title.get_text().strip() if title else None
        print(f"  Title: {title_text}")
        
        # Extract main content (with image processing)
        main_content = self.extract_main_content(soup, page_url=url)
        
        # Debug: Check content size
        content_text = main_content.get_text() if hasattr(main_content, 'get_text') else str(main_content)
        content_length = len(content_text.strip())
        print(f"  Content extracted: {content_length} characters")
        
        if content_length < 100:
            print(f"  ⚠️  Warning: Very little content extracted!")
            # Try to get body as fallback for debugging
            body = soup.find('body')
            if body:
                body_text = body.get_text().strip()
                print(f"  Body text length: {len(body_text)} characters")
                if len(body_text) > 100:
                    print(f"  → Using body content as fallback")
                    main_content = body
        
        # Convert to markdown
        markdown = self.html_to_markdown(main_content)
        markdown_length = len(markdown.strip())
        print(f"  Markdown output: {markdown_length} characters")
        
        # Save to file
        self.save_markdown(url, markdown, title_text)
        
        # Delay between requests
        time.sleep(self.delay)
        
        return True
    
    def scrape_documentation(self):
        """Main scraping workflow."""
        mode = "Single page" if self.single_page else "Multi-page"
        print(f"Starting scrape of: {self.base_url}")
        print(f"Mode: {mode}")
        print(f"Output directory: {self.output_dir.absolute()}")
        print(f"Scraper: {'Dynamic (Selenium)' if self.use_selenium else 'Static (Requests)'}")
        print(f"Image downloads: {'Enabled' if self.download_images else 'Disabled'}")
        print(f"Excluding selectors: {', '.join(self.exclude_selectors)}")
        print("-" * 60)
        
        # Setup Selenium if needed
        if self.use_selenium:
            if not self.setup_selenium():
                print("Falling back to static scraping...")
        
        try:
            if self.single_page:
                # Single page mode - just scrape the provided URL
                print("Scraping single page (no link following)...")
                print("-" * 60)
                success = self.scrape_page(self.base_url)
                successful = 1 if success else 0
                total = 1
            else:
                # Multi-page mode - extract links and follow them
                # Fetch base page
                soup = self.fetch_page(self.base_url)
                if not soup:
                    print("Failed to fetch base page. Exiting.")
                    return
                
                # Extract links
                content_links = self.extract_content_links(soup, self.base_url)
                print(f"Found {len(content_links)} content links to scrape")
                
                if len(content_links) == 0:
                    print("\nNo content links found!")
                    print("This might mean:")
                    print("  1. The page uses heavy JavaScript (try with Selenium)")
                    print("  2. All links are in header/footer (adjust --exclude-selector)")
                    print("  3. The page structure is different than expected")
                    print("\nTip: Try scraping the individual article URLs directly with --single-page")
                
                print("-" * 60)
                
                # Scrape each page
                successful = 0
                for i, link in enumerate(content_links, 1):
                    print(f"[{i}/{len(content_links)}] ", end="")
                    if self.scrape_page(link):
                        successful += 1
                total = len(content_links)
            
            print("-" * 60)
            print(f"Scraping complete!")
            print(f"Successfully scraped: {successful}/{total} page(s)")
            if self.download_images:
                print(f"Downloaded images: {len(self.downloaded_images)}")
                if len(self.downloaded_images) > 0:
                    print(f"Images saved to: {self.images_dir.absolute()}")
            print(f"Files saved to: {self.output_dir.absolute()}")
            
        finally:
            self.cleanup_selenium()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape documentation with JavaScript support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use Selenium for JavaScript-heavy sites
  python scrape_docs_dynamic.py https://learn.microsoft.com/collections/xyz
  
  # Static HTML only (faster, no JavaScript)
  python scrape_docs_dynamic.py https://docs.example.com --no-selenium
  
  # Custom output directory
  python scrape_docs_dynamic.py https://docs.example.com -o my_docs
  
  # Show browser window (not headless)
  python scrape_docs_dynamic.py https://docs.example.com --no-headless
  
  # Scrape a single page only (don't follow links)
  python scrape_docs_dynamic.py https://docs.example.com/article --single-page
        """
    )
    
    parser.add_argument('url', help='The base URL to scrape')
    parser.add_argument('--output-dir', '-o', default='scraped_docs',
                       help='Output directory (default: scraped_docs)')
    parser.add_argument('--exclude-selector', '-e', action='append',
                       dest='exclude_selectors',
                       help='CSS selector to exclude (can be used multiple times)')
    parser.add_argument('--delay', '-d', type=float, default=2.0,
                       help='Delay between requests in seconds (default: 2.0)')
    parser.add_argument('--no-selenium', action='store_true',
                       help='Disable Selenium (static HTML only)')
    parser.add_argument('--no-headless', action='store_true',
                       help='Show browser window (when using Selenium)')
    parser.add_argument('--no-images', action='store_true',
                       help='Disable image downloading')
    parser.add_argument('--single-page', '-s', action='store_true',
                       help='Scrape only the provided URL (do not follow links)')
    parser.add_argument('--cookies', '-c',
                       help='Cookie string in format "name1=value1; name2=value2"')
    parser.add_argument('--cookie-file',
                       help='Path to file containing cookies (Netscape format or cookie string)')
    
    args = parser.parse_args()
    
    # Validate URL
    parsed = urlparse(args.url)
    if not parsed.scheme or not parsed.netloc:
        print(f"Error: Invalid URL: {args.url}")
        sys.exit(1)
    
    # Create scraper
    scraper = DynamicDocumentationScraper(
        base_url=args.url,
        output_dir=args.output_dir,
        exclude_selectors=args.exclude_selectors,
        delay=args.delay,
        use_selenium=not args.no_selenium,
        headless=not args.no_headless,
        download_images=not args.no_images,
        single_page=args.single_page,
        cookies=args.cookies,
        cookie_file=args.cookie_file
    )
    
    try:
        scraper.scrape_documentation()
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user.")
        print(f"Partial results saved to: {scraper.output_dir.absolute()}")
        scraper.cleanup_selenium()
        sys.exit(0)


if __name__ == '__main__':
    main()

