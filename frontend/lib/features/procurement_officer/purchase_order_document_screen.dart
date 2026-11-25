import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/dialogs.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/status.dart';
import '../../core/theme.dart';

/// "PO-0004": the number a purchase order is quoted by on paper.
String poNumber(dynamic id) => 'PO-${id.toString().padLeft(4, '0')}';

/// A purchase order laid out as the document it is: number and date, who it is
/// to, an itemised table with unit prices and amounts, the total, and how it
/// was decided. Opens from the purchase order list; the Procurement Officer
/// and Manager can flag a supplier issue from here.
class PurchaseOrderDocumentScreen extends StatelessWidget {
  final Json order;
  final Json? supplier;
  final Map<int, Json> ingredients;

  const PurchaseOrderDocumentScreen({
    super.key,
    required this.order,
    required this.supplier,
    required this.ingredients,
  });

  Future<void> _flagIssue(BuildContext context) async {
    final api = context.read<AuthState>().api;
    final description = await promptText(
      context,
      title: 'Flag a supplier issue',
      label: 'What went wrong?',
      confirmLabel: 'Flag',
    );
    if (description == null || !context.mounted) return;
    final ok = await runAction(
      context,
      () => api.postJson('/procurement/discrepancies', {
        'po_id': order['po_id'],
        'supplier_id': order['supplier_id'],
        'description': description,
      }),
      success: 'Issue flagged against the supplier.',
    );
    if (ok && context.mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    final role = context.read<AuthState>().role;
    final canFlag = role == Roles.shiftSupervisor || Roles.isManagement(role);
    return Scaffold(
      appBar: AppBar(title: Text(poNumber(order['po_id']))),
      body: AsyncView<List<Json>>(
        load: () async => asJsonList(
          await api.getJson(
            '/procurement/purchase-orders/${order['po_id']}/items',
          ),
        ),
        builder: (context, items, reload) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _Paper(
              order: order,
              supplier: supplier,
              items: items,
              ingredients: ingredients,
            ),
            if (canFlag) ...[
              const SizedBox(height: 16),
              OutlinedButton.icon(
                icon: const Icon(Icons.flag_outlined),
                label: const Text('Flag a supplier issue'),
                onPressed: () => _flagIssue(context),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Paper extends StatelessWidget {
  final Json order;
  final Json? supplier;
  final List<Json> items;
  final Map<int, Json> ingredients;

  const _Paper({
    required this.order,
    required this.supplier,
    required this.items,
    required this.ingredients,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final style = statusStyle(order['status'] as String);
    final muted = text.bodySmall?.copyWith(color: scheme.onSurfaceVariant);
    final label = text.labelSmall?.copyWith(
      color: scheme.onSurfaceVariant,
      fontWeight: FontWeight.w800,
      letterSpacing: 1.1,
    );
    final head = text.labelMedium?.copyWith(
      fontWeight: FontWeight.w800,
      color: scheme.onSurfaceVariant,
    );

    final total = asDouble(order['total_cost']);
    final decided = order['decided_at'];
    final rejected = order['status'] == 'rejected';
    final note = order['decision_note'] as String?;

    Widget cell(Widget child, {Alignment align = Alignment.centerLeft}) =>
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 9),
          child: Align(alignment: align, child: child),
        );

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scheme.outlineVariant),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('PURCHASE ORDER', style: label),
                    const SizedBox(height: 4),
                    Text(
                      poNumber(order['po_id']),
                      style: text.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                ),
              ),
              SeverityChip(label: style.label, color: style.color),
            ],
          ),
          const SizedBox(height: 16),
          const Divider(height: 1),
          const SizedBox(height: 14),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('SUPPLIER', style: label),
                    const SizedBox(height: 4),
                    Text(
                      supplier?['name'] as String? ??
                          'Supplier #${order['supplier_id']}',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    if (supplier?['contact_info'] != null)
                      Text(supplier!['contact_info'] as String, style: muted),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('DATE ISSUED', style: label),
                  const SizedBox(height: 4),
                  Text(
                    friendlyDate(order['created_at']),
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 18),
          Table(
            columnWidths: const {
              0: FixedColumnWidth(28),
              1: FlexColumnWidth(3),
              2: FlexColumnWidth(1.6),
              3: FlexColumnWidth(1.4),
              4: FlexColumnWidth(1.5),
            },
            border: TableBorder(
              horizontalInside: BorderSide(
                color: scheme.outlineVariant.withValues(alpha: 0.6),
              ),
            ),
            children: [
              TableRow(
                decoration: BoxDecoration(
                  color: scheme.primary.withValues(alpha: 0.08),
                ),
                children: [
                  cell(Text('#', style: head)),
                  cell(Text('Item', style: head)),
                  cell(Text('Qty', style: head), align: Alignment.centerRight),
                  cell(
                    Text('Unit price', style: head),
                    align: Alignment.centerRight,
                  ),
                  cell(
                    Text('Amount', style: head),
                    align: Alignment.centerRight,
                  ),
                ],
              ),
              for (var i = 0; i < items.length; i++)
                TableRow(
                  children: [
                    cell(Text('${i + 1}', style: muted)),
                    cell(
                      Text(
                        ingredients[items[i]['ingredient_id']]?['name']
                                as String? ??
                            'Ingredient #${items[i]['ingredient_id']}',
                      ),
                    ),
                    cell(
                      Text(
                        '${trimNum(items[i]['quantity'])} ${ingredients[items[i]['ingredient_id']]?['unit'] ?? ''}',
                      ),
                      align: Alignment.centerRight,
                    ),
                    cell(
                      Text(asDouble(items[i]['unit_price']).toStringAsFixed(2)),
                      align: Alignment.centerRight,
                    ),
                    cell(
                      Text(
                        (asDouble(items[i]['quantity']) *
                                asDouble(items[i]['unit_price']))
                            .toStringAsFixed(2),
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      align: Alignment.centerRight,
                    ),
                  ],
                ),
            ],
          ),
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerRight,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: scheme.primary.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('TOTAL  ', style: label),
                  Text(
                    money(total),
                    style: text.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (order['exceeds_budget'] == true) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                const Icon(
                  Icons.error_rounded,
                  size: 18,
                  color: Severity.critical,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'This order was above the remaining budget when it was raised.',
                    style: text.bodySmall?.copyWith(
                      color: Severity.critical,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ],
          const SizedBox(height: 18),
          const Divider(height: 1),
          const SizedBox(height: 14),
          Text('AUTHORISATION', style: label),
          const SizedBox(height: 6),
          if (decided == null && order['status'] == 'pending_approval')
            Text(
              'Waiting for the Restaurant Manager to approve or reject this order.',
              style: muted,
            )
          else ...[
            Text(
              '${rejected ? 'Rejected' : 'Approved'}${decided == null ? '' : ' on ${friendlyDateTime(decided)}'}',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            if (rejected && note != null && note.isNotEmpty) ...[
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Severity.critical.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text('Reason: $note', style: text.bodyMedium),
              ),
            ],
          ],
        ],
      ),
    );
  }
}
