import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/json.dart';
import '../../core/theme.dart';
import '../../models/portion_recommendation.dart';
import '../../models/purchase_order.dart';

/// Ch4 §4.4.1: "The 'Needs your attention' list flags 3 pending Purchase
/// Orders in critical red and 2 portion-review dishes in warning amber,
/// each is paired with a label ('Review', 'View'), never left to color
/// alone." One combined list rather than two separate screens, per the
/// same section's "Screens are scoped to the task, not to the use-case
/// document" principle — a Manager's actual job here is clearing a queue
/// of approvals, not navigating module-by-module.
class ApprovalsScreen extends StatefulWidget {
  const ApprovalsScreen({super.key});

  @override
  State<ApprovalsScreen> createState() => _ApprovalsScreenState();
}

class _ApprovalsScreenState extends State<ApprovalsScreen> {
  late Future<_ApprovalsData> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_ApprovalsData> _load() async {
    final api = context.read<AuthState>().api;
    final posRaw = await api.listPurchaseOrders(status: 'pending_approval');
    final portionsRaw = await api.listPortionRecommendations(status: 'pending');
    Json? budget;
    try {
      budget = asJson(await api.getJson('/procurement/budget/utilisation'));
    } catch (_) {
      budget = null; // the queue is still usable without the budget figure
    }
    final menu = asJsonList(await api.getJson('/menu-items', query: {'include_inactive': true, 'limit': 500}));
    return _ApprovalsData(
      budget: budget,
      itemNames: {for (final m in menu) m['menu_item_id'] as int: m['name'] as String},
      purchaseOrders: posRaw
          .map((e) => PurchaseOrder.fromJson(e as Map<String, dynamic>))
          .toList(),
      portionRecommendations: portionsRaw
          .map((e) => PortionRecommendation.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_ApprovalsData>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          final message = snapshot.error is ApiException
              ? (snapshot.error as ApiException).message
              : 'Failed to load approvals.';
          return Center(child: Text(message));
        }
        final data = snapshot.data!;
        if (data.purchaseOrders.isEmpty &&
            data.portionRecommendations.isEmpty) {
          return RefreshIndicator(
            onRefresh: _refresh,
            child: ListView(
              children: const [
                SizedBox(height: 120),
                EmptyState(
                  icon: Icons.task_alt_rounded,
                  message: 'Nothing needs your attention right now.',
                ),
              ],
            ),
          );
        }
        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (data.budget != null) ...[
                _BudgetCard(budget: data.budget!),
                const SizedBox(height: 16),
              ],
              if (data.purchaseOrders.isNotEmpty) ...[
                SectionHeader(
                  icon: Icons.local_shipping_outlined,
                  label: 'Pending purchase orders',
                  trailing: '${data.purchaseOrders.length}',
                ),
                for (final po in data.purchaseOrders) ...[
                  _PurchaseOrderTile(po: po, remaining: data.remaining, onChanged: _refresh),
                  const SizedBox(height: 10),
                ],
                const SizedBox(height: 14),
              ],
              if (data.portionRecommendations.isNotEmpty) ...[
                SectionHeader(
                  icon: Icons.restaurant_menu_outlined,
                  label: 'Portion size reviews',
                  trailing: '${data.portionRecommendations.length}',
                ),
                for (final r in data.portionRecommendations) ...[
                  _PortionRecommendationTile(
                    recommendation: r,
                    itemName: data.itemNames[r.menuItemId],
                    onChanged: _refresh,
                  ),
                  const SizedBox(height: 10),
                ],
              ],
            ],
          ),
        );
      },
    );
  }
}

class _ApprovalsData {
  final List<PurchaseOrder> purchaseOrders;
  final List<PortionRecommendation> portionRecommendations;
  // This month's budget position, and dish names for the portion reviews.
  final Json? budget;
  final Map<int, String> itemNames;

  _ApprovalsData({
    required this.purchaseOrders,
    required this.portionRecommendations,
    required this.budget,
    required this.itemNames,
  });

  double? get remaining => budget == null ? null : asDouble(budget!['remaining']);
}

class _BudgetCard extends StatelessWidget {
  final Json budget;

  const _BudgetCard({required this.budget});

  @override
  Widget build(BuildContext context) {
    final pct = asDouble(budget['utilisation_pct']);
    final color = pct >= 100 ? Severity.critical : (pct >= 80 ? Severity.warning : Severity.ok);
    return Card(
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
                    'This month: ${money(budget['spent'])} of ${money(budget['budget_limit'])}',
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
            Text('${money(budget['remaining'])} remaining'),
          ],
        ),
      ),
    );
  }
}

class _PurchaseOrderTile extends StatelessWidget {
  final PurchaseOrder po;
  final double? remaining;
  final Future<void> Function() onChanged;

  const _PurchaseOrderTile({required this.po, required this.remaining, required this.onChanged});

  Future<void> _viewItems(BuildContext context) async {
    final api = context.read<AuthState>().api;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: AsyncView<({List<Json> items, Map<int, Json> ingredients})>(
          load: () async {
            final results = await Future.wait([
              api.getJson('/procurement/purchase-orders/${po.poId}/items'),
              api.getJson('/inventory/ingredients', query: {'limit': 500}),
            ]);
            return (
              items: asJsonList(results[0]),
              ingredients: {for (final i in asJsonList(results[1])) i['ingredient_id'] as int: i},
            );
          },
          builder: (context, data, _) => ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            children: [
              Text('PO #${po.poId} items', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              for (final item in data.items)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(data.ingredients[item['ingredient_id']]?['name'] as String? ?? 'Ingredient #${item['ingredient_id']}'),
                  subtitle: Text(
                    '${trimNum(item['quantity'])} ${data.ingredients[item['ingredient_id']]?['unit'] ?? ''} at ${money(item['unit_price'])}',
                  ),
                  trailing: Text(money(asDouble(item['quantity']) * asDouble(item['unit_price']))),
                ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'PO #${po.poId} · RM ${po.totalCost}',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                SeverityChip(label: 'Review', color: Severity.critical),
              ],
            ),
            if (po.exceedsBudget) ...[
              const SizedBox(height: 6),
              Text(
                'Exceeds monthly budget',
                style: TextStyle(
                  color: Severity.warning,
                  fontWeight: FontWeight.w600,
                  fontSize: 12,
                ),
              ),
            ],
            if (remaining != null) ...[
              const SizedBox(height: 6),
              Builder(
                builder: (context) {
                  final total = double.tryParse(po.totalCost.toString()) ?? 0;
                  final over = total > remaining!;
                  return Text(
                    over
                        ? 'Remaining budget ${money(remaining)}: this order is ${money(total - remaining!)} over'
                        : 'Remaining budget ${money(remaining)}: ${money(remaining! - total)} left if approved',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: over ? Severity.critical : Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  );
                },
              ),
            ],
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: () => _viewItems(context),
                icon: const Icon(Icons.list_alt_rounded, size: 18),
                label: const Text('View items'),
              ),
            ),
            PrimarySecondaryActions(
              primaryLabel: 'Approve',
              secondaryLabel: 'Reject',
              onPrimary: () => _act(context, approve: true),
              onSecondary: () => _act(context, approve: false),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _act(BuildContext context, {required bool approve}) async {
    final api = context.read<AuthState>().api;
    try {
      if (approve) {
        await api.approvePurchaseOrder(po.poId);
      } else {
        await api.rejectPurchaseOrder(po.poId);
      }
      await onChanged();
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _PortionRecommendationTile extends StatelessWidget {
  final PortionRecommendation recommendation;
  final String? itemName;
  final Future<void> Function() onChanged;

  const _PortionRecommendationTile({
    required this.recommendation,
    required this.itemName,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${itemName ?? 'Menu item #${recommendation.menuItemId}'} · ${recommendation.leftoverRate}% leftover rate',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                SeverityChip(label: 'View', color: Severity.warning),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              'Suggested portion: ${recommendation.suggestedPortionSize}',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 10),
            PrimarySecondaryActions(
              primaryLabel: 'Approve',
              secondaryLabel: 'Reject',
              onPrimary: () => _act(context, approve: true),
              onSecondary: () => _act(context, approve: false),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _act(BuildContext context, {required bool approve}) async {
    final api = context.read<AuthState>().api;
    try {
      if (approve) {
        await api.approvePortionRecommendation(recommendation.recommendationId);
      } else {
        await api.rejectPortionRecommendation(recommendation.recommendationId);
      }
      await onChanged();
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}
