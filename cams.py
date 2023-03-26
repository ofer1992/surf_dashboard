from bs4 import BeautifulSoup
import json

html = """<head>
    <link href="https://unpkg.com/video.js/dist/video-js.css" rel="stylesheet">
    <script src="https://unpkg.com/video.js/dist/video.js"></script>
</head>

<body>
    <div class="grid-container">

    </div>
</body>"""

page = BeautifulSoup(html, "html.parser")
with open("stream_url.json", 'r') as f:
    stream_urls = json.load(f)

for k, v in stream_urls.items():
  grid_item = page.new_tag("div", attrs={"class":"grid-item"})
  vid = page.new_tag("video", id=k+"-cam", width="500", height="500", controls="", preload="auto", attrs={"class":"video-js vjs-default-skin"})
  src = page.new_tag("source", src=v, type="application/x-mpegURL")
  
  page.body.div.append(grid_item)
  grid_item.append(vid)
  vid.append(src)

script = page.new_tag("script")
script.string = " ".join([f"videojs('{k}-cam');" for k in stream_urls.keys()])
page.body.append(script)

with open("cams.html", 'w') as f:
   f.write(page.prettify())