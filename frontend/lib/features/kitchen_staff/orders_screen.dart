import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/clock.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

/// Incoming orders for a meal period. Kitchen Staff start an order (Preparing)
/// and finish it (Completed). The portions of completed orders are what was
/// actually served, which is what the Leftovers screen measures the prep against.
class OrdersScreen extends StatefulWidget {
  const OrdersScreen({super.key});

  @override
  State<OrdersScreen> createState() => _OrdersScreenState();
}

class _OrdersScreenState extends State<OrdersScreen> {
  String _period = 'Lunch';
  int _version = 0;
  bool _busy = false;

  Future<List<Json>> _load() async {
    final api = context.read<AuthState>().api;
    return asJsonList(
      await api.getJson('/orders', query: {
        'order_date': fmtDate(restaurantToday()),
        'meal_period': _period,
      }),
    );
  }

  Future<void> _post(String path, String success, {Map<String, dynamic>? extra}) async {
    setState(() => _busy = true);
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson(path, {
        'order_date': fmtDate(restaurantToday()),
        'meal_period': _period,
        ...?extra,
      }),
      success: success,
    );
    if (!mounted) return;
    setState(() {
      _busy = false;
      if (ok) _version++;
    });
  }

  Future<void> _advance(Json order, String status) async {
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.patchJson('/orders/${order['order_id']}/status', {'status': status}),
    );
    if (ok && mounted) setState(() => _version++);
  }

  @override
  Widget build(BuildContext context) {
    return AsyncView<List<Json>>(
      key: ValueKey('$_period|$_version'),
      load: _load,
      builder: (context, orders, reload) {
        int count(String s) => orders.where((o) => o['status'] == s).length;
        final pending = orders.where((o) => o['status'] == 'pending').toList();
        final preparing = orders.where((o) => o['status'] == 'preparing').toList();
        final completed = orders.where((o) => o['status'] == 'completed').toList().reversed.toList();
        final open = pending.length + preparing.length;

        return RefreshableList(
          onRefresh: reload,
          children: [
            Row(
              children: [
                const IconBadge(icon: Icons.receipt_long_rounded),
                const SizedBox(width: 12),
                Expanded(child: Text('Incoming orders', style: Theme.of(context).textTheme.titleLarge)),
              ],
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: _period,
              decoration: const InputDecoration(
                labelText: 'Meal period',
                contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              ),
              items: mealPeriods.map((p) => DropdownMenuItem(value: p, child: Text(p))).toList(),
              onChanged: (v) => setState(() => _period = v ?? _period),
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                SeverityChip(label: '${count('pending')} incoming', color: Severity.warning),
                SeverityChip(label: '${count('preparing')} preparing', color: Theme.of(context).colorScheme.primary),
                SeverityChip(label: '${count('completed')} completed', color: Severity.ok),
              ],
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _busy ? null : () => _post('/orders/simulate', 'Sample orders added.'),
                    icon: const Icon(Icons.add_shopping_cart_rounded, size: 18),
                    label: const Text('Add sample orders'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: (_busy || open == 0)
                        ? null
                        : () => _post('/orders/complete-all', 'All orders marked completed.'),
                    icon: const Icon(Icons.done_all_rounded, size: 18),
                    label: const Text('Complete all'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            if (orders.isEmpty)
              EmptyState(
                icon: Icons.receipt_long_outlined,
                message: 'No orders for $_period yet.',
                detail: 'Orders appear here as they come in. There is no till connected, so tap '
                    '"Add sample orders" to create some to work through.',
              )
            else ...[
              if (pending.isNotEmpty) ...[
                SectionHeader(icon: Icons.notifications_active_rounded, label: 'Incoming', trailing: '${pending.length}'),
                for (final o in pending) _OrderTile(order: o, action: 'Start', onAction: () => _advance(o, 'preparing')),
              ],
              if (preparing.isNotEmpty) ...[
                const SizedBox(height: 8),
                SectionHeader(icon: Icons.soup_kitchen_rounded, label: 'Preparing', trailing: '${preparing.length}'),
                for (final o in preparing) _OrderTile(order: o, action: 'Done', onAction: () => _advance(o, 'completed')),
              ],
              if (completed.isNotEmpty) ...[
                const SizedBox(height: 8),
                SectionHeader(icon: Icons.check_circle_outline_rounded, label: 'Completed', trailing: '${completed.length}'),
                for (final o in completed.take(15)) _OrderTile(order: o),
                if (completed.length > 15)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text('and ${completed.length - 15} more', style: Theme.of(context).textTheme.bodySmall),
                  ),
              ],
            ],
          ],
        );
      },
    );
  }
}

class _OrderTile extends StatelessWidget {
  final Json order;
  final String? action;
  final VoidCallback? onAction;

  const _OrderTile({required this.order, this.action, this.onAction});

  @override
  Widget build(BuildContext context) {
    final qty = asDouble(order['quantity']).round();
    final done = order['status'] == 'completed';
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Card(
        child: ListTile(
          dense: true,
          leading: IconBadge(
            icon: done ? Icons.check_rounded : Icons.restaurant_rounded,
            color: done ? Severity.ok : null,
          ),
          title: Text('$qty × ${order['menu_item_name'] ?? 'Dish #${order['menu_item_id']}'}'),
          subtitle: Text('Order #${order['order_id']}${_time(order['created_at'])}'),
          trailing: action == null
              ? null
              : FilledButton.tonal(onPressed: onAction, child: Text(action!)),
        ),
      ),
    );
  }

  String _time(dynamic value) {
    if (value == null) return '';
    final t = DateTime.tryParse(value.toString())?.toLocal();
    if (t == null) return '';
    final hh = t.hour.toString().padLeft(2, '0');
    final mm = t.minute.toString().padLeft(2, '0');
    return '  ·  $hh:$mm';
  }
}
