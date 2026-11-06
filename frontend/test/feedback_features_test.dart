// Supervisor feedback: reject confirmation with a reason, an approvals
// history, inventory grouped with low stock first, staff contact details, and
// a profile page where people edit their own details (but not their role).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/core/json.dart';
import 'package:restaurant_ops/features/manager/approvals_screen.dart';
import 'package:restaurant_ops/features/manager/staff_detail_screen.dart';
import 'package:restaurant_ops/features/shared/inventory/inventory_list_screen.dart';
import 'package:restaurant_ops/features/shared/profile/contact_fields.dart';
import 'package:restaurant_ops/features/shared/profile/profile_screen.dart';

import 'helpers.dart';

Json _po(int id, String status, {String total = '530.00', int? decidedBy, String? note, String? decidedAt}) => {
  'po_id': id,
  'supplier_id': 1,
  'created_by': 2,
  'approved_by': status == 'rejected' || decidedBy == null ? null : decidedBy,
  'status': status,
  'total_cost': total,
  'created_at': '2026-11-01T09:00:00Z',
  'decided_by': decidedBy,
  'decided_at': decidedAt,
  'decision_note': note,
  'exceeds_budget': false,
};

Json _review(int id, String status, {String? note, String? decidedAt, int? decidedBy}) => {
  'recommendation_id': id,
  'menu_item_id': 8,
  'leftover_rate': '32.00',
  'suggested_portion_size': '0.180',
  'status': status,
  'created_at': '2026-11-01T09:00:00Z',
  'decided_by': decidedBy,
  'decided_at': decidedAt,
  'decision_note': note,
};

Map<String, Handler> _approvalRoutes({List<Json> orders = const [], List<Json> reviews = const []}) => {
  'GET /procurement/purchase-orders': (_, query) => query?['status_filter'] == 'pending_approval'
      ? [for (final o in orders) if (o['status'] == 'pending_approval') o]
      : orders,
  'GET /portion-feedback/recommendations': (_, query) => query?['status_filter'] == 'pending'
      ? [for (final r in reviews) if (r['status'] == 'pending') r]
      : reviews,
  'GET /menu-items': (_, _) => [
    {'menu_item_id': 8, 'name': 'Curry Laksa'},
  ],
  'GET /users': (_, _) => [
    {'user_id': 5, 'name': 'Mei Manager', 'email': 'm@x.com', 'role': 'Restaurant Manager', 'is_active': true},
  ],
};

Future<FakeApi> _pumpApprovals(WidgetTester tester, Map<String, Handler> routes) =>
    pumpAs(tester, Roles.manager, const Scaffold(body: ApprovalsScreen()), routes: routes);

void main() {
  group('rejecting asks for confirmation and a reason', () {
    testWidgets('a purchase order is only rejected after a reason is given, and the reason is sent', (tester) async {
      final api = await _pumpApprovals(tester, _approvalRoutes(orders: [_po(4, 'pending_approval')]));

      await tester.tap(find.text('Reject'));
      await tester.pumpAndSettle();
      expect(find.text('Reject PO #4?'), findsOneWidget);
      expect(find.textContaining('cannot be undone'), findsOneWidget);

      // Nothing typed: refused inline, nothing sent.
      await tester.tap(find.widgetWithText(FilledButton, 'Reject'));
      await tester.pumpAndSettle();
      expect(find.text('Required.'), findsOneWidget);
      expect(api.calls.where((c) => c.method == 'POST'), isEmpty);

      // Too short.
      await tester.enterText(find.byType(TextFormField), 'no');
      await tester.pumpAndSettle();
      expect(find.textContaining('at least 3 characters'), findsOneWidget);

      await tester.enterText(find.byType(TextFormField), 'Over this month\'s budget');
      await tester.tap(find.widgetWithText(FilledButton, 'Reject'));
      await tester.pumpAndSettle();

      final sent = api.calls.singleWhere((c) => c.method == 'POST');
      expect(sent.path, '/procurement/purchase-orders/4/reject');
      expect(sent.body, {'reason': 'Over this month\'s budget'});
    });

    testWidgets('cancelling the confirmation rejects nothing', (tester) async {
      final api = await _pumpApprovals(tester, _approvalRoutes(orders: [_po(4, 'pending_approval')]));

      await tester.tap(find.text('Reject'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(api.calls.where((c) => c.method == 'POST'), isEmpty);
      expect(find.text('PO #4 · RM 530.00'), findsOneWidget); // still waiting
    });

    testWidgets('a portion review is rejected the same way', (tester) async {
      final api = await _pumpApprovals(tester, _approvalRoutes(reviews: [_review(3, 'pending')]));

      await tester.tap(find.text('Reject'));
      await tester.pumpAndSettle();
      expect(find.text('Reject the portion change for Curry Laksa?'), findsOneWidget);
      await tester.enterText(find.byType(TextFormField), 'Guests like the bigger portion');
      await tester.tap(find.widgetWithText(FilledButton, 'Reject'));
      await tester.pumpAndSettle();

      final sent = api.calls.singleWhere((c) => c.method == 'POST');
      expect(sent.path, '/portion-feedback/recommendations/3/reject');
      expect(sent.body, {'reason': 'Guests like the bigger portion'});
    });

    testWidgets('approving needs no reason and goes straight through', (tester) async {
      final api = await _pumpApprovals(tester, _approvalRoutes(orders: [_po(4, 'pending_approval')]));

      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();

      expect(api.calls.singleWhere((c) => c.method == 'POST').path, '/procurement/purchase-orders/4/approve');
    });
  });

  group('approvals history', () {
    final orders = [
      _po(4, 'pending_approval'),
      _po(3, 'awaiting_delivery', total: '740.00', decidedBy: 5, decidedAt: '2026-11-02T16:00:00Z'),
      _po(2, 'rejected', total: '210.00', decidedBy: 5, decidedAt: '2026-11-03T02:00:00Z', note: 'Wrong supplier'),
    ];
    final reviews = [
      _review(1, 'approved', decidedBy: 5, decidedAt: '2026-11-01T10:00:00Z'),
      _review(7, 'pending'),
    ];

    Future<FakeApi> openHistory(WidgetTester tester) async {
      final api = await _pumpApprovals(tester, _approvalRoutes(orders: orders, reviews: reviews));
      await tester.tap(find.text('History'));
      await tester.pumpAndSettle();
      return api;
    }

    testWidgets('lists decided orders and reviews, newest first, with who and why', (tester) async {
      await openHistory(tester);

      // Pending ones are not history.
      expect(find.text('PO #4 · RM 530.00'), findsNothing);
      expect(find.text('PO #3 · RM 740.00'), findsOneWidget);
      expect(find.text('PO #2 · RM 210.00'), findsOneWidget);
      expect(find.text('Curry Laksa'), findsOneWidget);

      expect(find.text('Reason: Wrong supplier'), findsOneWidget);
      expect(find.textContaining('Mei Manager'), findsWidgets);
      expect(find.text('Approved'), findsWidgets);
      expect(find.text('Rejected'), findsWidgets);
      // An approved order says where it has got to.
      expect(find.textContaining('now awaiting delivery'), findsOneWidget);

      // Newest decision first: PO #2 (3 Nov) above PO #3 (2 Nov) above the review (1 Nov).
      double y(String text) => tester.getTopLeft(find.text(text)).dy;
      expect(y('PO #2 · RM 210.00'), lessThan(y('PO #3 · RM 740.00')));
      expect(y('PO #3 · RM 740.00'), lessThan(y('Curry Laksa')));
    });

    testWidgets('can be narrowed to rejected decisions', (tester) async {
      await openHistory(tester);

      await tester.tap(find.widgetWithText(ChoiceChip, 'Rejected'));
      await tester.pumpAndSettle();

      expect(find.text('PO #2 · RM 210.00'), findsOneWidget);
      expect(find.text('PO #3 · RM 740.00'), findsNothing);
      expect(find.text('Curry Laksa'), findsNothing);
    });

    testWidgets('says so when there is nothing yet', (tester) async {
      await _pumpApprovals(tester, _approvalRoutes());
      await tester.tap(find.text('History'));
      await tester.pumpAndSettle();
      expect(find.text('No decisions to show.'), findsOneWidget);
    });
  });

  group('inventory order', () {
    Json ingredient(int id, String name, double stock, {double? threshold, bool low = false}) => {
      'ingredient_id': id,
      'name': name,
      'unit': 'kg',
      'current_stock': stock.toString(),
      'low_stock_threshold': threshold?.toString(),
      'is_low_stock': low,
    };

    test('low stock comes first, the emptiest relative to its threshold at the top, then the rest A to Z', () {
      final groups = groupByPriority([
        ingredient(1, 'Rice', 50),
        ingredient(2, 'Beansprouts', 9, threshold: 10, low: true), // 90% full
        ingredient(3, 'Anchovies', 8),
        ingredient(4, 'Coffee Powder', 1, threshold: 10, low: true), // 10% full
        ingredient(5, 'Curry Paste', 6, threshold: 8, low: true), // 75% full
      ], 10);

      expect(groups.low.map((i) => i['name']), ['Coffee Powder', 'Curry Paste', 'Beansprouts']);
      expect(groups.ok.map((i) => i['name']), ['Anchovies', 'Rice']);
    });

    testWidgets('shows a low-stock group above a well-stocked group, each with a count', (tester) async {
      await pumpAs(
        tester,
        Roles.kitchenStaff,
        const Scaffold(body: InventoryListScreen()),
        routes: {
          'GET /inventory/ingredients': (_, _) => [
            ingredient(1, 'Rice', 50),
            ingredient(2, 'Beansprouts', 9, threshold: 10, low: true),
            ingredient(3, 'Anchovies', 80),
            ingredient(4, 'Coffee Powder', 1, threshold: 10, low: true),
          ],
        },
      );

      expect(find.text('Low stock: restock these'), findsOneWidget);
      expect(find.text('Well stocked'), findsOneWidget);
      double y(String text) => tester.getTopLeft(find.text(text)).dy;
      expect(y('Low stock: restock these'), lessThan(y('Coffee Powder')));
      expect(y('Coffee Powder'), lessThan(y('Beansprouts')));
      expect(y('Beansprouts'), lessThan(y('Well stocked')));
      expect(y('Well stocked'), lessThan(y('Anchovies')));
      expect(y('Anchovies'), lessThan(y('Rice')));
    });
  });

  group('phone numbers', () {
    test('are optional and checked for shape', () {
      expect(validateOptionalPhone(''), isNull);
      expect(validateOptionalPhone('   '), isNull);
      expect(validateOptionalPhone('+60 12-345 6789'), isNull);
      expect(validateOptionalPhone('03-1234 5678'), isNull);
      expect(validateOptionalPhone('hello'), isNotNull);
      expect(validateOptionalPhone('12'), isNotNull);
      expect(validateOptionalPhone('+60 12 abc 456'), isNotNull);
    });
  });

  group('profile', () {
    final me = {
      'user_id': 6,
      'name': 'Kay Kitchen',
      'email': 'kitchen@test.com',
      'role': 'Kitchen Staff',
      'is_active': true,
      'phone_number': '+60 12-345 6789',
      'address': null,
      'emergency_contact_name': null,
      'emergency_contact_phone': null,
      'created_at': '2026-10-01T00:00:00Z',
    };

    Future<FakeApi> openProfile(WidgetTester tester) => pumpAs(
      tester,
      Roles.kitchenStaff,
      const ProfileScreen(),
      routes: {
        'GET /users/me': (_, _) => me,
        'PATCH /users/me': (_, _) => me,
        'POST /users/me/password': (_, _) => <String, dynamic>{},
      },
    );

    testWidgets('shows who you are, and role and email cannot be edited', (tester) async {
      await openProfile(tester);

      expect(find.text('Kay Kitchen'), findsWidgets);
      expect(find.text('kitchen@test.com'), findsOneWidget);
      expect(find.text('Kitchen Staff'), findsOneWidget);
      expect(find.textContaining('only be changed by a Restaurant Manager or Owner'), findsOneWidget);
      // No input holds the role or the email.
      expect(find.widgetWithText(TextFormField, 'Kitchen Staff'), findsNothing);
      expect(find.widgetWithText(TextFormField, 'kitchen@test.com'), findsNothing);
      // The details that can be edited are filled in.
      expect(find.widgetWithText(TextFormField, '+60 12-345 6789'), findsOneWidget);
    });

    testWidgets('saving sends the name and contact details, never a role', (tester) async {
      final api = await openProfile(tester);

      await tester.enterText(find.widgetWithText(TextFormField, 'Kay Kitchen'), 'Kay K. Lim');
      await tester.enterText(find.widgetWithText(TextFormField, 'Address'), '12 Jalan Bukit');
      await tester.ensureVisible(find.text('Save changes'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save changes'));
      await tester.pumpAndSettle();

      final sent = api.calls.singleWhere((c) => c.method == 'PATCH' && c.path == '/users/me').body as Map;
      expect(sent['name'], 'Kay K. Lim');
      expect(sent['address'], '12 Jalan Bukit');
      expect(sent['phone_number'], '+60 12-345 6789');
      expect(sent.containsKey('role'), isFalse);
      expect(sent.containsKey('email'), isFalse);
      expect(sent.containsKey('is_active'), isFalse);
    });

    testWidgets('an invalid phone number is refused inline and nothing is saved', (tester) async {
      final api = await openProfile(tester);

      await tester.enterText(find.widgetWithText(TextFormField, '+60 12-345 6789'), 'not a number');
      await tester.ensureVisible(find.text('Save changes'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save changes'));
      await tester.pumpAndSettle();

      expect(find.textContaining('Enter a valid phone number'), findsWidgets);
      expect(api.calls.where((c) => c.method == 'PATCH'), isEmpty);
    });

    testWidgets('the name cannot be emptied', (tester) async {
      final api = await openProfile(tester);

      await tester.enterText(find.widgetWithText(TextFormField, 'Kay Kitchen'), '');
      await tester.ensureVisible(find.text('Save changes'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save changes'));
      await tester.pumpAndSettle();

      expect(find.text('Your name cannot be empty.'), findsOneWidget);
      expect(api.calls.where((c) => c.method == 'PATCH'), isEmpty);
    });

    testWidgets('changing the password needs it typed twice the same, then sends both passwords', (tester) async {
      final api = await openProfile(tester);
      Finder field(String label) => find.widgetWithText(TextFormField, label);

      await tester.enterText(field('Current password'), 'oldpassword1');
      await tester.enterText(field('New password'), 'newpassword1');
      await tester.enterText(field('Repeat the new password'), 'different123');
      await tester.ensureVisible(find.widgetWithText(OutlinedButton, 'Change password'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(OutlinedButton, 'Change password'));
      await tester.pumpAndSettle();
      expect(find.text('The two passwords do not match.'), findsOneWidget);
      expect(api.calls.where((c) => c.path == '/users/me/password'), isEmpty);

      await tester.enterText(field('Repeat the new password'), 'newpassword1');
      await tester.ensureVisible(find.widgetWithText(OutlinedButton, 'Change password'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(OutlinedButton, 'Change password'));
      await tester.pumpAndSettle();

      final sent = api.calls.singleWhere((c) => c.path == '/users/me/password');
      expect(sent.body, {'current_password': 'oldpassword1', 'new_password': 'newpassword1'});
    });

    testWidgets('a short new password is refused', (tester) async {
      final api = await openProfile(tester);
      await tester.enterText(find.widgetWithText(TextFormField, 'Current password'), 'oldpassword1');
      await tester.enterText(find.widgetWithText(TextFormField, 'New password'), 'short');
      await tester.ensureVisible(find.widgetWithText(OutlinedButton, 'Change password'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(OutlinedButton, 'Change password'));
      await tester.pumpAndSettle();

      expect(find.text('At least 8 characters.'), findsWidgets);
      expect(api.calls.where((c) => c.path == '/users/me/password'), isEmpty);
    });
  });

  group('staff details', () {
    final person = {
      'user_id': 9,
      'name': 'Aisha Rahman',
      'email': 'aisha@x.com',
      'role': 'Inventory Staff',
      'is_active': true,
      'phone_number': '+60 12-345 6789',
      'address': '12 Jalan Bukit, KL',
      'emergency_contact_name': 'Mei Tan',
      'emergency_contact_phone': null,
      'created_at': '2026-10-01T00:00:00Z',
    };

    testWidgets('a Manager sees the contact details', (tester) async {
      await pumpAs(tester, Roles.manager, StaffDetailScreen(user: person));

      expect(find.text('+60 12-345 6789'), findsOneWidget);
      expect(find.text('12 Jalan Bukit, KL'), findsOneWidget);
      expect(find.text('Mei Tan'), findsOneWidget); // the emergency contact, with no phone given
      expect(find.text('aisha@x.com'), findsOneWidget);
    });

    testWidgets('a detail that was never given reads "Not provided", not a blank', (tester) async {
      await pumpAs(tester, Roles.manager, StaffDetailScreen(user: {...person, 'phone_number': null, 'address': ''}));
      expect(find.text('Not provided'), findsNWidgets(2));
    });

    testWidgets('editing the details sends them for that person', (tester) async {
      final api = await pumpAs(
        tester,
        Roles.manager,
        StaffDetailScreen(user: person),
        routes: {'PATCH /users/9': (_, _) => {...person, 'phone_number': '+60 19-888 7777'}},
      );

      await tester.tap(find.byTooltip('Edit details'));
      await tester.pumpAndSettle();
      await tester.enterText(find.widgetWithText(TextFormField, '+60 12-345 6789'), '+60 19-888 7777');
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      final sent = api.calls.singleWhere((c) => c.method == 'PATCH').body as Map;
      expect(sent['phone_number'], '+60 19-888 7777');
      expect(sent['name'], 'Aisha Rahman');
      expect(sent.containsKey('role'), isFalse);
      expect(find.text('+60 19-888 7777'), findsOneWidget); // back to the read-only view, updated
    });

    testWidgets('a new account is created with its contact details', (tester) async {
      final api = await pumpAs(tester, Roles.manager, const StaffFormScreen(), routes: {'POST /users': (_, _) => person});

      await tester.enterText(find.widgetWithText(TextFormField, 'Full name'), 'Aisha Rahman');
      await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'aisha@x.com');
      await tester.enterText(find.widgetWithText(TextFormField, 'Temporary password'), 'password123');
      await tester.enterText(find.widgetWithText(TextFormField, 'Phone number'), '+60 12-345 6789');
      await tester.ensureVisible(find.text('Create account'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Create account'));
      await tester.pumpAndSettle();

      final sent = api.calls.singleWhere((c) => c.method == 'POST').body as Map;
      expect(sent['name'], 'Aisha Rahman');
      expect(sent['role'], Roles.kitchenStaff);
      expect(sent['phone_number'], '+60 12-345 6789');
    });

    testWidgets('a new account needs a valid email and password before anything is sent', (tester) async {
      final api = await pumpAs(tester, Roles.manager, const StaffFormScreen());

      await tester.enterText(find.widgetWithText(TextFormField, 'Full name'), 'Aisha');
      await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'not-an-email');
      await tester.enterText(find.widgetWithText(TextFormField, 'Temporary password'), 'short');
      await tester.ensureVisible(find.text('Create account'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Create account'));
      await tester.pumpAndSettle();

      expect(find.text('Enter a valid email.'), findsOneWidget);
      expect(find.text('At least 8 characters.'), findsOneWidget);
      expect(api.calls.where((c) => c.method == 'POST'), isEmpty);
    });
  });
}
