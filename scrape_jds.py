
import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import urlparse
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
REMOVE_TAGS = [
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "aside",
    "noscript",
    "iframe",
    "svg",
    "form"
]

def validate_url(url):
    if not url or not isinstance(url, str):
        raise ValueError("Please enter a valid URL.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://.")
    if not parsed.netloc:
        raise ValueError("Invalid website address.")
    return url.strip()
def clean_text(text):
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()
def extract_page_content(html):
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)
    for tag in soup(REMOVE_TAGS):
        tag.decompose()
    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )
    for tag in main_content(["button","input","select","textarea"]):
        tag.decompose()
    text = main_content.get_text( separator="\n",strip=True)
    text = clean_text(text)
    if len(text) < 100:
        raise ValueError(
            "The webpage returned very little readable text. "
            "It may require JavaScript, login, or bot verification."
        )
    return {
        "title": title,
        "text": text
    }

def scrape_jd_url(url, timeout=25):
    url = validate_url(url)
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise ValueError("The website took too long to respond.")
    except requests.exceptions.ConnectionError:
        raise ValueError(
            "Could not connect to the website. "
            "Check your internet connection and URL."
        )
    except requests.exceptions.HTTPError as error:
        raise ValueError(
            f"Website returned an HTTP error: {error}"
        )
    except requests.exceptions.RequestException as error:
        raise ValueError(
            f"Could not retrieve the webpage: {error}"
        )
    content_type = response.headers.get("Content-Type", "").lower()
    if "html" not in content_type:
        raise ValueError("The URL did not return an HTML webpage.")
    result = extract_page_content(response.text)
    result["url"] = response.url
    return result
def scrape_jd_text(url):
    result = scrape_jd_url(url)
    return result["text"]
