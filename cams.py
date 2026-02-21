from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import json
import os
import requests


def create_swell_card_content(soup, data):
    """
    Generates HTML content for the swell summary card using ISRAMAR forecast data.
    Uses the first (current) entry from the ISRAMAR forecast.
    """
    if not data or len(data) == 0:
        return "Data Unavailable"

    now = datetime.now(timezone.utc)
    current = min(data, key=lambda d: abs((d["dt"] - now).total_seconds()))

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

    add_item("Wave Height", current["wave_height"], "m")
    add_item("Period", current["wave_period"], "s")
    add_item("Dir", int(current["wave_dir"]), "°")
    add_item("Wind", int(current["wind_speed_kts"]), "kt")

    return container, current["datetime"]


def fetch_isramar_forecast(lon, lat):
    """
    Fetches 5-day wave forecast from ISRAMAR InfoLabel.aspx endpoint.
    Returns list of dicts with wave/wind data at 3h intervals.
    """
    modeldate = datetime.now(timezone.utc).strftime("%y%m%d0000")
    url = (
        f"https://isramar.ocean.org.il/isramar2009/wave_model/InfoLabel.aspx"
        f"?x={lon}&y={lat}&model=wam&modeldate={modeldate}&region=fine"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error fetching ISRAMAR forecast: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    base_dt = datetime.strptime("20" + modeldate, "%Y%m%d%H%M")

    results = []
    for i in range(41):
        wav = soup.find(id=f"wav{i}")
        wnd = soup.find(id=f"wnd{i}")
        if not wav:
            break
        wav_cells = [td.text.strip() for td in wav.find_all("td")]
        wnd_cells = [td.text.strip() for td in wnd.find_all("td")] if wnd else []
        dt = base_dt + timedelta(hours=3 * i)
        results.append({
            "dt": dt.replace(tzinfo=timezone.utc),
            "datetime": dt.strftime("%a %d/%m %H:%M"),
            "wave_height": float(wav_cells[2]) if len(wav_cells) > 2 else 0,
            "wave_dir": float(wav_cells[5]) if len(wav_cells) > 5 else 0,
            "wave_period": float(wav_cells[8]) if len(wav_cells) > 8 else 0,
            "wind_speed_kts": float(wnd_cells[5]) if len(wnd_cells) > 5 else 0,
            "wind_dir": float(wnd_cells[8]) if len(wnd_cells) > 8 else 0,
        })
    return results


def fetch_buoy_data():
    """
    Fetches latest observation from Hadera buoy JSON endpoint.
    """
    url = "https://isramar.ocean.org.il/isramar2009/station/data/Hadera_Hs_Per.json"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching buoy data: {e}")
        return None


def create_buoy_card_content(soup, buoy_data):
    """
    Generates HTML content for the live buoy observation card.
    """
    if not buoy_data or "parameters" not in buoy_data:
        return "Buoy Unavailable"

    params = {p["name"]: p["values"][0] for p in buoy_data["parameters"]}
    obs_time = buoy_data.get("datetime", "")

    container = soup.new_tag("div", attrs={"style": "display: flex; gap: 15px; align-items: center;"})

    # Title + time
    title_div = soup.new_tag("div")
    title = soup.new_tag("div", attrs={"class": "buoy-title"})
    title.string = "Hadera Buoy"
    time_div = soup.new_tag("div", attrs={"class": "buoy-time"})
    time_div.string = obs_time
    title_div.append(title)
    title_div.append(time_div)
    container.append(title_div)

    def add_item(label, value, unit):
        item = soup.new_tag("div", attrs={"class": "swell-item"})
        lbl = soup.new_tag("div", attrs={"class": "swell-label"})
        lbl.string = label
        val = soup.new_tag("div", attrs={"class": "swell-value"})
        val.string = f"{value}{unit}"
        item.append(lbl)
        item.append(val)
        container.append(item)

    hs = params.get("Significant wave height", 0)
    period = params.get("Peak wave period", 0)
    hmax = params.get("Maximal wave height", 0)

    add_item("Hs", f"{hs:.1f}", "m")
    add_item("Period", f"{period:.1f}", "s")
    add_item("Hmax", f"{hmax:.1f}", "m")

    return container


def inject_isramar_chart_data(soup, haifa_data, tlv_data):
    """
    Injects JavaScript to render ISRAMAR 5-day forecast as Chart.js charts.
    """
    def format_data(data):
        if not data:
            return "[]", "[]", "[]", "[]"
        labels = json.dumps([d["datetime"] for d in data])
        heights = json.dumps([d["wave_height"] for d in data])
        periods = json.dumps([d["wave_period"] for d in data])
        winds = json.dumps([d["wind_speed_kts"] for d in data])
        return labels, heights, periods, winds

    h_labels, h_heights, h_periods, h_winds = format_data(haifa_data)
    t_labels, t_heights, t_periods, t_winds = format_data(tlv_data)

    script_content = """
    document.addEventListener('DOMContentLoaded', function() {
        function createIsramarChart(ctxId, labels, heights, periods, winds) {
            const ctx = document.getElementById(ctxId);
            if (!ctx) return;

            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Wave Height (m)',
                            data: heights,
                            borderColor: 'rgba(0, 123, 255, 1)',
                            backgroundColor: 'rgba(0, 123, 255, 0.15)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.4,
                            yAxisID: 'y'
                        },
                        {
                            label: 'Period (s)',
                            data: periods,
                            borderColor: 'rgba(255, 159, 64, 1)',
                            backgroundColor: 'rgba(255, 159, 64, 0.05)',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            fill: false,
                            tension: 0.4,
                            yAxisID: 'y1'
                        },
                        {
                            label: 'Wind (kt)',
                            data: winds,
                            borderColor: 'rgba(150, 150, 150, 0.7)',
                            backgroundColor: 'rgba(150, 150, 150, 0.1)',
                            borderWidth: 1,
                            fill: true,
                            tension: 0.4,
                            yAxisID: 'y'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { position: 'top' },
                        tooltip: { mode: 'index', intersect: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            position: 'left',
                            title: { display: true, text: 'Height (m) / Wind (kt)' }
                        },
                        y1: {
                            beginAtZero: true,
                            position: 'right',
                            title: { display: true, text: 'Period (s)' },
                            grid: { drawOnChartArea: false }
                        },
                        x: {
                            ticks: {
                                maxTicksLimit: 10,
                                autoSkip: true,
                                maxRotation: 45,
                                minRotation: 45
                            }
                        }
                    }
                }
            });
        }
"""

    script_content += f"\n        createIsramarChart('isramarHaifaChart', {h_labels}, {h_heights}, {h_periods}, {h_winds});"
    script_content += f"\n        createIsramarChart('isramarTlvChart', {t_labels}, {t_heights}, {t_periods}, {t_winds});"
    script_content += "\n    });"

    script_tag = soup.new_tag("script")
    script_tag.string = script_content
    soup.body.append(script_tag)


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



def main():
    # Load Template
    if not os.path.exists("template.html"):
        print("Error: template.html not found.")
        return

    with open("template.html", "r") as f:
        template_content = f.read()

    soup = BeautifulSoup(template_content, "html.parser")

    # --- Fetch & Inject ISRAMAR Forecast ---
    ISRAMAR_COORDS = {
        "haifa": {"lon": 35.0368, "lat": 32.9151},
        "tlv": {"lon": 34.70, "lat": 32.08},
    }
    isramar_data = {}
    for loc, coords in ISRAMAR_COORDS.items():
        print(f"Fetching ISRAMAR forecast for {loc}...")
        isramar_data[loc] = fetch_isramar_forecast(coords["lon"], coords["lat"])

        # Summary Card (uses ISRAMAR entry closest to current time)
        card_id = f"{loc}-swell-card"
        card_div = soup.find(id=card_id)
        if card_div:
            card_div.clear()
            result = create_swell_card_content(soup, isramar_data[loc])
            if result == "Data Unavailable":
                card_div.string = "Forecast Unavailable"
            else:
                content, timestamp = result
                # Wrap time label + card in a container
                wrapper = soup.new_tag("div", attrs={"class": "swell-card-wrapper"})
                time_label = soup.new_tag("div", attrs={"class": "swell-time"})
                time_label.string = timestamp
                wrapper.append(time_label)
                card_div.append(content)
                card_div.wrap(wrapper)

    inject_isramar_chart_data(soup, isramar_data.get("haifa"), isramar_data.get("tlv"))

    # --- Fetch & Inject Buoy Data ---
    print("Fetching Hadera buoy data...")
    buoy_data = fetch_buoy_data()
    buoy_div = soup.find(id="buoy-card")
    if buoy_div:
        buoy_div.clear()
        content = create_buoy_card_content(soup, buoy_data)
        if content == "Buoy Unavailable":
            buoy_div.string = "Buoy Unavailable"
        else:
            buoy_div.append(content)

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

        # TLV municipality live beach cameras
        municipality_tlv = [
            "https://streaming.therdteam.com/live/play.html?id=10006",  # Yafo North
            "https://streaming.therdteam.com/live/play.html?id=10004",  # Aviv Beach
            "https://streaming.therdteam.com/live/play.html?id=10005",  # Yafo South
            "https://streaming.therdteam.com/live/play.html?id=10007",  # Goldman
            "https://streaming.therdteam.com/live/play.html?id=10001",  # Gordon South
            "https://streaming.therdteam.com/live/play.html?id=10000",  # Gordon North
            "https://streaming.therdteam.com/live/play.html?id=10002",  # Hilton North
            "https://streaming.therdteam.com/live/play.html?id=10003",  # Hilton South
        ]
        for url in municipality_tlv:
            grid.append(create_iframe_tag(soup, url))

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
