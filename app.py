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
            'CAN': 'ملغاة'
        }
        return statuses.get(code, "مجدولة")

    def fetch_and_analyze(self, day, start_h, end_h):
        now = datetime.now()
        try:
            target_date = datetime(now.year, now.month, int(day))
            date_str = target_date.strftime('%Y-%m-%d')
            iso_start = f"{date_str}T{start_h}:00.000+03:00"
            iso_end = f"{date_str}T{end_h}:00.000+03:00"
            
            params = {
                "$filter": f"(EarlyOrDelayedDateTime ge {iso_start} and EarlyOrDelayedDateTime lt {iso_end}) and PublicRemark/Code ne 'NOP' and tolower(FlightNature) eq 'arrival' and Terminal eq 'T1' and (tolower(InternationalStatus) eq 'international')",
                "$orderby": "EarlyOrDelayedDateTime",
                "$count": "true"
            }
            
            response = requests.get(self.url, params=params, headers=self.headers, timeout=10)
            data = response.json().get('value', [])
            
            if not data: return None

            flights_list, delayed_count = [], 0
            flight_times = []
            hourly_stats = Counter()

            for f in data:
                # --- التعديل الجوهري بناءً على الـ Network في الصورة ---
                # المصدر الحقيقي لجهة القدوم هو RouteOriginAirport
                origin_obj = f.get('RouteOriginAirport', {})
                if not origin_obj: # احتياطاً نجرب الحقل الآخر
                    origin_obj = f.get('OriginAirport', {})
                
                # جلب المدينة (عربي أو انجليزي أو الكود)
                origin_city = origin_obj.get('CityNameAr') or origin_obj.get('CityNameEn') or origin_obj.get('IATACode') or "غير معروف"
                
                # جلب اسم شركة الطيران (Airline)
                airline_name = f.get('Airline', {}).get('NameAr') or f.get('Airline', {}).get('NameEn') or "طيران"

                status_code = f.get('PublicRemark', {}).get('Code', '').upper()
                dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                dt_obj = datetime.fromisoformat(dt_raw)
                
                flights_list.append({
                    "code": f.get('FullFlightNumber') or f"{f.get('OperatingAirline', {}).get('IATA', '')} {f.get('FlightNumber', '')}",
                    "airline": airline_name,
                    "origin": origin_city,
                    "status": self.get_status_ar(status_code),
                    "raw_status": status_code,
                    "time": dt_obj.strftime('%H:%M')
                })

                if status_code not in ['ARR', 'DLV', 'LND']:
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
    <title>محلل KAIA الذكي</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background-color: #0b0f19; color: #f1f5f9; font-family: 'Segoe UI', Tahoma, sans-serif; }
        .card-custom { background: #161c2d; border: 1px solid #2d3748; border-radius: 12px; padding: 1.5rem; }
        .table { --bs-table-bg: #161c2d; color: #f1f5f9; border-color: #2d3748; }
        .status-badge { padding: 5px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; }
        .airline-text { font-size: 0.75rem; color: #94a3b8; display: block; }
        .flight-code { font-size: 1.1rem; color: #38bdf8; font-weight: bold; }
    </style>
</head>
<body class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h3 class="text-info"><i class="fa-solid fa-plane-arrival me-2"></i> لوحة تحكم الرحلات - الصالة 1</h3>
        <div class="text-secondary small">{{ current_time }}</div>
    </div>

    <div class="card-custom mb-4 shadow-lg">
        <form method="POST" class="row g-3">
            <div class="col-md-3"><label class="small mb-1 text-secondary">يوم</label><input type="number" name="day" class="form-control bg-dark text-white border-secondary" value="{{ current_day }}"></div>
            <div class="col-md-3"><label class="small mb-1 text-secondary">البداية</label><input type="text" name="start" class="form-control bg-dark text-white border-secondary" value="06:00"></div>
            <div class="col-md-3"><label class="small mb-1 text-secondary">النهاية</label><input type="text" name="end" class="form-control bg-dark text-white border-secondary" value="23:59"></div>
            <div class="col-md-3 mt-4 mt-md-auto"><button type="submit" class="btn btn-primary w-100 fw-bold">تحديث الرادار</button></div>
        </form>
    </div>

    {% if results %}
    <div class="row g-3 mb-4 text-center">
        <div class="col-3"><div class="card-custom py-2 border-primary"><h6>الكل</h6><h3>{{ results.total }}</h3></div></div>
        <div class="col-3"><div class="card-custom py-2 border-warning text-warning"><h6>منتظرة</h6><h3>{{ results.waiting }}</h3></div></div>
        <div class="col-3"><div class="card-custom py-2 border-danger text-danger"><h6>تأخير</h6><h3>{{ results.delayed }}</h3></div></div>
        <div class="col-3"><div class="card-custom py-2 border-info text-info"><h6>الذروة</h6><h3>{{ results.peak_hour }}</h3></div></div>
    </div>

    <div class="card-custom p-0 overflow-hidden shadow-lg">
        <div class="table-responsive" style="max-height: 550px;">
            <table class="table table-hover align-middle mb-0">
                <thead class="bg-dark">
                    <tr class="text-secondary">
                        <th class="ps-4">الرحلة</th>
                        <th>قادمة من</th>
                        <th>الوقت</th>
                        <th>الحالة</th>
                    </tr>
                </thead>
                <tbody>
                    {% for f in results.flights %}
                    <tr>
                        <td class="ps-4">
                            <span class="flight-code">{{ f.code }}</span>
                            <span class="airline-text">{{ f.airline }}</span>
                        </td>
                        <td class="fw-bold text-info">{{ f.origin }}</td>
                        <td>{{ f.time }}</td>
                        <td>
                            <span class="status-badge 
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
