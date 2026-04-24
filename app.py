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

    def fetch_gaps(self, day, start_h, end_h):
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

            # استخراج الأوقات فقط للرحلات التي لم تصل بعد (مجدولة أو متأخرة)
            flight_times = []
            for f in data:
                status = f.get('PublicRemark', {}).get('Code', '').upper()
                if status not in ['ARR', 'DLV', 'LND']:
                    dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                    flight_times.append(datetime.fromisoformat(dt_raw))

            flight_times.sort()
            
            gaps = []
            for i in range(len(flight_times) - 1):
                diff = (flight_times[i+1] - flight_times[i]).total_seconds() / 60
                if diff > 15:
                    gaps.append({
                        "from": flight_times[i].strftime('%H:%M'),
                        "to": flight_times[i+1].strftime('%H:%M'),
                        "duration": int(diff)
                    })
            return gaps
        except:
            return "error"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>رادار الفجوات الزمنية</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        body { 
            background-color: #000000; 
            color: #ffffff; 
            font-family: sans-serif;
            padding-top: 20px;
        }
        .search-section {
            background-color: #0a0a0a;
            border: 1px solid #1a1a1a;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
        }
        .gap-card {
            background-color: #111827; /* لون مقارب للصورة المرفقة */
            border-radius: 12px;
            padding: 15px 20px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-right: 5px solid #38bdf8;
        }
        .duration-badge {
            background-color: #22d3ee;
            color: #000000;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9rem;
        }
        .time-text {
            font-size: 1.4rem;
            font-weight: 500;
            letter-spacing: 1px;
        }
        .separator {
            color: #64748b;
            margin: 0 15px;
        }
        .form-control {
            background-color: #000;
            border: 1px solid #333;
            color: #fff;
        }
        .form-control:focus {
            background-color: #000;
            color: #fff;
            border-color: #38bdf8;
            box-shadow: none;
        }
        .btn-submit {
            background-color: #38bdf8;
            border: none;
            font-weight: bold;
            color: #000;
        }
    </style>
</head>
<body class="container">
    <div class="text-center mb-4">
        <h2 style="color: #38bdf8;">تحليل الفجوات الزمنية</h2>
        <p class="text-secondary">عرض الفترات التي تزيد عن 15 دقيقة بدون رحلات</p>
    </div>

    <div class="search-section shadow">
        <form method="POST" class="row g-3 align-items-end">
            <div class="col-md-3">
                <label class="small text-secondary mb-1">اليوم</label>
                <input type="number" name="day" class="form-control" value="{{ current_day }}">
            </div>
            <div class="col-md-3">
                <label class="small text-secondary mb-1">من الساعة</label>
                <input type="text" name="start" class="form-control" value="06:00">
            </div>
            <div class="col-md-3">
                <label class="small text-secondary mb-1">إلى الساعة</label>
                <input type="text" name="end" class="form-control" value="23:59">
            </div>
            <div class="col-md-3">
                <button type="submit" class="btn btn-submit w-100">تحليل الفجوات</button>
            </div>
        </form>
    </div>

    <div class="mx-auto" style="max-width: 600px;">
        {% if gaps == "error" %}
            <div class="alert alert-danger bg-dark text-danger border-0">حدث خطأ في جلب البيانات</div>
        {% elif gaps %}
            {% for gap in gaps %}
            <div class="gap-card shadow-sm">
                <div class="duration-badge">
                    {{ gap.duration }} دقيقة
                </div>
                <div class="time-text">
                    <span>{{ gap.to }}</span>
                    <span class="separator">〈</span>
                    <span>{{ gap.from }}</span>
                </div>
            </div>
            {% endfor %}
        {% elif request.method == 'POST' %}
            <div class="text-center text-secondary py-5">
                <h4>لا توجد فجوات تزيد عن 15 دقيقة</h4>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    now = datetime.now()
    gaps = None
    if request.method == 'POST':
        analyzer = GapAnalyzer()
        gaps = analyzer.fetch_gaps(
            request.form.get('day'), 
            request.form.get('start'), 
            request.form.get('end')
        )
    
    return render_template_string(
        HTML_TEMPLATE, 
        gaps=gaps, 
        current_day=now.day
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
