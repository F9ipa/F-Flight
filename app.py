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

            # تحويل البيانات إلى كائنات datetime وفرزها زمنياً
            all_flights = []
            for f in data:
                dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                all_flights.append({
                    "time": datetime.fromisoformat(dt_raw),
                    "status": f.get('PublicRemark', {}).get('Code', '').upper()
                })
            
            # ترتيب الرحلات زمنياً لضمان دقة التحليل
            all_flights.sort(key=lambda x: x['time'])

            # 1. تحليل ساعة الذروة (بناءً على توزيع الرحلات في النطاق المختار)
            hourly_counts = Counter(f['time'].hour for f in all_flights)
            peak_hour = max(hourly_counts, key=hourly_counts.get)
            peak_info = {
                "range": f"{peak_hour:02d}:00 - {peak_hour+1:02d}:00",
                "count": hourly_counts[peak_hour]
            }

            # 2. تحليل "أوقات لا يوجد بها رحلات" (مرتبة زمنياً)
            # نأخذ فقط الرحلات التي لم تصل بعد لحساب أوقات الراحة المستقبلية
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
            
            # التأكد من ترتيب أوقات الراحة من الأقرب إلى الأبعد زمنياً
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
    <title>Quiet & Peak Radar</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        :root {
            --bg: #000000;
            --card-matte: #0a0a0a;
            --accent-cyan: #00f2ff;
            --peak-gold: #ffcc00;
        }
        body { 
            background-color: var(--bg); 
            color: #ffffff; 
            font-family: 'Segoe UI', system-ui, sans-serif;
            padding: 20px;
        }
        .search-container {
            background-color: var(--card-matte);
            border: 1px solid #1a1a1a;
            border-radius: 16px;
            padding: 25px;
            margin-bottom: 30px;
        }
        .peak-card {
            background: linear-gradient(145deg, #1a1400, #0a0a0a);
            border: 1px solid var(--peak-gold);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(255, 204, 0, 0.05);
        }
        .quiet-item {
            background-color: var(--card-matte);
            border: 1px solid #1a1a1a;
            border-radius: 12px;
            padding: 18px 25px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-right: 4px solid var(--accent-cyan);
        }
        .duration-text {
            background: rgba(0, 242, 255, 0.1);
            color: var(--accent-cyan);
            padding: 5px 15px;
            border-radius: 8px;
            font-weight: 800;
            font-size: 1.1rem;
        }
        .time-display {
            font-size: 1.6rem;
            font-weight: 700;
            letter-spacing: 1px;
            color: #f0f0f0;
        }
        .arrow-sep { color: #333; margin: 0 15px; font-size: 1rem; }
        .form-label { color: #555; font-size: 0.8rem; font-weight: bold; margin-bottom: 8px; }
        .form-control { background: #000; border: 1px solid #222; color: #fff; border-radius: 10px; padding: 12px; }
        .form-control:focus { border-color: var(--accent-cyan); box-shadow: none; background: #000; color: #fff; }
        .btn-update { background: var(--accent-cyan); color: #000; font-weight: 900; border-radius: 10px; border: none; padding: 12px; }
    </style>
</head>
<body class="container">
    <div class="text-center mb-5">
        <h2 class="fw-bold">تحليل الحركة الزمنية <span style="color: var(--accent-cyan);">T1</span></h2>
    </div>

    <div class="search-container mx-auto" style="max-width: 850px;">
        <form method="POST" class="row g-3 align-items-end">
            <div class="col-md-3 col-6"><label class="form-label">اليوم</label><input type="number" name="day" class="form-control" value="{{ current_day }}"></div>
            <div class="col-md-3 col-6"><label class="form-label">بداية الوقت</label><input type="text" name="start" class="form-control" value="06:00"></div>
            <div class="col-md-3 col-6"><label class="form-label">نهاية الوقت</label><input type="text" name="end" class="form-control" value="23:59"></div>
            <div class="col-md-3 col-6"><button type="submit" class="btn btn-update w-100">تحديث البيانات</button></div>
        </form>
    </div>

    {% if data %}
    <div class="mx-auto" style="max-width: 650px;">
        <div class="peak-card">
            <div style="color: var(--peak-gold); font-size: 0.9rem; font-weight: bold;">ساعة الذروة القصوى</div>
            <div style="font-size: 2.2rem; font-weight: 900; margin: 10px 0;">{{ data.peak.range }}</div>
            <div style="color: #aaa;">كثافة الرحلات: <span style="color: #fff; font-size: 1.5rem;">{{ data.peak.count }}</span> رحلات</div>
        </div>

        <div class="text-secondary small mb-3 text-center">أوقات لا يوجد بها رحلات (مرتبة زمنياً)</div>

        {% for p in data.quiet %}
        <div class="quiet-item shadow-sm">
            <div class="duration-text">{{ p.duration }} دقيقة</div>
            <div class="time-display">
                <span>{{ p.end }}</span>
                <span class="arrow-sep">◀</span>
                <span>{{ p.start }}</span>
            </div>
        </div>
        {% else %}
        <div class="text-center py-5 text-secondary">لا توجد فترات راحة تتجاوز 15 دقيقة</div>
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
