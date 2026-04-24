from flask import Flask, render_template_string, request
import requests
from datetime import datetime

app = Flask(__name__)

class GapAnalyzer:
    def __init__(self):
        self.url = "https://www.kaia.sa/ext-api/flightsearch/flights"
        self.headers = {
            "Accept": "application/json",
            "Authorization": "Basic dGVzdGVyOlRoZVMzY3JldA==",
            "User-Agent": "Mozilla/5.0"
        }

    def fetch_quiet_periods(self, day, start_h, end_h):
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
            
            if not data: return []

            # استخراج أوقات الرحلات القادمة فقط
            flight_times = []
            for f in data:
                status = f.get('PublicRemark', {}).get('Code', '').upper()
                if status not in ['ARR', 'DLV', 'LND']:
                    dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                    flight_times.append(datetime.fromisoformat(dt_raw))

            flight_times.sort()
            
            quiet_periods = []
            for i in range(len(flight_times) - 1):
                diff = (flight_times[i+1] - flight_times[i]).total_seconds() / 60
                if diff > 15:
                    quiet_periods.append({
                        "start": flight_times[i].strftime('%H:%M'),
                        "end": flight_times[i+1].strftime('%H:%M'),
                        "duration": int(diff)
                    })
            return quiet_periods
        except:
            return "error"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quiet Hours Radar</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        :root {
            --bg-color: #050505;
            --card-bg: #121212;
            --accent-color: #00e5ff;
            --text-main: #e0e0e0;
            --text-dim: #757575;
        }
        body { 
            background-color: var(--bg-color); 
            color: var(--text-main); 
            font-family: 'Segoe UI', Roboto, sans-serif;
            padding: 20px;
            letter-spacing: -0.5px;
        }
        .header-title {
            font-weight: 800;
            color: var(--accent-color);
            text-transform: uppercase;
            font-size: 1.5rem;
            margin-bottom: 5px;
        }
        .search-panel {
            background-color: var(--card-bg);
            border: 1px solid #1f1f1f;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }
        .period-card {
            background-color: var(--card-bg);
            border-radius: 10px;
            padding: 18px 25px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            transition: transform 0.2s;
            border: 1px solid #1a1a1a;
        }
        .duration-tag {
            background-color: rgba(0, 229, 255, 0.1);
            color: var(--accent-color);
            padding: 6px 16px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.95rem;
            border: 1px solid rgba(0, 229, 255, 0.3);
        }
        .time-range {
            font-size: 1.6rem;
            font-weight: 600;
            font-family: monospace;
            display: flex;
            align-items: center;
        }
        .arrow-icon {
            color: var(--text-dim);
            margin: 0 20px;
            font-size: 1rem;
        }
        .form-control {
            background-color: #000;
            border: 1px solid #222;
            color: #fff;
            border-radius: 8px;
        }
        .form-control:focus {
            background-color: #000;
            border-color: var(--accent-color);
            color: #fff;
            box-shadow: none;
        }
        .btn-analyze {
            background-color: var(--accent-color);
            color: #000;
            font-weight: 800;
            border-radius: 8px;
            border: none;
            padding: 10px;
        }
        .btn-analyze:hover { background-color: #00b8cc; }
        .quiet-label { color: var(--text-dim); font-size: 0.8rem; margin-bottom: 10px; display: block; }
    </style>
</head>
<body class="container">
    <div class="text-center mb-5">
        <div class="header-title">أوقات لا يوجد بها رحلات</div>
        <div class="text-secondary small">نظام رصد فترات الراحة (أكثر من 15 دقيقة)</div>
    </div>

    <div class="search-panel shadow-sm mx-auto" style="max-width: 800px;">
        <form method="POST" class="row g-3 align-items-end">
            <div class="col-md-3 col-6">
                <label class="quiet-label">اليوم</label>
                <input type="number" name="day" class="form-control" value="{{ current_day }}">
            </div>
            <div class="col-md-3 col-6">
                <label class="quiet-label">من (ساعة)</label>
                <input type="text" name="start" class="form-control" value="06:00">
            </div>
            <div class="col-md-3 col-6">
                <label class="quiet-label">إلى (ساعة)</label>
                <input type="text" name="end" class="form-control" value="23:59">
            </div>
            <div class="col-md-3 col-6">
                <button type="submit" class="btn btn-analyze w-100">تحليل الآن</button>
            </div>
        </form>
    </div>

    <div class="mx-auto" style="max-width: 600px;">
        {% if results == "error" %}
            <div class="text-danger text-center">عذراً، تعذر الاتصال بالنظام</div>
        {% elif results %}
            <span class="quiet-label text-center mb-3">الفترات الزمنية المكتشفة</span>
            {% for p in results %}
            <div class="period-card">
                <div class="duration-tag">
                    {{ p.duration }} دقيقة
                </div>
                <div class="time-range">
                    <span>{{ p.end }}</span>
                    <span class="arrow-icon">◀</span>
                    <span>{{ p.start }}</span>
                </div>
            </div>
            {% endfor %}
        {% elif request.method == 'POST' %}
            <div class="text-center py-5">
                <div class="text-secondary">لا توجد أوقات راحة طويلة في هذا النطاق</div>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    now = datetime.now()
    results = None
    if request.method == 'POST':
        analyzer = GapAnalyzer()
        results = analyzer.fetch_quiet_periods(
            request.form.get('day'), 
            request.form.get('start'), 
            request.form.get('end')
        )
    
    return render_template_string(
        HTML_TEMPLATE, 
        results=results, 
        current_day=now.day
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
