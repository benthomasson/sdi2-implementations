"""Tests for Metrics Monitoring and Alerting System."""
import sys
sys.path.insert(0, '../implementer')

from metrics import DataPoint, AlertRule, Alert, MetricsService


def test_basic_ingest_and_query():
    """Req 1, 2: Basic ingest and query returns correct values."""
    svc = MetricsService()
    for i in range(60):
        svc.ingest(DataPoint('cpu', 45 + i * 0.5, timestamp=1000 + i * 60, tags={'host': 'web-1'}))

    results = svc.query('cpu', start=1000, end=4600, aggregation='avg', interval_seconds=300)
    assert len(results) > 0
    # Each 300s bucket has 5 points. First bucket: values 45, 45.5, 46, 46.5, 47 -> avg 46
    assert abs(results[0]['value'] - 46.0) < 0.01


def test_aggregation_functions():
    """Req 2: All aggregation functions work correctly."""
    svc = MetricsService()
    values = [10, 20, 30, 40, 50]
    for i, v in enumerate(values):
        svc.ingest(DataPoint('m', v, timestamp=100 + i, tags={}))

    def q(agg):
        r = svc.query('m', 100, 200, aggregation=agg, interval_seconds=200)
        return r[0]['value']

    assert q('sum') == 150
    assert q('avg') == 30
    assert q('min') == 10
    assert q('max') == 50
    assert q('count') == 5
    p99 = q('p99')
    assert p99 >= 49  # p99 of [10,20,30,40,50] should be close to 50


def test_tag_filtering():
    """Req 3: Tag filtering on queries works."""
    svc = MetricsService()
    svc.ingest(DataPoint('cpu', 80, timestamp=100, tags={'host': 'a', 'region': 'us'}))
    svc.ingest(DataPoint('cpu', 20, timestamp=100, tags={'host': 'b', 'region': 'eu'}))

    r = svc.query('cpu', 90, 200, aggregation='avg', interval_seconds=200, tags_filter={'host': 'a'})
    assert len(r) == 1
    assert r[0]['value'] == 80


def test_group_by():
    """Req 4: Group-by produces separate series per tag value."""
    svc = MetricsService()
    svc.ingest(DataPoint('cpu', 80, timestamp=100, tags={'host': 'a'}))
    svc.ingest(DataPoint('cpu', 20, timestamp=100, tags={'host': 'b'}))

    r = svc.query('cpu', 90, 200, aggregation='avg', interval_seconds=200, group_by=['host'])
    assert len(r) == 2
    by_host = {x['tags']['host']: x['value'] for x in r}
    assert by_host['a'] == 80
    assert by_host['b'] == 20


def test_alert_state_machine():
    """Req 5, 6, 7: OK -> PENDING -> ALERTING -> RESOLVED with duration."""
    svc = MetricsService()
    # Continuously ingest high values so they're always in the lookback window
    def add_data(up_to):
        for t in range(1000, up_to + 1, 10):
            svc.ingest(DataPoint('mem', 90, timestamp=t, tags={}))

    add_data(1200)
    svc.add_alert_rule(AlertRule('high_mem', 'mem', 'gt', 70, duration_seconds=120))

    # First eval: OK -> PENDING (window=[1080,1200] has data)
    a1 = svc.evaluate_alerts(1200)
    assert len(a1) == 1
    assert a1[0].state == 'PENDING'

    # 60s later, not enough duration yet
    add_data(1260)
    a2 = svc.evaluate_alerts(1260)
    assert len(a2) == 0  # no state change, still PENDING

    # 120s after pending_since: PENDING -> ALERTING
    add_data(1400)
    a3 = svc.evaluate_alerts(1400)
    assert len(a3) == 1
    assert a3[0].state == 'ALERTING'

    # Clear the condition: ingest low values covering the lookback window
    svc._data.clear()
    for t in range(1400, 1600, 10):
        svc.ingest(DataPoint('mem', 50, timestamp=t, tags={}))
    a4 = svc.evaluate_alerts(1500)
    assert len(a4) == 1
    assert a4[0].state == 'RESOLVED'


def test_rate_of_change_alert():
    """Req 8: Rate-of-change alert detects spikes."""
    svc = MetricsService()
    # Put points within 60s window before eval time (window = max(0,60) = 60)
    # Values go from 100 to 500 -> 400% change, threshold is 50%
    svc.ingest(DataPoint('req', 100, timestamp=1550, tags={}))
    svc.ingest(DataPoint('req', 500, timestamp=1600, tags={}))

    svc.add_alert_rule(AlertRule('spike', 'req', 'rate_change', 50, duration_seconds=0))
    a = svc.evaluate_alerts(1610)
    assert any(x.state in ('PENDING', 'ALERTING') for x in a)


def test_downsampling():
    """Req 9: Downsampling reduces data point count."""
    svc = MetricsService()
    day = 86400
    now = 100000
    # Insert 1000 points, 2 days old (within 1-7 day downsample range)
    for i in range(1000):
        svc.ingest(DataPoint('disk', float(i), timestamp=now - 2 * day + i * 60, tags={}))

    before = sum(len(v) for v in svc._data.values())
    compacted = svc.downsample(now)
    after = sum(len(v) for v in svc._data.values())
    assert compacted > 0
    assert after < before


def test_retention():
    """Req 10: Retention deletes old data."""
    svc = MetricsService(retention_seconds=3600)
    for i in range(100):
        svc.ingest(DataPoint('x', float(i), timestamp=1000 + i * 60, tags={}))

    removed = svc.apply_retention(current_time=8000)
    assert removed > 0
    # All remaining points should be >= 8000 - 3600 = 4400
    for series in svc._data.values():
        for ts, _ in series:
            assert ts >= 4400


def test_alert_callback():
    """Req 11: Alert callback is invoked on state change."""
    svc = MetricsService()
    # Ensure data is within the 60s lookback window of eval time
    svc.ingest(DataPoint('cpu', 99, timestamp=195, tags={}))
    svc.add_alert_rule(AlertRule('high', 'cpu', 'gt', 50, duration_seconds=0))

    fired = []
    svc.on_alert(lambda alert: fired.append(alert))
    svc.evaluate_alerts(200)
    assert len(fired) >= 1
    assert fired[0].rule_name == 'high'


def test_multiple_metrics_independent():
    """Req 12: Multiple metrics are independent."""
    svc = MetricsService()
    svc.ingest(DataPoint('cpu', 80, timestamp=100, tags={}))
    svc.ingest(DataPoint('mem', 40, timestamp=100, tags={}))

    r_cpu = svc.query('cpu', 50, 200, aggregation='avg', interval_seconds=200)
    r_mem = svc.query('mem', 50, 200, aggregation='avg', interval_seconds=200)
    assert r_cpu[0]['value'] == 80
    assert r_mem[0]['value'] == 40
    assert svc.get_metrics() == sorted(svc.get_metrics()) or set(svc.get_metrics()) == {'cpu', 'mem'}


if __name__ == '__main__':
    tests = [
        test_basic_ingest_and_query,
        test_aggregation_functions,
        test_tag_filtering,
        test_group_by,
        test_alert_state_machine,
        test_rate_of_change_alert,
        test_downsampling,
        test_retention,
        test_alert_callback,
        test_multiple_metrics_independent,
    ]
    for t in tests:
        try:
            t()
            print(f'PASS: {t.__name__}')
        except Exception as e:
            print(f'FAIL: {t.__name__}: {e}')
            import traceback
            traceback.print_exc()
    print(f'\nRan {len(tests)} tests')
