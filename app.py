from flask import Flask, render_template, request
import requests
from datetime import datetime
from collections import Counter
import os

app = Flask(__name__)

class FlightAnalyzer:
    def __init__(self):
        self.url = "https://www.kaia.sa/ext-api/flightsearch/flights"
        self.headers = {
            "Accept": "application/json",
            "Authorization": "Basic dGVzdGVyOlRoZVMzY3JldA==",
            "User-Agent": "Mozilla/5.0"
        }

    def fetch_and_analyze(self, day, start_h, end_h):
        now = datetime.now()
        try:
            target_date = datetime(now.year, now.month, int(day))
            date_str = target_date.strftime('%Y-%m-%d')
            iso_start = f"{date_str}T{start_h}:00.000+03:00"
            iso_end = f"{date_str}T{end_h}:00.000+03:00"
            limit_end_dt = datetime.fromisoformat(f"{date_str}T{end_h}")
            
            params = {
                "$filter": f"(EarlyOrDelayedDateTime ge {iso_start} and EarlyOrDelayedDateTime lt {iso_end}) and PublicRemark/Code ne 'NOP' and tolower(FlightNature) eq 'arrival' and Terminal eq 'T1' and (tolower(InternationalStatus) eq 'international')",
                "$orderby": "EarlyOrDelayedDateTime",
                "$count": "true"
            }
            
            response = requests.get(self.url, params=params, headers=self.headers, timeout=10)
            data = response.json().get('value', [])
            
            if not data: return None

            total_received = len(data)
            flight_times = []
            delayed_count = 0
            hourly_stats = Counter()

            for f in data:
                status_code = f.get('PublicRemark', {}).get('Code', '').upper()
                if status_code in ['ARR', 'DLV', 'LND']: continue

                dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                dt_obj = datetime.fromisoformat(dt_raw)
                if dt_obj >= limit_end_dt: continue

                flight_times.append(dt_obj)
                hourly_stats[dt_obj.hour] += 1
                if status_code == 'DEL': delayed_count += 1

            flight_times.sort()
            gaps = []
            for i in range(len(flight_times) - 1):
                diff = (flight_times[i+1] - flight_times[i]).total_seconds() / 60
                if diff > 15:
                    gaps.append({"from": flight_times[i].strftime('%H:%M'), "to": flight_times[i+1].strftime('%H:%M'), "duration": int(diff)})

            peak_hour = max(hourly_stats, key=hourly_stats.get) if hourly_stats else None

            return {
                "date": date_str,
                "total": total_received,
                "waiting": len(flight_times),
                "arrived": total_received - len(flight_times),
                "delayed": delayed_count,
                "peak_hour": f"{peak_hour:02d}:00" if peak_hour is not None else "N/A",
                "peak_count": hourly_stats[peak_hour] if peak_hour is not None else 0,
                "gaps": gaps
            }
        except:
            return "error"

@app.route('/', methods=['GET', 'POST'])
def index():
    results = None
    if request.method == 'POST':
        day = request.form.get('day')
        start = request.form.get('start')
        end = request.form.get('end')
        analyzer = FlightAnalyzer()
        results = analyzer.fetch_and_analyze(day, start, end)
    
    return render_template('index.html', results=results)

if __name__ == '__main__':
    app.run(debug=True)
