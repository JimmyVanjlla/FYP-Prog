import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/format.dart';
import '../../../core/json.dart';
import '../../../core/theme.dart';

/// FR5.4 / FR6.4 — everything the backend has raised for this user (prep
/// updates, high-demand alerts, near-expiry and low-stock warnings, PO
/// decisions, published shifts, failed scheduled jobs). Push delivery is
/// separate (see core/push_service.dart); this inbox is the in-app record,
/// so a missed push is never a missed alert.
class NotificationsScreen extends StatelessWidget {
  const NotificationsScreen({super.key});

  static ({IconData icon, Color? color, String label}) _style(String type) {
    switch (type) {
      case 'high_demand_alert':
        return (icon: Icons.trending_up_rounded, color: Severity.warning, label: 'High demand');
      case 'near_expiry_alert':
        return (icon: Icons.hourglass_bottom_rounded, color: Severity.warning, label: 'Near expiry');
      case 'low_stock_alert':
        return (icon: Icons.inventory_2_rounded, color: Severity.critical, label: 'Low stock');
      case 'job_failure':
        return (icon: Icons.error_rounded, color: Severity.critical, label: 'Job failed');
      case 'po_approved':
        return (icon: Icons.check_circle_rounded, color: Severity.ok, label: 'PO approved');
      case 'po_rejected':
        return (icon: Icons.cancel_rounded, color: Severity.critical, label: 'PO rejected');
      case 'shift_published':
        return (icon: Icons.event_available_rounded, color: null, label: 'Shift');
      case 'prep_update':
        return (icon: Icons.restaurant_rounded, color: null, label: 'Prep update');
      default:
        return (icon: Icons.notifications_rounded, color: null, label: 'Notice');
    }
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<List<Json>>(
      load: () async => asJsonList(await api.getJson('/kitchen/notifications', query: {'limit': 100})),
      builder: (context, items, reload) => RefreshableList(
        onRefresh: reload,
        empty: const EmptyState(
          icon: Icons.notifications_none_rounded,
          message: 'No notifications yet.',
          detail: 'Alerts and updates for your role will appear here.',
        ),
        children: [
          for (final n in items) ...[
            Card(
              child: ListTile(
                leading: IconBadge(
                  icon: _style(n['type'] as String).icon,
                  color: _style(n['type'] as String).color,
                ),
                title: Text(n['message'] as String),
                subtitle: Text(
                  '${_style(n['type'] as String).label}  ·  ${friendlyDateTime(n['created_at'])}',
                ),
                isThreeLine: (n['message'] as String).length > 60,
              ),
            ),
            const SizedBox(height: 10),
          ],
        ],
      ),
    );
  }
}
