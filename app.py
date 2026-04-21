from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime, timedelta
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

    def fetch_data(self, start_h, end_h):
        # توقيت السعودية GMT+3 لضمان دقة التاريخ في Render
        now_saudi = datetime.utcnow() + timedelta(hours=3)
        date_str = now_saudi.strftime('%Y-%m-%d')
        
        iso_start = f"{date_str}T{start_h}:00.000+03:00"
        iso_end = f"{date_str}T{end_h}:00.000+03:00"

        params = {
            "$filter": f"(EarlyOrDelayedDateTime ge {iso_start} and EarlyOrDelayedDateTime lt {iso_end}) and PublicRemark/Code ne 'NOP' and tolower(FlightNature) eq 'arrival' and Terminal eq 'T1' and (tolower(InternationalStatus) eq 'international')",
            "$orderby": "EarlyOrDelayedDateTime",
            "$count": "true"
        }
        
        try:
            response = requests.get(self.url, params=params, headers=self.headers, timeout=15)
            return response.json().get('value', [])
        except:
            return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    req_data = request.json
    start_h = req_data.get('start', '01:00')
    end_h = req_data.get('end', '23:59')
    
    analyzer = FlightAnalyzer()
    raw_data = analyzer.fetch_data(start_h, end_h)
    
    flights_list = []
    flight_times = []
    hourly_stats = Counter()

    for f in raw_data:
        status_info = f.get('PublicRemark', {})
        status_code = (status_info.get('Code') or '').upper()
        
        try:
            raw_time = f.get('EarlyOrDelayedDateTime').split('+')[0]
            dt_obj = datetime.fromisoformat(raw_time)
        except:
            continue
            
        is_delayed = (status_code == 'DEL')
        
        # جلب جهة الإقلاع (المغادرة) بشكل صحيح
        origin = f.get('OriginPersianName') or f.get('OriginEnglishName') or "غير معروف"
        
        flights_list.append({
            "time": dt_obj.strftime('%H:%M'),
            "origin": origin, # هذه ستظهر في خانة جهة الإقلاع
            "flight_no": f.get('FlightNumber'),
            "status": status_info.get('DescriptionAr', 'في موعدها'),
            "is_delayed": is_delayed
        })

        if status_code not in ['ARR', 'DLV', 'LND']:
            flight_times.append(dt_obj)
            hourly_stats[dt_obj.hour] += 1

    peak_data = None
    if hourly_stats:
        peak_hour = max(hourly_stats, key=hourly_stats.get)
        peak_data = {
            "time": f"{peak_hour:02d}:00 - {peak_hour+1:02d}:00",
            "count": hourly_stats[peak_hour]
        }

    gaps_list = []
    flight_times.sort()
    for i in range(len(flight_times) - 1):
        diff = (flight_times[i+1] - flight_times[i]).total_seconds() / 60
        if diff > 15:
            gaps_list.append({
                "from": flight_times[i].strftime('%H:%M'),
                "to": flight_times[i+1].strftime('%H:%M'),
                "duration": int(diff)
            })

    return jsonify({"flights": flights_list, "peak": peak_data, "gaps": gaps_list})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
