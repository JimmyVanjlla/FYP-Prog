import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/dialogs.dart';
import '../../../core/format.dart';
import '../../../core/json.dart';
import '../../../core/theme.dart';

/// One ingredient: stock against its threshold (FR3.1/FR3.3), batches and
/// their expiry (FR3.2), manual adjustments (FR3.4), waste recording
/// (FR6.1/FR6.5) and restocking requests (FR3.5). Inventory Staff and the
/// Manager manage it; Kitchen Staff can request more; everyone else views.
class IngredientDetailScreen extends StatelessWidget {
  final int ingredientId;

  const IngredientDetailScreen({super.key, required this.ingredientId});

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthState>();
    final api = auth.api;
    final role = auth.role;
    final canManage = role == Roles.inventoryStaff || role == Roles.manager;
    final canRequest = role == Roles.kitchenStaff;

    return Scaffold(
      appBar: AppBar(title: const Text('Ingredient')),
      body: AsyncView<_Detail>(
        load: () async {
          final results = await Future.wait([
            api.getJson('/inventory/ingredients', query: {'limit': 500}),
            api.getJson('/config'),
            api.getJson('/inventory/stock-batches', query: {'ingredient_id': ingredientId, 'limit': 200}),
            api.getJson('/inventory/stock-adjustments', query: {'ingredient_id': ingredientId, 'limit': 20}),
          ]);
          final ingredient = asJsonList(results[0]).firstWhere((i) => i['ingredient_id'] == ingredientId);
          return _Detail(
            ingredient: ingredient,
            config: asJson(results[1]),
            batches: asJsonList(results[2]),
            adjustments: asJsonList(results[3]),
          );
        },
        builder: (context, d, reload) {
          final ing = d.ingredient;
          final low = ing['is_low_stock'] == true;
          final own = ing['low_stock_threshold'];
          final threshold = own ?? d.config['default_low_stock_threshold'];
          final windowDays = (d.config['near_expiry_window_days'] as num).toInt();
          final unit = ing['unit'] as String;

          return RefreshableList(
            onRefresh: reload,
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(ing['name'] as String, style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              '${trimNum(ing['current_stock'])} $unit',
                              style: Theme.of(context).textTheme.headlineSmall,
                            ),
                          ),
                          SeverityChip(
                            label: low ? 'Low stock' : 'OK',
                            color: low ? Severity.critical : Severity.ok,
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Alerts below ${trimNum(threshold)} $unit'
                        '${own == null ? ' (system default)' : ' (set for this ingredient)'}',
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              if (canManage || canRequest)
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (canManage) ...[
                      OutlinedButton.icon(
                        icon: const Icon(Icons.tune_rounded),
                        label: const Text('Adjust stock'),
                        onPressed: () => _adjust(context, ing, reload),
                      ),
                      OutlinedButton.icon(
                        icon: const Icon(Icons.notifications_active_outlined),
                        label: const Text('Set threshold'),
                        onPressed: () => _setThreshold(context, ing, reload),
                      ),
                    ],
                    if (canRequest)
                      FilledButton.icon(
                        icon: const Icon(Icons.add_shopping_cart_rounded),
                        label: const Text('Request restock'),
                        onPressed: () => _requestRestock(context, ing),
                      ),
                  ],
                ),
              const SizedBox(height: 20),
              SectionHeader(icon: Icons.layers_rounded, label: 'Batches', trailing: '${d.batches.length}'),
              if (d.batches.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text('No batches recorded. Add one when a delivery arrives to track its expiry.'),
                ),
              for (final b in d.batches)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _BatchTile(
                    batch: b,
                    unit: unit,
                    windowDays: windowDays,
                    onRecordWaste: canManage ? () => _recordWaste(context, ing, b, reload) : null,
                  ),
                ),
              if (canManage) AddRow(label: 'Add batch', onTap: () => _addBatch(context, ing, reload)),
              const SizedBox(height: 20),
              if (d.adjustments.isNotEmpty) ...[
                const SectionHeader(icon: Icons.history_rounded, label: 'Recent adjustments'),
                for (final a in d.adjustments)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Card(
                      child: ListTile(
                        dense: true,
                        title: Text(
                          '${asDouble(a['adjusted_quantity']) > 0 ? '+' : ''}${trimNum(a['adjusted_quantity'])} $unit'
                          '  ·  ${a['reason_category']}',
                        ),
                        subtitle: Text(
                          [
                            friendlyDateTime(a['timestamp']),
                            if ((a['note'] as String?)?.isNotEmpty ?? false) a['note'] as String,
                          ].join('  ·  '),
                        ),
                      ),
                    ),
                  ),
              ],
            ],
          );
        },
      ),
    );
  }

  Future<void> _adjust(BuildContext context, Json ing, Future<void> Function() reload) async {
    final api = context.read<AuthState>().api;
    final qtyController = TextEditingController();
    String reason = 'miscount';
    final formKey = GlobalKey<FormState>();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: Text('Adjust ${ing['name']}'),
          content: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: qtyController,
                  autofocus: true,
                  keyboardType: const TextInputType.numberWithOptions(signed: true, decimal: true),
                  decoration: const InputDecoration(
                    labelText: 'Adjustment (+/-)',
                    helperText: 'e.g. -2.5 for spoilage, +5 to correct a miscount',
                  ),
                  // FR3.6 — validated inline, at the point of entry.
                  validator: (v) {
                    if (v == null || v.trim().isEmpty) return 'Enter a quantity.';
                    final parsed = num.tryParse(v.trim());
                    if (parsed == null) return 'Must be a number.';
                    if (parsed == 0) return 'Cannot be zero.';
                    if (parsed < 0 && -parsed > asDouble(ing['current_stock'])) {
                      return 'Would take stock below zero.';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: reason,
                  decoration: const InputDecoration(labelText: 'Reason'),
                  items: const ['spillage', 'spoilage', 'miscount']
                      .map((r) => DropdownMenuItem(value: r, child: Text(r)))
                      .toList(),
                  onChanged: (v) => setState(() => reason = v ?? reason),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(
              onPressed: () {
                if (formKey.currentState!.validate()) Navigator.pop(context, true);
              },
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final ok = await runAction(
      context,
      () => api.recordStockAdjustment(
        ingredientId: ing['ingredient_id'] as int,
        adjustedQuantity: qtyController.text.trim(),
        reasonCategory: reason,
      ),
      success: 'Stock adjusted.',
    );
    if (ok) await reload();
  }

  Future<void> _setThreshold(BuildContext context, Json ing, Future<void> Function() reload) async {
    final api = context.read<AuthState>().api;
    final value = await promptNumber(
      context,
      title: 'Low-stock threshold',
      label: 'Alert when stock falls below',
      suffix: ing['unit'] as String,
      initial: ing['low_stock_threshold'] == null ? '' : trimNum(ing['low_stock_threshold']),
      allowEmpty: true,
      emptyHelper: 'Leave blank to use the system default.',
      check: (v) => v < 0 ? 'Cannot be negative.' : null,
    );
    if (value == null || !context.mounted) return;
    final ok = await runAction(
      context,
      () => api.patchJson('/inventory/ingredients/${ing['ingredient_id']}/threshold', {
        'low_stock_threshold': value.isEmpty ? null : value,
      }),
      success: value.isEmpty ? 'Using the system default.' : 'Threshold saved.',
    );
    if (ok) await reload();
  }

  Future<void> _addBatch(BuildContext context, Json ing, Future<void> Function() reload) async {
    final api = context.read<AuthState>().api;
    final qty = TextEditingController();
    DateTime received = DateTime.now();
    DateTime expiry = DateTime.now().add(const Duration(days: 7));
    final formKey = GlobalKey<FormState>();

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('New batch'),
          content: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: qty,
                  autofocus: true,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: InputDecoration(labelText: 'Quantity', suffixText: ing['unit'] as String),
                  validator: (v) {
                    final n = double.tryParse(v?.trim() ?? '');
                    if (n == null) return 'Enter a number.';
                    if (n <= 0) return 'Must be greater than zero.';
                    return null;
                  },
                ),
                const SizedBox(height: 12),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Received'),
                  subtitle: Text(fmtDate(received)),
                  trailing: const Icon(Icons.calendar_today_rounded),
                  onTap: () async {
                    final d = await pickDate(context, initial: received);
                    if (d != null) setState(() => received = d);
                  },
                ),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Expires'),
                  subtitle: Text(fmtDate(expiry)),
                  trailing: const Icon(Icons.event_busy_rounded),
                  onTap: () async {
                    final d = await pickDate(context, initial: expiry);
                    if (d != null) setState(() => expiry = d);
                  },
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(
              onPressed: () {
                if (!formKey.currentState!.validate()) return;
                if (expiry.isBefore(received)) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('The expiry date cannot be before the received date.')),
                  );
                  return;
                }
                Navigator.pop(context, true);
              },
              child: const Text('Add'),
            ),
          ],
        ),
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final ok = await runAction(
      context,
      () => api.postJson('/inventory/stock-batches', {
        'ingredient_id': ing['ingredient_id'],
        'quantity': qty.text.trim(),
        'received_date': fmtDate(received),
        'expiry_date': fmtDate(expiry),
      }),
      success: 'Batch added.',
    );
    if (ok) await reload();
  }

  Future<void> _recordWaste(BuildContext context, Json ing, Json batch, Future<void> Function() reload) async {
    final api = context.read<AuthState>().api;
    final available = asDouble(batch['quantity']);
    final value = await promptNumber(
      context,
      title: 'Record waste',
      label: 'Quantity wasted',
      helper: 'Out of ${trimNum(available)} ${ing['unit']} in this batch.',
      suffix: ing['unit'] as String,
      confirmLabel: 'Record',
      check: (v) {
        if (v <= 0) return 'Must be greater than zero.';
        if (v > available) return 'More than the ${trimNum(available)} delivered in this batch.';
        return null;
      },
    );
    if (value == null || !context.mounted) return;
    final ok = await runAction(
      context,
      () => api.postJson('/waste/logs', {
        'source_type': 'expiry',
        'source_ref_id': batch['batch_id'],
        'ingredient_id': ing['ingredient_id'],
        'quantity_wasted': value,
      }),
      success: 'Waste recorded. Adjust stock separately to remove it from the count.',
    );
    if (ok) await reload();
  }

  Future<void> _requestRestock(BuildContext context, Json ing) async {
    final api = context.read<AuthState>().api;
    final qty = TextEditingController();
    bool urgent = false;
    final formKey = GlobalKey<FormState>();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: Text('Request more ${ing['name']}'),
          content: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: qty,
                  autofocus: true,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: InputDecoration(labelText: 'Quantity needed', suffixText: ing['unit'] as String),
                  validator: (v) {
                    final n = double.tryParse(v?.trim() ?? '');
                    if (n == null) return 'Enter a number.';
                    if (n <= 0) return 'Must be greater than zero.';
                    return null;
                  },
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Urgent'),
                  value: urgent,
                  onChanged: (v) => setState(() => urgent = v),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(
              onPressed: () {
                if (formKey.currentState!.validate()) Navigator.pop(context, true);
              },
              child: const Text('Send request'),
            ),
          ],
        ),
      ),
    );
    if (confirmed != true || !context.mounted) return;
    await runAction(
      context,
      () => api.createRestockingRequest(
        ingredientId: ing['ingredient_id'] as int,
        quantity: qty.text.trim(),
        urgency: urgent,
      ),
      success: 'Restock request sent to Inventory.',
    );
  }
}

class _Detail {
  final Json ingredient;
  final Json config;
  final List<Json> batches;
  final List<Json> adjustments;

  _Detail({required this.ingredient, required this.config, required this.batches, required this.adjustments});
}

class _BatchTile extends StatelessWidget {
  final Json batch;
  final String unit;
  final int windowDays;
  final VoidCallback? onRecordWaste;

  const _BatchTile({required this.batch, required this.unit, required this.windowDays, this.onRecordWaste});

  @override
  Widget build(BuildContext context) {
    final expiry = parseDate(batch['expiry_date']);
    final today = DateTime.now();
    final daysLeft = expiry == null
        ? null
        : DateTime(expiry.year, expiry.month, expiry.day)
            .difference(DateTime(today.year, today.month, today.day))
            .inDays;

    late final String label;
    late final Color color;
    if (batch['status'] == 'expired' || (daysLeft != null && daysLeft < 0)) {
      label = 'Expired';
      color = Severity.critical;
    } else if (daysLeft != null && daysLeft <= windowDays) {
      label = daysLeft == 0 ? 'Expires today' : 'Expires in $daysLeft d';
      color = Severity.warning;
    } else {
      label = daysLeft == null ? 'OK' : '$daysLeft d left';
      color = Severity.ok;
    }

    return Card(
      child: ListTile(
        leading: IconBadge(icon: Icons.layers_rounded, color: color),
        title: Text('${trimNum(batch['quantity'])} $unit'),
        subtitle: Text('Received ${friendlyDate(batch['received_date'])}  ·  expires ${friendlyDate(batch['expiry_date'])}'),
        trailing: Wrap(
          spacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SeverityChip(label: label, color: color),
            if (onRecordWaste != null)
              IconButton(
                tooltip: 'Record waste',
                icon: const Icon(Icons.delete_outline_rounded),
                onPressed: onRecordWaste,
              ),
          ],
        ),
      ),
    );
  }
}
