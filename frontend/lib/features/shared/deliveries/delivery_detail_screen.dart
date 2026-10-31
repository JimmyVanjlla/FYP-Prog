import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/dialogs.dart';
import '../../../core/format.dart';
import '../../../core/json.dart';
import '../../../core/status.dart';
import '../../../core/theme.dart';

/// One delivery, end to end:
///  - Delivery/Logistics Staff mark it in transit, then confirm receipt
///    item by item (FR10.2). A quantity that strays past the configured
///    threshold turns critical-red *as it's typed* (Ch4 section 4.4.1), and
///    will be reported as a discrepancy rather than accepted (FR10.5).
///  - Discrepancies and returns are shown and resolved here (FR10.3), and a
///    return is closed out once its discrepancies are (UC-DM-04).
///  - Inventory Staff then verify it against stock records, which is the
///    step that actually adds it to stock (UC-IM-01).
class DeliveryDetailScreen extends StatefulWidget {
  final int deliveryId;

  const DeliveryDetailScreen({super.key, required this.deliveryId});

  @override
  State<DeliveryDetailScreen> createState() => _DeliveryDetailScreenState();
}

class _Detail {
  final Json delivery;
  final List<Json> items;
  final Map<int, Json> ingredients;
  final List<Json> discrepancies;
  final double threshold;

  _Detail(this.delivery, this.items, this.ingredients, this.discrepancies, this.threshold);
}

class _DeliveryDetailScreenState extends State<DeliveryDetailScreen> {
  int _version = 0;

  Future<_Detail> _load() async {
    final api = context.read<AuthState>().api;
    final results = await Future.wait([
      api.getJson('/deliveries', query: {'limit': 500}),
      api.getJson('/deliveries/${widget.deliveryId}/items'),
      api.getJson('/inventory/ingredients', query: {'limit': 500}),
      api.getJson('/deliveries/discrepancies', query: {'delivery_id': widget.deliveryId}),
      api.getJson('/config'),
    ]);
    final delivery = asJsonList(results[0]).firstWhere((d) => d['delivery_id'] == widget.deliveryId);
    return _Detail(
      delivery,
      asJsonList(results[1]),
      {for (final i in asJsonList(results[2])) i['ingredient_id'] as int: i},
      asJsonList(results[3]),
      asDouble(asJson(results[4])['delivery_deviation_threshold'], 10),
    );
  }

  void _reload() => setState(() => _version++);

  Future<void> _setStatus(String status, String message) async {
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.patchJson('/deliveries/${widget.deliveryId}/status', {'status': status}),
      success: message,
    );
    if (ok) _reload();
  }

  Future<void> _verify() async {
    final proceed = await confirmAction(
      context,
      title: 'Verify against stock records?',
      message: 'The received quantities will be added to ingredient stock. This can only be done once.',
      confirmLabel: 'Verify and add to stock',
    );
    if (!proceed || !mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/deliveries/${widget.deliveryId}/verify'),
      success: 'Verified. Stock updated.',
    );
    if (ok) _reload();
  }

  Future<void> _resolve(Json discrepancy) async {
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/deliveries/discrepancies/${discrepancy['discrepancy_id']}/resolve'),
      success: 'Discrepancy resolved.',
    );
    if (ok) _reload();
  }

  @override
  Widget build(BuildContext context) {
    final role = context.read<AuthState>().role;
    final isDeliveryStaff = role == Roles.deliveryStaff;
    final canUpdateStatus = isDeliveryStaff || role == Roles.manager;
    final canResolve = canUpdateStatus || role == Roles.procurementOfficer;
    final isInventory = role == Roles.inventoryStaff;

    return Scaffold(
      appBar: AppBar(title: const Text('Delivery')),
      body: AsyncView<_Detail>(
        key: ValueKey(_version),
        load: _load,
        builder: (context, d, reload) {
          final status = d.delivery['status'] as String;
          final style = statusStyle(status);
          final awaiting = status == 'awaiting_delivery' || status == 'in_transit';
          final verified = d.delivery['verified_by'] != null;
          final openDiscrepancies = d.discrepancies.where((x) => x['status'] == 'open').toList();

          return RefreshableList(
            onRefresh: reload,
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              d.delivery['supplier_name'] as String? ?? 'PO #${d.delivery['po_id']}',
                              style: Theme.of(context).textTheme.titleLarge,
                            ),
                          ),
                          SeverityChip(label: style.label, color: style.color),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Expected ${friendlyDate(d.delivery['scheduled_date'])}'
                        '${d.delivery['po_total_cost'] == null ? '' : '  ·  ${money(d.delivery['po_total_cost'])}'}',
                      ),
                      if (status == 'delivered')
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            verified
                                ? 'Verified against stock records ${friendlyDateTime(d.delivery['verified_at'])}.'
                                : 'Received. Waiting for Inventory Staff to verify it against stock records.',
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              if (awaiting && isDeliveryStaff) ...[
                if (status == 'awaiting_delivery')
                  OutlinedButton.icon(
                    onPressed: () => _setStatus('in_transit', 'Marked as in transit.'),
                    icon: const Icon(Icons.local_shipping_outlined),
                    label: const Text('Mark as in transit'),
                  ),
                const SizedBox(height: 16),
                _ReceiptForm(
                  deliveryId: widget.deliveryId,
                  items: d.items,
                  ingredients: d.ingredients,
                  threshold: d.threshold,
                  onConfirmed: reload,
                ),
              ] else ...[
                SectionHeader(icon: Icons.inventory_rounded, label: 'Items', trailing: '${d.items.length}'),
                for (final item in d.items)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: _ItemRow(item: item, ingredient: d.ingredients[item['ingredient_id']], threshold: d.threshold),
                  ),
              ],

              if (d.discrepancies.isNotEmpty) ...[
                const SizedBox(height: 16),
                const SectionHeader(icon: Icons.report_problem_rounded, label: 'Discrepancies'),
                for (final x in d.discrepancies)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Card(
                      child: ListTile(
                        leading: IconBadge(
                          icon: Icons.report_problem_rounded,
                          color: x['status'] == 'open' ? Severity.critical : Severity.ok,
                        ),
                        title: Text(
                          '${d.ingredients[x['ingredient_id']]?['name'] ?? 'Ingredient #${x['ingredient_id']}'}: '
                          '${x['issue_type'] == 'shortage' ? 'short delivery' : 'wrong item'}',
                        ),
                        subtitle: Text(x['return_required'] == true ? 'Goods to be returned' : 'No return needed'),
                        trailing: x['status'] == 'open'
                            ? (canResolve
                                ? FilledButton.tonal(onPressed: () => _resolve(x), child: const Text('Resolve'))
                                : const SeverityChip(label: 'Open', color: Severity.critical))
                            : const SeverityChip(label: 'Resolved', color: Severity.ok),
                      ),
                    ),
                  ),
              ],

              if (status == 'return_pending' && canUpdateStatus) ...[
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed: openDiscrepancies.isNotEmpty
                      ? null
                      : () => _setStatus('return_resolved', 'Return marked as resolved.'),
                  icon: const Icon(Icons.assignment_return_rounded),
                  label: const Text('Mark return resolved'),
                ),
                if (openDiscrepancies.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      'Resolve the open discrepancies above first.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
              ],

              if (status == 'delivered' && !verified && isInventory) ...[
                const SizedBox(height: 16),
                FilledButton.icon(
                  onPressed: _verify,
                  icon: const Icon(Icons.fact_check_rounded),
                  label: const Text('Verify against stock records'),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _ItemRow extends StatelessWidget {
  final Json item;
  final Json? ingredient;
  final double threshold;

  const _ItemRow({required this.item, required this.ingredient, required this.threshold});

  @override
  Widget build(BuildContext context) {
    final expected = asDouble(item['expected_quantity']);
    final received = item['received_quantity'];
    final unit = ingredient?['unit'] ?? '';
    double? dev;
    if (received != null && expected > 0) dev = (asDouble(received) - expected).abs() / expected * 100;
    final off = dev != null && dev > threshold;
    return Card(
      child: ListTile(
        leading: IconBadge(icon: Icons.inventory_2_rounded, color: off ? Severity.critical : null),
        title: Text(ingredient?['name'] as String? ?? 'Ingredient #${item['ingredient_id']}'),
        subtitle: Text(
          received == null
              ? 'Expected ${trimNum(expected)} $unit'
              : 'Expected ${trimNum(expected)} $unit  ·  received ${trimNum(received)} $unit',
        ),
        trailing: received == null
            ? null
            : SeverityChip(label: off ? 'Off by ${dev.toStringAsFixed(0)}%' : 'Matches', color: off ? Severity.critical : Severity.ok),
      ),
    );
  }
}

/// The receipt-confirmation form: expected beside received for every item,
/// with the mismatch flagged the instant it's typed.
class _ReceiptForm extends StatefulWidget {
  final int deliveryId;
  final List<Json> items;
  final Map<int, Json> ingredients;
  final double threshold;
  final Future<void> Function() onConfirmed;

  const _ReceiptForm({
    required this.deliveryId,
    required this.items,
    required this.ingredients,
    required this.threshold,
    required this.onConfirmed,
  });

  @override
  State<_ReceiptForm> createState() => _ReceiptFormState();
}

class _ReceiptFormState extends State<_ReceiptForm> {
  late final Map<int, TextEditingController> _controllers = {
    for (final item in widget.items)
      item['item_id'] as int: TextEditingController(text: trimNum(item['expected_quantity'])),
  };
  bool _submitting = false;

  @override
  void dispose() {
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  double? _deviation(Json item) {
    final expected = asDouble(item['expected_quantity']);
    final entered = double.tryParse(_controllers[item['item_id']]!.text.trim());
    // A negative or unreadable entry is an input error, shown as such, not a discrepancy.
    if (entered == null || entered < 0 || expected <= 0) return null;
    return (entered - expected).abs() / expected * 100;
  }

  bool get _allValid => widget.items.every((item) {
    final v = double.tryParse(_controllers[item['item_id']]!.text.trim());
    return v != null && v >= 0;
  });

  int get _flagged => widget.items.where((i) => (_deviation(i) ?? 0) > widget.threshold).length;

  Future<void> _submit() async {
    setState(() => _submitting = true);
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/deliveries/${widget.deliveryId}/confirm-receipt', {
        'received_quantities': {
          for (final entry in _controllers.entries) '${entry.key}': entry.value.text.trim(),
        },
      }),
      success: _flagged > 0 ? 'Receipt recorded. Discrepancies were reported.' : 'Receipt confirmed.',
    );
    if (!mounted) return;
    setState(() => _submitting = false);
    if (ok) await widget.onConfirmed();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SectionHeader(icon: Icons.fact_check_outlined, label: 'Confirm what arrived'),
        for (final item in widget.items) ...[
          Builder(
            builder: (context) {
              final ingredient = widget.ingredients[item['ingredient_id']];
              final unit = ingredient?['unit'] ?? '';
              final dev = _deviation(item);
              final entered = double.tryParse(_controllers[item['item_id']]!.text.trim());
              final negative = entered != null && entered < 0;
              final off = dev != null && dev > widget.threshold;
              final expected = asDouble(item['expected_quantity']);
              return Card(
                shape: off
                    ? RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                        side: const BorderSide(color: Severity.critical, width: 1.5),
                      )
                    : null,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        ingredient?['name'] as String? ?? 'Ingredient #${item['ingredient_id']}',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      Text('Ordered ${trimNum(expected)} $unit', style: Theme.of(context).textTheme.bodySmall),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _controllers[item['item_id']],
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        onChanged: (_) => setState(() {}),
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: off || negative ? Severity.critical : null,
                        ),
                        decoration: InputDecoration(
                          labelText: 'Received',
                          suffixText: unit as String,
                          errorText: negative
                              ? 'Cannot be negative.'
                              : (entered == null && _controllers[item['item_id']]!.text.trim().isNotEmpty
                                  ? 'Enter a number.'
                                  : null),
                          helperText: off
                              ? '${dev.toStringAsFixed(0)}% ${(entered ?? 0) < expected ? 'short' : 'over'}: '
                                  'over the ${trimNum(widget.threshold)}% limit, will be reported as a discrepancy'
                              : null,
                          helperStyle: const TextStyle(color: Severity.critical, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
          const SizedBox(height: 10),
        ],
        if (_flagged > 0)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              '$_flagged item${_flagged == 1 ? '' : 's'} outside the tolerance will be reported as discrepancies.',
              style: const TextStyle(color: Severity.critical, fontWeight: FontWeight.w600),
            ),
          ),
        FilledButton(
          onPressed: _allValid && !_submitting ? _submit : null,
          child: _submitting
              ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
              : Text(_flagged > 0 ? 'Confirm and report discrepancies' : 'Confirm receipt'),
        ),
      ],
    );
  }
}
