from bs4 import BeautifulSoup
import json
import os
import requests
import datetime


def get_marine_forecast(lat, lon):
    """
    Fetches marine weather data from Open-Meteo API.
    """
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": [
            "wave_height",
            "wave_period",
            "wave_direction",
            "swell_wave_height",
            "swell_wave_period",
            "swell_wave_direction",
        ],
        "timezone": "auto",
        "forecast_days": 1,
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


def format_forecast_data(data):
    """
    Formats the raw API response into a simplified structure for the dashboard.
    Extracts current hour's data.
    """
    if not data or "hourly" not in data:
        return None

    # Get index for current hour (approximate)
    # Open-Meteo returns hourly data starting from 00:00 of requested days
    current_hour = datetime.datetime.now().hour

    return {
        "wave_height": data["hourly"]["wave_height"][current_hour],
        "wave_period": data["hourly"]["wave_period"][current_hour],
        "wave_direction": data["hourly"]["wave_direction"][current_hour],
        "swell_height": data["hourly"]["swell_wave_height"][current_hour],
        "swell_period": data["hourly"]["swell_wave_period"][current_hour],
        "swell_direction": data["hourly"]["swell_wave_direction"][current_hour],
        "time": data["hourly"]["time"][current_hour],
    }


def create_swell_card_content(soup, data):
    """
    Generates HTML content for the swell card based on data.
    """
    if not data:
        return "Data Unavailable"

    container = soup.new_tag(
        "div",
        attrs={"class": "swell-data-container", "style": "display: flex; gap: 15px;"},
    )

    # Helper to create item
    def add_item(label, value, unit):
        item = soup.new_tag("div", attrs={"class": "swell-item"})

        lbl = soup.new_tag("div", attrs={"class": "swell-label"})
        lbl.string = label

        val = soup.new_tag("div", attrs={"class": "swell-value"})
        val.string = f"{value}{unit}"

        item.append(lbl)
        item.append(val)
        container.append(item)

    add_item("Wave Height", data["wave_height"], "m")
    add_item("Swell", data["swell_height"], "m")
    add_item("Period", data["swell_period"], "s")
    add_item("Dir", data["swell_direction"], "°")

    return container


def create_video_tag(soup, id_name, stream_url):
    """Creates a video-js tag for a given stream URL."""
    grid_item = soup.new_tag("div", attrs={"class": "grid-item"})

    # Create video element
    vid = soup.new_tag(
        "video",
        id=f"{id_name}-cam",
        attrs={
            "class": "video-js vjs-default-skin vjs-big-play-centered",
            "controls": "",
            "preload": "auto",
            "playsinline": "",
        },
    )

    # Add source
    src = soup.new_tag("source", src=stream_url, type="application/x-mpegURL")
    vid.append(src)
    grid_item.append(vid)

    return grid_item


def create_iframe_tag(soup, src_url):
    """Creates an iframe tag (used for static Haifa cams)."""
    grid_item = soup.new_tag("div", attrs={"class": "grid-item"})
    iframe = soup.new_tag(
        "iframe", src=src_url, allowfullscreen="", autoplay=""
    )  # attributes that don't need values
    grid_item.append(iframe)
    return grid_item


def main():
    # Coordinates
    COORDS = {
        "haifa": {"lat": 32.8304, "lon": 34.9745},  # Bat Galim approximate
        "tlv": {"lat": 32.0853, "lon": 34.7818},  # Hilton/Tel Aviv
    }

    # Load Template
    if not os.path.exists("template.html"):
        print("Error: template.html not found.")
        return

    with open("template.html", "r") as f:
        template_content = f.read()

    soup = BeautifulSoup(template_content, "html.parser")

    # --- Fetch & Inject Swell Data ---
    for loc, coords in COORDS.items():
        print(f"Fetching swell data for {loc}...")
        raw_data = get_marine_forecast(coords["lat"], coords["lon"])
        formatted_data = format_forecast_data(raw_data)

        card_id = f"{loc}-swell-card"
        card_div = soup.find(id=card_id)
        if card_div:
            # Clear loading text
            card_div.clear()
            # Add new content
            content = create_swell_card_content(soup, formatted_data)
            if content == "Data Unavailable":
                card_div.string = "Forecast Unavailable"
            else:
                card_div.append(content)

    # Load Stream URLs
    stream_urls = {}
    if os.path.exists("stream_url.json"):
        with open("stream_url.json", "r") as f:
            stream_urls = json.load(f)
    else:
        print("Warning: stream_url.json not found. Only static cameras will be shown.")

    # --- Process Haifa Cams ---
    haifa_container = soup.find(id="haifa-cams")
    if haifa_container:
        # Create a grid container
        grid = soup.new_tag("div", attrs={"class": "grid-container"})
        haifa_container.append(grid)

        # 1. Static Hardcoded Cams (from original cams.py)
        static_haifa = [
            "https://g2.ipcamlive.com/player/player.php?alias=5ffd9eb29b665",  # Bat Galim?
            "https://g0.ipcamlive.com/player/player.php?alias=60acaa1aeee83",  # Meridian?
        ]
        for url in static_haifa:
            grid.append(create_iframe_tag(soup, url))

        # 2. Dynamic Cams (if any)
        # Original code also checked stream_url.json for "bat-galim", "meridian"
        relevant_haifa = ["bat-galim", "meridian"]
        for name in relevant_haifa:
            if name in stream_urls:
                print(f"Adding dynamic stream for {name}")
                grid.append(create_video_tag(soup, name, stream_urls[name]))

    # --- Process TLV Cams ---
    tlv_container = soup.find(id="tlv-cams")
    if tlv_container:
        # Create a grid container
        grid = soup.new_tag("div", attrs={"class": "grid-container"})
        tlv_container.append(grid)

        relevant_tlv = ["dolphinarium", "hilton", "yafo"]
        for name in relevant_tlv:
            if name in stream_urls:
                print(f"Adding dynamic stream for {name}")
                grid.append(create_video_tag(soup, name, stream_urls[name]))

    # --- Add Auto-Play Script ---
    # We need to initialize the video-js players
    # Collect all video IDs
    video_ids = [v["id"] for v in soup.find_all("video")]
    if video_ids:
        script_content = "window.addEventListener('load', function() {\n"
        for vid_id in video_ids:
            script_content += f"  if(document.getElementById('{vid_id}')) {{ videojs('{vid_id}').play(); }}\n"
        script_content += "});"

        script_tag = soup.new_tag("script")
        script_tag.string = script_content
        soup.body.append(script_tag)

    # Write Output
    with open("index.html", "w") as f:
        f.write(soup.prettify())

    print("Successfully generated index.html")


if __name__ == "__main__":
    main()
