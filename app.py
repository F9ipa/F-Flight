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
            'SCH': 'في موعدها',
            'DEL': 'متأخرة',
            'WIL': 'على وشك الهبوط',
            'LND': 'هبطت',
            'ARR': 'وصلت',
            'DLV': 'تم تسليم الحقائب',
            'CAN': 'ملغاة',
            'EST': 'وقت تقديري'
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
                "$orderby": "EarlyOrDelayedDateTime",
                "$count": "true"
            }
            
            response = requests.get(self.url, params=params, headers=self.headers, timeout=10)
            data = response.json().get('value', [])
            
            if not data: return None

            total_received = len(data)
            flight_times = []
            delayed_count = 0
            hourly_stats = Counter()
            flights_list = []

            for f in data:
                status_code = f.get('PublicRemark', {}).get('Code', '').upper()
                origin_city = f.get('OriginAirport', {}).get('CityNameAr', 'غير معروف')
                flight_code = f"{f.get('OperatingAirline', {}).get('IATA', '')} {f.get('FlightNumber', '')}"
                
                dt_raw = f.get('EarlyOrDelayedDateTime').split('+')[0]
                dt_obj = datetime.fromisoformat(dt_raw)
                time_str = dt_obj.strftime('%H:%M')

                # إضافة كافة الرحلات للجدول
                flights_list.append({
                    "code": flight_code,
                    "origin": origin_city,
                    "status": self.get_status_ar(status_code),
                    "raw_status": status_code,
                    "time": time_str
                })

                # منطق الإحصائيات (للرحلات التي لم تصل بعد)
                if status_code not in ['ARR', 'DLV', 'LND'] and dt_obj < limit_end_dt:
                    flight_times.append(dt_obj)
                    hourly_stats[dt_obj.hour] += 1
                    if status_code == 'DEL':
                        delayed_count += 1

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
                "date": date_str,
                "total": total_received,
                "waiting": len(flight_times),
                "arrived": total_received - len(flight_times),
                "delayed": delayed_count,
                "peak_hour": f"{peak_hour:02d}:00" if peak_hour is not None else "--:--",
                "peak_count": hourly_stats[peak_hour] if peak_hour is not None else 0,
                "gaps": gaps,
                "flights_list": flights_list
            }
        except Exception as e:
            print(f"Error: {e}")
            return "error"

# واجهة HTML مدمجة (Dark Mode)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>محلل الرحلات الذكي</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        body { background-color: #0f172a; color: #f8fafc; font-family: 'Segoe UI', Tahoma, sans-serif; }
        .card { background-color: #1e293b; border: 1px solid #334155; border-radius: 12px; }
        .form-control { background-color: #0f172a; border: 1px solid #475569; color: white; }
        .form-control:focus { background-color: #0f172a; color: white; border-color: #3b82f6; box-shadow: none; }
        .stat-box { padding: 15px; border-radius: 10px; text-align: center; }
        .table { color: #cbd5e1; border-color: #334155; }
        .table-dark { --bs-table-bg: #0f172a; }
        .badge-status { font-size: 0.8rem; padding: 6px 12px; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #1e293b; }
        ::-webkit-scrollbar-thumb { background: #475569; border-radius: 10px; }
    </style>
</head>
<body class="container py-4">
    <h3 class="text-center mb-4 text-info">✈️ نظام تحليل رحلات KAIA الذكي</h3>
    
    <div class="card p-4 mb-4 shadow-lg">
        <form method="POST" class="row g-3">
            <div class="col-md-4">
                <label class="form-label text-secondary">📅 اليوم (رقم)</label>
                <input type="number" name="day" class="form-control" value="{{ current_day }}" required>
            </div>
            <div class="col-md-4">
                <label class="form-label text-secondary">🕒 بداية الفترة</label>
                <input type="text" name="start" class="form-control" value="06:00">
            </div>
            <div class="col-md-4">
                <label class="form-label text-secondary">🕒 نهاية الفترة</label>
                <input type="text" name="end" class="form-control" value="14:00">
            </div>
            <div class="col-12 text-center mt-4">
                <button type="submit" class="btn btn-info w-50 fw-bold">استعلام وتحليل</button>
            </div>
        </form>
    </div>

    {% if results == "error" %}
        <div class="alert alert-danger text-center">حدث خطأ في جلب البيانات، تأكد من المدخلات.</div>
    {% elif results %}
        <div class="row g-3 mb-4">
            <div class="col-6 col-md-3"><div class="stat-box bg-dark border border-secondary"><h6>الإجمالي</h6><h3>{{ results.total }}</h3></div></div>
            <div class="col-6 col-md-3"><div class="stat-box bg-primary"><h6>منتظرة</h6><h3>{{ results.waiting }}</h3></div></div>
            <div class="col-6 col-md-3"><div class="stat-box bg-success"><h6>وصلت</h6><h3>{{ results.arrived }}</h3></div></div>
            <div class="col-6 col-md-3"><div class="stat-box bg-danger"><h6>متأخرة</h6><h3>{{ results.delayed }}</h3></div></div>
        </div>

        <div class="row g-3 mb-4">
            <div class="col-md-6">
                <div class="card p-3 h-100 border-info">
                    <h5 class="text-info">🔥 ذروة الرحلات</h5>
                    <p class="display-6 mb-0">{{ results.peak_hour }}</p>
                    <p class="mb-0 text-secondary">كثافة: {{ results.peak_count }} رحلة/ساعة</p>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card p-3 h-100 border-warning">
                    <h5 class="text-warning">⏳ فجوات العمل</h5>
                    <div style="max-height: 100px; overflow-y: auto;">
                        {% for gap in results.gaps %}
                            <div class="small border-bottom border-secondary py-1 text-light">
                                🕒 {{ gap.from }} ⬅️ {{ gap.to }} ({{ gap.duration }} دقيقة)
                            </div>
                        {% else %}
                            <p class="small text-muted">لا توجد فجوات تذكر.</p>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>

        <div class="card shadow-lg border-0 overflow-hidden">
            <div class="bg-dark p-3 border-bottom border-secondary">
                <h5 class="mb-0 text-info">📋 جدول بيانات الرحلات المكتشفة</h5>
            </div>
            <div class="table-responsive" style="max-height: 500px;">
                <table class="table table-hover mb-0">
                    <thead class="table-dark sticky-top">
                        <tr>
                            <th>الرمز</th>
                            <th>المصدر</th>
                            <th>الوقت</th>
                            <th>الحالة</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for f in results.flights_list %}
                        <tr>
                            <td class="fw-bold text-info">{{ f.code }}</td>
                            <td>{{ f.origin }}</td>
                            <td>{{ f.time }}</td>
                            <td>
                                <span class="badge badge-status 
                                    {% if f.raw_status == 'DEL' %}bg-danger
                                    {% elif f.raw_status in ['ARR', 'LND', 'DLV'] %}bg-success
                                    {% elif f.raw_status == 'WIL' %}bg-warning text-dark
                                    {% else %}bg-primary{% endif %}">
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
    results = None
    current_day = datetime.now().day
    if request.method == 'POST':
        day = request.form.get('day')
        start = request.form.get('start')
        end = request.form.get('end')
        analyzer = FlightAnalyzer()
        results = analyzer.fetch_and_analyze(day, start, end)
    
    return render_template_string(HTML_TEMPLATE, results=results, current_day=current_day)

if __name__ == '__main__':
    # لتشغيله محلياً
    app.run(host='0.0.0.0', port=5000, debug=True)
