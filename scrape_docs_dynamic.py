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
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from typing import Set, List, Dict, Tuple

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
        download_images: bool = True
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
        """
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "images"
        self.exclude_selectors = exclude_selectors or [
            'header', 'footer', 'nav', 
            '.header', '.footer', '.navigation',
            '.cookie-banner', '#cookie-banner',
            '.feedback', '.page-actions'
        ]
        self.delay = delay
        self.visited_urls: Set[str] = set()
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.headless = headless
        self.driver = None
        self.download_images = download_images
        self.downloaded_images: Dict[str, str] = {}  # URL -> local path mapping
        
        # Setup requests session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        
        # Configure html2text
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = False
        self.html_converter.body_width = 0
        self.html_converter.single_line_break = False
        
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
            self.driver.get(url)
            
            # Wait for page to load - look for common content indicators
            try:
                WebDriverWait(self.driver, wait_time).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                # Additional wait for dynamic content
                time.sleep(2)
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
        
        # Try to find main content area
        main_content = None
        for selector in [
            'main', 'article', '[role="main"]',
            '.content', '.main-content', '.documentation',
            '#content', '#main-content', '#main'
        ]:
            main_content = content_soup.select_one(selector)
            if main_content:
                break
        
        if not main_content:
            main_content = content_soup.find('body')
        
        result = main_content if main_content else content_soup
        
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
            return False
        
        # Extract title
        title = soup.find('title')
        title_text = title.get_text().strip() if title else None
        
        # Extract main content (with image processing)
        main_content = self.extract_main_content(soup, page_url=url)
        
        # Convert to markdown
        markdown = self.html_to_markdown(main_content)
        
        # Save to file
        self.save_markdown(url, markdown, title_text)
        
        # Delay between requests
        time.sleep(self.delay)
        
        return True
    
    def scrape_documentation(self):
        """Main scraping workflow."""
        print(f"Starting scrape of: {self.base_url}")
        print(f"Output directory: {self.output_dir.absolute()}")
        print(f"Mode: {'Dynamic (Selenium)' if self.use_selenium else 'Static (Requests)'}")
        print(f"Image downloads: {'Enabled' if self.download_images else 'Disabled'}")
        print(f"Excluding selectors: {', '.join(self.exclude_selectors)}")
        print("-" * 60)
        
        # Setup Selenium if needed
        if self.use_selenium:
            if not self.setup_selenium():
                print("Falling back to static scraping...")
        
        try:
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
                print("\nTip: Try scraping the individual article URLs directly")
            
            print("-" * 60)
            
            # Scrape each page
            successful = 0
            for i, link in enumerate(content_links, 1):
                print(f"[{i}/{len(content_links)}] ", end="")
                if self.scrape_page(link):
                    successful += 1
            
            print("-" * 60)
            print(f"Scraping complete!")
            print(f"Successfully scraped: {successful}/{len(content_links)} pages")
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
        download_images=not args.no_images
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

