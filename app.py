from flask import Flask, render_template_string, request
import requests
from datetime import datetime
from collections import Counter

app = Flask(__name__)

class FlightAnalyzer:
    def __init__(self):
        self.url = "https://www.kaia.sa/ext-api/flightsearch/flights"
        self.headers = {
            "Accept": "application/json",
            "Authorization": "Basic dGVzdGVyOlRoZVMzY3JldA==",
            "User-Agent": "Mozilla/5.0"
        }

    def get_status_ar(self, code):
        statuses = {
            'SCH': 'في موعدها', 'DEL': 'متأخرة', 'WIL': 'على وشك الهبوط',
            'LND': 'هبطت', 'ARR': 'وصلت', 'DLV': 'تم تسليم العفش',
            'CAN': 'ملغاة', 'EST': 'وقت تقديري'
        }
        return statuses.get(code, "مجدولة")

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
            json_data = response.json()
            data = json_data.get('value', [])
            
            if not data: return None

            flight_times, flights_list, delayed_count = [], [], 0
            hourly_stats = Counter()

            for f in data:
                # استخراج جهة القدوم بدقة من الـ API
                origin_info = f.get('OriginAirport', {})
                # نحاول جلب الاسم العربي، ثم الإنجليزي، ثم الكود الدولي للمطار
                origin_city = origin_info.get('CityNameAr') or origin_info.get('CityNameEn') or origin_info.get('IATACode') or "غير معروف"
                
                status_code = f.get('PublicRemark', {}).get('Code', '').upper()
                dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                dt_obj = datetime.fromisoformat(dt_raw)
                
                flights_list.append({
                    "code": f"{f.get('OperatingAirline', {}).get('IATA', '')} {f.get('FlightNumber', '')}",
                    "origin": origin_city,
                    "status": self.get_status_ar(status_code),
                    "raw_status": status_code,
                    "time": dt_obj.strftime('%H:%M')
                })

                if status_code not in ['ARR', 'DLV', 'LND'] and dt_obj < limit_end_dt:
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
                "total": len(data), "waiting": len(flight_times), "delayed": delayed_count,
                "peak_hour": f"{peak_hour:02d}:00" if peak_hour is not None else "--",
                "peak_count": hourly_stats[peak_hour] if peak_hour is not None else 0,
                "gaps": gaps, "flights": flights_list
            }
        except Exception as e:
            print(f"Error: {e}")
            return "error"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KAIA Smart Dashboard</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --bg: #0b0f19; --card: #161c2d; --text: #f1f5f9; --accent: #38bdf8; }
        body { background-color: var(--bg); color: var(--text); font-family: system-ui, -apple-system, sans-serif; }
        .dashboard-card { background: var(--card); border-radius: 12px; border: 1px solid #2d3748; padding: 1.25rem; }
        .form-control { background: #0b0f19; border: 1px solid #2d3748; color: white; border-radius: 8px; }
        .btn-primary { background: var(--accent); border: none; font-weight: 600; }
        .status-pill { padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; }
        .table-responsive { border-radius: 12px; border: 1px solid #2d3748; }
        .table { --bs-table-bg: transparent; color: var(--text); margin-bottom: 0; }
        .text-info-custom { color: var(--accent); }
    </style>
</head>
<body class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h4 class="text-info-custom fw-bold"><i class="fa-solid fa-tower-observation me-2"></i> رادار الصالة 1</h4>
        <div class="small text-secondary">{{ current_time }}</div>
    </div>

    <div class="dashboard-card mb-4">
        <form method="POST" class="row g-2 align-items-end">
            <div class="col-md-3"><label class="small text-secondary">يوم</label><input type="number" name="day" class="form-control form-control-sm" value="{{ current_day }}"></div>
            <div class="col-md-3"><label class="small text-secondary">من</label><input type="text" name="start" class="form-control form-control-sm" value="06:00"></div>
            <div class="col-md-3"><label class="small text-secondary">إلى</label><input type="text" name="end" class="form-control form-control-sm" value="23:59"></div>
            <div class="col-md-3"><button type="submit" class="btn btn-primary btn-sm w-100">تحديث</button></div>
        </form>
    </div>

    {% if results %}
    <div class="row g-3 mb-4 text-center">
        <div class="col-3"><div class="dashboard-card py-2"><div class="small text-secondary">الكل</div><div class="h4 mb-0">{{ results.total }}</div></div></div>
        <div class="col-3"><div class="dashboard-card py-2"><div class="small text-secondary">منتظرة</div><div class="h4 mb-0 text-warning">{{ results.waiting }}</div></div></div>
        <div class="col-3"><div class="dashboard-card py-2"><div class="small text-secondary">تأخير</div><div class="h4 mb-0 text-danger">{{ results.delayed }}</div></div></div>
        <div class="col-3"><div class="dashboard-card py-2"><div class="small text-secondary">ذروة</div><div class="h4 mb-0">{{ results.peak_hour }}</div></div></div>
    </div>

    <div class="table-responsive bg-card shadow-sm">
        <table class="table table-hover">
            <thead class="bg-dark text-secondary small">
                <tr>
                    <th class="ps-3">الرحلة</th>
                    <th>القادمة من</th>
                    <th>الموعد</th>
                    <th>الحالة</th>
                </tr>
            </thead>
            <tbody class="small">
                {% for f in results.flights %}
                <tr>
                    <td class="ps-3 fw-bold">{{ f.code }}</td>
                    <td class="text-info-custom">{{ f.origin }}</td>
                    <td>{{ f.time }}</td>
                    <td>
                        <span class="status-pill 
                            {% if f.raw_status == 'DEL' %}bg-danger bg-opacity-10 text-danger
                            {% elif f.raw_status in ['ARR', 'LND', 'DLV'] %}bg-success bg-opacity-10 text-success
                            {% else %}bg-primary bg-opacity-10 text-info{% endif %}">
                            {{ f.status }}
                        </span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
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
        analyzer = FlightAnalyzer()
        results = analyzer.fetch_and_analyze(request.form.get('day'), request.form.get('start'), request.form.get('end'))
    
    return render_template_string(HTML_TEMPLATE, results=results, current_day=now.day, current_time=now.strftime('%H:%M'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
