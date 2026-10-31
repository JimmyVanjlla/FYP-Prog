// Behaviour tests for the screens added after Sprint 5. Each pumps a real
// screen against a fake API and checks what a person would actually see or
// be stopped from doing.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/features/home_shell.dart';
import 'package:restaurant_ops/features/kitchen_staff/prep_screen.dart';
import 'package:restaurant_ops/features/manager/approvals_screen.dart';
import 'package:restaurant_ops/features/manager/settings_screen.dart';
import 'package:restaurant_ops/features/manager/staff_screen.dart';
import 'package:restaurant_ops/features/procurement_officer/purchase_order_form_screen.dart';
import 'package:restaurant_ops/features/shared/deliveries/delivery_detail_screen.dart';
import 'package:restaurant_ops/features/shared/forecasts/forecast_dashboard_screen.dart';
import 'package:restaurant_ops/features/shared/menu/menu_detail_screen.dart';
import 'package:restaurant_ops/features/shift_supervisor/schedule_builder_screen.dart';

import 'helpers.dart';

void main() {
  group('role navigation (FR1.3)', () {
    Future<void> expectDestinations(
      WidgetTester tester,
      String role,
      List<String> expected,
      List<String> absent,
    ) async {
      await pumpAs(tester, role, const HomeShell());
      final labels = destinationsFor(role).map((d) => d.label).toList();
      expect(labels, expected);
      // Everything it offers is reachable: in the bottom bar, or the drawer.
      if (labels.length <= 5) {
        for (final label in expected) {
          expect(find.text(label), findsWidgets);
        }
      } else {
        await tester.tap(find.byTooltip('Open navigation menu'));
        await tester.pumpAndSettle();
        for (final label in expected) {
          expect(find.text(label), findsWidgets);
        }
      }
      for (final label in absent) {
        expect(labels.contains(label), isFalse, reason: '$role should not be offered "$label"');
      }
    }

    testWidgets('delivery staff see only deliveries and their own shifts', (tester) async {
      await expectDestinations(tester, Roles.deliveryStaff, ['Deliveries', 'My shifts'], ['Inventory', 'Reports', 'Staff']);
    });

    testWidgets('kitchen staff get prep, leftovers, menu, inventory and shifts', (tester) async {
      await expectDestinations(
        tester,
        Roles.kitchenStaff,
        ['Prep', 'Leftovers', 'Menu', 'Inventory', 'My shifts'],
        ['Reports', 'Settings', 'Purchasing'],
      );
    });

    testWidgets('procurement officers get purchasing, suppliers and deliveries', (tester) async {
      await expectDestinations(
        tester,
        Roles.procurementOfficer,
        ['Purchasing', 'Suppliers', 'Deliveries', 'Menu', 'My shifts'],
        ['Staff', 'Settings', 'Prep'],
      );
    });

    testWidgets('shift supervisors get the schedule builder', (tester) async {
      await expectDestinations(
        tester,
        Roles.shiftSupervisor,
        ['Schedules', 'Forecasts', 'Menu', 'My shifts'],
        ['Reports', 'Settings', 'Purchasing'],
      );
    });

    testWidgets('the manager has too many destinations for a bar, so gets a drawer', (tester) async {
      await expectDestinations(
        tester,
        Roles.manager,
        [
          'Needs attention', 'Menu', 'Inventory', 'Forecasts', 'Waste', 'Reports',
          'Purchasing', 'Deliveries', 'Staff', 'Settings',
        ],
        const [],
      );
    });
  });

  group('prep confirmation (FR5.2 / FR5.5)', () {
    Map<String, Handler> prepRoutes() => {
      'GET /menu-items': (_, _) => [
        {'menu_item_id': 1, 'name': 'Nasi Lemak', 'is_active': true},
      ],
      'GET /forecasting/forecasts': (_, _) => [
        {'forecast_id': 1, 'menu_item_id': 1, 'meal_period': 'Lunch', 'predicted_quantity': '40.00'},
      ],
      'POST /kitchen/prep-recommendations': (_, _) => {
        'recommendation_id': 7,
        'menu_item_id': 1,
        'forecast_id': 1,
        'meal_period': 'Lunch',
        'recommended_quantity': '40.00',
        'confirmed': false,
      },
    };

    testWidgets('shows the recommendation pre-filled and editable', (tester) async {
      await pumpAs(tester, Roles.kitchenStaff, const Scaffold(body: PrepScreen()), routes: prepRoutes());

      expect(find.text('Nasi Lemak'), findsOneWidget);
      expect(find.text('Recommended: 40 portions'), findsOneWidget);
      expect(tester.widget<TextField>(find.widgetWithText(TextField, 'Quantity to prep')).controller!.text, '40');
    });

    testWidgets('a small change needs no reason', (tester) async {
      await pumpAs(tester, Roles.kitchenStaff, const Scaffold(body: PrepScreen()), routes: prepRoutes());

      await tester.enterText(find.widgetWithText(TextField, 'Quantity to prep'), '42'); // 5%, under 10%
      await tester.pump();

      expect(find.textContaining('Reason for the change'), findsNothing);
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Confirm')).onPressed, isNotNull);
    });

    testWidgets('a large change demands a reason at the field, before confirming', (tester) async {
      final api = await pumpAs(tester, Roles.kitchenStaff, const Scaffold(body: PrepScreen()), routes: prepRoutes());

      await tester.enterText(find.widgetWithText(TextField, 'Quantity to prep'), '60'); // 50%
      await tester.pump();

      expect(find.textContaining('Reason for the change'), findsOneWidget);
      expect(find.text('Please explain the change.'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Confirm')).onPressed, isNull);

      await tester.enterText(find.widgetWithText(TextField, 'Reason for the change (required)'), 'Large booking');
      await tester.pump();
      final confirm = find.widgetWithText(FilledButton, 'Confirm');
      expect(tester.widget<FilledButton>(confirm).onPressed, isNotNull);

      await tester.tap(confirm);
      await tester.pumpAndSettle();
      final sent = api.calls.lastWhere((c) => c.path.endsWith('/confirm')).body as Map;
      expect(sent['confirmed_quantity'], '60');
      expect(sent['deviation_reason'], 'Large booking');
    });

    testWidgets('a dish with no forecast takes a manual quantity instead of dead-ending', (tester) async {
      final routes = prepRoutes()..['GET /forecasting/forecasts'] = (_, _) => [];
      final api = await pumpAs(tester, Roles.kitchenStaff, const Scaffold(body: PrepScreen()), routes: routes);

      expect(find.text('No forecast'), findsOneWidget);
      await tester.enterText(find.widgetWithText(TextField, 'Quantity to prep'), '25');
      await tester.pump();
      await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
      await tester.pumpAndSettle();

      final manual = api.calls.firstWhere((c) => c.path == '/kitchen/prep-recommendations' && c.method == 'POST');
      expect((manual.body as Map)['manual_quantity'], '25');
    });
  });

  group('delivery receipt (FR10.2 / FR10.5)', () {
    Map<String, Handler> deliveryRoutes() => {
      'GET /deliveries': (_, _) => [
        {
          'delivery_id': 3,
          'po_id': 9,
          'scheduled_date': '2026-11-02',
          'status': 'awaiting_delivery',
          'verified_by': null,
          'supplier_name': 'Fresh Farm Supplies',
          'po_total_cost': '230.00',
        },
      ],
      'GET /deliveries/3/items': (_, _) => [
        {'item_id': 11, 'ingredient_id': 1, 'expected_quantity': '25.000', 'received_quantity': null},
      ],
      'GET /inventory/ingredients': (_, _) => [
        {'ingredient_id': 1, 'name': 'Chicken', 'unit': 'kg'},
      ],
    };

    testWidgets('a mismatch turns critical the moment it is typed, with the reason', (tester) async {
      await pumpAs(
        tester,
        Roles.deliveryStaff,
        const DeliveryDetailScreen(deliveryId: 3),
        routes: deliveryRoutes(),
      );

      expect(find.textContaining('will be reported as a discrepancy'), findsNothing);

      await tester.enterText(find.widgetWithText(TextField, 'Received'), '15'); // 40% short
      await tester.pump();

      expect(find.textContaining('40% short'), findsOneWidget);
      expect(find.textContaining('will be reported as a discrepancy'), findsWidgets);
      expect(find.text('Confirm and report discrepancies'), findsOneWidget);
    });

    testWidgets('a quantity within tolerance is accepted as a normal receipt', (tester) async {
      final api = await pumpAs(
        tester,
        Roles.deliveryStaff,
        const DeliveryDetailScreen(deliveryId: 3),
        routes: deliveryRoutes(),
      );

      await tester.enterText(find.widgetWithText(TextField, 'Received'), '24'); // 4% short
      await tester.pump();

      expect(find.textContaining('discrepancy'), findsNothing);
      await tester.tap(find.widgetWithText(FilledButton, 'Confirm receipt'));
      await tester.pumpAndSettle();
      final sent = api.calls.lastWhere((c) => c.path.endsWith('/confirm-receipt')).body as Map;
      expect((sent['received_quantities'] as Map)['11'], '24');
    });

    testWidgets('a negative quantity is refused inline', (tester) async {
      await pumpAs(
        tester,
        Roles.deliveryStaff,
        const DeliveryDetailScreen(deliveryId: 3),
        routes: deliveryRoutes(),
      );

      await tester.enterText(find.widgetWithText(TextField, 'Received'), '-5');
      await tester.pump();

      expect(find.text('Cannot be negative.'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Confirm receipt')).onPressed, isNull);
    });

    testWidgets('inventory staff can verify a received delivery into stock', (tester) async {
      final routes = deliveryRoutes()
        ..['GET /deliveries'] = (_, _) => [
          {
            'delivery_id': 3,
            'po_id': 9,
            'scheduled_date': '2026-11-02',
            'status': 'delivered',
            'verified_by': null,
            'supplier_name': 'Fresh Farm Supplies',
            'po_total_cost': '230.00',
          },
        ];
      await pumpAs(tester, Roles.inventoryStaff, const DeliveryDetailScreen(deliveryId: 3), routes: routes);

      expect(find.text('Verify against stock records'), findsOneWidget);
      // ...and delivery staff, who can't verify, are not offered it.
      await pumpAs(tester, Roles.deliveryStaff, const DeliveryDetailScreen(deliveryId: 3), routes: routes);
      expect(find.text('Verify against stock records'), findsNothing);
    });
  });

  group('purchase order form (FR9.3 / FR9.6)', () {
    Map<String, Handler> poRoutes({String remaining = '600.00'}) => {
      'GET /procurement/suppliers': (_, _) => [
        {'supplier_id': 1, 'name': 'Fresh Farm', 'contact_info': 'x', 'is_active': true},
      ],
      'GET /procurement/suppliers/pricing': (_, _) => [
        {'pricing_id': 1, 'supplier_id': 1, 'ingredient_id': 1, 'unit_price': '9.20'},
      ],
      'GET /inventory/ingredients': (_, _) => [
        {'ingredient_id': 1, 'name': 'Chicken', 'unit': 'kg'},
      ],
      'GET /procurement/recommendations': (_, _) => [
        {'recommendation_id': 1, 'ingredient_id': 1, 'forecast_id': 1, 'recommended_quantity': '5.000'},
      ],
      'GET /procurement/budget/utilisation': (_, _) => {
        'month': '2026-10-01',
        'budget_limit': '1000.00',
        'spent': '400.00',
        'remaining': remaining,
        'utilisation_pct': '40.00',
      },
    };

    testWidgets('pre-fills from the recommendation and shows the running total beside the items', (tester) async {
      await pumpAs(tester, Roles.procurementOfficer, const PurchaseOrderFormScreen(), routes: poRoutes());

      expect(find.text('RM 46.00'), findsWidgets); // 5 kg x RM 9.20, as the line cost and the total
      expect(find.textContaining('Remaining budget RM 600.00'), findsOneWidget);
      expect(find.text('Exceeds budget'), findsNothing);
    });

    testWidgets('going over budget is flagged but does not block submitting (FR9.6)', (tester) async {
      await pumpAs(tester, Roles.procurementOfficer, const PurchaseOrderFormScreen(), routes: poRoutes());

      await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '100'); // RM 920 > RM 600
      await tester.pump();

      expect(find.text('Exceeds budget'), findsOneWidget);
      expect(find.textContaining('Over the remaining budget'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Submit for approval')).onPressed, isNotNull);
    });

    testWidgets('a zero quantity is rejected inline and blocks submitting', (tester) async {
      await pumpAs(tester, Roles.procurementOfficer, const PurchaseOrderFormScreen(), routes: poRoutes());

      await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '0');
      await tester.pump();

      expect(find.text('Must be above zero.'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Submit for approval')).onPressed, isNull);
    });
  });

  group('schedule builder (FR8.1 / FR8.2)', () {
    testWidgets('flags a station below its recommendation, beside the roster', (tester) async {
      final routes = <String, Handler>{
        'GET /staffing/schedules/5/recommendations': (_, _) => [
          {'recommendation_id': 1, 'schedule_id': 5, 'station': 'Kitchen', 'recommended_staff_count': 3},
          {'recommendation_id': 2, 'schedule_id': 5, 'station': 'Front of House', 'recommended_staff_count': 1},
        ],
        'GET /staffing/schedules/5/assignments': (_, _) => [
          {'assignment_id': 1, 'schedule_id': 5, 'staff_id': 20, 'station': 'Kitchen', 'attendance_status': 'unconfirmed'},
          {'assignment_id': 2, 'schedule_id': 5, 'staff_id': 21, 'station': 'Front of House', 'attendance_status': 'unconfirmed'},
        ],
        'GET /staffing/staff': (_, _) => [
          {'user_id': 20, 'name': 'Aminah', 'role': 'Kitchen Staff'},
          {'user_id': 21, 'name': 'Raj', 'role': 'Kitchen Staff'},
        ],
        'GET /staffing/schedules': (_, _) => [
          {'schedule_id': 5, 'date': '2026-11-02', 'meal_period': 'Lunch', 'status': 'draft'},
        ],
      };
      await pumpAs(
        tester,
        Roles.shiftSupervisor,
        const ScheduleBuilderScreen(
          schedule: {'schedule_id': 5, 'date': '2026-11-02', 'meal_period': 'Lunch', 'status': 'draft'},
        ),
        routes: routes,
      );

      expect(find.text('2 below recommendation (1 of 3)'), findsOneWidget);
      expect(find.text('Meets recommendation (1 of 1)'), findsOneWidget);
      expect(find.text('Aminah'), findsOneWidget);
      expect(find.text('Assign staff'), findsNWidgets(2)); // one "+ add" row per station
      expect(find.text('Publish schedule'), findsOneWidget);
    });
  });

  group('settings validation (FR3.3 / FR7.5)', () {
    testWidgets('a leftover threshold above 100% is refused inline', (tester) async {
      await pumpAs(tester, Roles.manager, const Scaffold(body: SettingsScreen()));

      await tester.enterText(find.widgetWithText(TextFormField, 'Leftover rate threshold'), '150');
      await tester.pump();

      expect(find.text('Cannot be above 100.'), findsOneWidget);
    });

    testWidgets('a fractional near-expiry window is refused', (tester) async {
      await pumpAs(tester, Roles.manager, const Scaffold(body: SettingsScreen()));

      await tester.enterText(find.widgetWithText(TextFormField, 'Near-expiry window'), '2.5');
      await tester.pump();

      expect(find.text('Whole numbers only.'), findsOneWidget);
    });
  });

  group('manager screens', () {
    testWidgets('approvals show the remaining budget beside Approve/Reject', (tester) async {
      final routes = <String, Handler>{
        'GET /procurement/purchase-orders': (_, _) => [
          {
            'po_id': 4,
            'supplier_id': 1,
            'created_by': 2,
            'approved_by': null,
            'status': 'pending_approval',
            'total_cost': '750.00',
            'created_at': '2026-10-30T10:00:00',
            'exceeds_budget': true,
          },
        ],
      };
      await pumpAs(tester, Roles.manager, const Scaffold(body: ApprovalsScreen()), routes: routes);

      expect(find.textContaining('Remaining budget RM 600.00'), findsOneWidget);
      expect(find.textContaining('RM 150.00 over'), findsOneWidget);
      expect(find.text('Approve'), findsOneWidget);
      expect(find.text('Reject'), findsOneWidget);
    });

    testWidgets('staff screen lists accounts with role and status', (tester) async {
      final routes = <String, Handler>{
        'GET /users': (_, _) => [
          {'user_id': 1, 'name': 'Mei Ling', 'email': 'mei@x.com', 'role': 'Kitchen Staff', 'is_active': true},
          {'user_id': 2, 'name': 'Old Hand', 'email': 'old@x.com', 'role': 'Inventory Staff', 'is_active': false},
        ],
      };
      await pumpAs(tester, Roles.manager, const Scaffold(body: StaffScreen()), routes: routes);

      expect(find.text('Mei Ling'), findsOneWidget);
      expect(find.text('Active'), findsOneWidget);
      expect(find.text('Deactivated'), findsOneWidget);
      expect(find.text('Add staff account'), findsOneWidget);
    });
  });

  group('forecast dashboard (UC-DF-01 / FR4.6)', () {
    testWidgets('says why a forecast is missing, with the minimum-data threshold', (tester) async {
      final routes = <String, Handler>{
        'GET /forecasting/availability': (_, _) => [
          {
            'menu_item_id': 1,
            'menu_item_name': 'Satay',
            'meal_period': 'Lunch',
            'data_points': 3,
            'minimum_required': 14,
            'available': false,
            'message': 'Forecasts are not yet available for Satay (Lunch): 3 of the 14 days of order history needed so far.',
          },
        ],
        'GET /menu-items': (_, _) => [
          {'menu_item_id': 1, 'name': 'Satay'},
        ],
      };
      await pumpAs(tester, Roles.shiftSupervisor, const Scaffold(body: ForecastDashboardScreen()), routes: routes);

      expect(find.textContaining('without a forecast yet'), findsOneWidget);
      expect(find.textContaining('3 of the 14 days'), findsOneWidget);
    });
  });

  group('menu item detail (FR2.1 / FR2.2)', () {
    Map<String, Handler> menuRoutes({bool low = true}) => {
      'GET /menu-items': (_, _) => [
        {
          'menu_item_id': 1,
          'name': 'Nasi Lemak',
          'description': null,
          'price': '6.50',
          'category': 'Rice',
          'is_active': true,
          'profit_margin': '3.25',
          'is_available': true,
          'has_low_stock_ingredient': low,
          'recipe_links': [
            {'link_id': 1, 'ingredient_id': 1, 'quantity_per_serving': '0.150'},
          ],
        },
      ],
      'GET /inventory/ingredients': (_, _) => [
        {'ingredient_id': 1, 'name': 'Rice', 'unit': 'kg'},
      ],
    };

    testWidgets('shows the profit margin, recipe and low-ingredient warning', (tester) async {
      await pumpAs(tester, Roles.manager, const MenuDetailScreen(menuItemId: 1), routes: menuRoutes());

      expect(find.textContaining('Profit margin: RM 3.25 per serving (50%)'), findsOneWidget);
      expect(find.widgetWithText(ListTile, 'Rice'), findsOneWidget);
      expect(find.text('0.15 kg per serving'), findsOneWidget);
      expect(find.text('Low ingredient'), findsOneWidget);
    });

    testWidgets('only the manager can change the recipe or edit the item', (tester) async {
      await pumpAs(tester, Roles.kitchenStaff, const MenuDetailScreen(menuItemId: 1), routes: menuRoutes());

      expect(find.widgetWithText(ListTile, 'Rice'), findsOneWidget); // can see the recipe...
      expect(find.text('Add ingredient'), findsNothing);
      expect(find.text('Save changes'), findsNothing);
      expect(find.text('Deactivate menu item'), findsNothing);
    });
  });
}
