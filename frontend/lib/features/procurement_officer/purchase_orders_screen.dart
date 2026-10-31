import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/dialogs.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/status.dart';
import '../../core/theme.dart';
import 'purchase_order_form_screen.dart';

/// FR9.2-FR9.6 for the Procurement Officer (and the Manager's read of it):
/// this month's budget, the system's purchase recommendations, and every
/// purchase order with its status. New orders open the order form, which
/// shows the running total and remaining budget beside the line items.
class PurchaseOrdersScreen extends StatefulWidget {
  const PurchaseOrdersScreen({super.key});

  @override
  State<PurchaseOrdersScreen> createState() => _PurchaseOrdersScreenState();
}

class _Data {
  final Json budget;
  final List<Json> recommendations;
  final List<Json> orders;
  final Map<int, Json> suppliers;
  final Map<int, Json> ingredients;

  _Data(this.budget, this.recommendations, this.orders, this.suppliers, this.ingredients);
}

class _PurchaseOrdersScreenState extends State<PurchaseOrdersScreen> {
  int _version = 0;

  bool get _isOfficer => context.read<AuthState>().role == Roles.procurementOfficer;
  bool get _isManager => context.read<AuthState>().role == Roles.manager;

  Future<_Data> _load() async {
    final api = context.read<AuthState>().api;
    final results = await Future.wait([
      api.getJson('/procurement/budget/utilisation'),
      api.getJson('/procurement/recommendations', query: {'limit': 100}),
      api.getJson('/procurement/purchase-orders', query: {'limit': 200}),
      api.getJson('/procurement/suppliers', query: {'limit': 500}),
      api.getJson('/inventory/ingredients', query: {'limit': 500}),
    ]);
    return _Data(
      asJson(results[0]),
      asJsonList(results[1]),
      asJsonList(results[2]),
      {for (final s in asJsonList(results[3])) s['supplier_id'] as int: s},
      {for (final i in asJsonList(results[4])) i['ingredient_id'] as int: i},
    );
  }

  Future<void> _generate(BuildContext context, Future<void> Function() reload) async {
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/procurement/recommendations/generate'),
      success: 'Recommendations updated from the latest forecasts and stock.',
    );
    if (ok) await reload();
  }

  Future<void> _newOrder(BuildContext context) async {
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => const PurchaseOrderFormScreen()),
    );
    if (created == true && mounted) setState(() => _version++);
  }

  Future<void> _setBudget(BuildContext context, Json budget, Future<void> Function() reload) async {
    final value = await promptNumber(
      context,
      title: 'Budget for this month',
      label: 'Monthly budget',
      suffix: 'RM',
      initial: trimNum(budget['budget_limit']),
      check: (v) => v <= 0 ? 'Must be greater than zero.' : null,
    );
    if (value == null || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final now = DateTime.now();
    final ok = await runAction(
      context,
      () => api.postJson('/procurement/budget', {
        'month': fmtDate(DateTime(now.year, now.month, 1)),
        'budget_limit': value,
      }),
      success: 'Budget saved.',
    );
    if (ok) await reload();
  }

  @override
  Widget build(BuildContext context) {
    return AsyncView<_Data>(
      key: ValueKey(_version),
      load: _load,
      builder: (context, data, reload) {
        final pct = asDouble(data.budget['utilisation_pct']);
        final color = pct >= 100 ? Severity.critical : (pct >= 80 ? Severity.warning : Severity.ok);
        return RefreshableList(
          onRefresh: reload,
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.account_balance_wallet_outlined, size: 18),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'Budget: ${money(data.budget['spent'])} of ${money(data.budget['budget_limit'])}',
                            style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                          ),
                        ),
                        SeverityChip(label: '${pct.toStringAsFixed(0)}% used', color: color),
                      ],
                    ),
                    const SizedBox(height: 8),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: LinearProgressIndicator(value: (pct / 100).clamp(0.0, 1.0), minHeight: 8, color: color),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        Expanded(child: Text('${money(data.budget['remaining'])} remaining this month')),
                        if (_isManager)
                          TextButton(
                            onPressed: () => _setBudget(context, data.budget, reload),
                            child: const Text('Change'),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            SectionHeader(
              icon: Icons.auto_awesome_rounded,
              label: 'Recommended to buy',
              trailing: data.recommendations.isEmpty ? null : '${data.recommendations.length}',
            ),
            if (data.recommendations.isEmpty)
              const Padding(
                padding: EdgeInsets.only(bottom: 8),
                child: Text('Nothing recommended right now. Generate to check forecasts against current stock.'),
              ),
            for (final r in data.recommendations.take(12))
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Card(
                  child: ListTile(
                    dense: true,
                    leading: const IconBadge(icon: Icons.shopping_basket_rounded),
                    title: Text(data.ingredients[r['ingredient_id']]?['name'] as String? ?? 'Ingredient #${r['ingredient_id']}'),
                    trailing: Text(
                      '${trimNum(r['recommended_quantity'])} ${data.ingredients[r['ingredient_id']]?['unit'] ?? ''}',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
              ),
            OutlinedButton.icon(
              onPressed: () => _generate(context, reload),
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('Update recommendations'),
            ),
            const SizedBox(height: 20),
            SectionHeader(icon: Icons.receipt_long_rounded, label: 'Purchase orders', trailing: '${data.orders.length}'),
            if (_isOfficer) ...[
              AddRow(label: 'New purchase order', onTap: () => _newOrder(context)),
              const SizedBox(height: 10),
            ],
            for (final po in data.orders) ...[
              _OrderTile(
                order: po,
                supplierName: data.suppliers[po['supplier_id']]?['name'] as String?,
                ingredients: data.ingredients,
              ),
              const SizedBox(height: 10),
            ],
            if (data.orders.isEmpty)
              const EmptyState(
                icon: Icons.receipt_long_outlined,
                message: 'No purchase orders yet.',
              ),
          ],
        );
      },
    );
  }
}

class _OrderTile extends StatelessWidget {
  final Json order;
  final String? supplierName;
  final Map<int, Json> ingredients;

  const _OrderTile({required this.order, required this.supplierName, required this.ingredients});

  Future<void> _open(BuildContext context) async {
    final api = context.read<AuthState>().api;
    final canFlag = context.read<AuthState>().role == Roles.procurementOfficer ||
        context.read<AuthState>().role == Roles.manager;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (sheetContext) => SafeArea(
        child: AsyncView<List<Json>>(
          load: () async => asJsonList(await api.getJson('/procurement/purchase-orders/${order['po_id']}/items')),
          builder: (context, items, _) => ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            children: [
              Text('PO #${order['po_id']}  ·  ${supplierName ?? 'Supplier #${order['supplier_id']}'}',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              for (final item in items)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(ingredients[item['ingredient_id']]?['name'] as String? ?? 'Ingredient #${item['ingredient_id']}'),
                  subtitle: Text(
                    '${trimNum(item['quantity'])} ${ingredients[item['ingredient_id']]?['unit'] ?? ''} at ${money(item['unit_price'])}',
                  ),
                  trailing: Text(money(asDouble(item['quantity']) * asDouble(item['unit_price']))),
                ),
              const Divider(),
              Row(
                children: [
                  const Expanded(child: Text('Total', style: TextStyle(fontWeight: FontWeight.w700))),
                  Text(money(order['total_cost']), style: const TextStyle(fontWeight: FontWeight.w700)),
                ],
              ),
              if (canFlag) ...[
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  icon: const Icon(Icons.flag_outlined),
                  label: const Text('Flag a supplier issue'),
                  onPressed: () async {
                    final description = await promptText(
                      sheetContext,
                      title: 'Flag a supplier issue',
                      label: 'What went wrong?',
                      confirmLabel: 'Flag',
                    );
                    if (description == null || !sheetContext.mounted) return;
                    final ok = await runAction(
                      sheetContext,
                      () => api.postJson('/procurement/discrepancies', {
                        'po_id': order['po_id'],
                        'supplier_id': order['supplier_id'],
                        'description': description,
                      }),
                      success: 'Issue flagged against the supplier.',
                    );
                    if (ok && sheetContext.mounted) Navigator.pop(sheetContext);
                  },
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final style = statusStyle(order['status'] as String);
    return Card(
      child: ListTile(
        onTap: () => _open(context),
        leading: IconBadge(icon: Icons.receipt_long_rounded, color: style.color),
        title: Text('PO #${order['po_id']}  ·  ${money(order['total_cost'])}'),
        subtitle: Text('${supplierName ?? 'Supplier #${order['supplier_id']}'}  ·  ${friendlyDate(order['created_at'])}'),
        trailing: SeverityChip(label: style.label, color: style.color),
      ),
    );
  }
}
