// The in-app weekly report reads like a report: a header with the period, the
// headline figures, a written summary, a by-day table and a by-dish ranking.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/core/json.dart';
import 'package:restaurant_ops/features/manager/report_summary_screen.dart';

import 'helpers.dart';

Json _row(int item, String date, String period, double predicted, double actual) => {
  'menu_item_id': item,
  'meal_period': period,
  'forecast_date': date,
  'predicted': predicted.toString(),
  'actual': actual.toString(),
  'error': ((predicted - actual).abs() / actual).toString(),
};

Map<String, Handler> _routes({List<Json>? rows, double leftover = 0, double expiry = 0, int logs = 0}) => {
  'GET /reports/3/summary': (_, _) => {
    'report_id': 3,
    'type': 'weekly_summary',
    'status': 'generated',
    'period_start': '2026-11-08',
    'period_end': '2026-11-14',
    'generated_at': '2026-11-15T15:05:00Z',
    'forecast_accuracy': {
      'scored_forecasts': (rows ?? _defaultRows).length,
      'mean_error': 0.2,
      'rows': rows ?? _defaultRows,
    },
    'waste': {
      'leftover_cost': leftover.toString(),
      'expiry_cost': expiry.toString(),
      'total_cost': (leftover + expiry).toString(),
      'log_count': logs,
    },
    'budget': {'limit': '8000.00', 'spent': '530.00', 'utilisation_pct': '6.6'},
  },
  'GET /menu-items': (_, _) => [
    {'menu_item_id': 1, 'name': 'Nasi Lemak'},
    {'menu_item_id': 2, 'name': 'Roti Telur'},
  ],
};

final _defaultRows = [
  _row(1, '2026-11-08', 'Lunch', 24, 20), // 20% off
  _row(1, '2026-11-09', 'Lunch', 22, 20), // 10% off
  _row(2, '2026-11-08', 'Lunch', 15, 10), // 50% off
  _row(2, '2026-11-09', 'Lunch', 12, 10), // 20% off
];

Future<void> _open(WidgetTester tester, Map<String, Handler> routes) async {
  await pumpAs(tester, Roles.manager, const ReportSummaryScreen(reportId: 3), routes: routes);
  // A tall screen, so the whole (lazily built) report is on screen at once.
  tester.view.physicalSize = const Size(420, 5000);
  addTearDown(tester.view.resetPhysicalSize);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows the period, a written summary and the three sections in order', (tester) async {
    await _open(tester, _routes(leftover: 60, expiry: 20, logs: 5));

    expect(find.text('WEEKLY REPORT'), findsOneWidget);
    expect(find.textContaining('to'), findsWidgets);
    expect(find.textContaining('Report #3'), findsWidgets);
    expect(find.text('In summary'), findsOneWidget);
    expect(find.textContaining('RM 80.00 of food was wasted across 5 entries, 75% of it leftovers'), findsOneWidget);
    expect(find.textContaining('RM 7470.00 remains'), findsOneWidget);

    double y(String text) => tester.getTopLeft(find.text(text)).dy;
    expect(y('1. Forecast accuracy'), lessThan(y('2. Waste cost')));
    expect(y('2. Waste cost'), lessThan(y('3. Budget utilisation')));
  });

  testWidgets('ranks dishes by how far off they were, furthest first, and totals each day', (tester) async {
    await _open(tester, _routes());

    // Roti Telur averaged 35% off, Nasi Lemak 15%.
    expect(find.text('35.0%'), findsWidgets);
    expect(find.text('15.0%'), findsWidgets);
    double y(String text) => tester.getTopLeft(find.text(text).last).dy;
    expect(y('Roti Telur'), lessThan(y('Nasi Lemak')));

    // Day table: 8 Nov predicted 24 + 15 = 39, actual 20 + 10 = 30.
    expect(find.text('39'), findsOneWidget);
    expect(find.text('30'), findsWidgets);
  });

  testWidgets('says plainly when no waste was recorded', (tester) async {
    await _open(tester, _routes());
    expect(find.text('No waste was recorded.'), findsOneWidget);
    expect(find.text('No waste was recorded in this period.'), findsOneWidget);
  });

  testWidgets('a period with no scored forecasts says so instead of showing an empty table', (tester) async {
    await _open(tester, _routes(rows: []));
    expect(find.text('No forecasts were scored in this period.'), findsWidgets);
  });
}
