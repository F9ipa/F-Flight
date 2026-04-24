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
            data = response.json().get('value', [])
            
            if not data: return None

            flight_times, flights_list, delayed_count = [], [], 0
            hourly_stats = Counter()

            for f in data:
                # --- المنطق الذكي الجديد لجلب جهة القدوم ---
                origin_obj = f.get('OriginAirport', {})
                # نجرب جلب الاسم بالترتيب: مدينة عربي -> مدينة انجليزي -> اسم مطار عربي -> كود المطار
                origin_city = (
                    origin_obj.get('CityNameAr') or 
                    origin_obj.get('CityNameEn') or 
                    origin_obj.get('AirportNameAr') or 
                    origin_obj.get('IATACode') or 
                    "غير معروف"
                )
                
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
            print(f"Error detail: {e}")
            return "error"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KAIA Radar - الصالة 1</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --bg: #0b0f19; --card: #161c2d; --accent: #38bdf8; }
        body { background-color: var(--bg); color: #f1f5f9; font-family: 'Segoe UI', sans-serif; }
        .dashboard-card { background: var(--card); border-radius: 15px; border: 1px solid #2d3748; padding: 1.5rem; }
        .btn-primary { background: var(--accent); border: none; font-weight: bold; }
        .status-pill { padding: 4px 12px; border-radius: 50px; font-size: 0.8rem; }
        .table { color: #cbd5e1; vertical-align: middle; }
        .text-accent { color: var(--accent); }
        .table-hover tbody tr:hover { background-color: #1e293b; }
    </style>
</head>
<body class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h4 class="text-accent fw-bold"><i class="fa-solid fa-plane-arrival me-2"></i> رادار الرحلات الدولية - T1</h4>
        <div class="badge bg-dark border border-secondary p-2">{{ current_time }}</div>
    </div>

    <div class="dashboard-card mb-4 shadow">
        <form method="POST" class="row g-3 align-items-end">
            <div class="col-md-3"><label class="small text-secondary mb-1">📅 يوم الاستعلام</label><input type="number" name="day" class="form-control bg-dark text-white border-secondary" value="{{ current_day }}"></div>
            <div class="col-md-3"><label class="small text-secondary mb-1">🕒 من ساعة</label><input type="text" name="start" class="form-control bg-dark text-white border-secondary" value="06:00"></div>
            <div class="col-md-3"><label class="small text-secondary mb-1">🕒 إلى ساعة</label><input type="text" name="end" class="form-control bg-dark text-white border-secondary" value="23:59"></div>
            <div class="col-md-3"><button type="submit" class="btn btn-primary w-100">تحديث الرادار</button></div>
        </form>
    </div>

    {% if results %}
    <div class="row g-3 mb-4 text-center">
        <div class="col-3"><div class="dashboard-card"><div class="text-secondary small">الكل</div><div class="h3 mb-0">{{ results.total }}</div></div></div>
        <div class="col-3"><div class="dashboard-card"><div class="text-secondary small text-warning">منتظرة</div><div class="h3 mb-0 text-warning">{{ results.waiting }}</div></div></div>
        <div class="col-3"><div class="dashboard-card"><div class="text-secondary small text-danger">متأخرة</div><div class="h3 mb-0 text-danger">{{ results.delayed }}</div></div></div>
        <div class="col-3"><div class="dashboard-card"><div class="text-secondary small text-info">الذروة</div><div class="h3 mb-0 text-info">{{ results.peak_hour }}</div></div></div>
    </div>

    <div class="dashboard-card p-0 shadow overflow-hidden">
        <div class="table-responsive" style="max-height: 600px;">
            <table class="table table-hover mb-0">
                <thead class="bg-dark text-secondary small">
                    <tr>
                        <th class="ps-4 py-3">الرحلة</th>
                        <th class="py-3">قادمة من</th>
                        <th class="py-3">الموعد</th>
                        <th class="py-3">الحالة</th>
                    </tr>
                </thead>
                <tbody>
                    {% for f in results.flights %}
                    <tr style="border-bottom: 1px solid #2d3748;">
                        <td class="ps-4 fw-bold text-white">{{ f.code }}</td>
                        <td class="text-accent fw-medium">{{ f.origin }}</td>
                        <td>{{ f.time }}</td>
                        <td>
                            <span class="status-pill 
                                {% if f.raw_status == 'DEL' %}bg-danger bg-opacity-20 text-danger
                                {% elif f.raw_status in ['ARR', 'LND', 'DLV'] %}bg-success bg-opacity-20 text-success
                                {% elif f.raw_status == 'WIL' %}bg-warning bg-opacity-20 text-warning
                                {% else %}bg-primary bg-opacity-20 text-info{% endif %}">
                                {{ f.status }}
                            </span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
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
