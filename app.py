from flask import Flask, render_template, request, redirect
import os
import zipfile
import json
from datetime import datetime
from werkzeug.utils import secure_filename
from collections import defaultdict

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5 GB
ALLOWED_EXTENSIONS = {'zip'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_watch_events(json_data):
    events = []

    # Collect and sort all valid entries
    entries = []
    for entry in json_data:
        if "time" in entry and "subtitles" in entry:
            try:
                timestamp = datetime.strptime(entry["time"], "%Y-%m-%dT%H:%M:%S.%fZ")
                channel = entry["subtitles"][0]["name"]
                entries.append((timestamp, channel))
            except Exception:
                continue

    entries.sort(key=lambda x: x[0])

    # Estimate duration between views (max 30 min gap)
    for i in range(len(entries)):
        current_time, channel = entries[i]
        if i < len(entries) - 1:
            next_time = entries[i + 1][0]
            delta = (next_time - current_time).seconds // 60
            duration = delta if delta < 30 else 0
        else:
            duration = 0
        events.append({
            "timestamp": current_time.isoformat(),
            "channel": channel,
            "duration": duration
        })

    return events


@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        file.save(filepath)

        extract_path = os.path.join(app.config['UPLOAD_FOLDER'], "extracted")
        os.makedirs(extract_path, exist_ok=True)

        with zipfile.ZipFile(filepath, 'r') as zip_ref:
            zip_ref.extractall(extract_path)

        # Find JSON
        history_path = None
        for root, dirs, files in os.walk(extract_path):
            for file in files:
                if "Wiedergabeverlauf" in file and file.endswith(".json"):
                    history_path = os.path.join(root, file)
                    break
            if history_path:
                break

        if not history_path or not os.path.exists(history_path):
            return "Wiedergabeverlauf.json nicht gefunden."

        with open(history_path, encoding="utf-8") as f:
            json_data = json.load(f)

        events = extract_watch_events(json_data)

        # Collect top 100 channels by total duration
        channel_totals = defaultdict(int)
        for e in events:
            channel_totals[e["channel"]] += e["duration"]

        sorted_channels = sorted(channel_totals.items(), key=lambda x: -x[1])
        top_100_channels = [name for name, _ in sorted_channels[:100]]

        return render_template("result.html", watchEvents=events, top_channels=top_100_channels)

    return render_template("index.html")


import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
