// Accounts are created by a Manager or Owner (there is no self-registration in
// the app), and a supplier's prices can be changed and the supplier brought back.
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:restaurant_ops/core/api_client.dart';
import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/core/json.dart';
import 'package:restaurant_ops/core/theme.dart';
import 'package:restaurant_ops/features/procurement_officer/suppliers_screen.dart';
import 'package:restaurant_ops/features/shared/auth/login_screen.dart';

import 'helpers.dart';

Map<String, Handler> _supplierRoutes() => {
  'GET /procurement/suppliers/pricing': (_, _) => [
    {'pricing_id': 1, 'supplier_id': 7, 'ingredient_id': 1, 'unit_price': '2.50'},
  ],
  'GET /inventory/ingredients': (_, _) => [
    {'ingredient_id': 1, 'name': 'Rice', 'unit': 'kg', 'current_stock': '10'},
    {'ingredient_id': 2, 'name': 'Chicken', 'unit': 'kg', 'current_stock': '5'},
  ],
};

Json _supplier({required bool active}) => {
  'supplier_id': 7,
  'name': 'Pasar Besar Trading',
  'contact_info': '+60 12-3456789',
  'is_active': active,
};

void main() {
  testWidgets('the login screen has no Register link; accounts come from a Manager or Owner', (tester) async {
    FlutterSecureStoragePlatform.instance = FakeSecureStorage();
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthState>.value(
        value: AuthState(api: ApiClient(baseUrl: 'http://x')),
        child: MaterialApp(theme: buildAppTheme(), home: const LoginScreen()),
      ),
    );

    expect(find.textContaining('Register'), findsNothing);
    expect(find.textContaining('Manager or Owner creates it'), findsOneWidget);
  });

  group('supplier screen', () {
    testWidgets('tapping a price offers to change it, keeping its ingredient', (tester) async {
      final api = await pumpAs(
        tester,
        Roles.procurementOfficer,
        SupplierDetailScreen(supplier: _supplier(active: true)),
        routes: _supplierRoutes(),
      );

      await tester.tap(find.text('Rice'));
      await tester.pumpAndSettle();
      expect(find.text('Change price'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, '2.50'), findsOneWidget); // pre-filled with the current price

      await tester.enterText(find.widgetWithText(TextFormField, '2.50'), '2.80');
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();

      final saved = api.calls.lastWhere((c) => c.method == 'POST' && c.path == '/procurement/suppliers/pricing');
      expect(saved.body, {'supplier_id': 7, 'ingredient_id': 1, 'unit_price': '2.80'});
    });

    testWidgets('an active supplier offers Deactivate, and the warning says what it affects', (tester) async {
      await pumpAs(
        tester,
        Roles.procurementOfficer,
        SupplierDetailScreen(supplier: _supplier(active: true)),
        routes: _supplierRoutes(),
      );
      await tester.scrollUntilVisible(find.text('Deactivate supplier'), 200, scrollable: find.byType(Scrollable).first);

      expect(find.text('Reactivate supplier'), findsNothing);
      await tester.tap(find.text('Deactivate supplier'));
      await tester.pumpAndSettle();
      expect(find.textContaining('reactivate this supplier later'), findsOneWidget);
      expect(find.textContaining('margins and waste costs'), findsOneWidget);
    });

    testWidgets('a deactivated supplier can be reactivated', (tester) async {
      final api = await pumpAs(
        tester,
        Roles.procurementOfficer,
        SupplierDetailScreen(supplier: _supplier(active: false)),
        routes: {
          ..._supplierRoutes(),
          'PATCH /procurement/suppliers/7/reactivate': (_, _) => _supplier(active: true),
        },
      );
      await tester.scrollUntilVisible(find.text('Reactivate supplier'), 200, scrollable: find.byType(Scrollable).first);

      expect(find.text('Deactivate supplier'), findsNothing);
      await tester.tap(find.text('Reactivate supplier'));
      await tester.pumpAndSettle();

      expect(api.calls.any((c) => c.method == 'PATCH' && c.path == '/procurement/suppliers/7/reactivate'), isTrue);
      expect(find.text('Deactivate supplier'), findsOneWidget); // now active again
    });
  });
}
