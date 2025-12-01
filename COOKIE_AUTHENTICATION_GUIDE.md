# Cookie Authentication Guide

The documentation scraper now supports authentication via session cookies! This allows you to scrape internal documentation pages that require login.

## Quick Start

### Option 1: Cookie String (Command Line)

Pass cookies directly as a string:

```bash
python scrape_docs_dynamic.py https://internal-docs.example.com \
  --cookies "session_id=abc123; auth_token=xyz789; user_id=12345"
```

### Option 2: Cookie File

Save cookies to a file and reference it:

```bash
# Create cookie file
echo "session_id=abc123; auth_token=xyz789; user_id=12345" > cookies.txt

# Use with scraper
python scrape_docs_dynamic.py https://internal-docs.example.com \
  --cookie-file cookies.txt
```

## Getting Your Cookies

### From Browser Developer Tools

1. **Open your browser** and log into the documentation site
2. **Open Developer Tools** (F12 or Cmd+Option+I on Mac)
3. **Go to Application/Storage tab**
4. **Navigate to Cookies** → select your domain
5. **Copy cookie values** in the format: `name1=value1; name2=value2`

### From Browser Extensions

You can use browser extensions to export cookies:
- **EditThisCookie** (Chrome/Edge)
- **Cookie Editor** (Firefox/Chrome)

These can export cookies in Netscape format or JSON.

### Manual Extraction

In browser console:
```javascript
// Copy this into browser console to get cookie string
document.cookie
```

This will output: `name1=value1; name2=value2`

## Cookie Format

### Simple Cookie String Format (Recommended)

```
name1=value1; name2=value2; name3=value3
```

Example:
```
session_id=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9; csrf_token=a1b2c3d4; user_pref=dark_mode
```

**Important:** 
- Use semicolons (`;`) to separate cookies
- No spaces around the `=` sign
- Values can contain special characters (they'll be URL-encoded if needed)

### Netscape Format

If you have cookies in Netscape format (from browser exports), the scraper will automatically detect and parse them:

```
# Netscape HTTP Cookie File
.example.com	TRUE	/	FALSE	1735689600	session_id	eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
.example.com	TRUE	/	FALSE	1735689600	csrf_token	a1b2c3d4
```

## Usage Examples

### Single Page with Cookies

```bash
python scrape_docs_dynamic.py https://internal-docs.example.com/page \
  --single-page \
  --cookies "session_id=abc123; auth_token=xyz789"
```

### Multi-Page Scraping with Authentication

```bash
python scrape_docs_dynamic.py https://internal-docs.example.com/guide \
  --cookie-file cookies.txt \
  --output-dir internal_docs
```

### Using with Static Scraper

The static scraper (`scrape_docs.py`) also supports cookies:

```bash
python scrape_docs.py https://internal-docs.example.com \
  --cookies "session_id=abc123; auth_token=xyz789"
```

### Combining with Other Options

```bash
python scrape_docs_dynamic.py https://internal-docs.example.com \
  --cookies "session_id=abc123" \
  --single-page \
  --output-dir my_docs \
  --exclude-selector ".sidebar"
```

## Security Best Practices

 Armadillo⚠️ **Security Warning**: Cookies contain authentication credentials!

1. **Never commit cookies to version control**
   - Add `cookies.txt` to `.gitignore`
   - Don't share cookie files publicly

2. **Use cookie files instead of command-line arguments**
   - Command-line arguments are visible in process lists
   - Files are more secure (set appropriate permissions)

3. **Set file permissions** (Unix/Mac):
   ```bash
   chmod 600 cookies.txt  # Only you can read/write
   ```

4. **Use environment variables** (for scripts):
   ```bash
   export COOKIES="session_id=abc123"
   python scrape_docs_dynamic.py $URL --cookies "$COOKIES"
   ```

5. **Rotate cookies regularly**
   - Don't use expired or long-term cookies
   - Update cookie files when sessions expire

## Troubleshooting

### Cookies Not Working

**Check:**
1. Cookie format is correct (`name=value; name2=value2`)
2. Cookies are still valid (not expired)
3. Domain matches the site you're scraping
4. Cookies include all required authentication cookies

**Debug:**
```bash
# Use --no-headless to see what's happening
python scrape_docs_dynamic.py $URL \
  --cookies "..." \
  --no-headless
```

### Authentication Still Failing

**Common Issues:**
- **CSRF tokens**: Some sites require fresh CSRF tokens for each request
- **Session expiration**: Cookies may have expired
- **Domain mismatch**: Cookies must match the domain you're scraping
- **Path restrictions**: Some cookies are path-specific
限于**Secure/HttpOnly**: Some cookies can't be set programmatically

**Solution**: 
- Re-login and get fresh cookies
- Check browser DevTools to see all cookies needed
- Ensure you're copying all authentication-related cookies

### Cookie File Not Found

If using `--cookie-file`, ensure:
- File path is correct (use absolute path if unsure)
- File is readable
- File contains valid cookie data

### Selenium Cookie Issues

For Selenium (dynamic scraper):
- Cookies are applied after the first page load
- Domain must match the URL you're scraping
- Some sites require cookies before first request (may need manual login first)

## Advanced: Using Browser Profiles

For complex authentication, you might want to:

1. **Use a browser profile** with saved login:
   ```python
   # This would require modifying the scraper code
   # to load a Chrome profile with saved cookies
   ```

2. **Manually log in first** (if using `--no-headless`):
   - Run scraper with `--no-headless`
   - Log in manually in the browser window
   - Scraper will continue with authenticated session

## Cookie File Example

Create a file `cookies.txt`:

```
# Cookie file for internal-docs.example.com
session_id=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
csrf_token=a1b2c3d4e5f6g7h8i9j0
user_id=12345
remember_me=true
```

Then use it:
```bash
python scrape_docs_dynamic.py https://internal-docs.example.com \
  --cookie-file cookies.txt
```

## Tips

- **Test with single page first**: Use `--single-page` to verify cookies work
- **Check response**: Look for authentication errors in the output
- **Save working cookies**: Keep a backup of working cookie files
- **Document requirements**: Note which cookies are required for your site
- **Automate extraction**: Create a script to extract cookies automatically

## Need Help?

If cookies aren't working:
1. Check the cookie format matches the examples
2. Verify cookies are not expired
3. Ensure all required cookies are included
4. Try using `--no-headless` to debug visually
5. Check if the site uses additional authentication (2FA, tokens, etc.)

Happy authenticated scraping! 🔐

