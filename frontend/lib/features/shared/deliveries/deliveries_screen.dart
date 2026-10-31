import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/dialogs.dart';
import '../../../core/format.dart';
import '../../../core/json.dart';
import '../../../core/status.dart';
import '../../../core/theme.dart';
import 'delivery_detail_screen.dart';

/// FR10.1 / FR10.4 — the delivery calendar: what's still to arrive or be
/// resolved, grouped by day, and a history of what's been completed.
/// Scheduling, confirming and status updating all stay on this one flow
/// (Ch4 section 4.4.1: "scheduling, confirming and status updating a
/// delivery staying on Scheduled Deliveries instead of multiple screens").
class DeliveriesScreen extends StatelessWidget {
  const DeliveriesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const DefaultTabController(
      length: 2,
      child: Column(
        children: [
          TabBar(
            tabs: [
              Tab(icon: Icon(Icons.calendar_month_rounded), text: 'Scheduled'),
              Tab(icon: Icon(Icons.history_rounded), text: 'History'),
            ],
          ),
          Expanded(child: _Body()),
        ],
      ),
    );
  }
}

class _Body extends StatefulWidget {
  const _Body();

  @override
  State<_Body> createState() => _BodyState();
}

class _BodyState extends State<_Body> {
  int _version = 0;

  bool get _canSchedule {
    final role = context.read<AuthState>().role;
    return role == Roles.procurementOfficer || role == Roles.manager;
  }

  Future<({List<Json> deliveries, List<Json> schedulable})> _load() async {
    final api = context.read<AuthState>().api;
    final deliveries = asJsonList(await api.getJson('/deliveries', query: {'limit': 500}));
    var schedulable = <Json>[];
    if (_canSchedule) {
      final scheduled = deliveries.map((d) => d['po_id']).toSet();
      final orders = asJsonList(await api.getJson('/procurement/purchase-orders', query: {'limit': 500}));
      schedulable = orders.where((po) => po['status'] == 'approved' && !scheduled.contains(po['po_id'])).toList();
    }
    return (deliveries: deliveries, schedulable: schedulable);
  }

  bool _isDone(Json d) =>
      d['status'] == 'return_resolved' || (d['status'] == 'delivered' && d['verified_by'] != null);

  Future<void> _open(Json delivery) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => DeliveryDetailScreen(deliveryId: delivery['delivery_id'] as int)),
    );
    if (mounted) setState(() => _version++);
  }

  Future<void> _schedule(BuildContext context, List<Json> orders, Future<void> Function() reload) async {
    if (orders.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No approved purchase orders are waiting to be scheduled.')),
      );
      return;
    }
    int poId = orders.first['po_id'] as int;
    DateTime date = DateTime.now().add(const Duration(days: 1));
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Schedule a delivery'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<int>(
                initialValue: poId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Approved purchase order'),
                items: [
                  for (final po in orders)
                    DropdownMenuItem(
                      value: po['po_id'] as int,
                      child: Text('PO #${po['po_id']}  ·  ${money(po['total_cost'])}'),
                    ),
                ],
                onChanged: (v) => setState(() => poId = v ?? poId),
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Expected on'),
                subtitle: Text(friendlyDate(fmtDate(date))),
                trailing: const Icon(Icons.calendar_today_rounded),
                onTap: () async {
                  final d = await pickDate(context, initial: date, first: DateTime.now());
                  if (d != null) setState(() => date = d);
                },
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Schedule')),
          ],
        ),
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/deliveries', {'po_id': poId, 'scheduled_date': fmtDate(date)}),
      success: 'Delivery scheduled.',
    );
    if (ok) await reload();
  }

  @override
  Widget build(BuildContext context) {
    return AsyncView<({List<Json> deliveries, List<Json> schedulable})>(
      key: ValueKey(_version),
      load: _load,
      builder: (context, data, reload) {
        final open = data.deliveries.where((d) => !_isDone(d)).toList()
          ..sort((a, b) => (a['scheduled_date'] as String).compareTo(b['scheduled_date'] as String));
        final done = data.deliveries.where(_isDone).toList();
        final today = fmtDate(DateTime.now());

        final byDate = <String, List<Json>>{};
        for (final d in open) {
          byDate.putIfAbsent(d['scheduled_date'] as String, () => []).add(d);
        }

        return TabBarView(
          children: [
            RefreshableList(
              onRefresh: reload,
              children: [
                if (_canSchedule) ...[
                  AddRow(label: 'Schedule a delivery', onTap: () => _schedule(context, data.schedulable, reload)),
                  const SizedBox(height: 14),
                ],
                if (open.isEmpty)
                  const EmptyState(
                    icon: Icons.local_shipping_outlined,
                    message: 'Nothing waiting to arrive.',
                    detail: 'Scheduled deliveries and ones needing attention show up here.',
                  ),
                for (final entry in byDate.entries) ...[
                  SectionHeader(
                    icon: entry.key == today ? Icons.today_rounded : Icons.event_rounded,
                    label: entry.key == today ? 'Today' : friendlyDate(entry.key),
                    trailing: entry.key.compareTo(today) < 0 ? 'Overdue' : null,
                  ),
                  for (final d in entry.value) ...[
                    _DeliveryTile(delivery: d, overdue: entry.key.compareTo(today) < 0, onTap: () => _open(d)),
                    const SizedBox(height: 10),
                  ],
                  const SizedBox(height: 8),
                ],
              ],
            ),
            RefreshableList(
              onRefresh: reload,
              empty: const EmptyState(
                icon: Icons.history_rounded,
                message: 'No completed deliveries yet.',
              ),
              children: [
                for (final d in done) ...[
                  _DeliveryTile(delivery: d, overdue: false, onTap: () => _open(d)),
                  const SizedBox(height: 10),
                ],
              ],
            ),
          ],
        );
      },
    );
  }
}

class _DeliveryTile extends StatelessWidget {
  final Json delivery;
  final bool overdue;
  final VoidCallback onTap;

  const _DeliveryTile({required this.delivery, required this.overdue, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final status = delivery['status'] as String;
    final style = statusStyle(status);
    final received = status == 'delivered';
    final verified = delivery['verified_by'] != null;
    return Card(
      child: ListTile(
        onTap: onTap,
        leading: IconBadge(icon: Icons.local_shipping_rounded, color: style.color),
        title: Text(delivery['supplier_name'] as String? ?? 'PO #${delivery['po_id']}'),
        subtitle: Text(
          [
            'PO #${delivery['po_id']}',
            if (delivery['po_total_cost'] != null) money(delivery['po_total_cost']),
            if (received && !verified) 'awaiting stock check',
          ].join('  ·  '),
        ),
        trailing: SeverityChip(
          label: overdue && (status == 'awaiting_delivery' || status == 'in_transit') ? 'Overdue' : style.label,
          color: overdue && (status == 'awaiting_delivery' || status == 'in_transit') ? Severity.critical : style.color,
        ),
      ),
    );
  }
}
