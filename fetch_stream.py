import requests
from bs4 import BeautifulSoup
import re
import json


urls = {"dolphinarium": "https://beachcam.co.il/dolfinarium.html"}
stream_urls = {}
for name, url in urls.items():
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    iframe_src = soup.find('iframe')['src'] # Get the src attribute of the iframe element
    stream_url = None

    if 'ipcamlive.com' in iframe_src: # Check if the iframe src is from ipcamlive.com
        iframe_response = requests.get(iframe_src)
        iframe_soup = BeautifulSoup(iframe_response.content, 'html.parser')
        script_tag = iframe_soup.find_all('script')[-1] # Get the last script tag in the iframe
        script_text = script_tag.string.strip() # Get the text content of the script tag
        stream_id = re.search("var streamid = '(.*)';", script_text).group(1)

    if stream_id is not None:
        stream_url = f"https://s5.ipcamlive.com/streams/{stream_id}/stream.m3u8" # Construct the direct stream source URL using the value of streamid
        stream_urls[name] = stream_url
        print(stream_url) # Print the direct stream source URL

with open("stream_url.json", 'w') as f:
    json.dump(stream_urls, f)