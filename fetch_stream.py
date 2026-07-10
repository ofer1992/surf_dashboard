import requests
from bs4 import BeautifulSoup
import re
import json


urls = {
    "dolphinarium": "https://beachcam.co.il/dolfinarium.html",
    "hilton": "https://beachcam.co.il/yamit.html",
    "yafo": "https://beachcam.co.il/yafo.html",
    "bat-galim": "https://beachcam.co.il/batgalim.html",
    "meridian": "https://beachcam.co.il/meridian.html"
}


def fetch_stream_url(page_url):
    """Resolve the direct .m3u8 stream URL for a single beachcam page.

    The page embeds an ipcamlive player in an <iframe> (served from a
    rotating subdomain, e.g. g1.ipcamlive.com). The iframe page exposes the
    stream address/id via inline JS, which we combine into the m3u8 URL.
    """
    response = requests.get(page_url, timeout=30)
    soup = BeautifulSoup(response.content, "html.parser")

    iframe_src = None
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "")
        if "ipcamlive.com" in src and "player.php" in src:
            # The src attribute may span multiple lines; strip whitespace.
            iframe_src = re.sub(r"\s+", "", src)
            break
    if not iframe_src:
        raise ValueError("no ipcamlive iframe found")

    iframe_response = requests.get(iframe_src, timeout=30)
    iframe_soup = BeautifulSoup(iframe_response.content, "html.parser")
    script_tag = iframe_soup.find_all("script")[-1]  # last script tag holds the config
    script_text = script_tag.string.strip()

    stream_address = re.search("var address = '(.*)';", script_text).group(1)
    stream_address = "https" + stream_address[4:]
    stream_id = re.search("var streamid = '(.*)';", script_text).group(1)
    return f"{stream_address}streams/{stream_id}/stream.m3u8"


stream_urls = {}
for name, url in urls.items():
    try:
        stream_url = fetch_stream_url(url)
    except Exception as e:
        # A single broken cam must not abort the run: the forecast pipeline
        # depends on this script exiting successfully.
        print(f"failed extraction for {name}: {e}")
        continue
    stream_urls[name] = stream_url
    print(f"{name}: {stream_url}")

# Only overwrite the file when we resolved at least one stream, so a total
# site outage keeps the last-known-good URLs instead of blanking them out.
if stream_urls:
    with open("stream_url.json", 'w') as f:
        json.dump(stream_urls, f, indent=2)
else:
    print("no streams resolved; keeping existing stream_url.json")
