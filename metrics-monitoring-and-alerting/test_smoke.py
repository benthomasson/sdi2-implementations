"""Quick smoke test for all 12 testing requirements."""
from metrics import *

svc = MetricsService()

# 1. Basic ingest and query
for i in range(60):
    svc.ingest(DataPoint('cpu.usage', 45 + i * 0.5, timestamp=1000 + i * 60, tags={'host': 'web-1'}))
results = svc.query('cpu.usage', start=1000, end=4600, aggregation='avg', interval_seconds=300)
assert len(results) > 0, 'basic query failed'
print(f'1. Basic query: {len(results)} buckets')

# 2. Aggregation functions
for agg in ['sum', 'avg', 'min', 'max', 'count', 'p99']:
    r = svc.query('cpu.usage', 1000, 4600, aggregation=agg, interval_seconds=3600)
    assert len(r) > 0, f'{agg} failed'
    print(f'2. {agg}: {r[0]["value"]:.2f}')

# 3. Tag filtering
svc.ingest(DataPoint('cpu.usage', 99, timestamp=1500, tags={'host': 'web-2'}))
r = svc.query('cpu.usage', 1000, 4600, aggregation='avg', interval_seconds=3600, tags_filter={'host': 'web-2'})
assert len(r) > 0 and r[0]['value'] == 99, 'tag filter failed'
print(f'3. Tag filter OK')

# 4. Group-by
r = svc.query('cpu.usage', 1000, 4600, aggregation='avg', interval_seconds=3600, group_by=['host'])
hosts = set(x['tags']['host'] for x in r)
assert len(hosts) >= 2, 'group-by failed'
print(f'4. Group-by hosts: {hosts}')

# 5-7. Alert state machine
svc2 = MetricsService()
for i in range(10):
    svc2.ingest(DataPoint('mem', 80 + i, timestamp=1000 + i * 60, tags={}))
svc2.add_alert_rule(AlertRule('high_mem', 'mem', 'gt', 70, duration_seconds=120))
a1 = svc2.evaluate_alerts(1200)
assert any(a.state == 'PENDING' for a in a1), 'should be PENDING'
print(f'5. First eval: {[(a.rule_name, a.state) for a in a1]}')

a2 = svc2.evaluate_alerts(1400)
assert any(a.state == 'ALERTING' for a in a2), 'should be ALERTING'
print(f'5. Second eval (ALERTING): OK')

# 6. Alert resolves
svc2._data.clear()
for i in range(10):
    svc2.ingest(DataPoint('mem', 50, timestamp=1300 + i * 60, tags={}))
a3 = svc2.evaluate_alerts(1900)
assert any(a.state == 'RESOLVED' for a in a3), 'should be RESOLVED'
print(f'6. Resolved: OK')

# 7. Duration requirement
print('7. Duration requirement verified (PENDING before ALERTING)')

# 8. Rate-of-change alert
svc3 = MetricsService()
svc3.ingest(DataPoint('req_rate', 100, timestamp=1550, tags={}))
svc3.ingest(DataPoint('req_rate', 500, timestamp=1600, tags={}))
svc3.add_alert_rule(AlertRule('spike', 'req_rate', 'rate_change', 50, duration_seconds=0))
a = svc3.evaluate_alerts(1610)
assert any(x.state in ('PENDING','ALERTING') for x in a), 'rate change failed'
print(f'8. Rate change: OK')

# 9. Downsampling
svc4 = MetricsService()
day = 86400
for i in range(1000):
    svc4.ingest(DataPoint('disk', i, timestamp=100000 - 2 * day + i * 60, tags={}))
before = sum(len(v) for v in svc4._data.values())
compacted = svc4.downsample(100000)
after = sum(len(v) for v in svc4._data.values())
assert compacted > 0, 'downsample failed'
print(f'9. Downsample: {before} -> {after}, compacted={compacted}')

# 10. Retention
svc5 = MetricsService(retention_seconds=3600)
for i in range(100):
    svc5.ingest(DataPoint('temp', i, timestamp=i * 100, tags={}))
removed = svc5.apply_retention(10000)
assert removed > 0, 'retention failed'
print(f'10. Retention: removed {removed} points')

# 11. Callback
cb_calls = []
svc6 = MetricsService()
svc6.on_alert(lambda a: cb_calls.append(a))
for i in range(10):
    svc6.ingest(DataPoint('x', 100, timestamp=1000 + i * 60, tags={}))
svc6.add_alert_rule(AlertRule('r1', 'x', 'gt', 50, duration_seconds=0))
svc6.evaluate_alerts(1600)
assert len(cb_calls) > 0, 'callback not called'
print(f'11. Callback invoked {len(cb_calls)} times')

# 12. Multiple metrics independent
svc7 = MetricsService()
svc7.ingest(DataPoint('a', 10, 1000))
svc7.ingest(DataPoint('b', 20, 1000))
ra = svc7.query('a', 900, 1100, aggregation='avg', interval_seconds=300)
rb = svc7.query('b', 900, 1100, aggregation='avg', interval_seconds=300)
assert ra[0]['value'] == 10 and rb[0]['value'] == 20, 'metrics not independent'
print(f'12. Independent metrics: a={ra[0]["value"]}, b={rb[0]["value"]}')

print()
print('ALL 12 TESTS PASSED')
