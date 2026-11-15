// Review fixes, batch 2: the restaurant's clock, who can manage which accounts,
// forecast accuracy by day, the waste summary, the formal purchase order and
// starting an order from a recommendation.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/core/clock.dart';
import 'package:restaurant_ops/core/json.dart';
import 'package:restaurant_ops/features/manager/staff_screen.dart';
import 'package:restaurant_ops/features/manager/waste_screen.dart';
import 'package:restaurant_ops/features/procurement_officer/purchase_order_document_screen.dart';
import 'package:restaurant_ops/features/procurement_officer/purchase_orders_screen.dart';
import 'package:restaurant_ops/features/shared/forecasts/forecast_dashboard_screen.dart';

import 'helpers.dart';

Json _accuracy(int item, String date, String period, double predicted, double actual) => {
  'accuracy_id': item * 100 + date.hashCode % 100,
  'menu_item_id': item,
  'meal_period': period,
  'forecast_date': date,
  'predicted_quantity': predicted.toString(),
  'actual_quantity': actual.toString(),
  'accuracy_error': ((predicted - actual).abs() / actual).toString(),
};

void main() {
  group('the restaurant clock', () {
    test('is Malaysia time (UTC+8), whatever the phone says', () {
      // 17:00 UTC on 15 Nov is 01:00 on 16 Nov in Malaysia.
      expect(restaurantToday(now: DateTime.utc(2026, 11, 15, 17)), DateTime(2026, 11, 16));
      // 15:59 UTC is still 23:59 on the 15th.
      expect(restaurantToday(now: DateTime.utc(2026, 11, 15, 15, 59)), DateTime(2026, 11, 15));
      expect(restaurantNow(now: DateTime.utc(2026, 11, 15, 4, 30)), DateTime(2026, 11, 15, 12, 30));
    });
  });

  group('who can manage which accounts', () {
    test('an Owner assigns any role; a Manager only the roles below Manager', () {
      expect(Roles.assignableBy(Roles.owner), Roles.all);
      final byManager = Roles.assignableBy(Roles.manager);
      expect(byManager, isNot(contains(Roles.owner)));
      expect(byManager, isNot(contains(Roles.manager)));
      expect(byManager, contains(Roles.kitchenStaff));
      expect(Roles.assignableBy(Roles.kitchenStaff), isEmpty);
    });

    test('a Manager cannot manage a Manager or an Owner', () {
      expect(Roles.canManage(Roles.manager, Roles.kitchenStaff), isTrue);
      expect(Roles.canManage(Roles.manager, Roles.manager), isFalse);
      expect(Roles.canManage(Roles.manager, Roles.owner), isFalse);
      expect(Roles.canManage(Roles.owner, Roles.manager), isTrue);
    });

    Json user(int id, String name, String role) => {
      'user_id': id,
      'name': name,
      'email': '$name@x.com',
      'role': role,
      'is_active': true,
    };
    final staffRoutes = <String, Handler>{
      'GET /users': (_, _) => [user(1, 'Amy', Roles.kitchenStaff), user(2, 'Bo', Roles.manager), user(3, 'Cy', Roles.owner)],
    };

    testWidgets('a Manager sees the manage menu only on accounts below Manager', (tester) async {
      await pumpAs(tester, Roles.manager, const Scaffold(body: StaffScreen()), routes: staffRoutes);
      expect(find.byType(PopupMenuButton<String>), findsOneWidget); // Amy only
    });

    testWidgets('an Owner sees it on every account', (tester) async {
      await pumpAs(tester, Roles.owner, const Scaffold(body: StaffScreen()), routes: staffRoutes);
      expect(find.byType(PopupMenuButton<String>), findsNWidgets(3));
    });
  });

  group('forecast accuracy by day', () {
    final rows = [
      _accuracy(1, '2026-11-08', 'Lunch', 24, 20), // 20% off
      _accuracy(2, '2026-11-08', 'Lunch', 15, 10), // 50% off
      _accuracy(1, '2026-11-09', 'Lunch', 21, 20), // 5% off
    ];

    test('groups by date, newest first, with each day\'s average error', () {
      final days = groupAccuracyByDay(rows);
      expect(days.map((d) => d.date.day), [9, 8]);
      expect(days.last.rows, hasLength(2));
      expect(days.last.meanError, closeTo(0.35, 1e-9));
      expect(days.first.meanError, closeTo(0.05, 1e-9));
    });

    testWidgets('lists the days and opens one to show its forecasts, furthest off first', (tester) async {
      await pumpAs(
        tester,
        Roles.manager,
        const Scaffold(body: ForecastDashboardScreen()),
        routes: {
          'GET /forecasting/accuracy': (_, _) => rows,
          'GET /menu-items': (_, _) => [
            {'menu_item_id': 1, 'name': 'Nasi Lemak'},
            {'menu_item_id': 2, 'name': 'Roti Telur'},
          ],
        },
      );
      await tester.tap(find.text('Accuracy'));
      await tester.pumpAndSettle();

      expect(find.text('By day'), findsOneWidget);
      expect(find.text('Choose a date'), findsOneWidget);
      double y(String t) => tester.getTopLeft(find.text(t)).dy;
      expect(y('Mon 9 Nov'), lessThan(y('Sun 8 Nov')));

      await tester.tap(find.text('Sun 8 Nov'));
      await tester.pumpAndSettle();
      expect(find.text('Furthest off first'), findsOneWidget);
      expect(y('Roti Telur  ·  Lunch'), lessThan(y('Nasi Lemak  ·  Lunch')));
      expect(find.textContaining('Predicted 15, ordered 10'), findsOneWidget);
    });
  });

  group('waste screen', () {
    testWidgets('shows this week against last, the biggest sources, and the weekly chart', (tester) async {
      Json week(String start, double leftover, double expiry, int entries) => {
        'period_start': start,
        'period_end': start,
        'leftover_cost': leftover.toString(),
        'expiry_cost': expiry.toString(),
        'total_cost': (leftover + expiry).toString(),
        'entries': entries,
      };
      await pumpAs(
        tester,
        Roles.manager,
        const Scaffold(body: WasteScreen()),
        routes: {
          'GET /waste/summary': (_, _) => {
            'weeks': [week('2026-11-02', 100, 20, 30), week('2026-11-09', 60, 0, 20)],
            'top_dishes': [
              {'menu_item_id': 1, 'name': 'Curry Laksa', 'cost': '80.00'},
            ],
            'top_ingredients': [
              {'ingredient_id': 1, 'name': 'Coconut Milk', 'unit': 'litre', 'quantity': '12.5', 'cost': '45.00'},
            ],
          },
        },
      );
      expect(find.text('RM 60'), findsOneWidget); // this week
      expect(find.text('RM 120'), findsOneWidget); // last week
      expect(find.text('-RM 60'), findsOneWidget); // down on last week
      expect(find.text('Waste cost by week'), findsOneWidget);
      expect(find.text('Curry Laksa'), findsOneWidget);
      expect(find.text('Coconut Milk'), findsOneWidget);
      expect(find.text('12.5 litre'), findsOneWidget);
    });

    testWidgets('says so when nothing was wasted', (tester) async {
      await pumpAs(
        tester,
        Roles.manager,
        const Scaffold(body: WasteScreen()),
        routes: {'GET /waste/summary': (_, _) => {'weeks': [], 'top_dishes': [], 'top_ingredients': []}},
      );
      expect(find.textContaining('No waste recorded in the last eight weeks'), findsOneWidget);
    });
  });

  group('the purchase order document', () {
    Json order({String status = 'pending_approval', String? note, String? decidedAt}) => {
      'po_id': 4,
      'supplier_id': 1,
      'created_by': 2,
      'status': status,
      'total_cost': '530.00',
      'created_at': '2026-11-15T09:00:00Z',
      'decided_at': decidedAt,
      'decision_note': note,
      'exceeds_budget': false,
    };
    final routes = {
      'GET /procurement/purchase-orders/4/items': (_, _) => [
        {'item_id': 1, 'ingredient_id': 1, 'quantity': '20.000', 'unit_price': '12.50'},
        {'item_id': 2, 'ingredient_id': 2, 'quantity': '10.000', 'unit_price': '28.00'},
      ],
    };
    final ingredients = {
      1: {'ingredient_id': 1, 'name': 'Chicken', 'unit': 'kg'},
      2: {'ingredient_id': 2, 'name': 'Prawns', 'unit': 'kg'},
    };
    final supplier = {'supplier_id': 1, 'name': 'Fresh Farm Poultry & Seafood', 'contact_info': 'sales@freshfarm.example'};

    test('numbers read like a document: PO-0004', () {
      expect(poNumber(4), 'PO-0004');
      expect(poNumber(1234), 'PO-1234');
    });

    testWidgets('has a number, supplier, itemised amounts and a total', (tester) async {
      await pumpAs(
        tester,
        Roles.procurementOfficer,
        PurchaseOrderDocumentScreen(order: order(), supplier: supplier, ingredients: ingredients),
        routes: routes,
      );
      expect(find.text('PURCHASE ORDER'), findsOneWidget);
      expect(find.text('PO-0004'), findsWidgets);
      expect(find.text('Fresh Farm Poultry & Seafood'), findsOneWidget);
      expect(find.text('sales@freshfarm.example'), findsOneWidget);
      expect(find.text('250.00'), findsOneWidget); // 20 kg x 12.50
      expect(find.text('280.00'), findsOneWidget); // 10 kg x 28.00
      expect(find.text('RM 530.00'), findsOneWidget);
      expect(find.textContaining('Waiting for the Restaurant Manager'), findsOneWidget);
      expect(find.text('Flag a supplier issue'), findsOneWidget);
    });

    testWidgets('a rejected order shows who decided when, and why', (tester) async {
      await pumpAs(
        tester,
        Roles.manager,
        PurchaseOrderDocumentScreen(
          order: order(status: 'rejected', note: 'Over budget', decidedAt: '2026-11-16T03:00:00Z'),
          supplier: supplier,
          ingredients: ingredients,
        ),
        routes: routes,
      );
      expect(find.textContaining('Rejected on'), findsOneWidget);
      expect(find.text('Reason: Over budget'), findsOneWidget);
    });

    testWidgets('flagging a supplier issue needs words, not just numbers', (tester) async {
      final api = await pumpAs(
        tester,
        Roles.procurementOfficer,
        PurchaseOrderDocumentScreen(order: order(status: 'delivered'), supplier: supplier, ingredients: ingredients),
        routes: routes,
      );
      await tester.tap(find.text('Flag a supplier issue'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField), '4444');
      await tester.tap(find.widgetWithText(FilledButton, 'Flag'));
      await tester.pumpAndSettle();
      expect(find.textContaining('at least one letter'), findsOneWidget);
      expect(api.calls.where((c) => c.method == 'POST'), isEmpty);
    });
  });

  group('starting an order from a recommendation', () {
    testWidgets('tapping a recommended item opens an order with it filled in, from the cheapest supplier', (tester) async {
      final routes = {
        'GET /procurement/suppliers': (_, _) => [
          {'supplier_id': 1, 'name': 'Pricey Co', 'contact_info': 'x', 'is_active': true},
          {'supplier_id': 2, 'name': 'Cheap Co', 'contact_info': 'x', 'is_active': true},
        ],
        'GET /procurement/suppliers/pricing': (_, _) => [
          {'pricing_id': 1, 'supplier_id': 1, 'ingredient_id': 1, 'unit_price': '12.00'},
          {'pricing_id': 2, 'supplier_id': 2, 'ingredient_id': 1, 'unit_price': '9.20'},
        ],
        'GET /inventory/ingredients': (_, _) => [
          {'ingredient_id': 1, 'name': 'Chicken', 'unit': 'kg'},
          {'ingredient_id': 2, 'name': 'Prawns', 'unit': 'kg'},
        ],
        'GET /procurement/recommendations': (_, _) => [
          {'recommendation_id': 1, 'ingredient_id': 1, 'forecast_id': 1, 'recommended_quantity': '5.000'},
          {'recommendation_id': 2, 'ingredient_id': 2, 'forecast_id': 1, 'recommended_quantity': '3.000'},
        ],
        'GET /procurement/purchase-orders': (_, _) => [],
        'GET /procurement/budget/utilisation': (_, _) => {
          'month': '2026-11-01',
          'budget_limit': '1000.00',
          'spent': '400.00',
          'remaining': '600.00',
          'utilisation_pct': '40.00',
        },
      };
      await pumpAs(tester, Roles.procurementOfficer, const Scaffold(body: PurchaseOrdersScreen()), routes: routes);

      await tester.tap(find.text('Chicken'));
      await tester.pumpAndSettle();

      expect(find.text('New purchase order'), findsOneWidget);
      expect(find.text('Cheap Co'), findsOneWidget); // the cheaper supplier for Chicken
      expect(find.widgetWithText(TextField, 'Quantity'), findsOneWidget); // only the one item
      expect(tester.widget<TextField>(find.widgetWithText(TextField, 'Quantity')).controller!.text, '5');
      expect(find.text('RM 46.00'), findsWidgets); // 5 kg x 9.20
    });
  });
}
