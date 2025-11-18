from bs4 import BeautifulSoup
import json
import os
import requests
import datetime


def get_marine_forecast(lat, lon):
    """
    Fetches marine weather data from Open-Meteo API (24h forecast).
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
        "forecast_days": 1,  # Next 24h
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


def get_current_swell_data(data):
    """
    Extracts current hour's data for the summary card.
    """
    if not data or "hourly" not in data:
        return None

    current_hour = datetime.datetime.now().hour

    return {
        "wave_height": data["hourly"]["wave_height"][current_hour],
        "wave_period": data["hourly"]["wave_period"][current_hour],
        "wave_direction": data["hourly"]["wave_direction"][current_hour],
        "swell_height": data["hourly"]["swell_wave_height"][current_hour],
        "swell_period": data["hourly"]["swell_wave_period"][current_hour],
        "swell_direction": data["hourly"]["swell_wave_direction"][current_hour],
    }


def create_swell_card_content(soup, data):
    """
    Generates HTML content for the swell card.
    """
    if not data:
        return "Data Unavailable"

    container = soup.new_tag(
        "div",
        attrs={"class": "swell-data-container", "style": "display: flex; gap: 15px;"},
    )

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
    grid_item = soup.new_tag("div", attrs={"class": "grid-item"})
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
    src = soup.new_tag("source", src=stream_url, type="application/x-mpegURL")
    vid.append(src)
    grid_item.append(vid)
    return grid_item


def create_iframe_tag(soup, src_url):
    grid_item = soup.new_tag("div", attrs={"class": "grid-item"})
    iframe = soup.new_tag("iframe", src=src_url, allowfullscreen="", autoplay="")
    grid_item.append(iframe)
    return grid_item


def inject_chart_data(soup, haifa_data, tlv_data):
    """
    Injects the JavaScript to render charts with the fetched data.
    """
    script_content = """
    document.addEventListener('DOMContentLoaded', function() {
        function createChart(ctxId, label, labels, waveData, swellData) {
            const ctx = document.getElementById(ctxId);
            if (!ctx) return;
            
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Wave Height (m)',
                            data: waveData,
                            borderColor: 'rgba(0, 123, 255, 1)',
                            backgroundColor: 'rgba(0, 123, 255, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.4
                        },
                        {
                            label: 'Swell Height (m)',
                            data: swellData,
                            borderColor: 'rgba(40, 167, 69, 1)',
                            backgroundColor: 'rgba(40, 167, 69, 0.1)',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            fill: true,
                            tension: 0.4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'top' },
                        tooltip: { mode: 'index', intersect: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: { display: true, text: 'Height (m)' }
                        },
                        x: {
                            ticks: { 
                                maxTicksLimit: 8,
                                autoSkip: true,
                                maxRotation: 45,
                                minRotation: 45
                            }
                        }
                    }
                }
            });
        }

        // Injected Data
    """

    # Format data for JS
    def format_hourly(data):
        if not data or "hourly" not in data:
            return "[]", "[]", "[]"

        # Format time as "Day HH:MM" for clarity
        times = []
        for t in data["hourly"]["time"]:
            # t is ISO format "YYYY-MM-DDTHH:MM"
            dt = datetime.datetime.fromisoformat(t)
            times.append(dt.strftime("%d/%m %H:%M"))

        waves = data["hourly"]["wave_height"]
        swells = data["hourly"]["swell_wave_height"]
        return json.dumps(times), json.dumps(waves), json.dumps(swells)

    h_labels, h_waves, h_swells = format_hourly(haifa_data)
    t_labels, t_waves, t_swells = format_hourly(tlv_data)

    script_content += f"\n        createChart('haifaChart', 'Haifa Forecast', {h_labels}, {h_waves}, {h_swells});"
    script_content += f"\n        createChart('tlvChart', 'TLV Forecast', {t_labels}, {t_waves}, {t_swells});"
    script_content += "\n    });"

    script_tag = soup.new_tag("script")
    script_tag.string = script_content
    soup.body.append(script_tag)


def main():
    # Coordinates
    COORDS = {
        "haifa": {"lat": 32.8304, "lon": 34.9745},
        "tlv": {"lat": 32.0853, "lon": 34.7818},
    }

    # Load Template
    if not os.path.exists("template.html"):
        print("Error: template.html not found.")
        return

    with open("template.html", "r") as f:
        template_content = f.read()

    soup = BeautifulSoup(template_content, "html.parser")

    # Store fetched data for charts
    forecast_data = {}

    # --- Fetch & Inject Swell Data ---
    for loc, coords in COORDS.items():
        print(f"Fetching swell data for {loc}...")
        raw_data = get_marine_forecast(coords["lat"], coords["lon"])
        forecast_data[loc] = raw_data

        # Summary Card
        current_data = get_current_swell_data(raw_data)
        card_id = f"{loc}-swell-card"
        card_div = soup.find(id=card_id)
        if card_div:
            card_div.clear()
            content = create_swell_card_content(soup, current_data)
            if content == "Data Unavailable":
                card_div.string = "Forecast Unavailable"
            else:
                card_div.append(content)

    # Inject Chart JS
    inject_chart_data(soup, forecast_data.get("haifa"), forecast_data.get("tlv"))

    # Load Stream URLs
    stream_urls = {}
    if os.path.exists("stream_url.json"):
        with open("stream_url.json", "r") as f:
            stream_urls = json.load(f)

    # --- Process Haifa Cams ---
    haifa_container = soup.find(id="haifa-cams-container")
    if haifa_container:
        grid = soup.new_tag("div", attrs={"class": "grid-container"})
        haifa_container.append(grid)

        static_haifa = [
            "https://g2.ipcamlive.com/player/player.php?alias=5ffd9eb29b665",
            "https://g0.ipcamlive.com/player/player.php?alias=60acaa1aeee83",
        ]
        for url in static_haifa:
            grid.append(create_iframe_tag(soup, url))

        relevant_haifa = ["bat-galim", "meridian"]
        for name in relevant_haifa:
            if name in stream_urls:
                print(f"Adding dynamic stream for {name}")
                grid.append(create_video_tag(soup, name, stream_urls[name]))

    # --- Process TLV Cams ---
    tlv_container = soup.find(id="tlv-cams-container")
    if tlv_container:
        grid = soup.new_tag("div", attrs={"class": "grid-container"})
        tlv_container.append(grid)

        relevant_tlv = ["dolphinarium", "hilton", "yafo"]
        for name in relevant_tlv:
            if name in stream_urls:
                print(f"Adding dynamic stream for {name}")
                grid.append(create_video_tag(soup, name, stream_urls[name]))

    # --- Add Auto-Play Script ---
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
