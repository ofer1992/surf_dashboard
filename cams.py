from bs4 import BeautifulSoup
import json

def generate(html, relevant_cams, fname):
    page = BeautifulSoup(html, "html.parser")
    with open("stream_url.json", 'r') as f:
        stream_urls = json.load(f)

    # streamitup cams
    stream_urls = {k:v for k,v in stream_urls.items() if k in relevant_cams}
    for k, v in stream_urls.items():
        grid_item = page.new_tag("div", attrs={"class":"grid-item"})
        vid = page.new_tag("video", id=k+"-cam", width="500", height="500", controls="", preload="auto", attrs={"class":"video-js vjs-default-skin"})
        src = page.new_tag("source", src=v, type="application/x-mpegURL")

        page.body.div.append(grid_item)
        grid_item.append(vid)
        vid.append(src)

    script = page.new_tag("script")
    script.string = " ".join([f"videojs('{k}-cam').play();" for k in stream_urls.keys()])
    page.body.append(script)

    with open(fname, 'w') as f:
        f.write(page.prettify())

html_tlv = """<head>
    <link href="https://unpkg.com/video.js/dist/video-js.css" rel="stylesheet">
    <script src="https://unpkg.com/video.js/dist/video.js"></script>
</head>

<body>
    <div class="grid-container">
        <div class="grid-item">
            <iframe id="cam" width="500" height="500" allowfullscreen
                src="https://gocamstream.com/WebRTCApp/play.html?name=0002" scrolling="no">
            </iframe>
        </div>
    </div>
</body>"""

html_haifa = """<head>
    <link href="https://unpkg.com/video.js/dist/video-js.css" rel="stylesheet">
    <script src="https://unpkg.com/video.js/dist/video.js"></script>
</head>

<body>
    <div class="grid-container">
        <div class="grid-item">
            <iframe src="https://g2.ipcamlive.com/player/player.php?alias=5ffd9eb29b665" width="500" height="500"
                    autoplay allowfullscreen></iframe>
        </div>
        <div class="grid-item">
            <iframe src="https://g0.ipcamlive.com/player/player.php?alias=60acaa1aeee83" width="500" height="500"
                autoplay allowfullscreen></iframe>
        </div>
    </div>
</body>"""

generate(html_tlv, ["dolphinarium", "hilton"], "cams_haifa.html")
generate(html_haifa, ["bat-galim", "meridian"], "cams_haifa.html")
