import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
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
    return _ApprovalsData(
      purchaseOrders: posRaw
          .map((e) => PurchaseOrder.fromJson(e as Map<String, dynamic>))
          .toList(),
      portionRecommendations: portionsRaw
          .map((e) => PortionRecommendation.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  Future<void> _refresh() async {
    setState(() => _future = _load());
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
                Center(child: Text('Nothing needs your attention right now.')),
              ],
            ),
          );
        }
        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (data.purchaseOrders.isNotEmpty) ...[
                Text(
                  'Pending purchase orders',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                for (final po in data.purchaseOrders)
                  _PurchaseOrderTile(po: po, onChanged: _refresh),
                const SizedBox(height: 24),
              ],
              if (data.portionRecommendations.isNotEmpty) ...[
                Text(
                  'Portion size reviews',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                for (final r in data.portionRecommendations)
                  _PortionRecommendationTile(
                    recommendation: r,
                    onChanged: _refresh,
                  ),
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

  _ApprovalsData({
    required this.purchaseOrders,
    required this.portionRecommendations,
  });
}

class _PurchaseOrderTile extends StatelessWidget {
  final PurchaseOrder po;
  final Future<void> Function() onChanged;

  const _PurchaseOrderTile({required this.po, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text('PO #${po.poId} · RM ${po.totalCost}')),
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
  final Future<void> Function() onChanged;

  const _PortionRecommendationTile({
    required this.recommendation,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Menu item #${recommendation.menuItemId} · ${recommendation.leftoverRate}% leftover rate',
                  ),
                ),
                SeverityChip(label: 'View', color: Severity.warning),
              ],
            ),
            const SizedBox(height: 4),
            Text('Suggested portion: ${recommendation.suggestedPortionSize}'),
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
