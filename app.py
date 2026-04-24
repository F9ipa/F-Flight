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
            'CAN': 'ملغاة', 'EST': 'تقديرية'
        }
        return statuses.get(code, "مجدولة")

    def extract_city(self, flight_data):
        sources = [
            flight_data.get('RouteOriginAirport', {}),
            flight_data.get('OriginAirport', {}),
            flight_data.get('Airport', {}),
            flight_data.get('RouteDestinationAirport', {})
        ]
        for src in sources:
            if src:
                city = src.get('CityNameAr') or src.get('AirportNameAr') or src.get('CityNameEn')
                if city: return city
        return flight_data.get('OriginAirport', {}).get('IATACode') or "غير معروف"

    def fetch_and_analyze(self, day, start_h, end_h):
        try:
            now = datetime.now()
            target_date = datetime(now.year, now.month, int(day))
            date_str = target_date.strftime('%Y-%m-%d')
            iso_start = f"{date_str}T{start_h}:00.000+03:00"
            iso_end = f"{date_str}T{end_h}:00.000+03:00"
            
            params = {
                "$filter": f"(EarlyOrDelayedDateTime ge {iso_start} and EarlyOrDelayedDateTime lt {iso_end}) and PublicRemark/Code ne 'NOP' and tolower(FlightNature) eq 'arrival' and Terminal eq 'T1' and (tolower(InternationalStatus) eq 'international')",
                "$orderby": "EarlyOrDelayedDateTime", "$count": "true"
            }
            
            response = requests.get(self.url, params=params, headers=self.headers, timeout=10)
            data = response.json().get('value', [])
            if not data: return None

            flights_list, flight_times = [], []
            delayed_count = 0
            hourly_stats = Counter()

            for f in data:
                origin_city = self.extract_city(f)
                airline = f.get('Airline', {}).get('NameAr') or f.get('Airline', {}).get('NameEn') or "طيران"
                status_code = f.get('PublicRemark', {}).get('Code', '').upper()
                
                dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                dt_obj = datetime.fromisoformat(dt_raw)
                
                flights_list.append({
                    "code": f.get('FullFlightNumber') or f"{f.get('OperatingAirline', {}).get('IATA', '')} {f.get('FlightNumber', '')}",
                    "airline": airline, "origin": origin_city,
                    "status": self.get_status_ar(status_code), "raw_status": status_code,
                    "time": dt_obj.strftime('%H:%M')
                })

                # نركز في تحليل الفجوات على الرحلات القادمة (التي لم تصل بعد)
                if status_code not in ['ARR', 'DLV', 'LND']:
                    flight_times.append(dt_obj)
                    hourly_stats[dt_obj.hour] += 1
                    if status_code == 'DEL': delayed_count += 1

            # --- حساب الفجوات الزمنية (> 15 دقيقة) ---
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

            peak_hour = max(hourly_stats, key=hourly_stats.get) if hourly_stats else None
            return {
                "total": len(data), "waiting": len(flight_times), "delayed": delayed_count,
                "peak_hour": f"{peak_hour:02d}:00" if peak_hour is not None else "--",
                "gaps": gaps, "flights": flights_list
            }
        except: return "error"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KAIA Smart Radar</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background-color: #0f172a; color: #f8fafc; font-family: system-ui; }
        .card-main { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 1.5rem; }
        .stat-box { background: #0f172a; border: 1px solid #334155; border-radius: 12px; padding: 1rem; }
        .gap-alert { background: rgba(56, 189, 248, 0.1); border-right: 4px solid #38bdf8; padding: 10px; margin-bottom: 8px; border-radius: 4px; }
        .table { color: #f1f5f9; vertical-align: middle; }
        .status-pill { padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; }
        .text-accent { color: #38bdf8; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 10px; }
    </style>
</head>
<body class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h3 class="fw-bold text-accent"><i class="fa-solid fa-microchip me-2"></i> رادار الصالة 1 - التحليل الذكي</h3>
        <div class="badge bg-dark border border-secondary p-2">{{ current_time }}</div>
    </div>

    <div class="card-main mb-4 shadow">
        <form method="POST" class="row g-3 align-items-end">
            <div class="col-md-3"><label class="small text-secondary mb-1">يوم الاستعلام</label><input type="number" name="day" class="form-control bg-dark text-white border-secondary" value="{{ current_day }}"></div>
            <div class="col-md-3"><label class="small text-secondary mb-1">من الساعة</label><input type="text" name="start" class="form-control bg-dark text-white border-secondary" value="06:00"></div>
            <div class="col-md-3"><label class="small text-secondary mb-1">إلى الساعة</label><input type="text" name="end" class="form-control bg-dark text-white border-secondary" value="23:59"></div>
            <div class="col-md-3"><button type="submit" class="btn btn-primary w-100 fw-bold shadow-sm">تحديث وتحليل</button></div>
        </form>
    </div>

    {% if results %}
    <div class="row g-3 mb-4 text-center">
        <div class="col-md-3 col-6"><div class="stat-box"><h6>الرحلات</h6><h2 class="mb-0">{{ results.total }}</h2></div></div>
        <div class="col-md-3 col-6"><div class="stat-box text-warning"><h6>قادمة</h6><h2 class="mb-0">{{ results.waiting }}</h2></div></div>
        <div class="col-md-3 col-6"><div class="stat-box text-danger"><h6>متأخرة</h6><h2 class="mb-0">{{ results.delayed }}</h2></div></div>
        <div class="col-md-3 col-6"><div class="stat-box text-info"><h6>الذروة</h6><h2 class="mb-0 text-uppercase">{{ results.peak_hour }}</h2></div></div>
    </div>

    <div class="row g-4">
        <div class="col-lg-8">
            <div class="card-main p-0 overflow-hidden shadow">
                <div class="p-3 border-bottom border-secondary bg-dark bg-opacity-50">
                    <h6 class="mb-0"><i class="fa-solid fa-list-ul me-2 text-accent"></i> جدول الرحلات المكتشفة</h6>
                </div>
                <div class="table-responsive" style="max-height: 500px;">
                    <table class="table table-hover mb-0">
                        <thead>
                            <tr class="small text-secondary">
                                <th class="ps-4">الرحلة</th>
                                <th>جهة القدوم</th>
                                <th>الوقت</th>
                                <th>الحالة</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for f in results.flights %}
                            <tr>
                                <td class="ps-4">
                                    <div class="fw-bold text-accent">{{ f.code }}</div>
                                    <div class="small text-secondary" style="font-size: 0.7rem;">{{ f.airline }}</div>
                                </td>
                                <td class="fw-bold">{{ f.origin }}</td>
                                <td>{{ f.time }}</td>
                                <td>
                                    <span class="status-pill 
                                        {% if f.raw_status == 'DEL' %}bg-danger bg-opacity-20 text-danger
                                        {% elif f.raw_status in ['ARR', 'LND', 'DLV'] %}bg-success bg-opacity-20 text-success
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
        </div>
        
        <div class="col-lg-4">
            <div class="card-main shadow h-100">
                <h6 class="mb-3 text-accent"><i class="fa-solid fa-hourglass-start me-2"></i> الفجوات الزمنية (> 15 د)</h6>
                {% for gap in results.gaps %}
                <div class="gap-alert">
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="small fw-bold">{{ gap.from }} <i class="fa-solid fa-chevron-left mx-1"></i> {{ gap.to }}</span>
                        <span class="badge bg-info text-dark">{{ gap.duration }} دقيقة</span>
                    </div>
                </div>
                {% else %}
                <div class="text-center py-5 text-secondary">
                    <i class="fa-solid fa-check-circle fa-3x mb-3 opacity-25"></i>
                    <p>لا توجد فجوات كبيرة حالياً</p>
                </div>
                {% endfor %}
            </div>
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
