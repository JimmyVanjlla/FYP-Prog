// The bell shows how many notifications are unread; opening the inbox clears it.
import 'package:flutter_test/flutter_test.dart';

import 'package:restaurant_ops/core/auth_state.dart';
import 'package:restaurant_ops/features/home_shell.dart';

import 'helpers.dart';

void main() {
  testWidgets('the bell shows the unread count, and opening the inbox marks them read', (tester) async {
    var unread = 2;
    final api = await pumpAs(
      tester,
      Roles.kitchenStaff,
      const HomeShell(),
      routes: {
        'GET /kitchen/notifications/unread-count': (_, _) => {'unread': unread},
        'POST /kitchen/notifications/read': (_, _) {
          unread = 0;
          return {'unread': 0};
        },
        'GET /kitchen/notifications': (_, _) => [
          {
            'notification_id': 2,
            'type': 'shift_published',
            'message': "You're scheduled for 2026-11-17 (Lunch), station: Kitchen.",
            'status': 'sent',
            'created_at': '2026-11-15T10:58:00Z',
            'read_at': null,
          },
          {
            'notification_id': 1,
            'type': 'prep_update',
            'message': 'Prep update',
            'status': 'sent',
            'created_at': '2026-11-14T10:58:00Z',
            'read_at': '2026-11-14T12:00:00Z',
          },
        ],
      },
    );
    expect(find.text('2'), findsOneWidget); // the badge on the bell

    await tester.tap(find.byTooltip('Notifications, 2 unread'));
    await tester.pumpAndSettle();
    expect(find.textContaining("You're scheduled for 2026-11-17"), findsOneWidget);
    expect(find.textContaining('New  ·  Shift'), findsOneWidget); // the new one is picked out
    expect(find.textContaining('New  ·  Prep update'), findsNothing); // the old one is not
    expect(api.calls.any((c) => c.method == 'POST' && c.path == '/kitchen/notifications/read'), isTrue);

    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.byTooltip('Notifications'), findsOneWidget); // no unread now
    expect(find.text('2'), findsNothing);
  });

  testWidgets('with nothing unread the bell has no badge', (tester) async {
    await pumpAs(tester, Roles.kitchenStaff, const HomeShell(), routes: {
      'GET /kitchen/notifications/unread-count': (_, _) => {'unread': 0},
    });
    expect(find.byTooltip('Notifications'), findsOneWidget);
  });
}
