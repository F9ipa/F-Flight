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
        return statuses.get(code, "غير معروف")

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
                "$orderby": "EarlyOrDelayedDateTime", "$count": "true"
            }
            
            response = requests.get(self.url, params=params, headers=self.headers, timeout=10)
            data = response.json().get('value', [])
            if not data: return None

            flight_times, flights_list, delayed_count = [], [], 0
            hourly_stats = Counter()

            for f in data:
                status_code = f.get('PublicRemark', {}).get('Code', '').upper()
                dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                dt_obj = datetime.fromisoformat(dt_raw)
                
                flights_list.append({
                    "code": f"{f.get('OperatingAirline', {}).get('IATA', '')} {f.get('FlightNumber', '')}",
                    "origin": f.get('OriginAirport', {}).get('CityNameAr', 'غير معروف'),
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
        except: return "error"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KAIA Intelligence Dashboard</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --bg-dark: #0f172a; --card-bg: #1e293b; --accent: #38bdf8; }
        body { background-color: var(--bg-dark); color: #f8fafc; font-family: 'Inter', system-ui, -apple-system, sans-serif; }
        .dashboard-card { background: var(--card-bg); border-radius: 16px; border: 1px solid #334155; padding: 1.5rem; transition: 0.3s; }
        .stat-icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; margin-bottom: 1rem; }
        .form-control { background: #0f172a; border: 1px solid #334155; color: white; border-radius: 10px; }
        .btn-primary { background: var(--accent); border: none; font-weight: 600; border-radius: 10px; padding: 10px 25px; }
        .table-container { background: var(--card-bg); border-radius: 16px; border: 1px solid #334155; overflow: hidden; }
        .status-pill { padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 500; }
        .gap-item { border-right: 4px solid var(--accent); background: #111a2e; padding: 10px; border-radius: 0 8px 8px 0; margin-bottom: 10px; }
        .nav-header { border-bottom: 1px solid #334155; padding: 1rem 0; margin-bottom: 2rem; }
    </style>
</head>
<body class="container pb-5">
    <header class="nav-header d-flex justify-content-between align-items-center">
        <h4 class="mb-0 text-info font-monospace"><i class="fa-solid fa-plane-arrival me-2"></i> KAIA SMART ANALYZER</h4>
        <span class="badge bg-dark border border-secondary">{{ current_time }}</span>
    </header>

    <section class="mb-4">
        <div class="dashboard-card shadow-sm">
            <form method="POST" class="row g-3 align-items-end">
                <div class="col-md-3">
                    <label class="form-label small text-secondary">تاريخ اليوم</label>
                    <input type="number" name="day" class="form-control" value="{{ current_day }}">
                </div>
                <div class="col-md-3">
                    <label class="form-label small text-secondary">بداية النافذة</label>
                    <input type="text" name="start" class="form-control" value="06:00">
                </div>
                <div class="col-md-3">
                    <label class="form-label small text-secondary">نهاية النافذة</label>
                    <input type="text" name="end" class="form-control" value="14:00">
                </div>
                <div class="col-md-3">
                    <button type="submit" class="btn btn-primary w-100"><i class="fa-solid fa-magnifying-glass me-2"></i>تحديث البيانات</button>
                </div>
            </form>
        </div>
    </section>

    {% if results %}
    <div class="row g-4 mb-5">
        <div class="col-md-3">
            <div class="dashboard-card">
                <div class="stat-icon bg-info bg-opacity-10 text-info"><i class="fa-solid fa-list-check"></i></div>
                <div class="text-secondary small">إجمالي الحركة</div>
                <div class="h2 mb-0">{{ results.total }}</div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="dashboard-card">
                <div class="stat-icon bg-warning bg-opacity-10 text-warning"><i class="fa-solid fa-clock-rotate-left"></i></div>
                <div class="text-secondary small">في الانتظار</div>
                <div class="h2 mb-0 text-warning">{{ results.waiting }}</div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="dashboard-card">
                <div class="stat-icon bg-danger bg-opacity-10 text-danger"><i class="fa-solid fa-bolt"></i></div>
                <div class="text-secondary small">الرحلات المتأخرة</div>
                <div class="h2 mb-0 text-danger">{{ results.delayed }}</div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="dashboard-card">
                <div class="stat-icon bg-success bg-opacity-10 text-success"><i class="fa-solid fa-fire"></i></div>
                <div class="text-secondary small">ساعة الذروة</div>
                <div class="h2 mb-0">{{ results.peak_hour }}</div>
            </div>
        </div>
    </div>

    <div class="row g-4 mb-5">
        <div class="col-lg-8">
            <div class="table-container shadow-lg">
                <div class="p-3 bg-dark d-flex justify-content-between align-items-center">
                    <h6 class="mb-0"><i class="fa-solid fa-table me-2"></i>مجدول الرحلات التفصيلي</h6>
                </div>
                <div class="table-responsive" style="max-height: 400px;">
                    <table class="table table-hover table-dark mb-0">
                        <thead class="small text-secondary">
                            <tr>
                                <th class="ps-4">الرحلة</th>
                                <th>القادمة من</th>
                                <th>الموعد</th>
                                <th>الحالة</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for f in results.flights %}
                            <tr>
                                <td class="ps-4 fw-bold text-info">{{ f.code }}</td>
                                <td>{{ f.origin }}</td>
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
        </div>
        <div class="col-lg-4">
            <div class="dashboard-card h-100">
                <h6 class="mb-4"><i class="fa-solid fa-hourglass-half me-2"></i>تحليل الفجوات</h6>
                {% for gap in results.gaps %}
                <div class="gap-item">
                    <div class="d-flex justify-content-between mb-1">
                        <span class="fw-bold">{{ gap.from }} <i class="fa-solid fa-arrow-left-long mx-2"></i> {{ gap.to }}</span>
                        <span class="badge bg-secondary">{{ gap.duration }} د</span>
                    </div>
                </div>
                {% else %}
                <div class="text-center py-5 text-secondary">
                    <i class="fa-solid fa-circle-check fa-3x mb-3 opacity-25"></i>
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
    
    return render_template_string(
        HTML_TEMPLATE, 
        results=results, 
        current_day=now.day, 
        current_time=now.strftime('%H:%M')
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
