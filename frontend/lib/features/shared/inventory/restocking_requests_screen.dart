import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/json.dart';
import '../../../core/theme.dart';

/// UC-IM-06 / FR3.5 — Inventory Staff work through the restocking requests
/// Kitchen Staff have sent, urgent ones first.
class RestockingRequestsScreen extends StatelessWidget {
  const RestockingRequestsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<({List<Json> requests, Map<int, Json> ingredients})>(
      load: () async {
        final results = await Future.wait([
          api.getJson('/inventory/restocking-requests', query: {'limit': 200}),
          api.getJson('/inventory/ingredients', query: {'limit': 500}),
        ]);
        return (
          requests: asJsonList(results[0]),
          ingredients: {for (final i in asJsonList(results[1])) i['ingredient_id'] as int: i},
        );
      },
      builder: (context, data, reload) {
        final open = data.requests.where((r) => r['status'] == 'pending').toList();
        final done = data.requests.where((r) => r['status'] != 'pending').toList();
        return RefreshableList(
          onRefresh: reload,
          empty: const EmptyState(
            icon: Icons.add_shopping_cart_rounded,
            message: 'No restocking requests.',
            detail: 'Requests from Kitchen Staff appear here.',
          ),
          children: [
            if (open.isNotEmpty) SectionHeader(icon: Icons.pending_actions_rounded, label: 'To do', trailing: '${open.length}'),
            for (final r in open) _RequestTile(request: r, ingredient: data.ingredients[r['ingredient_id']], onChanged: reload),
            if (done.isNotEmpty) ...[
              const SizedBox(height: 14),
              const SectionHeader(icon: Icons.check_circle_outline_rounded, label: 'Handled'),
              for (final r in done) _RequestTile(request: r, ingredient: data.ingredients[r['ingredient_id']], onChanged: reload),
            ],
          ],
        );
      },
    );
  }
}

class _RequestTile extends StatelessWidget {
  final Json request;
  final Json? ingredient;
  final Future<void> Function() onChanged;

  const _RequestTile({required this.request, required this.ingredient, required this.onChanged});

  Future<void> _set(BuildContext context, String status) async {
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.patchJson('/inventory/restocking-requests/${request['request_id']}', {'status': status}),
      success: status == 'fulfilled' ? 'Marked as restocked.' : 'Request declined.',
    );
    if (ok) await onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final status = request['status'] as String;
    final urgent = request['urgency'] == true;
    final unit = ingredient?['unit'] ?? '';
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${ingredient?['name'] ?? 'Ingredient #${request['ingredient_id']}'}  ·  ${trimNum(request['quantity'])} $unit',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                    ),
                  ),
                  if (status == 'pending')
                    SeverityChip(
                      label: urgent ? 'Urgent' : 'Routine',
                      color: urgent ? Severity.critical : Severity.warning,
                    )
                  else
                    SeverityChip(
                      label: status == 'fulfilled' ? 'Restocked' : 'Declined',
                      color: status == 'fulfilled' ? Severity.ok : Severity.critical,
                    ),
                ],
              ),
              if (status == 'pending') ...[
                const SizedBox(height: 10),
                PrimarySecondaryActions(
                  primaryLabel: 'Restocked',
                  secondaryLabel: 'Decline',
                  onPrimary: () => _set(context, 'fulfilled'),
                  onSecondary: () => _set(context, 'declined'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
