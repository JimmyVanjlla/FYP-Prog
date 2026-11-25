// Review fixes, batch 3: restock decisions, deleting and restoring staff, the
// outlook tab, meal periods per dish, and leftover percentages.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/core/json.dart';
import 'package:restaurant_ops/features/kitchen_staff/leftover_log_screen.dart';
import 'package:restaurant_ops/features/kitchen_staff/orders_screen.dart';
import 'package:restaurant_ops/features/kitchen_staff/prep_screen.dart';
import 'package:restaurant_ops/features/manager/staff_screen.dart';
import 'package:restaurant_ops/features/shared/forecasts/forecast_dashboard_screen.dart';
import 'package:restaurant_ops/features/shared/inventory/restocking_requests_screen.dart';
import 'package:restaurant_ops/features/shared/menu/meal_period_picker.dart';

import 'helpers.dart';

Json _request(int id, String status, {String? note, String? decidedAt}) => {
  'request_id': id,
  'ingredient_id': 1,
  'requested_by': 9,
  'quantity': '20.000',
  'urgency': true,
  'status': status,
  'decided_by': status == 'pending' ? null : 3,
  'decided_at': decidedAt,
  'decision_note': note,
};

final _ingredients = <String, Handler>{
  'GET /inventory/ingredients': (_, _) => [
    {'ingredient_id': 1, 'name': 'Beansprouts', 'unit': 'kg'},
  ],
};

void main() {
  group('restocking requests', () {
    Future<FakeApi> open(WidgetTester tester, List<Json> requests) => pumpAs(
      tester,
      Roles.shiftSupervisor,
      const Scaffold(body: RestockingRequestsScreen()),
      routes: {..._ingredients, 'GET /inventory/restocking-requests': (_, _) => requests},
    );

    testWidgets('approving asks first; cancelling approves nothing', (tester) async {
      final api = await open(tester, [_request(5, 'pending')]);

      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      expect(find.text('Approve this request?'), findsOneWidget);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(api.calls.where((c) => c.method == 'PATCH'), isEmpty);

      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      await tester.tap(find.descendant(of: find.byType(AlertDialog), matching: find.widgetWithText(FilledButton, 'Approve')));
      await tester.pumpAndSettle();
      final sent = api.calls.singleWhere((c) => c.method == 'PATCH');
      expect(sent.path, '/inventory/restocking-requests/5');
      expect(sent.body, {'status': 'fulfilled'});
    });

    testWidgets('declining needs a reason made of words, and sends it', (tester) async {
      final api = await open(tester, [_request(5, 'pending')]);

      await tester.tap(find.text('Decline'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField), '12345');
      await tester.tap(find.widgetWithText(FilledButton, 'Decline'));
      await tester.pumpAndSettle();
      expect(find.textContaining('at least one letter'), findsOneWidget);
      expect(api.calls.where((c) => c.method == 'PATCH'), isEmpty);

      await tester.enterText(find.byType(TextFormField), 'Already ordered');
      await tester.tap(find.widgetWithText(FilledButton, 'Decline'));
      await tester.pumpAndSettle();
      expect(api.calls.singleWhere((c) => c.method == 'PATCH').body, {'status': 'declined', 'note': 'Already ordered'});
    });

    testWidgets('decided requests are in a History tab with the reason', (tester) async {
      await open(tester, [
        _request(5, 'pending'),
        _request(4, 'declined', note: 'Already ordered', decidedAt: '2026-11-15T10:00:00Z'),
        _request(3, 'fulfilled', decidedAt: '2026-11-14T10:00:00Z'),
      ]);
      expect(find.text('Approve'), findsOneWidget); // only the pending one on this tab
      await tester.tap(find.text('History'));
      await tester.pumpAndSettle();
      expect(find.text('Reason: Already ordered'), findsOneWidget);
      expect(find.text('Declined'), findsWidgets);
      expect(find.text('Approved'), findsWidgets);
    });
  });

  group('deleted staff', () {
    Json user(int id, String name, {bool active = true, String role = Roles.kitchenStaff, String? deletedAt}) => {
      'user_id': id,
      'name': name,
      'email': '$name@x.com',
      'role': role,
      'is_active': active,
      'deleted_at': deletedAt,
    };

    testWidgets('the Deleted tab lists accounts with the days left to restore, and restores one', (tester) async {
      final deletedAt = DateTime.now().subtract(const Duration(days: 13)).toUtc().toIso8601String();
      final api = await pumpAs(
        tester,
        Roles.manager,
        const Scaffold(body: StaffScreen()),
        routes: {
          'GET /users': (_, query) => query?['deleted'] == true ? [user(7, 'Zed', active: false, deletedAt: deletedAt)] : [user(1, 'Amy')],
        },
      );
      await tester.tap(find.text('Deleted'));
      await tester.pumpAndSettle();

      expect(find.text('Zed'), findsOneWidget);
      expect(find.textContaining('47 days left to restore'), findsOneWidget);
      await tester.tap(find.text('Restore account'));
      await tester.pumpAndSettle();
      expect(api.calls.any((c) => c.method == 'POST' && c.path == '/users/7/restore'), isTrue);
    });

    testWidgets('says so when there are none', (tester) async {
      await pumpAs(
        tester,
        Roles.manager,
        const Scaffold(body: StaffScreen()),
        routes: {'GET /users': (_, query) => query?['deleted'] == true ? [] : [user(1, 'Amy')]},
      );
      await tester.tap(find.text('Deleted'));
      await tester.pumpAndSettle();
      expect(find.text('No deleted accounts.'), findsOneWidget);
    });

    testWidgets('a deactivated account offers Delete, which asks first and calls the server', (tester) async {
      final api = await pumpAs(
        tester,
        Roles.manager,
        const Scaffold(body: StaffScreen()),
        routes: {
          'GET /users': (_, query) => query?['deleted'] == true ? [] : [user(2, 'Old Cook', active: false)],
        },
      );
      await tester.tap(find.byType(PopupMenuButton<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete account'));
      await tester.pumpAndSettle();
      expect(find.text('Delete Old Cook?'), findsOneWidget);
      expect(find.textContaining('60 days'), findsWidgets);
      await tester.tap(find.descendant(of: find.byType(AlertDialog), matching: find.widgetWithText(FilledButton, 'Delete')));
      await tester.pumpAndSettle();
      expect(api.calls.any((c) => c.method == 'DELETE' && c.path == '/users/2'), isTrue);
    });
  });

  group('outlook tab', () {
    testWidgets('shows each day and meal period with portions, how busy, and the staff needed', (tester) async {
      final today = DateTime.now();
      String day(int plus) {
        final d = today.add(Duration(days: plus));
        return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
      }

      await pumpAs(
        tester,
        Roles.shiftSupervisor,
        const Scaffold(body: ForecastDashboardScreen()),
        routes: {
          'GET /forecasting/outlook': (_, _) => [
            {'forecast_date': day(1), 'meal_period': 'Lunch', 'predicted_portions': 310, 'typical_portions': 250, 'level': 'Busy', 'recommended_kitchen_staff': 11},
            {'forecast_date': day(1), 'meal_period': 'Dinner', 'predicted_portions': 190, 'typical_portions': 220, 'level': 'Quiet', 'recommended_kitchen_staff': 7},
          ],
        },
      );
      expect(find.text('Outlook'), findsOneWidget);
      expect(find.text('310 portions  (typical 250)'), findsOneWidget);
      expect(find.text('Busy'), findsOneWidget);
      expect(find.text('Quiet'), findsOneWidget);
      expect(find.text('Lunch: 11 Kitchen Staff'), findsOneWidget);
    });

    testWidgets('says so when nothing is forecast', (tester) async {
      await pumpAs(tester, Roles.shiftSupervisor, const Scaffold(body: ForecastDashboardScreen()));
      expect(find.textContaining('No forecasts for the coming week'), findsOneWidget);
    });
  });

  group('meal periods per dish', () {
    Future<void> pickerHarness(WidgetTester tester, Set<String> start, void Function(Set<String>) seen) async {
      var selected = start;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: StatefulBuilder(
              builder: (context, setState) => MealPeriodPicker(
                selected: selected,
                onChanged: (v) {
                  setState(() => selected = v);
                  seen(v);
                },
              ),
            ),
          ),
        ),
      );
    }

    testWidgets('offers Breakfast, Lunch and Dinner and toggles them', (tester) async {
      Set<String> last = {};
      await pickerHarness(tester, {'Lunch', 'Dinner'}, (v) => last = v);
      await tester.tap(find.text('Breakfast'));
      await tester.pump();
      expect(last, {'Breakfast', 'Lunch', 'Dinner'});
      await tester.tap(find.text('Dinner'));
      await tester.pump();
      expect(last, {'Breakfast', 'Lunch'});
    });

    testWidgets('a dish always stays served at something', (tester) async {
      Set<String> last = {'Lunch'};
      await pickerHarness(tester, {'Lunch'}, (v) => last = v);
      await tester.tap(find.text('Lunch'));
      await tester.pump();
      expect(last, {'Lunch'});
    });

    testWidgets('the Prep screen lists only the dishes served at the chosen meal period', (tester) async {
      Json dish(int id, String name, List<String> periods) => {'menu_item_id': id, 'name': name, 'meal_periods': periods};
      await pumpAs(
        tester,
        Roles.kitchenStaff,
        const Scaffold(body: PrepScreen()),
        routes: {
          'GET /menu-items': (_, _) => [dish(1, 'Teh Tarik', ['Lunch', 'Dinner']), dish(2, 'Roti Canai', ['Breakfast'])],
        },
      );
      // The screen opens on Lunch.
      expect(find.text('Teh Tarik'), findsOneWidget);
      expect(find.text('Roti Canai'), findsNothing);
    });
  });

  group('leftover worked out from sales', () {
    Json dish(String name, {bool confirmed = true, double prepared = 8, int served = 5, bool recorded = false}) => {
      'menu_item_id': name.length,
      'menu_item_name': name,
      'prep_confirmed': confirmed,
      'prepared': confirmed ? prepared.toStringAsFixed(2) : null,
      'served': served,
      'leftover': confirmed ? (prepared - served).clamp(0, prepared).toStringAsFixed(2) : null,
      'leftover_percent': confirmed ? ((prepared - served).clamp(0, prepared) / prepared * 100).round() : null,
      'sold_beyond_prep': 0,
      'recorded': recorded,
    };

    Map<String, Handler> routes(List<Json> dishes, {int open = 0}) => {
      'GET /kitchen/leftover-summary': (_, _) => {
        'service_date': '2026-11-16',
        'meal_period': 'Lunch',
        'open_orders': open,
        'dishes': dishes,
      },
    };

    testWidgets('shows prepared, served and left over, and nothing to type', (tester) async {
      await pumpAs(tester, Roles.kitchenStaff, const Scaffold(body: LeftoverLogScreen()), routes: routes([dish('Curry Laksa')]));
      expect(find.text('Curry Laksa'), findsOneWidget);
      // 8 prepared, 5 served: 3 left over (38%).
      expect(find.text('8'), findsOneWidget);
      expect(find.text('5'), findsOneWidget);
      expect(find.text('3'), findsOneWidget);
      expect(find.text('38% left'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      expect(find.byType(ChoiceChip), findsNothing);
    });

    testWidgets('a dish whose prep was not confirmed is listed without a leftover', (tester) async {
      await pumpAs(
        tester,
        Roles.kitchenStaff,
        const Scaffold(body: LeftoverLogScreen()),
        routes: routes([dish('Roti Telur', confirmed: false)]),
      );
      expect(find.text('Prep not confirmed'), findsOneWidget);
      expect(find.textContaining('No dish has a confirmed prep quantity'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Record leftovers')).onPressed, isNull);
    });

    testWidgets('warns about orders that are not completed yet', (tester) async {
      await pumpAs(
        tester,
        Roles.kitchenStaff,
        const Scaffold(body: LeftoverLogScreen()),
        routes: routes([dish('Curry Laksa')], open: 3),
      );
      expect(find.textContaining('3 orders are not completed yet'), findsOneWidget);
    });

    testWidgets('recording sends the date and meal period, not any quantity', (tester) async {
      final api = await pumpAs(
        tester,
        Roles.kitchenStaff,
        const Scaffold(body: LeftoverLogScreen()),
        routes: {
          ...routes([dish('Curry Laksa')]),
          'POST /kitchen/leftovers/record': (_, _) => <Json>[],
        },
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Record leftovers'));
      await tester.pumpAndSettle();
      final sent = api.calls.singleWhere((c) => c.method == 'POST');
      expect(sent.path, '/kitchen/leftovers/record');
      final body = sent.body as Map;
      expect(body['meal_period'], 'Lunch');
      expect(body.keys.toSet(), {'service_date', 'meal_period'});
    });
  });

  group('incoming orders', () {
    Json order(int id, String status, {String name = 'Curry Laksa', int qty = 2}) => {
      'order_id': id,
      'menu_item_id': 1,
      'menu_item_name': name,
      'quantity': qty,
      'meal_period': 'Lunch',
      'order_date': '2026-11-16',
      'status': status,
      'created_at': '2026-11-16T04:30:00Z',
    };

    testWidgets('groups orders by status and moves one forward', (tester) async {
      final api = await pumpAs(
        tester,
        Roles.kitchenStaff,
        const Scaffold(body: OrdersScreen()),
        routes: {
          'GET /orders': (_, _) => [order(1, 'pending'), order(2, 'preparing', name: 'Roti Telur'), order(3, 'completed')],
          'PATCH /orders/1/status': (_, _) => order(1, 'preparing'),
        },
      );
      expect(find.text('2 × Curry Laksa'), findsNWidgets(2)); // one incoming, one completed
      expect(find.text('2 × Roti Telur'), findsOneWidget);
      expect(find.text('1 incoming'), findsOneWidget);
      expect(find.text('1 preparing'), findsOneWidget);
      expect(find.text('1 completed'), findsOneWidget);

      await tester.tap(find.widgetWithText(FilledButton, 'Start'));
      await tester.pumpAndSettle();
      final sent = api.calls.singleWhere((c) => c.method == 'PATCH');
      expect(sent.path, '/orders/1/status');
      expect((sent.body as Map)['status'], 'preparing');
    });

    testWidgets('with no orders it explains and offers sample orders', (tester) async {
      await pumpAs(
        tester,
        Roles.kitchenStaff,
        const Scaffold(body: OrdersScreen()),
        routes: {'GET /orders': (_, _) => <Json>[]},
      );
      expect(find.textContaining('No orders for Lunch yet'), findsOneWidget);
      expect(find.text('Add sample orders'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.ancestor(of: find.text('Complete all'), matching: find.bySubtype<FilledButton>())).onPressed, isNull);
    });
  });
}
