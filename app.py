from flask import Flask, render_template_string, request
import requests
from datetime import datetime
from collections import Counter

app = Flask(__name__)

class SmartQuietRadar:
    def __init__(self):
        self.url = "https://www.kaia.sa/ext-api/flightsearch/flights"
        self.headers = {
            "Accept": "application/json",
            "Authorization": "Basic dGVzdGVyOlRoZVMzY3JldA==",
            "User-Agent": "Mozilla/5.0"
        }

    def analyze_data(self, day, start_h, end_h):
        try:
            now = datetime.now()
            target_date = datetime(now.year, now.month, int(day))
            date_str = target_date.strftime('%Y-%m-%d')
            iso_start = f"{date_str}T{start_h}:00.000+03:00"
            iso_end = f"{date_str}T{end_h}:00.000+03:00"
            
            params = {
                "$filter": f"(EarlyOrDelayedDateTime ge {iso_start} and EarlyOrDelayedDateTime lt {iso_end}) and PublicRemark/Code ne 'NOP' and tolower(FlightNature) eq 'arrival' and Terminal eq 'T1' and (tolower(InternationalStatus) eq 'international')",
                "$orderby": "EarlyOrDelayedDateTime"
            }
            
            response = requests.get(self.url, params=params, headers=self.headers, timeout=10)
            data = response.json().get('value', [])
            
            if not data: return None

            flight_times = []
            hourly_counts = Counter()

            for f in data:
                status = f.get('PublicRemark', {}).get('Code', '').upper()
                # نأخذ جميع رحلات الجدول الزمني لتحليل الذروة
                dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                dt_obj = datetime.fromisoformat(dt_raw)
                flight_times.append(dt_obj)
                hourly_counts[dt_obj.hour] += 1

            flight_times.sort()
            
            # 1. تحديد وقت الذروة
            peak_hour = max(hourly_counts, key=hourly_counts.get)
            peak_info = {
                "range": f"{peak_hour:02d}:00 - {peak_hour+1:02d}:00",
                "count": hourly_counts[peak_hour]
            }

            # 2. تحديد أوقات الراحة (التي لم تصل بعد)
            quiet_periods = []
            # نفحص فقط الرحلات المنتظرة لحساب فترات الهدوء القادمة
            waiting_times = [t for t, f in zip(flight_times, data) if f.get('PublicRemark', {}).get('Code') not in ['ARR', 'DLV', 'LND']]
            waiting_times.sort()

            for i in range(len(waiting_times) - 1):
                diff = (waiting_times[i+1] - waiting_times[i]).total_seconds() / 60
                if diff > 15:
                    quiet_periods.append({
                        "start": waiting_times[i].strftime('%H:%M'),
                        "end": waiting_times[i+1].strftime('%H:%M'),
                        "duration": int(diff)
                    })

            return {"peak": peak_info, "quiet": quiet_periods}
        except:
            return "error"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quiet & Peak Radar</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        :root {
            --bg: #000000;
            --card: #0d0d0d;
            --accent: #00f2ff;
            --peak-bg: #1a1400;
            --peak-border: #ffcc00;
        }
        body { 
            background-color: var(--bg); 
            color: #ffffff; 
            font-family: 'Segoe UI', system-ui, sans-serif;
            padding: 20px;
        }
        .matte-card {
            background-color: var(--card);
            border: 1px solid #1a1a1a;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .peak-box {
            background-color: var(--peak-bg);
            border: 1px solid var(--peak-border);
            border-radius: 12px;
            padding: 15px;
            text-align: center;
            margin-bottom: 25px;
        }
        .peak-title { color: var(--peak-border); font-size: 0.8rem; font-weight: bold; text-transform: uppercase; }
        .peak-time { font-size: 1.8rem; font-weight: 800; margin: 5px 0; }
        .peak-count { font-size: 1rem; color: #ffeb99; }

        .quiet-card {
            background: linear-gradient(90deg, #0d0d0d 0%, #111 100%);
            border-radius: 10px;
            padding: 15px 20px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-right: 4px solid var(--accent);
        }
        .duration-pill {
            background-color: rgba(0, 242, 255, 0.1);
            color: var(--accent);
            padding: 4px 12px;
            border-radius: 6px;
            font-weight: bold;
            border: 1px solid rgba(0, 242, 255, 0.2);
        }
        .time-range { font-size: 1.5rem; font-weight: 600; font-family: monospace; }
        .arrow { color: #444; margin: 0 15px; }
        
        .form-control { background: #000; border: 1px solid #222; color: #fff; }
        .form-control:focus { background: #000; color: #fff; border-color: var(--accent); box-shadow: none; }
        .btn-run { background: var(--accent); color: #000; font-weight: 900; border: none; }
        .label-dim { color: #555; font-size: 0.75rem; margin-bottom: 5px; display: block; }
    </style>
</head>
<body class="container">
    <div class="text-center mb-4">
        <h3 style="letter-spacing: 1px;">رادار تحليل الحركة <span style="color: var(--accent);">T1</span></h3>
    </div>

    <div class="matte-card mx-auto" style="max-width: 800px;">
        <form method="POST" class="row g-2 align-items-end">
            <div class="col-md-3 col-6"><label class="label-dim">اليوم</label><input type="number" name="day" class="form-control" value="{{ current_day }}"></div>
            <div class="col-md-3 col-6"><label class="label-dim">من</label><input type="text" name="start" class="form-control" value="06:00"></div>
            <div class="col-md-3 col-6"><label class="label-dim">إلى</label><input type="text" name="end" class="form-control" value="23:59"></div>
            <div class="col-md-3 col-6"><button type="submit" class="btn btn-run w-100 py-2">تحديث</button></div>
        </form>
    </div>

    {% if data %}
    <div class="mx-auto" style="max-width: 600px;">
        <div class="peak-box shadow-lg">
            <div class="peak-title">⚠️ وقت الذروة (أعلى كثافة رحلات)</div>
            <div class="peak-time">{{ data.peak.range }}</div>
            <div class="peak-count">عدد الرحلات: <span style="font-size: 1.4rem;">{{ data.peak.count }}</span></div>
        </div>

        <div class="label-dim text-center mb-3">أوقات لا يوجد بها رحلات (> 15 دقيقة)</div>
        
        {% for p in data.quiet %}
        <div class="quiet-card">
            <div class="duration-pill">{{ p.duration }} دقيقة</div>
            <div class="time-range">
                <span>{{ p.end }}</span>
                <span class="arrow">◀</span>
                <span>{{ p.start }}</span>
            </div>
        </div>
        {% else %}
        <p class="text-center text-secondary py-4">لا توجد فترات هدوء طويلة حالياً</p>
        {% endfor %}
    </div>
    {% endif %}
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    now = datetime.now()
    results = None
    if request.method == 'POST':
        analyzer = SmartQuietRadar()
        results = analyzer.analyze_data(request.form.get('day'), request.form.get('start'), request.form.get('end'))
    return render_template_string(HTML_TEMPLATE, data=results, current_day=now.day)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
