import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/dialogs.dart';
import '../../../core/format.dart';
import '../../../core/json.dart';
import '../../../core/theme.dart';
import '../../procurement_officer/purchase_order_form_screen.dart';

/// UC-IM-06 / FR3.5 — Inventory Staff work through the restocking requests
/// Kitchen Staff have sent, urgent ones first. Approving asks for
/// confirmation; declining asks for a reason, which goes back to the kitchen;
/// every decision is kept in the History tab.
class RestockingRequestsScreen extends StatelessWidget {
  const RestockingRequestsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const DefaultTabController(
      length: 2,
      child: Column(
        children: [
          TabBar(
            tabs: [
              Tab(icon: Icon(Icons.pending_actions_rounded), text: 'To do'),
              Tab(icon: Icon(Icons.history_rounded), text: 'History'),
            ],
          ),
          Expanded(child: _Requests()),
        ],
      ),
    );
  }
}

typedef _Data = ({List<Json> requests, Map<int, Json> ingredients});

class _Requests extends StatefulWidget {
  const _Requests();

  @override
  State<_Requests> createState() => _RequestsState();
}

class _RequestsState extends State<_Requests> {
  int _version = 0;

  Future<_Data> _load() async {
    final api = context.read<AuthState>().api;
    final results = await Future.wait([
      api.getJson('/inventory/restocking-requests', query: {'limit': 500}),
      api.getJson('/inventory/ingredients', query: {'limit': 500}),
    ]);
    return (
      requests: asJsonList(results[0]),
      ingredients: {for (final i in asJsonList(results[1])) i['ingredient_id'] as int: i},
    );
  }

  @override
  Widget build(BuildContext context) {
    return AsyncView<_Data>(
      key: ValueKey(_version),
      load: _load,
      builder: (context, data, reload) {
        final open = data.requests.where((r) => r['status'] == 'pending').toList();
        final done = data.requests.where((r) => r['status'] != 'pending').toList()
          ..sort((a, b) => ((b['decided_at'] ?? '') as String).compareTo((a['decided_at'] ?? '') as String));
        Future<void> changed() async => setState(() => _version++);
        return TabBarView(
          children: [
            RefreshableList(
              onRefresh: reload,
              empty: const EmptyState(
                icon: Icons.add_shopping_cart_rounded,
                message: 'No restocking requests.',
                detail: 'Requests from Kitchen Staff appear here.',
              ),
              children: [
                if (open.isNotEmpty)
                  SectionHeader(icon: Icons.pending_actions_rounded, label: 'To decide', trailing: '${open.length}'),
                for (final r in open)
                  _RequestTile(request: r, ingredient: data.ingredients[r['ingredient_id']], onChanged: changed),
                if (open.isEmpty)
                  const EmptyState(
                    icon: Icons.check_circle_outline_rounded,
                    message: 'Nothing waiting.',
                    detail: 'Decided requests are in the History tab.',
                  ),
              ],
            ),
            RefreshableList(
              onRefresh: reload,
              children: [
                if (done.isEmpty)
                  const EmptyState(
                    icon: Icons.history_rounded,
                    message: 'No decisions yet.',
                    detail: 'Approved and declined requests appear here.',
                  ),
                for (final r in done) _RequestTile(request: r, ingredient: data.ingredients[r['ingredient_id']], onChanged: changed),
              ],
            ),
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

  String get _what =>
      '${ingredient?['name'] ?? 'Ingredient #${request['ingredient_id']}'}  ·  ${trimNum(request['quantity'])} ${ingredient?['unit'] ?? ''}';

  Future<void> _approve(BuildContext context) async {
    final sure = await confirmAction(
      context,
      title: 'Approve this request?',
      message: 'The kitchen is told that $_what is approved. Approving does not order it or change stock: '
          'stock goes up when the delivery is booked in. You can no longer change this decision.',
      confirmLabel: 'Approve',
    );
    if (!sure || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.patchJson('/inventory/restocking-requests/${request['request_id']}', {'status': 'fulfilled'}),
      success: 'Approved.',
    );
    if (!ok) return;
    // Approval alone orders nothing, so offer the next step while it is fresh:
    // a purchase request with this ingredient and quantity already filled in.
    if (context.mounted) await _offerPurchaseRequest(context);
    await onChanged();
  }

  Future<void> _offerPurchaseRequest(BuildContext context) async {
    final start = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Start a purchase request?'),
        content: Text(
          '$_what is approved, but nothing has been ordered yet. Start a purchase request with it filled in, '
          'and the Manager can approve the order.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Not now')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Start request')),
        ],
      ),
    );
    if (start != true || !context.mounted) return;
    await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => PurchaseOrderFormScreen(
          initialIngredientId: request['ingredient_id'] as int,
          initialQuantity: trimNum(request['quantity']),
        ),
      ),
    );
  }

  Future<void> _decline(BuildContext context) async {
    final reason = await promptText(
      context,
      title: 'Decline this request?',
      message: 'This cannot be undone. The reason is sent to the kitchen and kept in the history.',
      label: 'Reason for declining',
      confirmLabel: 'Decline',
      minLength: 3,
    );
    if (reason == null || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.patchJson('/inventory/restocking-requests/${request['request_id']}', {'status': 'declined', 'note': reason}),
      success: 'Declined.',
    );
    if (ok) await onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final status = request['status'] as String;
    final urgent = request['urgency'] == true;
    final note = request['decision_note'] as String?;
    final decidedAt = request['decided_at'];
    final text = Theme.of(context).textTheme;
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
                  Expanded(child: Text(_what, style: text.titleSmall?.copyWith(fontWeight: FontWeight.w700))),
                  if (status == 'pending')
                    SeverityChip(label: urgent ? 'Urgent' : 'Routine', color: urgent ? Severity.critical : Severity.warning)
                  else
                    SeverityChip(
                      label: status == 'fulfilled' ? 'Approved' : 'Declined',
                      color: status == 'fulfilled' ? Severity.ok : Severity.critical,
                    ),
                ],
              ),
              if (status != 'pending') ...[
                const SizedBox(height: 6),
                Text(
                  '${status == 'fulfilled' ? 'Approved' : 'Declined'}'
                  '${decidedAt == null ? '' : ' · ${friendlyDateTime(decidedAt)}'}',
                  style: text.bodySmall?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
                ),
                if (note != null && note.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: Severity.critical.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text('Reason: $note', style: text.bodyMedium),
                  ),
                ],
              ] else ...[
                const SizedBox(height: 10),
                PrimarySecondaryActions(
                  primaryLabel: 'Approve',
                  secondaryLabel: 'Decline',
                  onPrimary: () => _approve(context),
                  onSecondary: () => _decline(context),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
