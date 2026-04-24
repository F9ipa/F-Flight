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

            all_flights = []
            for f in data:
                dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                all_flights.append({
                    "time": datetime.fromisoformat(dt_raw),
                    "status": f.get('PublicRemark', {}).get('Code', '').upper()
                })
            
            # ترتيب الرحلات زمنياً لضمان دقة تحليل الفجوات
            all_flights.sort(key=lambda x: x['time'])

            # 1. تحليل ساعة الذروة
            hourly_counts = Counter(f['time'].hour for f in all_flights)
            peak_hour = max(hourly_counts, key=hourly_counts.get)
            peak_info = {
                "range": f"{peak_hour:02d}:00 - {peak_hour+1:02d}:00",
                "count": hourly_counts[peak_hour]
            }

            # 2. تحليل أوقات عدم وجود رحلات (المرتبة زمنياً)
            waiting_times = [f['time'] for f in all_flights if f['status'] not in ['ARR', 'DLV', 'LND']]
            
            quiet_periods = []
            for i in range(len(waiting_times) - 1):
                diff = (waiting_times[i+1] - waiting_times[i]).total_seconds() / 60
                if diff > 15:
                    quiet_periods.append({
                        "start": waiting_times[i].strftime('%H:%M'),
                        "end": waiting_times[i+1].strftime('%H:%M'),
                        "duration": int(diff),
                        "sort_key": waiting_times[i]
                    })
            
            quiet_periods.sort(key=lambda x: x['sort_key'])
            return {"peak": peak_info, "quiet": quiet_periods}
        except:
            return "error"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>رادار أوقات الراحة الذكي</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        :root {
            --bg: #000000;
            --card-matte: #0d0d0d;
            --accent: #00f2ff;
            --peak-gold: #ffcc00;
        }
        body { 
            background-color: var(--bg); 
            color: #ffffff; 
            font-family: system-ui, -apple-system, sans-serif;
            padding: 15px;
        }
        .search-container {
            background-color: var(--card-matte);
            border: 1px solid #1a1a1a;
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 25px;
        }
        .peak-card {
            background: linear-gradient(145deg, #1a1400, #0a0a0a);
            border: 1px solid var(--peak-gold);
            border-radius: 18px;
            padding: 20px;
            text-align: center;
            margin-bottom: 25px;
        }
        .quiet-item {
            background-color: var(--card-matte);
            border-radius: 14px;
            padding: 15px 20px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-right: 4px solid var(--accent);
        }
        .duration-badge {
            background: rgba(0, 242, 255, 0.15);
            color: var(--accent);
            padding: 6px 14px;
            border-radius: 8px;
            font-weight: 800;
            font-size: 1rem;
        }
        .time-text {
            font-size: 1.5rem;
            font-weight: 700;
            font-family: monospace;
        }
        .arrow { color: #444; margin: 0 12px; }
        .form-label { color: #777; font-size: 0.85rem; margin-bottom: 8px; display: block; }
        .form-control { background: #000; border: 1px solid #222; color: #fff; border-radius: 12px; padding: 10px; text-align: center; }
        .btn-update { background: var(--accent); color: #000; font-weight: 900; border-radius: 12px; border: none; padding: 12px; width: 100%; margin-top: 10px; }
    </style>
</head>
<body class="container">
    <div class="text-center mt-3 mb-4">
        <h4 class="fw-bold">رادار تحليل الحركة <span style="color: var(--accent);">T1</span></h4>
    </div>

    <div class="search-container mx-auto" style="max-width: 500px;">
        <form method="POST">
            <div class="row g-2">
                <div class="col-4">
                    <label class="form-label">اليوم</label>
                    <input type="number" name="day" class="form-control" value="{{ selected_day }}">
                </div>
                <div class="col-4">
                    <label class="form-label">بداية الوقت</label>
                    <input type="text" name="start" class="form-control" value="{{ selected_start }}">
                </div>
                <div class="col-4">
                    <label class="form-label">نهاية الوقت</label>
                    <input type="text" name="end" class="form-control" value="{{ selected_end }}">
                </div>
            </div>
            <button type="submit" class="btn btn-update">تحديث البيانات</button>
        </form>
    </div>

    {% if data %}
    <div class="mx-auto" style="max-width: 500px;">
        <div class="peak-card shadow">
            <div style="color: var(--peak-gold); font-size: 0.8rem; font-weight: bold;">ساعة الذروة المتوقعة</div>
            <div style="font-size: 2rem; font-weight: 900; margin: 5px 0;">{{ data.peak.range }}</div>
            <div style="color: #888;">الكثافة: <span style="color: #fff; font-size: 1.2rem;">{{ data.peak.count }}</span> رحلات</div>
        </div>

        <div class="text-center text-secondary small mb-3">أوقات لا يوجد بها رحلات (> 15 د)</div>

        {% for p in data.quiet %}
        <div class="quiet-item shadow-sm">
            <div class="duration-badge">{{ p.duration }} دقيقة</div>
            <div class="time-text">
                <span>{{ p.end }}</span>
                <span class="arrow">◀</span>
                <span>{{ p.start }}</span>
            </div>
        </div>
        {% else %}
        <div class="text-center py-5 text-secondary">لا توجد أوقات راحة طويلة حالياً</div>
        {% endfor %}
    </div>
    {% endif %}
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    now = datetime.now()
    # قيم افتراضية تلقائية بناءً على الوقت الحالي
    current_day = now.day
    current_hour = now.strftime('%H:00')
    default_end = "23:59"

    # استخدام القيم المرسلة أو الافتراضية
    day = request.form.get('day', current_day)
    start = request.form.get('start', current_hour)
    end = request.form.get('end', default_end)

    results = None
    if request.method == 'POST' or request.args.get('auto'):
        analyzer = SmartQuietRadar()
        results = analyzer.analyze_data(day, start, end)
    
    return render_template_string(
        HTML_TEMPLATE, 
        data=results, 
        selected_day=day, 
        selected_start=start, 
        selected_end=end
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
