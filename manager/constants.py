GAS_METRICS = {'co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc', 'ch4'}

POWER_METRICS = {'current_value', 'power_value', 'voltage', 'kw', 'kwh', 'pf'}

METRIC_UNIT = {
    'co': 'ppm', 'h2s': 'ppm', 'co2': 'ppm', 'no2': 'ppm',
    'so2': 'ppm', 'o3': 'ppm', 'nh3': 'ppm', 'voc': 'ppm',
    'ch4': '%LEL', 'o2': '%',
    'current_value': 'A', 'power_value': 'kW', 'voltage': 'V', 'kw': 'kW', 'kwh': 'kWh',
}

RULE_TYPE_LABEL = {
    'threshold': '임계치 초과',
    'missing':   '데이터 누락',
    'power':     '전력 이상',
}

RULE_COLOR = {
    'threshold': ('green',  '녹색'),
    'power':     ('orange', '주황'),
    'missing':   ('gray',   '회색'),
}
