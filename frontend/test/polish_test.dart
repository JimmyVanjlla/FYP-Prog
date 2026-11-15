// Small usability fixes from reviewing every role: whole-number portions,
// reasons that must be words, grouped menu, deactivated staff first, ingredient
// names in the waste log, and severity icons on forecast accuracy.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/core/dialogs.dart';
import 'package:restaurant_ops/core/json.dart';
import 'package:restaurant_ops/core/theme.dart';
import 'package:restaurant_ops/features/manager/staff_screen.dart';
import 'package:restaurant_ops/features/manager/waste_screen.dart';
import 'package:restaurant_ops/features/shared/forecasts/forecast_dashboard_screen.dart';
import 'package:restaurant_ops/features/shared/menu/menu_list_screen.dart';

import 'helpers.dart';

Json _dish(String name, {bool active = true, bool available = true, bool low = false}) => {
  'menu_item_id': name.hashCode,
  'name': name,
  'category': 'Rice',
  'price': '7.00',
  'is_active': active,
  'is_available': available,
  'has_low_stock_ingredient': low,
  'profit_margin': '4.00',
};

void main() {
  group('portions are whole numbers', () {
    test('rounded to the nearest', () {
      expect(portions('24.77'), '25');
      expect(portions('24.4'), '24');
      expect(portions('12.50'), '13');
      expect(portions(7), '7');
      expect(portions(null), '0');
    });
  });

  group('reasons must contain a letter', () {
    test('numbers and symbols alone are not words', () {
      expect(hasLetter('123123123'), isFalse);
      expect(hasLetter('???  !!'), isFalse);
      expect(hasLetter('  '), isFalse);
      expect(hasLetter('Over budget'), isTrue);
      expect(hasLetter('PO 12'), isTrue);
    });
  });

  group('menu is grouped like the ingredient list', () {
    test('unavailable, then low ingredient, then available, then deactivated, A to Z within each', () {
      final groups = groupMenu([
        _dish('Teh Tarik'),
        _dish('Curry Laksa', low: true),
        _dish('Nasi Lemak', low: true),
        _dish('Roti Canai'),
        _dish('Satay', available: false),
        _dish('Old Special', active: false),
        _dish('Chicken Rice'),
      ]);
      expect(groups.unavailable.map((d) => d['name']), ['Satay']);
      expect(groups.low.map((d) => d['name']), ['Curry Laksa', 'Nasi Lemak']);
      expect(groups.available.map((d) => d['name']), ['Chicken Rice', 'Roti Canai', 'Teh Tarik']);
      expect(groups.deactivated.map((d) => d['name']), ['Old Special']);
    });

    testWidgets('the screen shows tiles and the groups in that order', (tester) async {
      await pumpAs(
        tester,
        Roles.kitchenStaff,
        const Scaffold(body: MenuListScreen()),
        routes: {
          'GET /menu-items': (_, _) => [_dish('Teh Tarik'), _dish('Curry Laksa', low: true)],
        },
      );
      expect(find.text('Low ingredient: restock soon'), findsOneWidget);
      expect(find.text('Available'), findsWidgets);
      double y(String t) => tester.getTopLeft(find.text(t).first).dy;
      expect(y('Curry Laksa'), lessThan(y('Teh Tarik')));
    });
  });

  group('staff list', () {
    testWidgets('deactivated accounts come first', (tester) async {
      Json user(int id, String name, bool active) => {
        'user_id': id,
        'name': name,
        'email': '$name@x.com',
        'role': 'Kitchen Staff',
        'is_active': active,
      };
      await pumpAs(
        tester,
        Roles.manager,
        const Scaffold(body: StaffScreen()),
        routes: {
          'GET /users': (_, _) => [user(1, 'Amy', true), user(2, 'Zed', false), user(3, 'Bob', true)],
        },
      );
      double y(String t) => tester.getTopLeft(find.text(t).first).dy;
      expect(y('Zed'), lessThan(y('Amy')));
      expect(y('Amy'), lessThan(y('Bob')));
    });
  });

  group('waste log', () {
    testWidgets('names the ingredient instead of a number', (tester) async {
      await pumpAs(
        tester,
        Roles.manager,
        const Scaffold(body: WasteScreen()),
        routes: {
          'GET /waste/logs': (_, _) => [
            {
              'waste_log_id': 1,
              'source_type': 'leftover',
              'source_ref_id': 1,
              'ingredient_id': 14,
              'quantity_wasted': '0.300',
              'waste_cost': '1.05',
              'logged_at': '2026-11-15T10:00:00Z',
            },
          ],
          'GET /inventory/ingredients': (_, _) => [
            {'ingredient_id': 14, 'name': 'Coconut Milk', 'unit': 'litre'},
          ],
        },
      );
      expect(find.textContaining('Coconut Milk'), findsOneWidget);
      expect(find.textContaining('Ingredient #14'), findsNothing);
      expect(find.textContaining('0.3 litre wasted'), findsOneWidget);
    });
  });

  group('forecast accuracy severity', () {
    test('up to 10% shows nothing, 11 to 40% is yellow, over 40% is red', () {
      expect(accuracySeverity(0.05), isNull);
      expect(accuracySeverity(0.10), isNull);
      expect(accuracySeverity(0.11), Severity.warning);
      expect(accuracySeverity(0.40), Severity.warning);
      expect(accuracySeverity(0.41), Severity.critical);
      expect(accuracySeverity(1.2), Severity.critical);
    });
  });
}
