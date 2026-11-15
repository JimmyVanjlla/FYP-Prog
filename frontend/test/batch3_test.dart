// Review fixes, batch 3: restock decisions, deleting and restoring staff, the
// outlook tab, meal periods per dish, and leftover percentages.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/core/json.dart';
import 'package:restaurant_ops/features/kitchen_staff/leftover_log_screen.dart';
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
      Roles.inventoryStaff,
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

  group('leftover percentages', () {
    test('the standard levels', () {
      expect(leftoverLevels, [0, 25, 50, 75, 100]);
    });

    test('the basis is what Prep confirmed; a recommendation nobody confirmed is nothing', () {
      expect(leftoverPrepBasis({'confirmed': true, 'confirmed_quantity': '40.00', 'recommended_quantity': '35.00'}), 40);
      expect(leftoverPrepBasis({'confirmed': false, 'recommended_quantity': '35.00'}), isNull);
      expect(leftoverPrepBasis(null), isNull);
      expect(leftoverPrepBasis({'confirmed': true, 'confirmed_quantity': '0.00'}), isNull);
    });

    Map<String, Handler> leftoverRoutes({List<Json> prep = const []}) => {
      'GET /menu-items': (_, _) => [
        {'menu_item_id': 1, 'name': 'Curry Laksa', 'meal_periods': ['Lunch', 'Dinner']},
      ],
      'GET /kitchen/prep-recommendations': (_, _) => prep,
    };

    testWidgets('with no confirmed prep it explains, and the log cannot be saved', (tester) async {
      await pumpAs(tester, Roles.kitchenStaff, const Scaffold(body: LeftoverLogScreen()), routes: leftoverRoutes());
      expect(find.textContaining('was not confirmed'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Save log')).onPressed, isNull);
      // No typed quantities, and no vague levels.
      expect(find.text('Quantity prepared'), findsNothing);
      expect(find.text('Partially Eaten'), findsNothing);
    });

    testWidgets('choosing a percentage shows the estimate and saves it with the meal period', (tester) async {
      final api = await pumpAs(
        tester,
        Roles.kitchenStaff,
        const Scaffold(body: LeftoverLogScreen()),
        routes: leftoverRoutes(
          prep: [
            {'recommendation_id': 9, 'menu_item_id': 1, 'confirmed': true, 'confirmed_quantity': '40.00', 'recommended_quantity': '38.00'},
          ],
        ),
      );
      expect(find.textContaining('Based on the 40 portions confirmed in Prep for Lunch'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Save log')).onPressed, isNull); // nothing chosen yet

      await tester.tap(find.text('25%'));
      await tester.pumpAndSettle();
      expect(find.text('About 10 of 40 portions'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Save log'));
      await tester.pumpAndSettle();

      final sent = api.calls.singleWhere((c) => c.method == 'POST');
      expect(sent.path, '/kitchen/leftover-logs');
      final body = sent.body as Map;
      expect(body['leftover_percent'], 25);
      expect(body['meal_period'], 'Lunch');
      expect(body['menu_item_id'], 1);
      expect(body.containsKey('prepared_quantity'), isFalse);
    });
  });

  testWidgets('a dish whose prep was only recommended, not confirmed, cannot be logged', (tester) async {
    await pumpAs(
      tester,
      Roles.kitchenStaff,
      const Scaffold(body: LeftoverLogScreen()),
      routes: {
        'GET /menu-items': (_, _) => [
          {'menu_item_id': 2, 'name': 'Roti Telur', 'meal_periods': ['Lunch', 'Dinner']},
        ],
        'GET /kitchen/prep-recommendations': (_, _) => [
          {'recommendation_id': 4, 'menu_item_id': 2, 'confirmed': false, 'recommended_quantity': '9.00'},
        ],
      },
    );
    expect(find.textContaining('was not confirmed'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Save log')).onPressed, isNull);
  });
}
